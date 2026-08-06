"""§2 — đầu ra không được trôi so với 8 ảnh mẫu đã duyệt mắt trong examples/.

KHÔNG so bằng md5: nén PNG khác version và `warpPerspective` khác build OpenCV
làm lệch vài pixel — bình thường và vô hại.

Đo **hai thứ tách bạch** vì chúng hỏng theo cách khác nhau: **tỉ lệ khung** bắt
lỗi *chọn sai tứ giác* (crop lệch → khung méo); **tương quan nội dung** bắt lỗi
*nội dung* (mất mép, xoay nhầm, nắn sai).

Ngưỡng đã chốt bằng số đo trên máy sạch (rembg 2.0.77 / opencv 5.0.0):

| doc | Δaspect | NCC   |
|-----|---------|-------|
| 1   | 0.0135  | 0.879 |
| 2   | 0.0026  | 0.980 |
| 3   | 0.0055  | 0.994 |
| 4   | 0.0000  | 0.946 |
| 5   | 0.0075  | 0.810 |
| 6   | 0.0052  | 0.965 |
| 7   | 0.0000  | 0.926 |
| 8   | 0.0281  | 0.849 |

Thiết kế ban đầu đề xuất SSIM > 0.95; **số đo bác bỏ ngưỡng đó**: SSIM tụt tới
0.36 trên các ảnh đúng (doc-5, doc-8) vì đó là ảnh chụp có **nhiễu hạt** — một
lệch dưới một pixel trong phép nắn làm xô toàn bộ vân nhiễu và SSIM sập, dù mắt
thường không phân biệt được. Dùng **NCC trên ảnh xám đã hạ mẫu + làm mờ**: cặp
đúng ≥ 0.81, còn hai tài liệu **khác nhau** cho ≈ 0.0 — vẫn bắt được hồi quy
thật mà không báo động giả vì nhiễu.
"""

import cv2
import numpy as np

from conftest import decode, gray

ASPECT_TOLERANCE = 0.04
NCC_THRESHOLD = 0.70

_NORM_WIDTH = 256
_BLUR_KSIZE = 5


def _normalize(img):
    """Xám → hạ mẫu về bề ngang cố định → làm mờ nhẹ (dập nhiễu hạt)."""
    g = gray(img)
    height = max(1, round(g.shape[0] * _NORM_WIDTH / g.shape[1]))
    g = cv2.resize(g, (_NORM_WIDTH, height), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(g, (_BLUR_KSIZE, _BLUR_KSIZE), 0)


def content_similarity(got, ref):
    """Tương quan chéo chuẩn hoá: 1.0 = trùng, ~0.0 = không liên quan."""
    a = _normalize(got)
    b = _normalize(ref)
    a = cv2.resize(a, (b.shape[1], b.shape[0]))
    af = a.astype(np.float64) - a.mean()
    bf = b.astype(np.float64) - b.mean()
    denom = np.sqrt((af * af).sum() * (bf * bf).sum())
    return float((af * bf).sum() / denom) if denom else 0.0


def test_aspect_ratio_holds(pair, scan_cache_inscribed):
    got = decode(scan_cache_inscribed[pair.name])
    ref = cv2.imread(str(pair.expected_path))
    got_aspect = got.shape[0] / got.shape[1]
    ref_aspect = ref.shape[0] / ref.shape[1]
    assert abs(got_aspect - ref_aspect) < ASPECT_TOLERANCE, (
        f"{pair.name}: tỉ lệ khung trôi {got_aspect:.4f} vs {ref_aspect:.4f}"
    )


def test_content_matches_reference(pair, scan_cache_inscribed):
    got = decode(scan_cache_inscribed[pair.name])
    ref = cv2.imread(str(pair.expected_path))
    score = content_similarity(got, ref)
    assert score > NCC_THRESHOLD, f"{pair.name}: NCC {score:.4f} < {NCC_THRESHOLD}"


# --- QC-17: nới cạnh chỉ được THÊM lề, không được bớt nội dung --------------- #


def test_containing_quad_only_adds_margin(pair, scan_cache_contour, scan_cache_inscribed):
    """Khung cắt mặc định phải **bao** khung cắt nội tiếp, không bao giờ nhỏ hơn.

    Đây là bài thay cho việc so byte với ảnh mẫu ở chế độ mặc định: QC-17 cố ý đổi
    khung cắt, nên câu hỏi đúng không còn là "có giống ảnh cũ không" mà là "có mất
    gì so với ảnh cũ không".
    """
    grown = decode(scan_cache_contour[pair.name])
    inscribed = decode(scan_cache_inscribed[pair.name])
    assert grown.shape[0] >= inscribed.shape[0]
    assert grown.shape[1] >= inscribed.shape[1]


def test_containing_quad_keeps_the_same_document(
    pair, scan_cache_contour, scan_cache_inscribed
):
    """Nới lề không được biến nó thành tài liệu khác.

    **Dò mẫu chứ không so pixel tại chỗ**: khung cắt mới rộng hơn nên nội dung cũ
    nằm lệch đi vài phần trăm, và NCC so tại chỗ tụt xuống ~0.69 dù ảnh vẫn đúng.
    Câu hỏi đúng là "ruột ảnh cũ có nằm ở đâu đó trong ảnh mới không", và
    `matchTemplate` trả lời được điều đó bất kể lệch bao nhiêu.

    Không có bài này thì `containing_quad` có thể nhảy sang một tứ giác hoàn toàn
    khác mà bài "chỉ thêm lề" ở trên vẫn xanh.
    """
    score = _contains_content(
        decode(scan_cache_contour[pair.name]), decode(scan_cache_inscribed[pair.name])
    )
    assert score > NCC_THRESHOLD, f"{pair.name}: khớp mẫu {score:.4f}"


def test_match_template_rejects_a_different_document(scan_cache, scan_cache_inscribed):
    """Chốt chặn cho chính phép đo ở trên — nó phải TRƯỢT khi đưa nhầm tài liệu."""
    names = sorted(scan_cache)
    score = _contains_content(
        decode(scan_cache[names[0]]), decode(scan_cache_inscribed[names[4]])
    )
    assert score < NCC_THRESHOLD, f"khớp nhầm hai tài liệu khác nhau: {score:.4f}"


def _contains_content(outer, inner, width=400, keep=0.6):
    """Điểm khớp cao nhất khi tìm ruột `inner` bên trong `outer`, cùng tỉ lệ."""
    scale = width / outer.shape[1]
    big = cv2.resize(gray(outer), (width, max(1, round(outer.shape[0] * scale))))
    small = cv2.resize(
        gray(inner),
        (
            max(1, round(inner.shape[1] * scale)),
            max(1, round(inner.shape[0] * scale)),
        ),
    )
    h, w = small.shape
    dy, dx = int(h * (1 - keep) / 2), int(w * (1 - keep) / 2)
    template = small[dy : h - dy, dx : w - dx]
    if template.shape[0] > big.shape[0] or template.shape[1] > big.shape[1]:
        return 0.0
    return float(cv2.matchTemplate(big, template, cv2.TM_CCOEFF_NORMED).max())


def test_metric_rejects_wrong_document(scan_cache):
    """Chốt chặn cho chính phép đo: hai tài liệu khác nhau phải KHÔNG đạt ngưỡng.

    Không có bài này thì một metric quá dễ dãi sẽ cho mọi thứ đi qua và bộ
    regression thành vô dụng.
    """
    names = sorted(scan_cache)
    a = decode(scan_cache[names[0]])
    b = decode(scan_cache[names[4]])
    assert content_similarity(a, b) < NCC_THRESHOLD


def test_output_is_png(pair, scan_cache):
    assert scan_cache[pair.name].startswith(b"\x89PNG\r\n\x1a\n")


def test_output_is_cropped(pair, scan_cache):
    """Mọi ảnh mẫu phải được nắn — kích thước khác ảnh gốc."""
    got = decode(scan_cache[pair.name])
    src = cv2.imread(str(pair.input_path))
    assert got.shape[:2] != src.shape[:2], f"{pair.name}: không nắn, trả ảnh gốc"


def test_segment_at_model_size_feeds_the_model_the_same_tensor():
    """SPD-7: bật cờ tốc độ **không được** đổi thứ model nhìn thấy.

    Cả tối ưu nằm ở chỗ ta tự làm đúng phép resize mà `normalize()` sẽ làm, để hai
    phép resize bên trong `predict()` thành no-op. Nếu PIL bỏ đường tắt "kích thước
    đã khớp thì copy" thì giả định đó sập, và mask sẽ khác đi **âm thầm**.
    """
    import numpy as np
    from PIL import Image

    from qc_scanner.rembg_session import _model_input_size, get_session

    session = get_session("u2net")
    size = _model_input_size(session)
    assert size == (320, 320), "u2net khai batch cố định 320×320 trong chữ ký ONNX"

    rng = np.random.default_rng(0)
    big = Image.fromarray(rng.integers(0, 255, (900, 700, 3), dtype=np.uint8))
    small = big.resize(size, Image.Resampling.LANCZOS)

    # Đường tắt của PIL: resize về đúng kích thước hiện tại phải cho ảnh y hệt.
    again = small.resize(size, Image.Resampling.LANCZOS)
    assert np.array_equal(np.asarray(small), np.asarray(again))

    # Và mask model trả về cũng phải y hệt.
    assert np.array_equal(
        np.asarray(session.predict(small)[0]),
        np.asarray(session.predict(again)[0]),
    )


def test_speed_flag_is_off_by_default():
    """Cờ này đánh đổi 43ms lấy một false fail đã đo được — không bật lén."""
    from qc_scanner.config import Config

    assert Config().segment_at_model_size is False
