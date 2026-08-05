"""Dựng ảnh test bằng OpenCV thay vì đi xin ảnh thật.

Nhanh, tất định, chạy được ở CI, và mỗi ca hỏng dựng được đúng cái nó cần bắt.
"""

import cv2
import numpy as np


def _png(img):
    return cv2.imencode(".png", img)[1].tobytes()


def _paper(h, w, tint=245):
    """Tờ giấy sáng có chút chữ giả để không phải mặt phẳng trống trơn."""
    paper = np.full((h, w, 3), tint, np.uint8)
    for i in range(6, h - 6, max(8, h // 14)):
        cv2.line(paper, (w // 10, i), (w - w // 10, i), (70, 70, 70), max(1, h // 220))
    return paper


def document_on_dark_background(canvas=(1400, 1000), paper=(1000, 700)):
    img = np.full((canvas[0], canvas[1], 3), 25, np.uint8)
    ph, pw = paper
    y = (canvas[0] - ph) // 2
    x = (canvas[1] - pw) // 2
    img[y : y + ph, x : x + pw] = _paper(ph, pw)
    return _png(img)


def tiny_document():
    """TOO_SMALL: tờ giấy nhỏ giữa nền tối rộng.

    Diện tích phải nằm giữa `candidate_area_ratio` (0.05 — dưới mức này contour
    còn không được tính là ứng viên, và kết quả là SUBJECT_NOT_FOUND, một ca
    khác) và `min_quad_area_ratio` (0.20). Ở đây ≈ 0.10.
    """
    img = np.full((1600, 1600, 3), 25, np.uint8)
    img[590:1010, 500:1100] = _paper(420, 600)
    return _png(img)


def clipped_document():
    """CONTENT_CLIPPED: giấy tràn mép khung **và** có chữ chạy tới sát mép.

    Dòng kẻ đầu tiên của `_paper` nằm ở y=6, trong khi dải soi mực rộng 1% cạnh
    ngắn (9px) — nên chỗ bị khung cắt có nội dung thật, không phải viền trắng.
    """
    img = np.full((1200, 900, 3), 25, np.uint8)
    img[0:1100, 0:820] = _paper(1100, 820)
    return _png(img)


def clipped_margin_only():
    """CLIPPED_EDGE (warn, KHÔNG fail): giấy tràn mép khung nhưng chỉ mất viền trắng.

    Cặp đôi của `clipped_document`, dựng để chốt đúng ranh giới [EX-1]: mất viền
    thì được, mất chữ thì không. Không có ca này thì một cài đặt "cứ chạm mép là
    fail" vẫn xanh test — mà đó chính là hành vi sai cần tránh.
    """
    img = np.full((1200, 900, 3), 25, np.uint8)
    paper = np.full((950, 700, 3), 245, np.uint8)
    paper[120:-120, 120:-120] = _paper(950 - 240, 700 - 240)  # chữ lùi vào 120px
    # Chừa nền ở phải/dưới: giấy phủ kín cả 4 mép thì rembg trả nguyên khung và ca
    # này rơi sang NO_CROP_DETECTED, không còn kiểm được thứ định kiểm.
    img[0:950, 0:700] = paper
    return _png(img)


def document_fills_frame():
    """QC-15: giấy chiếm gần hết khung nhưng KHÔNG mất gì → phải `pass`.

    Chỉ chừa 10px nền quanh mép, nên `alpha_coverage` vượt `max_alpha_coverage`
    (0.95) — trước QC-15 ca này ăn `SUBJECT_FILLS_FRAME` mức `warn` dù chữ nằm
    gọn cách mép giấy 110px và không có gì bị cắt.
    """
    img = np.full((1200, 900, 3), 25, np.uint8)
    paper = np.full((1180, 880, 3), 245, np.uint8)
    paper[110:-110, 110:-110] = _paper(1180 - 220, 880 - 220)
    img[10:-10, 10:-10] = paper
    return _png(img)


def skewed_document():
    """EXTREME_SKEW: nắn ảnh bằng ma trận phối cảnh nghiêng mạnh."""
    img = np.full((1400, 1000, 3), 25, np.uint8)
    img[150:1250, 150:850] = _paper(1100, 700)
    # Hình thang mạnh: cạnh trên ngắn hơn cạnh dưới nhiều lần → skew_ratio cao.
    src = np.float32([[150, 150], [850, 150], [850, 1250], [150, 1250]])
    dst = np.float32([[400, 180], [620, 180], [950, 1280], [60, 1280]])
    warped = cv2.warpPerspective(
        img, cv2.getPerspectiveTransform(src, dst), (1000, 1400)
    )
    return _png(warped)


def two_documents():
    """MULTIPLE_DOCUMENTS: hai tờ trong cùng một khung."""
    img = np.full((1200, 1600, 3), 25, np.uint8)
    img[150:1050, 120:700] = _paper(900, 580)
    img[150:1050, 900:1480] = _paper(900, 580)
    return _png(img)


def white_on_white():
    """SUBJECT_NOT_FOUND: giấy trắng trên nền trắng — ca rembg thua nhất."""
    img = np.full((1200, 900, 3), 252, np.uint8)
    img[150:1050, 120:780] = _paper(900, 660, tint=250)
    return _png(img)


def blurry_document():
    img = cv2.imdecode(
        np.frombuffer(document_on_dark_background(), np.uint8), cv2.IMREAD_COLOR
    )
    return _png(cv2.GaussianBlur(img, (31, 31), 0))


def low_resolution_document():
    return document_on_dark_background(canvas=(400, 300), paper=(300, 200))


def dark_document():
    img = cv2.imdecode(
        np.frombuffer(document_on_dark_background(), np.uint8), cv2.IMREAD_COLOR
    )
    return _png((img * 0.16).astype(np.uint8))


def glaring_document():
    img = cv2.imdecode(
        np.frombuffer(document_on_dark_background(), np.uint8), cv2.IMREAD_COLOR
    )
    cv2.circle(img, (700, 700), 190, (255, 255, 255), -1)
    return _png(img)


def junk_bytes():
    return b"\x00\x01\x02not-an-image" * 8
