"""Hợp đồng đầu ra QC: mã lý do, Reason, ScanError.

Nguyên tắc bất biến: **mã nào cũng phải có `hint` và `audience`**. Mã không hành
động được là mã vô dụng — `REASONS` là nguồn sự thật duy nhất, và test
`test_qc_contract.py` chặn mọi mã thiếu hai trường đó.

Mã (`code`) là **ổn định vĩnh viễn** — nó đi vào log/CSV của khách. `message` và
`hint` có thể sửa/dịch.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

Severity = Literal["warn", "fail"]
Audience = Literal["capturer", "operator", "system"]
Verdict = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class ReasonSpec:
    """Định nghĩa tĩnh của một mã lý do."""

    code: str
    severity: Severity
    message: str
    hint: str
    audience: Audience


def _spec(code, severity, message, hint, audience):
    return ReasonSpec(code, severity, message, hint, audience)


#: Danh mục mã lý do. Thêm mã mới = thêm một dòng ở đây, không rải rác trong code.
REASONS: Dict[str, ReasonSpec] = {
    s.code: s
    for s in [
        # --- Đầu vào ---
        _spec(
            "FILE_EMPTY",
            "fail",
            "Không nhận được dữ liệu ảnh (0 byte).",
            "Không nhận được dữ liệu. Kiểm tra lại bước tải/upload.",
            "system",
        ),
        _spec(
            "DECODE_FAILED",
            "fail",
            "Không giải mã được dữ liệu thành ảnh.",
            "File không phải ảnh hợp lệ (hoặc đã hỏng). Kiểm tra định dạng: JPG/PNG.",
            "system",
        ),
        _spec(
            "LOW_RESOLUTION",
            "fail",
            "Độ phân giải ước lượng thấp hơn ngưỡng OCR đọc được.",
            "Ảnh quá nhỏ để OCR đọc được. Chụp lại ở độ phân giải cao hơn, "
            "hoặc lại gần tài liệu hơn.",
            "capturer",
        ),
        # --- Tách chủ thể ---
        _spec(
            "SUBJECT_NOT_FOUND",
            "fail",
            "Không tách được tờ giấy khỏi nền.",
            "Đặt tài liệu lên nền tối, tương phản (bàn sẫm màu) rồi chụp lại.",
            "capturer",
        ),
        _spec(
            "SUBJECT_FILLS_FRAME",
            "warn",
            "Tờ giấy chiếm gần hết khung hình.",
            "Tờ giấy chiếm gần hết khung, có thể đã bị cắt mất mép. "
            "Lùi ra để lộ viền nền quanh tài liệu.",
            "capturer",
        ),
        _spec(
            "RECOVERED_BY_EDGE_FALLBACK",
            "warn",
            "Đã nắn được bằng phương án dự phòng dò cạnh.",
            "Đã nắn được bằng phương án dự phòng — độ tin cậy thấp hơn, "
            "nên soi mắt thường trước khi dùng.",
            "operator",
        ),
        # --- Hình học biên ---
        _spec(
            "QUAD_NOT_FOUND",
            "fail",
            "Không tìm được tứ giác nào đạt bộ lọc hình học.",
            "Không thấy đủ 4 góc tờ giấy. Mở phẳng tài liệu, đừng để tay/vật che góc, "
            "chụp lại toàn bộ tờ.",
            "capturer",
        ),
        _spec(
            "TOO_SMALL",
            "fail",
            "Tứ giác chiếm quá ít diện tích khung hình.",
            "Tài liệu chiếm quá ít khung hình. Lại gần hơn hoặc zoom vào tài liệu.",
            "capturer",
        ),
        _spec(
            "NOT_CONVEX",
            "fail",
            "Tứ giác phát hiện được không lồi.",
            "Biên phát hiện bị méo (có thể do nếp gấp/bóng đổ). "
            "Vuốt phẳng tài liệu và chụp lại.",
            "capturer",
        ),
        _spec(
            "CLIPPED_EDGE",
            "warn",
            "Có góc tài liệu nằm sát/ngoài mép ảnh.",
            "Một phần tài liệu nằm ngoài khung hình. Lùi máy ra để thấy trọn 4 mép.",
            "capturer",
        ),
        _spec(
            "EXTREME_SKEW",
            "warn",
            "Góc chụp nghiêng mạnh, cạnh đối lệch nhau nhiều.",
            "Góc chụp quá nghiêng — chữ sẽ bị kéo giãn sau khi nắn. "
            "Chụp vuông góc từ trên xuống.",
            "capturer",
        ),
        _spec(
            "MULTIPLE_DOCUMENTS",
            "warn",
            "Phát hiện nhiều hơn một tài liệu lớn trong ảnh.",
            "Thấy nhiều hơn một tờ trong ảnh; chỉ tờ lớn nhất được xử lý. "
            "Chụp từng tờ một.",
            "capturer",
        ),
        _spec(
            "FALLBACK_ORIGINAL",
            "fail",
            "Trả ảnh gốc chưa nắn vì không dựng được tứ giác.",
            "Không nắn được, ảnh trả về là ảnh gốc chưa xử lý. Không đưa thẳng vào OCR.",
            "operator",
        ),
        _spec(
            "DETECTOR_DISAGREEMENT",
            "warn",
            "Hai detector cho tứ giác lệch nhau đáng kể.",
            "Hai phương pháp dò biên không đồng thuận — kết quả kém chắc chắn, "
            "nên soi mắt thường trước khi dùng.",
            "operator",
        ),
        # --- Chất lượng ảnh ---
        _spec(
            "BLURRY",
            "fail",
            "Ảnh mờ (variance of Laplacian dưới ngưỡng).",
            "Ảnh mờ/rung, OCR sẽ đọc sai. Giữ máy vững, chạm để lấy nét rồi chụp lại.",
            "capturer",
        ),
        _spec(
            "GLARE",
            "warn",
            "Có vùng bão hòa sáng lớn trên tài liệu.",
            "Có vệt lóa/phản quang che chữ. Đổi hướng đèn hoặc nghiêng nhẹ máy "
            "tránh phản chiếu.",
            "capturer",
        ),
        _spec(
            "TOO_DARK",
            "warn",
            "Độ sáng trung vị của tài liệu quá thấp.",
            "Ảnh thiếu sáng. Chụp nơi sáng hơn hoặc bật đèn.",
            "capturer",
        ),
    ]
}


@dataclass(frozen=True)
class Reason:
    """Một lý do cụ thể gắn vào kết quả, dựng từ `REASONS` + chi tiết runtime."""

    code: str
    severity: Severity
    message: str
    hint: str
    audience: Audience
    detail: Optional[str] = None

    @classmethod
    def of(cls, code: str, detail: Optional[str] = None) -> "Reason":
        spec = REASONS[code]
        return cls(
            code=spec.code,
            severity=spec.severity,
            message=spec.message,
            hint=spec.hint,
            audience=spec.audience,
            detail=detail,
        )

    def to_dict(self) -> dict:
        d = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
            "audience": self.audience,
        }
        if self.detail:
            d["detail"] = self.detail
        return d


def verdict_of(reasons: List[Reason]) -> Verdict:
    """fail nếu có ≥1 reason fail · warn nếu có reason nhưng không fail · pass nếu rỗng.

    Bất biến: ``verdict == "pass"`` ⟺ ``reasons == []``.
    """
    if any(r.severity == "fail" for r in reasons):
        return "fail"
    if reasons:
        return "warn"
    return "pass"


class ScanError(Exception):
    """Lỗi có mã lý do — thay cho việc nuốt exception rồi trả None (BUG-2).

    Chỉ bắt ở **biên** (CLI main, Flask handler) và dịch sang exit code /
    HTTP status + JSON body.
    """

    def __init__(self, code: str, detail: Optional[str] = None):
        self.reason = Reason.of(code, detail)
        super().__init__(f"{code}: {self.reason.message}")

    @property
    def code(self) -> str:
        return self.reason.code

    def to_dict(self) -> dict:
        return self.reason.to_dict()
