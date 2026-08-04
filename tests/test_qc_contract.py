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
def test_every_reason_speaks_to_both_audiences(code):
    """QC-13: hint tầng nào cũng phải có nội dung, không được để trống một tầng.

    Không có bài này thì việc thêm mã mới sẽ lặng lẽ chỉ điền tầng người chụp —
    đúng cái sai mà QC-13 sinh ra để sửa.
    """
    hints = REASONS[code].hints
    assert set(hints) == {"capturer", "operator"}, code
    for who, text in hints.items():
        assert text.strip(), f"{code} thiếu hint cho {who}"


@pytest.mark.parametrize("code", sorted(REASONS))
def test_operator_hint_is_not_a_copy_of_the_capturer_one(code):
    """Hai tầng phải khác nhau thật.

    Chép nguyên hint người chụp sang tầng vận hành là qua được bài trên mà chẳng
    giải quyết gì: người soi kho ảnh vẫn đọc "chụp lại", vẫn không làm được.
    """
    hints = REASONS[code].hints
    assert hints["capturer"] != hints["operator"], code


@pytest.mark.parametrize("code", sorted(REASONS))
def test_operator_hint_never_tells_them_to_retake_the_photo(code):
    """Người soi hàng chờ không cầm máy ảnh, và ảnh kho thì không chụp lại được."""
    text = REASONS[code].hints["operator"].lower()
    for forbidden in ("chụp lại", "chụp trên nền", "lùi máy", "bật đèn"):
        assert forbidden not in text, f"{code} bảo người vận hành {forbidden!r}"


def test_audience_switches_the_hint():
    capturer = Reason.of("CONTENT_CLIPPED")
    operator = capturer.for_audience("operator")
    assert operator.code == capturer.code and operator.severity == capturer.severity
    assert operator.hint != capturer.hint
    assert operator.hint == REASONS["CONTENT_CLIPPED"].hints["operator"]


def test_both_hints_travel_with_the_result():
    """Phía gọi phải tự hiển thị lại được theo vai người đọc, không cần gọi lại."""
    payload = ScanResult.of(b"x", [Reason.of("BLURRY")]).to_dict()
    assert set(payload["reasons"][0]["hints"]) == {"capturer", "operator"}


def test_system_codes_fall_back_to_the_operator_tier():
    """Mã hệ thống không có tầng riêng — người vận hành mới là người đọc log."""
    from qc_scanner.qc import ScanError

    err = ScanError("FILE_EMPTY")
    assert err.reason.hint == REASONS["FILE_EMPTY"].hints["operator"]


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


def test_every_metric_reaches_the_csv_report():
    """Metric không có cột CSV = metric không ai nhìn thấy.

    Đã xảy ra thật: `CSV_FIELDS` là danh sách chép tay và `DictWriter` được đặt
    `extrasaction="ignore"`, nên `border_ink_ratio` (QC-12) bị nuốt im lặng — hàm
    đo vẫn chạy, số vẫn đúng, báo cáo vẫn thiếu.
    """
    import dataclasses

    from qc_scanner.eval import CSV_FIELDS

    missing = {f.name for f in dataclasses.fields(Metrics)} - set(CSV_FIELDS)
    assert not missing, f"metric không có cột trong báo cáo: {sorted(missing)}"


def test_metrics_always_present(scan_cache_qc):
    """Không có metric thì không chốt được ngưỡng bằng số đo, chỉ đoán."""
    for name, result in scan_cache_qc.items():
        d = result.metrics.to_dict()
        assert "alpha_coverage" in d, name
        assert "fallback_used" in d, name
