"""Đầu vào PDF: mỗi trang thành một ảnh BGR, và **tránh resample bất cứ khi nào tránh được**.

Gần như mọi PDF giấy tờ đi qua đây là *một tấm ảnh scan đặt kín trang*. Cách hiển
nhiên — "render trang ở DPI nào đó" — làm hỏng đúng thứ lõi QC đang đo, vì DPI chọn
sẵn gần như không bao giờ trùng DPI thật của tấm ảnh bên trong, và mọi sai lệch đều
là một lần resample cả trang.

Đo trên một trang scan 300 DPI (`blur_score`, ngưỡng `min_blur_score` là **25**):

| Đường đi | `blur_score` |
|---|---|
| ảnh gốc, chưa qua PDF | 42.65 |
| **lấy thẳng ảnh nhúng ra** | **44.41** |
| render đúng DPI thật (300) | 36.91 |
| render lệch 1 DPI (301) | 27.38 |
| render gấp đôi (600) | **3.46** |

Dòng cuối là cả lý do file này tồn tại: chọn DPI cao hơn ảnh thật thì `blur_score`
rơi xuống 3.46 — dưới ngưỡng gấp 7 lần — và **mọi trang đều `BLURRY`**. Đó là một
lớp false-fail sinh ra hoàn toàn từ khâu đọc file, không liên quan gì tới chất lượng
tài liệu. Phóng to là bịa điểm ảnh, và bộ đo độ nét đọc đúng ra rằng chúng bị bịa.

Nên thứ tự ưu tiên là:

1. **Lấy thẳng bitmap nhúng** khi trang chỉ có đúng một đối tượng, là ảnh đó. Không
   resample một lần nào — đây là con đường duy nhất cho ra đúng điểm ảnh mà máy scan
   ghi được.
2. **Render ở đúng DPI của ảnh nhúng** khi trang còn thứ khác (hay gặp nhất: lớp chữ
   OCR vô hình của PDF "tìm kiếm được"). Mất 13% `blur_score` so với đường 1, vẫn cách
   ngưỡng rất xa.
3. **Render ở `pdf_render_dpi`** cho trang không có ảnh chiếm trọn — PDF sinh từ máy
   tính (hoá đơn điện tử, chữ vector). Không có "DPI thật" nào để bám vào.

Vì sao đường 1 đòi *trang chỉ có đúng một đối tượng* chứ không phải "có một ảnh chiếm
trọn trang": nới ra thì mọi thứ vẽ đè lên tấm scan (con dấu, chữ điền thêm bằng máy)
sẽ **biến mất không báo gì** khỏi ảnh đem chấm. Bỏ 13% độ nét đo được thì rẻ hơn
nhiều so với chấm QC trên một trang thiếu nội dung.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from .qc import ScanError


@dataclass(frozen=True)
class PdfPage:
    """Một trang đã đọc thành ảnh, **kèm cách nó được đọc**.

    `source` đi thẳng vào `Metrics.pdf_source` và ra cột CSV: khi một trang ăn
    `BLURRY` bất ngờ, biết nó đi đường `render@600` hay `embedded` là biết ngay lỗi
    nằm ở khâu đọc file hay ở chính tài liệu.
    """

    number: int
    image: np.ndarray
    source: str

#: PDF hợp lệ được phép có rác đứng trước header (spec cho phép offset), và pdfium
#: chấp nhận. Soi 1KB đầu thay vì đòi `data[:5]`.
PDF_MAGIC = b"%PDF-"


def is_pdf(data: bytes) -> bool:
    return bool(data) and PDF_MAGIC in data[:1024]


def open_document(data: bytes):
    """bytes → `PdfDocument`. Mọi lỗi thành `PDF_DECODE_FAILED`, kể cả file có mật khẩu."""
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
        count = len(doc)
    except Exception as exc:
        raise ScanError("PDF_DECODE_FAILED", str(exc)) from exc
    if count == 0:
        raise ScanError("PDF_NO_PAGES")
    return doc


def page_count(data: bytes) -> int:
    doc = open_document(data)
    try:
        return len(doc)
    finally:
        doc.close()


def page_images(data: bytes, cfg):
    """Sinh `PdfPage` cho từng trang, theo thứ tự.

    Trần `pdf_max_pages` **ném lỗi** chứ không cắt bớt: trả về 20 trang đầu của một
    file 200 trang mà không nói gì là đúng kiểu hỏng âm thầm mà cả dự án này tránh —
    phía gọi tưởng đã soi hết.
    """
    doc = open_document(data)
    try:
        count = len(doc)
        if count > cfg.pdf_max_pages:
            raise ScanError(
                "PDF_TOO_MANY_PAGES",
                f"{count} trang, trần hiện tại {cfg.pdf_max_pages}",
            )
        for index in range(count):
            page = doc[index]
            try:
                image, source = _page_to_bgr(page, cfg)
            finally:
                page.close()
            yield PdfPage(number=index + 1, image=image, source=source)
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# Một trang → một ảnh


def _page_to_bgr(page, cfg):
    image = _sole_full_page_image(page, cfg)
    if image is not None:
        if _is_upright(image):
            bgr = _bitmap_to_bgr(image.get_bitmap())
            if bgr is not None:
                return bgr, "embedded"
        # Ảnh bị xoay/lật khi đặt vào trang: bitmap thô không còn đúng chiều hiển thị,
        # nên phải render. Nhưng vẫn render ở DPI **của chính nó**, không phải mặc định.
        dpi = _native_dpi(image)
        if dpi:
            return _render(page, min(dpi, cfg.pdf_max_dpi))
    return _render(page, cfg.pdf_render_dpi)


def _sole_full_page_image(page, cfg):
    """Đối tượng ảnh duy nhất phủ gần kín trang — hoặc None.

    "Duy nhất" tính trên **mọi** loại đối tượng, không riêng ảnh: xem docstring module.
    """
    import pypdfium2 as pdfium

    objects = list(page.get_objects())
    if len(objects) != 1:
        return None
    obj = objects[0]
    if not isinstance(obj, pdfium.PdfImage):
        return None

    page_w, page_h = page.get_size()
    if page_w <= 0 or page_h <= 0:
        return None
    left, bottom, right, top = obj.get_pos()
    coverage = abs(right - left) * abs(top - bottom) / (page_w * page_h)
    return obj if coverage >= cfg.pdf_page_image_coverage else None


def _is_upright(image) -> bool:
    """Ma trận đặt ảnh chỉ có phóng to dương, không xoay/lật.

    Chỉ khi đó bitmap thô mới trùng đúng thứ người đọc PDF nhìn thấy.
    """
    try:
        m = image.get_matrix()
    except Exception:
        return False
    return m.b == 0 and m.c == 0 and m.a > 0 and m.d > 0


def _native_dpi(image):
    """DPI **thật** của ảnh nhúng khi đặt lên trang, hoặc None nếu không đọc được."""
    try:
        meta = image.get_metadata()
    except Exception:
        return None
    dpi = max(float(meta.horizontal_dpi), float(meta.vertical_dpi))
    # Không có sàn: ảnh nhúng 72 DPI thì trang đó **thật sự** thấp phân giải, và
    # `LOW_RESOLUTION` nói đúng chuyện đó. Render bù lên chỉ là bịa điểm ảnh rồi
    # giấu mất một tài liệu không đọc nổi.
    return dpi if dpi > 0 else None


def _render(page, dpi):
    bgr = _bitmap_to_bgr(page.render(scale=float(dpi) / 72.0))
    if bgr is None:
        raise ScanError("PDF_DECODE_FAILED", f"không render được trang ở {dpi:.0f} DPI")
    return bgr, f"render@{dpi:.0f}"


def _bitmap_to_bgr(bitmap):
    """Bitmap pdfium → mảng BGR **của riêng ta**.

    `.copy()` không phải cho vui: `to_numpy()` trả về *view* vào bộ nhớ pdfium quản lý,
    và bộ nhớ đó biến mất khi trang/tài liệu đóng. Không copy thì mảng trả ra trỏ vào
    vùng đã giải phóng — hỏng ngẫu nhiên, không exception nào.
    """
    array = bitmap.to_numpy()
    if array.ndim == 2:
        return cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
    channels = array.shape[2]
    if channels == 3:
        return array.copy()
    if channels != 4:
        return None
    if bitmap.format == 4:  # BGRx — kênh thứ tư là đệm, không mang thông tin
        return array[:, :, :3].copy()
    return _composite_on_white(array)


def _composite_on_white(bgra):
    """Ghép BGRA lên nền **trắng**, không phải đen.

    Chỗ trong suốt trong một trang giấy tờ là chỗ chưa vẽ gì lên, tức là giấy. Ghép lên
    nền đen thì `median_brightness` tụt và trang sạch ăn `TOO_DARK`.
    """
    alpha = bgra[:, :, 3:4].astype(np.float32) / 255.0
    color = bgra[:, :, :3].astype(np.float32)
    return (color * alpha + 255.0 * (1.0 - alpha)).round().astype(np.uint8)
