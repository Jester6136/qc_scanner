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
        ("clipped_document", "CLIPPED_EDGE"),
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


def test_edge_fallback_is_never_silent():
    """Đường lui được phép cứu ảnh, nhưng không được giấu việc đã phải dùng nó."""
    from qc_scanner.qc import REASONS

    assert REASONS["RECOVERED_BY_EDGE_FALLBACK"].severity == "warn"
    assert REASONS["FALLBACK_ORIGINAL"].severity == "fail"
