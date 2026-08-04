"""qc_scanner — cổng QC cho ảnh chụp tài liệu.

Không crop được thì nói rõ nguyên nhân và hướng xử lý, thay vì im lặng trả ảnh
gốc. Dùng `scan_qc()` để nhận phán quyết; `scan()` là API cũ chỉ trả ảnh.
"""

__version__ = "0.2.0"

from .config import Config
from .doc import scan, scan_qc
from .qc import REASONS, Metrics, Reason, ScanError, ScanResult

__all__ = [
    "__version__",
    "Config",
    "Metrics",
    "REASONS",
    "Reason",
    "ScanError",
    "ScanResult",
    "scan",
    "scan_qc",
]
