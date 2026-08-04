"""Lõi xử lý: `scan_qc()` trả phán quyết kèm ảnh; `scan()` là lớp bọc tương thích.

Nguyên tắc chi phối file này: **không im lặng**. Mọi nhánh không-lý-tưởng
(không tìm được biên, phải dùng đường lui, ảnh mờ) đều phải xuất hiện trong
`reasons`. Trả ảnh gốc mà không báo gì là bug, không phải fallback.
"""

from typing import List, Optional

import cv2
import imutils
import numpy as np
from imutils import perspective

from . import geometry as geo
from .config import DEFAULT, Config
from .detect import get_detector
from .qc import Metrics, Reason, ScanError, ScanResult
from .rembg_session import remove_background

# Giữ lại cho mã cũ import trực tiếp; nguồn sự thật nay là Config.
APPROX_POLY_DP_ACCURACY_RATIO = DEFAULT.approx_poly_epsilon_ratio
IMG_RESIZE_H = float(DEFAULT.work_height)


def scan_qc(data: bytes, config: Optional[Config] = None, debug=None) -> ScanResult:
    """Nắn phẳng tài liệu và **chấm điểm chất lượng** kết quả.

    Ném `ScanError` chỉ với lỗi đầu vào không thể đánh giá được (rỗng, không
    decode nổi). Mọi thất bại khác trả `ScanResult` có `verdict="fail"` kèm mã
    lý do — người gọi biết chuyện gì xảy ra và phải làm gì.
    """
    cfg = config or Config.from_env()
    metrics = Metrics()
    reasons: List[Reason] = []

    if not data:
        raise ScanError("FILE_EMPTY")

    orig = _decode(data)
    rgba = _segment(data, cfg)

    work = _to_work_size(rgba, cfg)
    ratio = rgba.shape[0] / work.shape[0]
    mask = _alpha_mask(work, cfg)

    metrics.alpha_coverage = (
        float(np.count_nonzero(mask) / mask.size) if mask is not None else 0.0
    )
    _debug(debug, "mask", mask)

    detector = get_detector(cfg.detector)
    candidates = detector.all_candidates(work, mask, cfg)
    metrics.contour_candidates = len(candidates)

    quad = _pick(detector, candidates, work, mask, cfg)

    # Đường lui: rembg không tách được chủ thể → thử dò cạnh trước khi bỏ cuộc.
    subject_missing = (
        metrics.alpha_coverage < cfg.min_alpha_coverage
        or metrics.alpha_coverage > cfg.max_alpha_coverage
    )
    if (quad is None or subject_missing) and cfg.enable_edge_fallback:
        recovered = get_detector("edge-hough").find_quad(work, mask, cfg)
        if recovered is not None and _passes_filters(recovered.corners, work, cfg):
            quad = recovered
            metrics.fallback_used = "edge_detect"
            reasons.append(Reason.of("RECOVERED_BY_EDGE_FALLBACK"))

    if metrics.alpha_coverage > cfg.max_alpha_coverage:
        reasons.append(
            Reason.of(
                "SUBJECT_FILLS_FRAME",
                f"alpha_coverage={metrics.alpha_coverage:.3f}",
            )
        )

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
        return ScanResult.of(_encode_png(orig), reasons, metrics)

    metrics.detector = quad.detector
    metrics.detector_confidence = quad.confidence
    reasons += _geometry_reasons(quad.corners, work, cfg, metrics)

    if cfg.cross_check_detectors:
        reasons += _cross_check(quad, work, mask, cfg, metrics)

    if len(candidates) >= 2:
        reasons.append(
            Reason.of("MULTIPLE_DOCUMENTS", f"contour_candidates={len(candidates)}")
        )

    corners = geo.expand(quad.corners, cfg.edge_expand_px, work.shape)
    warped = perspective.four_point_transform(orig, corners * ratio)
    if cfg.auto_rotate_portrait and warped.shape[1] > warped.shape[0]:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    _debug(debug, "warped", warped)

    reasons += _quality_reasons(warped, cfg, metrics)

    return ScanResult.of(_encode_png(warped), reasons, metrics)


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


def _segment(data, cfg):
    """rembg → RGBA. Gọi **đúng một lần** cho mọi mặt tiền."""
    try:
        processed = remove_background(data, cfg.rembg_model)
    except Exception as exc:
        raise ScanError("DECODE_FAILED", str(exc)) from exc
    img = cv2.imdecode(np.frombuffer(processed, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ScanError("DECODE_FAILED", "không decode được ảnh sau bước tách nền")
    return img


def _to_work_size(img, cfg: Config):
    """Hạ mẫu để dò biên. KHÔNG phóng to ảnh nhỏ hơn — phóng to là bịa thông tin."""
    if img.shape[0] <= cfg.work_height:
        return img.copy()
    return imutils.resize(img, height=cfg.work_height)


def _alpha_mask(work, cfg: Config):
    """Kênh alpha → mask nhị phân, khử đốm bằng medianBlur suy theo kích thước.

    medianBlur (không phải Gaussian) vì median giữ **cạnh sắc** trong khi xoá
    đốm — Gaussian làm nhoè góc và hỏng approxPolyDP.
    """
    if work.ndim != 3 or work.shape[2] != 4:
        return None
    _, mask = cv2.threshold(work[:, :, 3], 0, 255, cv2.THRESH_BINARY)
    ksize = int(work.shape[0] * cfg.blur_ksize_ratio) | 1  # ép về số lẻ
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
    if metrics.touches_border >= 1:
        reasons.append(
            Reason.of("CLIPPED_EDGE", f"touches_border={metrics.touches_border}")
        )
    return reasons


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
