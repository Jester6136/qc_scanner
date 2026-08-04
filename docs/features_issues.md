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

## A. ISSUES — Chặn mục tiêu QC (làm trước)

### 🎯 VẤN ĐỀ GỐC: qc_scanner hiện KHÔNG nói được vì sao {#root-no-qc}

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

---

### 🐞 BUG-1 · P0 · 🔴 · `rembg` chạy HAI LẦN ở đường CLI {#bug-double-rembg}

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

---

### 🐞 BUG-2 · P0 · 🔴 · `scan()` nuốt mọi exception, trả `None` {#bug-swallow}

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

---

### 🧱 QC-1 · P0 · 🔴 · Chưa có kiểu `ScanResult` (verdict + reasons + metrics) {#qc-contract}

Nền móng cho tất cả các mục QC còn lại. Thêm `scan_qc(data) -> ScanResult` theo hợp đồng ở
[algorithm.md §2](algorithm.md#2--hợp-đồng-đầu-ra-qc); giữ `scan()` cũ làm lớp bọc mỏng
(`return scan_qc(data).image`) để **không phá người dùng PyPI hiện tại**.

Bất biến bắt buộc: `verdict == "pass"` ⟺ `reasons == []`.

---

### 🧱 QC-2 · P0 · 🔴 · Cài danh mục mã lý do giai đoạn 1 {#qc-codes}

Bảy mã đầu tiên, đủ để xóa mọi nhánh im lặng hiện có: `DECODE_FAILED`, `SUBJECT_NOT_FOUND`,
`QUAD_NOT_FOUND`, `TOO_SMALL`, `CLIPPED_EDGE`, `NOT_CONVEX`, `EXTREME_SKEW`.
Định nghĩa đầy đủ (điều kiện, severity, hint, audience):
[algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes).

**Nguyên tắc không thương lượng**: mã nào cũng phải có `hint` (làm gì tiếp theo) và
`audience` (ai phải làm). Mã không hành động được là mã vô dụng.

---

### 🧱 QC-3 · P1 · 🔴 · Metric đo được đi kèm mọi kết quả {#qc-metrics}

`quad_area_ratio`, `contour_candidates`, `skew_ratio`, `is_convex`, `touches_border`,
`est_dpi`, `blur_score`, `alpha_coverage`, `fallback_used`.

Không có metric thì không chốt được ngưỡng bằng số đo — chỉ đoán. Đây cũng là dữ liệu để
tinh chỉnh ngưỡng trên tập vàng (Giai đoạn 3) và để dựng báo cáo QC hàng loạt (N-01).

---

### 🧱 QC-4 · P1 · 🔴 · Bề mặt hóa QC ra cả 3 mặt tiền {#qc-surface}

- **CLI**: exit code theo verdict (0 pass · 1 warn · 2 fail) + báo cáo JSON ra stderr hoặc
  `--report out.json`. Ảnh vẫn ra stdout (không phá pipe hiện tại).
- **Server**: mặc định trả PNG + header `X-QC-Scanner-Verdict` / `X-QC-Scanner-Reasons`;
  `?format=json` trả `ScanResult` đầy đủ. HTTP status: 200 pass/warn, **422** fail, 400 input hỏng.
- **Library**: `scan_qc()` trả `ScanResult`.

---

### 🧱 QC-7 · P1 · ⚪ · Fallback dò cạnh khi rembg thua {#qc-edge-fallback}

Ca hay gặp nhất: **giấy trắng trên nền sáng** → rembg không tách được (`alpha_coverage` gần 0
hoặc gần 1). Thay vì fail ngay, chạy Canny + HoughLinesP → giao điểm → tứ giác ứng viên;
qua được bộ lọc thì dùng, hạ verdict xuống `warn` kèm `RECOVERED_BY_EDGE_FALLBACK`.
Thuật toán: [algorithm.md §6](algorithm.md#6--fallback-dò-cạnh-khi-rembg-thất-bại).

Đây là mức "hơn cả thế" của mục tiêu QC: **tự khắc phục trước, rồi mới báo** — nhưng không
bao giờ giấu việc đã phải dùng đường lui.

---

### 🧱 QC-9 · P2 · ⚪ · Nhiều tài liệu trong một ảnh bị âm thầm bỏ qua {#qc-multi}

Vòng lặp [doc.py:48-56](../src/qc_scanner/doc.py#L48-L56) `break` ngay ở tứ giác đầu tiên. Chụp
2 tờ trong một khung → tờ thứ hai **biến mất không dấu vết**.

**Hướng**: đếm contour có diện tích ≥ 5% ảnh (`contour_candidates`); ≥2 → reason
`MULTIPLE_DOCUMENTS` (warn). Về sau có thể trả **nhiều** ảnh đầu ra (Giai đoạn 5).

---

## B. ISSUES — Bảo mật & đúng đắn {#b-issues--bảo-mật--đúng-đắn}

### 🔒 SEC-1 · P0 · 🔴 · SSRF + đọc file nội bộ qua `GET /?url=` {#sec-ssrf}

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

---

### 🐞 BUG-3 · P1 · 🔴 · So sánh `bytes` với `str` → file rỗng lọt qua {#bug-empty-check}

[server.py:31](../src/qc_scanner/cmd/server.py#L31): `if file_content == "":`. Nội dung file là
**`bytes`**, và `b"" == ""` luôn `False` trong Python 3 → **chốt chặn này không bao giờ kích
hoạt**. Upload file rỗng đi thẳng vào `scan()` → rembg/`imdecode` lỗi → 500 "oops".

**Hướng**: `if not file_content:` (bắt cả `b""` lẫn `""`), trả 400 kèm mã `FILE_EMPTY` + hint.

---

### 🐞 BUG-4 · P1 · 🔴 · `img.shape[2]` vỡ trên ảnh grayscale {#bug-shape}

[doc.py:33](../src/qc_scanner/doc.py#L33) truy cập `img.shape[2]` không kiểm `ndim`. Ảnh
grayscale sau `IMREAD_UNCHANGED` có `shape` 2 chiều → **`IndexError`** → bị BUG-2 nuốt →
"oops". Bình thường rembg luôn trả RGBA, nhưng khi rembg thất bại/đổi hành vi (hoặc do BUG-1
chạy hai lần) thì nhánh này phát nổ với thông báo vô nghĩa.

**Hướng**: kiểm `img.ndim == 3 and img.shape[2] == 4`; không đạt → reason `SUBJECT_NOT_FOUND`
(kèm hint đổi nền) thay vì `ValueError` chung chung. Thông báo hiện tại — "The image lacks an
alpha channel for background removal" — mô tả *triệu chứng kỹ thuật*, không nói người dùng
phải làm gì; đúng thứ QC-3 phải thay.

---

### ⚠️ OPS-1 · P2 · 🔴 · Server không giới hạn kích thước upload, xử lý đồng bộ {#ops-server-limits}

Không `MAX_CONTENT_LENGTH`, không timeout. Mỗi request chạy rembg **đồng bộ** trong worker
thread của waitress (mặc định 4 thread) → 5 ảnh lớn cùng lúc là server treo. Request **đầu
tiên** còn cộng thời gian **tải model rembg** (vài chục MB) → dễ timeout ở tầng proxy.

**Hướng**: `app.config["MAX_CONTENT_LENGTH"]`; pre-warm model lúc khởi động (nạp sẵn session,
liên quan N-06); tài liệu hóa số thread; cân nhắc hàng đợi nếu cần chịu tải thật.

---

### ⚠️ OPS-2 · P2 · 🔴 · Thư mục local không phải git repo {#ops-no-git}

`/Users/bags/prj/collab-prj/qc_scanner` **không có `.git`** — mọi thay đổi hiện không được version
control, không rollback được. Đợt đổi tên 2026-08 (`docscan` → `qc_scanner`, xoá `LICENSE.txt`
và `MANIFEST.in`) vì vậy **không có lịch sử để đối chiếu hay hoàn tác**.

**Hướng**: `git init` + commit hiện trạng **trước khi** sửa dòng code đầu tiên. Nếu cần đối
chiếu với bản gốc, upstream `danielgatis/docscan` vẫn còn trên GitHub.

---

## C. ISSUES — Chất lượng thuật toán

### 🎯 QUAL-1 · P1 · 🔴 · Lấy tứ giác ĐẦU TIÊN, không lọc rác {#qual-quad-filter}

[doc.py:48-56](../src/qc_scanner/doc.py#L48-L56) duyệt contour theo diện tích giảm dần và `break`
ở đa giác 4 đỉnh đầu tiên. **Không kiểm**: lồi, diện tích tối thiểu, tỉ lệ cạnh, có chạm mép ảnh
không. Một vệt nhiễu vuông vắn hoặc một ô trong bảng có thể thắng tờ giấy thật.

**Hướng**: duyệt hết ứng viên, cho điểm bằng bộ lọc — `isContourConvex`, `quad_area_ratio ≥ 0.2`,
`skew_ratio ≤ 1.8` — chọn ứng viên tốt nhất; không ứng viên nào đạt → `QUAD_NOT_FOUND` với
lý do cụ thể (bằng chính metric đã tính). Bộ lọc này **dùng chung** với QC-2/QC-3 — một lần
tính, vừa để chọn vừa để giải thích.

---

### 🎯 QUAL-2 · P2 · 🔴 · Hằng số cứng không scale theo ảnh {#qual-scale}

`IMG_RESIZE_H = 500.0` và `medianBlur(img, 15)` — [doc.py:11, 38](../src/qc_scanner/doc.py#L11).
Ảnh cao 300px bị **phóng to** lên 500 (bịa thông tin); ảnh 4000px bị thu 8× rồi blur ksize 15
có thể nuốt luôn góc giấy nhỏ. `APPROX_POLY_DP_ACCURACY_RATIO = 0.02` cũng chưa từng được
kiểm chứng bằng số đo.

**Hướng**: không upscale (`min(h, 500)`); ksize blur suy theo kích thước làm việc (lẻ, ~3% chiều
cao); quét ε trên tập vàng rồi mới chốt (QUAL-3 / Giai đoạn 3).

---

### 🔬 S-1 · P1 · ⚪ · Model nền của rembg đã cũ (U²-Net, mặc định) {#s-model-swap}

rembg mặc định dùng **U²-Net** — mô hình *salient object detection* đời 2020, huấn luyện cho
"vật thể nổi bật" nói chung, **không biết khái niệm tờ giấy**. rembg hiện đã hỗ trợ các model
tốt hơn (`isnet-general-use`, **BiRefNet**) — đổi bằng **một tham số `session`**, không đổi
kiến trúc, rủi ro gần bằng 0.

**Hướng**: sau khi có bộ eval ([test_eval.md §5](test_eval.md)), chạy so ba model trên cùng tập
vàng, chốt mặc định bằng số. Đây là **việc rẻ nhất trong toàn bộ roadmap** — làm trước S-3.
Khảo sát: [algorithm.md §8.1-B](algorithm.md#81-các-họ-phương-pháp-hiện-có).

---

### 🔬 S-2 · P1 · ⚪ · Chưa tách interface `Detector` — bị khoá vào một phương pháp {#s-detector-iface}

Việc dò biên hiện dính chặt vào `scan()`: rembg → contour → approxPolyDP, không thay được từng
mảnh. Muốn thử phương pháp khác phải viết lại hàm.

**Hướng**: `Detector.find_quad(img) -> QuadCandidate | None` (4 điểm + confidence + tên
detector); ba cài đặt: `rembg-contour` (hiện tại), `docaligner` (S-3), `edge-hough`
([QC-7](#qc-edge-fallback)). Lõi QC nhận `QuadCandidate` từ bất kỳ detector nào → **đổi
detector là đổi một dòng cấu hình**, và chạy được **hai detector song song trên cùng tập vàng**
để so bằng số thay vì cảm tính.

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

### 🔬 S-6 · P2 · ⚪ · Bất đồng giữa hai detector = tín hiệu QC miễn phí {#s-disagreement}

Khi có ≥2 detector (S-2): chúng cho **cùng** tứ giác → độ tin cậy cao; **lệch nhau** (IoU thấp)
→ reason `DETECTOR_DISAGREEMENT` (warn), cho người soi. Không cần model mới, không cần nhãn —
tận dụng thứ đã có. Chỉ làm sau khi S-2/S-3 xong.

---

### 🔬 S-5 · P3 · ⚪ · Dewarping: nắn giấy CONG, không chỉ phối cảnh phẳng {#s-dewarp}

`four_point_transform` chỉ sửa được biến dạng **phẳng**. Giấy cong, gập nếp, sách đóng gáy →
sau khi nắn **vẫn méo**, dòng chữ vẫn cong → OCR vẫn sai. Họ phương pháp giải quyết: dự đoán
**lưới biến dạng** thay vì 4 điểm — UVDoc, DocTr++, DocRes, D²Dewarp/DocMatcher (2025).

**Chưa quyết**: đắt và phức tạp, và **có thể không giải quyết vấn đề nào của khách** nếu hồ sơ
đều được ép phẳng. Chốt qua [need_exchange.md EX-5](need_exchange.md) trước, đo sau, làm sau cùng.

---

### 🎯 QUAL-3 · P2 · ⚪ · Chưa quét ngưỡng trên tập vàng {#qual-sweep}

Mọi ngưỡng trong §7 algorithm (0.20 diện tích, 1.8 skew, 150 DPI, ngưỡng blur) hiện là **ước
đoán**. Phải chốt bằng số đo trên tập vàng thật của khách — xem
[test_eval.md §5](test_eval.md) và `need_exchange.md` EX-2.

---

## D. ISSUES — Đóng gói & phụ thuộc

### 📦 DEP-1 · P1 · 🔴 · `requirements.txt` không ghim version nào {#dep-pin}

Tám dòng, **không dòng nào có version**: `click flask imutils numpy onnxruntime opencv-python
rembg waitress`. `rembg` là dependency biến động nhất (API `remove()` đã đổi qua các bản: thêm
`session`, alpha matting, tách `rembg[cli]`), và `setup.py` đọc thẳng file này làm
`install_requires` — [setup.py:9-10](../setup.py#L9-L10). Người cài hôm nay và tháng sau **không
nhận cùng phần mềm**, còn chất lượng đầu ra thì đổi thầm lặng.

**Hướng**: ghim dải tương thích (`rembg>=2.0,<3`, `opencv-python>=4.8,<5`, …); tách
`requirements-dev.txt` cho test; regression test trên `examples/` để bắt trôi chất lượng khi nâng.

### 📦 PKG-1 · P2 · 🔴 · `python_requires=">=3.5, <4"` sai thực tế {#pkg-pyversion}

[setup.py:20](../setup.py#L20). rembg/onnxruntime/numpy hiện đại cần **≥3.9**. Khai báo sai
khiến pip cho phép cài trên môi trường chắc chắn gãy. **Hướng**: `>=3.9,<4`, xác nhận bằng CI.

### 📦 PKG-2 · P3 · 🔴 · Version hardcode trong `setup.py` {#pkg-version}

`version="1.0.6"` — [setup.py:15](../setup.py#L15) — không có `__version__` trong package
([`src/qc_scanner/__init__.py`](../src/qc_scanner/__init__.py) rỗng), nên runtime không tự biết mình
là bản nào (log/báo cáo QC cần thông tin này). **Hướng**: `__version__` trong `__init__.py`
làm nguồn sự thật, `setup.py` đọc lại.

### 📦 PKG-3 · P3 · 🔴 · Import thừa {#pkg-imports}

`os`, `sys` ở [doc.py:1-2](../src/qc_scanner/doc.py#L1-L2) (`sys` có dùng cho stderr, `os` thì
không); `glob`, `os` ở [cli.py:1-2](../src/qc_scanner/cmd/cli.py#L1-L2) — `glob` có lẽ là dấu vết
của ý định làm batch CLI (xem N-01). **Hướng**: dọn, thêm linter vào CI (N-05).

### 📦 PKG-4 · P2 · 🔴 · Không có test, không có CI {#pkg-notest}

Không thư mục `tests/`, không `pytest`, không workflow chạy test. 8 cặp ảnh trong `examples/`
là **tài sản chưa dùng** — chúng chính là bộ regression sẵn có.
Xem [test_eval.md §2](test_eval.md).

---

## E. FEATURES — Đã có (đã ship)

| Mã | Tính năng | Ghi chú |
|----|-----------|---------|
| F-01 | Hàm lõi `scan(bytes) -> bytes`: tách nền → dò biên → nắn phối cảnh → PNG | [doc.py:14](../src/qc_scanner/doc.py#L14) |
| F-02 | CLI `qc-scanner`: stdin/stdout pipe **hoặc** đối số file vào/ra | [cmd/cli.py](../src/qc_scanner/cmd/cli.py) |
| F-03 | HTTP server `qc-scanner-server`: `POST /` form-file, `GET /?url=` | [cmd/server.py](../src/qc_scanner/cmd/server.py) (GET-url: xem SEC-1) |
| F-04 | Fallback trả ảnh gốc khi không tìm được biên | [doc.py:59-60](../src/qc_scanner/doc.py#L59-L60) — đúng ý tưởng, **sai ở chỗ im lặng** (QC-1) |
| F-05 | Đóng gói setuptools + 2 console script (`qc-scanner`, `qc-scanner-server`) | [setup.py:22-27](../setup.py#L22-L27) |
| F-06 | 8 cặp ảnh mẫu input/output | [examples/](../examples/) — dùng làm fixture regression |

## F. FEATURES — Đề xuất (backlog)

| Mã | Tính năng | Ưu tiên | Ghi chú |
|----|-----------|---------|---------|
| N-01 | **Batch CLI + báo cáo QC tổng hợp** (CSV: file, verdict, reason, metric) | P1 | Dạng "QC" vận hành cần nhất; `glob` đã import sẵn (PKG-3) |
| N-02 | Tham số hóa qua CLI/env (ngưỡng, kích thước làm việc, bật/tắt rembg) | P2 | Điều kiện để quét ngưỡng (QUAL-3) |
| N-03 | Chế độ debug: xuất ảnh trung gian (mask, contour, tứ giác chọn) | P2 | Công cụ chính khi soi ca sai |
| N-04 | Dockerfile + pre-warm model rembg trong image | P2 | Bỏ độ trễ lần chạy đầu (OPS-1) |
| N-05 | CI: cài sạch + test + lint + build wheel | P2 | Chặn hồi quy (PKG-4) |
| N-06 | Tái dùng `rembg` session giữa các call | P2 | **Đòn bẩy tốc độ chính** (chặng chiếm ~95%) |
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
