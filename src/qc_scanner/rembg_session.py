"""Tái dùng phiên rembg giữa các lần gọi (N-06).

rembg chiếm ~95% thời gian xử lý, và mặc định nó **dựng lại onnxruntime session
mỗi lần `remove()`** — nạp lại model từ đĩa cho từng ảnh. Với server và chế độ
batch, giữ session sống là đòn bẩy tốc độ chính; phần OpenCV không đáng tối ưu.

Session được cache theo tên model nên đổi model (S-1) không phải trả giá nạp lại.
"""

import threading

from rembg import new_session
from rembg.bg import remove as _rembg_remove

_lock = threading.Lock()
_sessions = {}


def get_session(model_name: str = "u2net"):
    session = _sessions.get(model_name)
    if session is None:
        with _lock:
            session = _sessions.get(model_name)
            if session is None:
                session = new_session(model_name)
                _sessions[model_name] = session
    return session


def remove_background(data: bytes, model_name: str = "u2net") -> bytes:
    return _rembg_remove(data, session=get_session(model_name))


def warmup(model_name: str = "u2net") -> None:
    """Nạp model sẵn lúc khởi động — bỏ độ trễ (và rủi ro timeout) của request đầu."""
    get_session(model_name)
