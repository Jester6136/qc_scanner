"""Fixture dùng chung: cặp (ảnh vào, ảnh mẫu đã duyệt) trong examples/.

`scan()` gọi rembg (~3s/ảnh) nên mọi kết quả được cache theo session — bộ test
chạy rembg đúng một lần cho mỗi ảnh.
"""

import os
import pathlib
from dataclasses import dataclass

import cv2
import numpy as np
import pytest

# Bộ test cũ nói về **hợp đồng API**, không nói về xác thực, nên nó chạy ở chế độ
# mở. Đặt ở đây — trước khi bất kỳ test nào import `cmd.server` — vì module đó đọc
# cấu hình xác thực đúng một lần lúc nạp.
#
# Xác thực có bài riêng (`test_auth.py`), và bài đó nạp lại module với key thật.
# Trộn hai thứ vào nhau thì mỗi test API lại phải mang theo một header, và cái giá
# là: hôm nào xác thực hỏng, hàng chục bài đỏ cùng lúc mà không bài nào chỉ đúng
# nguyên nhân.
os.environ.setdefault("QC_SCANNER_AUTH", "off")

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


@dataclass(frozen=True)
class Pair:
    name: str
    input_path: pathlib.Path
    expected_path: pathlib.Path

    @property
    def input_bytes(self) -> bytes:
        return self.input_path.read_bytes()


def _pairs():
    out = []
    for expected in sorted(EXAMPLES.glob("doc-*.out.png")):
        stem = expected.name[: -len(".out.png")]
        candidates = [
            p
            for p in EXAMPLES.glob(f"{stem}.*")
            if not p.name.endswith(".out.png")
        ]
        if candidates:
            out.append(Pair(stem, candidates[0], expected))
    return out


PAIRS = _pairs()


@pytest.fixture(scope="session", params=PAIRS, ids=lambda p: p.name)
def pair(request):
    return request.param


@pytest.fixture(scope="session")
def scan_cache_qc():
    """name -> ScanResult, tính một lần cho cả session."""
    from qc_scanner.doc import scan_qc

    return {p.name: scan_qc(p.input_bytes) for p in PAIRS}


@pytest.fixture(scope="session")
def scan_cache(scan_cache_qc):
    """name -> PNG bytes."""
    return {name: r.image for name, r in scan_cache_qc.items()}


@pytest.fixture(scope="session")
def scan_cache_contour():
    """name -> PNG bytes, nhánh `rembg-contour` với QC-17 BẬT.

    Cặp đôi của `scan_cache_inscribed`: hai fixture này chỉ khác nhau đúng ở QC-17,
    nên hiệu của chúng đo được QC-17 và không đo gì khác. Không thể dùng
    `scan_cache` (mặc định) cho việc đó nữa — mặc định nay là `docaligner`, vốn
    không trả contour nên QC-17 không chạy, và phép so sẽ thành so hai detector
    khác nhau chứ không phải so bật/tắt một tính năng.
    """
    from qc_scanner.config import Config
    from qc_scanner.doc import scan_qc

    config = Config(detector="rembg-contour", deskew=False)
    return {p.name: scan_qc(p.input_bytes, config=config).image for p in PAIRS}


@pytest.fixture(scope="session")
def scan_cache_inscribed():
    """name -> PNG bytes, với QC-17 và QC-19 TẮT (cắt theo tứ giác nội tiếp, không xoay).

    Ảnh `examples/*.out.png` là đầu ra của thuật toán gốc, nên bộ hồi quy so byte
    với chúng phải chạy ở đúng chế độ đó. QC-17 (nới cạnh bao mép giấy cong) và QC-19
    (nắn thẳng phần dư) đều **cố ý** đổi khung cắt — kiểm chúng bằng bài riêng, chứ
    không bằng cách dời mốc so sánh.

    Đã thử dựng lại `examples/*.out.png` bằng pipeline đầy đủ và **đó là việc sai**:
    mốc hồi quy khi ấy trôi theo mọi tính năng mới, nên nó thôi phát hiện được thứ nó
    sinh ra để phát hiện — chất lượng tụt dần một cách im lặng. Mốc phải đứng yên;
    thứ thay đổi là danh sách tính năng được tắt ở đây, và mỗi dòng tắt là một tính
    năng đã có bài kiểm riêng.

    `detector` cũng bị ghim, cùng lý do: `examples/*.out.png` là đầu ra của
    `rembg-contour`, nên bộ hồi quy phải tiếp tục hỏi *"nhánh đó còn chạy đúng
    như cũ không"*. Mặc định đã chuyển sang `docaligner`, và chất lượng của nhánh
    mới được đo bằng IoU trên tập vàng SmartDoc — đó mới là bài kiểm hợp với nó,
    chứ không phải so byte với ảnh do nhánh cũ sinh ra.
    """
    from qc_scanner.config import Config
    from qc_scanner.doc import scan_qc

    config = Config(
        detector="rembg-contour", contain_paper_contour=False, deskew=False
    )
    return {p.name: scan_qc(p.input_bytes, config=config).image for p in PAIRS}


def decode(png_bytes, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.frombuffer(png_bytes, np.uint8), flags)


def gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
