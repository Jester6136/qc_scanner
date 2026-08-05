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

    segment_at_model_size: bool = False
    """Hạ ảnh về đúng kích thước model **trước khi** tách nền. Nhanh hơn, nhưng không
    miễn phí — đọc hết đoạn này rồi hãy bật.

    **Được gì**: `predict()` của rembg phóng mask 320×320 ngược lên đúng kích thước
    ảnh gốc bằng LANCZOS, rồi lõi QC hạ ngay về `work_height` — phép phóng đó là công
    toi và tỉ lệ với số pixel ảnh gốc. Bật cờ này thì cả hai phép resize trong
    `predict()` thành no-op. Đo ghép cặp trên ảnh 3024×4032: **413ms → 370ms
    (tiết kiệm 43ms/ảnh)** trên CPU máy phát triển; trên máy có GPU phần trăm còn cao
    hơn nhiều vì chặng suy luận đo được 187ms mà `ort.run` thật chỉ 6.5ms.

    **Đầu vào model KHÔNG đổi một bit** — ta tự làm đúng phép resize mà `normalize()`
    sẽ làm, nên tensor và mask 320×320 y hệt. Thứ đổi là chặng resample cuối:
    320→work thay vì 320→gốc→work.

    **Mất gì**: chặng resample khác nhau làm metric trôi nhẹ — đo trên 37 ảnh thật,
    `quad_area_ratio` lệch trung vị **0.14%** (tối đa 0.40%). Đủ nhỏ với mọi ảnh trừ
    một: `04.56.41` có `quad_area_ratio` **0.9002** trong khi `no_crop_area_ratio` là
    **0.90** — biên 0.02%. Trôi xuống 0.8980 là nó rơi khỏi nhánh miễn trừ và ăn
    `CONTENT_CLIPPED` → `fail`, dù ảnh đó đã soi mắt thường và crop ra nguyên tờ
    (xem QC-16). Tức **một false fail**.

    Nên mặc định **tắt**: 43ms không đáng đổi lấy một ảnh tốt bị loại. Bật khi đã chạy
    `qc-scanner-batch` trên ảnh thật của mình và đối chiếu verdict trước/sau.

    Ghi chú riêng: ca `04.56.41` mong manh vì **ngưỡng**, không phải vì cờ này — nó đã
    lật hai lần trong cùng một đợt làm việc. Xem QUAL-4.
    """

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

    content_clip_band_ratio: float = 0.01
    """Bề rộng dải sát mép ảnh đem soi mực, theo cạnh ngắn của ảnh gốc (QC-12)."""

    max_border_ink_ratio: float = 0.08
    """Trên mức này coi như đã cắt vào **chữ**, không phải chỉ mất viền trắng (QC-12).

    Đo trên 17 ảnh thật/mẫu + 4 ảnh cắt cố ý 12% mỗi chiều:

    - không mất gì (tứ giác nằm trong ảnh): **0.000** — 12 ảnh;
    - chạm mép nhưng chỗ chạm là giấy trắng: **0.000–0.041** (doc-1, doc-5, và ca
      mẫu `clipped_margin_only`);
    - cắt vào chữ thật: **0.150–0.507** (4 ảnh cắt cố ý + 2 ảnh thật).

    Ngưỡng đặt ở 0.08, giữa 0.041 và 0.150. Không đặt sát 0 vì nhóm "mất viền" không
    về đúng 0 được: vệt tối ở mép giấy luôn còn sót lại chút ít sau khi co mask.
    """

    no_crop_area_ratio: float = 0.90
    """Tứ giác lớn hơn tỉ lệ này **và** chạm ≥ `no_crop_touched_edges` mép → không cắt
    được gì (QC-11).

    Đo trên 17 ảnh thật: dấu hiệu kép này bắt đúng 2 ảnh, cả hai đều thật sự không cắt
    được, 0 báo động giả. Riêng `quad_area_ratio > 0.90` thì không đủ — ảnh chụp sát tài
    liệu vẫn cho tỉ lệ cao mà biên vẫn đúng; điều kiện chạm mép mới là thứ phân biệt
    "tài liệu chiếm hết khung" với "detector trả lại chính khung hình".
    """

    contain_paper_contour: bool = True
    """Nới 4 cạnh tứ giác ra cho tới khi bao trọn mép giấy, trước khi nắn (QC-17).

    Tắt đi thì quay lại hành vi cũ: cắt theo tứ giác nội tiếp, và **cắt lẹm vào chỗ
    mép giấy cong**.
    """

    max_edge_grow_ratio: float = 0.05
    """Mỗi cạnh được đẩy ra tối đa bấy nhiêu lần cạnh ngắn của ảnh làm việc (QC-17).

    Chặn ca bệnh lý: mask lỗi có một gai nhọn thì cạnh không bị đẩy ra vô hạn. Đo
    trên 45 ảnh, mức nới thật cần rất nhỏ — diện tích chỉ tăng trung vị 4.6%.
    """

    no_crop_min_confidence: float = 0.9
    """Detector tự tin từ mức này trở lên thì "giấy đầy khung" KHÔNG bị coi là lỗi.

    Phân biệt hai chuyện trước đây bị gộp làm một:

    * **Detector thua** — không dựng nổi 4 đỉnh nên phải ép `minAreaRect` (`conf 0.6`),
      hoặc góc rơi ra ngoài ảnh. Ảnh ra là ảnh vào, và chẳng ai biết tờ giấy ở đâu.
      Đây mới là `NO_CROP_DETECTED`.
    * **Người chụp lấy khung sát** — detector cho tứ giác 4 đỉnh đàng hoàng (`conf 0.9`)
      nằm trong ảnh, chỉ là tờ giấy vốn chiếm gần hết khung nên chẳng có gì để cắt.
      Nội dung còn nguyên → không phải lỗi.

    Đo trên 45 ảnh, nhóm `area > 0.90 & tb >= 3`: `conf 0.6` gồm đúng những ca hỏng thật
    (bắt mặt bàn, ảnh chưa cắt, góc lệch ra ngoài 18–59px); `conf 0.9` gồm những ca đã
    soi mắt thường và **crop ra nguyên tờ, không mất gì** (04.56.41 · 04.57.20 · 04.58.02).
    """

    no_crop_touched_edges: int = 3
    """Số mép tứ giác phải chạm để tính là không cắt được gì.

    Ban đầu đặt 4. Đo lại trên 45 ảnh: hạ xuống 3 bắt thêm **3 ảnh**, cả ba đều cắt đi
    dưới 10% khung (0.900 · 0.947 · 0.964) — tức ảnh ra gần y ảnh vào, đúng thứ mã này
    sinh ra để bắt. Và **không ảnh nào** có diện tích > 0.90 mà chạm dưới 3 mép, nên
    hạ ngưỡng không mở cửa cho ca mới nào. Vẫn giữ điều kiện chạm mép (thay vì bỏ hẳn)
    để ảnh chụp sát tài liệu mà nằm trọn trong khung không bị vạ lây.
    """

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

    # --- Bối cảnh đầu vào (QC-14) ---
    pre_cropped: bool = False
    """Ảnh vào **đã được cắt sát từ trước** (bản scan, hoặc đã qua công cụ crop khác).

    Khi bật, các mã về biên (`CLIPPED_EDGE`, `CONTENT_CLIPPED`, `NO_CROP_DETECTED`,
    `SUBJECT_FILLS_FRAME`) bị bỏ qua: với ảnh đã cắt thì "giấy chạm mép khung" là
    chuyện đương nhiên, không phải lỗi.

    **Phải khai báo, không tự đoán được.** Đo trên 37 ảnh (8 đã cắt + 29 ảnh chụp):
    `alpha_coverage` chạy 0.270–0.998 ở nhóm đã cắt và 0.260–0.996 ở nhóm ảnh chụp —
    hai dải trùng gần như hoàn toàn, `quad_area_ratio` cũng vậy. Không có ngưỡng nào
    tách được chúng, nên đoán mò chỉ đổi loại lỗi này lấy loại lỗi khác.
    """

    # --- Đầu vào PDF (N-08) ---
    pdf_pre_cropped: bool = True
    """Coi mỗi trang PDF là ảnh **đã cắt sẵn** → bỏ qua các kiểm tra về biên (QC-14).

    Với PDF thì `pre_cropped` gần như luôn đúng, vì trang PDF **chính là** tờ giấy:
    máy scan (hay app scan trên điện thoại) cắt xong mới đóng thành PDF. Không có nền
    quanh mép để mà dò.

    Đo trên một trang scan đặt kín khổ:

    | | `pdf_pre_cropped` tắt | bật |
    |---|---|---|
    | phán quyết | `fail` — `NO_CROP_DETECTED` | `pass` |
    | `quad_area_ratio` | 0.994 | — |
    | `touches_border` | 4/4 | — |

    Tức là để tắt thì **mọi trang PDF scan đều `fail`**, vì dấu hiệu "tứ giác trùm gần
    kín khung và chạm cả 4 mép" đúng theo nghĩa đen với mọi trang PDF.

    Cái giá của việc bật: PDF chỉ là ảnh chụp bọc lại (trang rộng hơn tờ giấy, có nền
    quanh mép) thì mất `CLIPPED_EDGE` — đo trên cùng bộ: `warn` → `pass`. Chọn bật
    làm mặc định vì hai sai lầm không cùng giá: bên tắt là **false fail** trên ca phổ
    biến (ảnh tốt bị loại hẳn), bên bật là **thiếu một cảnh báo** trên ca hiếm.

    Chưa hỏi được khách PDF của họ thuộc loại nào — xem [EX-17].
    """

    pdf_max_pages: int = 50
    """Trần số trang cho một file. Vượt → `PDF_TOO_MANY_PAGES`, **không xử lý trang nào**.

    Có trần vì một request giữ một suất `MAX_CONCURRENCY` suốt thời gian chạy: ~0.5s
    mỗi trang, nên 50 trang là ~25s. Đặt cao hơn thì phải nâng cả timeout ở tầng proxy.
    """

    pdf_render_dpi: int = 200
    """DPI khi phải render — chỉ dùng cho trang **không** có ảnh nhúng chiếm trọn.

    Tức là PDF sinh từ máy tính (hoá đơn điện tử, chữ vector), nơi không có "DPI thật"
    nào để bám vào. Trang scan đi đường khác, ở đúng DPI của ảnh nhúng — xem `pdf.py`.
    200 DPI cho khổ A4 ra 1654×2339, thừa xa `min_long_side_px`.
    """

    pdf_max_dpi: int = 400
    """Trần DPI khi render theo DPI thật của ảnh nhúng.

    Chặn ca một trang nhỏ chứa ảnh siêu nét: render đúng 1200 DPI thì ra ảnh vài trăm
    triệu điểm, đủ để cạn RAM worker.
    """

    pdf_out_dpi: int = 300
    """DPI giả định khi ghép ảnh đã nắn thành PDF — quyết định **khổ trang** của file ra.

    Là phỏng đoán, và không tránh được: từ một ảnh đã cắt thì không biết tờ giấy thật
    to bao nhiêu, mà khổ giấy chưa chốt được với khách ([EX-4]). 300 DPI là mặc định
    của máy scan văn phòng, nên khổ trang ra thường đúng với A4/A5.

    **Không ảnh hưởng chất lượng**: số điểm ảnh trong file không đổi dù đặt bao nhiêu,
    và đó mới là thứ OCR dùng. Nó chỉ đổi con số "trang này to bằng chừng nào giấy".
    """

    pdf_out_jpeg_quality: int = 0
    """0 = ghép PDF **không mất dữ liệu** (mặc định). 1–100 = nén JPEG ở mức đó.

    Mặc định lossless vì cùng lý do đầu ra là PNG chứ không phải JPEG: file đi tiếp vào
    OCR/VLM và nhiễu nén quanh nét chữ nhỏ làm giảm độ chính xác bóc dữ liệu.

    Và ở đây gần như không có gì để đánh đổi — đo trên một trang 1053×1852: PNG gốc
    1276 KB, **PDF lossless 988 KB** (nhỏ hơn PNG), JPEG q92 166 KB. Chỉ bật khi dung
    lượng thật sự thành vấn đề, ví dụ trả PDF hàng chục trang qua đường mạng chậm.
    """

    pdf_page_image_coverage: float = 0.9
    """Ảnh nhúng phải phủ ít nhất bấy nhiêu diện tích trang mới được coi là "trang scan".

    Dưới mức này thì nó là hình minh hoạ trong một trang có bố cục, không phải bản
    scan — render cả trang mới đúng.
    """

    # --- Bối cảnh người dùng (QC-13) ---
    hint_audience: str = "capturer"
    """Ai sẽ đọc `hint`: `capturer` (chụp lại được) hay `operator` (soi trong hàng chờ).

    [EX-3] chốt có **cả hai** luồng: realtime cho ảnh chụp mới, batch cho kho ảnh cũ.
    Với ảnh kho thì "chụp lại trên nền tối" là lời khuyên vô dụng — không ai chụp lại
    được nữa. Mặc định `capturer` vì luồng realtime là luồng có người đang đứng chờ;
    `qc-scanner-batch` tự đổi sang `operator`.
    """

    # --- Detector ---
    rembg_model: str = "u2net"
    """Model nền của rembg. `isnet-general-use` / `birefnet-general` thường tốt hơn,
    nhưng KHÔNG đổi mặc định trước khi đo trên tập vàng."""

    onnx_providers: str = ""
    """Execution provider của onnxruntime, ngăn cách bằng dấu phẩy. Rỗng = để tự chọn.

    Máy có GPU NVIDIA thì cài `onnxruntime-gpu` và đặt::

        QC_SCANNER_ONNX_PROVIDERS=CUDAExecutionProvider,CPUExecutionProvider

    Luôn để `CPUExecutionProvider` ở cuối làm đường lui. Nhưng **đường lui đó chính là
    cái bẫy**: thiếu thư viện CUDA thì onnxruntime tụt về CPU trong im lặng — không lỗi,
    không cảnh báo, chỉ chậm gấp mấy chục lần. Vì thế provider thật sự đang chạy được
    báo cáo ở `/healthz` và in ra lúc khởi động; đừng tin là GPU đang bật cho tới khi
    đọc thấy `CUDAExecutionProvider` ở đó.

    Để rỗng thì rembg tự dò: có `onnxruntime-gpu` + GPU thì nó chọn CUDA. Khai báo
    tường minh vẫn hơn khi muốn chắc chắn — hoặc khi muốn **ép** về CPU trên máy có GPU
    để so tốc độ.
    """

    require_gpu: bool = False
    """Không có GPU thì **chết ngay lúc khởi động** thay vì lặng lẽ chạy CPU.

    Mặc định tắt: chạy chậm còn hơn không chạy. Nhưng với container dựng riêng cho GPU
    thì ngược lại — một service chạy đúng mà chậm gấp 30 lần là kiểu hỏng **tệ hơn**
    một service không lên, vì nó không báo gì cả và có thể sống nhiều tháng như thế.
    `docker-compose.gpu.yml` bật cờ này.

    Đây là bài học từ lần dựng đầu trên máy H100: `/healthz` có nói đúng
    `providers: [CPUExecutionProvider]`, nhưng phải có người nghĩ ra việc đi đọc nó.
    """

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
