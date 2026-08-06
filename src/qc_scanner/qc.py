"""Hợp đồng đầu ra QC: mã lý do, Reason, ScanError.

Nguyên tắc bất biến: **mã nào cũng phải có `hint` và `audience`**. Mã không hành
động được là mã vô dụng — `REASONS` là nguồn sự thật duy nhất, và test
`test_qc_contract.py` chặn mọi mã thiếu hai trường đó.

Mã (`code`) là **ổn định vĩnh viễn** — nó đi vào log/CSV của khách. `message` và
`hint` có thể sửa/dịch.
"""

from dataclasses import dataclass, field, replace
from typing import Literal, Optional

Severity = Literal["warn", "fail"]
Audience = Literal["capturer", "operator", "system"]
Verdict = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class ReasonSpec:
    """Định nghĩa tĩnh của một mã lý do, kèm hint cho **cả hai** nhóm người dùng."""

    code: str
    severity: Severity
    message: str
    hints: dict  # {"capturer": ..., "operator": ...} — bắt buộc đủ cả hai
    audience: Audience
    """Nhóm *chính* của mã này — dùng làm mặc định khi luồng gọi không khai báo gì."""

    @property
    def hint(self) -> str:
        """Hint mặc định. Giữ trường này để mã cũ đọc `spec.hint` không gãy."""
        return hint_for(self.hints, self.audience)


def hint_for(hints: dict, audience: Audience) -> str:
    """Chọn hint hợp với người nhận; mã `system` không có tầng riêng nên về `operator`.

    Người vận hành mới là người đọc log của mã hệ thống — người chụp không thấy,
    và cũng không làm gì được với "kiểm tra bước upload".
    """
    return hints.get(audience) or hints["operator"]


def _spec(code, severity, message, capturer, operator, audience):
    return ReasonSpec(
        code, severity, message, {"capturer": capturer, "operator": operator}, audience
    )


#: Danh mục mã lý do. Thêm mã mới = thêm một dòng ở đây, không rải rác trong code.
REASONS: dict[str, ReasonSpec] = {
    s.code: s
    for s in [
        # --- Đầu vào ---
        _spec(
            "FILE_EMPTY",
            "fail",
            "Không nhận được dữ liệu ảnh (0 byte).",
            "Chưa nhận được ảnh. Kiểm tra lại bước tải lên.",
            "Không có gì để soi. Báo bên gửi kiểm tra bước tải lên.",
            "system",
        ),
        _spec(
            "MISSING_FILE",
            "fail",
            "Request thiếu trường form `file`.",
            "Chưa đính kèm ảnh. Chọn ảnh rồi gửi lại.",
            "Lỗi tích hợp, không phải lỗi ảnh: request thiếu trường `file`. "
            "Báo bên phát triển.",
            "system",
        ),
        _spec(
            "DECODE_FAILED",
            "fail",
            "Không giải mã được dữ liệu thành ảnh.",
            "File không phải ảnh hợp lệ. Gửi lại dạng JPG hoặc PNG.",
            "File hỏng hoặc sai định dạng, không mở ra được. Xin lại bản gốc.",
            "system",
        ),
        _spec(
            "INFERENCE_FAILED",
            "fail",
            "Model chạy lỗi (hết tài nguyên hoặc hỏng thiết bị).",
            "Lỗi máy chủ, không phải do ảnh. Thử lại sau ít phút.",
            "Lỗi tài nguyên máy chủ (thường là hết bộ nhớ GPU), **không phải lỗi ảnh**. "
            "Cho chạy lại, đừng loại ảnh.",
            "system",
        ),
        _spec(
            "MODEL_MISSING",
            "fail",
            "Thiếu file mô hình — máy chủ chưa cài đặt xong.",
            "Lỗi máy chủ, không phải do ảnh. Báo người quản trị.",
            "Image thiếu mô hình DocAligner; nó phải được nướng vào lúc **build** "
            "(`qc-scanner-fetch-models`). Ảnh không có lỗi — cho chạy lại sau khi sửa image.",
            "system",
        ),
        _spec(
            "UNAUTHORIZED",
            "fail",
            "Thiếu hoặc sai API key.",
            "Yêu cầu chưa được xác thực. Báo bên tích hợp kiểm tra API key.",
            "Request không kèm `Authorization: Bearer <key>` hợp lệ. Ảnh **chưa được "
            "xử lý lần nào** — đây là lỗi tích hợp, không phải lỗi ảnh.",
            "system",
        ),
        # --- Đầu vào PDF ---
        _spec(
            "PDF_DECODE_FAILED",
            "fail",
            "Không mở được file PDF.",
            "PDF hỏng hoặc có mật khẩu. Gửi lại bản không đặt mật khẩu.",
            "PDF hỏng hoặc có mật khẩu, không mở ra được. Xin lại bản đã gỡ mật khẩu.",
            "system",
        ),
        _spec(
            "PDF_NO_PAGES",
            "fail",
            "File PDF không có trang nào.",
            "File PDF rỗng. Kiểm tra lại bước xuất file.",
            "PDF rỗng, không có gì để soi. Báo bên gửi kiểm tra bước xuất file.",
            "system",
        ),
        _spec(
            "PDF_TOO_MANY_PAGES",
            "fail",
            "PDF vượt trần số trang cho một lần xử lý.",
            "File quá nhiều trang. Tách nhỏ rồi gửi lại.",
            "Vượt trần `pdf_max_pages` nên **không trang nào** được xử lý — cắt bớt "
            "trong im lặng sẽ khiến bên gọi tưởng đã soi hết. Tách file, hoặc nâng "
            "`QC_SCANNER_PDF_MAX_PAGES`.",
            "operator",
        ),
        _spec(
            "PDF_MULTIPAGE",
            "fail",
            "PDF nhiều trang đưa vào đường xử lý một-ảnh.",
            "PDF có nhiều trang. Gửi từng trang một.",
            "Lỗi tích hợp: `scan_qc()` trả đúng một kết quả nên không chứa nổi PDF "
            "nhiều trang. Dùng `scan_document()`; qua HTTP thì đã là mặc định.",
            "system",
        ),
        _spec(
            "SERVER_BUSY",
            "fail",
            "Máy chủ kín tải, chưa nhận thêm request.",
            "Hệ thống đang bận. Thử lại sau vài giây.",
            "Quá tải tạm thời, **không phải lỗi ảnh** — ảnh chưa được xử lý lần nào. "
            "Cho chạy lại. Gặp thường xuyên thì giảm request song song, hoặc thêm container.",
            "system",
        ),
        _spec(
            "LOW_RESOLUTION",
            "fail",
            "Ảnh quá nhỏ so với ngưỡng OCR đọc được.",
            "Ảnh quá nhỏ để OCR đọc. Lại gần hơn rồi chụp lại.",
            "Quá nhỏ để OCR đọc, cắt tay cũng không thêm được điểm ảnh. "
            "Tìm bản lớn hơn, không có thì nhập tay.",
            "capturer",
        ),
        # --- Tách chủ thể ---
        _spec(
            "SUBJECT_NOT_FOUND",
            "fail",
            "Không tách được tờ giấy khỏi nền.",
            "Máy không thấy tờ giấy. Đặt lên nền tối rồi chụp lại.",
            "Không tách được giấy khỏi nền (thường là giấy trắng trên nền sáng). "
            "Cắt tay theo mép giấy trước khi cho xuống OCR.",
            "capturer",
        ),
        # ⚠️ KHÔNG CÒN ĐƯỢC PHÁT kể từ QC-15 (2026-08-05). Giữ định nghĩa lại để log
        # và CSV cũ vẫn tra được mã này, và để bật lại chỉ là một dòng trong `doc.py`.
        # Lý do bỏ: `border_ink_ratio` đo thẳng thứ mã này chỉ phỏng đoán.
        _spec(
            "SUBJECT_FILLS_FRAME",
            "warn",
            "Tờ giấy chiếm gần hết khung. (Đã ngừng phát — xem QC-15.)",
            "Giấy chiếm gần hết khung, có thể mất mép. Lùi máy ra rồi chụp lại.",
            "Giấy chiếm gần hết khung nên không chắc còn đủ 4 mép. "
            "Soi xem có mất phần nào không.",
            "capturer",
        ),
        _spec(
            "RECOVERED_BY_EDGE_FALLBACK",
            "warn",
            "Nắn được bằng phương án dự phòng dò cạnh.",
            "Ảnh vẫn dùng được. Chụp trên nền tối thì lần sau chắc hơn.",
            "Nắn bằng phương án dự phòng nên kém tin cậy hơn. Soi trước khi dùng.",
            "operator",
        ),
        _spec(
            "RECOVERED_BY_MASK_FALLBACK",
            "warn",
            "Detector chính không thấy tài liệu; tách nền tìm được.",
            "Ảnh vẫn dùng được. Chụp thấy trọn 4 mép thì lần sau chắc hơn.",
            "Detector chính trả rỗng, tứ giác này do tách nền tìm ra. Hay gặp với ảnh "
            "**đã cắt sẵn**. Soi trước khi dùng.",
            "operator",
        ),
        # --- Hình học biên ---
        _spec(
            "QUAD_NOT_FOUND",
            "fail",
            "Không dựng được tứ giác nào đạt bộ lọc hình học.",
            "Máy không thấy đủ 4 góc. Mở phẳng tờ giấy, đừng che góc, chụp lại cả tờ.",
            "Không dựng được 4 góc. Cắt tay theo mép giấy rồi đưa lại vào luồng.",
            "capturer",
        ),
        _spec(
            "TOO_SMALL",
            "fail",
            "Tứ giác chiếm quá ít diện tích khung hình.",
            "Tài liệu quá nhỏ trong khung. Lại gần hoặc zoom vào rồi chụp lại.",
            "Quá nhỏ trong khung nên phần cắt ra thiếu điểm ảnh cho OCR. "
            "Tìm bản chụp gần hơn, không có thì nhập tay.",
            "capturer",
        ),
        _spec(
            "NOT_CONVEX",
            "fail",
            "Tứ giác dựng được không lồi.",
            "Biên bị méo, thường do nếp gấp. Vuốt phẳng tài liệu rồi chụp lại.",
            "Biên méo, thường do nếp gấp hoặc bóng đổ. Soi xem chữ có bị kéo méo không; "
            "có thì cắt tay theo mép giấy.",
            "capturer",
        ),
        _spec(
            "CLIPPED_EDGE",
            "warn",
            "Có góc tài liệu nằm sát hoặc ngoài mép ảnh.",
            "Một phần tài liệu nằm ngoài khung. Lùi máy ra cho thấy trọn 4 mép.",
            "Có góc nằm sát/ngoài mép ảnh. Soi xem phần mất là viền trắng hay có chữ.",
            "capturer",
        ),
        _spec(
            "CONTENT_CLIPPED",
            "fail",
            "Chữ chạy ra ngoài mép ảnh — đã mất nội dung.",
            "Mất **chữ** chứ không chỉ mất viền. Lùi máy ra, chụp lại cả tờ kèm chút nền.",
            "Chữ đã nằm ngoài khung, **không lấy lại được** từ ảnh này — cắt tay cũng vô ích. "
            "Tìm bản chụp khác, hoặc nhập tay.",
            "capturer",
        ),
        _spec(
            "NO_CROP_DETECTED",
            "fail",
            "Không cắt được gì — ảnh ra gần như ảnh vào.",
            "Máy không tìm được biên tờ giấy. Đặt lên nền tối rồi chụp lại cả 4 mép.",
            "Máy không cắt được gì. Cắt tay theo mép giấy trước khi cho xuống OCR.",
            "capturer",
        ),
        _spec(
            "EXTREME_SKEW",
            "warn",
            "Góc chụp nghiêng mạnh, hai cạnh đối lệch nhau nhiều.",
            "Chụp quá nghiêng nên chữ bị kéo giãn. Chụp vuông góc từ trên xuống.",
            "Chữ bị kéo giãn sau khi nắn. Soi kỹ vùng chữ nhỏ và số trước khi cho qua.",
            "capturer",
        ),
        _spec(
            "TEXT_NOT_LEVEL",
            "fail",
            "Chữ vẫn nghiêng sau khi nắn — phép nắn đã hỏng.",
            "Ảnh nắn ra bị xiên, thường do gấp góc giấy. "
            "Vuốt phẳng cả 4 góc rồi chụp lại.",
            "Ảnh nắn ra xiên, chữ chạy chéo — đừng đưa xuống OCR. "
            "Kiểm xem giấy có gấp góc không; có thì cắt tay theo mép thật.",
            "capturer",
        ),
        _spec(
            "MULTIPLE_DOCUMENTS",
            "warn",
            "Có nhiều hơn một tài liệu lớn trong ảnh.",
            "Ảnh có nhiều tờ, máy chỉ lấy tờ lớn nhất. Chụp từng tờ một.",
            "Máy chỉ xử lý tờ lớn nhất. Kiểm xem có đúng tờ cần lấy không, "
            "và các tờ còn lại có bị bỏ sót không.",
            "capturer",
        ),
        _spec(
            "FALLBACK_ORIGINAL",
            "fail",
            "Trả ảnh gốc chưa nắn vì không dựng được tứ giác.",
            "Máy không nắn được ảnh này. Chụp lại trên nền tối, thấy trọn 4 mép.",
            "Ảnh trả về là ảnh gốc chưa xử lý. Đừng đưa thẳng vào OCR.",
            "operator",
        ),
        _spec(
            "DETECTOR_DISAGREEMENT",
            "warn",
            "Hai detector cho tứ giác lệch nhau đáng kể.",
            "Máy chưa chắc về biên tờ giấy. Chụp trên nền tối sẽ chắc hơn.",
            "Hai phương pháp dò biên không đồng thuận nên kết quả kém chắc. "
            "Soi trước khi dùng.",
            "operator",
        ),
        # --- Chất lượng ảnh ---
        _spec(
            "BLURRY",
            "fail",
            "Ảnh mờ, dưới ngưỡng độ nét.",
            "Ảnh mờ hoặc rung. Giữ máy vững, chạm lấy nét rồi chụp lại.",
            "Mờ/rung nên OCR sẽ đọc sai, cắt tay không cứu được. "
            "Tìm bản chụp khác, không có thì nhập tay.",
            "capturer",
        ),
        _spec(
            "GLARE",
            "warn",
            "Có vùng bão hoà sáng lớn trên tài liệu.",
            "Có vệt loá che chữ. Đổi hướng đèn hoặc nghiêng nhẹ máy.",
            "Có vệt loá trên tài liệu. Soi xem chỗ loá có che dữ liệu cần lấy không.",
            "capturer",
        ),
        _spec(
            "TOO_DARK",
            "warn",
            "Tài liệu quá tối.",
            "Ảnh thiếu sáng. Chụp ở nơi sáng hơn.",
            "Ảnh thiếu sáng. Tăng sáng khi soi; vẫn không đọc nổi thì nhập tay.",
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
    """Hint đã chọn theo người nhận của luồng đang chạy."""

    audience: Audience
    """Người nhận của `hint` ở trên — KHÔNG phải nhóm chính của mã.

    Với ảnh tồn kho thì mọi mã đều rơi về `operator`, kể cả mã vốn dành cho người
    chụp: không ai chụp lại được nữa.
    """

    detail: Optional[str] = None
    hints: dict = field(default_factory=dict)
    """Cả hai tầng, luôn đi kèm — để phía gọi tự hiển thị lại theo vai người đọc."""

    @classmethod
    def of(
        cls, code: str, detail: Optional[str] = None, audience: Optional[str] = None
    ) -> "Reason":
        spec = REASONS[code]
        who = audience or spec.audience
        return cls(
            code=spec.code,
            severity=spec.severity,
            message=spec.message,
            hint=hint_for(spec.hints, who),
            audience=who,
            detail=detail,
            hints=dict(spec.hints),
        )

    def for_audience(self, audience: Optional[str]) -> "Reason":
        """Cùng một lý do, đọc bằng hint hợp với người nhận.

        Đổi ở một chỗ duy nhất, ngay trước khi trả kết quả, thay vì bắt mọi nơi
        dựng `Reason` phải nhớ truyền bối cảnh xuống.
        """
        if not audience or audience == self.audience:
            return self
        return replace(self, hint=hint_for(self.hints, audience), audience=audience)

    def to_dict(self) -> dict:
        d = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
            "audience": self.audience,
            "hints": self.hints,
        }
        if self.detail:
            d["detail"] = self.detail
        return d


def verdict_of(reasons: list[Reason]) -> Verdict:
    """fail nếu có ≥1 reason fail · warn nếu có reason nhưng không fail · pass nếu rỗng.

    Bất biến: ``verdict == "pass"`` ⟺ ``reasons == []``.
    """
    if any(r.severity == "fail" for r in reasons):
        return "fail"
    if reasons:
        return "warn"
    return "pass"


@dataclass
class Metrics:
    """Số đo thô đi kèm **mọi** kết quả — để tra ngược và tinh chỉnh ngưỡng.

    Không có metric thì không chốt được ngưỡng bằng số đo, chỉ đoán. Đây cũng là
    dữ liệu đổ ra CSV cho báo cáo QC hàng loạt.
    """

    alpha_coverage: Optional[float] = None
    """% pixel alpha > 0 sau rembg."""

    contour_candidates: int = 0
    """Số contour chiếm ≥ `candidate_area_ratio` diện tích ảnh."""

    quad_area_ratio: Optional[float] = None
    """Diện tích tứ giác / diện tích ảnh."""

    skew_ratio: Optional[float] = None
    """Tỉ lệ cạnh đối dài/ngắn (lấy max của hai cặp)."""

    is_convex: Optional[bool] = None
    touches_border: int = 0
    """Số góc nằm sát mép ảnh."""

    corners_outside_px: float = 0.0
    """Góc tứ giác lọt ra ngoài ảnh bao nhiêu pixel (theo ảnh làm việc).

    > 0 nghĩa là detector suy ra một góc mà nó **không nhìn thấy** — dấu hiệu nó thua,
    dùng để phân biệt "detector trả lại khung hình" với "người chụp lấy khung sát".
    """

    border_ink_ratio: Optional[float] = None
    """Mật độ pixel mực sát mép ảnh, ở những cạnh tứ giác bị khung hình cắt (QC-12).

    `0.0` khi tứ giác nằm trọn trong ảnh — khi đó biên cắt là mép tờ giấy, không
    phải chỗ nội dung bị mất.
    """

    est_dpi: Optional[float] = None
    """DPI ước lượng của ảnh đã nắn, giả định khổ A4."""

    blur_score: Optional[float] = None
    """Variance of Laplacian trên ảnh đã nắn."""

    glare_ratio: Optional[float] = None
    median_brightness: Optional[float] = None

    text_skew_deg: Optional[float] = None
    """Góc nghiêng dòng chữ trên ảnh **đã nắn**; `None` = không đủ mực để đo (QC-18).

    `None` khác 0.0 và khác biệt đó quan trọng: 0.0 nghĩa là "đã đo, chữ thẳng",
    `None` nghĩa là **chưa ai kiểm** — trang gần như trắng thì phép đo vô nghĩa nên
    nó im lặng thay vì bịa ra một con số.

    Đây là góc **đo được trước khi sửa**, không phải góc còn lại sau khi sửa — xem
    `deskew_applied_deg`.
    """

    deskew_applied_deg: Optional[float] = None
    """Góc đã thật sự xoay để nắn thẳng; `None` = không xoay (QC-19).

    Tách khỏi `text_skew_deg` để báo cáo QC vẫn nói được ảnh vào lệch bao nhiêu sau
    khi ảnh ra đã được sửa. Gộp làm một thì mọi ảnh đều báo 0° và chỉ số mất hết
    giá trị chẩn đoán.
    """

    pre_cropped: bool = False
    """Phía gọi khai báo ảnh vào đã cắt sẵn → các kiểm tra về biên đã bị bỏ qua (QC-14)."""

    page: Optional[int] = None
    """Số trang trong file PDF nguồn, tính từ 1. `None` với đầu vào là ảnh rời.

    Nằm ở đây cùng `pre_cropped` vì cùng loại: dữ kiện về **bối cảnh đầu vào**, không
    đòi hành động gì, nhưng thiếu nó thì một dòng CSV của PDF 12 trang không tra
    ngược được về trang nào.
    """

    pdf_source: Optional[str] = None
    """Trang PDF đã được đọc bằng đường nào: `embedded` · `render@<DPI>`.

    `embedded` = lấy thẳng bitmap nhúng, **không resample lần nào**. Đáng ghi lại vì
    đường render làm `blur_score` tụt (13% khi đúng DPI, gấp 12 lần khi sai DPI), nên
    khi soi một ca `BLURRY` bất thường thì đây là cột phải nhìn trước. Xem `pdf.py`."""

    fallback_used: str = "none"
    """`none` · `edge_detect` · `original` — minh bạch đường đi."""

    detector: Optional[str] = None
    detector_confidence: Optional[float] = None
    detector_iou: Optional[float] = None
    """IoU giữa hai detector khi bật đối chiếu chéo (S-6)."""

    def to_dict(self) -> dict:
        return {
            k: (round(v, 4) if isinstance(v, float) else v)
            for k, v in self.__dict__.items()
            if v is not None
        }


@dataclass
class ScanResult:
    """Đầu ra của `scan_qc()`: **một phán quyết kèm ảnh**, không chỉ là ảnh."""

    image: Optional[bytes]
    """PNG đã nắn, hoặc best-effort, hoặc None nếu fail cứng."""

    verdict: Verdict
    reasons: list[Reason] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)

    corners: Optional[list[list[float]]] = None
    """4 góc đã dùng để nắn, theo hệ toạ độ **ảnh gốc**, thứ tự TL-TR-BR-BL.

    Đây là thứ so được với nhãn vàng để tính IoU — không có nó thì không đo được
    độ chính xác dò biên, chỉ đo được "có ra ảnh hay không".
    """

    def __post_init__(self):
        # Bất biến: pass ⟺ reasons rỗng. Không có "pass kèm ghi chú".
        expected = verdict_of(self.reasons)
        if self.verdict != expected:
            raise AssertionError(
                f"verdict {self.verdict!r} không khớp reasons (đúng phải là {expected!r})"
            )

    @classmethod
    def of(cls, image, reasons, metrics=None, corners=None, audience=None) -> "ScanResult":
        # Chọn tầng hint ở đúng một chỗ, ngay trước khi trả ra — chứ không bắt mọi
        # nơi dựng `Reason` phải nhớ mang bối cảnh theo.
        reasons = [r.for_audience(audience) for r in reasons]
        return cls(
            image=image,
            verdict=verdict_of(reasons),
            reasons=reasons,
            metrics=metrics or Metrics(),
            corners=corners,
        )

    @property
    def codes(self) -> list[str]:
        return [r.code for r in self.reasons]

    def to_dict(self, include_image: bool = False) -> dict:
        d = {
            "verdict": self.verdict,
            "reasons": [r.to_dict() for r in self.reasons],
            "metrics": self.metrics.to_dict(),
        }
        if self.corners is not None:
            d["corners"] = self.corners
        if include_image:
            import base64

            d["image"] = (
                base64.b64encode(self.image).decode("ascii") if self.image else None
            )
        return d


#: Thứ tự "tệ dần" của phán quyết — dùng để gộp nhiều trang thành một kết luận.
_VERDICT_RANK = {"pass": 0, "warn": 1, "fail": 2}


@dataclass
class DocumentResult:
    """Kết quả của **một file**, có thể gồm nhiều trang (PDF) hoặc đúng một (ảnh rời).

    Vì sao cần một lớp riêng thay vì trả `list[ScanResult]`: phía gọi hầu như luôn cần
    một câu trả lời cho cả file — nhận hay không nhận — và nếu mỗi nơi tự gộp thì mỗi
    nơi gộp một kiểu. `verdict` ở đây là **trang tệ nhất**, không phải trang đầu: một
    bộ hồ sơ có 1 trang mờ không đọc được thì cả bộ chưa dùng được, dù 11 trang kia
    hoàn hảo.
    """

    pages: list[ScanResult]
    source: Literal["image", "pdf"] = "image"

    @property
    def verdict(self) -> Verdict:
        if not self.pages:
            return "fail"
        return max((p.verdict for p in self.pages), key=lambda v: _VERDICT_RANK[v])

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self, include_image: bool = False) -> dict:
        return {
            "source": self.source,
            "verdict": self.verdict,
            "page_count": self.page_count,
            "pages": [
                {"page": i, **p.to_dict(include_image=include_image)}
                for i, p in enumerate(self.pages, start=1)
            ],
        }


class ScanError(Exception):
    """Lỗi có mã lý do — thay cho việc nuốt exception rồi trả None (BUG-2).

    Chỉ bắt ở **biên** (CLI main, Flask handler) và dịch sang exit code /
    HTTP status + JSON body.
    """

    def __init__(self, code: str, detail: Optional[str] = None):
        # Không nhận `audience`: mọi mã ném ra ở đây đều là mã `system` (file rỗng,
        # decode hỏng). Chúng không có tầng riêng cho hai nhóm — cả hai luồng đều
        # phải nhờ tới người vận hành, nên `hint_for` trả về tầng operator.
        self.reason = Reason.of(code, detail)
        super().__init__(f"{code}: {self.reason.message}")

    @property
    def code(self) -> str:
        return self.reason.code

    def to_dict(self) -> dict:
        return self.reason.to_dict()
