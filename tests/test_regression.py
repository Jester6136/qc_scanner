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


def test_aspect_ratio_holds(pair, scan_cache):
    got = decode(scan_cache[pair.name])
    ref = cv2.imread(str(pair.expected_path))
    got_aspect = got.shape[0] / got.shape[1]
    ref_aspect = ref.shape[0] / ref.shape[1]
    assert abs(got_aspect - ref_aspect) < ASPECT_TOLERANCE, (
        f"{pair.name}: tỉ lệ khung trôi {got_aspect:.4f} vs {ref_aspect:.4f}"
    )


def test_content_matches_reference(pair, scan_cache):
    got = decode(scan_cache[pair.name])
    ref = cv2.imread(str(pair.expected_path))
    score = content_similarity(got, ref)
    assert score > NCC_THRESHOLD, f"{pair.name}: NCC {score:.4f} < {NCC_THRESHOLD}"


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
