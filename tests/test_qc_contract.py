"""§3a — bất biến của hợp đồng QC, thực thi ở mức code.

Bài `test_every_reason_is_actionable` là **nguyên tắc thiết kế biến thành test**:
không ai thêm được mã lý do thiếu hướng xử lý mà bộ test vẫn xanh.
"""

import pytest

from qc_scanner.qc import REASONS, Metrics, Reason, ScanResult, verdict_of

AUDIENCES = {"capturer", "operator", "system"}
SEVERITIES = {"warn", "fail"}


@pytest.mark.parametrize("code", sorted(REASONS))
def test_every_reason_is_actionable(code):
    spec = REASONS[code]
    assert spec.hint.strip(), f"{code} thiếu hint — mã không hành động được là mã vô dụng"
    assert spec.audience in AUDIENCES, f"{code} có audience lạ: {spec.audience}"
    assert spec.severity in SEVERITIES
    assert spec.message.strip()


@pytest.mark.parametrize("code", sorted(REASONS))
def test_code_is_stable_uppercase(code):
    """Mã đi vào log/CSV của khách nên phải ổn định, viết HOA, không dấu."""
    assert code.isupper()
    assert code.replace("_", "").isalnum()
    assert code.isascii()


def test_pass_iff_no_reasons():
    assert verdict_of([]) == "pass"
    assert verdict_of([Reason.of("CLIPPED_EDGE")]) == "warn"
    assert verdict_of([Reason.of("QUAD_NOT_FOUND")]) == "fail"
    assert verdict_of([Reason.of("CLIPPED_EDGE"), Reason.of("BLURRY")]) == "fail"


def test_result_rejects_inconsistent_verdict():
    with pytest.raises(AssertionError):
        ScanResult(image=b"x", verdict="pass", reasons=[Reason.of("BLURRY")])


def test_result_of_computes_verdict():
    r = ScanResult.of(b"x", [Reason.of("CLIPPED_EDGE")], Metrics())
    assert r.verdict == "warn"
    assert (r.verdict == "pass") == (r.reasons == [])


def test_to_dict_is_json_serializable():
    import json

    r = ScanResult.of(b"png", [Reason.of("TOO_SMALL", "quad_area_ratio=0.05")])
    payload = json.loads(json.dumps(r.to_dict(), ensure_ascii=False))
    assert payload["verdict"] == "fail"
    assert payload["reasons"][0]["hint"]
    assert payload["reasons"][0]["detail"] == "quad_area_ratio=0.05"


def test_real_results_satisfy_invariants(scan_cache_qc):
    for name, result in scan_cache_qc.items():
        assert (result.verdict == "pass") == (result.reasons == []), name
        for reason in result.reasons:
            assert reason.hint and reason.audience in AUDIENCES, name


def test_metrics_always_present(scan_cache_qc):
    """Không có metric thì không chốt được ngưỡng bằng số đo, chỉ đoán."""
    for name, result in scan_cache_qc.items():
        d = result.metrics.to_dict()
        assert "alpha_coverage" in d, name
        assert "fallback_used" in d, name
