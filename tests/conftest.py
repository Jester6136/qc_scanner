"""Fixture dùng chung: cặp (ảnh vào, ảnh mẫu đã duyệt) trong examples/.

`scan()` gọi rembg (~3s/ảnh) nên mọi kết quả được cache theo session — bộ test
chạy rembg đúng một lần cho mỗi ảnh.
"""

import pathlib
from dataclasses import dataclass

import cv2
import numpy as np
import pytest

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
    """
    from qc_scanner.config import Config
    from qc_scanner.doc import scan_qc

    config = Config(contain_paper_contour=False, deskew=False)
    return {p.name: scan_qc(p.input_bytes, config=config).image for p in PAIRS}


def decode(png_bytes, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.frombuffer(png_bytes, np.uint8), flags)


def gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
