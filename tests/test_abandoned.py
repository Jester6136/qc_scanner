"""QC-22: đường cắt của **chính ta** chém vào tài liệu.

Lỗ hổng này lọt tới tay khách. PDF thật, trang bìa một sổ đỏ: tứ giác nằm gọn
giữa khung (`touches_border = 0`) rồi chém chéo qua tờ giấy, xén trọn dòng tiêu
đề. Kết quả trả về `pass` với **không một mã lý do nào**.

Nó lọt vì mọi phép kiểm cắt xén khác đều hỏi *"khung hình có cắt mất chữ không"*,
nên chỉ soi những cạnh mà tứ giác áp vào mép ảnh. Ở đây `border_ink_ratio = 0.000`
không có nghĩa là không mất gì — nó có nghĩa là phép kiểm **không hề chạy**.

Đo thẳng trên `content_outside_quad` chứ không đi qua `scan_qc`: ép rembg khoanh
nhầm một cách tất định thì không làm được, còn truyền tứ giác vào tay thì dựng
đúng tình huống. Cùng lý do với `test_border_ink.py`.
"""

import cv2
import numpy as np

from qc_scanner import geometry as geo

H, W = 1200, 900


def _document(gold_on_red=False):
    """Tờ giấy phủ gần kín khung, đầy chữ.

    `gold_on_red` dựng lại bìa sổ đỏ — chữ **sáng trên nền tối**. Đây là ca đã làm
    hỏng hai thước trước đó: `ink_mask` tìm nét tối trên nền sáng nên không thấy gì,
    `paper_mask` đo theo độ sáng nên không coi bìa đỏ là giấy. Cả hai cùng trả 0.000
    ở đúng ca cần bắt.
    """
    img = np.full((H, W, 3), 40, np.uint8)  # mặt bàn tối
    if gold_on_red:
        page, text = (35, 30, 120), (90, 190, 220)
    else:
        page, text = (245, 245, 245), (50, 50, 50)
    cv2.rectangle(img, (60, 60), (W - 60, H - 60), page, -1)
    for y in range(120, H - 100, 46):
        cv2.line(img, (110, y), (W - 110, y), text, 9)
    return img


def _mask(img):
    """Mặt nạ = đúng tờ giấy. Ở đây ta kiểm phép đo, không kiểm rembg."""
    m = np.zeros((H, W), np.uint8)
    cv2.rectangle(m, (60, 60), (W - 60, H - 60), 255, -1)
    return m


WHOLE = np.array([[60, 60], [W - 60, 60], [W - 60, H - 60], [60, H - 60]], np.float32)
#: Cắt chéo bỏ hẳn góc dưới-trái — đúng hình dạng của ca thật.
DIAGONAL = np.array([[60, 60], [W - 60, 60], [W - 60, H - 60], [60, H // 2]], np.float32)


def test_a_diagonal_cut_through_the_page_is_caught():
    img = _document()
    ratio, structure = geo.content_outside_quad(img, DIAGONAL, _mask(img))

    assert ratio >= 0.10, "một mảng tài liệu bị bỏ lại ngoài đường cắt"
    assert structure >= 0.10, "mảng đó đầy chữ, không phải nền trơn"


def test_a_correct_crop_raises_nothing():
    img = _document()
    ratio, _ = geo.content_outside_quad(img, WHOLE, _mask(img))
    assert ratio < 0.10


def test_light_text_on_a_dark_cover_is_caught_too():
    """Ca thật đầu tiên gặp được là **bìa đỏ sổ đỏ, chữ nhũ vàng**.

    Thước dựa trên `ink_mask`/`paper_mask` trả 0.000 ở đây và bỏ lọt hoàn toàn. Mật
    độ biên không giả định chiều tương phản nên không có điểm mù đó — đó là cả lý do
    phép đo này đếm biên chứ không đếm mực.
    """
    img = _document(gold_on_red=True)
    ratio, structure = geo.content_outside_quad(img, DIAGONAL, _mask(img))

    assert ratio >= 0.10
    assert structure >= 0.10


def test_a_mask_that_swallows_the_table_is_not_mistaken_for_a_cut():
    """Ca thật `abc1b13`: cắt **hoàn toàn đúng**, nhưng rembg trùm cả mặt bàn.

    Ảnh này cho tỉ lệ mảng 0.241 — **cao hơn cả ba ca cắt lẹm thật**. Nếu chỉ đo diện
    tích thì nó là báo động giả đứng đầu bảng. Thước cấu trúc là thứ duy nhất tách
    được: mặt bàn trơn, còn nửa tài liệu bị cắt thì đầy chi tiết.
    """
    img = _document()
    mask = _mask(img)
    cv2.rectangle(mask, (0, 0), (55, H - 1), 255, -1)  # rembg nuốt thêm dải bàn trơn

    ratio, structure = geo.content_outside_quad(img, WHOLE, mask)
    assert structure < 0.10, "dải bàn trơn không được coi là nội dung"


def test_a_thin_rim_of_mask_around_the_quad_is_not_a_cut():
    """Mặt nạ luôn rộng hơn tứ giác một viền mỏng, và viền đó **bao quanh** nên cộng
    lại ra diện tích đáng kể — ảnh cắt đúng vẫn cho 0.074 khi co nhẹ. Đây là lý do
    bước co phải mạnh (6% cạnh ngắn), chứ không phải để khử nhiễu."""
    img = _document()
    inner = np.array(
        [[75, 75], [W - 75, 75], [W - 75, H - 75], [75, H - 75]], np.float32
    )
    ratio, _ = geo.content_outside_quad(img, inner, _mask(img))
    assert ratio < 0.10


def test_erosion_is_what_separates_a_rim_from_a_cut():
    """Khoá lại chính tham số quyết định. Co yếu thì viền và vết cắt lẫn vào nhau;
    đó là phiên bản đầu và nó **không tách được** ca thật."""
    img = _document()
    mask = _mask(img)
    weak = geo.content_outside_quad(img, DIAGONAL, mask, erode_ratio=0.02)[0]
    strong = geo.content_outside_quad(img, DIAGONAL, mask, erode_ratio=0.06)[0]
    assert strong > 0.10, "vết cắt đặc nên chịu được co mạnh"
    assert strong > weak * 0.5, "co mạnh không được ăn mất phần lớn vết cắt"


def test_an_amorphous_mask_is_not_trusted_as_evidence():
    """Cổng thứ ba, và nó ra đời từ một thất bại đo được trên bộ chuẩn.

    Với hai điều kiện đầu, phép kiểm loại oan **171/244 ảnh nền bàn bừa bộn** của
    SmartDoc (`background05`) — trong khi IoU của tứ giác với nhãn ở đó là 0.988, tức
    cắt gần như hoàn hảo. Tính chung 173/2421 = 7.15% báo động giả, **0 ca bắt đúng**.

    Nguyên nhân: rembg trùm cả mặt bàn, nên mảng "bị bỏ rơi" là bút, dây, giấy khác —
    to *và* có cấu trúc, qua được cả hai cổng đầu. Cổng cấu trúc chỉ chặn được nền
    **trơn**; bàn **bừa bộn** thì có cấu trúc.

    Điểm bất đối xứng cứu được: khi *tứ giác* sai thì mặt nạ vẫn là một tờ giấy vuông
    vắn; khi *mặt nạ* sai thì nó vô định hình.
    """
    assert geo.mask_quad_fit(_mask(_document())) >= 0.85, "mặt nạ đúng một tờ giấy"

    # Hình dạng của ca thật: tài liệu NHỎ giữa khung, rác rải khắp bàn quanh nó. Đốm
    # nằm gọn trong tờ giấy thì hình chữ nhật bao không đổi và bài này xanh mà chẳng
    # kiểm gì — phải để rác vươn ra ngoài mới tái hiện được.
    messy = np.zeros((H, W), np.uint8)
    cv2.rectangle(messy, (330, 480), (570, 720), 255, -1)  # tờ giấy
    for cx, cy, r in ((90, 90, 80), (800, 120, 70), (120, 1080, 90), (810, 1100, 75)):
        cv2.circle(messy, (cx, cy), r, 255, -1)  # bút, dây, giấy khác trên bàn
    assert geo.mask_quad_fit(messy) < 0.85, "mặt nạ vô định hình thì không đáng tin"


def test_the_gate_still_lets_the_real_cut_through():
    """Ngưỡng phải nằm giữa **vùng bằng phẳng**, không sát mép nào.

    Quét trên 2421 ảnh SmartDoc + 32 ảnh thật: `fit ≥ 0.83…0.88` đều cho 0 báo động
    giả và giữ đủ 3/3 ca cắt lẹm; 0.89 bắt đầu **mất ca thật của khách**. Báo động giả
    cao nhất đo được 0.822, ca cắt lẹm thấp nhất 0.889.
    """
    assert geo.mask_quad_fit(_mask(_document())) >= 0.889


def test_no_mask_means_no_claim():
    """Không có mặt nạ thì không có căn cứ nào — phải trả 0.0, không được đoán."""
    img = _document()
    assert geo.content_outside_quad(img, WHOLE, None) == (0.0, 0.0)
