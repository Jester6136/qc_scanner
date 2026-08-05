"""§3b/§3c — mỗi mã lý do có ít nhất một ca kích hoạt được, và không false pass.

`test_no_false_pass_on_bad_input` là bài **quan trọng nhất trong repo**: false
pass là chế độ hỏng đắt nhất — ảnh xấu trôi xuống OCR và chỉ lộ ra lúc nghiệm
thu. Nó cố ý không đòi đúng mã: một ảnh hỏng bị bắt vì lý do khác vẫn tốt hơn
nhiều so với việc nó được cho qua.
"""

import pytest

import synthetic as S
from qc_scanner.config import Config
from qc_scanner.doc import scan_qc
from qc_scanner.qc import ScanError

BAD_CASES = [
    "tiny_document",
    "clipped_document",
    "clipped_margin_only",
    "skewed_document",
    "two_documents",
    "white_on_white",
    "blurry_document",
    "low_resolution_document",
    "dark_document",
    "glaring_document",
]


@pytest.fixture(scope="module")
def qc():
    cache = {}

    def run(builder_name):
        if builder_name not in cache:
            cache[builder_name] = scan_qc(getattr(S, builder_name)())
        return cache[builder_name]

    return run


@pytest.mark.parametrize("case", BAD_CASES)
def test_no_false_pass_on_bad_input(case, qc):
    result = qc(case)
    assert result.verdict != "pass", f"{case} được cho qua — false pass"
    assert result.reasons


@pytest.mark.parametrize(
    "case,code",
    [
        ("tiny_document", "TOO_SMALL"),
        ("clipped_document", "CONTENT_CLIPPED"),
        ("clipped_margin_only", "CLIPPED_EDGE"),
        ("skewed_document", "EXTREME_SKEW"),
        ("two_documents", "MULTIPLE_DOCUMENTS"),
        ("blurry_document", "BLURRY"),
        ("low_resolution_document", "LOW_RESOLUTION"),
        ("dark_document", "TOO_DARK"),
        ("glaring_document", "GLARE"),
    ],
)
def test_case_triggers_expected_code(case, code, qc):
    assert code in qc(case).codes


def test_clean_document_passes(qc):
    """Đối chứng: không có bài này thì một hệ thống fail-mọi-thứ cũng xanh."""
    result = scan_qc(S.document_on_dark_background())
    assert result.verdict == "pass", result.codes


def test_empty_input_raises_file_empty():
    with pytest.raises(ScanError) as exc:
        scan_qc(b"")
    assert exc.value.code == "FILE_EMPTY"


def test_junk_input_raises_decode_failed():
    with pytest.raises(ScanError) as exc:
        scan_qc(S.junk_bytes())
    assert exc.value.code == "DECODE_FAILED"


def test_subject_not_found_falls_back_to_original():
    """Không tách được chủ thể → vẫn trả ảnh, nhưng NÓI RÕ là ảnh gốc chưa nắn."""
    config = Config(enable_edge_fallback=False, candidate_area_ratio=0.5)
    result = scan_qc(S.tiny_document(), config=config)
    assert result.verdict == "fail"
    assert "FALLBACK_ORIGINAL" in result.codes
    assert result.image is not None
    assert result.metrics.fallback_used == "original"


# --- QC-12: mất viền trắng ≠ mất chữ (EX-1) --------------------------------- #


def test_losing_white_margin_is_only_a_warning(qc):
    """Ranh giới của EX-1, chiều "được phép": chạm mép nhưng không mất nội dung."""
    result = qc("clipped_margin_only")
    assert result.verdict == "warn", result.codes
    assert "CONTENT_CLIPPED" not in result.codes


def test_losing_text_is_a_failure(qc):
    """Chiều "không được phép": có chữ ở chỗ bị khung cắt."""
    result = qc("clipped_document")
    assert result.verdict == "fail", result.codes
    assert "CONTENT_CLIPPED" in result.codes


def test_content_clipped_replaces_clipped_edge(qc):
    """Đã nói mất chữ thì không nói thêm chạm mép — đó chỉ là cách chữ bị mất."""
    assert "CLIPPED_EDGE" not in qc("clipped_document").codes


def test_border_ink_is_zero_when_quad_is_inside_the_frame(qc):
    """Tứ giác nằm trọn trong ảnh thì biên cắt là mép giấy, không có gì bị mất."""
    result = qc("document_on_dark_background")
    assert result.metrics.border_ink_ratio == 0.0


# --- QC-15: chiếm hết khung, tự nó, không phải lỗi -------------------------- #


def test_filling_the_frame_is_not_a_defect_by_itself():
    """Điều kiện cũ VẪN đạt, nhưng không còn sinh ra lý do nào.

    Bài này cố tình kiểm cả `alpha_coverage > max_alpha_coverage` — nếu không thì
    sau này ai đó chỉnh ảnh mẫu làm nó tụt xuống dưới ngưỡng, test vẫn xanh mà
    chẳng kiểm gì nữa.
    """
    result = scan_qc(S.document_fills_frame())
    assert result.metrics.alpha_coverage > Config().max_alpha_coverage
    assert "SUBJECT_FILLS_FRAME" not in result.codes
    assert result.verdict != "fail", result.codes

    # `border_ink_ratio` ở đây CAO (≈0.99) dù chữ nằm cách mép giấy 110px: rembg
    # nuốt luôn viền nền 10px nên tứ giác trùng khung, và dải soi rơi vào chính nền
    # tối đó. Đây đúng là lý do `CONTENT_CLIPPED` bị chặn khi không có cắt thật —
    # lúc ấy con số này đo mép TẤM ẢNH chứ không đo mép crop.
    assert "CONTENT_CLIPPED" not in result.codes


def test_subject_fills_frame_is_retired_but_still_decodable():
    """Giữ định nghĩa để log/CSV cũ tra được, dù không còn phát nữa."""
    from qc_scanner.qc import REASONS

    assert "SUBJECT_FILLS_FRAME" in REASONS


# --- QC-14: ảnh khai báo là đã cắt sẵn -------------------------------------- #

PRE_CROPPED = Config(pre_cropped=True)


def test_pre_cropped_drops_border_reasons():
    """Với ảnh đã cắt, "giấy chạm mép khung" là đương nhiên chứ không phải lỗi."""
    result = scan_qc(S.clipped_document(), config=PRE_CROPPED)
    assert not (set(result.codes) & {"CLIPPED_EDGE", "CONTENT_CLIPPED"})
    assert result.metrics.pre_cropped is True


def test_pre_cropped_still_reports_everything_else():
    """Cờ này chỉ tắt kiểm tra về BIÊN. Ảnh mờ vẫn là ảnh mờ.

    Không có bài này thì `pre_cropped` dễ trượt thành một công tắc "cho qua tất".
    """
    result = scan_qc(S.blurry_document(), config=PRE_CROPPED)
    assert "BLURRY" in result.codes
    assert result.verdict == "fail"


def test_pre_cropped_is_off_by_default():
    """Mặc định phải là ảnh chụp: bật nhầm thì mất luôn khả năng bắt crop hụt."""
    assert Config().pre_cropped is False
    assert scan_qc(S.clipped_document()).metrics.pre_cropped is False


# --- QC-11: "không cắt được gì" phải là fail, không phải warn --------------- #
#
# Kiểm thẳng vào luật hình học thay vì dựng ảnh tổng hợp: dấu hiệu này phụ thuộc
# rembg tách nhầm nền, mà cái đó không tái tạo được ổn định bằng ảnh vẽ tay. Ca
# thật (`abc1b13d82af03f15abe.jpg`, `40b9f8b0c422457c1c33.jpg`) nằm trong ảnh
# khách nên không commit được — số đo của chúng ghi ở docs/features_issues.md §A2.


def _geometry_codes(corners, shape=(500, 400), config=None, confidence=0.6):
    """Chạy luật hình học với một `detector_confidence` cho trước.

    `confidence` mặc định 0.6 = detector đã phải ép `minAreaRect` vì không dựng nổi
    4 đỉnh — tức nó **thua**. Đó là điều kiện của `NO_CROP_DETECTED` từ QC-16.
    """
    import numpy as np

    from qc_scanner.doc import _geometry_reasons
    from qc_scanner.qc import Metrics

    work = np.zeros((*shape, 3), dtype="uint8")
    metrics = Metrics(detector_confidence=confidence)
    reasons = _geometry_reasons(
        np.asarray(corners, dtype="float32"), work, config or Config(), metrics
    )
    return [r.code for r in reasons]


FULL_FRAME = [[0, 0], [399, 0], [399, 499], [0, 499]]


def test_full_frame_quad_is_fail_not_warn():
    """Tứ giác trùng khung hình + detector thua = chưa cắt gì."""
    assert "NO_CROP_DETECTED" in _geometry_codes(FULL_FRAME)


def test_no_crop_replaces_clipped_edge():
    """Chạm 4 mép ở đây là hệ quả, không phải lý do — nói cả hai làm loãng."""
    assert "CLIPPED_EDGE" not in _geometry_codes(FULL_FRAME)


def test_full_frame_with_a_confident_detector_is_only_a_warning():
    """QC-16: cùng tứ giác đó, nhưng detector dựng được 4 đỉnh thật.

    Đây là **người chụp lấy khung sát**, không phải detector thua: tờ giấy vốn
    chiếm hết khung nên chẳng có gì để cắt, và nội dung còn nguyên.
    """
    codes = _geometry_codes(FULL_FRAME, confidence=0.9)
    assert "NO_CROP_DETECTED" not in codes
    assert "CLIPPED_EDGE" in codes, "vẫn phải nhắc là tứ giác áp mép khung"


def test_corners_outside_the_frame_count_as_a_struggling_detector():
    """Góc nằm ngoài ảnh = detector suy ra thứ nó không nhìn thấy (ca `abc1b13…`)."""
    spilling = [[-60, -20], [460, -20], [460, 520], [-60, 520]]
    assert "NO_CROP_DETECTED" in _geometry_codes(spilling, confidence=0.9)


def test_large_but_properly_cropped_quad_is_not_no_crop():
    """Đối chứng: chiếm gần hết khung mà KHÔNG chạm mép thì vẫn hợp lệ.

    Đây là lý do điều kiện phải kép — chỉ dựa vào diện tích sẽ đánh trượt ảnh
    chụp sát tài liệu, vốn là cách chụp đúng.
    """
    almost_full = [[8, 8], [391, 8], [391, 491], [8, 491]]
    assert "NO_CROP_DETECTED" not in _geometry_codes(almost_full)


def test_no_crop_is_fail_severity():
    from qc_scanner.qc import REASONS

    assert REASONS["NO_CROP_DETECTED"].severity == "fail"


def test_edge_fallback_is_never_silent():
    """Đường lui được phép cứu ảnh, nhưng không được giấu việc đã phải dùng nó."""
    from qc_scanner.qc import REASONS

    assert REASONS["RECOVERED_BY_EDGE_FALLBACK"].severity == "warn"
    assert REASONS["FALLBACK_ORIGINAL"].severity == "fail"


def test_every_reason_code_appears_in_the_published_catalogue():
    """`algorithm.md §7` tự nhận là **danh mục** mã lý do, nên nó phải đầy đủ.

    Không có bài này thì nó trôi trong im lặng: `INFERENCE_FAILED`, `MISSING_FILE` và
    `DETECTOR_DISAGREEMENT` đều từng chạy trong production mà không có dòng nào trong
    danh mục. Khách đọc tài liệu, gặp một mã không có ở đó, và không biết phải làm gì.
    """
    import pathlib

    from qc_scanner.qc import REASONS

    root = pathlib.Path(__file__).resolve().parent.parent
    catalogue = (root / "docs" / "algorithm.md").read_text(encoding="utf-8")
    missing = sorted(code for code in REASONS if f"`{code}`" not in catalogue)
    assert not missing, f"thiếu trong docs/algorithm.md §7: {missing}"
