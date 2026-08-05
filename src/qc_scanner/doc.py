"""Lõi xử lý: `scan_qc()` trả phán quyết kèm ảnh; `scan()` là lớp bọc tương thích.

Nguyên tắc chi phối file này: **không im lặng**. Mọi nhánh không-lý-tưởng
(không tìm được biên, phải dùng đường lui, ảnh mờ) đều phải xuất hiện trong
`reasons`. Trả ảnh gốc mà không báo gì là bug, không phải fallback.
"""

import dataclasses
from typing import Optional

import cv2
import imutils
import numpy as np
from imutils import perspective

from . import geometry as geo
from .config import DEFAULT, Config
from .detect import get_detector
from .pdf import is_pdf, page_images
from .qc import DocumentResult, Metrics, Reason, ScanError, ScanResult
from .rembg_session import segment_mask

# Giữ lại cho mã cũ import trực tiếp; nguồn sự thật nay là Config.
APPROX_POLY_DP_ACCURACY_RATIO = DEFAULT.approx_poly_epsilon_ratio
IMG_RESIZE_H = float(DEFAULT.work_height)


def scan_document(
    data: bytes, config: Optional[Config] = None, debug=None
) -> DocumentResult:
    """Đầu vào **bất kỳ** (ảnh rời hoặc PDF) → kết quả cho cả file, một mục mỗi trang.

    N-08. Đây là cửa vào nên dùng ở mọi mặt tiền mới: nó là hàm duy nhất không phải
    biết trước file có mấy trang. `scan_qc()` vẫn nguyên chữ ký cũ cho mã đã có.
    """
    cfg = config or Config.from_env()
    if not data:
        raise ScanError("FILE_EMPTY")

    if not is_pdf(data):
        return DocumentResult(pages=[scan_qc(data, cfg, debug)], source="image")

    # Trang PDF **chính là** tờ giấy, không phải ảnh chụp tờ giấy: không có nền quanh
    # mép để dò biên, nên mọi kiểm tra về "giấy chạm mép khung" đều báo nhầm. Xem
    # `Config.pdf_pre_cropped` để biết số đo và cái giá của lựa chọn này.
    page_cfg = dataclasses.replace(cfg, pre_cropped=True) if cfg.pdf_pre_cropped else cfg

    pages = []
    for page in page_images(data, cfg):
        result = scan_image(page.image, page_cfg, debug)
        result.metrics.page = page.number
        result.metrics.pdf_source = page.source
        pages.append(result)
    return DocumentResult(pages=pages, source="pdf")


def scan_qc(data: bytes, config: Optional[Config] = None, debug=None) -> ScanResult:
    """Nắn phẳng tài liệu và **chấm điểm chất lượng** kết quả.

    Ném `ScanError` chỉ với lỗi đầu vào không thể đánh giá được (rỗng, không
    decode nổi). Mọi thất bại khác trả `ScanResult` có `verdict="fail"` kèm mã
    lý do — người gọi biết chuyện gì xảy ra và phải làm gì.

    Nhận PDF **một trang** như một tấm ảnh. PDF nhiều trang thì ném `PDF_MULTIPAGE`
    thay vì lặng lẽ chấm trang đầu: một chữ ký trả về đúng một kết quả thì không có
    chỗ chứa 11 trang còn lại, và bỏ chúng đi mà không nói là kiểu hỏng tệ nhất —
    phía gọi tưởng đã soi hết cả hồ sơ.
    """
    cfg = config or Config.from_env()
    metrics = Metrics()

    if not data:
        raise ScanError("FILE_EMPTY")

    if is_pdf(data):
        return _single_pdf_page(data, cfg, debug)

    # SPD-1: giải mã ảnh **một lần duy nhất**, và lấy thẳng mask thay vì bytes PNG.
    # Đường cũ giải mã 2 lần (OpenCV cho `orig`, PIL bên trong rembg) rồi ghép +
    # mã hoá + giải mã lại một ảnh RGBA toàn cỡ chỉ để lấy đúng kênh alpha.
    #
    # Phụ phẩm đáng kể: mọi thứ giờ suy ra từ CÙNG một mảng. Đường cũ tính `ratio`
    # giữa ảnh PIL giải mã và ảnh OpenCV giải mã, tức ngầm tin hai thư viện xoay
    # EXIF giống hệt nhau — đúng trên thực tế, nhưng là giả định không ai kiểm.
    return scan_image(_decode(data), cfg, debug, metrics=metrics)


def _single_pdf_page(data, cfg, debug):
    document = scan_document(data, cfg, debug)
    if document.page_count != 1:
        raise ScanError("PDF_MULTIPAGE", f"{document.page_count} trang")
    return document.pages[0]


def scan_image(
    image, config: Optional[Config] = None, debug=None, metrics: Optional[Metrics] = None
) -> ScanResult:
    """Ảnh BGR **đã giải mã** → phán quyết. Lõi thật sự; `scan_qc()` chỉ thêm bước giải mã.

    Tách ra để đường PDF không phải mã hoá lại từng trang thành PNG chỉ để `scan_qc()`
    giải mã ngược — đúng vòng phí phạm mà SPD-1 đã bỏ đi ở chỗ khác.
    """
    cfg = config or Config.from_env()
    metrics = metrics if metrics is not None else Metrics()
    reasons: list[Reason] = []

    orig = image
    alpha = _segment(orig, cfg)

    work = _to_work_size(orig, cfg)
    ratio = orig.shape[0] / work.shape[0]
    # Ép mask về ĐÚNG kích thước `work`, không tính lại độc lập. Hai đường resize
    # riêng thì phép làm tròn lệch nhau 1px và `cv2.bitwise_and` vỡ — đã dính đúng
    # thế khi thêm `segment_height`. Trước đó nó chạy được chỉ vì hai đường tình cờ
    # cùng xuất phát từ một kích thước; đó là may, không phải bất biến.
    mask = _alpha_mask(_resize_to(alpha, work.shape), cfg)

    # Nền bị bôi đen, đúng như ảnh cutout rembg trả về trước đây: đường lui
    # edge-hough chạy Canny trên `work` nên nó phải thấy cùng một thứ.
    if mask is not None:
        work = cv2.bitwise_and(work, work, mask=mask)

    metrics.alpha_coverage = (
        float(np.count_nonzero(mask) / mask.size) if mask is not None else 0.0
    )
    _debug(debug, "mask", mask)

    detector = get_detector(cfg.detector)
    candidates = detector.all_candidates(work, mask, cfg)
    metrics.contour_candidates = len(candidates)

    quad = _pick(detector, candidates, work, mask, cfg)

    # Đường lui: rembg không tách được chủ thể → thử dò cạnh trước khi bỏ cuộc.
    #
    # QC-16 — điều kiện kích hoạt trước đây gồm cả `alpha_coverage > 0.95`, và nó
    # sai theo hướng đắt nhất: **ghi đè một tứ giác đúng bằng một tứ giác sai**.
    # Ca thật (`04.57.20`): rembg cho tứ giác 0.964 khung, conf 0.9, đúng tờ giấy;
    # alpha 0.969 vượt ngưỡng nên đường lui chạy và trả một dải 0.404 — mất nguyên
    # nửa trên tài liệu. Chuỗi kết thúc bằng `CONTENT_CLIPPED` → `fail`.
    #
    # "Giấy chiếm gần hết khung" KHÔNG có nghĩa là rembg thất bại. Đường lui chỉ chạy
    # khi rembg **không tìm thấy gì**, chứ không phải khi nó tìm thấy quá nhiều.
    #
    # Đã thử nới điều kiện sang cả ca "tứ giác gần trọn khung" và **đo thấy tệ hơn**:
    # trên ba ảnh thật (04.56.41 · 04.57.20 · 04.58.02), rembg cho tứ giác đúng cả tờ
    # còn edge-hough chỉ bắt được một mảnh (0.461 · 0.404 · 0.422) — lần lượt mất
    # trang trong có chữ viết tay, mất nửa trên, và mất hẳn một trang. Đường lui thắng
    # 0/3. Nới điều kiện ở đây là đổi một tứ giác đúng lấy một tứ giác sai.
    fallback_needed = quad is None or metrics.alpha_coverage < cfg.min_alpha_coverage

    if fallback_needed and cfg.enable_edge_fallback:
        recovered = get_detector("edge-hough").find_quad(work, mask, cfg)
        if recovered is not None and _passes_filters(recovered.corners, work, cfg):
            quad = recovered
            metrics.fallback_used = "edge_detect"
            reasons.append(Reason.of("RECOVERED_BY_EDGE_FALLBACK"))

    # QC-15: KHÔNG còn phát `SUBJECT_FILLS_FRAME`. "Giấy chiếm gần hết khung" là một
    # *phỏng đoán* về việc có thể đã mất mép, ra đời khi chưa đo được điều đó. Nay
    # `border_ink_ratio` đo thẳng: giấy đầy khung mà không cắt vào chữ thì **không
    # mất gì** — báo warn ở đó là đẩy ảnh dùng được vào hàng chờ người soi.
    # Đo trên 45 ảnh: mã này phát 4 lần, cả 4 lần đều đi kèm NO_CROP_DETECTED hoặc
    # CONTENT_CLIPPED. Nó chưa bao giờ tự mình quyết verdict.
    # `alpha_coverage` vẫn nằm nguyên trong metrics cho ai cần tra ngược.

    if quad is None:
        if metrics.alpha_coverage < cfg.min_alpha_coverage:
            reasons.append(
                Reason.of(
                    "SUBJECT_NOT_FOUND",
                    f"alpha_coverage={metrics.alpha_coverage:.3f}",
                )
            )
        else:
            reasons.append(Reason.of("QUAD_NOT_FOUND"))
        reasons.append(Reason.of("FALLBACK_ORIGINAL"))
        metrics.fallback_used = "original"
        return ScanResult.of(
            _encode_png(orig),
            _apply_pre_cropped(reasons, cfg, metrics),
            metrics,
            audience=cfg.hint_audience,
        )

    metrics.detector = quad.detector
    metrics.detector_confidence = quad.confidence

    if cfg.cross_check_detectors:
        reasons += _cross_check(quad, work, mask, cfg, metrics)

    if len(candidates) >= 2:
        reasons.append(
            Reason.of("MULTIPLE_DOCUMENTS", f"contour_candidates={len(candidates)}")
        )

    # Phán quyết hình học nói về **biên tờ giấy detector tìm được**, không nói về lề
    # cắt. Đã thử đo trên tứ giác đã nới và **đo thấy hỏng**: nới làm góc chạm mép ảnh
    # nên 5 ảnh vốn `pass` bị đẩy sang `warn` (CLIPPED_EDGE), và ca hỏng thật
    # `abc1b13…` thoát `NO_CROP_DETECTED` vì góc lệch ra ngoài bị kẹp lại thành 0.
    reasons += _geometry_reasons(quad.corners, work, cfg, metrics)

    # QC-17: chỉ tới đây mới nới, và chỉ để CẮT — mép giấy cong thì dây cung nối hai
    # góc nằm trong tờ giấy và cắt lẹm vào nội dung.
    corners = quad.corners
    if cfg.contain_paper_contour and quad.contour is not None:
        corners = geo.containing_quad(
            corners, quad.contour, work.shape, cfg.max_edge_grow_ratio
        )
    corners = geo.expand(corners, cfg.edge_expand_px, work.shape)

    reasons = _content_reasons(orig, corners * ratio, cfg, metrics, reasons)

    warped = perspective.four_point_transform(orig, corners * ratio)
    if cfg.auto_rotate_portrait and warped.shape[1] > warped.shape[0]:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    _debug(debug, "warped", warped)

    reasons += _quality_reasons(warped, cfg, metrics)
    reasons = _apply_pre_cropped(reasons, cfg, metrics)

    return ScanResult.of(
        _encode_png(warped),
        reasons,
        metrics,
        corners=(corners * ratio).tolist(),
        audience=cfg.hint_audience,
    )


def scan(data: bytes) -> bytes:
    """API cũ (`bytes -> bytes`), giữ nguyên chữ ký cho người dùng hiện tại.

    Không mang phán quyết — dùng `scan_qc()` nếu cần biết ảnh có đáng tin không.
    """
    result = scan_qc(data)
    if result.image is None:
        fail = next((r for r in result.reasons if r.severity == "fail"), None)
        raise ScanError(fail.code if fail else "QUAD_NOT_FOUND")
    return result.image


# --------------------------------------------------------------------------- #
# Các bước


def _decode(data):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ScanError("DECODE_FAILED", "cv2.imdecode không đọc được dữ liệu vào")
    return img


def _segment(image, cfg):
    """rembg → mask xám cùng cỡ ảnh vào. Gọi **đúng một lần** cho mọi mặt tiền.

    **Lỗi model KHÔNG phải lỗi ảnh.** Trước đây mọi exception ở đây đều thành
    `DECODE_FAILED` — "không giải mã được dữ liệu thành ảnh". Đo trên máy H100 mới lộ:
    GPU hết bộ nhớ (`CUBLAS_STATUS_ALLOC_FAILED`) cũng ra đúng thông báo đó, tức là
    **nói dối** — ảnh hoàn toàn bình thường. Và qua HTTP nó thành `400`, nghĩa là bảo
    phía gọi "file của bạn hỏng, đừng thử lại", trong khi việc đúng phải làm là **thử
    lại**. Ảnh tốt bị loại vĩnh viễn vì một sự cố nhất thời của máy chủ.

    Ảnh đã qua `_decode()` trước khi tới đây, nên tới bước này thì "không giải mã
    được" vốn đã không còn là cách giải thích hợp lý cho bất cứ lỗi nào.
    """
    try:
        return segment_mask(
            image,
            cfg.rembg_model,
            cfg.onnx_providers,
            at_model_size=cfg.segment_at_model_size,
        )
    except Exception as exc:
        raise ScanError("INFERENCE_FAILED", str(exc)) from exc


def _resize_to(img, shape):
    """Đưa `img` về đúng (cao, rộng) của `shape`. Không làm gì nếu đã đúng."""
    if img.shape[:2] == tuple(shape[:2]):
        return img
    return cv2.resize(img, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)


def _to_work_size(img, cfg: Config):
    """Hạ mẫu để dò biên. KHÔNG phóng to ảnh nhỏ hơn — phóng to là bịa thông tin."""
    if img.shape[0] <= cfg.work_height:
        return img.copy()
    return imutils.resize(img, height=cfg.work_height)


def _alpha_mask(alpha, cfg: Config):
    """Mask xám → mask nhị phân, khử đốm bằng medianBlur suy theo kích thước.

    medianBlur (không phải Gaussian) vì median giữ **cạnh sắc** trong khi xoá
    đốm — Gaussian làm nhoè góc và hỏng approxPolyDP.
    """
    if alpha is None or alpha.ndim != 2:
        return None
    _, mask = cv2.threshold(alpha, 0, 255, cv2.THRESH_BINARY)
    ksize = int(alpha.shape[0] * cfg.blur_ksize_ratio) | 1  # ép về số lẻ
    return cv2.medianBlur(mask, max(3, ksize))


def _pick(detector, candidates, work, mask, cfg):
    from .detect import best_candidate

    reference = mask if mask is not None else work
    return best_candidate(candidates, reference, cfg)


def _passes_filters(corners, work, cfg: Config):
    area_ratio = geo.quad_area(corners) / float(work.shape[0] * work.shape[1])
    return (
        geo.is_convex(corners)
        and area_ratio >= cfg.min_quad_area_ratio
        and geo.skew_ratio(corners) <= cfg.max_skew_ratio
    )


def _geometry_reasons(corners, work, cfg: Config, metrics: Metrics):
    img_area = float(work.shape[0] * work.shape[1])
    metrics.quad_area_ratio = geo.quad_area(corners) / img_area
    metrics.skew_ratio = geo.skew_ratio(corners)
    metrics.is_convex = geo.is_convex(corners)
    metrics.touches_border = geo.touches_border(corners, work.shape, cfg.border_margin_px)
    metrics.corners_outside_px = geo.corners_outside(corners, work.shape)

    reasons = []
    if not metrics.is_convex:
        reasons.append(Reason.of("NOT_CONVEX"))
    if metrics.quad_area_ratio < cfg.min_quad_area_ratio:
        reasons.append(
            Reason.of("TOO_SMALL", f"quad_area_ratio={metrics.quad_area_ratio:.3f}")
        )
    if metrics.skew_ratio > cfg.max_skew_ratio:
        reasons.append(
            Reason.of("EXTREME_SKEW", f"skew_ratio={metrics.skew_ratio:.2f}")
        )
    # QC-11: tứ giác gần trọn khung *và* chạm gần hết mép = detector trả lại chính
    # khung hình, không phải tờ giấy. Ca này trước đây chỉ ra `warn` (CLIPPED_EDGE) nên
    # ảnh chưa cắt vẫn trôi được xuống người dùng. Phát riêng một mã `fail` và **thay**
    # cho CLIPPED_EDGE — chạm mép ở đây là hệ quả, nói thêm chỉ làm loãng lý do thật.
    #
    # QC-16: nhưng chỉ khi detector THẬT SỰ thua. Tờ giấy chiếm gần hết khung mà biên
    # vẫn dựng được đàng hoàng (4 đỉnh thật, `conf 0.9`, không góc nào lọt ra ngoài
    # ảnh) là **người chụp lấy khung sát**, không phải lỗi — nội dung còn nguyên, chỉ
    # là chẳng có gì để cắt.
    struggled = (
        metrics.detector_confidence is not None
        and metrics.detector_confidence < cfg.no_crop_min_confidence
    ) or metrics.corners_outside_px > cfg.border_margin_px
    if (
        metrics.quad_area_ratio > cfg.no_crop_area_ratio
        and metrics.touches_border >= cfg.no_crop_touched_edges
        and struggled
    ):
        reasons.append(
            Reason.of(
                "NO_CROP_DETECTED",
                f"quad_area_ratio={metrics.quad_area_ratio:.3f}, "
                f"touches_border={metrics.touches_border}, "
                f"confidence={metrics.detector_confidence}, "
                f"corners_outside_px={metrics.corners_outside_px:.0f}",
            )
        )
    elif metrics.touches_border >= 1:
        reasons.append(
            Reason.of("CLIPPED_EDGE", f"touches_border={metrics.touches_border}")
        )
    return reasons


def _content_reasons(orig, corners_full, cfg: Config, metrics: Metrics, reasons):
    """QC-12: phân biệt *mất viền trắng* (chấp nhận được) với *mất chữ* (không).

    [EX-1] chốt tiêu chí "đạt" nằm ở **nội dung**, không ở hình học. `CLIPPED_EDGE`
    chỉ đếm góc chạm mép nên vừa báo thừa (mất viền cũng `warn`) vừa báo thiếu (mất
    hẳn một dòng cũng chỉ `warn`). Có mực sát mép thì thay nó bằng một mã `fail` —
    giữ cả hai chỉ làm loãng, vì lúc đó "chạm mép" chỉ là cách nội dung bị mất.

    Biên độ "chạm mép" ở đây tính bằng pixel **ảnh gốc** và cố tình chặt hơn của
    `CLIPPED_EDGE` (vốn nới theo `ratio`). Nới ra thì tứ giác chỉ *gần* mép cũng bị
    soi, mà dải sát mép giấy luôn có **bóng mép** — ngưỡng thích nghi đọc bóng đó
    thành mực. Đo thật trên doc-5 (tứ giác cách mép 4px): margin 2 → 0.000, margin 5
    → 0.187 tuy chẳng mất chữ nào. Mã mức `fail` thì phải đòi bằng chứng chặt: tứ
    giác thật sự chạm mép, chứ không phải gần mép.
    """
    metrics.border_ink_ratio = geo.ink_at_image_border(
        orig,
        corners_full,
        band_ratio=cfg.content_clip_band_ratio,
        margin_px=cfg.border_margin_px,
    )
    if metrics.border_ink_ratio <= cfg.max_border_ink_ratio:
        return reasons

    # QC-16: không cắt gì thì "chữ bị đường cắt chém" là câu hỏi sai — cái đo được
    # là mép **tấm ảnh**, không phải mép crop. Tệ hơn, đúng ca đó tứ giác hay trùm cả
    # nền (rembg không tách được), và ngưỡng thích nghi đọc mảng nền tối thành mực:
    # ảnh `04.57.20` cho ink 0.213 tuy không mất chữ nào, chỉ vì dải trái là mặt bàn.
    # `NO_CROP_DETECTED` đã nói đúng và đủ chuyện gì xảy ra; thêm mã thứ hai chỉ là
    # khẳng định một điều mình không đo được.
    if (metrics.quad_area_ratio or 0) > cfg.no_crop_area_ratio:
        return reasons

    kept = [r for r in reasons if r.code != "CLIPPED_EDGE"]
    kept.append(
        Reason.of("CONTENT_CLIPPED", f"border_ink_ratio={metrics.border_ink_ratio:.3f}")
    )
    return kept


def _quality_reasons(warped, cfg: Config, metrics: Metrics):
    metrics.est_dpi = geo.estimate_dpi(warped.shape)
    metrics.blur_score = geo.blur_score(warped)
    metrics.glare_ratio = geo.glare_ratio(warped)
    metrics.median_brightness = geo.median_brightness(warped)

    reasons = []
    long_side = max(warped.shape[:2])
    if long_side < cfg.min_long_side_px:
        reasons.append(Reason.of("LOW_RESOLUTION", f"long_side={long_side}px"))
    if metrics.blur_score < cfg.min_blur_score:
        reasons.append(Reason.of("BLURRY", f"blur_score={metrics.blur_score:.1f}"))
    if metrics.glare_ratio > cfg.glare_ratio:
        reasons.append(Reason.of("GLARE", f"glare_ratio={metrics.glare_ratio:.3f}"))
    if metrics.median_brightness < cfg.min_median_brightness:
        reasons.append(
            Reason.of("TOO_DARK", f"median_brightness={metrics.median_brightness:.0f}")
        )
    return reasons


#: Các mã chỉ có nghĩa khi ảnh vào là ảnh CHỤP. Với ảnh đã cắt sẵn thì "giấy chạm
#: mép khung" là điều đương nhiên, không phải lỗi. QC-14.
BORDER_REASONS = frozenset(
    {"CLIPPED_EDGE", "CONTENT_CLIPPED", "NO_CROP_DETECTED", "SUBJECT_FILLS_FRAME"}
)


def _apply_pre_cropped(reasons, cfg: Config, metrics: Metrics):
    """QC-14: ảnh khai báo là đã cắt sẵn thì bỏ các mã về biên.

    **Không phát một mã cảnh báo thay thế.** Đã cân nhắc một mã
    `PRE_CROPPED_UNVERIFIED` mức `warn` cho đúng nguyên tắc "không im lặng", nhưng
    nó nói lại đúng thứ phía gọi vừa khai báo, đổi lại là đẩy *toàn bộ* kho ảnh đã
    cắt vào hàng chờ người soi ([EX-8]) — tốn công thật để đổi lấy thông tin bằng
    không. Sự thật "đã bỏ qua kiểm tra biên" đi vào `metrics.pre_cropped`, nơi dành
    cho dữ kiện không đòi hành động.

    Rủi ro còn lại là gắn cờ nhầm cho một ảnh chụp: khi đó qc_scanner mất khả năng
    bắt crop hụt. Đó là đánh đổi thuộc về phía gọi, và vì thế nó phải **khai báo**
    chứ không được đoán.
    """
    metrics.pre_cropped = bool(cfg.pre_cropped)
    if not cfg.pre_cropped:
        return reasons
    return [r for r in reasons if r.code not in BORDER_REASONS]


def _cross_check(quad, work, mask, cfg: Config, metrics: Metrics):
    """S-6: bất đồng giữa hai detector là tín hiệu QC miễn phí — không cần nhãn."""
    other_name = "edge-hough" if quad.detector != "edge-hough" else "rembg-contour"
    other = get_detector(other_name).find_quad(work, mask, cfg)
    if other is None:
        return []
    metrics.detector_iou = geo.iou(quad.corners, other.corners, work.shape)
    if metrics.detector_iou < cfg.min_detector_iou:
        return [
            Reason.of(
                "DETECTOR_DISAGREEMENT",
                f"IoU({quad.detector},{other_name})={metrics.detector_iou:.2f}",
            )
        ]
    return []


def _encode_png(image):
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ScanError("DECODE_FAILED", "cv2.imencode PNG thất bại")
    return buf.tobytes()


def _debug(debug_dir, name, image):
    """QC-10: xuất ảnh trung gian để soi ca sai."""
    if not debug_dir or image is None:
        return
    import pathlib

    path = pathlib.Path(debug_dir)
    path.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path / f"{name}.png"), image)
