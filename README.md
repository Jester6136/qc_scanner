# QC Scanner

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.txt)

**Take a photo of a document — or a PDF — and get back a flat, cropped scan.**

QC Scanner finds the sheet of paper in a photo — shot at an angle, on a cluttered desk — detects its
four corners, and applies a perspective transform so the page comes out flat and trimmed. It is a
**pre-processing step** for OCR / document-understanding pipelines: flatter page, sharper glyphs,
better extraction downstream.

<p style="display: flex;align-items: center;justify-content: center;">
  <img src="examples/doc-1.jpg" width="100" />
  <img src="examples/doc-1.out.png" width="100" />
  <img src="examples/doc-2.png" width="100" />
  <img src="examples/doc-2.out.png" width="100" />
  <img src="examples/doc-3.jpg" width="100" />
  <img src="examples/doc-3.out.png" width="100" />
  <img src="examples/doc-4.jpg" width="100" />
  <img src="examples/doc-4.out.png" width="100" />
  <img src="examples/doc-5.jpg" width="100" />
  <img src="examples/doc-5.out.png" width="100" />
  <img src="examples/doc-6.jpg" width="100" />
  <img src="examples/doc-6.out.png" width="100" />
  <img src="examples/doc-7.jpg" width="100" />
  <img src="examples/doc-7.out.png" width="100" />
  <img src="examples/doc-8.jpg" width="100" />
  <img src="examples/doc-8.out.png" width="100" />
</p>

## Cách hoạt động

```
photo ──► DocAligner (hồi quy thẳng 4 góc)  ─────────────────────────►  4 corners
              │                                                             │
              │  trả rỗng (ảnh ĐÃ cắt sẵn)          metric hình học         │
              ▼                                     + chất lượng            │
        rembg (U²-Net) → alpha mask → contour  ──►  reasons[] + verdict      ▼
              │                                                   four-point transform → PNG
              │  rembg cũng thua
              ▼
        edge-Hough fallback
```

Một hàm lõi `scan_qc()`, ba mặt tiền (CLI, HTTP server, Python library) gọi chung nó. Không
database, không hàng đợi. Chi tiết: [docs/algorithm.md](docs/algorithm.md).

Đầu vào nhận ảnh (JPG · PNG · WebP · BMP · TIFF) hoặc **PDF**, nhận ra từ nội dung file chứ
không từ tên file. PDF nhiều trang cho một phán quyết mỗi trang — xem [PDF](#pdf) bên dưới.

Đầu ra mặc định là PNG, hoặc **PDF** khi yêu cầu. Cả hai đều **không nén mất dữ liệu**: ảnh này
đi tiếp vào OCR/VLM, và nhiễu nén JPEG quanh nét chữ nhỏ làm giảm độ chính xác bóc dữ liệu.

## Kết quả trả về

```python
from qc_scanner import scan_qc

result = scan_qc(open("photo.jpg", "rb").read())
result.verdict          # "pass" | "warn" | "fail"
result.codes            # ["CLIPPED_EDGE"]
result.reasons[0].hint  # "Một phần tài liệu nằm ngoài khung hình. Lùi máy ra..."
result.metrics.skew_ratio
result.image            # PNG bytes
```

| Verdict | Nghĩa |
|---|---|
| `pass` | Ảnh ra dùng được, không có ghi chú nào |
| `warn` | Ảnh ra dùng được, có ghi chú kèm theo |
| `fail` | Ảnh vào hợp lệ nhưng đầu ra không đáng tin cho OCR |

Bất biến: `verdict == "pass"` ⟺ `reasons == []`. Mỗi mã lý do kèm `hint` (làm gì tiếp theo) và
`audience` (ai thực hiện: người chụp / vận hành / hệ thống gọi). Hiện có **31 mã**, danh mục đầy
đủ trong [docs/api.md](docs/api.md).

## Cài đặt

Chưa publish lên PyPI — cài từ nguồn:

```bash
pip install -r requirements.txt
pip install .
```

Cần **hai** model, tải một lần:

```bash
qc-scanner-fetch-models --head heatmap    # DocAligner ~83MB → ~/.cache/qc-scanner/docaligner/
```

rembg (~176MB → `~/.u2net/`) tự tải ở lần chạy đầu. Máy không có mạng sẽ dừng ở bước này;
[Dockerfile](Dockerfile) nướng sẵn **cả hai** vào image nên container chạy được offline.

## CLI

```bash
qc-scanner photo.jpg out.png          # exit 0 pass · 1 warn · 2 fail · 3 đầu vào hỏng
cat photo.jpg | qc-scanner > out.png
qc-scanner photo.jpg out.png --report qc.json
qc-scanner hoso.pdf out.png           # PDF vào: trang 1 → out.png, trang 2 → out.p2.png, …
qc-scanner hoso.pdf out.pdf           # PDF ra: mọi trang trong một file
```

Báo cáo QC ra stderr, hoặc ra file với `--report`:

```json
{
  "verdict": "warn",
  "reasons": [{"code": "CLIPPED_EDGE", "severity": "warn",
               "hint": "Một phần tài liệu nằm ngoài khung hình. Lùi máy ra để thấy trọn 4 mép.",
               "audience": "capturer"}],
  "metrics": {"quad_area_ratio": 0.79, "skew_ratio": 1.0, "touches_border": 3, "...": "..."}
}
```

## Chạy lô

```bash
qc-scanner-batch anh-vao/ anh-ra/ --report qc.csv
qc-scanner-batch anh-vao/ anh-ra/ --report qc.csv -j 4
qc-scanner-batch anh-vao/ anh-ra/ --format pdf     # một file vào → một file ra
```

CSV một dòng mỗi **trang**: file, verdict, reasons và toàn bộ metric; một PDF 12 trang cho 12
dòng, phân biệt bằng cột `page`. `--jobs` mặc định 2; thứ tự dòng trong CSV không phụ thuộc số
luồng.

Đo trên 37 ảnh, CPU 10 nhân: 1 luồng 14.2s · **2 luồng 11.8s** · 3 luồng 12.0s · 4 luồng 12.7s.
onnxruntime đã dùng hết số nhân cho một lần suy luận, nên thêm luồng chỉ chồng phần OpenCV lên
phần suy luận.

## HTTP server

```bash
qc-scanner-server -a 127.0.0.1 -p 5000

curl -F "file=@photo.jpg" http://127.0.0.1:5000/ -o out.png -D-
# X-QC-Scanner-Verdict: warn
# X-QC-Scanner-Reasons: CLIPPED_EDGE

curl -F "file=@photo.jpg" "http://127.0.0.1:5000/?format=json"
curl -F "file=@hoso.pdf"  "http://127.0.0.1:5000/?format=pdf" -o daxuly.pdf
```

| Status | Khi nào |
|---|---|
| `200` | verdict `pass` hoặc `warn` |
| `422` | verdict `fail` — ảnh hợp lệ, đầu ra không đáng tin |
| `400` | đầu vào không đánh giá được (thiếu file, ảnh hỏng, tham số sai) |
| `413` | file vượt 32MB |
| `503` | kín tải (`SERVER_BUSY`) hoặc lỗi tài nguyên (hết bộ nhớ GPU) — kèm `Retry-After` |

FastAPI + uvicorn, có sẵn Swagger UI ở `/docs`. `GET /` trả `405`: API không có trang web, và
nhánh `GET /?url=` cũ đã bỏ hẳn vì là lỗ SSRF ([SEC-1](docs/features_issues.md#sec-ssrf)).

CORS bật cho mọi origin, thu hẹp bằng `QC_SCANNER_CORS_ORIGINS`. Hai header phán quyết nằm trong
`Access-Control-Expose-Headers`; thiếu khai báo đó thì `fetch()` vẫn trả `200` nhưng JS đọc
`X-QC-Scanner-Verdict` ra `null`.

Hợp đồng API đầy đủ: **[docs/api.md](docs/api.md)**.

## Docker

```bash
docker compose up -d --build
docker compose logs -f qc-scanner

# từ máy khác trong cùng LAN
curl -F "file=@photo.jpg" "http://<IP-máy-chạy>:5000/?format=json"
```

Model nướng sẵn vào image lúc build nên container chạy được khi máy đích không ra Internet.
Cổng mở trên mọi giao diện mạng; đổi bằng `QC_SCANNER_PORT=8000 docker compose up -d`.

Trên macOS, cổng 5000 do **AirPlay Receiver** chiếm sẵn. Docker vẫn bind được và container vẫn
báo `healthy` (healthcheck chạy bên trong container), nhưng gọi từ ngoài vào nhận `403` kèm
header `Server: AirTunes/...`. Kiểm bằng `curl -sI http://localhost:5000/healthz | grep Server`.

### Bản GPU NVIDIA

Bản CPU và bản GPU là **cùng một service** `qc-scanner`; file đè chỉ thay Dockerfile và biến môi
trường, nên không chạy được cả hai cùng lúc và `docker exec qc-scanner …` dùng chung.

Kiểm host trước khi build:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Lệnh này in bảng GPU nếu **NVIDIA Container Toolkit** đã cài. Báo
`could not select device driver` là chưa có.

```bash
docker compose down --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
docker compose ps
```

Dòng log đầu tiên báo provider đang chạy:

```
qc-scanner 0.2.0 · model=u2net · providers=['CUDAExecutionProvider', 'CPUExecutionProvider'] · max_concurrency=16
```

`QC_SCANNER_REQUIRE_GPU=1` (bật sẵn trong `docker-compose.gpu.yml`) làm container thoát với mã 3
khi không có provider tăng tốc, kèm các lệnh chẩn đoán. Không có cờ này thì onnxruntime tụt về
CPU mà không báo lỗi: service vẫn chạy đúng, healthcheck vẫn xanh, chỉ chậm hơn nhiều lần.

`--remove-orphans` xoá container `qc-scanner-gpu` do bản compose cũ (dùng `profiles: gpu`) tạo ra.
Container đó vẫn chạy image cũ nếu không xoá.

## Đo tốc độ

```bash
docker exec qc-scanner qc-scanner-bench                                # tự sinh ảnh
docker exec qc-scanner qc-scanner-bench --url http://127.0.0.1:5000    # đo cả đường HTTP
docker exec qc-scanner qc-scanner-bench --images /data -n 32           # đo trên ảnh thật
```

Bốn mục: **CHẶNG** (thời gian đi đâu, GPU hay CPU) · **SONG SONG** (trần thông lượng một tiến
trình) · **BATCH** (dynamic batching đáng bao nhiêu) · **QUY RA CCU** (ảnh/s quy ra số người
dùng đồng thời). Thêm `--url` thì có mục **HTTP**, in p50/p95 độ trễ và **điểm gãy** — mức song
song cuối cùng còn làm tăng thông lượng, tức con số nên đưa cho bên gọi API.

Mặc định tự sinh ảnh 3024×4032 nên chạy được trong container trắng. Cỡ ảnh giữ như ảnh điện
thoại thật vì chi phí CPU tỉ lệ với số pixel.

## PDF

Cùng một endpoint, cùng một CLI, cùng một batch — không có tham số nào phải bật.

```bash
qc-scanner hoso.pdf out.png              # trang 1 → out.png, trang 2 → out.p2.png, …
qc-scanner hoso.pdf out.png --page 2     # chỉ một trang
curl -F "file=@hoso.pdf" http://127.0.0.1:5000/ | jq '.verdict, .page_count'
```

Ảnh rời và PDF một trang giữ nguyên hợp đồng cũ. PDF nhiều trang trả JSON kể cả khi không có
`?format=json`, vì không có hình dạng "một file PNG" nào để trả về:

```jsonc
{"source": "pdf", "verdict": "fail", "page_count": 3,
 "pages": [{"page": 1, "verdict": "pass", "reasons": [], "metrics": {...}, "image": "..."}, ...]}
```

`verdict` gộp là **trang tệ nhất**: một bộ hồ sơ có 1 trang không đọc được thì chưa dùng được,
dù 11 trang kia hoàn hảo. `qc-scanner-batch` ghi một dòng CSV mỗi trang, có cột `page`.

Trang scan được lấy **thẳng bitmap nhúng** ra, không render, không resample. Chọn sẵn một DPI
để render thì gần như không bao giờ trùng DPI thật của ảnh bên trong, và lệch lên trên là mọi
trang đều `BLURRY` — đo trên một trang 300 DPI, `blur_score` 44.4 (lấy thẳng) · 36.9 (render
đúng DPI) · **3.5** (render gấp đôi), với ngưỡng là 25. Trang không phải bản scan mới render, ở
`QC_SCANNER_PDF_RENDER_DPI`. Cột `metrics.pdf_source` nói mỗi trang đi đường nào.

Trang PDF **chính là** tờ giấy, nên `pre_cropped` bật sẵn cho mọi trang PDF
(`QC_SCANNER_PDF_PRE_CROPPED=0` để tắt). Không có nó thì "tứ giác trùm gần kín khung và chạm cả
4 mép" đúng theo nghĩa đen với mọi trang scan, và mọi trang đều `fail`.

Trần 50 trang một file. Vượt trần thì **không trang nào được xử lý** (`PDF_TOO_MANY_PAGES`) —
trả về 50 trang đầu của một file 200 trang mà không nói gì sẽ khiến phía gọi tưởng đã soi hết.

### PDF ở đầu ra

```bash
qc-scanner hoso.pdf out.pdf                          # CLI: suy từ đuôi file
qc-scanner anh.jpg out.pdf                           # ảnh vào cũng ra PDF được
curl -F "file=@hoso.pdf" "…:5000/?format=pdf" -o daxuly.pdf
qc-scanner-batch vao/ ra/ --format pdf               # một file vào → một file ra
```

Mọi trang nằm gọn trong một file, nên ràng buộc "stdout chỉ chứa được một ảnh" cũng biến mất.
Khi verdict là `fail` thì trả lý do chứ không trả file — một PDF trông bình thường cho tài liệu
không đọc được là cách chắc chắn nhất để nó bị dùng tiếp.

Ảnh vào PDF **không bị nén mất dữ liệu**, và ở đây không có gì để đánh đổi: đo trên một trang
1053×1852, PNG 1276 KB → **PDF lossless 988 KB**, tức nhỏ hơn cả PNG. (JPEG q92 xuống 166 KB,
mở bằng `QC_SCANNER_PDF_OUT_JPEG_QUALITY` khi dung lượng thật sự thành vấn đề.)

Khổ trang suy từ `QC_SCANNER_PDF_OUT_DPI` và là **phỏng đoán** — từ một ảnh đã cắt thì không
biết tờ giấy thật to bao nhiêu ([EX-4](docs/need_exchange.md)). Số điểm ảnh không đổi.

Chi tiết: [N-08](docs/features_issues.md#n-pdf) · [docs/api.md](docs/api.md).

## Cấu hình

Mọi tham số nằm trong [`config.py`](src/qc_scanner/config.py), override bằng
`QC_SCANNER_<TÊN_TRƯỜNG>`:

```bash
QC_SCANNER_MIN_QUAD_AREA_RATIO=0.10 qc-scanner photo.jpg out.png
qc-scanner photo.jpg out.png --detector edge-hough --cross-check
```

Các biến hay dùng nhất:

| Biến | Mặc định | Tác dụng |
|---|---|---|
| `QC_SCANNER_HINT_AUDIENCE` | `capturer` | `hint` viết cho người chụp hay người vận hành |
| `QC_SCANNER_PRE_CROPPED` | `false` | Ảnh đã cắt sát từ trước → bỏ qua các mã về biên |
| `QC_SCANNER_MAX_CONCURRENCY` | `cpu/4`, trong [2, 32] | Số ảnh **xử lý** cùng lúc — van CPU |
| `QC_SCANNER_MAX_IN_FLIGHT` | `max_concurrency × 2` | Số request **đang bay**; vượt → `503`. Chọn theo thời gian chờ, không theo RAM |
| `QC_SCANNER_GPU_CONCURRENCY` | `2` | Số lần suy luận lên GPU cùng lúc |
| `QC_SCANNER_GPU_MEM_LIMIT_MB` | `0` (không giới hạn) | Trần bộ nhớ GPU của onnxruntime |
| `QC_SCANNER_ONNX_PROVIDERS` | tự dò | Ví dụ `CUDAExecutionProvider,CPUExecutionProvider` |
| `QC_SCANNER_REQUIRE_GPU` | `false` | Không có GPU thì thoát thay vì chạy CPU |
| `QC_SCANNER_CORS_ORIGINS` | `*` | Origin được phép gọi từ trình duyệt |
| `QC_SCANNER_SEGMENT_AT_MODEL_SIZE` | `false` | Nhanh hơn ~43ms/ảnh, đổi lại metric trôi ~0.14% |
| `QC_SCANNER_PDF_PRE_CROPPED` | `true` | Coi mỗi trang PDF là ảnh đã cắt sẵn |
| `QC_SCANNER_PDF_MAX_PAGES` | `50` | Trần số trang một file |
| `QC_SCANNER_PDF_RENDER_DPI` | `200` | DPI khi phải render (trang không phải bản scan) |
| `QC_SCANNER_PDF_OUT_DPI` | `300` | Khổ trang của PDF ra — không đổi số điểm ảnh |
| `QC_SCANNER_PDF_OUT_JPEG_QUALITY` | `0` (lossless) | Nén JPEG khi ghép PDF, nếu cần file nhỏ |

Ba van cho ba tài nguyên khác nhau, và không van nào suy ra được từ van kia:

| Van | Chặn cái gì | Vì sao riêng |
|---|---|---|
| `MAX_IN_FLIGHT` | request đang nằm trong RAM | Thân request vào bộ nhớ **trước khi** xin suất xử lý |
| `MAX_CONCURRENCY` | ảnh đang xử lý | Phần CPU chiếm 62% thời gian mỗi ảnh → cần song song theo số nhân |
| `GPU_CONCURRENCY` | lần suy luận trên GPU | VRAM thường dùng chung với service khác → phải giữ thấp |

---

## Hiện trạng

| | |
|---|---|
| Xác thực | API key kiểu Bearer, nhiều key thu hồi riêng từng client; không đặt key thì **server không khởi động** |
| Mã lý do | 31 mã, mỗi mã kèm `hint` + `audience` |
| Đường lui | DocAligner trả rỗng → rembg (`RECOVERED_BY_MASK_FALLBACK`); rembg thua → dò cạnh (`RECOVERED_BY_EDGE_FALLBACK`); hết đường → ảnh gốc kèm `FALLBACK_ORIGINAL` (fail) |
| Bộ đo | 401 test + CI; `python -m qc_scanner.eval` đổ metric ra CSV, so hai lần chạy. Tập vàng công khai: `qc-scanner-smartdoc` (SmartDoc 2015, CC-BY-4.0) |
| Hợp đồng API | [docs/api.md](docs/api.md) + 36 test hợp đồng |
| Ngưỡng | 5 ngưỡng chốt bằng số đo trên 37–45 ảnh (`max_border_ink_ratio`, `no_crop_area_ratio`, `no_crop_min_confidence`, `min_long_side_px`, `min_blur_score`); phần còn lại là ước đoán ban đầu |
| Độ chính xác | Chưa đo được — crop rate / false pass / false fail cần ảnh **có nhãn** ([EX-2](docs/need_exchange.md)) |

Đã chạy trên 8 ảnh mẫu + 30 ảnh thật của khách (CCCD, sổ đỏ, hoá đơn, giấy A4):
13 pass · 13 warn · 12 fail.

### Tốc độ

Đo trên máy server 64 nhân + H100 (GPU dùng chung với một service vLLM giữ 77.8/81.5 GB):

| | CPU | GPU |
|---|---|---|
| Thời gian mỗi ảnh | 574 ms | 477 ms |
| — trong đó suy luận | 284 ms | 180 ms |
| — trong đó phần CPU | 291 ms (51%) | 297 ms (62%) |
| Thông lượng một tiến trình | **8.68 ảnh/s** (16 luồng) | 6.65 ảnh/s (4 luồng) |

GPU cho thông lượng thấp hơn vì VRAM còn trống chỉ đủ 2 luồng suy luận, trong khi bản CPU dùng
được 16 luồng. Nhả thêm VRAM (`gpu_memory_utilization` của vLLM) sẽ đảo lại tương quan này.

**Thông lượng bão hoà ở 16 luồng.** Quét đủ dải trên bản CPU: 1→1.69 · 2→2.75 · 4→4.51 ·
8→6.02 · **16→7.81** · 24→8.06 · 32→7.30 · 48→8.26 · 64→7.96 ảnh/s. Từ 16 trở đi là dao động
quanh ~8, nên `MAX_CONCURRENCY` mặc định (`cpu/4` → 16 trên máy này) nằm đúng chỗ.

**Đường HTTP đạt đúng trần đó**: 8.43 req/s ở 32 request song song, so với 8.26 ảnh/s của lõi.
Nhưng **mức nên khuyên bên gọi là 16** — 7.69 req/s (91% của đỉnh) với p50 1.75s, so với 2.55s
ở mức 32. Đổi 46% độ trễ lấy 9.6% thông lượng là món lỗ cho người đang chờ.

Trước khi sửa, đường HTTP khoá ở **2.86 req/s** vì `docker-compose.yml` ghi cứng
`QC_SCANNER_MAX_CONCURRENCY: "2"` — số đo trên máy dev 10 nhân lọt vào file bàn giao. Mất ~64%
năng lực máy, và mất trong im lặng: service chạy đúng, healthcheck xanh.

**Dynamic batching**: đo trực tiếp trên H100 — batch 1 tốn 6.5 ms/ảnh, batch 32 tốn 2.73 ms/ảnh.
Tiết kiệm 3.8 ms trên tổng 477 ms, tức **0.8%**, trong khi phần CPU 297 ms/ảnh không batch được.
Xem [SPD-5](docs/features_issues.md#spd-batching).

### Việc còn lại

- [OPS-3](docs/features_issues.md#ops-docker-unverified): chưa kiểm gọi từ máy khác qua LAN, chạy
  khi ngắt mạng, và build image trong CI.
- [QUAL-4](docs/features_issues.md#qual-knife-edge): ảnh `04.56.41` nằm cách ngưỡng 0.02% và đã
  lật verdict hai lần; nhánh miễn trừ cần vùng đệm thay vì ngưỡng cứng.
- [EX-2](docs/need_exchange.md): chốt ngưỡng và nâng cấp detector cần tập ảnh có nhãn.
- [EX-15](docs/need_exchange.md#ex-multipage): giấy chứng nhận chụp từng mặt — ai ghép và kiểm đủ mặt.
- [PKG-5](docs/features_issues.md#pkg-license): chưa có file giấy phép — README nói MIT nhưng
  `LICENSE.txt` không tồn tại, và giấy phép của model đi kèm image cũng chưa liệt kê.
- [EX-16](docs/need_exchange.md#ex-throughput): "700 CCU" là bao nhiêu ảnh/giây.
- [EX-17](docs/need_exchange.md#ex-pdfkind): PDF của khách là bản scan hay ảnh chụp bọc lại —
  quyết định mặc định của `pdf_pre_cropped`.

## Tài liệu

Tài liệu dự án viết bằng tiếng Việt, đặt trong [docs/](docs/):

| File | Nội dung |
|---|---|
| [overall_roadmap.md](docs/overall_roadmap.md) | Tổng quan dự án, nguyên tắc thiết kế, roadmap theo giai đoạn |
| [algorithm.md](docs/algorithm.md) | Thuật toán từng bước, hợp đồng đầu ra QC, danh mục mã lý do, khảo sát công nghệ 2026 |
| [features_issues.md](docs/features_issues.md) | Sổ tính năng + issue (BUG-\*/SEC-\*/QC-\*/QUAL-\*/SPD-\*/S-\*/N-\*) kèm bằng chứng `path:line` |
| [test_eval.md](docs/test_eval.md) | Smoke test, bộ regression, cách eval chất lượng & độ chính xác phán quyết |
| [api.md](docs/api.md) | Hợp đồng HTTP bàn giao cho khách: endpoint, status theo verdict, schema JSON, bất biến |
| [need_exchange.md](docs/need_exchange.md) | Câu hỏi cần làm rõ với khách hàng trước khi chốt thiết kế/nghiệm thu |

## Development

```bash
conda create -n qc_scanner python=3.12 && conda activate qc_scanner
pip install -r requirements-dev.txt
pip install -e .
```

```bash
pytest                    # 451 bài, ~95s sau khi model đã cache
ruff check src tests
```

Quy ước khi gửi thay đổi:

- thay đổi thuật toán kèm số đo trước/sau (`python -m qc_scanner.eval ... --baseline`);
- thêm reason code kèm `hint` + `audience` — `test_qc_contract.py` chặn nếu thiếu;
- nâng dependency thì chạy bộ regression và ghi version cũ/mới trong commit.

Chi tiết: [docs/test_eval.md](docs/test_eval.md).

## License

MIT — xem [LICENSE.txt](LICENSE.txt). Lõi bắt nguồn từ
[danielgatis/docscan](https://github.com/danielgatis/docscan) (MIT); bước tách nền dùng
[rembg](https://github.com/danielgatis/rembg).
