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


#: Đuôi file ảnh — thư mục gốc nào chứa những thứ này là thư mục ảnh thật.
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".pdf"}

#: Thư mục ảnh ĐƯỢC PHÉP vào image: ảnh mẫu tự dựng, không phải giấy tờ của ai.
_ALLOWED_IMAGE_DIRS = {"examples"}


def _dockerignore_patterns(name=".dockerignore"):
    """Mẫu loại trừ, đã bỏ `/` đầu-cuối để so được bằng `fnmatch`.

    `.gitignore` cho phép `tmp/` và `/tmp`; cả hai đều nói về cùng một thư mục.
    """
    return [
        line.strip().strip("/")
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _ignored(path_name, patterns):
    import fnmatch

    return any(fnmatch.fnmatch(path_name, pat) for pat in patterns)


#: Mọi file ignore phải chặn ảnh khách. `.gitignore` là hàng rào **nguy hiểm nhất**:
#: ảnh lọt vào image thì build lại là xong, lọt vào lịch sử git thì xoá đi cũng không
#: thật sự mất. Các file `*.dockerignore` đứng riêng vì BuildKit ưu tiên
#: `<tên-Dockerfile>.dockerignore` khi có, và khi đó bản chung **không** được đọc —
#: mỗi file là một hàng rào độc lập, phải tự đứng vững.
def _ignore_files():
    return sorted(p.name for p in ROOT.glob("*.dockerignore")) + [
        ".dockerignore",
        ".gitignore",
    ]


#: Tên thư mục nháp chứa ảnh khách. Đây là **quy ước đặt tên**, không phải danh sách
#: thư mục đang tồn tại — chính vì thế nó kiểm được ở nơi chưa có thư mục nào.
_SCRATCH_DIR_NAMES = ["tmp", "tmp_2", "tmp_3", "tmp_9", "tmp_99", "tmp-moi"]


def test_the_ignore_rule_covers_scratch_dirs_that_do_not_exist_yet():
    """Kiểm **quy tắc**, không kiểm thứ tình cờ có trên đĩa.

    Bản đầu của test này quét thư mục thật rồi hỏi "cái nào không bị chặn". Nó bắt
    đúng lỗi lúc đó (`tmp_3/` lọt cả `.gitignore` lẫn `.dockerignore`), nhưng chỉ
    trên **máy có ảnh khách**. Trên server và trong CI thì `tmp*` không tồn tại —
    không tìm thấy gì, không có gì để tố, test xanh mà chẳng kiểm gì. Một chốt chặn
    im lặng đúng ở nơi nó chạy tự động là chốt chặn tệ nhất: nó tạo cảm giác đã
    được kiểm.

    Nên nó hỏi câu đứng vững ở mọi checkout: *nếu mai có `tmp_4/`, hàng rào có sẵn
    sàng không.* Đó cũng là lý do các file ignore dùng glob thay vì liệt kê tay —
    danh sách liệt kê đòi hỏi ai đó nhớ ra, glob thì mặc định đã chặn.
    """
    leaking = {}
    for name in _ignore_files():
        patterns = _dockerignore_patterns(name)
        missed = [d for d in _SCRATCH_DIR_NAMES if not _ignored(d, patterns)]
        if missed:
            leaking[name] = missed

    assert not leaking, (
        f"tên thư mục nháp KHÔNG bị chặn: {leaking} — "
        "dùng glob (vd `tmp[-_]*`) thay vì liệt kê từng thư mục"
    )


def test_no_directory_on_disk_holding_real_images_escapes_the_fence():
    """Vành đai thứ hai: quét đĩa thật, bắt cả thư mục KHÔNG theo quy ước đặt tên.

    Bổ sung cho test trên chứ không thay thế: test kia kiểm quy tắc và chạy ở mọi
    nơi; test này kiểm hiện trạng và **chỉ có tác dụng trên máy có ảnh khách**. Nếu
    ai đó để ảnh vào `anh_khach/` thì glob `tmp[-_]*` không cứu được, chỉ có phép
    quét này thấy.
    """
    image_dirs = []
    for entry in ROOT.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in _ALLOWED_IMAGE_DIRS:
            continue
        if any(child.suffix.lower() in _IMAGE_SUFFIXES for child in entry.rglob("*")):
            image_dirs.append(entry.name)

    leaking = {}
    for name in _ignore_files():
        patterns = _dockerignore_patterns(name)
        missed = [d for d in image_dirs if not _ignored(d, patterns)]
        if missed:
            leaking[name] = sorted(missed)

    assert not leaking, (
        f"thư mục có ảnh nhưng KHÔNG bị chặn: {leaking} — "
        "ảnh khách sẽ vào git hoặc vào image đem giao"
    )
