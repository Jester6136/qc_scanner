import cv2
import imutils
import numpy as np
from imutils import perspective
from rembg.bg import remove as rembg

from .qc import ScanError

APPROX_POLY_DP_ACCURACY_RATIO = 0.02
IMG_RESIZE_H = 500.0


def scan(data):
    """Nắn phẳng tài liệu trong ảnh, trả PNG bytes.

    Ném `ScanError` (có mã lý do + hint) khi không xử lý được — KHÔNG trả None.
    rembg được gọi **đúng một lần**, ở đây, cho cả ba mặt tiền.
    """
    if not data:
        raise ScanError("FILE_EMPTY")

    processed_data = _remove_background(data)
    img_array = np.frombuffer(processed_data, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)

    if img is None:
        raise ScanError("DECODE_FAILED", "cv2.imdecode trả None sau bước tách nền")

    # Dò biên trên ảnh nhỏ cho nhanh/ổn định; nắn trên ảnh gốc để giữ độ phân giải.
    orig = img.copy()
    ratio = img.shape[0] / IMG_RESIZE_H
    img = imutils.resize(img, height=int(IMG_RESIZE_H))

    if img.ndim != 3 or img.shape[2] != 4:
        raise ScanError(
            "SUBJECT_NOT_FOUND",
            f"ảnh sau rembg không có kênh alpha (shape={img.shape})",
        )

    _, img = cv2.threshold(img[:, :, 3], 0, 255, cv2.THRESH_BINARY)
    img = cv2.medianBlur(img, 15)

    cnts = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

    outline = None
    for c in cnts:
        perimeter = cv2.arcLength(c, True)
        polygon = cv2.approxPolyDP(c, APPROX_POLY_DP_ACCURACY_RATIO * perimeter, True)
        if len(polygon) == 4:
            outline = polygon.reshape(4, 2)
            break

    if outline is None:
        result = orig
    else:
        result = perspective.four_point_transform(orig, outline * ratio)

    return _encode_png(result)


def _remove_background(data):
    try:
        return rembg(data)
    except Exception as exc:  # rembg/PIL không phân biệt được lỗi decode
        raise ScanError("DECODE_FAILED", str(exc)) from exc


def _encode_png(image):
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ScanError("DECODE_FAILED", "cv2.imencode PNG thất bại")
    return buf.tobytes()
