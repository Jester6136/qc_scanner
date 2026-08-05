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

**Đợt chốt yêu cầu khách 2026-08-05** (xem §A2) mở thêm 6 mục và **đóng gần hết ngay trong
ngày**: QC-11 · QC-12 · QC-13 · QC-14 🟢 · S-5 đã đo → chốt **không làm** ⚪ · N-11 **bỏ** theo
yêu cầu ⚫. Chỉ còn **OPS-3**, để cuối vì máy phát triển không build Docker được.

**Đợt soi ảnh thật 2026-08-05 (tmp_2)** mở và đóng thêm hai mục: **QC-15** (ngừng phát
`SUBJECT_FILLS_FRAME`) và **QC-16** (đường lui ghi đè tứ giác đúng bằng tứ giác sai — ba sửa
đổi, 6 ảnh chuyển `fail` → `warn`, tất cả đã soi mắt thường).

**Còn mở, và lý do**:

| Mã | Vì sao chưa làm |
|---|---|
| QUAL-3 quét ngưỡng | Cần tập vàng có nhãn của khách (EX-2). Bộ eval đã chạy được, chỉ thiếu dữ liệu. |
| S-1 đổi model nền | **Đã đo** (xem mục S-1). isnet chậm gấp 3 và đổi 2 verdict; không có nhãn thì không biết đổi là tốt hay tệ. |
| S-3 DocAligner | Chỗ cắm đã sẵn (S-2). Nguyên tắc "đo trước, đổi sau" cấm đổi đường chính khi chưa có tập vàng. |
| S-5 dewarping | **Đã đo, chốt là KHÔNG làm.** 36 ảnh thật, không ảnh nào cong quá sàn nhiễu của mask. Mở lại khi có ảnh hoá đơn cuộn. |
| N-03/07/09/10 | Chờ nhu cầu khách (EX-3/EX-5/EX-10). |

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
| 1 | [QC-11](#qc-no-crop) | ~30 phút | ✅ xong 2026-08-05 |
| 2 | [QC-12](#qc-content-clipped) | ~nửa ngày | ✅ xong 2026-08-05 |
| 3 | [QC-13](#qc-two-tier-hint) | ~nửa ngày | ✅ xong 2026-08-05 |
| 4 | [QC-14](#qc-precropped) | ~2h | ✅ xong 2026-08-05 |
| 5 | [S-5](#s-dewarp) đo độ cong | ~2h đo | ⚫ hạ ưu tiên — khách nói giấy cong là **hiếm** |
| — | ~~N-11 công cụ gán nhãn~~ | — | ⚫ **BỎ** theo yêu cầu khách 2026-08-05 |
| 6 | [OPS-3](#ops-docker-unverified) | ~nửa ngày | **máy dev không build Docker** — làm cuối, trên máy server |

---

### 🧱 N-12 · P1 · 🟢 · Chuyển HTTP service từ Flask sang FastAPI {#n-fastapi}

> **✅ Đã làm 2026-08-05** theo yêu cầu khách.

Flask + waitress → **FastAPI + uvicorn**. Hợp đồng trong [api.md](api.md) **không đổi một chữ**,
và đó là điều đáng nói nhất: 30 test hợp đồng viết theo tài liệu chứ không theo framework, nên
chúng là thứ chứng minh việc đổi nền không làm gãy tích hợp của khách. Chỉ phần *dựng client*
trong test phải sửa (`app.test_client()` → `TestClient`), phần **khẳng định** thì y nguyên.

**Một cái bẫy phải xử lý riêng**: FastAPI trả `422` cho lỗi validate tham số, mà `422` trong hợp
đồng này đã mang nghĩa khác hẳn — *"ảnh hợp lệ nhưng đầu ra không đáng tin cho OCR"*. Để mặc
định thì hai chuyện rất khác nhau (phía gọi truyền sai tham số / ảnh chụp hỏng) đội chung một
mã, và phía tích hợp không phân biệt được nên retry hay sửa code. Nên tham số khai báo lỏng
(`Optional[UploadFile]`, đọc query thủ công) rồi tự kiểm, để mọi lỗi đầu vào rơi về `400`.

Giới hạn 32 MB cũng phải làm tay: Flask có `MAX_CONTENT_LENGTH`, Starlette thì không. Middleware
chặn theo `Content-Length` **trước khi đọc thân request** — đọc rồi mới đo thì ảnh 2GB đã nằm
trong RAM mất rồi, đúng thứ giới hạn này sinh ra để tránh.

**Được thêm**: `/docs` (Swagger UI) — trả lời luôn câu "mở bằng trình duyệt không thấy gì".
Nó **mô tả** hợp đồng chứ không định nghĩa; những thứ quan trọng nhất (nghĩa của `422`, bất biến
`pass ⟺ reasons rỗng`, mã nào ổn định vĩnh viễn) là quy ước, không suy ra được từ chữ ký hàm.

**Đã kiểm bằng service thật**, không chỉ `TestClient`: `/healthz` → 200 · `GET /` → 405 ·
`/docs` → 200 · `POST /` → PNG 1088×1905 kèm `x-qc-scanner-verdict: warn` · thiếu `file` → 400 ·
file rỗng → 400 `FILE_EMPTY` đúng hình dạng `{"error": {...}}`.

---

### 🔴 OPS-3 · P0 · 🔴 · Dockerfile CHƯA BUILD THỬ LẦN NÀO {#ops-docker-unverified}

[Dockerfile](../Dockerfile) được viết ở Giai đoạn 4 nhưng **chưa chạy `docker build` lần nào**
— không có bằng chứng nào là nó dựng được, càng không có bằng chứng service bên trong chạy được.

Sau [EX-13](need_exchange.md), image này **chính là thứ bàn giao cho khách**, kèm HTTP service
để hệ khác gọi vào. Một artefact chưa từng được kiểm mà lại là bề mặt bàn giao chính là rủi ro
lớn nhất hiện tại của dự án.

> **Cập nhật 2026-08-05 — đã build thật, và nó chạy.** `docker compose up --build -d` dựng
> image trong **386.9s**, container lên `Up (healthy)`, cổng `0.0.0.0:5000->5000`. Rủi ro lớn
> nhất của dự án ("thứ bàn giao chính chưa có bằng chứng chạy được") **không còn là giả định**.
>
> **Bẫy gặp ngay lần đầu, và nó không phải lỗi của mình**: trên macOS cổng 5000 bị **AirPlay
> Receiver** chiếm sẵn. Docker vẫn bind được, container vẫn `healthy` — vì healthcheck chạy
> *bên trong* container, nơi cổng 5000 là của nó — nhưng gọi từ host vào nhận `403 Forbidden`
> với header `Server: AirTunes/890.79.5`. Server của mình **không có mã 403 nào**, nên chính
> header đó là thứ chỉ ra thủ phạm. Đã cho cổng host đổi được bằng `QC_SCANNER_PORT`.
>
> Bài học đáng ghi: `healthy` của compose **không** chứng minh khách gọi được — nó chỉ chứng
> minh tiến trình bên trong sống. Muốn biết khách gọi được thì phải gọi từ ngoài vào.
>
> **Còn lại chưa kiểm**: gọi API từ host qua cổng không bị chiếm · chạy khi **ngắt mạng** ·
> gọi từ máy B qua LAN · thêm bước build image vào CI.

**Hoãn tới cuối (chốt 2026-08-05)**: máy phát triển hiện tại không build Docker được. Việc này
làm khi lên máy server. Rủi ro **không giảm** vì hoãn — chỉ dời chỗ; đến lúc build mà hỏng thì
vẫn hỏng, nên đừng coi phần còn lại "xong" là cả gói đã xong.

> **✅ Phần không cần Docker đã xong 2026-08-05**: [docs/api.md](api.md) — hợp đồng API đầy đủ
> (endpoint, tham số, status theo verdict, schema JSON, bất biến, phần "chưa có và biết là chưa
> có") — cùng **30 test hợp đồng** ở `tests/test_api_contract.py` chạy qua `app.test_client()`,
> không cần image.
>
> Sửa luôn một bất nhất phát hiện khi viết tài liệu: cùng khoá `error` mà ca thiếu `file` trả
> **chuỗi** còn ca ảnh hỏng trả **object**, phía tích hợp phải đoán kiểu dữ liệu. Nay mọi lỗi
> 400 đều là object có `code`; thêm mã `MISSING_FILE`.
>
> **Đã thêm 2026-08-05**: [`docker-compose.yml`](../docker-compose.yml) để khách chỉ cần
> `docker compose up --build -d` là có API. Vẫn **chưa chạy thử** — viết theo đúng Dockerfile và
> server hiện có, không có bằng chứng nào là nó dựng lên được.
>
> Kèm theo, bịt một lỗ rò thật: `.dockerignore` thiếu `tmp_2/`, mà `COPY . .` thì lấy tất —
> **ảnh CCCD/sổ đỏ của khách sẽ bị nướng vĩnh viễn vào image đem đi phân phối**. Nay chặn cả
> `tmp`, `tmp_2`, và bỏ luôn `docs`/`tests` cho nhẹ image.
>
> **Còn lại đúng phần cần Docker**: `docker build`, `docker compose up`, kiểm ngắt mạng, thêm
> build image vào CI. Nghi ngờ đầu tiên nếu container chết ngay: `read_only: true` trong compose.

**Hướng**: (1) `docker build` thật, sửa tới khi qua; (2) `docker run` rồi gọi thử `POST /`,
`?format=json`, ca hỏng, `/healthz`; (3) kiểm model đã nướng sẵn bằng cách chạy image **ngắt
mạng**; (4) viết **tài liệu API** (endpoint, status code theo verdict, header, schema JSON);
(5) thêm **test hợp đồng API** để thay đổi schema làm gãy test chứ không gãy tích hợp của khách;
(6) thêm bước build image vào CI.

---

### 🧱 QC-11 · P0 · 🟢 · `NO_CROP_DETECTED` — bắt ca "không crop được gì mà vẫn báo warn" {#qc-no-crop}

> **✅ Đã làm 2026-08-05.** Mã `NO_CROP_DETECTED` (`fail`) trong [qc.py](../src/qc_scanner/qc.py),
> ngưỡng `no_crop_area_ratio = 0.90` trong [config.py](../src/qc_scanner/config.py), luật ở
> `_geometry_reasons()`. Nó **thay** `CLIPPED_EDGE` chứ không cộng thêm — chạm 4 mép ở đây là hệ
> quả, nêu cả hai làm loãng lý do thật. Chạy lại 9 ảnh thật: đúng 2 ảnh đổi `warn` → `fail`, 7
> ảnh còn lại không đổi. 4 test trong `tests/test_reason_codes.py` kiểm thẳng luật hình học
> (kể cả **đối chứng** tứ giác 0.94 khung mà không chạm đủ 4 mép thì không được báo).
>
> *Khác kế hoạch một điểm*: định dựng ca test bằng ảnh giấy trắng trên nền trắng, nhưng dấu hiệu
> này phụ thuộc việc rembg tách nhầm nền — không tái tạo ổn định bằng ảnh vẽ tay, mà ảnh thật thì
> không commit được (dữ liệu khách). Nên test đánh thẳng vào `_geometry_reasons()`.

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

### 🧱 QC-12 · P0 · 🟢 · `CONTENT_CLIPPED` — mất viền thì được, mất CHỮ thì không {#qc-content-clipped}

> **✅ Đã làm 2026-08-05.** `geo.ink_at_image_border()` + mã `CONTENT_CLIPPED` (`fail`), ngưỡng
> `max_border_ink_ratio = 0.08`. Nó **thay** `CLIPPED_EDGE` khi có mực ở mép, giữ `CLIPPED_EDGE`
> mức `warn` cho ca chỉ mất viền — đúng ranh giới [EX-1](need_exchange.md).
>
> **Ba lần đo lại mới ra cách đo dùng được**, ghi lại để không ai đi lại đường cụt:
> 1. *Đo dải biên trên ảnh đã nắn* — vô dụng. `warpPerspective` chèn pixel đen ngoài tứ giác;
>    cạnh trái `doc-3.out.png` có **95%** pixel < 30. Đo được toàn vùng đệm, ảnh sạch cũng cho
>    0.10–0.92, ảnh cắt cố ý còn *thấp hơn* ảnh sạch.
> 2. *Chuyển sang đo trên ảnh gốc, trong phần nằm trong tứ giác* — đúng hướng nhưng nới biên
>    "chạm mép" theo `ratio` thì doc-5 (tứ giác cách mép 4px) nhảy 0.000 → 0.187 vì dải rơi vào
>    **bóng mép giấy**. Mã mức `fail` phải đòi tứ giác *thật sự* chạm mép: margin 2px ảnh gốc.
> 3. *Co mask đều vài pixel để bỏ vệt biên* — co đều thì ăn luôn vào phía mép ảnh, đúng chỗ cần
>    soi. Phải co **theo dọc dải** (kernel dẹt song song mép ảnh), cộng điều kiện cạnh phải áp
>    ≥10% mép ảnh mới xét — tứ giác chạm mép bằng một góc thì mẫu số bé, tỉ lệ bị vệt ranh giới
>    chi phối.
>
> Kết quả tách nhóm rõ: không mất gì **0.000** (12 ảnh) · mất viền **0.000–0.041** · mất chữ
> **0.150–0.507** (4 ảnh cắt cố ý 12% mỗi chiều + 2 ảnh thật). Ngưỡng 0.08 nằm giữa.
> Test: cặp `clipped_document` / `clipped_margin_only` chốt **cả hai chiều** của EX-1.
>
> ⚠️ **Hệ quả phải báo khách** → [QC-14](#qc-precropped) bên dưới: ảnh **đã cắt sẵn** (chữ chạy
> tới sát mép) nay đều `fail`. Đo trên `examples/*.out.png`: 0.124–0.891, tức đúng dấu hiệu của
> ảnh mất chữ.


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

### 🧱 QC-17 · P0 · 🟢 · Mép giấy CONG bị cắt lẹm vào nội dung {#qc-containing-quad}

> **✅ Đã làm 2026-08-05.** Từ ảnh `04.58.45` khách chỉ ra: "crop được rồi nhưng do nó cong cong
> nên bị lẹm".

`approxPolyDP` trả tứ giác **nội tiếp** — nó nối 4 góc bằng đường thẳng. Tờ giấy cong thì mép
vồng ra *ngoài* dây cung, và `four_point_transform` cắt đúng theo dây cung → **lẹm vào nội dung
ở giữa cạnh**. Ảnh `04.59.48` mất nguyên dòng cuối *"Thông tin chi tiết được thể hiện tại mã QR"*.

Đây chính là phần "giấy cong" mà [S-5](#s-dewarp) đo và kết luận là hiếm — và kết luận đó vẫn
đúng: **cong ít cũng đủ gây lẹm**, dù không đủ để cần dewarping lưới.

**Đã làm**: `geo.containing_quad()` — đẩy từng cạnh ra ngoài cho tới khi bao trọn contour, giữ
nguyên **hướng** 4 cạnh. Đầu ra vẫn là phép nắn phối cảnh 4 điểm nên rẻ, không thêm phụ thuộc,
không đụng phần còn lại của luồng. Nó **không duỗi thẳng** giấy cong — chỉ thôi cắt lẹm.

Đổi lại là thêm chút nền quanh mép; theo [EX-1](need_exchange.md) mất viền còn hơn mất chữ.
Đo trên 45 ảnh: diện tích tăng **trung vị 4.6%**, nhiều nhất 17% — không ca nào phình bất
thường. `max_edge_grow_ratio` chặn ca mask lỗi có gai nhọn.

**Một cái bẫy đã sập rồi mới thấy**: lần đầu tôi đo hình học trên tứ giác **đã nới**, và nó hỏng
— nới làm góc chạm mép ảnh nên **5 ảnh vốn `pass` bị đẩy sang `warn`** (`CLIPPED_EDGE`), còn ca
hỏng thật `abc1b13…` **thoát** `NO_CROP_DETECTED` vì góc lệch ra ngoài bị kẹp lại thành 0. Sửa:
phán quyết hình học nói về **biên tờ giấy detector tìm được**; nới chỉ là lề khi cắt. Sau đó
phân bố verdict không đổi (17 warn · 15 fail · 13 pass), chỉ 4 ảnh đổi mã.

**Ảnh hưởng tới bộ hồi quy**: `examples/*.out.png` là đầu ra thuật toán gốc, nên NCC tụt còn
0.56 — test bắt đúng thứ nó sinh ra để bắt, chỉ là lần này thay đổi có chủ ý. Tách làm hai:
bài cũ chạy với `contain_paper_contour=False` (giữ nguyên chức năng canh thuật toán gốc không
trôi), và hai bài mới cho QC-17 — "chỉ được thêm lề, không được bớt" và "ruột ảnh cũ phải nằm
trong ảnh mới" (dò mẫu, vì so pixel tại chỗ tụt xuống 0.69 do lệch, dù ảnh vẫn đúng), kèm một
bài chốt chặn bắt chính phép dò mẫu phải trượt khi đưa nhầm tài liệu khác.

---

### 🧱 QC-15 · P1 · 🟢 · `SUBJECT_FILLS_FRAME` — chiếm hết khung, tự nó, không phải lỗi {#qc-fills-frame}

> **✅ Đã làm 2026-08-05**, theo yêu cầu "cởi mở hơn: không chém vào chữ thì vẫn dùng được".

Mã này phát khi `alpha_coverage > 0.95`, với thông điệp "có thể đã bị cắt mất mép". Nó là một
**phỏng đoán**, ra đời khi chưa đo được điều nó phỏng đoán. Nay `border_ink_ratio` đo thẳng.

Đo trên 45 ảnh: mã này phát **4 lần**, và cả 4 lần đều đi kèm `NO_CROP_DETECTED` hoặc
`CONTENT_CLIPPED` — hai mã nói cùng chuyện đó nhưng có số đo đằng sau. Nó **chưa bao giờ tự
mình quyết verdict**.

**Đã làm**: ngừng phát. Định nghĩa vẫn nằm trong `REASONS` để log/CSV cũ tra được, và bật lại
chỉ là một dòng trong `doc.py`. `alpha_coverage` vẫn nguyên trong metrics.

---

### 🧱 QC-16 · P0 · 🟢 · Đường lui ghi đè tứ giác ĐÚNG bằng tứ giác SAI {#qc-fallback-overrides}

> **✅ Đã làm 2026-08-05.** Phát hiện khi soi ảnh `04.57.20` mà khách chỉ ra.

Ảnh `04.57.20`: rembg cho tứ giác **0.964 khung, conf 0.9, đúng cả tờ**. Nhưng `alpha_coverage`
0.969 vượt `max_alpha_coverage` nên điều kiện kích hoạt đường lui coi là "không tách được chủ
thể", chạy `edge-hough`, nhận về một **dải 0.404** và **ghi đè**. Ảnh ra mất nguyên nửa trên
(411×1344 từ 970×1364). Chuỗi kết thúc bằng `CONTENT_CLIPPED` → `fail`.

Đây là kiểu sai đắt nhất: **đổi một kết quả đúng lấy một kết quả sai**, rồi báo lỗi vì chính
cái sai mình vừa tạo ra.

**Đã sửa ba chỗ, mỗi chỗ có số đo:**

1. **Đường lui chỉ chạy khi rembg KHÔNG tìm thấy gì** (`quad is None` hoặc
   `alpha < min_alpha_coverage`). Bỏ hẳn `alpha > max` khỏi điều kiện.
   *Đã thử hướng ngược lại* — nới điều kiện sang cả ca "tứ giác gần trọn khung" — và **đo thấy
   tệ hơn**: trên 3 ảnh thật (04.56.41 · 04.57.20 · 04.58.02), rembg đúng cả 3, edge-hough chỉ
   bắt được một mảnh (0.461 · 0.404 · 0.422), lần lượt mất trang trong có chữ viết tay, mất nửa
   trên, mất hẳn một trang. **Đường lui thắng 0/3.**

2. **`NO_CROP_DETECTED` chỉ phát khi detector THẬT SỰ thua** — `conf < 0.9` (phải ép
   `minAreaRect` vì không dựng nổi 4 đỉnh) hoặc có góc lọt ra ngoài ảnh. Tờ giấy chiếm gần hết
   khung mà biên vẫn dựng đàng hoàng là **người chụp lấy khung sát**, nội dung còn nguyên.
   Đo trên nhóm `area > 0.90 & tb >= 3`: `conf 0.6` gồm đúng các ca hỏng thật (bắt mặt bàn, góc
   lệch ra ngoài 18–59px); `conf 0.9` gồm các ca đã soi mắt thường và **crop ra nguyên tờ**.
   Kèm theo, hạ `touched_edges` từ 4 → 3: bắt thêm 3 ảnh cắt đi <10% khung, và **không ảnh nào**
   có diện tích > 0.90 mà chạm dưới 3 mép nên không mở cửa cho ca mới.

3. **`CONTENT_CLIPPED` không phát khi không có cắt thật** (`quad_area_ratio > 0.90`). Lúc đó
   con số nó đo là mép **tấm ảnh**, không phải mép crop — và tứ giác thường trùm cả nền, khiến
   ngưỡng thích nghi đọc mảng bàn tối thành "mực". `04.57.20` cho ink 0.213 tuy không mất chữ
   nào, chỉ vì dải trái là mặt bàn.

*Đã thử và bác*: lọc "nét mảnh" (mở hình thái để bỏ mảng dày, giữ nét chữ) để tách mực khỏi nền.
**Tệ hơn**: ca báo oan cho 0.124 còn ca cắt thật chỉ 0.061–0.086 — thứ bị lọc đi là chữ, thứ còn
lại là ranh giới giấy/bàn.

**Kết quả trên 45 ảnh**: 21 fail → **15 fail**, 11 warn → 17 warn, pass giữ nguyên 13.
Sáu ảnh chuyển `fail` → `warn`, **cả sáu đã soi mắt thường: crop ra nguyên tờ, không mất gì.**

---

### 🧱 QC-14 · P1 · 🟢 · Ảnh ĐÃ CẮT SẴN bị `CONTENT_CLIPPED` báo oan {#qc-precropped}

> **✅ Đã làm 2026-08-05**, sau khi khách xác nhận **có** gửi cả ảnh đã cắt sẵn (EX-14) và gửi
> thêm 20 ảnh thật (đợt 2).
>
> **Đã thử tự đoán trước, và bỏ vì số liệu bác bỏ.** Nếu tách được "ảnh đã cắt" khỏi "ảnh chụp"
> bằng pixel thì không cần phiền phía gọi. Đo trên 37 ảnh (8 đã cắt + 29 ảnh chụp):
> `alpha_coverage` **0.270–0.998** ở nhóm đã cắt và **0.260–0.996** ở nhóm ảnh chụp;
> `quad_area_ratio` cũng trùng dải. Không có ngưỡng nào tách được — đoán mò chỉ đổi loại lỗi
> này lấy loại lỗi khác. Nên **phía gọi phải khai báo**.
>
> Cài đặt: `Config.pre_cropped` · `qc-scanner --pre-cropped` · `qc-scanner-batch --pre-cropped`
> · `POST /?pre_cropped=1` · `QC_SCANNER_PRE_CROPPED`. Khi bật, bốn mã về biên bị bỏ:
> `CLIPPED_EDGE`, `CONTENT_CLIPPED`, `NO_CROP_DETECTED`, `SUBJECT_FILLS_FRAME`.
> Kết quả trên `examples/*.out.png`: 7 fail + 1 warn → **7 pass + 1 fail**, ca fail còn lại là
> `LOW_RESOLUTION` — đúng, vì đó không phải lỗi biên.
>
> **Cân nhắc đã bác**: phát thêm một mã `PRE_CROPPED_UNVERIFIED` mức `warn` cho đúng nguyên tắc
> "không im lặng". Bỏ, vì nó nói lại đúng thứ phía gọi vừa khai báo, đổi lại là đẩy *toàn bộ*
> kho ảnh đã cắt vào hàng chờ người soi ([EX-8](need_exchange.md)) — tốn công thật để lấy thông
> tin bằng không. Sự thật "đã bỏ qua kiểm tra biên" đi vào `metrics.pre_cropped`, chỗ dành cho
> dữ kiện không đòi hành động.
>
> **Rủi ro còn lại, phải nói rõ với khách**: gắn cờ nhầm cho một ảnh chụp thì qc_scanner mất
> khả năng bắt crop hụt trên ảnh đó. Vì thế cờ này để **tắt mặc định**, và có test chặn nó
> trượt thành công tắc "cho qua tất" (ảnh mờ vẫn phải `fail`).

---

### 📕 QC-14 (hồ sơ gốc) {#qc-precropped-original}

Phát sinh từ chính QC-12. Với ảnh **đã được cắt sát** từ trước (bản scan, hoặc ảnh đã qua một
công cụ crop khác), chữ chạy tới sát mép là chuyện **bình thường** — nhưng nhìn từ ngoài nó
giống hệt ảnh bị khung hình cắt mất chữ. Đo trên `examples/*.out.png`: `border_ink_ratio`
0.124–0.891, đều `fail`.

Hai thứ này **không phân biệt được từ một tấm ảnh đơn lẻ**: cùng một bức ảnh "chữ chạm mép" có
thể là bản cắt đẹp, cũng có thể là bản mất mất dòng cuối. Chỉ có bối cảnh mới trả lời được.

[EX-3](need_exchange.md) chốt kho ảnh là **hỗn hợp**: phần lớn tồn kho + một phần chụp mới. Nếu
phần tồn kho đó đã qua cắt, QC sẽ báo trượt gần như toàn bộ.

**Hướng**: cần khách trả lời trước (**EX-14**, xem [need_exchange.md](need_exchange.md)) — ảnh
tồn kho là **ảnh chụp thô** hay **ảnh đã cắt**? Nếu có ảnh đã cắt thì thêm bối cảnh đầu vào
(`--pre-cropped` / trường trong request) để tắt `CONTENT_CLIPPED` cho luồng đó, thay vì đoán.
Chín ảnh thật hiện có đều là ảnh chụp thô nên chưa chạm phải, nhưng đó là mẫu quá nhỏ để kết luận.

---

### 🧱 QC-13 · P1 · 🟢 · Hint hai tầng: người chụp / vận hành {#qc-two-tier-hint}

> **✅ Đã làm 2026-08-05.** `ReasonSpec.hints = {capturer, operator}` cho **cả 19 mã**;
> `Reason.for_audience()` đổi tầng, và việc đổi diễn ra ở **đúng một chỗ** — `ScanResult.of()`,
> ngay trước khi trả kết quả — thay vì bắt mọi nơi dựng `Reason` mang bối cảnh theo.
>
> Khai báo bối cảnh ở từng mặt tiền: `qc-scanner --audience`, `POST /?audience=`,
> `Config.hint_audience` / `QC_SCANNER_HINT_AUDIENCE`. **`qc-scanner-batch` mặc định
> `operator`** — chạy lô là xử lý kho ảnh, ở đó không ai chụp lại được nữa.
>
> Kết quả trả về **cả hai tầng** trong trường `hints`, nên phía gọi hiển thị lại theo vai người
> đọc mà không phải gọi lại lần nữa.
>
> Ba test giữ đúng tinh thần chứ không chỉ giữ cấu trúc: (1) mã nào cũng phải đủ hai tầng;
> (2) hai tầng phải **khác nhau thật** — chép nguyên hint người chụp sang là qua bài (1) mà
> chẳng sửa được gì; (3) hint tầng vận hành **không được chứa** "chụp lại" / "lùi máy" /
> "bật đèn", tức chính thứ [nguyên tắc §3.4 roadmap](overall_roadmap.md) cấm.
>
> Mã `system` (`FILE_EMPTY`, `DECODE_FAILED`) không có tầng riêng — cả hai luồng đều phải nhờ
> người vận hành, nên `hint_for()` cho chúng rơi về tầng `operator`.

[EX-3](need_exchange.md) chốt **cả hai luồng**: batch cho kho ảnh cũ (không ai chụp lại được)
và realtime cho ảnh chụp mới (chụp lại được ngay).

Hiện mỗi `Reason` chỉ có **một** `hint` và **một** `audience`. Với ảnh kho, hint kiểu "đặt tài
liệu lên nền tối rồi chụp lại" là **vô dụng** — không ai chụp lại được. Đúng thứ
[nguyên tắc §3.4 roadmap](overall_roadmap.md) cấm: thông điệp không hành động được.

**Hướng**: mỗi mã có `hints: {capturer: ..., operator: ...}`; luồng gọi khai báo bối cảnh
(realtime hay batch) và chỉ nhận hint hợp với mình. Test hợp đồng phải đòi **cả hai** tầng có
nội dung, không chỉ một.

---

### 📦 N-11 · ⚫ BỎ · Công cụ hỗ trợ gán nhãn tập vàng {#n-label-tool}

> **⚫ Bỏ 2026-08-05 theo yêu cầu.** Không dựng công cụ gán nhãn.
>
> Hệ quả phải nhớ: [QUAL-3](#qual-sweep) (quét ngưỡng), [S-1](#s-model-swap) (đổi model)
> và [S-3](#s-docaligner) (đổi detector) vẫn cần nhãn để quyết bằng số. Bỏ công cụ **không** bỏ
> nhu cầu đó — chỉ có nghĩa là khi cần nhãn thì sẽ gán bằng cách khác, hoặc chấp nhận chốt
> những mục kia bằng cảm tính. Ghi ra đây để lúc đó không ai ngạc nhiên.

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

### ⚡ SPD-1 · P2 · 🟢 XONG · Mỗi lần scan giải mã ảnh 2 lần + mã hoá thừa 1 PNG toàn cỡ {#spd-roundtrip}

`rembg.remove()` nhận **bytes** và trả **bytes PNG RGBA nguyên kích thước ảnh gốc**. Nghĩa là
một lần scan làm chuỗi này: OpenCV giải mã ảnh (`orig`) → PIL giải mã **lại** ảnh đó bên trong
rembg → ghép mask thành kênh alpha ở full-res → **mã hoá PNG** vài triệu pixel → `cv2.imdecode`
giải mã ngược lại — tất cả để lấy đúng **một kênh alpha**.

**✅ Đã làm**: `segment_mask()` gọi thẳng `session.predict()` và lấy mask. Bỏ hẳn ghép alpha,
mã hoá PNG và một lần giải mã.

Đo trên 37 ảnh thật (`tmp/` + `tmp_2/` + `examples/`). Máy đo bị throttle nhiệt nên số tuyệt
đối trôi giữa các lần chạy — chạy A/B **xen kẽ trong cùng một tiến trình**, 111 cặp, lấy trung
vị: chặng tách nền **0.566s → 0.409s, nhanh 1.38x**. Chặng này chiếm ~80% một lần scan nên cả
lần scan nhanh khoảng **1.2x** (~0.16s/ảnh).

Phán quyết **không đổi một ảnh nào**, ảnh ra **trùng byte 37/37**, metric lệch **0.000**.

**Đã thử và loại bỏ**: hạ mẫu ảnh xuống 500px *trước* khi suy luận (model vốn ép về 320×320,
tưởng là miễn phí). Nhanh thêm ~0.02s/ảnh nhưng hạ mẫu hai chặng làm nhoè thêm và **mask co
lại thật sự**: `abc1b13…` tụt `alpha_coverage` 0.666→0.606 và **thoát** `NO_CROP_DETECTED` —
một ảnh không cắt được gì tụt từ `fail` xuống `warn`. Soi mắt thường xác nhận ảnh đó đúng là
không cắt được gì. Đổi một ca lọt lưới lấy 5% tốc độ là đổi sai chiều.

**Phụ phẩm**: mọi thứ giờ suy ra từ **cùng một mảng**. Đường cũ tính `ratio` giữa ảnh PIL giải
mã và ảnh OpenCV giải mã, tức ngầm tin hai thư viện xoay EXIF giống hệt nhau — đúng trên thực
tế, nhưng là giả định không ai kiểm.

---

### ⚡ SPD-2 · P1 · 🟢 XONG · `scan_qc()` chạy trên vòng lặp sự kiện → chặn cả `/healthz` {#spd-event-loop}

Endpoint khai báo `async def` nhưng gọi `scan_qc()` — code **đồng bộ**, ~0.4s CPU. Coroutine
không nhả điều khiển ở chỗ nào cả, nên nó chạy thẳng trên vòng lặp sự kiện và **chặn toàn bộ
tiến trình**.

Đo trên server thật, 8 request song song: `/healthz` trễ **trung vị 617ms, tối đa 698ms**. Đây
không phải chuyện chậm — healthcheck của compose để `timeout: 10s` thì chưa sao, nhưng bất kỳ
proxy hay orchestrator nào dùng ngưỡng chặt hơn sẽ coi service là chết **đúng lúc nó đang bận
nhất**, rồi restart container giữa lúc tải cao.

**✅ Đã làm**: đổi endpoint sang `def` (Starlette tự đẩy sang threadpool), giữ `/healthz` ở
`async def` để nó luôn chạy trên vòng lặp sự kiện. Thêm `QC_SCANNER_MAX_CONCURRENCY` (mặc định
2) chặn số ảnh xử lý cùng lúc.

Sau khi sửa: `/healthz` **trung vị 2ms, tối đa 9–61ms**. Thông lượng gần như không đổi (2.95s →
2.83s cho 8 ảnh) — đúng như dự đoán, onnxruntime vốn đã dùng hết nhân CPU nên không còn chỗ
song song hoá. Quét mặc định bằng số: 1→3.19s · **2→2.83s** · 4→2.93s · 8→3.10s.

Khác biệt nằm gọn ở **một từ khoá**, rất dễ bị "sửa lại cho nhất quán" — nên có test chặn.

---

### ⚡ SPD-3 · P2 · 🟢 XONG · Upload > 1MB bị đổ ra file tạm trên đĩa {#spd-spool}

Starlette mặc định `spool_max_size = 1MB`: phần upload vượt mức đó được ghi xuống
`SpooledTemporaryFile` **trên đĩa**. Ảnh vào là giấy tờ tuỳ thân và gần như ảnh nào cũng vượt
1MB, nên [EX-12] "mạng nội bộ, **không lưu ảnh**" trên thực tế đang bị vi phạm ở mọi request.

Container hiện có `tmpfs: /tmp` nên trong Docker nó rơi vào RAM — nhưng đó là may, không phải
thiết kế: chạy trực tiếp bằng `qc-scanner-server` (đúng cách CI và dev chạy) thì ảnh nằm trên
đĩa thật.

**✅ Đã làm**: nâng `MultiPartParser.spool_max_size` bằng `MAX_UPLOAD_BYTES` (32MB) → mọi
request hợp lệ nằm trọn trong RAM. Trần RAM là 32MB × `MAX_CONCURRENCY`, và SPD-2 là thứ chặn
số nhân đó. Có test chốt ngưỡng.

Chạy lô cũng được thêm `--jobs` (mặc định 2): luồng chồng phần OpenCV lên phần suy luận vì
onnxruntime và `cv2.imencode/imdecode` đều nhả GIL. Đo trên 37 ảnh: 1→14.2s · **2→11.8s** ·
3→12.0s · 4→12.7s. `ex.map` giữ **đúng thứ tự đầu vào** nên CSV và log không xáo trộn — có test
so kết quả chạy song song với chạy tuần tự.

---

### ⚡ SPD-4 · P2 · 🟡 ĐÃ VIẾT, CHƯA CHẠY THỬ · Tuỳ chọn GPU NVIDIA {#spd-gpu}

Sau SPD-1, `inner_session.run()` chiếm **81% tổng thời gian** (12.4s/15.3s trên 37 ảnh). Phần
còn lại: mã hoá PNG 0.89s, resize PIL 0.48s, giải mã 0.44s. Nói cách khác **mọi tối ưu CPU
khác cộng lại cũng không bằng đổi chỗ chạy cho model**.

**✅ Đã làm**: `QC_SCANNER_ONNX_PROVIDERS` + [requirements-gpu.txt](../requirements-gpu.txt) +
[Dockerfile.gpu](../Dockerfile.gpu) + [docker-compose.gpu.yml](../docker-compose.gpu.yml).

**Ba lỗi đã sửa sau khi thử dựng trên máy server** — đều là loại chỉ lộ ra khi chạy thật:

1. `pip3 install --break-system-packages`: pip của Ubuntu 22.04 là bản 22.x, **không có cờ đó**
   (thêm từ 23.0.1). Build đứt ngay dòng đầu. → dùng venv `/opt/venv`, miễn nhiễm luôn với
   PEP 668 nếu sau này nâng base image lên 24.04.
2. `onnxruntime-gpu>=1.17`: wheel 1.17/1.18 trên PyPI dựng cho **CUDA 11.8**, không khớp base
   image CUDA 12.4 + cuDNN 9. → `>=1.19`.
3. **`profiles: ["gpu"]` không làm được việc người ta tưởng.** Compose quy định service **không
   khai `profiles` thì LUÔN chạy**, nên `docker compose --profile gpu up` không *thay* bản CPU
   mà *thêm* bản GPU vào — hai container cùng đòi cổng 5000:

   ```
   Bind for 0.0.0.0:5000 failed: port is already allocated
   ```

   Ghi chú "đừng chạy cả hai" trong file cũ là vô dụng: nó không cho người dùng cách nào để
   tuân theo. → chuyển sang **file đè lên cùng một service**, khi đó chạy nhầm cả hai là điều
   không thể diễn đạt được.

**Lần dựng đầu trên máy H100 (64 nhân)**: build cả hai image OK, nhưng bên trong container GPU:

```
Available providers: 'AzureExecutionProvider, CPUExecutionProvider'
```

Chẩn đoán trong container cho ra thủ phạm:

```
nvidia-smi        → H100 PCIe, nhìn thấy bình thường
libcuda.so.1      → nạp được
pip list          → onnxruntime 1.23.2  ← bản CPU
                    onnxruntime-gpu 1.23.2
```

**Cả hai gói cùng có mặt.** Chúng dùng chung thư mục `onnxruntime/`, nên bản cài sau ghi đè
`onnxruntime_pybind11_state.so` của bản cài trước — và bản CPU thì không biết CUDA là gì.

Nguồn gốc: `setup.py` lấy `install_requires` từ **requirements.txt**, trong đó có `onnxruntime`.
Nên dòng cuối `pip install .` kéo bản CPU vào và đè lên `onnxruntime-gpu` vừa cài.
→ `pip install --no-cache-dir --no-deps .` (requirements-gpu.txt đã là danh sách phụ thuộc đầy đủ).

**Và chốt chặn build đã có thì bỏ lọt, vì đặt sai chỗ**: nó nằm ngay sau
`pip install -r requirements-gpu.txt`, tức là kiểm một trạng thái **trung gian** mà không ai
chạy — lúc đó bản CPU chưa được kéo vào. Một chốt chặn chạy quá sớm còn tệ hơn không có: nó
tạo cảm giác đã được kiểm. → chuyển xuống sau bước cài cuối cùng, thêm kiểm thứ hai độc lập với
metadata (`libonnxruntime_providers_cuda*` phải còn trên đĩa).

Cả hai điều kiện đó giờ có test giữ ở `tests/test_packaging.py`, kèm bài chốt hai file
requirements không lệch nhau — vì `--no-deps` biến requirements-gpu.txt thành nguồn phụ thuộc
duy nhất của image GPU.

Bài học không nằm ở việc chẩn đoán, mà ở chỗ **nó suýt trôi qua**: service vẫn chạy, vẫn trả
ảnh đúng, healthcheck vẫn xanh, chỉ chậm gấp mấy chục lần. `/healthz` có nói thật, nhưng phải
có người **nghĩ ra** việc đi đọc nó. → thêm `QC_SCANNER_REQUIRE_GPU`: container dựng riêng cho
GPU mà không có GPU thì **chết hẳn** kèm ba lệnh chẩn đoán, thay vì chạy tiếp. Ở container đó,
"chạy được bằng CPU" không phải đường lui hợp lệ — nó là lỗi cấu hình đang giả trang thành
thành công.

Cũng phát hiện `MAX_CONCURRENCY` mặc định `2` là **số đo trên máy 10 nhân** đem nguyên sang máy
64 nhân: `scan_qc` trực tiếp đạt 8.7 ảnh/s ở 16 luồng và vẫn còn tăng, trong khi đường HTTP chỉ
ra 4.9 req/s — chênh lệch đó chính là cái van khoá lại. → mặc định suy theo số nhân
(`cpu/8`, chặn trong [2, 16]); máy 10 nhân vẫn ra 2 nên kết quả đã đo không đổi.

Thêm chốt chặn lúc build cho lỗi đóng gói hay gặp nhất: cài nhầm `onnxruntime` (CPU) bên cạnh
`onnxruntime-gpu`. Hai gói ghi đè lên nhau nên `import onnxruntime` lấy bản nào là ngẫu nhiên —
và bản CPU chạy **đúng**, chỉ chậm gấp mấy chục lần. Thà đứt build còn hơn phát hiện sau.

**⚠️ Chưa có bằng chứng thực nghiệm nào**: máy phát triển là macOS, không có CUDA. Toàn bộ
đường GPU viết theo tài liệu onnxruntime.

Cái bẫy phải biết trước: **onnxruntime hỏng âm thầm**. Thiếu thư viện CUDA hoặc lệch phiên bản
CUDA/cuDNN thì nó **không báo lỗi** — chỉ lặng lẽ chạy `CPUExecutionProvider`. Service vẫn
`healthy`, vẫn trả ảnh đúng, chỉ chậm hơn vài chục lần, và không có gì trong log nói ra điều
đó. Vì vậy `/healthz` báo cáo `providers` **thật sự đang chạy** (không phải cái được yêu cầu),
và server in dòng đó lúc khởi động. Kiểm sau khi `up`:

```
curl -s http://localhost:5000/healthz     # "providers": ["CUDAExecutionProvider", ...]
```

Cũng lưu ý `onnxruntime` và `onnxruntime-gpu` **xung đột** — cài cả hai thì import lấy bản nào
là ngẫu nhiên. Phải `pip uninstall onnxruntime` trước.

Khi GPU chạy thật thì nút cổ chai **đảo chiều** sang phần CPU (giải mã ảnh, mã hoá PNG), nên
`MAX_CONCURRENCY` và `--jobs` phải nâng lên — con số 4 trong `Dockerfile.gpu` là ước đoán,
phải đo lại trên máy thật.

---

### ⚡ SPD-6 · P1 · 🟢 XONG · GPU hết bộ nhớ bị báo thành "ảnh hỏng" {#spd-oom}

Trên máy H100, `bench` ở `jobs=8` cho:

```
CUBLAS failure 3: CUBLAS_STATUS_ALLOC_FAILED
  → ScanError: DECODE_FAILED: Không giải mã được dữ liệu thành ảnh.
```

**Thông báo đó là nói dối** — ảnh hoàn toàn bình thường, GPU mới là thứ hết chỗ. Và qua HTTP nó
thành `400`, tức bảo phía gọi *"file của bạn hỏng, đừng thử lại"*. Hậu quả thật: **ảnh tốt bị
loại vĩnh viễn** vì một sự cố nhất thời của máy chủ, và người vận hành đi tìm lỗi ở đúng chỗ
không có lỗi.

Gốc rễ: `_segment()` bắt `except Exception` rồi gán cứng một mã. Ảnh đã qua `_decode()` trước
đó rồi, nên tới bước này "không giải mã được" vốn đã không còn là cách giải thích hợp lý cho
bất cứ lỗi nào.

**✅ Đã làm**: mã mới `INFERENCE_FAILED` (audience `system`, hint nói thẳng *"không phải lỗi
ảnh — cho chạy lại, đừng loại nó"*), HTTP `503` + `Retry-After` thay vì `400`.

**Nguyên nhân bên dưới**: GPU là tài nguyên **dùng chung**. `nvidia-smi` cho thấy một service
`VLLM::EngineCore` đang giữ **77.8 / 81.5 GB** (vLLM mặc định pre-allocate `gpu_memory_utilization=0.9`),
chỉ chừa ~2.9GB. Van cũ `MAX_CONCURRENCY=16` thả 16 lần suy luận cùng lúc vào chỗ đó.

**Tách hai van cho hai tài nguyên** — đây mới là bài học kiến trúc:

| Van | Theo cái gì | Vì sao |
|---|---|---|
| `MAX_CONCURRENCY` | số nhân CPU | phần CPU chiếm **62%** thời gian mỗi ảnh, cần song song để nhanh |
| `GPU_CONCURRENCY` | VRAM còn trống | VRAM dùng chung với service khác, tràn là **cả hai cùng chết** |

Gộp làm một thì luôn phải hy sinh một bên: hoặc bỏ phí 64 nhân CPU, hoặc làm sập vLLM bên cạnh.
Thêm `QC_SCANNER_GPU_MEM_LIMIT_MB` đặt trần arena (mặc định onnxruntime để arena tự lớn dần theo
luỹ thừa 2 và có thể giành hết phần còn trống).

`bench` cũng thôi tự sát khi một mức luồng thất bại — ca thật: OOM ở `jobs=8` làm chết cả script,
mang theo mục BATCH, đúng mục cần nhất.

---

### ⚡ SPD-7 · P2 · 🟡 CÓ CỜ, MẶC ĐỊNH TẮT · "Chặng suy luận" hoá ra 96% là resize {#spd-resample}

Số quyết định, lấy từ cùng một lần chạy `bench` trên H100:

```
BATCH  batch=1  →   6.5 ms/ảnh     ← ort.run THẬT SỰ trên GPU
CHẶNG  suy luận → 187.4 ms/ảnh
```

**180ms trong "chặng suy luận" không hề chạy trên GPU.** Đó là hai phép LANCZOS của PIL bên
trong `predict()` của rembg: hạ ảnh gốc xuống 320×320, rồi **phóng mask 320×320 ngược lên đúng
kích thước ảnh gốc**. Phép phóng thứ hai là công toi hoàn toàn — lõi QC nhận xong hạ ngay về
`work_height=500`. Đo riêng trên ảnh 3024×4032: hạ 43ms, phóng 26ms.

**Cách bỏ mà không đụng chất lượng suy luận**: tự resize xuống đúng 320×320 (cùng LANCZOS,
cùng tham số) trước khi gọi `predict()`. Khi đó cả hai phép resize bên trong thành **no-op** —
PIL trả `copy()` khi kích thước đã khớp. Tensor vào model **không đổi một bit**, mask 320×320
ra y hệt. Lấy kích thước từ chữ ký ONNX chứ không hardcode 320 (isnet dùng 1024).

Đo ghép cặp xen kẽ trên ảnh 3024×4032: **413ms → 370ms, tiết kiệm 43ms/ảnh** trên CPU máy phát
triển. Trên máy có GPU tỉ lệ còn cao hơn nhiều.

**Nhưng không miễn phí, nên mặc định TẮT.** Chặng resample cuối đổi (320→work thay vì
320→gốc→work) làm metric trôi: `quad_area_ratio` lệch trung vị **0.14%**, tối đa 0.40%. Đủ nhỏ
với 36/37 ảnh. Ảnh thứ 37 là `04.56.41`, có `quad_area_ratio` **0.9002** trong khi
`no_crop_area_ratio` là **0.90** — biên **0.02%**. Trôi xuống 0.8980 là nó ăn `CONTENT_CLIPPED`
→ `fail`, dù đã soi mắt thường và crop ra nguyên tờ (xem QC-16). Tức **một false fail**.

43ms không đáng đổi lấy một ảnh tốt bị loại. Bật bằng `QC_SCANNER_SEGMENT_AT_MODEL_SIZE=1` sau
khi đã chạy `qc-scanner-batch` trên ảnh thật của mình và đối chiếu verdict trước/sau.

**Đã thử và bỏ**: knob `segment_height` (hạ ảnh xuống 1200–2000 trước khi tách nền). Quét trên
37 ảnh cho thấy ≥1200 không đổi phán quyết, nhưng số đo tốc độ **tăng đều theo thứ tự chạy** —
tức là throttle nhiệt của máy đo, không phải hiệu ứng thật. Ảnh trong tập thử đa số dưới 1400px
nên phép hạ mẫu gần như không làm gì. Bỏ đi thay vì giữ một knob không chứng minh được lợi ích.

**Bug bắt được nhân tiện**: mask và `work` từng được resize bằng hai đường độc lập, chỉ khớp
nhau nhờ cùng xuất phát từ một kích thước. Thêm bất kỳ bước hạ mẫu nào ở giữa là làm tròn lệch
1px và `cv2.bitwise_and` vỡ. Nay ép mask về **đúng** `work.shape` — khớp theo cấu trúc, không
theo may mắn.

---

### 🎯 QUAL-4 · P2 · ⚪ · Ca `04.56.41` nằm cách ngưỡng 0.02% {#qual-knife-edge}

`quad_area_ratio = 0.9002` với `no_crop_area_ratio = 0.90`. Ảnh này đã **lật verdict hai lần**
trong cùng một đợt làm việc, mỗi lần vì một thay đổi hoàn toàn khác nhau và không lần nào liên
quan tới chất lượng ảnh — chỉ vì số thứ tư sau dấu phẩy.

Nó đang là **một ảnh chặn một tối ưu 43ms/ảnh** ([SPD-7](#spd-resample)), và nó sẽ còn chặn
những thay đổi khác nữa.

Vấn đề không phải ngưỡng 0.90 sai, mà là nhánh miễn trừ trong `_content_reasons` dùng **một
ngưỡng cứng** cho một đại lượng liên tục. Hướng: vùng đệm (0.88–0.92 thì không phát
`CONTENT_CLIPPED` nhưng hạ xuống `warn`), hoặc gộp thêm `detector_confidence` như `NO_CROP_DETECTED`
đã làm. **Chưa sửa** vì sửa ngưỡng phải kèm số đo trên tập vàng của khách ([EX-2](need_exchange.md)),
mà một ảnh thì chưa đủ để chốt hình dạng vùng đệm.

---

### ⚡ SPD-5 · P1 · 🟡 ĐÃ ĐO SƠ BỘ, CHỜ SỐ TRÊN MÁY H100 · Dynamic batching cho 700 CCU {#spd-batching}

**Câu hỏi**: API có thể phải chịu ~700 CCU; gom nhiều ảnh thành một batch rồi đẩy lên GPU một
lần có giúp không?

**Phát hiện chặn đường**: file ONNX u2net xuất ra với **batch đóng cứng bằng 1**:

```
input : input.1 [1, 3, 320, 320]
batch=2 → InvalidArgument: Got invalid dimensions for input: input.1
```

Nên dynamic batching hiện tại **không chạy được** dù có muốn. Sửa được: U²-Net toàn tích chập
nên vá trục batch thành động (`dim_param = "N"`) là chấp nhận được — đã kiểm chạy batch 1/2/4
trên CPU. Nhưng kết quả **không trùng bit** với chạy lẻ: lệch tối đa `2.086e-07`. Ở mức đó, sau
khi min-max chuẩn hoá → ép uint8 → ngưỡng `>0` thì gần như chắc chắn cho mask giống hệt, nhưng
"gần như chắc chắn" **không phải** thứ được phép giả định ở dự án này — phải chạy lại 37 ảnh và
đối chiếu byte trước khi dùng.

**Nhưng đó không phải lý do chính để dè dặt.** Batching chỉ nén được phần **suy luận**. Đo trên
ảnh cỡ thật (3024×4032, đúng cỡ ảnh điện thoại — đây là chỗ dễ đo sai nhất, ảnh 500px sẽ cho
một con số đẹp và vô dụng):

| Chặng | ms/ảnh | Batching giúp? |
|---|---|---|
| giải mã ảnh | ~30 | ❌ CPU |
| suy luận rembg | ~370 | ✅ |
| phần còn lại (resize, mã hoá PNG…) | ~190 | ❌ CPU |

Trên CPU thì suy luận áp đảo nên batching có vẻ hấp dẫn. **Trên H100 tỉ lệ đảo ngược**: phần
suy luận co lại còn vài ms, và ~220ms CPU mỗi ảnh trở thành toàn bộ nút cổ chai — thứ mà
batching **không chạm tới được**. Khi đó gom batch là tối ưu đúng vào chỗ đã hết chậm.

**Cách chốt**: [`qc-scanner-bench`](../src/qc_scanner/bench.py) đo thẳng cả hai số trên máy đích
và tự in ra kết luận. Con số cần so là *ms/ảnh tiết kiệm được nhờ batch* với *ms CPU mỗi ảnh* —
không phải "batch nhanh gấp mấy lần".

**Đường rẻ hơn nên thử trước**: nhân số tiến trình. Phần CPU song song hoá hoàn hảo giữa các
container, u2net chỉ ~176MB nên nhiều container dùng chung một H100 thoải mái về VRAM, và
không phải viết hàng đợi batching nào cả. `bench` in luôn bảng "cần bao nhiêu tiến trình cho
700 CCU".

**Còn phải chốt với khách**: "700 CCU" tự nó **chưa phải một yêu cầu về tải**. 700 người mỗi
phút gửi một ảnh là 11.7 ảnh/s; 700 người gửi liên tục là hàng trăm ảnh/s. Chênh nhau hai bậc
và ra hai kiến trúc khác hẳn nhau. Xem [EX-16](need_exchange.md#ex-throughput).

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

### 🔬 S-5 · P3 · ⚪ · Dewarping: nắn giấy CONG, không chỉ phối cảnh phẳng {#s-dewarp}

> **📏 Đã ĐO 2026-08-05 → hạ từ P1 xuống P3, hoãn.** Khách cũng xác nhận giấy cong là **hiếm**
> trong kho ảnh thật.
>
> **Cách đo**: giấy phẳng thì 4 mép là đoạn thẳng; giấy cong/vênh thì mép phình ra khỏi dây
> cung nối hai góc. Đo độ lệch lớn nhất của contour so với dây cung, chia cho chiều dài mép →
> *tỉ lệ vồng*, không phụ thuộc kích thước ảnh. Đo trên **mép** chứ không trên dòng chữ vì mép
> đã có sẵn trong pipeline (contour + 4 góc), không phải dựng thêm bộ dò dòng chữ.
>
> **Kết quả trên 36 ảnh** (9 đợt 1 + 20 đợt 2 + 7 ảnh mẫu):
>
> | Nhóm | trung vị | p90 | max |
> |---|---|---|---|
> | tmp đợt 1 (n=9) | 0.051 | 0.355 | 0.355 |
> | tmp_2 đợt 2 (n=20) | 0.021 | 0.175 | 0.305 |
> | examples (n=7) | 0.039 | 0.072 | 0.072 |
>
> **5 giá trị cao nhất đều là ảnh mà bước TÁCH NỀN đã sai** (`abc1b13…` bắt mặt bàn, `2aOboQp…`
> bắt cả xấp giấy, `40b9f8b…` không cắt được gì) — mép "vồng" đó là biên của vật khác, không
> phải giấy cong. Bỏ nhóm này ra thì giá trị lớn nhất còn **0.074**, mà ngay cả ảnh mẫu *phẳng
> đã biết* (doc-4/5/6) cũng cho 0.069–0.072. Nghĩa là **0.07 là sàn nhiễu của mask rembg, không
> phải độ cong thật**. Không ảnh nào trong tay vượt sàn đó.
>
> **Kết luận**: không có bằng chứng nào đòi dewarping trong tập ảnh hiện có → **không làm**,
> tiết kiệm 1 tuần+.
>
> ⚠️ **Giới hạn của phép đo, phải nói thẳng**: nó bắt được giấy cong kiểu *vênh mép* (hoá đơn
> cuộn tròn), nhưng **bỏ sót** tờ phẳng ở mép mà gợn sóng ở giữa, và cũng không bắt được *nếp
> gấp* (tờ chứng nhận mở đôi — nếp là đường gãy, không làm vồng mép ngoài). Bằng chứng dứt điểm
> phải là **một tập ảnh hoá đơn cuộn thật**, thứ chưa có trong mẫu. Mở lại mục này khi có.
>
> 💡 Quan sát phụ đáng ghi: tỉ lệ vồng cao lại là **tín hiệu tách nền sai** rất sạch trên mẫu
> này (5/5). Có thể thành một metric rẻ tiền sau, nhưng chưa đủ dữ liệu để chốt ngưỡng.

<details><summary>Bối cảnh gốc (trước khi đo)</summary>

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

</details>

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

### 📄 N-08 · P3 · 🟢 XONG · Đầu vào PDF, nhiều trang {#n-pdf}

Khách yêu cầu nhận PDF (2026-08-05). Trước đó mục này nằm trong backlog chờ nhu cầu.

**Bề mặt**: cùng một endpoint, cùng một CLI, cùng một batch — định dạng nhận ra từ **nội dung
file**, không từ tên file hay `Content-Type`. Ảnh rời và PDF một trang giữ hợp đồng cũ **từng
byte**; phía tích hợp hiện tại không phải sửa gì.

| Mặt tiền | PDF một trang | PDF nhiều trang |
|---|---|---|
| `POST /` | như ảnh: PNG + 2 header | JSON `{source, verdict, page_count, pages[]}` — kể cả khi không có `?format=json` |
| `qc-scanner` | như ảnh | trang 1 → `OUTPUT`, còn lại → `OUTPUT.p2.png`… · `--page N` chọn một trang |
| `qc-scanner-batch` | `{stem}.png` | `{stem}.p1.png`… · **một dòng CSV mỗi trang**, có cột `page` |
| `scan_qc()` | như ảnh | ném `PDF_MULTIPAGE` — xem dưới |

**Quyết định 1 — không render ở một DPI chọn sẵn.** Đây là chỗ dễ làm sai nhất, và cái sai
không lộ ra ở khâu đọc file mà ở phán quyết QC. Đo trên một trang scan 300 DPI
(`min_blur_score` = 25):

| Đường đọc | `blur_score` |
|---|---|
| ảnh gốc, chưa qua PDF | 42.65 |
| **lấy thẳng bitmap nhúng** | **44.41** |
| render đúng DPI thật (300) | 36.91 |
| render lệch 1 DPI (301) | 27.38 |
| render gấp đôi (600) | **3.46** |

DPI chọn sẵn gần như không bao giờ trùng DPI thật của ảnh bên trong, và lệch lên trên thì
`blur_score` rơi xuống dưới ngưỡng **7 lần** — tức **mọi trang đều `BLURRY`**, một lớp
false-fail sinh ra hoàn toàn từ khâu đọc file. Nên trang scan được lấy thẳng bitmap nhúng ra,
không resample lần nào. Chỉ trang không phải bản scan mới render, ở `pdf_render_dpi`.

Đường lấy-thẳng đòi trang chỉ có **đúng một đối tượng**, chứ không phải "có một ảnh chiếm trọn
trang": nới ra thì mọi thứ vẽ đè lên tấm scan (con dấu, chữ điền bằng máy) **biến mất không
báo gì**. Bỏ 13% `blur_score` rẻ hơn nhiều so với chấm QC trên một trang thiếu nội dung.

**Quyết định 2 — trang PDF là tờ giấy, nên `pre_cropped` bật sẵn** (`pdf_pre_cropped`). Tắt
thì mọi trang scan đều `NO_CROP_DETECTED` → `fail`: `quad_area_ratio` 0.994, chạm 4/4 mép —
dấu hiệu "không cắt được gì" đúng theo nghĩa đen với mọi trang PDF. Cái giá là mất
`CLIPPED_EDGE` khi PDF chỉ là ảnh chụp bọc lại. Chọn theo cùng cân nhắc của
[EX-7](need_exchange.md#ex-7): false fail đắt hơn thiếu một cảnh báo. Chờ khách xác nhận loại
PDF thật — [EX-17](need_exchange.md#ex-pdfkind).

**Quyết định 3 — không cắt bớt trong im lặng.** Quá `pdf_max_pages` (50) thì **không trang nào
được xử lý** (`PDF_TOO_MANY_PAGES`), và `scan_qc()` — vốn trả đúng một kết quả — **từ chối**
PDF nhiều trang (`PDF_MULTIPAGE`) thay vì chấm trang đầu rồi bỏ phần còn lại. Cả hai đều là
cùng một lỗi: phía gọi nhận một câu trả lời và tưởng đã soi hết hồ sơ.

**Verdict gộp là trang tệ nhất**, không phải trang đầu: một bộ hồ sơ có 1 trang không đọc được
thì chưa dùng được, dù 11 trang kia hoàn hảo.

**Bắt được nhân tiện**: `algorithm.md §7` tự nhận là *danh mục* mã lý do nhưng thiếu 3 mã đang
chạy thật (`INFERENCE_FAILED`, `MISSING_FILE`, `DETECTOR_DISAGREEMENT`). Đã bổ sung, và thêm
test khoá danh mục cho khớp với `REASONS` để nó không trôi tiếp.

**PDF ở đầu ra** (`?format=pdf` · `qc-scanner … out.pdf` · `qc-scanner-batch --format pdf`):
mọi trang trong một file, dùng được cho cả ảnh lẫn PDF đầu vào. Ghép **không nén mất dữ liệu**,
vì lý do y hệt lý do đầu ra mặc định là PNG chứ không phải JPEG. Và ở đây không có gì để đánh
đổi — đo trên một trang 1053×1852:

| | Dung lượng |
|---|---|
| PNG (đầu ra hiện tại) | 1276 KB |
| **PDF lossless** | **988 KB** |
| PDF JPEG q92 | 166 KB |

PDF lossless *nhỏ hơn* PNG. Cửa JPEG vẫn có (`pdf_out_jpeg_quality`) nhưng mặc định đóng.
`fail` thì trả lý do chứ không trả file: một PDF trông bình thường cho tài liệu không đọc được
là cách chắc chắn nhất để nó bị dùng tiếp.

Khổ trang là **phỏng đoán** (`pdf_out_dpi`, mặc định 300) vì khổ giấy thật chưa chốt được với
khách ([EX-4](need_exchange.md)). Có test khoá việc nó **không** đụng tới số điểm ảnh.

Phụ thuộc mới: `pypdfium2` (Apache-2.0/BSD, wheel thuần, không cần binary ngoài — khác
`pdf2image` cần poppler và PyMuPDF là AGPL). 37 test ở
[tests/test_pdf.py](../tests/test_pdf.py).

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
| ~~N-08~~ | 🟢 **Đầu vào PDF / đa trang** | P3 | Xong — xem [N-08](#n-pdf) bên dưới |
| N-09 | Hậu xử lý làm nét/khử bóng (adaptive threshold, shadow removal) | P3 | Đầu ra "giống bản scan"; chờ chốt EX-5 |
| ~~N-10~~ | 🟡 onnxruntime-gpu tùy chọn | P3 | Đã viết, **chưa chạy thử** — xem [SPD-4](#spd-gpu) |

---

## Cách dùng file này
- Raise issue mới: thêm mục vào §A–§D với mã tăng dần, priority, `path:line` bằng chứng.
- Đóng issue: đổi 🔴→🟢, ghi commit/PR đã sửa + số đo trước/sau nếu là thay đổi chất lượng.
- Issue về **chất lượng nắn** phải kèm ảnh ví dụ sai + metric (xem [test_eval.md](test_eval.md)).
- Thêm **reason code** mới: khai báo đủ hint + audience trong
  [algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes), kèm ca test.
