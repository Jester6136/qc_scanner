# qc_scanner — Tổng quan dự án & Roadmap

> Thay cho "project-insight". Đây là **điểm vào** cho người mới: dự án là gì, đang ở đâu,
> đi về đâu. Chi tiết kỹ thuật ở `algorithm.md`; việc cần làm ở `features_issues.md`;
> cách kiểm ở `test_eval.md`; việc cần hỏi khách ở `need_exchange.md`.

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
- Quy mô code: **164 dòng Python**, 3 file. Cực nhỏ — đọc hết trong 10 phút.
- Kỹ thuật: **KHÔNG có model riêng của dự án**. `rembg` (U²-Net qua onnxruntime) tách nền,
  phần còn lại là OpenCV thuần (contour + approxPolyDP + four-point transform).

## 2. Kiến trúc (một đoạn)

Ba mặt tiền chung **một** hàm lõi `scan(bytes) -> bytes`:

```
CLI  (qc-scanner)          ─┐
Server (qc-scanner-server) ─┼──►  qc_scanner.doc.scan()  ──►  rembg → OpenCV contour → warp → PNG
Library (import scan)   ─┘
```

Không state, không DB, không hàng đợi, không config file. Mọi tham số **hardcode**
(`APPROX_POLY_DP_ACCURACY_RATIO=0.02`, `IMG_RESIZE_H=500`, medianBlur ksize 15).

Kiến trúc đích (theo hướng QC) tách lõi thành hai lớp, mặt tiền giữ nguyên:

```
scan(bytes) -> bytes                  # API cũ, giữ để không phá người dùng hiện tại
scan_qc(bytes) -> ScanResult          # API mới: ảnh + verdict + reasons[] + metrics + hints
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

## 4. Hiện trạng (2026-08)

- Luồng lõi **chạy được**; có 8 cặp ảnh mẫu input/output trong [examples/](../examples/).
- **Chưa có gì của QC**: `scan()` trả `bytes` hoặc `None`; không verdict, không reason code,
  không metric, không hint. Toàn bộ mục §1 ở trên là **việc phải làm**, chưa phải hiện trạng.
- **Chất lượng chưa được đo lần nào**: không test, không CI, không tập vàng có nhãn 4 góc.
  Không biết tỉ lệ phát hiện biên đúng là bao nhiêu.
- **Lỗi chặn ở đường CLI**: `rembg` bị gọi **hai lần** → chậm gấp đôi, mask sai.
  [BUG-1](features_issues.md#bug-double-rembg).
- **Nuốt lỗi**: `scan()` bắt mọi exception, in stderr, trả `None` → CLI ghi `None` (crash),
  server trả 500 "oops, something went wrong!". Đây chính là phản-QC.
  [BUG-2](features_issues.md#bug-swallow).
- **Lỗ hổng SSRF** ở HTTP server (`GET /?url=` fetch URL bất kỳ, kể cả `file://` và metadata
  nội bộ). [SEC-1](features_issues.md#sec-ssrf).
- **Dependency không ghim version nào** → build hôm nay và tháng sau có thể khác nhau.
- Thư mục local **không phải git repo** (`.git` không tồn tại) → thay đổi chưa được version
  control. Cần `git init` / clone lại từ remote trước khi sửa.

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

### Giai đoạn 0 — Chặn máu & dựng bộ đo (1–2 ngày) 🎯 ĐANG TỚI
- [ ] `git init` + commit hiện trạng trước khi sửa bất cứ thứ gì.
- [ ] **BUG-1** Bỏ `rembg` gọi hai lần ở CLI.
- [ ] **BUG-2** Thay "nuốt lỗi trả None" bằng lỗi có mã — nền móng của QC.
- [ ] **SEC-1** Tắt/allowlist `GET /?url=` ở server.
- [ ] Regression test trên 8 cặp trong `examples/` — [test_eval.md §2](test_eval.md).
- **Tiêu chí ra**: `pytest` xanh trên máy sạch; CLI lỗi thì exit code ≠ 0 kèm mã lý do.

### Giai đoạn 1 — Lõi QC: verdict + reason + hint (TRỌNG TÂM)
- [ ] **QC-1** Kiểu `ScanResult{image, verdict, reasons[], metrics, hints[]}` + `scan_qc()`.
      Giữ `scan()` cũ làm lớp mỏng bọc ngoài (tương thích ngược).
- [ ] **QC-2** Cài **danh mục mã lý do** giai đoạn 1: `DECODE_FAILED`, `SUBJECT_NOT_FOUND`,
      `QUAD_NOT_FOUND`, `TOO_SMALL`, `CLIPPED_EDGE`, `NOT_CONVEX`, `EXTREME_SKEW`.
      — [algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes)
- [ ] **QC-3** Mỗi mã kèm `hint` tiếng Việt + đối tượng nhận (người chụp / vận hành / hệ thống).
- [ ] **QC-4** Bề mặt hóa QC ra cả 3 mặt tiền:
      CLI → exit code theo verdict + JSON ra stderr/`--report`;
      server → header/`multipart` hoặc `?format=json` trả cả ảnh lẫn phán quyết;
      library → trả `ScanResult`.
- [ ] **QC-5** Metric đo được kèm theo: `quad_area_ratio`, `skew_ratio`, `est_dpi`,
      `blur_score` (variance of Laplacian), `contour_candidates`.
- **Tiêu chí ra**: mọi ảnh trong tập thử ra đúng 1 verdict + ≥1 reason khi không phải `pass`;
  không còn đường nào trả `None`.

### Giai đoạn 2 — QC nâng cao & tự khắc phục ("hơn cả thế")
- [ ] **QC-6** Kiểm chất lượng ảnh (không chỉ hình học): `BLURRY`, `GLARE`, `TOO_DARK`,
      `LOW_RESOLUTION` — chặn ảnh mà OCR chắc chắn đọc sai.
- [ ] **QC-7** **Fallback dò cạnh** khi rembg không tách được chủ thể (giấy trắng trên nền
      trắng): Canny + HoughLines + giao điểm → tứ giác. Thành công thì hạ `fail` → `warn`
      kèm reason `RECOVERED_BY_EDGE_FALLBACK`.
- [ ] **QC-8** Tự sửa nhẹ: nới biên vài pixel khi tứ giác chạm mép, tự xoay về chiều đứng.
- [ ] **QC-9** `MULTIPLE_DOCUMENTS` — phát hiện nhiều tứ giác lớn (nhiều tờ trong một khung),
      báo rõ thay vì lặng lẽ lấy tờ to nhất.
- [ ] **QC-10** Chế độ debug: xuất ảnh trung gian (mask, contour vẽ chồng, tứ giác chọn) để
      soi ca sai — công cụ chính khi tinh chỉnh ngưỡng.
- **Tiêu chí ra**: false-pass giảm đo được; một phần ca `QUAD_NOT_FOUND` cũ chuyển thành
  `warn` nhờ fallback.

### Giai đoạn 3 — Chất lượng phát hiện biên & nâng cấp lõi thuật toán

Lõi hiện tại viết ~2019 (rembg/U²-Net + contour). Khảo sát công nghệ 2026 kết luận **có khoảng
cách đáng kể** so với hướng hiện đại (hồi quy 4 góc trực tiếp) —
[algorithm.md §8](algorithm.md#8-khảo-sát-lõi-thuật-toán-có-còn-hợp-thời-2026).
Thứ tự bắt buộc: **đo trước, đổi sau.**

- [ ] Gán nhãn 4 điểm góc cho tập ảnh thật của khách → **tập vàng** (`need_exchange.md` EX-2).
      Có thể dùng SAM/SAM2 hỗ trợ gán nhãn cho nhanh.
- [ ] Đo baseline: IoU tứ giác + crop rate + ma trận nhầm lẫn của verdict.
- [ ] **QUAL-1** Loại tứ giác rác: yêu cầu lồi (`isContourConvex`), diện tích ≥ X% ảnh, tỉ lệ
      cạnh hợp lý — thay vì "lấy tứ giác đầu tiên gặp". Giữ giá trị **dù đổi detector nào**.
- [ ] **QUAL-2** `medianBlur` / `IMG_RESIZE_H` scale theo kích thước ảnh thay vì hằng số.
- [ ] **S-1** Đổi model nền của rembg (`isnet-general-use`, rồi **BiRefNet**) — **một dòng**,
      rủi ro ~0, đo ngay bằng bộ eval. Việc rẻ nhất trong toàn bộ roadmap.
- [ ] **S-2** Tách interface `Detector` (trả 4 điểm + confidence) → 3 cài đặt: rembg-contour ·
      DocAligner · edge-Hough. Lõi QC không phụ thuộc detector.
- [ ] **S-3** ⭐ Thử **DocAligner** (Apache-2.0, ONNXRuntime — đã là dependency sẵn) làm đường
      chính: hồi quy thẳng 4 góc, **suy được góc bị che/ngoài khung**, có confidence tự nhiên
      nạp vào QC. Giữ pipeline cũ làm đối chứng; chốt bằng số đo trên tập vàng.
- [ ] **QUAL-3** Quét ngưỡng (`APPROX_POLY_DP_ACCURACY_RATIO`, diện tích tối thiểu) trên tập
      vàng, chốt mặc định bằng số đo.
- [ ] **S-6** Khi có 2 detector: **bất đồng giữa chúng = tín hiệu QC miễn phí** → cùng tứ giác
      thì tin cao; lệch nhau thì `warn` cho người soi.
- **Tiêu chí ra**: chọn detector mặc định bằng **bảng số đo**, không bằng cảm tính.

### Giai đoạn 4 — Ổn định, đóng gói, tiện dụng
- [ ] **DEP-1** Ghim version `requirements.txt` (nhất là `rembg`, `opencv-python`, `onnxruntime`).
- [ ] **PKG-1** `python_requires` khớp thực tế (rembg/onnxruntime cần ≥3.9).
- [ ] **PKG-2** `__version__` trong package, nguồn sự thật duy nhất cho `setup.py`.
- [ ] **N-04** Dockerfile + pre-warm model rembg trong image (bỏ lần tải đầu chạy chậm).
- [ ] **N-05** CI: cài sạch + chạy test + build wheel.
- [ ] **N-01** Batch CLI (thư mục / glob — `glob` đã import sẵn mà chưa dùng) + **báo cáo QC
      tổng hợp** (CSV: file, verdict, reason, metric) — đây là dạng "QC" mà vận hành cần nhất.
- [ ] **N-02** Tham số hóa qua CLI/env (ngưỡng, kích thước làm việc, bật/tắt rembg).
- [ ] **N-06** Tái dùng `rembg` session giữa các call (server/batch) — đòn bẩy tốc độ chính.

### Giai đoạn 5 — Mở rộng (chờ chốt nhu cầu với khách)
- [ ] Tách **nhiều tài liệu** trong một ảnh thành nhiều đầu ra (nối tiếp QC-9).
- [ ] Đầu vào PDF / đa trang.
- [ ] **S-5 Dewarping** (UVDoc / DocTr++ / DocRes) — nắn cả giấy **cong/gập**, không chỉ phối
      cảnh phẳng. Chỉ làm nếu khảo sát ảnh khách thấy biến dạng cong đáng kể → chốt qua
      [EX-5](need_exchange.md). Đắt và phức tạp: **không nhảy thẳng lên đây.**
- [ ] Hậu xử lý làm nét/khử bóng (adaptive threshold, shadow removal) cho đầu ra "giống bản scan".
- [ ] onnxruntime-gpu tùy chọn.

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

## 8. Tài liệu liên quan
- [algorithm.md](algorithm.md) — thuật toán từng bước + hợp đồng QC + danh mục mã lý do.
- [features_issues.md](features_issues.md) — sổ tính năng + issue (mã BUG-*/SEC-*/QC-*/QUAL-*/N-*).
- [test_eval.md](test_eval.md) — smoke test + cách eval chất lượng & phán quyết.
- [need_exchange.md](need_exchange.md) — câu hỏi cần làm rõ với khách hàng.
- [../README.md](../README.md) — giới thiệu & cách dùng.
