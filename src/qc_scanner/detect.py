"""Interface `Detector` + hai cài đặt (S-2).

Lõi QC nhận `QuadCandidate` từ **bất kỳ** detector nào rồi mới phán quyết, nên
đổi detector là đổi một dòng cấu hình — và chạy được hai detector song song
trên cùng tập ảnh để so bằng số thay vì bằng cảm tính.

Chỗ cắm cho hướng hồi quy 4 góc trực tiếp (DocAligner…): thêm một lớp cài
`find_quad()` rồi đăng ký vào `DETECTORS`. Không đụng vào lõi QC.
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from . import geometry as geo
from .config import Config
from .qc import ScanError


@dataclass
class QuadCandidate:
    """4 điểm (hệ toạ độ ảnh làm việc) + độ tin cậy + tên detector sinh ra nó."""

    corners: np.ndarray
    confidence: float
    detector: str

    contour: Optional[np.ndarray] = None
    """Contour gốc sinh ra tứ giác này, nếu detector có.

    Lõi QC dùng nó để nới cạnh ra bao trọn mép giấy cong (QC-17). Detector nào
    không làm việc trên contour (edge-hough) thì để `None` và bước đó tự bỏ qua.
    """

    def __post_init__(self):
        self.corners = geo.order_corners(self.corners)


class Detector:
    """Giao thức: nhận ảnh làm việc → trả tứ giác tốt nhất, hoặc None."""

    name = "base"

    low_confidence = None
    """Dưới mức này thì coi như detector **không chắc** — `None` = dùng cấu hình.

    Phải theo từng detector vì các thang này KHÔNG so được với nhau: rembg trả
    đúng hai giá trị rời rạc (0.9 khi `approxPolyDP` ra 4 đỉnh, 0.6 khi phải ép về
    `minAreaRect`), còn docaligner trả đỉnh thấp nhất trong 4 bản đồ nhiệt — một
    số thực liên tục. Áp ngưỡng 0.9 của rembg lên docaligner là gắn cờ gần như mọi
    ảnh: trung vị của nó trên 30 ảnh thật là 0.841.
    """

    uses_mask = True
    """Detector này có đọc mask rembg không.

    `False` thì lõi đưa cho nó ảnh **chưa bôi nền đen**. Chuyện này quan trọng hơn
    vẻ ngoài: bôi nền là đã áp kết quả của rembg lên đầu vào, nên một detector độc
    lập sẽ thừa hưởng luôn cái sai của rembg — đúng thứ mà phép so sánh đang muốn
    đo xem có tránh được không. Chưa kể mô hình học trên ảnh chụp thật, ảnh có
    nền đen tuyệt đối nằm ngoài phân phối nó từng thấy.
    """

    def find_quad(self, work_img, mask, config) -> Optional[QuadCandidate]:
        raise NotImplementedError

    def all_candidates(self, work_img, mask, config) -> list[QuadCandidate]:
        found = self.find_quad(work_img, mask, config)
        return [found] if found else []


class RembgContourDetector(Detector):
    """Đường chính hiện tại: mask alpha của rembg → contour → approxPolyDP.

    Khác bản gốc ở chỗ **không lấy tứ giác đầu tiên gặp**: duyệt hết ứng viên,
    chấm điểm bằng bộ lọc hình học rồi mới chọn (QUAL-1). Một vệt nhiễu vuông
    vắn hoặc một ô trong bảng không còn thắng được tờ giấy thật.
    """

    name = "rembg-contour"

    def all_candidates(self, work_img, mask, config: Config):
        if mask is None:
            return []
        cnts = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

        img_area = float(mask.shape[0] * mask.shape[1])
        out = []
        for c in cnts:
            if cv2.contourArea(c) < config.candidate_area_ratio * img_area:
                break  # đã sắp giảm dần nên các contour sau còn nhỏ hơn
            perimeter = cv2.arcLength(c, True)
            polygon = cv2.approxPolyDP(
                c, config.approx_poly_epsilon_ratio * perimeter, True
            )
            if len(polygon) != 4:
                polygon = _min_area_quad(c)
                confidence = 0.6  # phải ép về hình chữ nhật xoay → kém chắc chắn
            else:
                confidence = 0.9
            out.append(
                QuadCandidate(polygon.reshape(4, 2), confidence, self.name, contour=c)
            )
        return out

    def find_quad(self, work_img, mask, config: Config):
        return best_candidate(self.all_candidates(work_img, mask, config), mask, config)


class EdgeHoughDetector(Detector):
    """Đường lui cổ điển: Canny → HoughLinesP → 2 cụm hướng → 4 giao điểm.

    Ca rembg hay thua nhất là **giấy trắng trên nền sáng**. Dò cạnh không cần
    tách nền nên vẫn có cơ hội — đổi lại nó bắt nhầm đường kẻ trong tài liệu,
    nên chỉ dùng làm đường lui, không làm đường chính.
    """

    name = "edge-hough"

    def all_candidates(self, work_img, mask, config: Config):
        gray = geo._gray(work_img)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, 75, 200)

        h, w = edges.shape[:2]
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=60,
            minLineLength=int(min(h, w) * 0.3),
            maxLineGap=int(min(h, w) * 0.05),
        )
        if lines is None or len(lines) < 4:
            return []

        # OpenCV 4 trả (N, 1, 4), OpenCV 5 trả (N, 4). Chuẩn hoá về (N, 4) thay
        # vì đoán theo version — hai build khác nhau vẫn phải chạy như nhau.
        segments = np.asarray(lines).reshape(-1, 4)

        horizontal, vertical = [], []
        for x1, y1, x2, y2 in segments:
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            (horizontal if angle < 45 or angle > 135 else vertical).append(
                (x1, y1, x2, y2)
            )
        if not horizontal or not vertical:
            return []

        top = min(horizontal, key=lambda ln: (ln[1] + ln[3]) / 2)
        bottom = max(horizontal, key=lambda ln: (ln[1] + ln[3]) / 2)
        left = min(vertical, key=lambda ln: (ln[0] + ln[2]) / 2)
        right = max(vertical, key=lambda ln: (ln[0] + ln[2]) / 2)

        corners = []
        for hline in (top, bottom):
            for vline in (left, right):
                pt = _intersect(hline, vline)
                if pt is None:
                    return []
                corners.append(pt)
        quad = np.array(corners, dtype=np.float32)
        if geo.quad_area(geo.order_corners(quad)) < 1e-3:
            return []
        return [QuadCandidate(quad, 0.5, self.name)]

    def find_quad(self, work_img, mask, config: Config):
        return best_candidate(self.all_candidates(work_img, mask, config), work_img, config)


def best_candidate(candidates, reference_img, config: Config):
    """Chọn ứng viên tốt nhất: ưu tiên qua được bộ lọc, sau đó diện tích lớn hơn.

    Trả về cả ứng viên **không** qua lọc (khi không còn gì tốt hơn) — lõi QC cần
    nó để giải thích *vì sao* loại, bằng chính metric đã tính, thay vì im lặng.
    """
    if not candidates:
        return None
    shape = reference_img.shape
    img_area = float(shape[0] * shape[1])

    def score(cand):
        area_ratio = geo.quad_area(cand.corners) / img_area
        passes = (
            geo.is_convex(cand.corners)
            and area_ratio >= config.min_quad_area_ratio
            and geo.skew_ratio(cand.corners) <= config.max_skew_ratio
        )
        return (1 if passes else 0, area_ratio, cand.confidence)

    return max(candidates, key=score)


class DocAlignerDetector(Detector):
    """Hồi quy 4 góc trực tiếp — KHÔNG qua mask, KHÔNG qua contour.

    Khác hẳn hai detector kia về bản chất: chúng đi tìm *vùng*, rồi suy ra góc từ
    biên vùng đó; cái này đoán thẳng 4 góc. Hệ quả thực tế là nó **không có
    contour** để trả về, nên bước nới cạnh bao mép giấy cong (QC-17) tự bỏ qua —
    đây là điều phải nhớ khi đọc kết quả so sánh, chứ không phải lỗi.

    Cần trỏ `docaligner_model` vào file `.onnx` đã tải sẵn. Xem `docaligner.py`
    về lý do không tải tự động.
    """

    name = "docaligner"
    uses_mask = False

    #: Đo được: trên 926 ảnh SmartDoc có nhãn, thang này nằm gọn trong 0.912–0.945
    #: và **không ảnh nào** IoU < 0.90 — tức ở đó không có ca thua nào để hiệu
    #: chuẩn, và tương quan conf–IoU chỉ −0.08. Trên 30 ảnh thật của khách thì
    #: rộng hơn hẳn: 0.349–0.935, trung vị 0.841, phân vị 10 là 0.449.
    #:
    #: Chưa có bằng chứng "conf thấp ⇒ cắt sai", nên đặt ở phân vị 10 và để nó chỉ
    #: nói *một nửa* câu: `NO_CROP_DETECTED` còn đòi thêm góc lọt ra ngoài khung.
    #: Đặt cao hơn là gắn cờ hàng loạt dựa trên một tín hiệu chưa chứng minh được.
    low_confidence = 0.45

    def find_quad(self, work_img, mask, config: Config):
        from . import docaligner as da

        path = da.resolve_model(config.docaligner_head, config.docaligner_model)
        if path is None:
            raise ScanError(
                "MODEL_MISSING",
                f"thiếu mô hình DocAligner (tìm ở {da.model_home()}); "
                "chạy `qc-scanner-fetch-models` hoặc trỏ QC_SCANNER_DOCALIGNER_MODEL",
            )

        if config.docaligner_head == "point":
            corners, confidence = da.predict_point(path, work_img, config.onnx_providers)
        else:
            corners, confidence = da.predict_heatmap(
                path, work_img, config.onnx_providers
            )
        if corners is None:
            return None
        return QuadCandidate(corners, float(confidence), self.name)


DETECTORS = {
    RembgContourDetector.name: RembgContourDetector,
    EdgeHoughDetector.name: EdgeHoughDetector,
    DocAlignerDetector.name: DocAlignerDetector,
}


def get_detector(name: str) -> Detector:
    try:
        return DETECTORS[name]()
    except KeyError:
        raise ValueError(
            f"detector không rõ: {name!r} (có: {', '.join(sorted(DETECTORS))})"
        ) from None


def _min_area_quad(contour):
    box = cv2.boxPoints(cv2.minAreaRect(contour))
    return np.asarray(box, dtype=np.float32).reshape(4, 1, 2)


def _intersect(line_a, line_b):
    x1, y1, x2, y2 = line_a
    x3, y3, x4, y4 = line_b
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None
    det_a = x1 * y2 - y1 * x2
    det_b = x3 * y4 - y3 * x4
    return (
        (det_a * (x3 - x4) - (x1 - x2) * det_b) / denom,
        (det_a * (y3 - y4) - (y1 - y2) * det_b) / denom,
    )
