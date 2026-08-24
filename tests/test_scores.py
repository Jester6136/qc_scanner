import cv2
import numpy as np

from classify_scanned.scoring import composite_score, image_quality


def test_image_quality_is_content_aware_for_bright_scan():
    image = np.full((1000, 700, 3), 255, dtype=np.uint8)
    cv2.putText(image, "GIAY CHUNG NHAN", (80, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    result = image_quality(image)
    assert result["score"] is not None
    assert result["brightness"] >= 245
    assert result["contrast"] > 50
    assert result["content_ratio"] < 0.2


def test_composite_score_contains_breakdown_and_penalty():
    result = composite_score(
        {"blur_score": 120, "median_brightness": 245, "est_dpi": 300, "glare_ratio": 0.01},
        [{"code": "BLURRY"}],
    )
    assert result["composite"] is not None
    assert set(result["breakdown"]) >= {"blur", "brightness", "resolution", "glare"}
    assert result["penalties"] == [{"code": "BLURRY", "amount": 20.0}]


def test_score_pdf_does_not_run_document_detection():
    from classify_scanned.doc import score_pdf
    from test_pdf import EXAMPLES, build_pdf

    one_page = build_pdf([EXAMPLES / "doc-1.out.png"])
    result = score_pdf(one_page)
    assert result["source"] == "pdf"
    assert result["page_count"] == 1
    assert result["scores"]["score"] == result["scores"]["original"]["score"]
    assert result["pages"][0]["scores"]["original"]["score"] is not None
