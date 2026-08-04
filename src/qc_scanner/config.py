"""Ngưỡng QC và tham số thuật toán — một chỗ duy nhất, đọc được từ env.

⚠️ Mọi ngưỡng ở đây là **ước đoán ban đầu**, chưa chốt trên tập vàng của khách.
Đổi ngưỡng phải kèm số đo trước/sau cả false-pass **lẫn** false-fail: siết một
chiều luôn nới chiều kia.

Override bằng biến môi trường `QC_SCANNER_<TÊN_TRƯỜNG>`, ví dụ::

    QC_SCANNER_MIN_QUAD_AREA_RATIO=0.10 qc-scanner in.jpg out.png
"""

import os
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Config:
    # --- Kích thước làm việc (QUAL-2: suy theo ảnh, không hardcode) ---
    work_height: int = 500
    """Chiều cao ảnh dùng để dò biên. KHÔNG bao giờ phóng to ảnh nhỏ hơn mức này."""

    blur_ksize_ratio: float = 0.03
    """Kernel medianBlur = tỉ lệ này × chiều cao làm việc (làm tròn về số lẻ)."""

    approx_poly_epsilon_ratio: float = 0.02
    """ε của approxPolyDP tính theo chu vi contour (Ramer–Douglas–Peucker)."""

    # --- Tách chủ thể ---
    min_alpha_coverage: float = 0.05
    """Dưới mức này coi như rembg không tìm thấy chủ thể."""

    max_alpha_coverage: float = 0.95
    """Trên mức này chủ thể chiếm gần hết khung — có thể đã mất mép."""

    # --- Hình học tứ giác ---
    min_quad_area_ratio: float = 0.20
    """Tứ giác nhỏ hơn tỉ lệ này so với ảnh là quá nhỏ để dùng."""

    candidate_area_ratio: float = 0.05
    """Contour phải chiếm ít nhất tỉ lệ này mới được tính là một ứng viên tài liệu."""

    max_skew_ratio: float = 1.8
    """Tỉ lệ cạnh đối dài/ngắn tối đa trước khi coi là nghiêng cực đoan."""

    border_margin_px: int = 2
    """Góc nằm trong khoảng này tính từ mép ảnh coi như chạm biên."""

    # --- Chất lượng ảnh ---
    min_long_side_px: int = 600
    """Cạnh dài tối thiểu của ảnh đã nắn.

    Chốt chặn độ phân giải KHÔNG dùng `est_dpi`: DPI chỉ tính được khi biết khổ
    giấy thật, mà điều đó chưa xác nhận được với khách. Đo trên 17 ảnh (8 mẫu +
    9 ảnh thật), ngưỡng DPI-theo-A4 150 loại nhầm 15/17 — toàn giấy tờ khổ nhỏ
    hoàn toàn đọc được. Số pixel cạnh dài **không phụ thuộc khổ giấy**, nên
    dùng làm chốt chặn; `est_dpi` vẫn được báo cáo nhưng không dùng để phán quyết.
    """

    min_blur_score: float = 25.0
    """Variance of Laplacian tối thiểu; dưới mức này coi là mờ.

    Đo trên ảnh mẫu: bản sắc nét 42.7–358, bản làm mờ nhân tạo (GaussianBlur
    k≥9) 2.7–9.4. Ngưỡng 25 nằm gọn giữa hai cụm.
    """

    glare_ratio: float = 0.02
    """Tỉ lệ pixel bão hòa sáng (>250) tối đa trước khi báo lóa."""

    min_median_brightness: float = 60.0
    """Độ sáng trung vị tối thiểu của tài liệu đã nắn."""

    # --- Đường lui / tự sửa ---
    enable_edge_fallback: bool = True
    """Bật đường lui dò cạnh Canny+Hough khi rembg thua."""

    edge_expand_px: int = 0
    """Nới biên tứ giác thêm bấy nhiêu pixel (QC-8) — 0 = tắt."""

    auto_rotate_portrait: bool = False
    """Tự xoay ảnh đã nắn về chiều đứng."""

    # --- Detector ---
    rembg_model: str = "u2net"
    """Model nền của rembg. `isnet-general-use` / `birefnet-general` thường tốt hơn,
    nhưng KHÔNG đổi mặc định trước khi đo trên tập vàng."""

    detector: str = "rembg-contour"
    """Detector đường chính: `rembg-contour` hoặc `edge-hough`."""

    cross_check_detectors: bool = False
    """Chạy thêm detector thứ hai; hai bên lệch nhau → DETECTOR_DISAGREEMENT (S-6)."""

    min_detector_iou: float = 0.85
    """IoU tối thiểu giữa hai detector trước khi coi là bất đồng."""

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        values = {}
        for f in fields(cls):
            raw = os.environ.get(f"QC_SCANNER_{f.name.upper()}")
            if raw is None:
                continue
            if f.type is bool or f.type == "bool":
                values[f.name] = raw.strip().lower() in {"1", "true", "yes", "on"}
            elif f.type is int or f.type == "int":
                values[f.name] = int(raw)
            elif f.type is float or f.type == "float":
                values[f.name] = float(raw)
            else:
                values[f.name] = raw
        values.update(overrides)
        return cls(**values)


DEFAULT = Config()
