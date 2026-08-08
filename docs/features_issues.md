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

**Đang mở**: [OPS-3](#ops-docker-unverified) (P0) · [PKG-6](#pkg-model-licence) (P0) ·
[PKG-5](#pkg-license) (P1) · [QC-23](#qc-glare-severity) (P1) ·
[QC-18b](#qc-fold-residual) (P1) · [QUAL-5](#qual-ocr-truth) (P1) · [SPD-8](#spd-onnx-threads) (P1) ·
[QUAL-3](#qual-sweep) · [QUAL-4](#qual-knife-edge) · [QC-24](#qc-text-height) (P2).

**Đã hết chặn một phần**: [S-3 đã đóng](#s-docaligner) — DocAligner là detector mặc định, và
việc đó quyết được là nhờ **tập vàng công khai** [SmartDoc 2015](https://zenodo.org/records/1230218)
(CC-BY-4.0, 926 ảnh, 5 nền, nhãn 4 góc). Bộ chuyển: `qc-scanner-smartdoc`. Nghĩa là QUAL-3/QUAL-4
không còn phải chờ khách nữa cho phần **hình học**; chúng vẫn chờ [EX-2](need_exchange.md) cho
phần **verdict**, vì SmartDoc không có nhãn verdict và ngưỡng của nó lệch miền (832/836 ảnh bị
`TOO_SMALL` do khung video để xa).

Mọi ngưỡng trong [`config.py`](../src/qc_scanner/config.py) vẫn là ước đoán, trừ 11 cái đã chốt
bằng số đo: `max_border_ink_ratio` · `no_crop_area_ratio` · `no_crop_min_confidence` ·
`min_long_side_px` · `min_blur_score` · `max_text_skew_deg` · `edge_grow_percentile` ·
`no_crop_corner_outside_px` · `border_paper_min_ratio` · `border_paper_percentile` ·
`DocAlignerDetector.low_confidence`.

⚠️ "Chốt bằng số đo" **không đồng nghĩa với đúng**: 8/11 số này đo trên 30–38 ảnh của đúng một
khách, do chính tôi dán nhãn. Xem [QUAL-5](#qual-ocr-truth).

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

### 📦 PKG-6 · P0 · Hai giấy phép model đang bị bỏ ngỏ {#pkg-model-licence}

**`isnet-general-use`** đang được [`config.py`](../src/qc_scanner/config.py) *khuyên dùng* trong
docstring của `rembg_model`. Code của nó Apache-2.0, nhưng **dữ liệu huấn luyện DIS5K buộc người
dùng thương mại ký thoả thuận riêng**. Ta đang chỉ khách đi vào chỗ đó.

**`QC_SCANNER_REMBG_MODEL` không có allowlist** — nhận bất kỳ tên model nào rembg biết, gồm
`bria-rmbg` vốn cần giấy phép trả phí. Một biến môi trường đặt sai là vi phạm giấy phép, im lặng.

Ngược lại, phần đang chạy thì **sạch**: DocAligner Apache-2.0, U²-Net Apache-2.0, rembg MIT.

**Việc**: bỏ lời khuyên `isnet-general-use` khỏi docstring; thêm allowlist cho model nền; ghi
giấy phép từng model vào tài liệu bàn giao. Gắn với [PKG-5](#pkg-license).

---

### ✅ QC-22 · Chữ bị chính đường cắt của ta chém — ĐÃ BỊT {#qc-crop-cuts-text}

Mọi phép kiểm cắt xén khác đều hỏi *"khung hình có cắt mất gì không"*, nên chỉ soi những cạnh
mà tứ giác **áp vào mép tấm ảnh**. Tứ giác nằm gọn giữa khung rồi tự nó chém qua tài liệu thì
`border_ink_ratio = 0.000` — không phải vì không mất gì, mà vì phép kiểm **không hề chạy**.

Ca đưa tới quyết định là một PDF thật của khách: bìa sổ đỏ, `touches_border = 0`, mất trọn dòng
tiêu đề, verdict **`pass` với không một mã lý do nào**. Kiểu hỏng đắt nhất — mất nội dung mà mọi
thứ báo xanh.

**Cách giải: so tứ giác với mặt nạ phân vùng.** Mặt nạ vốn đã được tính cho `alpha_coverage`,
nên phép kiểm không thêm lần chạy mô hình nào. Hai điều kiện, phải có **cả hai**:

1. `abandoned_ratio ≥ 0.10` — phần mặt nạ bị tứ giác bỏ lại ngoài, sau khi **co 6% cạnh ngắn**.
2. `abandoned_structure ≥ 0.10` — mật độ biên trong mảng đó, so với trong lòng tứ giác.

**Ba thước đã thử và thất bại**, ghi lại để không ai đi lại:

| cách hỏi | vì sao hỏng |
|---|---|
| "ngoài đường cắt có giấy và có mực không" | ảnh cắt **đúng** vẫn lên 0.3–1.0 — đếm phải **bóng mép giấy** |
| "có nét mực nào vắt qua đường cắt không" | ca hỏng đã biết chỉ **0.012**, ảnh tốt lên **0.43** |
| "cạnh tứ giác có tựa vào biên Canny không" | chấm ảnh **đúng** 0.000 còn ca cắt thật 0.405–0.515 — ngược hoàn toàn |

**Hai bẫy mà thiết kế cuối phải né**, cả hai đều lộ ra khi đo:

* *Mảng lớn ≠ cắt lẹm.* Ảnh `abc1b13` cắt **hoàn toàn đúng** nhưng rembg trùm cả mặt bàn, cho
  `abandoned_ratio = 0.241` — **cao hơn cả ba ca cắt lẹm thật**. Chỉ đo diện tích thì nó là báo
  động giả đứng đầu bảng. Thước cấu trúc là thứ duy nhất tách được (0.000 so với 0.512–1.127).
* *Mực không phải lúc nào cũng tối.* Ca thật đầu tiên là **bìa đỏ sổ đỏ, chữ nhũ vàng** — sáng
  trên tối. Cả `ink_mask` lẫn `paper_mask` (đều đo theo độ sáng) trả 0.000 ở đó và bỏ lọt đúng
  ca cần bắt. Vì thế phép đo cuối đếm **mật độ biên**, không đếm mực.

Bước **co 6%** là điều kiện phân biệt chính, không phải khử nhiễu: mặt nạ luôn rộng hơn tứ giác
một viền mỏng *bao quanh*, cộng lại ra diện tích đáng kể (ảnh cắt đúng vẫn cho 0.074 khi co 2%).
Vết cắt thật dồn về **một phía** và đặc nên chịu được co mạnh: 0.250 → 0.195, trong khi viền tan
hết 0.074 → 0.000.

**Cổng thứ ba là bài học đắt nhất của mục này.** Bản đầu chỉ có hai cổng trên, đo được **32/32
đúng trên 32 ảnh thật** và đã được push. Con số đó **đúng nhưng vô nghĩa**: 29 ca âm tính trong
tập ấy đều chụp trên nền tương đối sạch, nên tập đó không hề chứa hướng hỏng thật sự.

Chạy trên SmartDoc (2421 ảnh, 5 nền) thì lộ ra ngay:

| nền | ảnh | IoU tb | báo động giả (2 cổng) | (3 cổng) |
|---|---|---|---|---|
| background01–04 | 2177 | 0.985–0.988 | 2 | 0 |
| **background05** (bàn bừa bộn) | 244 | **0.988** | **171 (70%)** | **0** |
| TỔNG | 2421 | | 173 = **7.15%**, bắt đúng **0** | **0** |

Tứ giác ở `background05` gần như hoàn hảo (IoU 0.988) mà vẫn bị loại: rembg trùm cả mặt bàn, nên
mảng "bị bỏ rơi" là bút, dây, giấy khác — to *và* có cấu trúc, qua được cả hai cổng đầu. Cổng cấu
trúc chỉ chặn được nền **trơn**; bàn **bừa bộn** thì có cấu trúc.

Cứu được nhờ một điểm bất đối xứng: khi *tứ giác* sai thì mặt nạ vẫn là tờ giấy vuông vắn; khi
*mặt nạ* sai thì nó vô định hình. Quét ngưỡng trên **toàn bộ** 2421 + 32 ảnh:

| `fit ≥` | báo động giả | giữ ca cắt lẹm |
|---|---|---|
| 0.00 | 173 (7.15%) | 3/3 |
| 0.80 | 8 (0.33%) | 3/3 |
| **0.83–0.88** | **0** | **3/3** |
| 0.89 | 0 | 2/3 ← mất ca thật của khách |

Chọn 0.85 vì nằm giữa **vùng bằng phẳng**: báo động giả cao nhất 0.822, ca cắt lẹm thấp nhất
0.889. Chọn ngưỡng trên vài mẫu chính là sai lầm đã gây ra vòng này.

**Kết quả cuối:** SmartDoc 2421 ảnh → **0 báo động giả**; 32 ảnh thật → bắt đúng 3/3 ca cắt lẹm,
verdict toàn kho pass 19→18, warn 6→5, fail 7→9.

---

### ✅ QC-25 · `pre_cropped` suy từ ĐỊNH DẠNG FILE, giấu mất crop hụt — ĐÃ SỬA {#qc-pre-cropped-guess}

`pdf_pre_cropped` coi **mọi** trang PDF là "đã cắt sẵn" rồi xoá 5 mã lý do về biên
(`CLIPPED_EDGE`, `CONTENT_CLIPPED`, `NO_CROP_DETECTED`, `SUBJECT_FILLS_FRAME`,
`RECOVERED_BY_MASK_FALLBACK`). Giả định: *trang PDF chính là tờ giấy, máy scan cắt xong mới
đóng thành PDF.*

Giả định đó sai với **PDF ghép từ ảnh chụp điện thoại** — vẫn còn nền, vẫn cần cắt, vẫn cắt
sai được. Ca thật của khách (`132578.pdf`): trang bìa sổ đỏ bị cắt còn `quad_area_ratio = 0.506`,
**mất trọn tấm bìa đỏ**, ra `pass` với danh sách lý do **rỗng**. `CONTENT_CLIPPED` đã bắt được
nó và bị xoá ngay tại đây.

Điều trớ trêu: ghi chú của chính hàm `_apply_pre_cropped` đã dự báo đúng chuyện này — *"rủi ro
còn lại là gắn cờ nhầm cho một ảnh chụp: khi đó qc_scanner mất khả năng bắt crop hụt. Đó là
đánh đổi thuộc về phía gọi, và vì thế nó phải **khai báo** chứ không được đoán."* Đường PDF
đang đoán, và đoán theo định dạng file.

**Cách sửa:** "đã cắt sẵn" phải có nghĩa là **không có gì để cắt**. Cắt đi một nửa khung rồi
vẫn tự nhận là cắt sẵn thì mâu thuẫn với chính mình. Thêm điều kiện `quad_area_ratio ≥ 0.90`.

Đo trên **50 trang của 22 file sổ đỏ thật**:

| ngưỡng | số trang đổi phán quyết |
|---|---|
| 0.50 | 0 — không sửa được gì |
| **0.70–0.94** | **1** — đúng trang hỏng, `pass → fail` |
| 0.95 | 2 — bắt đầu gắn cờ oan trang scan đầy khung (0.948) |
| 0.99 | 5 — gắn cờ oan cả 0.987 và 0.989 |

Chọn 0.90 cho nằm giữa vùng phẳng. Sau khi sửa: mã bị dập giảm 49 → 40, `CONTENT_CLIPPED` bị
dập 1 → **0**, và không trang nào khác đổi phán quyết.

**Ghi chú:** không dựng được tứ giác (`quad_area_ratio is None`) thì vẫn dập như cũ — khi đó
trả nguyên ảnh gốc, tức **không có phép cắt nào** để nghi ngờ.

---

### 🖼️ QC-23 · P1 · `GLARE` và `TOO_DARK` là cờ phẳng, không có mức độ {#qc-glare-severity}

Ảnh thật `04.58.13`: `glare_ratio = 0.843` (ngưỡng `0.02` — vượt **42 lần**),
`median_brightness = 255.0`. Tức 84% diện tích tài liệu bão hoà trắng, quá nửa ảnh không còn
thông tin. Verdict: **`warn`**.

Loá 3% và loá 84% cho ra cùng một phán quyết. Nguyên tắc đã chốt với khách là *không đạt thì
phải nhè ra*, nên mức trên phải là `fail`.

**Đo thêm (50 trang sổ đỏ thật của khách) — và nó lật ngược cả hướng sửa ở trên:**

`GLARE` phát trên **44/50 trang**, kéo theo 42/50 trang ra `warn`. Toàn bộ đều là bản scan
sạch, không trang nào loá.

| ảnh | `glare_ratio` | thực tế |
|---|---|---|
| `10225-C-I 612206` tr1 | **0.945** | scan sạch, **không loá** |
| `04.58.13` | **0.843** | loá thật, mất nội dung |

Bản scan sạch chấm **cao hơn** ảnh loá thật — thứ tự bị đảo, nên **không ngưỡng nào tách được**.
Đây không phải lỗi chỉnh ngưỡng mà là **phép đo sai bản chất**: `glare_ratio` đếm tỉ lệ pixel
≥ 250, mà nền giấy trắng trong bản scan vốn đã ~255. Càng scan đẹp, điểm càng cao. Thêm một
ngưỡng thứ hai như đề xuất cũ sẽ **không** giải quyết được gì.

Hệ quả nặng hơn con số: một cờ bật trên 88% hồ sơ làm mức `warn` mất hết ý nghĩa, và người vận
hành sẽ học cách bỏ qua nó — kể cả khi gặp ảnh loá thật.

**Quyết định của khách (2026-08-08): GIỮ NGUYÊN**, chấp nhận `warn` là nhiễu. Không tắt `GLARE`,
không thay phép đo lúc này.

**Việc còn lại, khi nào ưu tiên trở lại**: thay phép đo, không phải thêm ngưỡng. Cần phân biệt
"nền giấy trắng" với "vùng cháy sáng mất chữ" — hiện chỉ có **2 ảnh loá thật** để hiệu chuẩn,
quá mỏng (thiết kế thước trên vài mẫu chính là nguyên nhân của QC-22 và QC-25). Nguồn dữ liệu
đúng là **SmartDoc-QA**: cùng trang chụp ở nhiều mức thiếu sáng/loá, **kèm kết quả OCR**, nên
hiệu chuẩn được theo tỉ lệ lỗi ký tự thật thay vì theo mắt — xem [QUAL-5](#qual-ocr-truth).

---

### 🎯 QUAL-5 · P1 · Ngưỡng chất lượng đang chốt theo MẮT TÔI, không theo OCR {#qual-ocr-truth}

Khảo sát 2026 (xem [algorithm.md §8.4](algorithm.md#doi-chieu)) cho hai kết quả đổi cách nghĩ:

- **Không có ngưỡng variance-of-Laplacian nào trong văn liệu bình duyệt.** Con số 200 hay lưu
  truyền là tài liệu nhà cung cấp, không suy dẫn. `min_blur_score = 25.0` của ta cũng vậy —
  chốt ở chỗ *mắt người thấy xấu*, không phải chỗ *OCR bắt đầu hỏng*.
- **Trần lý thuyết**: [arXiv:1906.01907](https://arxiv.org/abs/1906.01907) Bảng V — chỉ số nét
  thủ công tương quan với độ chính xác OCR 0.90 trên tập chỉ-mờ nhưng chỉ **0.62** trên
  SmartDoc-QA (đa biến dạng). Ảnh khách thuộc loại thứ hai, nên `min_blur_score` dù chốt hoàn
  hảo cũng chỉ giải thích ~38% phương sai.

**Việc rẻ nhất, không cần thêm ảnh khách**: lấy 30 ảnh đang `pass`, làm mờ/thu nhỏ/tăng loá dần
theo bước cố định, ghi lại điểm OCR bắt đầu hỏng. Cho ngưỡng **cả 4 chỉ số cùng lúc**.

**Chặn**: ngưỡng phụ thuộc engine OCR (PCC 0.78 PaddleOCR → 0.91 Keras OCR) → phải chốt engine
hạ nguồn trước ([EX-19](need_exchange.md)). Bộ [SmartDoc-QA](https://zenodo.org/records/5293201)
(CC-BY-4.0, 4.260 ảnh, ground truth là **kết quả OCR**) dùng được ngay cho việc này.

---

### ⚡ SPD-8 · P1 · Không có tham số nào cho số luồng ONNX {#spd-onnx-threads}

`grep intra_op|num_threads|SessionOptions` trên toàn `src/` và `docs/`: **rỗng**. Mặc định của
ONNXRuntime là số nhân vật lý, nên máy 64 nhân chạy 16 worker thành ~1024 luồng tranh nhau.

Chưa đo được vì máy dev nhỏ; đây là thứ **rẻ nhất** trong toàn bộ khảo sát hiệu năng và có thể
thắng lớn nhất trên máy server. Cần đo cùng [OPS-3](#ops-docker-unverified).

---

### 🔬 QC-24 · P2 · Độ phân giải đang đo sai đại lượng {#qc-text-height}

`min_long_side_px = 600` đo cạnh dài tấm ảnh. Khảo sát 2 triệu ký tự (tài liệu Tesseract chính
thức dẫn): tỉ lệ lỗi OCR tương quan mạnh nhất với **chiều cao chữ tính bằng pixel**, *bất kể dpi
hay cỡ điểm*. Tối ưu 20–40px; dưới x-height 10px "rất ít cơ hội".

Đo chiều cao chữ thì **không cần biết khổ giấy** — gỡ luôn nút thắt [EX-4](need_exchange.md), vốn
là lý do `est_dpi` hiện phải giả định A4 và sai với CCCD/hoá đơn.

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

### 🔬 S-3b · DocAligner là detector mặc định — và cái giá phải trả {#s-docaligner}

Quyết định dựa trên [SmartDoc 2015](https://zenodo.org/records/1230218) (926 ảnh, 5 nền, nhãn 4
góc của người khác dựng — **lần đầu tiên** dự án có số không do tôi tự chấm). Bảng đầy đủ nằm
trong docstring `Config.detector`; điều quyết định là cột `background05`:

| detector | bg01–04 (trung vị IoU) | **bg05** | ≥0.90 toàn bộ |
|---|---|---|---|
| rembg + QC-17 | 0.902–0.919 | **0.192** | 73% |
| rembg tắt QC-17 | 0.956–0.966 | **0.187** | 90% |
| **DocAligner heatmap** | 0.985–0.988 | **0.988** | **100%** |

`bg05` là bàn làm việc bừa — tạp chí, dây cáp, cốc, tờ giấy nằm chồng lên xấp giấy khác. rembg
**sụp hoàn toàn** (0/89 ảnh đạt ngưỡng). Đó lại là ca thực tế nhất.

**Đo được thêm hai thứ trước nay chỉ đoán:**

- **QC-17 tốn ~5 điểm IoU** (0.963 → 0.911), đều trên mọi nền. Không có nghĩa QC-17 sai: nó *cố
  ý* chừa viền, mà IoU so với nhãn ôm sát giấy thì phạt đúng cái nó mua ([EX-1]). Nay biết giá.
- Kết luận "rembg không thua" rút từ **một nền dễ** là **sai** — chỉ 5 nền đầy đủ mới lộ ra.
  Đây là lý do cụ thể để không tin bất kỳ so sánh nào chạy trên tập con dễ.

**Cái giá, đã có đường xử lý, không cái nào bỏ được:**

| vấn đề | xử lý |
|---|---|
| trả rỗng với ảnh **đã cắt sẵn** (7/30 ảnh thật, và **mọi** trang PDF) | đường lui rembg + `RECOVERED_BY_MASK_FALLBACK`, và mã này nằm trong `BORDER_REASONS` nên ảnh khai `pre_cropped` không bị hạ verdict |
| `MULTIPLE_DOCUMENTS` suýt **tắt lặng lẽ** — nó đếm ứng viên của detector, mà mô hình hồi quy góc chỉ trả một tứ giác | đếm contour trong mask, độc lập detector |
| thang confidence không so được (rembg 0.6/0.9 rời rạc; DocAligner số thực, trung vị 0.841) | ngưỡng theo từng detector |
| không có contour → **QC-17 không chạy** | chưa xử lý — xem [QC-17b](#qc-padding-floor) |
| mô hình 83MB nằm trên Google Drive | nướng vào image lúc build (`qc-scanner-fetch-models`), mã `MODEL_MISSING` nếu thiếu |

**Hồi quy còn lại**: 1/30 ảnh (sổ đỏ) DocAligner nắn chéo trong khi rembg làm đúng. Cổng QC
**bắt được** (`fail`), không lọt. Đổi lấy 11 ảnh tốt lên.

**Chưa thu được khoản nhanh**: detector nhanh hơn 7.8× (42ms so với 330ms) nhưng tổng thời gian
mỗi ảnh lại **nhích lên** 0.395s → 0.436s, vì rembg vẫn chạy cho `alpha_coverage`, đường lui, và
đếm đa tài liệu. Gỡ rembg khỏi đường chính là việc riêng, chưa làm.

---

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
| QC-21 | `border_ink_ratio` đếm cả mặt bàn là "mực"; nay lọc theo độ sáng cục bộ (`paper_mask`) | {#qc-paper-gate} |
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
