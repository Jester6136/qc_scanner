"""Quality and composite scores owned by classify_scanned.

This module deliberately lives next to the QC decision. Callers consume the
scores from the API; they do not reimplement the thresholds.
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

WEIGHTS = {
    "blur": 0.30,
    "brightness": 0.20,
    "resolution": 0.20,
    "glare": 0.15,
    "text_skew": 0.10,
    "geometry": 0.05,
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, float(value))), 2)


def _up(value: Any, floor: float, ceiling: float) -> float | None:
    if value is None:
        return None
    return _clamp((float(value) - floor) / (ceiling - floor) * 100)


def _down(value: Any, best: float, worst: float) -> float | None:
    if value is None:
        return None
    return _clamp((worst - float(value)) / (worst - best) * 100)


def _brightness(value: Any) -> float | None:
    if value is None:
        return None
    # Scan paper is normally bright; do not use a photographic mid-grey target.
    return _clamp(100.0 - abs(float(value) - 245.0) * 2.0)


def _geometry(metrics: dict) -> float | None:
    values = []
    if metrics.get("quad_area_ratio") is not None:
        values.append(_up(metrics["quad_area_ratio"], 0.20, 0.85))
    if metrics.get("is_convex") is not None:
        values.append(100.0 if metrics["is_convex"] else 0.0)
    if metrics.get("touches_border") is not None:
        values.append(_down(metrics["touches_border"], 0.0, 2.0))
    if metrics.get("content_loss_score") is not None:
        values.append(_down(metrics["content_loss_score"], 0.0, 1.0))
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 2) if values else None


def image_quality(image: np.ndarray | None, corners: list[list[float]] | None = None) -> dict:
    """Score the source/processed pixels while ignoring blank paper as content."""
    if image is None:
        return {"score": None, "error": "image_missing"}
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        # Measure pixel quality inside the detected document, not on the table/background.
        if corners and len(corners) >= 4:
            points = np.asarray(corners, dtype=np.float32)
            x, y, width, height = cv2.boundingRect(points)
            x = max(0, x); y = max(0, y)
            right = min(gray.shape[1], x + width); bottom = min(gray.shape[0], y + height)
            if right > x and bottom > y:
                gray = gray[y:bottom, x:right]
        max_side = 1600
        if max(gray.shape[:2]) > max_side:
            scale = max_side / max(gray.shape[:2])
            gray = cv2.resize(gray, (max(1, round(gray.shape[1] * scale)), max(1, round(gray.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        height, width = gray.shape[:2]
        pixels = gray.reshape(-1).astype(np.float32)
        background = float(np.percentile(pixels, 95))
        foreground = pixels[pixels < min(235.0, background - 8.0)]
        if foreground.size == 0:
            foreground = np.array([float(np.percentile(pixels, 5))])
        brightness = _clamp(100.0 - abs(background - 245.0) * 2.0)
        dark_ratio = float(np.mean(pixels < 35.0))
        if dark_ratio > 0.20:
            brightness *= _clamp(1.0 - (dark_ratio - 0.20) * 2.0)
        content_contrast = background - float(np.mean(foreground))
        contrast = _clamp((content_contrast - 12.0) / 75.0 * 100.0)
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        magnitude = cv2.magnitude(sobel_x, sobel_y).reshape(-1)
        content_mask = pixels < min(245.0, background - 5.0)
        edge_mean = float(np.mean(magnitude[content_mask])) if np.any(content_mask) else 0.0
        sharpness = _clamp((edge_mean - 4.0) / 18.0 * 100.0)
        resolution = _clamp(min(width, height) / 700.0 * 100.0)
        score = round(0.15 * resolution + 0.20 * brightness + 0.30 * contrast + 0.35 * sharpness, 2)
        return {
            "score": score,
            "width": width,
            "height": height,
            "brightness": round(background, 2),
            "contrast": round(content_contrast, 2),
            "sharpness": round(edge_mean, 2),
            "resolution_score": round(resolution, 2),
            "content_ratio": round(float(foreground.size / max(1, pixels.size)), 4),
        }
    except Exception as exc:
        return {"score": None, "error": str(exc)}


def composite_score(metrics: dict, reasons: list[dict] | list[str] | None = None) -> dict:
    breakdown = {
        "blur": _up(metrics.get("blur_score"), 25.0, 300.0),
        "brightness": _brightness(metrics.get("median_brightness")),
        "resolution": _up(metrics.get("est_dpi"), 72.0, 300.0),
        "glare": _down(metrics.get("glare_ratio"), 0.0, 0.10),
        "text_skew": _down(abs(metrics["text_skew_deg"]), 0.0, 8.0) if metrics.get("text_skew_deg") is not None else None,
        "geometry": _geometry(metrics),
    }
    available = {key: value for key, value in breakdown.items() if value is not None}
    total_weight = sum(WEIGHTS[key] for key in available)
    score = round(sum(available[key] * WEIGHTS[key] for key in available) / total_weight, 2) if available else None
    penalties = []
    penalty_map = {
        "CONTENT_CLIPPED": 25.0, "CONTENT_OUTSIDE_CROP": 20.0, "BLURRY": 20.0,
        "LOW_RESOLUTION": 20.0, "NO_CROP_DETECTED": 18.0, "FALLBACK_ORIGINAL": 25.0,
        "GLARE": 10.0, "TEXT_NOT_LEVEL": 10.0, "CLIPPED_EDGE": 8.0,
        "DETECTOR_DISAGREEMENT": 5.0,
    }
    for reason in reasons or []:
        code = reason.get("code") if isinstance(reason, dict) else str(reason)
        if code in penalty_map:
            penalties.append({"code": code, "amount": penalty_map[code]})
    if score is not None:
        score = _clamp(score - sum(item["amount"] for item in penalties))
    return {
        "mode": "standard",
        "composite": score,
        "quality": score,
        "breakdown": breakdown,
        "weights": WEIGHTS,
        "penalties": penalties,
        "available_metrics": list(available),
    }


def capture_quality(metrics: dict) -> float | None:
    """Score capture conditions; independent detector success must not hide bad input."""
    available = any(metrics.get(key) is not None for key in (
        "border_mean", "border_std", "alpha_coverage", "content_loss_score",
        "quad_area_ratio", "detector_confidence", "glare_ratio",
    ))
    if not available:
        return None
    # A full-bleed, sufficiently large embedded PDF is normally a scan.
    # Border/alpha/glare statistics are capture heuristics for camera photos;
    # applying them to a scan makes clean white pages score artificially low.
    scan_like = bool(metrics.get("likely_full_bleed_scan")) and (
        float(metrics.get("est_dpi") or 0.0) >= 150.0
        or metrics.get("frame_mode") == "full_frame"
    )
    if scan_like:
        loss = float(metrics.get("content_loss_score") or 0.0)
        confidence = metrics.get("detector_confidence")
        penalty = max(0.0, loss) * 20.0
        if confidence is not None:
            penalty += max(0.0, 0.40 - float(confidence)) / 0.40 * 5.0
        return _clamp(100.0 - penalty)

    penalty = 0.0
    border_mean = metrics.get("border_mean")
    border_std = metrics.get("border_std")
    alpha = metrics.get("alpha_coverage")
    loss = metrics.get("content_loss_score")
    area = metrics.get("quad_area_ratio")
    confidence = metrics.get("detector_confidence")
    glare = metrics.get("glare_ratio")
    if border_mean is not None:
        penalty += max(0.0, 190.0 - float(border_mean)) / 100.0 * 20.0
    if border_std is not None:
        penalty += max(0.0, float(border_std) - 12.0) / 80.0 * 20.0
    if alpha is not None:
        penalty += max(0.0, 0.90 - float(alpha)) / 0.45 * 15.0
    if loss is not None:
        penalty += max(0.0, float(loss)) * 15.0
    if area is not None:
        penalty += max(0.0, 0.85 - float(area)) / 0.40 * 20.0
    if confidence is not None:
        penalty += max(0.0, 0.85 - float(confidence)) / 0.85 * 10.0
    if glare is not None:
        penalty += max(0.0, float(glare)) / 0.08 * 15.0
    if metrics.get("touches_border") is not None and not metrics.get("likely_full_bleed_scan"):
        penalty += max(0.0, float(metrics["touches_border"])) * 6.0
    return _clamp(100.0 - penalty)


def confidence_score(metrics: dict) -> dict:
    value = metrics.get("detector_confidence")
    score = round(float(value) * 100, 2) if value is not None else None
    return {"detector_score": score, "overall_score": score, "fallback_used": metrics.get("fallback_used")}


def page_scores(original: np.ndarray | None, processed: np.ndarray | None, metrics: dict, reasons: list[dict] | None, corners: list[list[float]] | None = None) -> dict:
    original_score = image_quality(original, corners=corners)
    pixel_score = original_score.get("score")
    capture_score = capture_quality(metrics)
    if pixel_score is not None and capture_score is not None:
        original_score["pixel_score"] = pixel_score
        original_score["capture_score"] = capture_score
        original_score["score"] = round(0.45 * pixel_score + 0.55 * capture_score, 2)
    elif capture_score is not None:
        original_score["capture_score"] = capture_score
    return {
        "original": original_score,
        "processed": image_quality(processed),
        "confidence": confidence_score(metrics),
        "composite": composite_score(metrics, reasons),
    }


def aggregate_scores(scores: list[dict]) -> dict:
    def average_section(section: str) -> dict:
        keys = set()
        for item in scores:
            keys.update((item.get(section) or {}).keys())
        result = {}
        for key in keys:
            values = [(item.get(section) or {}).get(key) for item in scores]
            values = [float(value) for value in values if isinstance(value, (int, float))]
            if values:
                result[key] = round(sum(values) / len(values), 2)
        return result

    original = average_section("original")
    processed = average_section("processed")
    confidence = average_section("confidence")
    composite = average_section("composite")
    composite["quality"] = composite.get("composite")
    composite["page_count"] = len(scores)
    first_composite = next((item.get("composite") or {} for item in scores), {})
    for key in ("mode", "weights", "available_metrics"):
        if key in first_composite:
            composite[key] = first_composite[key]
    penalties = []
    for item in scores:
        for penalty in (item.get("composite") or {}).get("penalties", []):
            if penalty not in penalties:
                penalties.append(penalty)
    composite["penalties"] = penalties
    return {
        "original": original,
        "processed": processed,
        "confidence": confidence,
        "composite": composite,
        "page_count": len(scores),
    }
