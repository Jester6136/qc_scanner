"""QC-18: chữ có nằm ngang sau khi nắn không.

Chỉ số duy nhất soi **đầu ra**. Mọi kiểm tra hình học khác soi tứ giác *trước* khi
nắn và hỏi "biên có hợp lý không"; cái này hỏi thẳng thứ phía OCR cần.
"""

import cv2
import numpy as np
import pytest

from qc_scanner import geometry as geo


def _page(angle=0.0, lines=22, size=(1000, 700)):
    """Trang giấy có dòng chữ giả, quay đi `angle` độ (dương = ngược kim đồng hồ)."""
    h, w = size
    img = np.full((h, w, 3), 250, np.uint8)
    for i in range(60, h - 60, (h - 120) // lines):
        cv2.line(img, (70, i), (w - 70, i), (40, 40, 40), 4)
    if angle:
        m = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1.0)
        img = cv2.warpAffine(img, m, (w, h), borderValue=(250, 250, 250))
    return img


@pytest.mark.parametrize("truth", [0, 3, 10, 15, 24, 30, -12, -25])
def test_meter_reads_back_an_angle_it_was_given(truth):
    """Kiểm chính cái thước trước khi tin số nó đọc.

    Sai số cho phép 1.0° = đúng bước quét. Ngưỡng `max_text_skew_deg` được đặt
    ngoài tầm sai số này chứ không sát nó.
    """
    measured = geo.text_skew_deg(_page(truth), step=1.0)
    assert measured is not None
    assert abs(measured - truth) <= 1.0


def test_blank_page_returns_none_instead_of_claiming_45_degrees():
    """Trang trắng KHÔNG được coi là nghiêng.

    Mọi góc cho profile cùng 0 điểm nên `argmax` trả về ứng viên đầu tiên, tức
    `-limit`. Đo thật trên trang trắng: **-45.0°**. Không có cổng chặn mực thì mọi
    trang gần trắng đều bị kết luận nghiêng 45° và trượt QC.
    """
    blank = np.full((1000, 700, 3), 255, np.uint8)
    assert geo.text_skew_deg(blank, step=1.0) is None


def test_a_single_line_of_text_is_still_enough_to_measure():
    """Cổng chặn mực phải đủ thấp cho trang thưa chữ thật.

    Ngưỡng từng suýt đặt ở 0.005; ca này đo được **0.0048** — tức là nó sẽ im lặng
    trên một tài liệu hoàn toàn hợp lệ. Ngưỡng thật là 0.002.
    """
    img = np.full((1000, 700, 3), 255, np.uint8)
    cv2.putText(img, "CONG HOA XA HOI", (60, 500), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3)
    assert geo.text_skew_deg(img, step=1.0) is not None


def test_merging_characters_into_lines_would_have_missed_the_tilt():
    """Vì sao là projection profile chứ không phải gộp-dòng rồi `minAreaRect`.

    Bản gộp-dòng cần một nhân hình thái **nằm ngang**, tức nó giả định sẵn thứ đang
    cần kiểm: chữ chéo không gộp nổi thành dòng nên rơi khỏi phép đo. Đo trên chính
    ảnh gấp mép, bản đó trả `0.0°` trong khi chữ lệch 24°.

    Test này dựng lại đúng phép đo cũ và chứng minh nó mù, để không ai "tối ưu"
    ngược về nó.
    """
    tilted = _page(24.0)
    gray = cv2.cvtColor(tilted, cv2.COLOR_BGR2GRAY)
    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
    merged = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)
    count, _, stats, _ = cv2.connectedComponentsWithStats(merged, 8)
    wide = [
        i
        for i in range(1, count)
        if stats[i, cv2.CC_STAT_WIDTH] > 4 * max(stats[i, cv2.CC_STAT_HEIGHT], 1)
    ]

    # Phép đo cũ gần như không thấy dòng nào; phép đo mới đọc đúng 24°.
    assert len(wide) < 5
    assert abs(geo.text_skew_deg(tilted, step=1.0) - 24.0) <= 1.0


def test_threshold_sits_outside_the_meters_own_error():
    """Ngưỡng phải cách xa nhiễu đo, và cách xa trần của nhóm ảnh sạch.

    Ngành đặt ±1° (FADGI mức 4 sao, Dynamsoft) nhưng đo trên **máy quét phẳng**.
    Ta nhận ảnh chụp rồi nắn phối cảnh; trần nhóm sạch đo được cũng là 1.0°, mà sai
    số thước cũng 1.0° — đặt ngưỡng ở đó thì mọi ảnh sạch thành ca 50-50.
    """
    from qc_scanner.config import Config

    cfg = Config()
    assert cfg.max_text_skew_deg >= 5 * cfg.text_skew_step_deg
    assert cfg.max_text_skew_deg < 24.0  # ca hỏng thật vẫn phải bị bắt


def test_a_broken_warp_is_never_rotated_straight():
    """Quy tắc quan trọng nhất của QC-19: **không xoay che một phép nắn hỏng**.

    Lệch 24° không phải "hơi nghiêng" mà là dấu hiệu tứ giác đã sai (nếp gấp làm máy
    nhận nhầm mép). Xoay nó về 0 thì ảnh vẫn mất nội dung — chỉ khác là nay trông
    hợp lệ, và người soi mất luôn manh mối duy nhất. Nên deskew chỉ chạy TRONG
    ngưỡng `max_text_skew_deg`.
    """
    import dataclasses

    from qc_scanner import doc
    from qc_scanner.config import Config
    from qc_scanner.qc import Metrics

    cfg = Config()
    warped = _page(0.0)

    hong = Metrics(text_skew_deg=24.0)
    assert doc._deskew(warped, cfg, hong) is warped
    assert hong.deskew_applied_deg is None

    sua_duoc = Metrics(text_skew_deg=3.0)
    assert doc._deskew(warped, cfg, sua_duoc) is not warped
    assert sua_duoc.deskew_applied_deg == 3.0

    tat = dataclasses.replace(cfg, deskew=False)
    m = Metrics(text_skew_deg=3.0)
    assert doc._deskew(warped, tat, m) is warped
    assert m.deskew_applied_deg is None


def test_the_reported_angle_is_the_one_measured_not_the_one_left_over():
    """`text_skew_deg` phải là góc **đo được**, không phải phần dư sau khi sửa.

    Gộp hai thứ làm một thì sau khi bật deskew, mọi ảnh đều báo ~0° và chỉ số mất
    sạch giá trị chẩn đoán — không ai biết ảnh vào vốn lệch bao nhiêu nữa.
    """
    from qc_scanner import doc
    from qc_scanner.config import Config
    from qc_scanner.qc import Metrics

    m = Metrics(text_skew_deg=3.0)
    doc._deskew(_page(0.0), Config(), m)
    assert m.text_skew_deg == 3.0
    assert m.deskew_applied_deg == 3.0


def test_deskew_actually_straightens():
    """Xoay xong thì đo lại phải ra ~0 — kiểm kết quả, không kiểm ý định."""
    tilted = _page(6.0)
    before = geo.text_skew_deg(tilted, step=0.5)
    after = geo.text_skew_deg(geo.deskew(tilted, before), step=0.5)
    assert abs(before) >= 5.0
    assert abs(after) <= 1.0


def test_a_lost_detector_fails_even_when_its_quad_is_small():
    """QC-20: "không cắt được gì" KHÔNG đồng nghĩa "tứ giác to gần bằng khung".

    Ảnh thật `2aOboQpF50…`: detector không dựng nổi 4 đỉnh (`conf 0.6`), trả về một
    `minAreaRect` xoay bao cả cái loa, cây bút và chiếc ghế, góc lọt 32.6px ra ngoài
    khung. Ảnh ra gần y ảnh vào — nhưng hình chữ nhật ấy chỉ phủ **0.793** khung nên
    không vượt ngưỡng diện tích 0.90, và cả chuỗi chỉ ra `warn`.

    Một tứ giác sai bét vẫn có thể nhỏ hơn khung.
    """
    from qc_scanner.config import Config
    from qc_scanner.doc import _no_crop_detected
    from qc_scanner.qc import Metrics

    cfg = Config()

    # Ca thật đã lọt: tứ giác NHỎ hơn ngưỡng diện tích, nhưng detector đã thua.
    lot = Metrics(
        detector_confidence=0.6, corners_outside_px=32.6,
        quad_area_ratio=0.793, touches_border=3,
    )
    assert _no_crop_detected(lot, cfg, struggled=True)

    # Detector tự tin, góc nằm trong ảnh → người chụp lấy khung sát, KHÔNG phải lỗi.
    sat = Metrics(
        detector_confidence=0.9, corners_outside_px=0.0,
        quad_area_ratio=0.793, touches_border=3,
    )
    assert not _no_crop_detected(sat, cfg, struggled=False)

    # Đường cũ (QC-11) vẫn phải nguyên: tứ giác gần trọn khung + chạm mép + thua.
    khung = Metrics(
        detector_confidence=0.6, corners_outside_px=0.0,
        quad_area_ratio=0.985, touches_border=4,
    )
    assert _no_crop_detected(khung, cfg, struggled=True)
