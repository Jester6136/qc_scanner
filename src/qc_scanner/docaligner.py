"""DocAligner — hồi quy trực tiếp 4 góc, để **đánh giá** cạnh `rembg-contour`.

Vì sao tự chạy ONNX thay vì `pip install docaligner-docsaid`:

* Gói đó kéo theo `capybara-docsaid`, và **tải mô hình từ Google Drive lúc chạy
  lần đầu**. Khách hàng chạy trong mạng nội bộ không ra Internet ([EX-12]), nên
  một phụ thuộc tải-lúc-chạy là hỏng ngay từ đầu, chưa nói tới việc Google Drive
  giới hạn lượt tải. Tiền xử lý của nó vỏn vẹn là resize + chia 255, chép lại
  rẻ hơn nhiều so với gánh cả cây phụ thuộc.
* Ta đã có `onnxruntime` cho rembg. Không thêm phụ thuộc nào.

Mô hình vẫn là Apache-2.0 (DocsaidLab/DocAligner). File `.onnx` phải tự tải rồi
trỏ `QC_SCANNER_DOCALIGNER_MODEL` vào — **không** tải tự động, đúng lý do trên.
"""

import threading

import cv2
import numpy as np

#: Cả hai kiến trúc đều chạy ở đúng 256×256. Đây là **hằng số của mô hình**, không
#: phải tham số chỉnh được: đồ thị ONNX cố định kích thước đầu vào.
INPUT_SIZE = 256

_sessions = {}
_lock = threading.Lock()


def _session(model_path, providers=""):
    """Nạp một lần rồi giữ lại — nạp ONNX tốn hơn chạy suy luận nhiều lần."""
    key = (model_path, providers)
    with _lock:
        if key not in _sessions:
            import onnxruntime as ort

            names = [p for p in providers.split(",") if p] or None
            _sessions[key] = ort.InferenceSession(model_path, providers=names)
        return _sessions[key]


def _preprocess(image):
    """BGR bất kỳ cỡ → NCHW float32 [0,1] ở 256×256.

    Chép từ `docaligner/*/infer.py`: resize thẳng, KHÔNG giữ tỉ lệ khung. Nghe như
    một lỗi, nhưng mô hình được huấn luyện đúng như thế — "sửa" thành letterbox là
    đưa vào phân phối ảnh mà nó chưa từng thấy.
    """
    resized = cv2.resize(image, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_AREA)
    if resized.ndim == 2:
        resized = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
    tensor = np.transpose(resized, (2, 0, 1)).astype(np.float32) / 255.0
    return tensor[None]


def predict_point(model_path, image, providers=""):
    """Nhánh `point_reg` (lcnet050): trả thẳng 8 số + một điểm `has_obj`.

    Trả `(corners, confidence)` theo hệ toạ độ của `image`, hoặc `(None, conf)` khi
    mô hình nói không thấy tài liệu nào.
    """
    session = _session(model_path, providers)
    outputs = session.run(None, {"img": _preprocess(image)})
    named = {o.name: v for o, v in zip(session.get_outputs(), outputs)}
    has_obj = float(np.ravel(named["has_obj"])[0])
    if has_obj <= 0.5:
        return None, has_obj

    h, w = image.shape[:2]
    points = np.asarray(named["points"], dtype=np.float32).reshape(4, 2)
    return points * np.array([w, h], dtype=np.float32), has_obj


def predict_heatmap(model_path, image, providers="", threshold=0.3):
    """Nhánh `heatmap_reg` (fastvit_sa24): 4 bản đồ nhiệt, mỗi góc một bản.

    Toạ độ góc = **trọng tâm của vùng liên thông lớn nhất** trong bản đồ đã ngưỡng
    hoá, không phải argmax. Bản gốc làm vậy và nó đúng: argmax nhảy theo một pixel
    nhiễu duy nhất, còn trọng tâm lấy trung bình cả vùng nên mượt hơn hẳn.

    Độ tin cậy = đỉnh **thấp nhất** trong 4 bản đồ. Một tứ giác chỉ chắc bằng góc
    yếu nhất của nó — lấy trung bình sẽ giấu mất đúng cái góc đang hỏng.
    """
    session = _session(model_path, providers)
    heatmaps = session.run(None, {"img": _preprocess(image)})[0][0]

    h, w = image.shape[:2]
    corners, peaks = [], []
    for plane in heatmaps[:4]:
        peaks.append(float(plane.max()))
        resized = cv2.resize(plane, (w, h), interpolation=cv2.INTER_LINEAR)
        mask = (resized >= threshold).astype(np.uint8)
        if not mask.any():
            return None, min(peaks)
        count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
        if count < 2:
            return None, min(peaks)
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        corners.append(centroids[largest])

    return np.asarray(corners, dtype=np.float32), min(peaks)
