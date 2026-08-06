"""Bộ chuyển SmartDoc → tập vàng. Chạy được ở mọi checkout, không cần tải gì.

Bộ dữ liệu nặng 1.5GB và nằm ngoài repo, nên thứ kiểm được ở đây là **phần dịch
định dạng** — cũng chính là phần dễ sai âm thầm: nhầm thứ tự 4 góc thì IoU tụt
đều trên mọi ảnh, trông y như "detector kém", và không có gì báo rằng lỗi nằm ở
thước chứ không ở vật được đo.
"""

import cv2
import numpy as np
import pytest

from qc_scanner.smartdoc import build, read_ground_truth

_XML = """<?xml version='1.0' encoding='utf-8'?>
<ground_truth version="0.2">
  <segmentation_results>
    <frame index="1" rejected="false">
      <point name="bl" x="10.5" y="90.5"/>
      <point name="tl" x="11.0" y="20.0"/>
      <point name="tr" x="80.0" y="21.0"/>
      <point name="br" x="81.5" y="91.0"/>
    </frame>
    <frame index="2" rejected="true">
      <point name="bl" x="0" y="0"/>
      <point name="tl" x="0" y="0"/>
      <point name="tr" x="0" y="0"/>
      <point name="br" x="0" y="0"/>
    </frame>
    <frame index="3" rejected="false">
      <point name="tl" x="1" y="2"/>
      <point name="tr" x="3" y="4"/>
    </frame>
  </segmentation_results>
</ground_truth>
"""


@pytest.fixture
def gt_file(tmp_path):
    path = tmp_path / "datasheet001.gt.xml"
    path.write_text(_XML, encoding="utf-8")
    return path


def test_corners_come_out_in_the_order_the_evaluator_expects(gt_file):
    """XML ghi bl→tl→tr→br; bộ eval chờ TL-TR-BR-BL. Đây là chỗ dễ nhầm nhất."""
    corners = read_ground_truth(gt_file)[1]
    assert corners == [[11.0, 20.0], [80.0, 21.0], [81.5, 91.0], [10.5, 90.5]]


def test_rejected_frames_are_dropped(gt_file):
    """`rejected="true"` = khung không có tài liệu. Giữ lại là tự tạo ra ca thua giả."""
    assert 2 not in read_ground_truth(gt_file)


def test_frames_missing_a_corner_are_dropped(gt_file):
    """Nhãn thiếu góc thì bỏ, không đoán bù — nhãn đoán bù là nhãn sai có vẻ đúng."""
    assert 3 not in read_ground_truth(gt_file)


def test_build_writes_labels_next_to_the_frames(tmp_path, gt_file):
    """Đường đi trọn vẹn: video + XML → ảnh rời + `labels.jsonl` bộ eval đọc được."""
    # Dựng đúng bố cục thật của bộ dữ liệu: tên nền nằm ở thư mục `*_gt`, và nó
    # phải chui vào tên file ảnh — nền là biến khó nhất của SmartDoc, gộp chung
    # một rổ thì lúc kết quả xấu không biết xấu ở nền nào.
    truth_dir = tmp_path / "gt" / "background00_gt"
    truth_dir.mkdir(parents=True)
    (truth_dir / gt_file.name).write_text(
        gt_file.read_text(encoding="utf-8"), encoding="utf-8"
    )
    gt_file.unlink()

    videos = tmp_path / "input" / "background00"
    videos.mkdir(parents=True)
    writer = cv2.VideoWriter(
        str(videos / "datasheet001.avi"),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (120, 100),
    )
    if not writer.isOpened():
        pytest.skip("bản OpenCV này không ghi được MJPG")
    for _ in range(3):
        writer.write(np.full((100, 120, 3), 200, np.uint8))
    writer.release()

    out = tmp_path / "goldens"
    count, labels = build(tmp_path, out, stride=1)

    assert count == 1  # khung 2 bị loại, khung 3 thiếu góc
    assert labels.exists()
    written = sorted(p.name for p in out.glob("*.png"))
    assert written == ["background00-datasheet001-0001.png"]
