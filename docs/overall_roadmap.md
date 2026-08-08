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
Hợp đồng đầu ra QC đầy đủ: [algorithm.md §2](algorithm.md#hop-dong) ·
danh mục mã lý do: [algorithm.md §7](algorithm.md#ma-ly-do).

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

## 4. Hiện trạng

**Chạy được và đã bàn giao được**: lõi QC, ba mặt tiền (CLI, HTTP, batch), Docker image có sẵn
HTTP service, đầu vào/đầu ra PDF, chặn tải hai tầng. Đã build và chạy trên máy server 64 nhân.

| | |
|---|---|
| Hợp đồng đầu ra | `ScanResult{image, verdict, reasons[], metrics}`; **31 mã lý do**, mã nào cũng có `hint` + `audience`; bất biến `pass ⟺ reasons == []` ép ở mức code |
| Bộ đo | **451 test** + CI (lint · test 3.9/3.12 · build wheel). Bài quan trọng nhất: *không false pass* trên 9 ảnh hỏng dựng bằng OpenCV |
| Đã chạy trên ảnh thật | 8 ảnh mẫu + 30 ảnh khách (CCCD, sổ đỏ, hoá đơn, A4) → 13 pass · 13 warn · 12 fail |
| Tốc độ | ~0.58s/ảnh; **8.4 ảnh/s** một tiến trình trên máy 64 nhân |

**Thứ chặn nhiều nhất vẫn là tập vàng có nhãn của khách** ([EX-2](need_exchange.md)). Không có
nó thì không chốt được ngưỡng (QUAL-3), không dám đổi model nền (S-1) hay detector (S-3), và
không báo cáo được crop rate / false pass / false fail lúc nghiệm thu. Công cụ đo đã sẵn và chạy
được — chỉ thiếu dữ liệu. 29 ảnh thật đang có **chưa có nhãn**, nên chỉ dùng để so hai cấu hình
với nhau, không dùng để chấm đúng/sai.

Bàn giao là **Docker image kèm HTTP service** ([EX-13](need_exchange.md)), nên
[api.md](api.md) là bề mặt bàn giao chính và có test hợp đồng giữ.


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

## 6. Roadmap

**Đã xong** — Giai đoạn 0 (chặn máu + dựng bộ đo) · 1 (verdict + reason + hint) · 2 (QC nâng cao,
tự khắc phục) · 4 (ổn định, đóng gói) · 6 (việc phát sinh từ đợt chốt yêu cầu khách). Chi tiết ở
lịch sử commit; những gì còn hiệu lực nằm trong
[features_issues.md](features_issues.md).

### Giai đoạn 3 — Chất lượng phát hiện biên 🎯 CHẶN Ở TẬP VÀNG

Phần không cần nhãn đã làm: lọc tứ giác, hằng số suy theo ảnh, tách interface `Detector`, đối
chiếu chéo hai detector, bộ eval.

- [ ] **QUAL-3** quét ngưỡng — tối ưu **tổng** false pass + false fail
      ([EX-7](need_exchange.md#ex-7) chốt cân bằng, không siết một chiều).
- [ ] **S-1** chốt model nền bằng số (đã đo sơ bộ: isnet chậm gấp 3, đổi 2 verdict).
- [ ] **S-3** thử DocAligner làm đường chính. *Không còn bắt buộc vì tốc độ* —
      [EX-10](need_exchange.md) chốt ngân sách <1s mà hiện đã đạt — nhưng vẫn là ứng viên cho
      **chất lượng**, nhất là ca giấy trắng nền sáng mà rembg thua.
- [ ] **QUAL-4** vùng đệm cho ngưỡng `no_crop_area_ratio`.

### Còn lại, không chờ tập vàng

- [ ] **OPS-3** — gọi qua LAN từ máy khác · chạy khi ngắt mạng · build image trong CI ·
      bật lại `read_only`. Xem [features_issues.md](features_issues.md#ops-docker-unverified).

### Chờ nhu cầu khách

- [ ] Tách **nhiều tài liệu** trong một ảnh thành nhiều đầu ra (nối tiếp QC-9).
- [ ] Hậu xử lý làm nét / khử bóng cho đầu ra "giống bản scan".
- [ ] Hàng đợi bất đồng bộ + `job_id` — **chỉ khi** [EX-16](need_exchange.md#ex-throughput) cho
      thấy cần. Đo được: một tiến trình 8.4 ảnh/s, kịch bản 700 CCU nặng nhất cần 9 container
      gọn trong một máy, nên hiện **chưa cần**.

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
