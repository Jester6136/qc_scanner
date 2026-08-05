# qc_scanner — Tổng quan dự án & Roadmap

> Thay cho "project-insight". Đây là **điểm vào** cho người mới: dự án là gì, đang ở đâu,
> đi về đâu. Chi tiết kỹ thuật ở `algorithm.md`; việc cần làm ở `features_issues.md`;
> cách kiểm ở `test_eval.md`; việc cần hỏi khách ở `need_exchange.md`;
> hợp đồng HTTP bàn giao cho khách ở `api.md`.

---

## 1. Dự án là gì

**qc_scanner** nhận ảnh chụp một tờ tài liệu (điện thoại, chụp nghiêng, nền lộn xộn) → **tìm biên
tờ giấy** → **nắn phối cảnh** → trả ảnh PNG phẳng, cắt gọn đúng khổ giấy. Đây là **tiền xử lý**
cho các bước phía sau (OCR / VLM extract), không phải sản phẩm cuối: ảnh nắn phẳng → chữ nét hơn
→ mô hình bóc dữ liệu chính xác hơn.

### 🎯 Mục tiêu định hướng: qc_scanner là một **cổng QC**, không phải một hàm crop

Hiện tại qc_scanner chỉ trả **ảnh** — thành công hay thất bại đều là một ảnh, người gọi không biết
gì. Đó là điểm phải thay đổi. Định hướng sản phẩm:

> **Mỗi lần xử lý phải trả về một *phán quyết chất lượng*: đạt / đạt-có-cảnh-báo / không đạt.
> Nếu không crop được, phải nói rõ NGUYÊN NHÂN (mã lý do) và HƯỚNG XỬ LÝ cụ thể cho người dùng.
> Và nếu tự khắc phục được thì tự khắc phục trước, rồi mới báo.**

Ba mức, theo thứ tự ưu tiên:

| Mức | Tên | Nội dung |
|-----|-----|----------|
| 1 | **Nói được vì sao** | Thất bại có **mã lý do** (`QUAD_NOT_FOUND`, `TOO_SMALL`, `BLURRY`…), không phải "oops" |
| 2 | **Nói được làm gì tiếp** | Mỗi mã kèm **hướng xử lý** cho đúng đối tượng: người chụp lại / người vận hành / hệ thống gọi |
| 3 | **Tự khắc phục** ("hơn cả thế") | Có đường lui tự động (fallback dò cạnh, nới biên, best-effort) rồi hạ mức xuống *cảnh báo* thay vì *fail* |

Vì sao QC quan trọng hơn crop: ở quy mô hàng vạn ảnh, **ảnh crop sai mà im lặng còn tệ hơn ảnh
báo fail** — nó trôi xuống OCR, sinh dữ liệu sai, và không ai biết cho tới lúc nghiệm thu.
Hợp đồng đầu ra QC đầy đủ: [algorithm.md §2](algorithm.md#2--hợp-đồng-đầu-ra-qc) ·
danh mục mã lý do: [algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes).

- Nguồn gốc: lõi bắt nguồn từ OSS `danielgatis/docscan` (MIT); dự án đã **đổi tên thành
  `qc_scanner`** (2026-08) để phản ánh định hướng QC. **Chưa publish** dưới tên mới.
- Quy mô code: **1639 dòng Python**, 9 file (ban đầu 164 dòng / 3 file). Phần lớn phần tăng thêm
  là lõi QC, bộ eval và chú thích lý do — thuật toán nắn ảnh vẫn nhỏ như cũ.
- Kỹ thuật: **KHÔNG có model riêng của dự án**. `rembg` (U²-Net qua onnxruntime) tách nền,
  phần còn lại là OpenCV thuần (contour + approxPolyDP + four-point transform).

## 2. Kiến trúc (một đoạn)

Bốn mặt tiền chung **một** hàm lõi `scan_qc()`:

```
CLI    (qc-scanner)        ─┐
Batch  (qc-scanner-batch)  ─┤
Server (qc-scanner-server) ─┼──►  qc_scanner.doc.scan_qc()  ──►  ScanResult
Library (import scan_qc)   ─┘                │
                                             ├── Detector (rembg-contour | edge-hough)
                                             ├── geometry: metric hình học + chất lượng
                                             └── qc.REASONS: verdict + hint + audience
```

Không state, không DB, không hàng đợi. Tham số **không còn hardcode** — tất cả nằm trong
`config.py`, override được bằng `QC_SCANNER_*`.

```
scan(bytes) -> bytes                  # API cũ, giữ để không phá người dùng hiện tại
scan_qc(bytes) -> ScanResult          # API chính: ảnh + verdict + reasons[] + metrics
```

Chi tiết luồng: [algorithm.md](algorithm.md).

## 3. Nguyên tắc thiết kế (bất biến)

1. **Một hàm lõi duy nhất** — CLI/server/library đều gọi lõi chung; không nhân bản logic.
2. **Không im lặng** — mọi nhánh không-lý-tưởng (không tìm được biên, dùng fallback, ảnh mờ)
   phải xuất hiện trong `reasons[]`. Trả ảnh gốc mà không báo gì là **bug**, không phải fallback.
3. **Không nén mất mát ở đầu ra** — luôn **PNG**. Ảnh này đi tiếp vào OCR/VLM; nén JPEG làm
   nhiễu nét chữ nhỏ → rủi ro sai dữ liệu bóc ra. (Cùng tinh thần ai-hub `#decide-png`.)
4. **Mọi mã lý do phải có hướng xử lý** — thêm reason code mà không kèm `hint` + đối tượng
   nhận (người chụp / vận hành / hệ thống) là thiếu, không được merge.
5. **Fail-soft nhưng có nhãn** — ưu tiên vẫn trả ảnh best-effort kèm `verdict=warn`, để caller
   tự quyết dùng hay bỏ; chỉ `fail` khi đầu ra chắc chắn vô dụng.
6. **Vendor `rembg` nguyên trạng** — không sửa vendor; mọi tinh chỉnh bọc ở lớp `doc.py`.

## 4. Hiện trạng (2026-08-05)

- Luồng lõi chạy được; **Giai đoạn 0, 1, 2, 4 đã xong**, Giai đoạn 3 làm được phần không cần
  nhãn (QUAL-1/2, S-2, S-6, bộ eval).
- **QC đã có thật**: `scan_qc()` trả `ScanResult{image, verdict, reasons[], metrics}`; 26 mã
  lý do, mã nào cũng có `hint` + `audience`; bất biến `pass ⟺ reasons==[]` được ép ở mức code.
- **239 test** + CI (lint, test trên 3.9/3.12, build wheel). Bài quan trọng nhất là
  "không false pass trên 9 ảnh hỏng dựng bằng OpenCV".
- **Đã đo** trên 8 ảnh mẫu + 9 ảnh thật (`tmp/`): 11 pass · 5 warn · 1 fail. Tốc độ
  **~0.4s/ảnh** sau khi tái dùng session (trước ~3.0s).
- Các lỗi chặn đã đóng hết: rembg gọi hai lần, nuốt lỗi trả `None`, SSRF `GET /?url=`,
  so `bytes` với `str`, vỡ trên ảnh grayscale, dependency không ghim.
- **Vẫn thiếu, và là thứ chặn nhiều nhất: tập vàng có nhãn của khách** (EX-2). Không có nó thì
  không chốt được ngưỡng (QUAL-3), không dám đổi model nền (S-1) hay detector (S-3), và không
  báo cáo được crop rate / false pass / false fail lúc nghiệm thu. Công cụ đã sẵn — chỉ thiếu
  dữ liệu.
- 9 ảnh thật trong `tmp/` là mẫu đầu tiên, **chưa có nhãn** nên chỉ dùng để so cấu hình với
  nhau, chưa dùng để chấm đúng/sai được.
- **2026-08-05 đã chốt 12/13 câu hỏi với khách** → sinh ra Giai đoạn 6 và Giai đoạn 7 (chờ tập
  vàng). Bàn giao là **Docker image kèm HTTP service** → hợp đồng API là bề mặt bàn giao chính.
- **Dewarping (S-5) đã đo và loại khỏi phạm vi** (cùng ngày). EX-5 nói hoá đơn có cong nên nó
  từng được nâng lên P1, nhưng **đo trên 36 ảnh thật thì không ảnh nào cong quá sàn nhiễu của
  mask**. Đây là ví dụ đúng của nguyên tắc "đo trước, làm sau": một câu trả lời phỏng vấn suýt
  kéo theo 1 tuần+ công việc mà số đo không ủng hộ.
- **Đã đo trên 29 ảnh thật của khách** (9 đợt 1 + 20 đợt 2), gồm cả CCCD, sổ đỏ, hoá đơn.

## 5. Bắc Nam của bài toán

Với qc_scanner, "tốt" = **tỉ lệ phán quyết đúng trên ảnh thật của khách**, đo bằng hai con số tách bạch:

- **Tỉ lệ nắn đúng** (crop rate) — trong số ảnh đạt, bao nhiêu % nắn đúng biên thật (IoU ≥ 0.9).
- **Độ chính xác của phán quyết** — quan trọng ngang, đây là phần QC:
  - *false pass*: nói "đạt" nhưng crop sai → **tệ nhất**, dữ liệu bẩn trôi xuống OCR.
  - *false fail*: nói "không đạt" nhưng ảnh dùng được → phí công chụp lại, chấp nhận được hơn.
  - *sai nguyên nhân*: fail đúng nhưng chỉ sai đường → người dùng làm lại vẫn sai.

Thời gian xử lý bị chi phối gần như hoàn toàn bởi **rembg (onnxruntime CPU)**; phần OpenCV chỉ
vài chục ms. Đòn bẩy tốc độ chỉ có 2: (a) tái dùng `rembg` session thay vì tạo mới mỗi call,
(b) chạy onnxruntime trên GPU. **Đừng tối ưu OpenCV.**

**Không thể cải thiện cái không đo được** → Giai đoạn 0 dựng bộ đo trước khi chỉnh thuật toán.

---

## 6. Roadmap chi tiết

### Giai đoạn 0 — Chặn máu & dựng bộ đo ✅ XONG
- [x] `git init` + commit hiện trạng trước khi sửa bất cứ thứ gì.
- [x] **BUG-1** Bỏ `rembg` gọi hai lần ở CLI.
- [x] **BUG-2** Thay "nuốt lỗi trả None" bằng lỗi có mã — nền móng của QC.
- [x] **SEC-1** Tắt/allowlist `GET /?url=` ở server.
- [x] Regression test trên 8 cặp trong `examples/` — [test_eval.md §2](test_eval.md).
- **Tiêu chí ra**: `pytest` xanh trên máy sạch; CLI lỗi thì exit code ≠ 0 kèm mã lý do.

### Giai đoạn 1 — Lõi QC: verdict + reason + hint ✅ XONG
- [x] **QC-1** Kiểu `ScanResult{image, verdict, reasons[], metrics}` + `scan_qc()`.
      Giữ `scan()` cũ làm lớp mỏng bọc ngoài (tương thích ngược).
- [x] **QC-2** Cài **danh mục mã lý do** giai đoạn 1: `DECODE_FAILED`, `SUBJECT_NOT_FOUND`,
      `QUAD_NOT_FOUND`, `TOO_SMALL`, `CLIPPED_EDGE`, `NOT_CONVEX`, `EXTREME_SKEW`.
      — [algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes)
- [x] **QC-3** Mỗi mã kèm `hint` tiếng Việt + đối tượng nhận (người chụp / vận hành / hệ thống).
- [x] **QC-4** Bề mặt hóa QC ra cả 3 mặt tiền:
      CLI → exit code theo verdict + JSON ra stderr/`--report`;
      server → header/`multipart` hoặc `?format=json` trả cả ảnh lẫn phán quyết;
      library → trả `ScanResult`.
- [x] **QC-5** Metric đo được kèm theo: `quad_area_ratio`, `skew_ratio`, `est_dpi`,
      `blur_score` (variance of Laplacian), `contour_candidates`.
- **Tiêu chí ra**: mọi ảnh trong tập thử ra đúng 1 verdict + ≥1 reason khi không phải `pass`;
  không còn đường nào trả `None`.

### Giai đoạn 2 — QC nâng cao & tự khắc phục ("hơn cả thế") ✅ XONG
- [x] **QC-6** Kiểm chất lượng ảnh (không chỉ hình học): `BLURRY`, `GLARE`, `TOO_DARK`,
      `LOW_RESOLUTION` — chặn ảnh mà OCR chắc chắn đọc sai.
- [x] **QC-7** **Fallback dò cạnh** khi rembg không tách được chủ thể (giấy trắng trên nền
      trắng): Canny + HoughLines + giao điểm → tứ giác. Thành công thì hạ `fail` → `warn`
      kèm reason `RECOVERED_BY_EDGE_FALLBACK`.
- [x] **QC-8** Tự sửa nhẹ: nới biên vài pixel khi tứ giác chạm mép, tự xoay về chiều đứng.
- [x] **QC-9** `MULTIPLE_DOCUMENTS` — phát hiện nhiều tứ giác lớn (nhiều tờ trong một khung),
      báo rõ thay vì lặng lẽ lấy tờ to nhất.
- [x] **QC-10** Chế độ debug: xuất ảnh trung gian (mask, contour vẽ chồng, tứ giác chọn) để
      soi ca sai — công cụ chính khi tinh chỉnh ngưỡng.
- **Tiêu chí ra**: false-pass giảm đo được; một phần ca `QUAD_NOT_FOUND` cũ chuyển thành
  `warn` nhờ fallback.

### Giai đoạn 3 — Chất lượng phát hiện biên & nâng cấp lõi 🎯 CHẶN Ở TẬP VÀNG

Lõi hiện tại viết ~2019 (rembg/U²-Net + contour). Khảo sát công nghệ 2026 kết luận **có khoảng
cách đáng kể** so với hướng hiện đại (hồi quy 4 góc trực tiếp) —
[algorithm.md §8](algorithm.md#8-khảo-sát-lõi-thuật-toán-có-còn-hợp-thời-2026).
Thứ tự bắt buộc: **đo trước, đổi sau.**

- [ ] Gán nhãn 4 điểm góc cho tập ảnh thật của khách → **tập vàng** (`need_exchange.md` EX-2).
      Có thể dùng SAM/SAM2 hỗ trợ gán nhãn cho nhanh.
- [x] Đo baseline: IoU tứ giác + crop rate + ma trận nhầm lẫn của verdict.
- [x] **QUAL-1** Loại tứ giác rác: yêu cầu lồi (`isContourConvex`), diện tích ≥ X% ảnh, tỉ lệ
      cạnh hợp lý — thay vì "lấy tứ giác đầu tiên gặp". Giữ giá trị **dù đổi detector nào**.
- [x] **QUAL-2** `medianBlur` / `IMG_RESIZE_H` scale theo kích thước ảnh thay vì hằng số.
- [~] **S-1** (đã đo, chưa đổi) Đổi model nền của rembg (`isnet-general-use`, rồi **BiRefNet**) — **một dòng**,
      rủi ro ~0, đo ngay bằng bộ eval. Việc rẻ nhất trong toàn bộ roadmap.
- [x] **S-2** Tách interface `Detector` (trả 4 điểm + confidence) → 3 cài đặt: rembg-contour ·
      DocAligner · edge-Hough. Lõi QC không phụ thuộc detector.
- [ ] **S-3** ⭐ Thử **DocAligner** (Apache-2.0, ONNXRuntime — đã là dependency sẵn) làm đường
      chính: hồi quy thẳng 4 góc, **suy được góc bị che/ngoài khung**, có confidence tự nhiên
      nạp vào QC. Giữ pipeline cũ làm đối chứng; chốt bằng số đo trên tập vàng.
- [ ] **QUAL-3** Quét ngưỡng (`APPROX_POLY_DP_ACCURACY_RATIO`, diện tích tối thiểu) trên tập
      vàng, chốt mặc định bằng số đo.
- [x] **S-6** Khi có 2 detector: **bất đồng giữa chúng = tín hiệu QC miễn phí** → cùng tứ giác
      thì tin cao; lệch nhau thì `warn` cho người soi.
- **Tiêu chí ra**: chọn detector mặc định bằng **bảng số đo**, không bằng cảm tính.

### Giai đoạn 4 — Ổn định, đóng gói, tiện dụng ✅ XONG
- [x] **DEP-1** Ghim version `requirements.txt` (nhất là `rembg`, `opencv-python`, `onnxruntime`).
- [x] **PKG-1** `python_requires` khớp thực tế (rembg/onnxruntime cần ≥3.9).
- [x] **PKG-2** `__version__` trong package, nguồn sự thật duy nhất cho `setup.py`.
- [x] **N-04** Dockerfile + pre-warm model rembg trong image (bỏ lần tải đầu chạy chậm).
- [x] **N-05** CI: cài sạch + chạy test + build wheel.
- [x] **N-01** Batch CLI (thư mục / glob — `glob` đã import sẵn mà chưa dùng) + **báo cáo QC
      tổng hợp** (CSV: file, verdict, reason, metric) — đây là dạng "QC" mà vận hành cần nhất.
- [x] **N-02** Tham số hóa qua CLI/env (ngưỡng, kích thước làm việc, bật/tắt rembg).
- [x] **N-06** Tái dùng `rembg` session giữa các call (server/batch) — đòn bẩy tốc độ chính.

### Giai đoạn 5 — Mở rộng ⏸ PHẦN LỚN ĐÃ CHUYỂN ĐI

> Sau đợt chốt 2026-08-05: **S-5 dewarping đã có câu trả lời (CÓ) và chuyển sang GĐ 6/7**.
> Phần còn lại vẫn chờ nhu cầu — riêng **PDF/đa trang chưa hỏi**, là câu duy nhất còn thiếu
> ngoài EX-9.
- [ ] Tách **nhiều tài liệu** trong một ảnh thành nhiều đầu ra (nối tiếp QC-9).
- [ ] Đầu vào PDF / đa trang.
- [x] ~~**S-5 Dewarping** — chờ chốt EX-5~~ → **đã chốt: CÓ cong**. Chuyển sang GĐ 6 (đo) và
      GĐ 7 (làm).
- [ ] Hậu xử lý làm nét/khử bóng (adaptive threshold, shadow removal) cho đầu ra "giống bản scan".
- [ ] onnxruntime-gpu tùy chọn.


### Giai đoạn 6 — Việc phát sinh từ đợt chốt yêu cầu khách (2026-08-05) 🎯 LÀM TIẾP

12/13 câu hỏi trong [need_exchange.md](need_exchange.md) đã có câu trả lời. Sáu việc dưới đây
sinh ra từ đó. **Tính đến 2026-08-05: QC-11/12/13/14 đã xong, S-5 đã đo và chốt là không làm,
N-11 bị bỏ theo yêu cầu. Chỉ còn OPS-3, và nó đợi máy server.**

- [x] **QC-11** ✅ `NO_CROP_DETECTED` (fail) — bắt ca detector trả nguyên khung hình.
      Dấu hiệu đã đo: `quad_area_ratio > 0.90` và `touches_border == 4` → đúng 2/17 ảnh, 0 báo
      động giả.
- [x] **QC-12** ✅ `CONTENT_CLIPPED` (fail) — dò pixel mực chạm mép cắt.
      [EX-1](need_exchange.md): mất viền trắng thì được, mất **chữ** thì không. Quan trọng nhất
      với hoá đơn — mất dòng tổng tiền là hỏng cả bản ghi.
- [x] **QC-13** ✅ Hint hai tầng (người chụp / vận hành).
      [EX-3](need_exchange.md): có cả ảnh kho lẫn ảnh chụp mới. Hint "chụp lại trên nền tối"
      vô dụng với ảnh kho — vi phạm chính nguyên tắc §3.4 bên dưới.
- [x] **QC-14** ✅ Cờ `pre_cropped` cho ảnh đã cắt sẵn. Khách xác nhận có gửi loại này
      (EX-14). Không tự đoán được — đo 37 ảnh, hai nhóm trùng dải `alpha_coverage`.
- ~~**N-11** Công cụ gán nhãn tập vàng~~ — **BỎ** theo yêu cầu khách 2026-08-05.
- [x] **S-5 (bước đo)** ✅ Đã đo độ vồng mép giấy trên 36 ảnh. Không ảnh nào vượt sàn nhiễu
      của mask (0.07, đo trên chính ảnh mẫu phẳng đã biết); 5 giá trị cao nhất đều là ảnh
      **tách nền sai**, không phải giấy cong. → **Không làm dewarping**, S-5 hạ P1 → P3.
      Tiết kiệm 1 tuần+. Mở lại khi có tập ảnh hoá đơn cuộn thật.
- [ ] **OPS-3 — LÀM CUỐI, TRÊN MÁY SERVER.** `docker build` + chạy thử service + kiểm ngắt mạng
      + thêm build image vào CI. **Máy phát triển hiện tại không build Docker** (chốt
      2026-08-05) nên việc này dời xuống cuối, làm khi lên máy triển khai.
      Hoãn **không** làm rủi ro nhỏ đi: [EX-13](need_exchange.md) chốt bàn giao là **Docker image
      có sẵn HTTP service**, mà image đó vẫn chưa có bằng chứng dựng được.
      ✅ **Phần không cần Docker đã xong**: [api.md](api.md) + 30 test hợp đồng. Còn lại đúng
      phần phải có Docker mới làm được.

**Tiêu chí ra**: ảnh crop sai không còn lọt xuống mức `warn`; mỗi mã lý do hành động được với
**cả hai** nhóm người dùng; hợp đồng API có tài liệu và có test giữ. *(Phần `docker run` được
của khách nằm ở OPS-3, kiểm trên máy server.)*

### Giai đoạn 7 — Chỉ chạy được khi có tập vàng (EX-2)

- [ ] **QUAL-3** Quét ngưỡng, tối ưu **tổng** false pass + false fail ([EX-7](need_exchange.md)
      chốt cân bằng, không ưu tiên một chiều như giả định cũ).
- [ ] **S-1** Chốt model nền bằng số (đã đo sơ bộ: isnet chậm gấp 3, đổi 2 verdict).
- [ ] **S-3** Thử DocAligner làm đường chính. *Không còn bắt buộc vì tốc độ* —
      [EX-10](need_exchange.md) chốt ngân sách <1s mà hiện đã đạt 0.4s — nhưng vẫn là ứng viên
      cho chất lượng, nhất là ca giấy trắng nền sáng mà rembg thua.
- [ ] **S-5 (bước làm)** Dewarping, nếu số đo ở Giai đoạn 6 cho thấy đáng.

---

## 7. Rủi ro & phụ thuộc

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|--------|-----------|------------|
| **False pass** (crop sai mà báo đạt) | dữ liệu bẩn trôi xuống OCR, phát hiện muộn | QC-5 metric + ngưỡng chặt; đo ma trận nhầm lẫn (Giai đoạn 3) |
| Reason code nở ra vô tội vạ, không ai hành động được | QC thành nhiễu | Nguyên tắc §3.4: mã nào cũng phải có hint + đối tượng nhận |
| `rembg` đổi API/model giữa các version | import gãy, chất lượng đổi thầm lặng | Ghim version (DEP-1); regression test trên `examples/` |
| Không có tập vàng của khách | không chứng minh được chất lượng lúc nghiệm thu | EX-1/EX-2 trong `need_exchange.md` |
| SSRF ở server nếu deploy public | đọc file nội bộ / metadata cloud | SEC-1: tắt GET-url hoặc allowlist |
| rembg tải model lần đầu (chậm/không mạng) | request đầu timeout, môi trường offline chết | Pre-warm trong Docker image (N-04) |
| Thư mục local không có `.git` | mất thay đổi, không rollback được | `git init` ngay ở Giai đoạn 0 |
| Sửa vendor `rembg` | lệch bản gốc, khó nâng cấp | Bọc ở `doc.py`, không sửa vendor |
| **Docker image chưa từng build thử** mà lại là thứ bàn giao | khách nhận về không chạy được | OPS-3 — làm trước tiên ở Giai đoạn 6 |
| **Giấy cong** (hoá đơn) — nắn phối cảnh không sửa được | cả một nhóm ảnh không bao giờ đạt, dù dò biên chuẩn | Đo tỉ lệ trước (GĐ 6), rồi mới quyết dewarping (S-5) |
| rembg tách nhầm **vật khác** (bàn trắng thay vì giấy trắng) | crop sai mà chỉ báo `warn` | QC-11 đưa ca này lên `fail`; dài hạn là S-3 |
| Hint viết cho người chụp, nhưng ảnh là ảnh kho | QC ra thông điệp không ai làm gì được | QC-13 hint hai tầng |

## 8. Tài liệu liên quan
- [algorithm.md](algorithm.md) — thuật toán từng bước + hợp đồng QC + danh mục mã lý do.
- [features_issues.md](features_issues.md) — sổ tính năng + issue (mã BUG-*/SEC-*/QC-*/QUAL-*/N-*).
- [test_eval.md](test_eval.md) — smoke test + cách eval chất lượng & phán quyết.
- [need_exchange.md](need_exchange.md) — câu hỏi cần làm rõ với khách hàng.
- [../README.md](../README.md) — giới thiệu & cách dùng.
