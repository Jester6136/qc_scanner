"""QC-21: `border_ink_ratio` phải đếm **mực trên giấy**, không đếm nền tối.

Đo thẳng trên `ink_at_image_border` chứ không đi qua `scan_qc`: ca cần kiểm là
"tứ giác trùm cả nền", mà ép rembg khoanh nhầm một cách tất định thì không làm
được. Truyền tứ giác vào tay là dựng đúng tình huống, không phải dựng gần đúng.
"""

import cv2
import numpy as np

from qc_scanner import geometry as geo

FULL_FRAME = np.array([[0, 0], [899, 0], [899, 1199], [0, 1199]], dtype=np.float32)


def _scene(table_width=260):
    """Mặt bàn tối có vân, chạy tới sát mép trái; tờ giấy sạch ở phần còn lại.

    Vân bàn là thứ làm hỏng phép đo cũ: `ink_mask` hỏi "tối hơn xung quanh", và
    vân gỗ trả lời *có* y như nét chữ. Bàn phẳng lì thì test này xanh cả trước
    lẫn sau khi sửa, tức là không kiểm gì.
    """
    img = np.full((1200, 900, 3), 60, np.uint8)
    # Vân bàn phải chạy **qua dải sát mép** mới tái hiện được lỗi: dải soi chỉ rộng
    # 1% cạnh ngắn (9px), nên vân rải ngẫu nhiên khắp mặt bàn hầu như không rơi vào
    # đó và phép đo cũ chỉ ra 0.0397 — dưới ngưỡng, test xanh mà chẳng kiểm gì.
    for y in range(0, 1200, 22):
        cv2.line(img, (0, y), (table_width - 1, y), (26, 26, 26), 8)

    paper_width = 900 - table_width
    paper = np.full((1200, paper_width, 3), 245, np.uint8)
    for y in range(40, 1160, 60):
        cv2.line(paper, (30, y), (paper_width - 30, y), (60, 60, 60), 6)
    img[:, table_width:] = paper
    return img


def test_dark_table_inside_the_quad_is_not_counted_as_ink():
    """Ca thật `04.57.20`: dải trái là mặt bàn, không mất chữ nào, vẫn bị báo động.

    Trước khi sửa: 0.2271, đủ vượt `max_border_ink_ratio` 0.08 → CONTENT_CLIPPED
    (`fail`). Nền cục bộ tại chính những pixel bị gọi là "mực" có trung vị 64,
    trong khi vùng giấy của cùng ảnh nằm ở 130–155.
    """
    img = _scene()

    without_gate = geo.ink_at_image_border(img, FULL_FRAME, paper_min_ratio=0)
    with_gate = geo.ink_at_image_border(img, FULL_FRAME, paper_min_ratio=0.6)

    assert without_gate > 0.08, "ảnh dựng không tái hiện được lỗi cũ thì test vô nghĩa"
    assert with_gate <= 0.08


def test_text_running_off_the_edge_is_still_caught():
    """Nửa còn lại của cùng một phép tách — và là nửa quan trọng hơn.

    Bỏ nền khỏi phép đếm mà làm mất luôn khả năng bắt chữ bị cắt thì đã đổi một
    lỗi báo thừa lấy một lỗi **cho lọt**, tức là đổi lấy thứ đắt hơn ([EX-1]).
    """
    img = np.full((1200, 900, 3), 245, np.uint8)
    for y in range(6, 1194, 40):
        cv2.line(img, (0, y), (880, y), (55, 55, 55), 9)  # chữ chạy thẳng ra mép trái

    assert geo.ink_at_image_border(img, FULL_FRAME, paper_min_ratio=0.6) > 0.08


def test_the_paper_level_follows_the_image_not_a_fixed_brightness():
    """Ảnh chụp thiếu sáng: cả tờ giấy cũng tối, nhưng chữ vẫn phải bắt được.

    Mốc "sáng" là hằng số tuyệt đối thì ảnh tối bị coi là toàn nền, và mọi kiểm
    tra cắt xén tắt lịm — im lặng, đúng kiểu hỏng khó thấy nhất.
    """
    img = np.full((1200, 900, 3), 96, np.uint8)  # giấy xám vì thiếu sáng
    for y in range(6, 1194, 40):
        cv2.line(img, (0, y), (880, y), (18, 18, 18), 9)

    assert geo.ink_at_image_border(img, FULL_FRAME, paper_min_ratio=0.6) > 0.08


def test_paper_level_holds_when_the_quad_is_mostly_background():
    """Tứ giác trùm 78% mặt bàn — mốc "giấy" phải đứng yên đúng lúc này.

    Đây là ca đã bác bỏ lựa chọn đầu của tôi. Với phân vị 75, mốc rơi thẳng vào
    vùng nền và **100%** mặt bàn được nhận là giấy: không phải sai lệch, mà là
    tắt hẳn phép kiểm — và tắt không tiếng động, chẳng mã lý do nào bật lên.
    p85 còn 1%, p90 còn 0%.
    """
    scene = _scene(table_width=700)
    assert geo.paper_mask(scene, FULL_FRAME, 0.6, percentile=75)[:, :700].mean() > 0.9

    mask = geo.paper_mask(scene, FULL_FRAME, min_ratio=0.6)
    assert mask[:, :700].mean() < 0.1, "mặt bàn bị nhận nhầm là giấy"
    assert mask[:, 700:].mean() > 0.9, "dải giấy thật bị loại"
