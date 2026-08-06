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
            "Không nhận được dữ liệu. Kiểm tra lại bước tải/upload.",
            "Không có gì để soi. Báo bên gửi ảnh kiểm tra bước tải lên.",
            "system",
        ),
        _spec(
            "MISSING_FILE",
            "fail",
            "Request không có trường form `file`.",
            "Ảnh chưa được đính kèm. Kiểm tra lại bước chọn/tải ảnh.",
            "Hệ gọi gửi request thiếu trường `file`. Đây là lỗi tích hợp, "
            "báo bên phát triển — không phải lỗi của ảnh.",
            "system",
        ),
        _spec(
            "DECODE_FAILED",
            "fail",
            "Không giải mã được dữ liệu thành ảnh.",
            "File không phải ảnh hợp lệ (hoặc đã hỏng). Kiểm tra định dạng: JPG/PNG.",
            "File hỏng hoặc sai định dạng — không mở ra để soi được. Xin lại bản gốc.",
            "system",
        ),
        _spec(
            "INFERENCE_FAILED",
            "fail",
            "Model tách nền chạy lỗi (thiếu tài nguyên hoặc hỏng thiết bị).",
            "Lỗi phía máy chủ, không phải do ảnh của bạn. Thử lại sau ít phút.",
            "Lỗi tài nguyên phía máy chủ (thường là hết bộ nhớ GPU), **không phải lỗi ảnh**. "
            "Ảnh này vẫn dùng được — cho chạy lại, đừng loại nó.",
            "system",
        ),
        _spec(
            "MODEL_MISSING",
            "fail",
            "Thiếu file mô hình của detector — máy chủ chưa cài đặt xong.",
            "Lỗi phía máy chủ, không phải do ảnh của bạn. Báo người quản trị.",
            "Image thiếu mô hình DocAligner. Nó phải được nướng vào lúc **build** "
            "(`qc-scanner-fetch-models`); máy khách không ra Internet nên không có "
            "đường tải lúc chạy. Ảnh không có lỗi gì — chạy lại sau khi sửa image.",
            "system",
        ),
        # --- Đầu vào PDF ---
        _spec(
            "PDF_DECODE_FAILED",
            "fail",
            "Không mở được file PDF.",
            "File PDF hỏng, hoặc có mật khẩu mở file. Gửi lại bản không đặt mật khẩu.",
            "PDF hỏng hoặc được đặt mật khẩu — không mở ra để soi được. "
            "Xin lại bản gốc, hoặc bản đã gỡ mật khẩu.",
            "system",
        ),
        _spec(
            "PDF_NO_PAGES",
            "fail",
            "File PDF không có trang nào.",
            "File PDF rỗng (0 trang). Kiểm tra lại bước xuất/tải file.",
            "PDF rỗng, không có gì để soi. Báo bên gửi kiểm tra bước xuất file.",
            "system",
        ),
        _spec(
            "PDF_TOO_MANY_PAGES",
            "fail",
            "File PDF vượt trần số trang cho một lần xử lý.",
            "File quá nhiều trang cho một lần gửi. Tách nhỏ rồi gửi lại.",
            "Vượt trần `pdf_max_pages`. Không trang nào được xử lý — cắt bớt trong im "
            "lặng sẽ khiến bên gọi tưởng đã soi hết. Tách file, hoặc nâng "
            "`QC_SCANNER_PDF_MAX_PAGES` nếu máy chủ chịu được thời gian xử lý.",
            "operator",
        ),
        _spec(
            "PDF_MULTIPAGE",
            "fail",
            "PDF nhiều trang được đưa vào đường xử lý một-ảnh.",
            "File PDF có nhiều trang. Gửi từng trang, hoặc dùng luồng xử lý nhiều trang.",
            "Đây là lỗi tích hợp, không phải lỗi tài liệu: `scan_qc()` trả đúng một kết "
            "quả nên không chứa nổi PDF nhiều trang. Dùng `scan_document()` — hoặc với "
            "HTTP thì phản hồi nhiều trang đã là mặc định, không cần đổi gì.",
            "system",
        ),
        _spec(
            "SERVER_BUSY",
            "fail",
            "Máy chủ đang kín tải, không nhận thêm request lúc này.",
            "Hệ thống đang bận. Thử lại sau vài giây — ảnh của bạn không có vấn đề gì.",
            "Quá tải tạm thời, **không phải lỗi ảnh**. Ảnh này chưa được xử lý lần nào; "
            "cho chạy lại, đừng loại. Gặp thường xuyên thì giảm số request gửi song "
            "song, hoặc thêm container.",
            "system",
        ),
        _spec(
            "LOW_RESOLUTION",
            "fail",
            "Độ phân giải ước lượng thấp hơn ngưỡng OCR đọc được.",
            "Ảnh quá nhỏ để OCR đọc được. Chụp lại ở độ phân giải cao hơn, "
            "hoặc lại gần tài liệu hơn.",
            "Ảnh quá nhỏ để OCR đọc; cắt tay cũng không thêm được điểm ảnh. "
            "Tìm bản chụp lớn hơn trong kho, không có thì nhập tay.",
            "capturer",
        ),
        # --- Tách chủ thể ---
        _spec(
            "SUBJECT_NOT_FOUND",
            "fail",
            "Không tách được tờ giấy khỏi nền.",
            "Đặt tài liệu lên nền tối, tương phản (bàn sẫm màu) rồi chụp lại.",
            "Máy không tách được tờ giấy khỏi nền (thường do giấy trắng trên nền "
            "sáng). Cắt tay theo mép giấy trước khi cho xuống OCR.",
            "capturer",
        ),
        # ⚠️ KHÔNG CÒN ĐƯỢC PHÁT kể từ QC-15 (2026-08-05). Giữ định nghĩa lại để log
        # và CSV cũ vẫn tra được mã này, và để bật lại chỉ là một dòng trong `doc.py`.
        # Lý do bỏ: `border_ink_ratio` đo thẳng thứ mã này chỉ phỏng đoán.
        _spec(
            "SUBJECT_FILLS_FRAME",
            "warn",
            "Tờ giấy chiếm gần hết khung hình. (Mã đã ngừng phát — xem QC-15.)",
            "Tờ giấy chiếm gần hết khung, có thể đã bị cắt mất mép. "
            "Lùi ra để lộ viền nền quanh tài liệu.",
            "Giấy chiếm gần hết khung nên không chắc còn đủ 4 mép. "
            "Soi xem có mất phần nào của tài liệu không rồi mới cho qua.",
            "capturer",
        ),
        _spec(
            "RECOVERED_BY_EDGE_FALLBACK",
            "warn",
            "Đã nắn được bằng phương án dự phòng dò cạnh.",
            "Ảnh vẫn dùng được, nhưng máy phải dò biên bằng phương án dự phòng. "
            "Chụp trên nền tối, tương phản thì lần sau chắc chắn hơn.",
            "Đã nắn được bằng phương án dự phòng — độ tin cậy thấp hơn, "
            "nên soi mắt thường trước khi dùng.",
            "operator",
        ),
        _spec(
            "RECOVERED_BY_MASK_FALLBACK",
            "warn",
            "Detector chính không thấy tài liệu; đã lấy được bằng tách nền.",
            "Ảnh vẫn dùng được. Máy phải dùng phương án dự phòng để tìm tờ giấy — "
            "chụp sao cho thấy trọn 4 mép trên nền tương phản thì chắc chắn hơn.",
            "Detector chính trả về rỗng, tứ giác này do tách nền tìm ra. Hay gặp "
            "với ảnh ĐÃ cắt sẵn (không còn nền quanh giấy). Soi trước khi dùng.",
            "operator",
        ),
        # --- Hình học biên ---
        _spec(
            "QUAD_NOT_FOUND",
            "fail",
            "Không tìm được tứ giác nào đạt bộ lọc hình học.",
            "Không thấy đủ 4 góc tờ giấy. Mở phẳng tài liệu, đừng để tay/vật che góc, "
            "chụp lại toàn bộ tờ.",
            "Máy không dựng được 4 góc tờ giấy. Cắt tay theo mép giấy rồi đưa lại "
            "vào luồng.",
            "capturer",
        ),
        _spec(
            "TOO_SMALL",
            "fail",
            "Tứ giác chiếm quá ít diện tích khung hình.",
            "Tài liệu chiếm quá ít khung hình. Lại gần hơn hoặc zoom vào tài liệu.",
            "Tài liệu quá nhỏ trong khung nên phần cắt ra thiếu điểm ảnh cho OCR. "
            "Tìm bản chụp gần hơn, không có thì nhập tay.",
            "capturer",
        ),
        _spec(
            "NOT_CONVEX",
            "fail",
            "Tứ giác phát hiện được không lồi.",
            "Biên phát hiện bị méo (có thể do nếp gấp/bóng đổ). "
            "Vuốt phẳng tài liệu và chụp lại.",
            "Biên méo, thường do nếp gấp hoặc bóng đổ. Soi xem chữ có bị kéo méo "
            "không; nếu có thì cắt tay theo mép giấy.",
            "capturer",
        ),
        _spec(
            "CLIPPED_EDGE",
            "warn",
            "Có góc tài liệu nằm sát/ngoài mép ảnh.",
            "Một phần tài liệu nằm ngoài khung hình. Lùi máy ra để thấy trọn 4 mép.",
            "Có góc nằm sát/ngoài mép ảnh. Máy không thấy chữ ở chỗ đó nên chỉ báo "
            "nhắc — soi lại xem phần mất là viền trắng hay có nội dung.",
            "capturer",
        ),
        _spec(
            "CONTENT_CLIPPED",
            "fail",
            "Có chữ chạy tới sát mép ảnh ở cạnh bị khung hình cắt — nội dung đã mất.",
            "Một phần CHỮ nằm ngoài khung hình, không phải chỉ mất viền trắng. "
            "Lùi máy ra, chụp lại sao cho thấy trọn tài liệu kèm chút nền quanh mép.",
            "Chữ đã nằm ngoài khung hình — phần đó KHÔNG lấy lại được từ ảnh này, "
            "cắt tay cũng vô ích. Tìm bản chụp khác của cùng tài liệu, hoặc nhập tay.",
            "capturer",
        ),
        _spec(
            "NO_CROP_DETECTED",
            "fail",
            "Tứ giác gần trọn khung và chạm cả 4 mép — thực chất không cắt được gì.",
            "Không tìm được biên tờ giấy, ảnh ra gần như ảnh vào. "
            "Đặt tài liệu lên nền tối, tương phản và chụp lại sao cho thấy trọn 4 mép.",
            "Máy không cắt được gì, ảnh ra gần như ảnh vào. Cắt tay theo mép giấy "
            "trước khi cho xuống OCR.",
            "capturer",
        ),
        _spec(
            "EXTREME_SKEW",
            "warn",
            "Góc chụp nghiêng mạnh, cạnh đối lệch nhau nhiều.",
            "Góc chụp quá nghiêng — chữ sẽ bị kéo giãn sau khi nắn. "
            "Chụp vuông góc từ trên xuống.",
            "Góc chụp rất nghiêng nên chữ bị kéo giãn sau khi nắn. "
            "Soi kỹ vùng chữ nhỏ/số trước khi cho qua.",
            "capturer",
        ),
        _spec(
            "TEXT_NOT_LEVEL",
            "fail",
            "Dòng chữ vẫn nghiêng mạnh SAU khi nắn — phép nắn đã hỏng.",
            "Ảnh nắn ra bị xiên, chữ chạy chéo. Thường do tờ giấy bị gấp/quặp góc "
            "làm máy nhận nhầm mép. Vuốt phẳng cả 4 góc rồi chụp lại.",
            "Ảnh nắn ra bị xiên, chữ chạy chéo — đừng đưa xuống OCR. Kiểm xem tờ "
            "giấy có bị gấp góc không; có thì cắt tay theo mép thật của tờ giấy.",
            "capturer",
        ),
        _spec(
            "MULTIPLE_DOCUMENTS",
            "warn",
            "Phát hiện nhiều hơn một tài liệu lớn trong ảnh.",
            "Thấy nhiều hơn một tờ trong ảnh; chỉ tờ lớn nhất được xử lý. "
            "Chụp từng tờ một.",
            "Ảnh có nhiều tờ, máy chỉ xử lý tờ lớn nhất. Kiểm xem tờ cắt ra có "
            "đúng tờ cần lấy không, và các tờ còn lại có bị bỏ sót không.",
            "capturer",
        ),
        _spec(
            "FALLBACK_ORIGINAL",
            "fail",
            "Trả ảnh gốc chưa nắn vì không dựng được tứ giác.",
            "Không nắn được ảnh này. Chụp lại trên nền tối, tương phản, "
            "thấy trọn 4 mép tờ giấy.",
            "Không nắn được, ảnh trả về là ảnh gốc chưa xử lý. Không đưa thẳng vào OCR.",
            "operator",
        ),
        _spec(
            "DETECTOR_DISAGREEMENT",
            "warn",
            "Hai detector cho tứ giác lệch nhau đáng kể.",
            "Máy chưa chắc chắn về biên tờ giấy. Chụp trên nền tối, tương phản "
            "sẽ cho kết quả chắc hơn.",
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
            "Ảnh mờ/rung nên OCR sẽ đọc sai; không xử lý lại được bằng cắt tay. "
            "Tìm bản chụp khác, không có thì nhập tay.",
            "capturer",
        ),
        _spec(
            "GLARE",
            "warn",
            "Có vùng bão hòa sáng lớn trên tài liệu.",
            "Có vệt lóa/phản quang che chữ. Đổi hướng đèn hoặc nghiêng nhẹ máy "
            "tránh phản chiếu.",
            "Có vệt lóa trên tài liệu. Soi xem chỗ lóa có che đúng dữ liệu cần "
            "lấy không rồi mới quyết.",
            "capturer",
        ),
        _spec(
            "TOO_DARK",
            "warn",
            "Độ sáng trung vị của tài liệu quá thấp.",
            "Ảnh thiếu sáng. Chụp nơi sáng hơn hoặc bật đèn.",
            "Ảnh thiếu sáng. Tăng sáng/tương phản khi soi; chữ vẫn không đọc nổi "
            "thì nhập tay.",
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
