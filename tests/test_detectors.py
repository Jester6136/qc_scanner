"""S-2 — lõi QC không phụ thuộc detector nào, và bộ lọc tứ giác (QUAL-1) hoạt động."""

import numpy as np
import pytest

import synthetic as S
from qc_scanner import geometry as geo
from qc_scanner.config import Config
from qc_scanner.detect import DETECTORS, QuadCandidate, best_candidate, get_detector
from qc_scanner.doc import scan_qc


def test_unknown_detector_fails_loudly():
    with pytest.raises(ValueError, match="detector không rõ"):
        get_detector("không-tồn-tại")


@pytest.mark.parametrize("name", sorted(DETECTORS))
def test_every_detector_is_usable_as_primary(name):
    """Đổi detector phải là đổi một dòng cấu hình, không phải viết lại lõi."""
    result = scan_qc(S.document_on_dark_background(), config=Config(detector=name))
    assert result.verdict in {"pass", "warn", "fail"}
    assert result.image is not None


def test_result_records_which_detector_ran():
    result = scan_qc(S.document_on_dark_background(), config=Config(detector="rembg-contour"))
    assert result.metrics.detector == "rembg-contour"
    assert result.metrics.detector_confidence is not None


def test_cross_check_reports_iou():
    """S-6: bất đồng giữa hai detector là tín hiệu QC miễn phí — không cần nhãn."""
    result = scan_qc(
        S.document_on_dark_background(),
        config=Config(cross_check_detectors=True),
    )
    assert result.metrics.detector_iou is not None
    if result.metrics.detector_iou < Config().min_detector_iou:
        assert "DETECTOR_DISAGREEMENT" in result.codes


def test_quad_filter_prefers_valid_candidate_over_larger_junk():
    """QUAL-1: không còn 'lấy tứ giác đầu tiên gặp'.

    Ứng viên rác to hơn nhưng nghiêng cực đoan phải thua ứng viên hợp lệ nhỏ hơn.
    """
    shape = np.zeros((500, 500), np.uint8)
    good = QuadCandidate(
        np.array([[50, 50], [450, 50], [450, 450], [50, 450]], np.float32), 0.9, "x"
    )
    junk = QuadCandidate(
        np.array([[0, 0], [499, 0], [260, 499], [240, 499]], np.float32), 0.9, "x"
    )
    picked = best_candidate([junk, good], shape, Config())
    assert np.allclose(picked.corners, good.corners)


def test_non_convex_quad_is_detected():
    concave = np.array([[0, 0], [100, 0], [50, 40], [100, 100]], np.float32)
    assert not geo.is_convex(concave)


def test_skew_ratio_is_one_for_a_rectangle():
    rect = np.array([[0, 0], [200, 0], [200, 100], [0, 100]], np.float32)
    assert geo.skew_ratio(rect) == pytest.approx(1.0, abs=1e-3)


def test_iou_of_identical_quads_is_one():
    quad = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], np.float32)
    assert geo.iou(quad, quad, (100, 100)) == pytest.approx(1.0, abs=1e-2)


def test_work_size_never_upscales():
    """QUAL-2: phóng to ảnh nhỏ là bịa thông tin."""
    from qc_scanner.doc import _to_work_size

    small = np.zeros((200, 300, 4), np.uint8)
    assert _to_work_size(small, Config(work_height=500)).shape[0] == 200
