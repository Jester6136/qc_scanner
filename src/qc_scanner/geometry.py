"""Số đo hình học của một tứ giác ứng viên.

Tách riêng vì bộ lọc chọn tứ giác và bộ sinh mã lý do **dùng chung** những số
này: tính một lần, vừa để chọn ứng viên vừa để giải thích vì sao chọn/loại.
"""

import cv2
import numpy as np

A4_HEIGHT_INCHES = 11.69

#: Chiều cao đem đo góc chữ. Đo ở 800px tốn 26.3ms trên 1669ms của cả `scan_qc`
#: (1.6%); giữ nguyên cỡ ảnh thì tốn gấp nhiều lần mà góc đọc ra không đổi — dòng
#: chữ là cấu trúc thô, không cần tới điểm ảnh gốc.
_SKEW_WORK_HEIGHT = 800


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


def text_skew_deg(image, step=1.0, limit=45.0, min_ink_ratio=0.002):
    """Góc nghiêng của **dòng chữ**, đo trên ảnh ĐÃ NẮN. `None` = không đủ mực để đo.

    Đây là phép kiểm *đầu ra*, không phải phỏng đoán *đầu vào*: mọi thứ khác trong
    module này soi tứ giác trước khi nắn và hỏi "biên có hợp lý không". Hàm này soi
    kết quả sau khi nắn và hỏi thẳng **"chữ có nằm ngang không"** — thứ duy nhất
    phía OCR thật sự cần. Nhờ vậy nó bắt được cả những kiểu hỏng chưa ai kể tên,
    miễn là chúng làm lệch chữ.

    Cách đo: nhị phân hoá thích nghi → quay thử từng góc → chọn góc làm **profile
    chiếu theo hàng** gắt nhất (`var(diff(row_sums))`). Chữ nằm ngang thì các hàng
    luân phiên đậm–nhạt rất mạnh; lệch đi thì các dòng nhoè vào nhau và profile bẹt.

    Vì sao là projection profile chứ không phải gộp ký tự thành dòng rồi đo
    `minAreaRect`: bản gộp-dòng cần một nhân hình thái **nằm ngang**, tức là nó giả
    định sẵn thứ đang cần kiểm. Đo bản đó trên chính ảnh gấp mép ra `0.0°` trong
    khi chữ lệch 24° — chữ chéo không gộp nổi thành dòng nên rơi khỏi phép đo.
    Projection profile thử mọi góc như nhau nên không có điểm mù đó.

    Cổng `min_ink_ratio` là **bắt buộc**, không phải đề phòng: trang trắng cho mọi
    góc cùng 0 điểm nên `argmax` trả về ứng viên đầu tiên, tức `-limit`. Không có
    cổng thì trang trắng bị kết luận nghiêng 45°. Ngưỡng 0.002 nằm giữa trang trắng
    (0.0000) và ca thưa chữ nhất đo được (một dòng chữ đơn: 0.0048; ảnh thật thưa
    nhất trong kho: 0.0120).

    Sai số của chính thước: **≤ 1.0°** — kiểm bằng cách quay một ảnh đã nắn đi những
    góc biết trước (0·3·5·10·15·20·24·30·−12·−25) rồi bắt nó đọc lại.
    """
    gray = _gray(image)
    height = gray.shape[0]
    if height > _SKEW_WORK_HEIGHT:
        scale = _SKEW_WORK_HEIGHT / height
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    if np.count_nonzero(ink) / ink.size < min_ink_ratio:
        return None

    ink = (ink > 0).astype(np.float32)
    h, w = ink.shape
    center = (w / 2, h / 2)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-limit, limit + 1e-9, step):
        matrix = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(
            ink, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0
        )
        score = float(np.var(np.diff(rotated.sum(axis=1))))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def deskew(image, angle):
    """Xoay ảnh đi `angle` độ, nới khung để không cắt mất góc nào (QC-19).

    `BORDER_REPLICATE` cho bốn nêm góc mới: nền quanh tài liệu có thể là mặt bàn tối,
    tô trắng vào đó là **bịa ra giấy** ở chỗ vốn không có giấy — và `median_brightness`
    lẫn `border_ink_ratio` đều đọc vùng mép.

    `INTER_CUBIC` chứ không phải `INTER_LINEAR`: ảnh này đi tiếp vào OCR, và nét chữ
    nhỏ là thứ mất trước tiên khi nội suy.
    """
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    matrix[0, 2] += new_w / 2 - w / 2
    matrix[1, 2] += new_h / 2 - h / 2
    return cv2.warpAffine(
        image,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def containing_quad(corners, contour, shape, max_grow_ratio=0.05, percentile=99.0):
    """Đẩy 4 cạnh ra ngoài cho tới khi tứ giác **bao trọn** contour (QC-17).

    `approxPolyDP` cho tứ giác **nội tiếp**: nó nối 4 góc bằng đường thẳng. Mép tờ
    giấy cong thì phần vồng ra nằm *ngoài* dây cung, và `four_point_transform` cắt
    lẹm đúng chỗ đó — ảnh thật `04.59.02` mất nguyên dòng cuối vì vậy.

    Giữ nguyên **hướng** 4 cạnh nên đầu ra vẫn là phép nắn phối cảnh 4 điểm, không
    phải dewarp lưới: rẻ, không thêm phụ thuộc, và không đụng vào phần còn lại của
    luồng. Nó KHÔNG duỗi thẳng được giấy cong — chỉ thôi cắt lẹm vào chỗ cong.

    Đổi lại là thêm chút nền quanh mép, và theo [EX-1] thì mất viền còn hơn mất chữ.
    Đo trên 45 ảnh: diện tích tăng trung vị 4.6%, nhiều nhất 17%.

    `max_grow_ratio` chặn ca bệnh lý: mask lỗi có một gai nhọn thì cạnh không bị đẩy
    ra vô hạn. Tính theo cạnh ngắn của ảnh làm việc.
    """
    pts = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
    quad = order_corners(corners).astype(np.float64)
    center = quad.mean(axis=0)
    limit = max_grow_ratio * min(shape[:2])

    lines = []
    for i in range(4):
        a, b = quad[i], quad[(i + 1) % 4]
        edge = b - a
        normal = np.array([-edge[1], edge[0]], dtype=np.float64)
        length = np.linalg.norm(normal)
        if length < 1e-9:
            return order_corners(corners)
        normal /= length
        if normal @ (a - center) < 0:  # ép pháp tuyến hướng RA NGOÀI
            normal = -normal
        # Phân vị chứ không phải cực đại: một gai đơn lẻ trên mask kéo cả cạnh ra
        # theo, và cạnh đó mang theo nền vào ảnh. Đo trên 38 ảnh thật, đổi 100 → 99
        # hạ viền nền trung bình 4.58% → 4.21% mà **không** ảnh nào bị cắt thêm
        # (lẹm > 1% giữ nguyên 4 ảnh, lẹm tối đa giữ nguyên 0.0795).
        distances = (pts - a) @ normal
        if percentile >= 100:
            reach = np.max(distances)
        else:
            reach = np.percentile(distances, percentile)
        grow = float(np.clip(reach, 0.0, limit))
        lines.append((normal, normal @ a + grow))

    grown = []
    for i in range(4):
        (n1, c1), (n2, c2) = lines[i - 1], lines[i]
        matrix = np.array([n1, n2])
        if abs(np.linalg.det(matrix)) < 1e-9:  # hai cạnh gần song song
            return order_corners(corners)
        grown.append(np.linalg.solve(matrix, np.array([c1, c2])))

    h, w = shape[:2]
    grown = np.asarray(grown, dtype=np.float32)
    grown[:, 0] = np.clip(grown[:, 0], 0, w - 1)
    grown[:, 1] = np.clip(grown[:, 1], 0, h - 1)
    return order_corners(grown)


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
