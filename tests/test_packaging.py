"""§4 — đóng gói: những giả định mà chỉ Docker build mới phát hiện ra là sai.

Bài học SPD-4: image GPU build xong, chạy được, healthcheck xanh — và im lặng chạy
CPU, vì `pip install .` kéo `onnxruntime` (bản CPU) đè lên `onnxruntime-gpu`. Loại
lỗi đó không bao giờ hiện ra trong test đơn vị, nên phải chốt ở đây.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Gói runtime của ONNX — đúng chỗ hai file requirements ĐƯỢC PHÉP khác nhau.
RUNTIME_PACKAGES = {"onnxruntime", "onnxruntime-gpu", "onnxruntime-rocm", "onnx"}


def _requirements(name):
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    out = {}
    for line in lines:
        line = line.split("#")[0].strip()
        if not line:
            continue
        pkg = re.split(r"[<>=!\[]", line, maxsplit=1)[0].strip()
        out[pkg] = line
    return out


def test_gpu_requirements_only_differ_in_the_onnx_runtime():
    """`Dockerfile.gpu` cài gói bằng `--no-deps`, nên requirements-gpu.txt là **nguồn
    duy nhất** của phụ thuộc ở image GPU.

    Thêm một dep vào requirements.txt mà quên file GPU thì image GPU thiếu gói, và
    chỉ lộ ra lúc chạy. Bài này bắt sự lệch đó ngay lúc commit.
    """
    cpu = _requirements("requirements.txt")
    gpu = _requirements("requirements-gpu.txt")

    only_cpu = set(cpu) - set(gpu) - RUNTIME_PACKAGES
    only_gpu = set(gpu) - set(cpu) - RUNTIME_PACKAGES
    assert not only_cpu, f"requirements-gpu.txt thiếu: {sorted(only_cpu)}"
    assert not only_gpu, f"requirements-gpu.txt thừa: {sorted(only_gpu)}"

    for pkg in set(cpu) & set(gpu) - RUNTIME_PACKAGES:
        assert cpu[pkg] == gpu[pkg], f"{pkg} ghim khác nhau: {cpu[pkg]} vs {gpu[pkg]}"


def test_cpu_and_gpu_never_declare_the_same_onnx_runtime():
    """Hai gói dùng chung thư mục `onnxruntime/` và ghi đè lên nhau.

    Cài cả hai thì `import onnxruntime` lấy bản nào là do thứ tự cài quyết định — và
    bản CPU chạy **đúng**, chỉ chậm gấp mấy chục lần. Không có lỗi nào để lần ra.
    """
    cpu = _requirements("requirements.txt")
    gpu = _requirements("requirements-gpu.txt")
    assert "onnxruntime" in cpu and "onnxruntime-gpu" not in cpu
    assert "onnxruntime-gpu" in gpu and "onnxruntime" not in gpu


def test_gpu_dockerfile_installs_the_package_without_dependencies():
    """Chốt chính xác dòng đã gây ra sự cố trên máy H100.

    Bỏ `--no-deps` thì `setup.py` (đọc install_requires từ requirements.txt) kéo
    `onnxruntime` bản CPU vào và ghi đè lên bản GPU vừa cài xong.
    """
    text = (ROOT / "Dockerfile.gpu").read_text(encoding="utf-8")
    assert "pip install --no-cache-dir --no-deps ." in text


def test_gpu_dockerfile_checks_packaging_after_the_last_install():
    """Chốt chặn phải nằm SAU bước cài cuối cùng.

    Bản đầu đặt nó ngay sau `requirements-gpu.txt` và vì thế bỏ lọt đúng lỗi nó sinh
    ra để bắt — lúc đó bản CPU chưa được kéo vào. Một chốt chặn chạy quá sớm còn tệ
    hơn không có: nó tạo cảm giác đã được kiểm.
    """
    text = (ROOT / "Dockerfile.gpu").read_text(encoding="utf-8")
    last_install = text.rindex("pip install")
    guard = text.index("grep -qi '^onnxruntime=='")
    assert guard > last_install
