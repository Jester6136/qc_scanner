# Sổ tính năng & issue — qc_scanner

> **File này ghi việc CHƯA làm và quyết định CÒN HIỆU LỰC.** Việc đã làm xong không ở đây — nó
> ở lịch sử commit, nơi có kèm diff. Chép lại vào tài liệu chỉ tạo thêm một bản sao để trôi.
>
> Mục đã đóng giữ đúng **một dòng** trong §C vì có chỗ khác trỏ tới. Lý do đằng sau từng ngưỡng
> nằm trong docstring của [`config.py`](../src/qc_scanner/config.py), cạnh chính con số đó.
>
> Ưu tiên: **P0** chặn/đắt nghiêm trọng · **P1** đáng làm sớm · **P2** cải thiện · **P3** nice-to-have.
>
> Bối cảnh: mục tiêu dự án là biến qc_scanner thành **cổng QC** — không crop được thì phải nói rõ
> nguyên nhân + hướng xử lý. Xem [overall_roadmap.md §1](overall_roadmap.md).

---

## Tình trạng

**Đang mở**: [OPS-3](#ops-docker-unverified) (P0) · [PKG-5](#pkg-license) (P1) · [QC-18b](#qc-fold-residual) (P1) ·
[S-3](#s-docaligner) (P1) · [QUAL-3](#qual-sweep) · [QUAL-4](#qual-knife-edge).

**Chặn nhiều nhất**: tập vàng có nhãn của khách ([EX-2](need_exchange.md)). QUAL-3, QUAL-4, S-1,
S-3 đều đứng chờ đúng một thứ này — công cụ đo đã dựng xong và chạy được
(`python -m qc_scanner.eval --labels`).

Mọi ngưỡng trong [`config.py`](../src/qc_scanner/config.py) vẫn là ước đoán, trừ 8 cái đã chốt
bằng số đo: `max_border_ink_ratio` · `no_crop_area_ratio` · `no_crop_min_confidence` ·
`min_long_side_px` · `min_blur_score` · `max_text_skew_deg` · `edge_grow_percentile` ·
`no_crop_corner_outside_px`.

---

## A. Đang mở

### 🔴 OPS-3 · P0 · Docker: còn bốn thứ chưa kiểm {#ops-docker-unverified}

Image **là thứ bàn giao cho khách** ([EX-13](need_exchange.md)), nên mỗi thứ chưa kiểm là một
rủi ro nằm thẳng trên bề mặt bàn giao.

Đã chạy được trên máy server: build, container `Up (healthy)`, API trả lời, bench chạy trong
container.

**Còn lại**:

1. Gọi từ **máy khác qua LAN** — đây là ca dùng thật (service ở máy A, app ở máy B).
2. Chạy khi **ngắt mạng**, để chứng minh model thật sự đã nướng vào image.
3. Thêm bước **build image vào CI**.
4. Bật lại `read_only: true` trong compose (đang tắt, chưa xác nhận ổn định).

Bài học đáng giữ: `healthy` của compose **không** chứng minh khách gọi được — nó chỉ chứng minh
tiến trình bên trong sống. Trên macOS, AirPlay chiếm cổng 5000 nên container `healthy` mà gọi từ
ngoài vào nhận `403` kèm header `Server: AirTunes/…`; server này không có mã 403 nào, chính
header đó là thứ chỉ ra thủ phạm.

---

### 📦 PKG-5 · P1 · Không có file giấy phép nào {#pkg-license}

`LICENSE.txt` **chưa từng tồn tại** trong lịch sử git, nhưng README có badge MIT trỏ thẳng vào
nó (link hỏng) và `setup.py` không khai trường `license` nào.

Đây không phải chuyện hình thức: [EX-13](need_exchange.md) chốt bàn giao cho khách là **Docker
image**, tức có phân phối thật. Và giấy phép của qc_scanner không phải thứ duy nhất phải nói rõ
— **model đi kèm có điều khoản riêng**: U²-Net (mặc định hiện tại) khác BiRefNet, DocAligner là
Apache-2.0, `pypdfium2` là Apache-2.0/BSD. Image nướng sẵn model vào trong, nên điều khoản của
model đi theo image tới tay khách.

**Cần người quyết định, không phải người viết code**: chốt giấy phép cho qc_scanner, thêm
`LICENSE.txt`, khai `license` trong `setup.py`, và liệt kê giấy phép của model + thư viện đi
kèm image.

---

### 🔬 S-3 · P1 · ⭐ Hồi quy 4 góc trực tiếp (DocAligner) thay cho contour {#s-docaligner}

Hạn chế **cố hữu** của contour, không sửa được bằng tinh chỉnh: chỉ suy được góc **nhìn thấy
được** — góc bị tay che hoặc nằm ngoài khung là mất hẳn; và không sinh ra **confidence** nào để
QC dùng.

[DocAligner](https://github.com/DocsaidLab/DocAligner) (Apache-2.0) xuất thẳng toạ độ 4 góc và
chạy ONNXRuntime — qc_scanner đã phụ thuộc `onnxruntime` sẵn nên **không thêm runtime mới**. Nó
thay được **cả** rembg lẫn contour, tức bỏ luôn chặng chiếm ~50% thời gian mỗi ảnh.

**Rủi ro**: mỗi ảnh một tài liệu (đa tài liệu cần bước khác); repo không công bố benchmark nên
bắt buộc tự đo trên ảnh khách. Chỗ cắm đã sẵn (interface `Detector`). **Không đổi mặc định trước
khi có tập vàng.**

---

### 🎯 QUAL-3 · P2 · Chưa quét ngưỡng trên tập vàng {#qual-sweep}

Phần lớn ngưỡng trong `config.py` là ước đoán. Phải chốt bằng số đo trên tập vàng thật —
[test_eval.md §5](test_eval.md), [EX-2](need_exchange.md).

**Mục tiêu đã đổi theo [EX-7](need_exchange.md#ex-7)**: khách muốn **cân bằng** false pass và
false fail, không ưu tiên chặn false pass. Quét ngưỡng phải tối ưu **tổng số lỗi** chứ không
siết một chiều rồi khoe. Giả định cũ (false pass ≤1% / false fail ≤10%) không còn đúng — sửa lại
bảng chỉ tiêu trong test_eval.md §5 khi chốt ngưỡng thật.

---

### 🎯 QUAL-4 · P2 · Ca `04.56.41` nằm cách ngưỡng 0.02% {#qual-knife-edge}

`quad_area_ratio = 0.9002` với `no_crop_area_ratio = 0.90`. Ảnh này đã **lật verdict hai lần**
trong cùng một đợt làm việc, mỗi lần vì một thay đổi hoàn toàn khác nhau và không lần nào liên
quan tới chất lượng ảnh — chỉ vì số thứ tư sau dấu phẩy. Nó đang chặn một tối ưu 43ms/ảnh
([SPD-7](#spd-resample)), và sẽ còn chặn tiếp.

Vấn đề không phải ngưỡng 0.90 sai, mà là nhánh miễn trừ trong `_content_reasons` dùng **một
ngưỡng cứng** cho một đại lượng liên tục.

**Hướng**: vùng đệm (0.88–0.92 thì không phát `CONTENT_CLIPPED` nhưng hạ xuống `warn`), hoặc gộp
thêm `detector_confidence` như `NO_CROP_DETECTED` đã làm. Chưa sửa vì một ảnh không đủ để chốt
hình dạng vùng đệm — cần [EX-2](need_exchange.md).

---

### 🎯 QC-18b · P1 · Nếp gấp KHÔNG làm lệch tứ giác thì vẫn lọt {#qc-fold-residual}

[QC-18](#qc-text-level) bắt được ảnh gấp mép của khách, nhưng phải nói rõ nó bắt **cái gì**:
`TEXT_NOT_LEVEL` phát hiện *phép nắn đã hỏng*, không phát hiện *tờ giấy bị gấp*. Hai chuyện đó
trùng nhau ở ca đã gặp vì nếp gấp cắt mất một góc tờ giấy nên tứ giác lệch hẳn đi.

Ca còn lọt: nếp gấp **nằm giữa trang** hoặc gấp mà 4 góc vẫn đúng chỗ. Khi đó tứ giác đúng, chữ
vẫn ngang, mọi chỉ số đều đẹp — mà một dải nội dung thì bị che.

**Hai hướng đã đo và bỏ**, ghi lại để không ai đo lại:

| Hướng | Ảnh gấp mép | Ảnh tốt tệ nhất | Kết luận |
|---|---|---|---|
| phần dư diện tích `mask \ quad` | 0.912 | 0.9125 | lẫn hẳn vào nhau |
| thuỳ dư lớn nhất / diện tích tứ giác | 0.0347 | **0.0382** | ảnh tốt còn tệ hơn |

Cả hai chết vì cùng một lý do: `approxPolyDP` cho tứ giác **nội tiếp**, nên nó khớp *dọc theo
chính nếp gấp* — nếp gấp không sinh phần dư nào. Toàn bộ phần dư đo được là góc bo tròn của mask.

`--cross-check` cũng không cứu: hai detector cho `detector_iou = 0.899`, tức **đồng thuận cao**.
Chúng sai giống nhau vì cùng đọc một mask.

⚠️ Patent Xerox [US10212299B2](https://patents.google.com/patent/US10212299B2/en) (cấp 2019-02-19)
phủ đúng bài toán này bằng cách chia ảnh làm 4 góc phần tư + edge profile + tương quan chéo 2-D.
**Tránh đường đó.** Liên quan [PKG-5](#pkg-license).

**Chặn bởi**: cần ảnh gấp-giữa-trang thật để đo — hiện có đúng 1 ảnh gấp mép. Xem
[EX-2](need_exchange.md).

---

## B. Quyết định còn hiệu lực

Đã đo, đã chốt. Ghi lại vì chúng là **lý do KHÔNG làm** một việc — thứ không nằm trong commit
nào, và là thứ hay bị đề xuất lại nhất.

### 🔬 S-5 · Dewarping: đo rồi, **không làm** {#s-dewarp}

Giấy phẳng thì 4 mép là đoạn thẳng; giấy cong thì mép phình ra khỏi dây cung nối hai góc. Đo độ
lệch lớn nhất của contour so với dây cung, chia cho chiều dài mép → *tỉ lệ vồng*, không phụ
thuộc kích thước ảnh.

Trên 36 ảnh (29 ảnh thật + 7 ảnh mẫu): trung vị 0.021–0.051, max 0.355. Nhưng **5 giá trị cao
nhất đều là ảnh mà bước tách nền đã sai** — mép "vồng" đó là biên của mặt bàn hay xấp giấy,
không phải giấy cong. Bỏ nhóm đó ra thì max còn **0.074**, trong khi ảnh mẫu *phẳng đã biết*
cũng cho 0.069–0.072. Tức **0.07 là sàn nhiễu của mask rembg, không phải độ cong thật**, và
không ảnh nào vượt sàn đó.

Không có bằng chứng nào đòi dewarping → không làm, tiết kiệm 1 tuần+.

⚠️ **Giới hạn của phép đo**: nó bắt giấy *vênh mép* (hoá đơn cuộn), nhưng **bỏ sót** tờ phẳng ở
mép mà gợn sóng ở giữa, và không bắt được *nếp gấp*. Bằng chứng dứt điểm phải là một tập ảnh hoá
đơn cuộn thật — chưa có. **Mở lại khi có.**

💡 Quan sát phụ: tỉ lệ vồng cao lại là tín hiệu tách nền sai rất sạch (5/5). Có thể thành một
metric rẻ tiền sau, nhưng chưa đủ dữ liệu chốt ngưỡng.

### ⚡ SPD-5 · Dynamic batching: đo trên H100, cải thiện **0.8%** → không làm {#spd-batching}

Đo trực tiếp: `ort.run` batch=1 tốn 6.5 ms/ảnh, batch=32 tốn 2.73 ms/ảnh. Tiết kiệm 3.8 ms trên
tổng 477 ms — **0.8%** — trong khi phần CPU 297 ms/ảnh **batching không chạm tới được**.

Batching chỉ nén được phần suy luận. Trên CPU suy luận áp đảo nên nó có vẻ hấp dẫn; trên GPU tỉ
lệ đảo ngược và phần CPU thành toàn bộ nút cổ chai. Gom batch khi đó là tối ưu đúng vào chỗ đã
hết chậm.

Kèm theo, file ONNX u2net xuất ra với **batch đóng cứng bằng 1**, nên làm thật còn phải vá trục
batch và chứng minh mask không đổi trên 37 ảnh. Chi phí đó cho 0.8% là không đáng.

**Đường rẻ hơn, đã xác nhận bằng số**: nhân số tiến trình. Một tiến trình đạt 8.4 ảnh/s trên máy
64 nhân; kịch bản 700 CCU nặng nhất cần 9 container ≈ 38 GB trên máy 231 GB — gọn trong **một**
máy sau một bộ cân bằng tải, không viết thêm dòng code nào.

Còn phải chốt với khách "700 CCU" nghĩa là bao nhiêu ảnh/s:
[EX-16](need_exchange.md#ex-throughput).

### ⚡ SPD-4 · GPU chạy được, nhưng hiện **chậm hơn CPU** {#spd-gpu}

Đường CUDA đã chạy thật trên H100 (`/healthz` báo `CUDAExecutionProvider`). Nhưng trên chính máy
đó nó cho thông lượng **thấp hơn** bản CPU — 6.65 ảnh/s so với 8.68 — vì một service vLLM giữ
77.8/81.5 GB VRAM, chỉ chừa lại ~2.9 GB nên `GPU_CONCURRENCY` phải hạ xuống 2, trong khi bản CPU
dùng được 16 luồng.

Nhả thêm VRAM (`gpu_memory_utilization` của vLLM) sẽ đảo lại tương quan. Chừng nào chưa nhả thì
**bản CPU là lựa chọn đúng**.

Cái bẫy phải nhớ: onnxruntime tụt về CPU **trong im lặng** khi thiếu thư viện CUDA — không lỗi,
không cảnh báo, chỉ chậm gấp mấy chục lần. Vì thế `/healthz` báo provider thật, và
`QC_SCANNER_REQUIRE_GPU=1` làm container thoát hẳn thay vì chạy chậm âm thầm.

### ⚡ SPD-7 · Hạ ảnh về đúng cỡ model: có cờ, **mặc định tắt** {#spd-resample}

`predict()` của rembg phóng mask 320×320 ngược lên đúng kích thước ảnh gốc rồi lõi QC hạ ngay về
`work_height` — phép phóng đó là công toi, tốn 43ms/ảnh. Tự resize xuống 320×320 trước thì cả
hai phép resize trong `predict()` thành no-op và **tensor vào model không đổi một bit**.

Nhưng chặng resample cuối khác đi làm metric trôi trung vị 0.14%, và có đúng **một** ảnh thật
nằm cách ngưỡng 0.02% nên lật thành false fail — xem [QUAL-4](#qual-knife-edge). 43ms không đáng
đổi lấy một ảnh tốt bị loại.

Bật bằng `QC_SCANNER_SEGMENT_AT_MODEL_SIZE=1` **sau khi** đã chạy `qc-scanner-batch` trên ảnh
thật của mình và đối chiếu verdict trước/sau.

### 🔬 S-1 · Đổi model nền: đã đo, **chưa đủ căn cứ đổi** {#s-model-swap}

Đổi model nay là một tham số (`--model` / `QC_SCANNER_REMBG_MODEL`). Trên 9 ảnh thật:

| model | thời gian/ảnh (median) | verdict |
|---|---|---|
| `u2net` (mặc định) | **0.395s** | 6 pass · 3 warn |
| `isnet-general-use` | 1.198s | 4 pass · 5 warn |

isnet **chậm gấp 3** và đẩy 2 ảnh từ `pass` sang `warn` (`CLIPPED_EDGE`). Không có nhãn thì
không biết mã đó **đúng** (isnet bắt biên sát hơn, phát hiện tài liệu thật sự chạm mép) hay
**sai**. Cần [EX-2](need_exchange.md).

---

### 🖼️ QC-17b · Viền quanh ảnh ra: đã siết, và **đây là mức dừng** {#qc-padding-floor}

Yêu cầu ban đầu là "siết `max_edge_grow_ratio` lại, viền to quá". Đo trên 38 ảnh vào thật thì
**đó là cái núm sai**, và số liệu nói rõ vì sao — viền nền trung bình / số ảnh bị cắt lẹm vào
giấy quá 1%:

| Siết bằng trần | viền TB | lẹm > 1% | | Siết bằng phân vị | viền TB | lẹm > 1% |
|---|---|---|---|---|---|---|
| 0.05 (cũ) | 4.58% | 4 | | 100 (cũ) | 4.58% | 4 |
| 0.03 | 4.28% | 7 | | **95 (nay)** | **3.38%** | **6** |
| 0.02 | 3.66% | **9** | | 92 | 3.02% | **12** |

Cùng mức viền, phân vị rẻ hơn hẳn: trần 0.02 cho viền 3.66% với 9 ảnh bị cắt, thua phân vị 95
ở **cả hai** cột. Lý do: trần chỉ chặn ca bệnh lý, còn phân vị sửa đúng cơ chế — cạnh bị đẩy tới
**điểm contour xa nhất**, nên một cái gai đơn lẻ trên mask kéo cả cạnh ra và mang nền vào ảnh.

Cột `viền 90%` **không đổi** qua mọi mức trần từ 0.01 đến 0.05 — nhóm ảnh viền dày nhất không hề
dày vì nới ra.

**Vì sao dừng ở 95**: xuống 92 thì số ảnh bị cắt gấp đôi mà viền chỉ bớt thêm 0.36 điểm.

**Vì sao siết nữa cũng không hết viền**: phần lớn viền còn lại không do nới ra. Ảnh `04.55.30`
(CCCD), tứ giác **chưa nới** đã cắt vào thẻ ~15px mỗi cạnh; với tài liệu **bo góc**, phủ hết thẻ
bằng một tứ giác thì bắt buộc kéo theo nền ở bốn góc lượn. Muốn hết hẳn thì phải bỏ mô hình
"một tứ giác" — tức [S-3](#s-docaligner), không phải chỉnh ngưỡng.

---

### 🖼️ QC-19b · `deskew` mặc định **bật** — và điều kiện để tắt {#qc-deskew-default}

Xoay một góc khác bội số 90° buộc **nội suy lại mọi điểm ảnh**. [FADGI] mức 4 sao vì thế **cấm**
de-skew bằng phần mềm với bản gốc lưu trữ.

Ta vẫn bật mặc định vì đầu ra của qc_scanner đi vào **OCR**, không vào kho lưu trữ ([EX-13]): ở
đó chữ nằm ngang đáng giá hơn phần độ phân giải thực bị mất. Đo được: 18/38 ảnh lệch > 0.5° còn
2, tốn 1.0ms.

**Tắt `QC_SCANNER_DESKEW=0` nếu** khách dùng ảnh ra làm bản gốc lưu trữ, hoặc phải tuân FADGI/
ISO 19264. Đây là câu hỏi nghiệp vụ, không phải câu hỏi kỹ thuật — chưa hỏi khách bao giờ.

[FADGI]: https://www.digitizationguidelines.gov/guidelines/FADGI%20Technical%20Guidelines%20for%20Digitizing%20Cultural%20Heritage%20Materials_3rd%20Edition_05092023.pdf
[EX-13]: need_exchange.md

---

## C. Đã đóng

Chi tiết ở commit tương ứng. Giữ ở đây vì có chỗ khác trỏ tới.

| Mã | Việc | |
|---|---|---|
| VẤN ĐỀ GỐC | qc_scanner không nói được **vì sao**; nay `scan_qc()` trả verdict + reasons + metrics | {#root-no-qc} |
| BUG-2 | `scan()` nuốt mọi exception rồi trả `None`; nay `ScanError` mang mã lý do | {#bug-swallow} |
| SEC-1 | `GET /?url=` đọc được file nội bộ và metadata cloud — bỏ hẳn, `GET /` trả `405` | {#sec-ssrf} |
| QC-1 | Kiểu `ScanResult`; bất biến `verdict == "pass"` ⟺ `reasons == []` | {#qc-contract} |
| QC-7 | Đường lui dò cạnh khi rembg thua, **có nhãn** `RECOVERED_BY_EDGE_FALLBACK` | {#qc-edge-fallback} |
| QC-9 | Nhiều tài liệu trong một ảnh bị âm thầm bỏ qua → `MULTIPLE_DOCUMENTS` | {#qc-multi} |
| QC-11 | `NO_CROP_DETECTED` — không cắt được gì là `fail`, không phải `warn` | {#qc-no-crop} |
| QC-12 | `CONTENT_CLIPPED` — mất viền trắng thì được, mất **chữ** thì không | {#qc-content-clipped} |
| QC-13 | Hint hai tầng: người chụp (chụp lại được) / người vận hành (không) | {#qc-two-tier-hint} |
| QC-14 | Cờ `pre_cropped`; đo 37 ảnh thấy **không tự đoán được**, phía gọi phải khai báo | {#qc-precropped} |
| QUAL-1 | Lấy tứ giác **đầu tiên** không lọc rác; nay lọc lồi/diện tích/skew rồi mới chọn | {#qual-quad-filter} |
| QUAL-2 | Hằng số cứng không scale theo kích thước ảnh | {#qual-scale} |
| DEP-1 | `requirements.txt` không ghim version nào | {#dep-pin} |
| SPD-1 | Bỏ vòng "mã hoá PNG toàn cỡ rồi giải mã lại" của rembg — nhanh **1.38x** | {#spd-roundtrip} |
| SPD-2 | `scan_qc()` chạy trên vòng lặp sự kiện làm `/healthz` trễ 617ms dưới tải; nay 2ms | {#spd-event-loop} |
| SPD-3 | Upload > 1MB bị ghi ra file tạm trên đĩa, trái [EX-12](need_exchange.md) | {#spd-spool} |
| SPD-6 | GPU hết bộ nhớ bị báo thành "ảnh hỏng" (`400`); nay `INFERENCE_FAILED` + `503` | {#spd-oom} |
| OPS-4 | `MAX_CONCURRENCY` chặn xử lý nhưng **không** chặn bộ nhớ; nay có `MAX_IN_FLIGHT` + `503` | {#ops-inflight} |
| N-08 | Đầu vào **và** đầu ra PDF, một phán quyết mỗi trang | {#n-pdf} |
| QC-18 | `TEXT_NOT_LEVEL` — đo góc dòng chữ **sau khi nắn**; chỉ số đầu tiên soi đầu ra | {#qc-text-level} |
| QC-19 | Nắn thẳng phần dư (18/38 ảnh lệch > 0.5° → còn 2); không xoay khi nắn hỏng | {#qc-deskew} |
| QC-20 | `NO_CROP_DETECTED` thêm đường vào: detector thua **và** góc lọt ra ngoài ảnh | {#qc-lost-paper} |

Bốn bài học đáng giữ lại, vì chúng không nằm trong diff nào:

**Mốc hồi quy phải đứng yên, kể cả khi nó bắt đúng thứ ta vừa cố tình đổi.** QC-19 làm 6 bài
`test_regression` đỏ, và phản xạ đầu tiên là dựng lại `examples/*.out.png` bằng pipeline mới.
Làm rồi mới thấy sai: mốc khi ấy trôi theo mọi tính năng, nên nó thôi phát hiện được thứ nó sinh
ra để phát hiện — chất lượng tụt dần mà không bài nào đỏ. Cách đúng đã có sẵn tiền lệ từ QC-17:
**tắt tính năng mới trong fixture** và kiểm nó bằng bài riêng. `examples/*.out.png` là đầu ra
thuật toán gốc và phải giữ nguyên như vậy; thứ được phép dài thêm là danh sách cờ tắt trong
`conftest.py`, mỗi dòng ứng với một tính năng đã có bài kiểm của nó.

Hệ quả phụ đáng nhớ: `tests/test_pdf.py` dựng PDF **từ chính** `examples/doc-1.out.png`, nên dựng
lại ảnh mẫu làm đỏ thêm một bài chẳng liên quan gì tới hồi quy ảnh. Ảnh mẫu là **dữ liệu dùng
chung**, không phải tài sản riêng của `test_regression.py`.

**Phép đo giả định sẵn thứ nó định kiểm thì luôn trả lời "đạt".** Bản đo góc chữ đầu tiên gộp ký
tự thành dòng bằng một nhân hình thái **nằm ngang** rồi đo góc — trên ảnh lệch 24° nó trả `0.0°`,
vì chữ chéo không gộp nổi thành dòng nên rơi khỏi phép đo. Kết quả "sạch" đó suýt được dùng làm
bằng chứng rằng ý tưởng sai. `tests/test_text_skew.py` dựng lại đúng phép đo mù đó và khoá nó lại.
Hệ quả chung: **kiểm cái thước trước khi tin số nó đọc** — quay ảnh những góc biết trước rồi bắt
thước đọc lại là việc rẻ hơn nhiều so với gỡ một kết luận sai.

**Đơn vị đo phải khớp thứ đang bảo vệ.** `MAX_IN_FLIGHT` sinh ra để chặn RAM, nhưng máy server
có 231 GB nên trần 2 GB chẳng bao giờ là ràng buộc. Ràng buộc thật là **thời gian chờ**, và con
số đúng chỉ lộ ra khi đo thông lượng — không phải khi đếm megabyte.

**Một con số đúng bị chép ra nhiều bản thì các bản sẽ trôi khỏi nhau.** `MAX_CONCURRENCY: "2"`
(số của máy dev 10 nhân) lọt vào `docker-compose.yml` làm máy 64 nhân mất ~64% năng lực trong im
lặng; rồi `bench.py` giữ thêm một bản sao với default `"2"` riêng, nên công cụ đo nói dối về
đúng thứ nó đang đo. Nay cả hai van sống ở [`limits.py`](../src/qc_scanner/limits.py), có test
chặn việc chép lại.

---

## D. Backlog

| Mã | Tính năng | Ưu tiên | Ghi chú |
|----|-----------|---------|---------|
| N-03 | Chế độ debug đầy đủ | P2 | Một phần: `--debug-dir` xuất mask + ảnh đã nắn; chưa vẽ chồng contour/tứ giác |
| N-07 | Tách nhiều tài liệu trong một ảnh thành nhiều đầu ra | P3 | Nối tiếp QC-9 — hiện chỉ báo `MULTIPLE_DOCUMENTS` rồi lấy tờ lớn nhất |
| N-09 | Hậu xử lý làm nét / khử bóng | P3 | Đầu ra "giống bản scan"; chờ nhu cầu khách |

---

## Cách dùng file này

- **Chỉ ghi việc chưa làm.** Làm xong thì xoá mục đó và để commit kể lại — trừ khi có chỗ khác
  trỏ tới, khi đó rút về một dòng trong §C.
- Issue mới: thêm vào §A với mã tăng dần, priority, và `path:line` làm bằng chứng.
- Issue về **chất lượng nắn** phải kèm ảnh ví dụ sai + metric — xem [test_eval.md](test_eval.md).
- Thêm **reason code** mới: khai đủ hint + audience trong
  [algorithm.md §7](algorithm.md#ma-ly-do) kèm ca test. Có test khoá
  danh mục đó cho khớp với `REASONS`.
- Chốt một **ngưỡng**: ghi số đo vào docstring của trường đó trong
  [`config.py`](../src/qc_scanner/config.py), **cạnh chính con số** — không phải vào đây.
