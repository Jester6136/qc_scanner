"""Tách nền: giữ phiên onnxruntime sống, và **chỉ suy luận ở kích thước làm việc**.

Hai đòn bẩy tốc độ, theo thứ tự quan trọng:

1. **Tái dùng phiên** (N-06). Mặc định rembg dựng lại onnxruntime session mỗi lần
   `remove()` — nạp lại model từ đĩa cho từng ảnh. Phiên được cache theo (tên model,
   danh sách provider) nên đổi model (S-1) hay bật GPU đều không phải trả giá nạp lại.

2. **Bỏ vòng PNG toàn cỡ** (SPD-1). `rembg.remove()` trả về *bytes PNG RGBA nguyên
   kích thước ảnh gốc*: nó giải mã lại ảnh vào bằng PIL, ghép mask thành kênh alpha,
   mã hoá PNG — rồi phía nhận `cv2.imdecode` nó ra để lấy đúng **một kênh alpha**.
   Ghép + mã hoá + giải mã lại một ảnh RGBA vài triệu pixel là công toi hoàn toàn.
   `segment_mask()` gọi thẳng `session.predict()` và lấy mask, bỏ cả ba bước.

   **Không** hạ mẫu ảnh trước khi suy luận, dù model vốn ép đầu vào về 320×320.
   Đã thử và **đo thấy tệ hơn**: đưa ảnh 500px vào thì hạ mẫu hai chặng
   (gốc→500→320) làm nhoè thêm, mask co lại thật sự chứ không chỉ khác đi —
   `abc1b13…` tụt alpha 0.666→0.606 và **thoát** `NO_CROP_DETECTED`, tức một ảnh
   không cắt được gì lọt xuống chỉ còn `warn`. Nhanh thêm 0.02s không đáng đổi lấy
   một ca lọt lưới. Giữ nguyên độ phân giải đầu vào thì mask trùng khít đường cũ:
   đo trên 37 ảnh, 36 ảnh **giống hệt từng pixel**, ảnh còn lại lệch tối đa 1/255.

Phần nặng còn lại là `inner_session.run()` — bản thân model, ~90% thời gian một lần
scan trên CPU. Đó là lý do `QC_SCANNER_ONNX_PROVIDERS` tồn tại.
"""

import threading

import cv2
import numpy as np
from PIL import Image
from rembg import new_session
from rembg.bg import remove as _rembg_remove

_lock = threading.Lock()
_sessions = {}


def _parse_providers(providers):
    """`"CUDAExecutionProvider,CPUExecutionProvider"` → list; rỗng → để rembg tự chọn."""
    if not providers:
        return None
    if isinstance(providers, str):
        providers = providers.split(",")
    return [p.strip() for p in providers if p.strip()] or None


def get_session(model_name: str = "u2net", providers=None):
    wanted = _parse_providers(providers)
    key = (model_name, tuple(wanted) if wanted else None)
    session = _sessions.get(key)
    if session is None:
        with _lock:
            session = _sessions.get(key)
            if session is None:
                kwargs = {"providers": wanted} if wanted else {}
                session = new_session(model_name, **kwargs)
                _sessions[key] = session
    return session


def active_providers(model_name: str = "u2net", providers=None) -> list[str]:
    """Provider onnxruntime **thực sự** đang chạy.

    Đáng có riêng một hàm vì cái bẫy lớn nhất của đường GPU là nó hỏng **âm thầm**:
    thiếu thư viện CUDA thì onnxruntime lặng lẽ tụt về `CPUExecutionProvider`, không
    lỗi, không cảnh báo — chỉ là chậm gấp mấy chục lần. Phải hỏi được sự thật thì
    mới phát hiện ra, nên `/healthz` báo cáo giá trị này.
    """
    return list(get_session(model_name, providers).inner_session.get_providers())


def segment_mask(image_bgr: np.ndarray, model_name: str = "u2net", providers=None):
    """Ảnh BGR → mask xám **cùng kích thước** (0–255).

    Trả mask chứ không trả ảnh đã ghép alpha: lõi QC chỉ dùng mask, và tránh
    ghép/mã hoá/giải mã lại chính là chỗ tiết kiệm (xem docstring module).
    """
    pil = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    mask = get_session(model_name, providers).predict(pil)[0]
    return np.asarray(mask)


def remove_background(data: bytes, model_name: str = "u2net", providers=None) -> bytes:
    """Đường cũ `bytes -> bytes PNG RGBA`. Lõi QC **không** dùng nữa (xem `segment_mask`).

    Giữ lại vì đây là API công khai từ trước và có người gọi trực tiếp; ai cần đúng
    ảnh đã tách nền ở nguyên kích thước thì vẫn dùng được.
    """
    return _rembg_remove(data, session=get_session(model_name, providers))


def warmup(model_name: str = "u2net", providers=None) -> None:
    """Nạp model sẵn lúc khởi động — bỏ độ trễ (và rủi ro timeout) của request đầu."""
    get_session(model_name, providers)
