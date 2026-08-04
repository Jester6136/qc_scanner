# Features & Issues — qc_scanner

> Sổ đăng ký **tính năng + vấn đề** của dự án. Mỗi mục có: mã, mức ưu tiên, trạng thái,
> mô tả, bằng chứng (`path:line`), và hướng xử lý. Cập nhật khi raise/đóng.
>
> Ưu tiên: **P0** chặn/đắt nghiêm trọng · **P1** đáng làm sớm · **P2** cải thiện · **P3** nice-to-have.
> Trạng thái: 🔴 mở · 🟡 đang làm · 🟢 xong · ⚪ backlog.
>
> Bối cảnh: mục tiêu dự án là biến qc_scanner thành **cổng QC** — không crop được thì phải nói rõ
> nguyên nhân + hướng xử lý. Xem [overall_roadmap.md §1](overall_roadmap.md).

---

## Tình trạng (cập nhật 2026-08-05)

**Đã đóng**: BUG-1/2/3/4 · SEC-1 · OPS-1/2 · QC-1/2/3/4/5/6/7/8/9/10 · QUAL-1/2 · S-2/S-6 ·
DEP-1 · PKG-1/2/3/4 · N-01/02/04/05/06 — cùng **vấn đề gốc** ở đầu file.

**Mở thêm sau đợt chốt yêu cầu khách 2026-08-05** (xem §A2): OPS-3 · QC-11 · QC-12 · QC-13 ·
N-11, và S-5 nâng từ P3 lên P1. Năm mục đầu **làm được ngay, không chờ gì**.

**Còn mở, và lý do**:

| Mã | Vì sao chưa làm |
|---|---|
| QUAL-3 quét ngưỡng | Cần tập vàng có nhãn của khách (EX-2). Bộ eval đã chạy được, chỉ thiếu dữ liệu. |
| S-1 đổi model nền | **Đã đo** (xem mục S-1). isnet chậm gấp 3 và đổi 2 verdict; không có nhãn thì không biết đổi là tốt hay tệ. |
| S-3 DocAligner | Chỗ cắm đã sẵn (S-2). Nguyên tắc "đo trước, đổi sau" cấm đổi đường chính khi chưa có tập vàng. |
| S-5 dewarping | Chờ chốt EX-5: ảnh khách có giấy cong/gập không. Làm thừa thì đắt vô ích. |
| N-03/07/08/09/10 | Chờ nhu cầu khách (EX-3/EX-5/EX-10). |

Mọi **ngưỡng** trong `config.py` vẫn là ước đoán, trừ hai cái đã chốt bằng số đo (cạnh dài
tối thiểu, ngưỡng mờ) — xem [algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes).

---

## A. ISSUES — Chặn mục tiêu QC (làm trước)

### 🎯 VẤN ĐỀ GỐC (🟢 ĐÃ GIẢI QUYẾT): qc_scanner KHÔNG nói được vì sao {#root-no-qc}

Toàn bộ đầu ra của `scan()` là `bytes` hoặc `None`. Ba nhánh dưới đây **không phân biệt được
từ bên ngoài**:

| Chuyện thật sự xảy ra | Caller nhận được |
|---|---|
| Nắn đúng biên, ảnh sạch | `bytes` |
| **Không tìm được tứ giác → trả ảnh GỐC chưa nắn** — [doc.py:59-60](../src/qc_scanner/doc.py#L59-L60) | `bytes` (giống hệt trên!) |
| Bất kỳ exception nào | `None` + một dòng stderr |

Nhánh giữa là **nguồn *false pass*** — ảnh chưa nắn trôi thẳng xuống OCR, không ai biết cho
tới lúc kết quả sai. Nhánh cuối xóa sạch nguyên nhân: người vận hành chỉ thấy "oops".

Đây không phải một bug lẻ mà là **thiếu hợp đồng đầu ra**. Lời giải là QC-1…QC-5 bên dưới,
theo hợp đồng ở [algorithm.md §2](algorithm.md#2--hợp-đồng-đầu-ra-qc).

**✅ Đã giải quyết**: `scan_qc()` trả `ScanResult{image, verdict, reasons[], metrics}`. Ba
nhánh trên nay phân biệt được từ bên ngoài:

| Chuyện thật sự xảy ra | Caller nhận được |
|---|---|
| Nắn đúng biên, ảnh sạch | `verdict="pass"`, `reasons=[]` |
| Không tìm được tứ giác → trả ảnh gốc | `verdict="fail"`, `reasons=[QUAD_NOT_FOUND, FALLBACK_ORIGINAL]`, `metrics.fallback_used="original"` |
| Đầu vào không đánh giá được | `ScanError` có mã + hint + audience |

Bất biến `verdict=="pass"` ⟺ `reasons==[]` được ép trong `ScanResult.__post_init__`, không
phải chỉ là quy ước viết trong tài liệu.

---

### 🐞 BUG-1 · P0 · 🟢 ĐÃ SỬA · `rembg` chạy HAI LẦN ở đường CLI {#bug-double-rembg}

CLI gọi `rembg.remove(input.read())` rồi truyền kết quả vào `scan()` —
[cmd/cli.py:21](../src/qc_scanner/cmd/cli.py#L21) — nhưng `scan()` mở đầu bằng `rembg(data)` lần
nữa — [doc.py:17](../src/qc_scanner/doc.py#L17).

**Hậu quả**: (a) thời gian xử lý **gấp đôi** ở chặng chiếm ~95% tổng thời gian; (b) lần hai
chạy trên PNG đã trong suốt, mask alpha sinh ra từ một ảnh đã bị tách nền → biên có thể sai
lệch so với đường library/server (vốn chỉ gọi 1 lần). Ba mặt tiền **không cho cùng kết quả**
trên cùng một ảnh — điều này làm mọi phép đo chất lượng vô nghĩa.

**Hướng**: bỏ `rembg.remove()` ở CLI (giữ rembg **bên trong** `scan()` là đúng chỗ — một lõi
duy nhất). Xóa luôn import `rembg` thừa ở CLI. Test hồi quy: CLI và library phải ra **byte
giống hệt nhau** trên cùng input.

**✅ Đã làm**: bỏ lời gọi ở CLI; rembg chỉ còn trong `doc._segment()`. Chốt bằng hai test —
`test_surfaces.py::test_rembg_runs_once_per_scan` (đếm lời gọi) và ba bài so byte giữa
library / CLI file / CLI pipe / server.

---

### 🐞 BUG-2 · P0 · 🟢 ĐÃ SỬA · `scan()` nuốt mọi exception, trả `None` {#bug-swallow}

[doc.py:69-71](../src/qc_scanner/doc.py#L69-L71) bắt `Exception` trần, in stderr, `return None`.

**Hậu quả dây chuyền**:
- CLI: `output.write(None)` → `TypeError` khó hiểu, và **exit code vẫn có thể là 0** ở một số
  đường → script gọi qc_scanner tưởng đã thành công. — [cli.py:21](../src/qc_scanner/cmd/cli.py#L21)
- Server: `BytesIO(None)` → `TypeError` → rơi vào `except` → **500 "oops, something went
  wrong!"** — [server.py:35-41](../src/qc_scanner/cmd/server.py#L35-L41). Nguyên nhân thật
  (ảnh không có alpha? decode hỏng?) bị nuốt.
- Nội dung lỗi chỉ ra **stderr của process** — không vào được log có cấu trúc, không tra được.

Đây là **phản đề trực tiếp** của mục tiêu QC. Phải sửa trước khi làm bất cứ gì khác.

**Hướng**: định nghĩa `ScanError(code, message, hint)`; các nhánh lỗi raise mã tương ứng
(`DECODE_FAILED`, `SUBJECT_NOT_FOUND`…). Bỏ `except Exception` trần — chỉ bắt ở **biên** (CLI
main, Flask handler) và ở đó dịch mã → exit code / HTTP status + JSON body.

**✅ Đã làm**: `ScanError` trong `qc.py` dựng trên danh mục `REASONS`, nên mọi lỗi tự động có
hint + audience. `except Exception` trần đã biến mất khỏi lõi; chỉ CLI `main()` và Flask
handler bắt, rồi dịch sang exit code 3 / HTTP 400.

**Phát hiện thêm khi kiểm**: mô tả cũ nói server trả 500 với ảnh hỏng. Thực tế nó trả
**200 OK + PNG rỗng 0 byte** — `BytesIO(None)` là hợp lệ nên `send_file` không ném gì. Đây là
hỏng âm thầm, **tệ hơn 500**: caller nhận HTTP thành công với file rỗng.

---

### 🧱 QC-1 · P0 · 🟢 XONG · Chưa có kiểu `ScanResult` (verdict + reasons + metrics) {#qc-contract}

Nền móng cho tất cả các mục QC còn lại. Thêm `scan_qc(data) -> ScanResult` theo hợp đồng ở
[algorithm.md §2](algorithm.md#2--hợp-đồng-đầu-ra-qc); giữ `scan()` cũ làm lớp bọc mỏng
(`return scan_qc(data).image`) để **không phá người dùng PyPI hiện tại**.

Bất biến bắt buộc: `verdict == "pass"` ⟺ `reasons == []`.

---

### 🧱 QC-2 · P0 · 🟢 XONG · Cài danh mục mã lý do giai đoạn 1 {#qc-codes}

Bảy mã đầu tiên, đủ để xóa mọi nhánh im lặng hiện có: `DECODE_FAILED`, `SUBJECT_NOT_FOUND`,
`QUAD_NOT_FOUND`, `TOO_SMALL`, `CLIPPED_EDGE`, `NOT_CONVEX`, `EXTREME_SKEW`.
Định nghĩa đầy đủ (điều kiện, severity, hint, audience):
[algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes).

**Nguyên tắc không thương lượng**: mã nào cũng phải có `hint` (làm gì tiếp theo) và
`audience` (ai phải làm). Mã không hành động được là mã vô dụng.

---

### 🧱 QC-3 · P1 · 🟢 XONG · Metric đo được đi kèm mọi kết quả {#qc-metrics}

`quad_area_ratio`, `contour_candidates`, `skew_ratio`, `is_convex`, `touches_border`,
`est_dpi`, `blur_score`, `alpha_coverage`, `fallback_used`.

Không có metric thì không chốt được ngưỡng bằng số đo — chỉ đoán. Đây cũng là dữ liệu để
tinh chỉnh ngưỡng trên tập vàng (Giai đoạn 3) và để dựng báo cáo QC hàng loạt (N-01).

---

### 🧱 QC-4 · P1 · 🟢 XONG · Bề mặt hóa QC ra cả 3 mặt tiền {#qc-surface}

- **CLI**: exit code theo verdict (0 pass · 1 warn · 2 fail) + báo cáo JSON ra stderr hoặc
  `--report out.json`. Ảnh vẫn ra stdout (không phá pipe hiện tại).
- **Server**: mặc định trả PNG + header `X-QC-Scanner-Verdict` / `X-QC-Scanner-Reasons`;
  `?format=json` trả `ScanResult` đầy đủ. HTTP status: 200 pass/warn, **422** fail, 400 input hỏng.
- **Library**: `scan_qc()` trả `ScanResult`.

---

### 🧱 QC-7 · P1 · 🟢 XONG · Fallback dò cạnh khi rembg thua {#qc-edge-fallback}

Ca hay gặp nhất: **giấy trắng trên nền sáng** → rembg không tách được (`alpha_coverage` gần 0
hoặc gần 1). Thay vì fail ngay, chạy Canny + HoughLinesP → giao điểm → tứ giác ứng viên;
qua được bộ lọc thì dùng, hạ verdict xuống `warn` kèm `RECOVERED_BY_EDGE_FALLBACK`.
Thuật toán: [algorithm.md §6](algorithm.md#6--fallback-dò-cạnh-khi-rembg-thất-bại).

Đây là mức "hơn cả thế" của mục tiêu QC: **tự khắc phục trước, rồi mới báo** — nhưng không
bao giờ giấu việc đã phải dùng đường lui.

---

### 🧱 QC-9 · P2 · 🟢 XONG · Nhiều tài liệu trong một ảnh bị âm thầm bỏ qua {#qc-multi}

Vòng lặp [doc.py:48-56](../src/qc_scanner/doc.py#L48-L56) `break` ngay ở tứ giác đầu tiên. Chụp
2 tờ trong một khung → tờ thứ hai **biến mất không dấu vết**.

**Hướng**: đếm contour có diện tích ≥ 5% ảnh (`contour_candidates`); ≥2 → reason
`MULTIPLE_DOCUMENTS` (warn). Về sau có thể trả **nhiều** ảnh đầu ra (Giai đoạn 5).

---

---

## A2. ISSUES — Phát sinh từ đợt chốt yêu cầu khách 2026-08-05

> Sáu mục dưới đây **không có trong sổ cũ**; chúng sinh ra từ các quyết định ở
> [need_exchange.md](need_exchange.md). Thứ tự trong bảng là thứ tự đề nghị làm.

| # | Mã | Công | Chặn ở đâu |
|---|---|---|---|
| 1 | [OPS-3](#ops-docker-unverified) | ~nửa ngày | không |
| 2 | [QC-11](#qc-no-crop) | ~30 phút | không |
| 3 | [QC-12](#qc-content-clipped) | ~nửa ngày | không |
| 4 | [QC-13](#qc-two-tier-hint) | ~nửa ngày | không |
| 5 | [N-11](#n-label-tool) | ~1 ngày | không (dựng trước, chờ ảnh) |
| 6 | [S-5](#s-dewarp) đo độ cong | ~2h đo | cần ảnh EX-2 |

---

### 🔴 OPS-3 · P0 · 🔴 · Dockerfile CHƯA BUILD THỬ LẦN NÀO {#ops-docker-unverified}

[Dockerfile](../Dockerfile) được viết ở Giai đoạn 4 nhưng **chưa chạy `docker build` lần nào**
— không có bằng chứng nào là nó dựng được, càng không có bằng chứng service bên trong chạy được.

Sau [EX-13](need_exchange.md), image này **chính là thứ bàn giao cho khách**, kèm HTTP service
để hệ khác gọi vào. Một artefact chưa từng được kiểm mà lại là bề mặt bàn giao chính là rủi ro
lớn nhất hiện tại của dự án.

**Hướng**: (1) `docker build` thật, sửa tới khi qua; (2) `docker run` rồi gọi thử `POST /`,
`?format=json`, ca hỏng, `/healthz`; (3) kiểm model đã nướng sẵn bằng cách chạy image **ngắt
mạng**; (4) viết **tài liệu API** (endpoint, status code theo verdict, header, schema JSON);
(5) thêm **test hợp đồng API** để thay đổi schema làm gãy test chứ không gãy tích hợp của khách;
(6) thêm bước build image vào CI.

---

### 🧱 QC-11 · P0 · 🔴 · `NO_CROP_DETECTED` — bắt ca "không crop được gì mà vẫn báo warn" {#qc-no-crop}

Ảnh `abc1b13d82af03f15abe.jpg`: rembg tách **cái bàn trắng** thay vì tờ hoá đơn trắng đặt trên
nó. Tứ giác "tài liệu" thành ra gần trọn khung, một góc ở toạ độ **x = −105**, `approxPolyDP`
không ra nổi 4 đỉnh nên phải ép `minAreaRect` (`confidence 0.6`). Ảnh ra gần như ảnh vào.

Verdict hiện tại: **`warn`**. Theo [EX-8](need_exchange.md) thì `warn` vào hàng chờ người soi,
nên ca này chưa lọt hẳn — nhưng nó bị xếp cùng nhóm với những cảnh báo lành tính, và bản chất
nó là *hệ thống không làm được gì cả*, không phải *làm được nhưng có rủi ro*.

**Dấu hiệu nhận biết đã đo**: `quad_area_ratio > 0.90` **và** `touches_border == 4`. Chạy trên
17 ảnh (8 mẫu + 9 ảnh thật): đánh dấu đúng **2 ảnh**, cả hai đều thật sự không được crop
(`abc1b13…` và `40b9f8b0…` — ảnh sau ra 1264×957 từ 1280×960). **0 báo động giả** trên 15 ảnh
còn lại.

**Hướng**: thêm mã `NO_CROP_DETECTED` severity `fail`, hint hai tầng (người chụp: "đặt tài liệu
lên nền tương phản rồi chụp lại"; vận hành: "detector không tách được tài liệu, cần xử lý tay").
Kèm ca test dựng bằng ảnh giấy trắng trên nền trắng.

---

### 🧱 QC-12 · P0 · 🔴 · `CONTENT_CLIPPED` — mất viền thì được, mất CHỮ thì không {#qc-content-clipped}

[EX-1](need_exchange.md) chốt tiêu chí "đạt" nằm ở **nội dung**, không ở hình học: mất viền
trắng chấp nhận được, mất chữ thì không.

`CLIPPED_EDGE` hiện chỉ đếm số góc chạm mép ảnh — nó **không biết** chỗ bị cắt có chữ hay chỉ
có viền trắng. Vì thế nó vừa báo thừa (ảnh chỉ mất viền vẫn bị `warn`, đúng 5/17 ảnh đã thử),
vừa báo thiếu (ảnh mất hẳn một dòng chữ vẫn chỉ `warn`, không `fail`).

**Hướng**: sau khi nắn, dò pixel mực (nhị phân hoá thích nghi) trong dải sát bốn biên; có mực
chạm biên → `CONTENT_CLIPPED` severity `fail`. Bề rộng dải và ngưỡng mật độ mực phải chốt bằng
số đo trên tập vàng. `CLIPPED_EDGE` giữ nguyên mức `warn` cho ca chỉ mất viền.

⚠️ Với hoá đơn thì mã này quan trọng nhất: mất dòng tổng tiền là hỏng cả bản ghi.

---

### 🧱 QC-13 · P1 · 🔴 · Hint hai tầng: người chụp / vận hành {#qc-two-tier-hint}

[EX-3](need_exchange.md) chốt **cả hai luồng**: batch cho kho ảnh cũ (không ai chụp lại được)
và realtime cho ảnh chụp mới (chụp lại được ngay).

Hiện mỗi `Reason` chỉ có **một** `hint` và **một** `audience`. Với ảnh kho, hint kiểu "đặt tài
liệu lên nền tối rồi chụp lại" là **vô dụng** — không ai chụp lại được. Đúng thứ
[nguyên tắc §3.4 roadmap](overall_roadmap.md) cấm: thông điệp không hành động được.

**Hướng**: mỗi mã có `hints: {capturer: ..., operator: ...}`; luồng gọi khai báo bối cảnh
(realtime hay batch) và chỉ nhận hint hợp với mình. Test hợp đồng phải đòi **cả hai** tầng có
nội dung, không chỉ một.

---

### 📦 N-11 · P1 · 🔴 · Công cụ hỗ trợ gán nhãn tập vàng {#n-label-tool}

[EX-2](need_exchange.md) chốt: **khách cấp ảnh, bên làm gán nhãn, khách duyệt**. Nghĩa là công
việc gán nhãn ~100 ảnh rơi về phía mình, và cần công cụ chứ không gán tay từng toạ độ.

**Hướng**: (1) nạp sẵn tứ giác qc_scanner đoán được làm điểm khởi đầu — phần lớn ảnh chỉ cần
sửa nhẹ thay vì click từ đầu; (2) sửa 4 góc bằng chuột, xuất JSONL đúng format
[test_eval.md §5](test_eval.md); (3) gắn verdict + reason kỳ vọng; (4) xuất bản đối chiếu để
khách duyệt. Có thể dùng SAM/SAM2 hỗ trợ nếu gán tay quá chậm.

Dựng **trước** khi ảnh về — để ảnh về là gán được ngay, không mất thêm một vòng chờ.


## B. ISSUES — Bảo mật & đúng đắn {#b-issues--bảo-mật--đúng-đắn}

### 🔒 SEC-1 · P0 · 🟢 ĐÃ SỬA · SSRF + đọc file nội bộ qua `GET /?url=` {#sec-ssrf}

[server.py:25-29](../src/qc_scanner/cmd/server.py#L25-L29) gọi `urlopen(unquote_plus(url))` với
URL **do người dùng cung cấp**, không allowlist, không kiểm scheme, không timeout, không giới
hạn kích thước.

**Khai thác được ngay** nếu server lộ ra ngoài:
- `?url=file:///etc/passwd` → `urlopen` hỗ trợ scheme `file://` → **đọc file cục bộ**.
- `?url=http://169.254.169.254/...` → metadata cloud (credential IAM).
- `?url=http://<host-nội-bộ>:port/` → quét mạng nội bộ, dùng server làm proxy.
- URL trỏ file khổng lồ / stream vô tận → cạn RAM (`.read()` không giới hạn).

**Hướng** (theo thứ tự ưu tiên): (1) **bỏ hẳn** nhánh GET-url — POST file đã đủ cho mọi ca
dùng thật; (2) nếu buộc phải giữ: allowlist scheme `http/https` + allowlist host + chặn dải
IP private/link-local (giải DNS rồi kiểm IP, chống DNS rebinding) + `timeout` + đọc có
`Content-Length`/giới hạn byte. Mặc định **tắt**, bật bằng cờ.

**✅ Đã làm**: chọn phương án (1) — bỏ hẳn nhánh GET-url. `GET /` nay trả 405, có test chốt
(`test_failures.py::test_server_url_fetch_endpoint_is_gone`). Kèm `MAX_CONTENT_LENGTH` 32MB
và đổi bind mặc định `0.0.0.0` → `127.0.0.1`: server vẫn **không có xác thực**, nên mặc định
không nên nghe trên mọi interface. Docker vẫn bind `0.0.0.0` vì đó là trong network
namespace riêng, việc phơi ra ngoài do `-p` quyết định.

---

### 🐞 BUG-3 · P1 · 🟢 ĐÃ SỬA · So sánh `bytes` với `str` → file rỗng lọt qua {#bug-empty-check}

[server.py:31](../src/qc_scanner/cmd/server.py#L31): `if file_content == "":`. Nội dung file là
**`bytes`**, và `b"" == ""` luôn `False` trong Python 3 → **chốt chặn này không bao giờ kích
hoạt**. Upload file rỗng đi thẳng vào `scan()` → rembg/`imdecode` lỗi → 500 "oops".

**Hướng**: `if not file_content:` (bắt cả `b""` lẫn `""`), trả 400 kèm mã `FILE_EMPTY` + hint.

**✅ Đã làm**: chốt chặn chuyển vào `scan_qc()` (`if not data`) nên **cả ba mặt tiền** cùng
được bảo vệ, không chỉ server.

---

### 🐞 BUG-4 · P1 · 🟢 ĐÃ SỬA · `img.shape[2]` vỡ trên ảnh grayscale {#bug-shape}

[doc.py:33](../src/qc_scanner/doc.py#L33) truy cập `img.shape[2]` không kiểm `ndim`. Ảnh
grayscale sau `IMREAD_UNCHANGED` có `shape` 2 chiều → **`IndexError`** → bị BUG-2 nuốt →
"oops". Bình thường rembg luôn trả RGBA, nhưng khi rembg thất bại/đổi hành vi (hoặc do BUG-1
chạy hai lần) thì nhánh này phát nổ với thông báo vô nghĩa.

**Hướng**: kiểm `img.ndim == 3 and img.shape[2] == 4`; không đạt → reason `SUBJECT_NOT_FOUND`
(kèm hint đổi nền) thay vì `ValueError` chung chung. Thông báo hiện tại — "The image lacks an
alpha channel for background removal" — mô tả *triệu chứng kỹ thuật*, không nói người dùng
phải làm gì; đúng thứ QC-3 phải thay.

**✅ Đã làm**: `_alpha_mask()` trả `None` khi thiếu alpha, và lõi xử lý tiếp bằng
`SUBJECT_NOT_FOUND` — có hint "đặt lên nền tối, tương phản".

---

### ⚠️ OPS-1 · P2 · 🟢 XONG · Server không giới hạn kích thước upload, xử lý đồng bộ {#ops-server-limits}

Không `MAX_CONTENT_LENGTH`, không timeout. Mỗi request chạy rembg **đồng bộ** trong worker
thread của waitress (mặc định 4 thread) → 5 ảnh lớn cùng lúc là server treo. Request **đầu
tiên** còn cộng thời gian **tải model rembg** (vài chục MB) → dễ timeout ở tầng proxy.

**Hướng**: `app.config["MAX_CONTENT_LENGTH"]`; pre-warm model lúc khởi động (nạp sẵn session,
liên quan N-06); tài liệu hóa số thread; cân nhắc hàng đợi nếu cần chịu tải thật.

**✅ Đã làm**: `MAX_CONTENT_LENGTH` 32MB; server nạp model trước khi mở cổng (`--no-warmup`
để tắt); session rembg dùng chung giữa các request (N-06) nên request thứ hai trở đi không
nạp lại model. **Chưa làm**: hàng đợi — chỉ đáng làm khi biết tải thật (EX-10).

---

### ⚠️ OPS-2 · P2 · 🟢 XONG · Thư mục local không phải git repo {#ops-no-git}

`/Users/bags/prj/collab-prj/qc_scanner` **không có `.git`** — mọi thay đổi hiện không được version
control, không rollback được. Đợt đổi tên 2026-08 (`docscan` → `qc_scanner`, xoá `LICENSE.txt`
và `MANIFEST.in`) vì vậy **không có lịch sử để đối chiếu hay hoàn tác**.

**Hướng**: `git init` + commit hiện trạng **trước khi** sửa dòng code đầu tiên. Nếu cần đối
chiếu với bản gốc, upstream `danielgatis/docscan` vẫn còn trên GitHub.

**✅ Đã làm**: repo đã là git repo, hiện trạng ban đầu nằm ở commit `3811542` trước khi sửa
dòng code nào.

---

## C. ISSUES — Chất lượng thuật toán

### 🎯 QUAL-1 · P1 · 🟢 XONG · Lấy tứ giác ĐẦU TIÊN, không lọc rác {#qual-quad-filter}

[doc.py:48-56](../src/qc_scanner/doc.py#L48-L56) duyệt contour theo diện tích giảm dần và `break`
ở đa giác 4 đỉnh đầu tiên. **Không kiểm**: lồi, diện tích tối thiểu, tỉ lệ cạnh, có chạm mép ảnh
không. Một vệt nhiễu vuông vắn hoặc một ô trong bảng có thể thắng tờ giấy thật.

**Hướng**: duyệt hết ứng viên, cho điểm bằng bộ lọc — `isContourConvex`, `quad_area_ratio ≥ 0.2`,
`skew_ratio ≤ 1.8` — chọn ứng viên tốt nhất; không ứng viên nào đạt → `QUAD_NOT_FOUND` với
lý do cụ thể (bằng chính metric đã tính). Bộ lọc này **dùng chung** với QC-2/QC-3 — một lần
tính, vừa để chọn vừa để giải thích.

**✅ Đã làm**: `detect.best_candidate()` chấm điểm theo đúng bộ lọc đó. Contour không cho đúng
4 đỉnh nay ép về `minAreaRect` với confidence 0.6 thay vì bị bỏ qua. Ngưỡng vẫn là **ước
đoán** cho tới khi có tập vàng (QUAL-3).

---

### 🎯 QUAL-2 · P2 · 🟢 XONG · Hằng số cứng không scale theo ảnh {#qual-scale}

`IMG_RESIZE_H = 500.0` và `medianBlur(img, 15)` — [doc.py:11, 38](../src/qc_scanner/doc.py#L11).
Ảnh cao 300px bị **phóng to** lên 500 (bịa thông tin); ảnh 4000px bị thu 8× rồi blur ksize 15
có thể nuốt luôn góc giấy nhỏ. `APPROX_POLY_DP_ACCURACY_RATIO = 0.02` cũng chưa từng được
kiểm chứng bằng số đo.

**Hướng**: không upscale (`min(h, 500)`); ksize blur suy theo kích thước làm việc (lẻ, ~3% chiều
cao); quét ε trên tập vàng rồi mới chốt (QUAL-3 / Giai đoạn 3).

**✅ Đã làm**: cả hai. `_to_work_size()` không bao giờ phóng to; ksize = 3% chiều cao làm việc,
ép về số lẻ. ε vẫn 0.02 — chờ tập vàng để quét.

---

### 🔬 S-1 · P1 · 🟡 ĐÃ ĐO, CHƯA ĐỔI · Model nền của rembg đã cũ (U²-Net, mặc định) {#s-model-swap}

rembg mặc định dùng **U²-Net** — mô hình *salient object detection* đời 2020, huấn luyện cho
"vật thể nổi bật" nói chung, **không biết khái niệm tờ giấy**. rembg hiện đã hỗ trợ các model
tốt hơn (`isnet-general-use`, **BiRefNet**) — đổi bằng **một tham số `session`**, không đổi
kiến trúc, rủi ro gần bằng 0.

**Hướng**: sau khi có bộ eval ([test_eval.md §5](test_eval.md)), chạy so ba model trên cùng tập
vàng, chốt mặc định bằng số. Đây là **việc rẻ nhất trong toàn bộ roadmap** — làm trước S-3.
Khảo sát: [algorithm.md §8.1-B](algorithm.md#81-các-họ-phương-pháp-hiện-có).

**🟡 Đã đo, chưa đổi**. Đổi model nay là một tham số (`--model` / `QC_SCANNER_REMBG_MODEL`),
đúng như dự đoán là việc rẻ. Kết quả trên 9 ảnh thật trong `tmp/`:

| model | thời gian/ảnh (median) | verdict |
|---|---|---|
| `u2net` (mặc định) | **0.395s** | 6 pass · 3 warn |
| `isnet-general-use` | 1.198s | 4 pass · 5 warn |

isnet **chậm gấp 3** và đẩy 2 ảnh từ `pass` sang `warn` (`CLIPPED_EDGE`). Không có nhãn thì
không biết `CLIPPED_EDGE` đó **đúng** (isnet bắt biên sát hơn, phát hiện được tài liệu thật
sự chạm mép) hay **sai** — nên chưa đủ căn cứ đổi mặc định. Cần EX-2.

---

### 🔬 S-2 · P1 · 🟢 XONG · Chưa tách interface `Detector` — bị khoá vào một phương pháp {#s-detector-iface}

Việc dò biên hiện dính chặt vào `scan()`: rembg → contour → approxPolyDP, không thay được từng
mảnh. Muốn thử phương pháp khác phải viết lại hàm.

**Hướng**: `Detector.find_quad(img) -> QuadCandidate | None` (4 điểm + confidence + tên
detector); ba cài đặt: `rembg-contour` (hiện tại), `docaligner` (S-3), `edge-hough`
([QC-7](#qc-edge-fallback)). Lõi QC nhận `QuadCandidate` từ bất kỳ detector nào → **đổi
detector là đổi một dòng cấu hình**, và chạy được **hai detector song song trên cùng tập vàng**
để so bằng số thay vì cảm tính.

**✅ Đã làm**: `detect.py` có `Detector` + `QuadCandidate` và hai cài đặt (`rembg-contour`,
`edge-hough`), chọn bằng `--detector`. Chỗ cắm cho `docaligner` (S-3) là thêm một lớp và
đăng ký vào `DETECTORS` — không đụng lõi QC.

---

### 🔬 S-3 · P1 · ⚪ · ⭐ Hồi quy 4 góc trực tiếp (DocAligner) thay cho contour {#s-docaligner}

Hạn chế **cố hữu** của contour, không sửa được bằng tinh chỉnh: chỉ suy được góc **nhìn thấy
được** — góc bị tay che hoặc nằm ngoài khung là mất hẳn; và không sinh ra **confidence** nào để
QC dùng.

Hướng hiện đại (các app scanner thương mại đã chuyển sang): mô hình **xuất thẳng toạ độ 4 góc**.
Mã nguồn mở dùng được ngay: **[DocAligner](https://github.com/DocsaidLab/DocAligner)**
(Apache-2.0, `pip install docaligner-docsaid`, chạy **ONNXRuntime** — qc_scanner đã phụ thuộc
`onnxruntime` sẵn nên **không thêm runtime mới**).

**Vì sao hợp qc_scanner**: (a) suy được góc bị che/ngoài khung; (b) confidence tự nhiên → nạp
thẳng vào `metrics`/`verdict`; (c) thay được **cả** rembg lẫn contour → bỏ luôn chặng chiếm
~95% thời gian.

**Rủi ro**: mỗi ảnh một tài liệu (đa tài liệu cần bước khác); repo **không công bố benchmark**
→ bắt buộc tự đo trên ảnh khách. **Không đổi mặc định trước khi có tập vàng.**

---

### 🔬 S-6 · P2 · 🟢 XONG · Bất đồng giữa hai detector = tín hiệu QC miễn phí {#s-disagreement}

**✅ Đã làm**: `--cross-check` chạy detector thứ hai, tính IoU, IoU < 0.85 →
`DETECTOR_DISAGREEMENT` (warn). Mặc định tắt vì tốn thêm một lượt dò.

Khi có ≥2 detector (S-2): chúng cho **cùng** tứ giác → độ tin cậy cao; **lệch nhau** (IoU thấp)
→ reason `DETECTOR_DISAGREEMENT` (warn), cho người soi. Không cần model mới, không cần nhãn —
tận dụng thứ đã có. Chỉ làm sau khi S-2/S-3 xong.

---

### 🔬 S-5 · **P1** · 🔴 · Dewarping: nắn giấy CONG, không chỉ phối cảnh phẳng {#s-dewarp}

`four_point_transform` chỉ sửa được biến dạng **phẳng**. Giấy cong, gập nếp, sách đóng gáy →
sau khi nắn **vẫn méo**, dòng chữ vẫn cong → OCR vẫn sai. Họ phương pháp giải quyết: dự đoán
**lưới biến dạng** thay vì 4 điểm — UVDoc, DocTr++, DocRes, D²Dewarp/DocMatcher (2025).

**✅ Đã chốt qua [EX-5](need_exchange.md) — và câu trả lời là CÓ**: hoá đơn thường cong/nhăn.
Mục này chuyển từ P3 "chưa quyết" lên **P1, trong phạm vi**.

Hệ quả cần nói rõ: với nhóm ảnh hoá đơn cong, **dò biên chuẩn đến mấy cũng không đủ** — nắn
xong dòng chữ vẫn cong, OCR vẫn sai. Không có mục nào khác trong sổ này thay thế được nó.

**Nhưng đừng nhảy thẳng vào**: 1 tuần+, và chưa biết bao nhiêu phần trăm ảnh thật sự bị ảnh
hưởng. **Bước tiếp theo là ĐO**, không phải làm: trên tập ảnh EX-2, đo độ cong (độ lệch của
dòng chữ so với đường thẳng sau khi nắn) và đếm tỉ lệ ảnh vượt ngưỡng OCR chịu được. Có số rồi
mới quyết đáng hay không đáng.

---

### 🎯 QUAL-3 · P2 · ⚪ · Chưa quét ngưỡng trên tập vàng {#qual-sweep}

Mọi ngưỡng trong §7 algorithm (0.20 diện tích, 1.8 skew, ngưỡng glare/độ sáng) hiện là **ước
đoán**. Phải chốt bằng số đo trên tập vàng thật của khách — xem
[test_eval.md §5](test_eval.md) và `need_exchange.md` EX-2.

**Mục tiêu đã đổi theo [EX-7](need_exchange.md)**: khách muốn **cân bằng** false pass và false
fail, không phải ưu tiên chặn false pass. Nghĩa là quét ngưỡng phải tối ưu **tổng số lỗi**, chứ
không phải siết một chiều rồi khoe. Giả định cũ (false pass ≤1% / false fail ≤10%) **không còn
đúng** — cần sửa lại bảng chỉ tiêu trong test_eval.md §5 khi chốt ngưỡng thật.

---

## D. ISSUES — Đóng gói & phụ thuộc

### 📦 DEP-1 · P1 · 🟢 XONG · `requirements.txt` không ghim version nào {#dep-pin}

Tám dòng, **không dòng nào có version**: `click flask imutils numpy onnxruntime opencv-python
rembg waitress`. `rembg` là dependency biến động nhất (API `remove()` đã đổi qua các bản: thêm
`session`, alpha matting, tách `rembg[cli]`), và `setup.py` đọc thẳng file này làm
`install_requires` — [setup.py:9-10](../setup.py#L9-L10). Người cài hôm nay và tháng sau **không
nhận cùng phần mềm**, còn chất lượng đầu ra thì đổi thầm lặng.

**Hướng**: ghim dải tương thích (`rembg>=2.0,<3`, `opencv-python>=4.8,<5`, …); tách
`requirements-dev.txt` cho test; regression test trên `examples/` để bắt trôi chất lượng khi nâng.

**✅ Đã làm** cả ba. Lưu ý: đã dùng `opencv-python>=4.8,<6` chứ không phải `<5` — OpenCV 5 đã
phát hành và **đang là bản chạy thật ở đây**. Chính nó phơi ra một lỗi: `HoughLinesP` đổi
shape trả về từ `(N,1,4)` sang `(N,4)`, làm đường lui dò cạnh vỡ. Đã chuẩn hoá shape thay vì
ghim version để né.

### 📦 PKG-1 · P2 · 🟢 XONG · `python_requires=">=3.5, <4"` sai thực tế {#pkg-pyversion}

[setup.py:20](../setup.py#L20). rembg/onnxruntime/numpy hiện đại cần **≥3.9**. Khai báo sai
khiến pip cho phép cài trên môi trường chắc chắn gãy. **Hướng**: `>=3.9,<4`, xác nhận bằng CI.

### 📦 PKG-2 · P3 · 🟢 XONG · Version hardcode trong `setup.py` {#pkg-version}

`version="1.0.6"` — [setup.py:15](../setup.py#L15) — không có `__version__` trong package
([`src/qc_scanner/__init__.py`](../src/qc_scanner/__init__.py) rỗng), nên runtime không tự biết mình
là bản nào (log/báo cáo QC cần thông tin này). **Hướng**: `__version__` trong `__init__.py`
làm nguồn sự thật, `setup.py` đọc lại.

### 📦 PKG-3 · P3 · 🟢 XONG · Import thừa {#pkg-imports}

`os`, `sys` ở [doc.py:1-2](../src/qc_scanner/doc.py#L1-L2) (`sys` có dùng cho stderr, `os` thì
không); `glob`, `os` ở [cli.py:1-2](../src/qc_scanner/cmd/cli.py#L1-L2) — `glob` có lẽ là dấu vết
của ý định làm batch CLI (xem N-01). **Hướng**: dọn, thêm linter vào CI (N-05).

### 📦 PKG-4 · P2 · 🟢 XONG · Không có test, không có CI {#pkg-notest}

Không thư mục `tests/`, không `pytest`, không workflow chạy test. 8 cặp ảnh trong `examples/`
là **tài sản chưa dùng** — chúng chính là bộ regression sẵn có.
Xem [test_eval.md §2](test_eval.md).

**✅ Đã làm**: 122 test trong `tests/`, workflow CI ở `.github/workflows/ci.yml` (cài sạch +
ruff + pytest trên 3.9/3.12 + build wheel, có cache model rembg).

---

## E. FEATURES — Đã có (đã ship)

| Mã | Tính năng | Ghi chú |
|----|-----------|---------|
| F-01 | Hàm lõi `scan(bytes) -> bytes`: tách nền → dò biên → nắn phối cảnh → PNG | [doc.py:14](../src/qc_scanner/doc.py#L14) |
| F-02 | CLI `qc-scanner`: stdin/stdout pipe **hoặc** đối số file vào/ra | [cmd/cli.py](../src/qc_scanner/cmd/cli.py) |
| F-03 | HTTP server `qc-scanner-server`: `POST /` form-file, `GET /?url=` | [cmd/server.py](../src/qc_scanner/cmd/server.py) (GET-url: xem SEC-1) |
| F-04 | Fallback trả ảnh gốc khi không tìm được biên | Nay **có nhãn**: `FALLBACK_ORIGINAL` + `metrics.fallback_used` |
| F-07 | `scan_qc()` trả verdict + reasons + metrics | [qc.py](../src/qc_scanner/qc.py) · [doc.py](../src/qc_scanner/doc.py) |
| F-08 | Batch CLI `qc-scanner-batch` + báo cáo CSV | [cmd/batch.py](../src/qc_scanner/cmd/batch.py) |
| F-09 | Bộ eval: metric ra CSV, so hai lần chạy, tính crop/false-pass/false-fail khi có nhãn | [eval.py](../src/qc_scanner/eval.py) |
| F-10 | Docker + CI + bộ test 122 bài | [Dockerfile](../Dockerfile) · [ci.yml](../.github/workflows/ci.yml) |
| F-05 | Đóng gói setuptools + 2 console script (`qc-scanner`, `qc-scanner-server`) | [setup.py:22-27](../setup.py#L22-L27) |
| F-06 | 8 cặp ảnh mẫu input/output | [examples/](../examples/) — dùng làm fixture regression |

## F. FEATURES — Đề xuất (backlog)

| Mã | Tính năng | Ưu tiên | Ghi chú |
|----|-----------|---------|---------|
| ~~N-01~~ | 🟢 **Batch CLI + báo cáo QC tổng hợp** | P1 | Xong: `qc-scanner-batch IN OUT --report qc.csv` |
| ~~N-02~~ | 🟢 Tham số hóa qua CLI/env | P2 | Xong: `config.py` + `QC_SCANNER_*` |
| N-03 | Chế độ debug đầy đủ | P2 | Một phần: `--debug-dir` xuất mask + ảnh đã nắn; chưa vẽ chồng contour/tứ giác |
| ~~N-04~~ | 🟢 Dockerfile + nướng sẵn model | P2 | Xong |
| ~~N-05~~ | 🟢 CI | P2 | Xong: lint + test 3.9/3.12 + build wheel |
| ~~N-06~~ | 🟢 Tái dùng `rembg` session | P2 | Xong. **Đo được: ~3.0s → ~0.4s mỗi ảnh** |
| N-07 | Tách nhiều tài liệu trong một ảnh thành nhiều đầu ra | P3 | Nối tiếp QC-9 |
| N-08 | Đầu vào PDF / đa trang | P3 | Chờ nhu cầu khách (`need_exchange.md` EX-3) |
| N-09 | Hậu xử lý làm nét/khử bóng (adaptive threshold, shadow removal) | P3 | Đầu ra "giống bản scan"; chờ chốt EX-5 |
| N-10 | onnxruntime-gpu tùy chọn | P3 | Chỉ đáng làm sau khi đo (N-06 rẻ hơn nhiều) |

---

## Cách dùng file này
- Raise issue mới: thêm mục vào §A–§D với mã tăng dần, priority, `path:line` bằng chứng.
- Đóng issue: đổi 🔴→🟢, ghi commit/PR đã sửa + số đo trước/sau nếu là thay đổi chất lượng.
- Issue về **chất lượng nắn** phải kèm ảnh ví dụ sai + metric (xem [test_eval.md](test_eval.md)).
- Thêm **reason code** mới: khai báo đủ hint + audience trong
  [algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes), kèm ca test.
