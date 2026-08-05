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


def corners_outside(corners, shape):
    """Góc nào lọt ra ngoài khung ảnh, và lọt bao xa (pixel). 0 nếu nằm gọn bên trong."""
    height, width = shape[:2]
    xs, ys = corners[:, 0], corners[:, 1]
    return float(
        max(0.0, -xs.min(), -ys.min(), xs.max() - (width - 1), ys.max() - (height - 1))
    )


def ink_mask(image, block_ratio=0.05, offset=15):
    """Pixel **mực** = tối hơn hẳn vùng giấy quanh nó.

    Ngưỡng thích nghi cục bộ chứ không phải ngưỡng tuyệt đối: thứ cần đếm là
    "tối hơn giấy quanh nó", không phải "tối". Nền bàn sẫm hay bóng đổ chuyển dần
    thì trung bình cục bộ cũng tối theo nên không bị tính là mực — đúng những ca
    mà ngưỡng tuyệt đối báo động giả.
    """
    gray = _gray(image)
    block = max(15, int(min(gray.shape[:2]) * block_ratio) | 1)
    mask = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, offset
    )
    return cv2.medianBlur(mask, 3)  # bỏ đốm lẻ, giữ nét chữ


def ink_at_image_border(image, corners, band_ratio=0.01, margin_px=2):
    """QC-12: có **chữ** chạy tới sát mép ảnh không, ở những cạnh tứ giác bị khung cắt.

    Chỉ xét các cạnh mà tứ giác **chạm mép ảnh** — đó mới là chỗ nội dung có thể đã
    nằm ngoài khung hình. Cạnh nào tứ giác nằm trọn trong ảnh thì biên cắt là mép
    tờ giấy do rembg tìm ra, không phải chỗ mất chữ.

    Đo trên ảnh **gốc**, không đo trên ảnh đã nắn: `warpPerspective` chèn pixel đen
    ngoài tứ giác nên dải biên ảnh nắn phần lớn là vùng đệm, không phải nội dung
    (đo thử `doc-3.out.png`: 95% cạnh trái là pixel < 30). Và chỉ đếm trong phần
    **nằm trong tứ giác** — bên ngoài là mặt bàn, tối nhưng không phải chữ.

    Trả tỉ lệ lớn nhất trong các cạnh bị chạm, `0.0` nếu không cạnh nào chạm. Lấy
    `max` chứ không lấy trung bình: mất một dòng ở **một** cạnh đã đủ hỏng bản ghi.
    """
    h, w = image.shape[:2]
    quad = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(quad, np.round(order_corners(corners)).astype(np.int32), 255)

    # Đường biên tứ giác luôn có vệt tối (mép giấy, bóng đổ, ranh giới giấy/nền) mà
    # ngưỡng thích nghi đọc thành mực, nên phải co mask trước khi đếm. Nhưng co
    # **đều** thì hỏng: nó ăn luôn vào phía mép ảnh, đúng chỗ cần soi. Co theo
    # **dọc dải** — kernel dẹt song song với mép ảnh đang xét — xoá được ranh giới
    # cắt ngang dải mà không đụng tới chiều vuông góc với khung hình.
    erode = max(3, int(round(min(h, w) * 0.01)))
    horizontal = cv2.erode(quad, np.ones((1, erode * 2 + 1), np.uint8))
    vertical = cv2.erode(quad, np.ones((erode * 2 + 1, 1), np.uint8))

    ink = ink_mask(image)
    band = max(2, int(round(min(h, w) * band_ratio)))

    #: Tỉ lệ tối thiểu của một mép ảnh mà tứ giác phải áp vào thì mới coi là bị
    #: khung cắt. Tứ giác chạm mép bằng đúng một góc thì cạnh nó cắt chéo qua dải,
    #: phần giấy còn lại chỉ là một nêm nhỏ — mẫu số bé, tỉ lệ bị chi phối bởi vệt
    #: ranh giới chứ không phải nội dung (ca `clipped_margin_only` cho 0.12 dù
    #: không mất chữ nào). Tài liệu bị khung cắt thật thì áp gần trọn mép.
    min_flush = 0.10

    best = 0.0
    for line, inner, rows, cols in (
        (quad[:, : margin_px + 1].max(axis=1), vertical, slice(None), slice(0, band)),
        (
            quad[:, w - 1 - margin_px :].max(axis=1),
            vertical,
            slice(None),
            slice(w - band, w),
        ),
        (quad[: margin_px + 1, :].max(axis=0), horizontal, slice(0, band), slice(None)),
        (
            quad[h - 1 - margin_px :, :].max(axis=0),
            horizontal,
            slice(h - band, h),
            slice(None),
        ),
    ):
        along = line > 0
        if along.mean() < min_flush:
            continue
        # Chỉ soi đoạn thật sự áp mép, không soi cả cạnh: phần tứ giác lùi vào
        # trong ảnh không bị khung cắt nên chữ ở đó không mất đi đâu cả.
        region = inner[rows, cols].copy()
        if rows == slice(None):
            region[~along, :] = 0
        else:
            region[:, ~along] = 0
        paper_px = int(np.count_nonzero(region))
        if paper_px == 0:
            continue
        inked = int(np.count_nonzero(ink[rows, cols] & region))
        best = max(best, inked / paper_px)
    return best


def _gray(image):
    if image.ndim == 2:
        return image
    channels = image.shape[2]
    if channels == 4:
        image = image[:, :, :3]
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
