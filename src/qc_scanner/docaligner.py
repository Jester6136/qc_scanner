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

import hashlib
import os
import pathlib
import shutil
import threading
import urllib.request

import cv2
import numpy as np

#: File mô hình cho từng nhánh, kèm id Google Drive của tác giả.
#:
#: Tải **lúc build image**, không bao giờ lúc chạy — khách chạy trong mạng nội bộ
#: không ra Internet ([EX-12]), và một phụ thuộc tải-lúc-chạy sẽ hỏng ở đúng nơi
#: khó gỡ nhất: máy khách, lần chạy đầu, sau khi đã bàn giao. Cùng lý do rembg
#: được nướng sẵn vào image.
#: SHA-256 ghim vào đây, không phải để chống kẻ tấn công mà để chống **thất bại im
#: lặng**: Google Drive khi bị giới hạn lượt tải trả về một trang HTML kèm HTTP
#: **200**. Không kiểm thì trang HTML đó được ghi thành file `.onnx`, `docker build`
#: báo thành công, và lỗi chỉ lộ ra trên máy khách dưới dạng một thông báo parse
#: ONNX khó hiểu — với một image đã bàn giao. Đổi lại, ghim băm cũng khoá luôn việc
#: tác giả thay file trên Drive mà ta không hay.
MODELS = {
    "heatmap": (
        "fastvit_sa24_heatmap.onnx",
        "14vUH77v6yGg7zFctUgcT6BzV5Iisg4Dl",
        "7f9f5a8935b2eb22b3ee0245d34996063f54562df390d34714af2d76928695bc",
    ),
    "point": (
        "lcnet050_point.onnx",
        "1J7cRuupeEIudYrH_CCSV9WvFfu9JM_qU",
        "32d186080ce16442674d4c0eaaaaac878eea289b56a8d1284f05fff1ff42e220",
    ),
}

#: Nơi chứa mô hình. Đặt tên theo lối `U2NET_HOME` của rembg cho nhất quán.
HOME_ENV = "DOCALIGNER_HOME"
DEFAULT_HOME = "~/.cache/qc-scanner/docaligner"


def model_home():
    return pathlib.Path(os.environ.get(HOME_ENV) or DEFAULT_HOME).expanduser()


def resolve_model(head, configured=""):
    """Đường dẫn file `.onnx`, hoặc `None` nếu chưa có sẵn.

    Trả `None` thay vì tự tải: hàm này chạy trong đường xử lý request, và một
    request đầu tiên treo vài chục giây để tải 83MB là kiểu hỏng tệ hơn báo lỗi.
    """
    if configured:
        path = pathlib.Path(configured).expanduser()
        return path if path.exists() else None
    name = MODELS[head][0]
    path = model_home() / name
    return path if path.exists() else None


def digest(path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def fetch(head, dest=None):
    """Tải mô hình về. Gọi lúc **build image** hoặc lúc dựng máy dev, không lúc chạy.

    Tải vào file tạm rồi mới đổi tên: một lần tải đứt giữa chừng không được phép
    để lại thứ trông như đã tải xong. Kiểm SHA-256 trước khi đổi tên — xem `MODELS`
    về lý do (Drive trả HTML kèm HTTP 200 khi bị giới hạn lượt tải).
    """
    name, file_id, expected = MODELS[head]
    target = pathlib.Path(dest or model_home()) / name
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        if digest(target) == expected:
            return target
        # File có sẵn nhưng sai băm: hỏng, tải dở, hoặc bản khác. Tải lại thay vì
        # dùng bừa — "đã có file" không phải là "đã có model".
        target.unlink()

    url = (
        "https://drive.usercontent.google.com/download"
        f"?id={file_id}&export=download&confirm=t"
    )
    staging = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url) as response, open(staging, "wb") as fh:
        shutil.copyfileobj(response, fh)

    actual = digest(staging)
    if actual != expected:
        size = staging.stat().st_size
        head_bytes = staging.read_bytes()[:200]
        staging.unlink()
        hint = ""
        if b"<html" in head_bytes.lower():
            hint = (
                " — nội dung trả về là HTML, gần như chắc chắn Google Drive đang "
                "giới hạn lượt tải. Thử lại sau, hoặc tải tay rồi trỏ "
                f"{HOME_ENV} vào thư mục chứa file."
            )
        raise RuntimeError(
            f"tải {name} về nhưng SHA-256 không khớp "
            f"(nhận {actual[:16]}…, {size} byte; cần {expected[:16]}…){hint}"
        )

    staging.rename(target)
    return target

#: Cả hai kiến trúc đều chạy ở đúng 256×256. Đây là **hằng số của mô hình**, không
#: phải tham số chỉnh được: đồ thị ONNX cố định kích thước đầu vào.
INPUT_SIZE = 256


def main(argv=None):
    """`qc-scanner-fetch-models` — tải mô hình về máy này.

    Bước BUILD, không phải bước chạy. Dockerfile gọi nó để nướng mô hình vào image.
    """
    import argparse

    ap = argparse.ArgumentParser(description=main.__doc__.splitlines()[0])
    ap.add_argument("--head", choices=sorted(MODELS), action="append")
    ap.add_argument("--dest", help=f"Mặc định ${HOME_ENV} hoặc {DEFAULT_HOME}")
    args = ap.parse_args(argv)

    for head in args.head or ["heatmap"]:
        path = fetch(head, args.dest)
        print(f"{head}: {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return 0

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
