"""Số đo hình học của một tứ giác ứng viên.

Tách riêng vì bộ lọc chọn tứ giác và bộ sinh mã lý do **dùng chung** những số
này: tính một lần, vừa để chọn ứng viên vừa để giải thích vì sao chọn/loại.
"""

import cv2
import numpy as np

A4_HEIGHT_INCHES = 11.69


def order_corners(pts):
    """Sắp 4 điểm theo thứ tự TL-TR-BR-BL."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    return np.array(
        [
            pts[np.argmin(s)],  # TL: x+y nhỏ nhất
            pts[np.argmin(diff)],  # TR: x-y lớn nhất
            pts[np.argmax(s)],  # BR
            pts[np.argmax(diff)],  # BL
        ],
        dtype=np.float32,
    )


def quad_area(quad):
    return float(abs(cv2.contourArea(np.asarray(quad, dtype=np.float32))))


def is_convex(quad):
    return bool(cv2.isContourConvex(order_corners(quad).astype(np.int32)))


def skew_ratio(quad):
    """Tỉ lệ dài/ngắn của hai cặp cạnh đối — 1.0 là chụp vuông góc hoàn hảo.

    Ảnh chụp nghiêng làm một cặp cạnh đối lệch nhau nhiều; lấy max của hai cặp.
    """
    tl, tr, br, bl = order_corners(quad)
    top = np.linalg.norm(tr - tl)
    bottom = np.linalg.norm(br - bl)
    left = np.linalg.norm(bl - tl)
    right = np.linalg.norm(br - tr)
    pairs = [(top, bottom), (left, right)]
    ratios = [max(a, b) / min(a, b) for a, b in pairs if min(a, b) > 1e-6]
    return float(max(ratios)) if ratios else float("inf")


def touches_border(quad, shape, margin=2):
    """Số góc nằm sát mép ảnh — dấu hiệu tài liệu bị cắt ngoài khung."""
    h, w = shape[:2]
    count = 0
    for x, y in order_corners(quad):
        if x <= margin or y <= margin or x >= w - 1 - margin or y >= h - 1 - margin:
            count += 1
    return int(count)


def expand(quad, px, shape):
    """Nới tứ giác ra ngoài `px` pixel theo hướng ly tâm, kẹp trong khung ảnh."""
    if px <= 0:
        return quad
    pts = order_corners(quad)
    center = pts.mean(axis=0)
    out = []
    h, w = shape[:2]
    for p in pts:
        v = p - center
        n = np.linalg.norm(v)
        p2 = p + (v / n * px if n > 1e-6 else 0)
        out.append([np.clip(p2[0], 0, w - 1), np.clip(p2[1], 0, h - 1)])
    return np.array(out, dtype=np.float32)


def iou(quad_a, quad_b, shape):
    """IoU giữa hai tứ giác, tính bằng mask raster (đủ chính xác cho mục đích QC)."""
    h, w = shape[:2]
    ma = np.zeros((h, w), np.uint8)
    mb = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(ma, order_corners(quad_a).astype(np.int32), 1)
    cv2.fillConvexPoly(mb, order_corners(quad_b).astype(np.int32), 1)
    union = np.count_nonzero(ma | mb)
    return float(np.count_nonzero(ma & mb) / union) if union else 0.0


def estimate_dpi(warped_shape):
    """DPI ước lượng, giả định tài liệu là khổ A4 dựng đứng.

    Giả định này sai với CCCD/hoá đơn — cần chốt khổ giấy thật với khách trước
    khi tin con số này.
    """
    h, w = warped_shape[:2]
    long_side = max(h, w)
    return float(long_side / A4_HEIGHT_INCHES)


def blur_score(image):
    """Variance of Laplacian — thấp = mờ."""
    gray = _gray(image)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def glare_ratio(image, threshold=250):
    gray = _gray(image)
    return float(np.count_nonzero(gray >= threshold) / gray.size)


def median_brightness(image):
    return float(np.median(_gray(image)))


def _gray(image):
    if image.ndim == 2:
        return image
    channels = image.shape[2]
    if channels == 4:
        image = image[:, :, :3]
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
