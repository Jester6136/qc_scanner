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

import contextlib
import os
import threading

import cv2
import numpy as np
from PIL import Image
from rembg import new_session
from rembg.bg import remove as _rembg_remove

_lock = threading.Lock()
_sessions = {}

#: Tên provider được coi là chạy trên phần cứng tăng tốc.
ACCELERATED = ("CUDA", "Tensorrt", "TensorRT", "ROCM", "MIGraphX")

#: Bao nhiêu lần suy luận được lên GPU cùng lúc. **Tách riêng khỏi số ảnh xử lý đồng
#: thời** — đó là cả điểm của biến này.
#:
#: Đo trên máy H100 thật: phần CPU chiếm 62% thời gian mỗi ảnh, phần GPU 38%. Nên
#: muốn chạy nhanh thì phải cho nhiều ảnh làm việc CPU song song. Nhưng bộ nhớ GPU là
#: tài nguyên **dùng chung và có hạn** — trên chính máy đó, một service vLLM đã chiếm
#: sẵn 77.8/81.5 GB, chỉ chừa lại ~2.9GB. Thả 16 lần suy luận cùng lúc vào chỗ đó thì
#: nhận `CUBLAS_STATUS_ALLOC_FAILED`.
#:
#: Hai giới hạn cho hai tài nguyên khác nhau: `MAX_CONCURRENCY` theo số nhân CPU,
#: `GPU_CONCURRENCY` theo VRAM còn trống. Gộp làm một thì luôn phải hy sinh một bên.
GPU_CONCURRENCY = max(1, int(os.environ.get("QC_SCANNER_GPU_CONCURRENCY", "2")))
_gpu_slots = threading.BoundedSemaphore(GPU_CONCURRENCY)

#: Trần bộ nhớ GPU cho onnxruntime, tính bằng MB. 0 = không đặt trần.
#:
#: Đáng đặt khi GPU dùng chung: mặc định onnxruntime để arena tự lớn dần và có thể
#: giành hết phần còn trống, làm service bên cạnh chết theo. Đặt trần thì phần vượt
#: rơi về CPU thay vì làm sập cả hai.
GPU_MEM_LIMIT_MB = int(os.environ.get("QC_SCANNER_GPU_MEM_LIMIT_MB", "0"))


def _parse_providers(providers):
    """`"CUDAExecutionProvider,CPUExecutionProvider"` → list; rỗng → để rembg tự chọn."""
    if not providers:
        return None
    if isinstance(providers, str):
        providers = providers.split(",")
    return [p.strip() for p in providers if p.strip()] or None


def _with_options(names):
    """Gắn `gpu_mem_limit` vào provider CUDA nếu có khai trần bộ nhớ."""
    if not names or not GPU_MEM_LIMIT_MB:
        return names
    out = []
    for name in names:
        if name == "CUDAExecutionProvider":
            out.append(
                (
                    name,
                    {
                        "gpu_mem_limit": GPU_MEM_LIMIT_MB * 1024 * 1024,
                        # Xin đúng phần cần thay vì nhân đôi arena mỗi lần thiếu —
                        # trên GPU chật thì lần nhân đôi đó chính là lần chết.
                        "arena_extend_strategy": "kSameAsRequested",
                    },
                )
            )
        else:
            out.append(name)
    return out


def get_session(model_name: str = "u2net", providers=None):
    wanted = _parse_providers(providers)
    key = (model_name, tuple(wanted) if wanted else None, GPU_MEM_LIMIT_MB)
    session = _sessions.get(key)
    if session is None:
        with _lock:
            session = _sessions.get(key)
            if session is None:
                kwargs = {"providers": _with_options(wanted)} if wanted else {}
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


def segment_mask(
    image_bgr: np.ndarray,
    model_name: str = "u2net",
    providers=None,
    at_model_size: bool = False,
):
    """Ảnh BGR → mask xám **cùng kích thước** (0–255).

    Trả mask chứ không trả ảnh đã ghép alpha: lõi QC chỉ dùng mask, và tránh
    ghép/mã hoá/giải mã lại chính là chỗ tiết kiệm (xem docstring module).
    """
    session = get_session(model_name, providers)
    pil = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))

    # SPD-7: hạ ảnh về đúng kích thước model **trước khi** đưa vào `predict()`.
    #
    # `predict()` làm hai việc đắt mà không ai xin: LANCZOS hạ ảnh gốc xuống
    # 320×320, rồi LANCZOS **phóng mask 320×320 ngược lên đúng kích thước ảnh gốc**.
    # Phép phóng thứ hai là công toi hoàn toàn — lõi QC nhận xong hạ ngay về
    # `work_height`. Với ảnh điện thoại 3024×4032 nó tốn ~26ms/ảnh, và tỉ lệ với số
    # pixel nên ảnh càng nét càng đắt.
    #
    # Mẹo ở đây: nếu ta tự resize xuống đúng 320×320 (cùng LANCZOS, cùng tham số),
    # thì bên trong `predict()` cả hai phép resize đều thành **no-op** — PIL trả
    # `copy()` khi kích thước đã khớp. Tensor đưa vào model **không đổi một bit**,
    # nên mask 320×320 ra cũng y hệt. Chỉ khác chặng resample cuối: 320→work thay vì
    # 320→gốc→work. Đo trên 37 ảnh thật để chắc chuyện đó không đổi phán quyết.
    #
    # Kích thước lấy từ chữ ký ONNX chứ không hardcode 320: model khác thì khác
    # (isnet dùng 1024). Không đọc được thì bỏ qua tối ưu, chạy đường cũ.
    #
    # Mặc định TẮT: chặng resample đổi làm metric trôi ~0.14%, và có đúng một ảnh
    # thật nằm cách ngưỡng 0.02% nên lật thành false fail. Xem `Config
    # .segment_at_model_size` để biết số đo đầy đủ trước khi bật.
    target = _model_input_size(session) if at_model_size else None
    if target is not None:
        pil = pil.resize(target, Image.Resampling.LANCZOS)

    # Chỉ chặn khi thật sự chạy trên GPU. Trên CPU thì `MAX_CONCURRENCY` đã chặn rồi,
    # thêm một van nữa chỉ làm chậm mà không giữ được gì.
    gate = _gpu_slots if _is_accelerated(session) else contextlib.nullcontext()
    with gate:
        mask = session.predict(pil)[0]
    return np.asarray(mask)


def _model_input_size(session):
    """(rộng, cao) mà model mong đợi, hoặc None nếu trục không cố định."""
    try:
        shape = session.inner_session.get_inputs()[0].shape
    except Exception:
        return None
    if len(shape) != 4:
        return None
    height, width = shape[2], shape[3]
    if not isinstance(height, int) or not isinstance(width, int):
        return None
    return (width, height)


def _is_accelerated(session) -> bool:
    return any(p.startswith(ACCELERATED) for p in session.inner_session.get_providers())


def remove_background(data: bytes, model_name: str = "u2net", providers=None) -> bytes:
    """Đường cũ `bytes -> bytes PNG RGBA`. Lõi QC **không** dùng nữa (xem `segment_mask`).

    Giữ lại vì đây là API công khai từ trước và có người gọi trực tiếp; ai cần đúng
    ảnh đã tách nền ở nguyên kích thước thì vẫn dùng được.
    """
    return _rembg_remove(data, session=get_session(model_name, providers))


def warmup(model_name: str = "u2net", providers=None) -> None:
    """Nạp model sẵn lúc khởi động — bỏ độ trễ (và rủi ro timeout) của request đầu."""
    get_session(model_name, providers)
