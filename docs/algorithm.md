# Thuật toán luồng xử lý qc_scanner

> Mô tả **thuật toán** của luồng chính (ảnh chụp → tách nền → dò biên → nắn phối cảnh → PNG),
> kèm **hợp đồng đầu ra QC** đang hướng tới. Nguồn sự thật là code; tài liệu này giải thích
> *vì sao* và *cách* các bước ghép lại. Tham chiếu ghi dạng `path:line` để tra ngược.
>
> ✅ Cập nhật 2026-08-05: §2, §6, §7 **đã được cài đặt**. §1 mô tả thuật toán cũ và được giữ
> lại để đối chiếu — §1b bên dưới mô tả luồng đang chạy.

---

## 0. Bức tranh tổng thể

```
 ảnh / PDF (bytes)
        │
        ▼
 ┌──────────────────────┐   PDF → lấy thẳng bitmap nhúng, hoặc render     (pdf.py)
 │  đọc thành ảnh BGR   │   ảnh → cv2.imdecode, một lần duy nhất
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐   rembg / U²-Net → mask xám cùng cỡ ảnh
 │  tách chủ thể        │   (không đi vòng qua PNG RGBA toàn cỡ)   (rembg_session.py)
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐   hạ về work_height · threshold · medianBlur
 │  dò + chọn tứ giác   │   findContours → approxPolyDP → LỌC → chọn tốt nhất
 └──────────┬───────────┘   rembg thua → đường lui edge-Hough        (detect.py)
            ▼
 ┌──────────────────────┐   metric hình học + nội dung + chất lượng
 │  chấm điểm           │   → reasons[] → verdict                     (qc.py)
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐   nới cạnh bao trọn mép giấy cong
 │  nắn + mã hoá        │   four_point_transform trên ảnh GỐC → PNG   (geometry.py)
 └──────────┬───────────┘
            ▼
   ScanResult{image, verdict, reasons[], metrics}
```

Một lõi, ba mặt tiền gọi chung. Không state, không I/O ngoài (trừ rembg tải model lần đầu),
không hàng đợi.

| Cửa vào | Nhận | Trả |
|---|---|---|
| `scan_document(bytes)` | ảnh **hoặc** PDF | `DocumentResult` — một `ScanResult` mỗi trang |
| `scan_qc(bytes)` | ảnh, hoặc PDF **một trang** | `ScanResult` |
| `scan_image(ndarray)` | ảnh BGR đã giải mã | `ScanResult` |
| `scan(bytes)` | ảnh | `bytes` PNG — API cũ, **không mang phán quyết** |

Mặt tiền: [`cmd/cli.py`](../src/qc_scanner/cmd/cli.py) ·
[`cmd/server.py`](../src/qc_scanner/cmd/server.py) ·
[`cmd/batch.py`](../src/qc_scanner/cmd/batch.py) · library.

---

## 1. `scan_qc()` — luồng đang chạy

```
scan_qc(data, config) -> ScanResult
 1. data rỗng                         → ScanError(FILE_EMPTY)
 2. orig = imdecode(data)             → None thì ScanError(DECODE_FAILED)
 3. rgba = rembg(data, session dùng lại)          # gọi ĐÚNG MỘT LẦN, mọi mặt tiền
 4. work  = hạ mẫu về work_height (KHÔNG phóng to ảnh nhỏ hơn)
    mask  = threshold(alpha) → medianBlur(ksize ≈ 3% chiều cao)
    metrics.alpha_coverage = tỉ lệ pixel alpha > 0
 5. quad = detector.find_quad(...)    # MẶC ĐỊNH: docaligner — hồi quy thẳng 4 góc,
                                      # nhận ảnh CHƯA bôi nền đen (Detector.uses_mask)
    mask_candidates = contour trong mask   # luôn tính, độc lập detector — MULTIPLE_DOCUMENTS
                                           # đếm ở đây, không đếm ứng viên của detector
 6. nếu quad None và detector chính KHÔNG phải rembg:
        thử rembg-contour → qua lọc thì dùng + RECOVERED_BY_MASK_FALLBACK (warn)
        (docaligner trả rỗng với ảnh ĐÃ cắt sẵn: không còn nền quanh giấy để nhận ra
         "có tài liệu" — mọi trang PDF rơi vào đây)
    nếu vẫn None HOẶC alpha_coverage < 0.05:
        thử đường lui edge-hough → qua lọc thì dùng + RECOVERED_BY_EDGE_FALLBACK (warn)
    (QC-16: KHÔNG chạy đường lui khi rembg tìm thấy *quá nhiều* — đo thấy nó ghi đè
     tứ giác đúng bằng tứ giác sai, thắng 0/3 trên ảnh thật)
 7. vẫn không có quad → trả ảnh GỐC + QUAD_NOT_FOUND/SUBJECT_NOT_FOUND + FALLBACK_ORIGINAL
    (fail).  Khác bản cũ ở đúng một chỗ: **có nhãn**.
 8. metric hình học → reasons: NOT_CONVEX · TOO_SMALL · EXTREME_SKEW · CLIPPED_EDGE
    tứ giác gần trọn khung + chạm ≥3 mép + detector THUA → NO_CROP_DETECTED (thay CLIPPED_EDGE)
    có cắt thật, mà chỗ cắt CÓ MỰC → CONTENT_CLIPPED (thay CLIPPED_EDGE)
    ≥2 contour trong mask → MULTIPLE_DOCUMENTS
    cross-check bật → IoU hai detector thấp → DETECTOR_DISAGREEMENT
 9. QC-17: nới 4 cạnh ra bao trọn contour (mép giấy cong vồng ra ngoài dây cung)
    warp trên ảnh GỐC, PNG
10. metric chất lượng → LOW_RESOLUTION · BLURRY · GLARE · TOO_DARK
    QC-18: đo góc dòng chữ TRÊN ẢNH ĐÃ NẮN → lệch > 8° → TEXT_NOT_LEVEL (fail).
    Bước duy nhất kiểm **kết quả** thay vì phỏng đoán từ đầu vào.
10b. QC-19: xoay về thẳng đúng góc vừa đo — nhưng CHỈ trong ngưỡng trên.
    Vượt ngưỡng thì không xoay: đó là phép nắn hỏng, xoay chỉ giấu nó đi.
    Chấm điểm TRƯỚC rồi mới xoay, để metric còn nói được ảnh vào lệch bao nhiêu.
11. verdict suy từ reasons; pass ⟺ reasons rỗng
```

`scan()` cũ vẫn còn, là lớp bọc mỏng trả `result.image` — không phá người dùng hiện tại,
nhưng cũng **không mang phán quyết**, nên mã mới nên gọi `scan_qc()`.

Mọi ngưỡng nằm trong [`config.py`](../src/qc_scanner/config.py), override được bằng biến môi
trường `QC_SCANNER_*`.

---

## 2. Hợp đồng đầu ra QC {#hop-dong}

Đây là thay đổi cốt lõi của dự án: **đầu ra không còn là ảnh, mà là một phán quyết kèm ảnh.**

```python
@dataclass
class ScanResult:
    image:    bytes | None      # PNG đã nắn, hoặc best-effort, hoặc None nếu fail cứng
    verdict:  Literal["pass", "warn", "fail"]
    reasons:  list[Reason]      # RỖNG khi và chỉ khi verdict == "pass"
    metrics:  Metrics           # số đo thô, để tra cứu/tinh chỉnh ngưỡng
    
@dataclass
class Reason:
    code:     str               # mã ổn định, vd "QUAD_NOT_FOUND" — xem §7
    severity: Literal["warn", "fail"]
    message:  str               # mô tả người đọc được
    hint:     str               # LÀM GÌ TIẾP THEO — bắt buộc, không được rỗng
    audience: Literal["capturer", "operator", "system"]   # `hint` ở trên viết cho ai
    hints:    dict              # CẢ HAI tầng: {"capturer": ..., "operator": ...}
```

**Hint hai tầng (QC-13)**. Cùng một lý do đọc khác nhau tuỳ người nhận: người chụp còn chụp
lại được, người soi kho ảnh thì không. Luồng gọi khai báo vai — `qc-scanner --audience`,
`POST /?audience=`, `QC_SCANNER_HINT_AUDIENCE` — và `qc-scanner-batch` mặc định `operator`.
Trường `hints` luôn mang đủ cả hai để phía gọi tự hiển thị lại mà không phải xử lý lại ảnh.
Mã `system` không có tầng riêng, rơi về tầng `operator`.

### Quy tắc phán quyết

```
fail  = có ít nhất 1 reason severity=fail   → ảnh KHÔNG dùng được cho OCR
warn  = không có fail, có ≥1 reason         → dùng được nhưng rủi ro, nên soi lại
pass  = reasons rỗng                        → nắn sạch, tin được
```

Bất biến: **`verdict == "pass"` ⟺ `reasons == []`**. Không có "pass kèm ghi chú".

### `metrics` — số đo đi kèm mọi kết quả

| Trường | Ý nghĩa | Dùng để |
|---|---|---|
| `quad_area_ratio` | diện tích tứ giác / diện tích ảnh | bắt `TOO_SMALL`, `TOO_LARGE` |
| `contour_candidates` | số contour có ≥ 5% diện tích ảnh | bắt `MULTIPLE_DOCUMENTS` |
| `skew_ratio` | tỉ lệ cạnh đối dài/ngắn (max của 2 cặp) | bắt `EXTREME_SKEW` |
| `is_convex` | tứ giác có lồi không | bắt `NOT_CONVEX` |
| `touches_border` | số góc nằm sát mép ảnh (< 2px) | bắt `CLIPPED_EDGE` |
| `border_ink_ratio` | mật độ mực sát mép ảnh, ở cạnh tứ giác bị khung cắt; `0.0` khi tứ giác nằm trọn trong ảnh | bắt `CONTENT_CLIPPED` |
| `est_dpi` | ước lượng DPI đầu ra (giả định khổ A4) | bắt `LOW_RESOLUTION` |
| `blur_score` | variance of Laplacian trên ảnh đã nắn | bắt `BLURRY` |
| `text_skew_deg` | góc nghiêng dòng chữ trên ảnh **đã nắn**, đo **trước** khi sửa; `None` = trang quá ít mực để đo | bắt `TEXT_NOT_LEVEL` |
| `deskew_applied_deg` | góc đã thật sự xoay để nắn thẳng; `None` = không xoay | minh bạch (QC-19) |
| `alpha_coverage` | % pixel alpha > 0 sau rembg | bắt `SUBJECT_NOT_FOUND` |
| `fallback_used` | `none` / `edge_detect` / `original` | minh bạch đường đi |

`scan()` cũ giữ nguyên chữ ký (`bytes -> bytes`) như lớp bọc mỏng quanh `scan_qc()`, để không
phá người dùng PyPI hiện tại.

---

## 3. Mặt tiền CLI — [cmd/cli.py](../src/qc_scanner/cmd/cli.py)

Ảnh ra stdout (hoặc file), **phán quyết đi theo exit code**: `0` pass · `1` warn · `2` fail ·
`3` đầu vào không đánh giá được. Báo cáo JSON (reason + hint + metrics) ra stderr, hoặc ra file
với `--report`. Pipe cũ (`cat a.jpg | qc-scanner > b.png`) không vỡ.

PDF nhiều trang: trang đầu vào OUTPUT, các trang sau thành `OUTPUT.p2.png`… — hoặc gộp cả vào
một file nếu OUTPUT có đuôi `.pdf`. Ghi đè mọi trang lên cùng một đích sẽ để lại đúng trang cuối
mà không báo gì, nên ca stdout + nhiều trang bị **từ chối** thay vì làm im lặng.

`qc-scanner-batch` chạy cả thư mục, xuất CSV **một dòng mỗi trang** kèm toàn bộ metric — đây là
hình thức QC mà vận hành tiêu thụ được ở quy mô hàng vạn ảnh.

---

## 4. Mặt tiền HTTP — [cmd/server.py](../src/qc_scanner/cmd/server.py)

Hợp đồng đầy đủ ở [api.md](api.md); `tests/test_api_contract.py` giữ đúng những gì tài liệu đó
hứa. Tóm tắt phần thuật toán quan tâm:

| Status | Nghĩa |
|---|---|
| `200` | pass/warn — PNG kèm header `X-QC-Scanner-Verdict` / `-Reasons`, hoặc JSON/PDF nếu xin |
| `422` | fail — **ảnh hợp lệ** nhưng đầu ra không đáng tin cho OCR. Đừng retry |
| `400` | đầu vào không đánh giá được |
| `503` | kín tải hoặc lỗi tài nguyên — **nên** retry, kèm `Retry-After` |

Ba chỗ mà thuật toán quyết định hình dạng HTTP:

* **`422` tách khỏi `400`** vì "ảnh xấu" và "request sai" đòi hai hành động khác nhau ở phía gọi.
* **`503` tách khỏi `400`** vì lỗi tài nguyên máy chủ **không phải** lỗi ảnh; trả `400` ở đó là
  bảo phía gọi loại vĩnh viễn một tấm ảnh tốt.
* **PDF nhiều trang luôn trả JSON**, kể cả khi không xin — không có hình dạng "một file PNG" nào
  chứa được N trang. Verdict gộp là **trang tệ nhất**.

---


## 5. Chi phí thời gian {#chi-phi}

Đo trên máy server 64 nhân, ảnh 3024×4032 (cỡ ảnh điện thoại thật — đây là chỗ dễ đo sai nhất,
ảnh 500px cho một con số đẹp và vô dụng):

| Chặng | ms/ảnh | Tỉ trọng |
|---|---|---|
| giải mã ảnh | ~52 | 9% |
| suy luận rembg | ~301 | 52% |
| phần còn lại (resize, contour, warp, mã hoá PNG) | ~231 | 39% |
| **tổng** | **~584** | |

⚠️ Bảng trên đo trên **máy server 64 nhân**. Trên máy dev (Apple Silicon) cùng luồng ấy tốn
~1669ms — con số bạn sẽ thấy trong vài docstring của [`geometry.py`](../src/qc_scanner/geometry.py).
Hai số không mâu thuẫn, nhưng đừng trộn chúng vào cùng một phép tính tỉ trọng.

**Đã đổi từ khi chuyển detector mặc định sang DocAligner (S-3b):** riêng chặng dò biên nhanh hơn
**7.8×** (330ms → 42ms trên cùng máy dev), nhưng **tổng thời gian mỗi ảnh lại nhích lên**
(0.395s → 0.436s) vì rembg vẫn phải chạy cho `alpha_coverage`, đường lui, và đếm đa tài liệu.
Muốn thu khoản đó thì phải gỡ rembg khỏi đường chính — việc riêng, chưa làm.

**Kết luận đã đổi so với bản đầu.** Tài liệu này từng ghi "rembg chiếm ~95%, đừng tối ưu
OpenCV". Con số đó đo trên bản **tạo lại session mỗi lần gọi** (~3.0s/ảnh), nên phần nạp model
lấn át tất cả. Bỏ được nó rồi thì tỉ lệ thật lộ ra: **gần một nửa thời gian nằm ngoài rembg**,
và SPD-1 lấy được 1.38x đúng ở phần "đừng tối ưu" đó.

Hai hệ quả còn hiệu lực:

* Phần ngoài rembg chạy trên CPU và **không batch được** — đây là lý do dynamic batching chỉ
  đáng 0.8% ([SPD-5](features_issues.md#spd-batching)).
* Thông lượng bão hoà ở ~16 luồng trong một tiến trình (8.4 ảnh/s). Muốn hơn thì **nhân số
  container**, không phải tối ưu tiếp trong một tiến trình.

Đo lại trên máy đích bằng `qc-scanner-bench` — số ở đây là của một máy cụ thể, không phải hằng số.

---


## 6. Đường lui dò cạnh {#duong-lui}

Ca thường gặp nhất mà rembg chịu thua: **giấy trắng trên nền trắng/sáng** → `alpha_coverage`
gần 0 hoặc gần 1 (nuốt cả ảnh). Khi đó thay vì `fail` ngay, chạy đường lui:

```
nếu alpha_coverage < 0.05 hoặc > 0.95:
    gray  = cvtColor(orig_resized, GRAY); GaussianBlur; Canny(75, 200)
    lines = HoughLinesP(...)
    gom line theo hướng → 2 cụm (ngang / dọc) → lấy 2 line ngoài cùng mỗi cụm
    4 giao điểm → tứ giác ứng viên
    nếu qua được bộ lọc hình học (lồi, diện tích, tỉ lệ):
        dùng tứ giác này; verdict = warn
        reasons += RECOVERED_BY_EDGE_FALLBACK   # minh bạch: kết quả kém tin cậy hơn
    ngược lại:
        verdict = fail; reasons += SUBJECT_NOT_FOUND
```

Đây là mức 3 của mục tiêu QC ("hơn cả thế"): **tự khắc phục trước, rồi mới báo** — nhưng
không bao giờ giấu việc đã phải dùng đường lui.

---

## 7. Danh mục mã lý do {#ma-ly-do}

Nguyên tắc bất biến: **mã nào cũng phải có `hint` và `audience`**. Mã không hành động được
là mã vô dụng.

### Đầu vào

| Mã | Sev | Điều kiện phát hiện | Hướng xử lý (hint) | Ai |
|---|---|---|---|---|
| `DECODE_FAILED` | fail | `imdecode` trả None | File hỏng hoặc sai định dạng, không mở ra được. Xin lại bản gốc. | system |
| `FILE_EMPTY` | fail | `len(data) == 0` | Không có gì để soi. Báo bên gửi kiểm tra bước tải lên. | system |
| `MISSING_FILE` | fail | request HTTP không có trường form `file` | Lỗi tích hợp, không phải lỗi ảnh: request thiếu trường `file`. Báo bên phát triển. | system |
| `SERVER_BUSY` | fail | số request đang bay ≥ `MAX_IN_FLIGHT` | Quá tải tạm thời, **không phải lỗi ảnh** — ảnh chưa được xử lý lần nào. Cho chạy lại. Gặp thường xuyên thì giảm request song song, hoặc thêm container. | system |
| `INFERENCE_FAILED` | fail | model tách nền ném lỗi (hay gặp: hết bộ nhớ GPU) | Lỗi tài nguyên máy chủ (thường là hết bộ nhớ GPU), **không phải lỗi ảnh**. Cho chạy lại, đừng loại ảnh. | system |
| `UNAUTHORIZED` | fail | request thiếu `Authorization: Bearer <key>` hợp lệ | Request không kèm `Authorization: Bearer <key>` hợp lệ. Ảnh **chưa được xử lý lần nào** — đây là lỗi tích hợp, không phải lỗi ảnh. | system |
| `MODEL_MISSING` | fail | không tìm thấy file `.onnx` của DocAligner | Image thiếu mô hình DocAligner; nó phải được nướng vào lúc **build** (`qc-scanner-fetch-models`). Ảnh không có lỗi — cho chạy lại sau khi sửa image. | system |
| `LOW_RESOLUTION` | fail | **cạnh dài ảnh đã nắn < 600px** (xem ghi chú) | Ảnh quá nhỏ để OCR đọc. Lại gần hơn rồi chụp lại. | capturer |

### Đầu vào PDF (N-08)

| Mã | Sev | Điều kiện | Hướng xử lý | Ai |
|---|---|---|---|---|
| `PDF_DECODE_FAILED` | fail | pdfium không mở được file | PDF hỏng hoặc có mật khẩu, không mở ra được. Xin lại bản đã gỡ mật khẩu. | system |
| `PDF_NO_PAGES` | fail | mở được nhưng 0 trang | PDF rỗng, không có gì để soi. Báo bên gửi kiểm tra bước xuất file. | system |
| `PDF_TOO_MANY_PAGES` | fail | số trang > `pdf_max_pages` (50) | Vượt trần `pdf_max_pages` nên **không trang nào** được xử lý — cắt bớt trong im lặng sẽ khiến bên gọi tưởng đã soi hết. Tách file, hoặc nâng `QC_SCANNER_PDF_MAX_PAGES`. | operator |
| `PDF_MULTIPAGE` | fail | PDF > 1 trang đưa vào `scan_qc()` | Lỗi tích hợp: `scan_qc()` trả đúng một kết quả nên không chứa nổi PDF nhiều trang. Dùng `scan_document()`; qua HTTP thì đã là mặc định. | system |

### Tách chủ thể

| Mã | Sev | Điều kiện | Hướng xử lý | Ai |
|---|---|---|---|---|
| `SUBJECT_NOT_FOUND` | fail | `alpha_coverage < 0.05` (và fallback §6 cũng thua) | Máy không thấy tờ giấy. Đặt lên nền tối rồi chụp lại. | capturer |
| ~~`SUBJECT_FILLS_FRAME`~~ | *ngừng phát (QC-15)* | `alpha_coverage > 0.95` | Giấy chiếm gần hết khung, có thể mất mép. Lùi máy ra rồi chụp lại. | capturer |
| `RECOVERED_BY_MASK_FALLBACK` | warn | detector chính trả rỗng → tách nền tìm được (hay gặp với ảnh **đã cắt sẵn**) | Detector chính trả rỗng, tứ giác này do tách nền tìm ra. Hay gặp với ảnh **đã cắt sẵn**. Soi trước khi dùng. | operator |
| `RECOVERED_BY_EDGE_FALLBACK` | warn | dùng đường lui §6 | Nắn bằng phương án dự phòng nên kém tin cậy hơn. Soi trước khi dùng. | operator |
| `DETECTOR_DISAGREEMENT` | warn | `cross_check_detectors` bật và IoU giữa hai detector < 0.85 (S-6) | Hai phương pháp dò biên không đồng thuận nên kết quả kém chắc. Soi trước khi dùng. | operator |

### Hình học biên

| Mã | Sev | Điều kiện | Hướng xử lý | Ai |
|---|---|---|---|---|
| `QUAD_NOT_FOUND` | fail | không contour nào cho đúng 4 đỉnh | Máy không thấy đủ 4 góc. Mở phẳng tờ giấy, đừng che góc, chụp lại cả tờ. | capturer |
| `TOO_SMALL` | fail | `quad_area_ratio < 0.20` | Tài liệu quá nhỏ trong khung. Lại gần hoặc zoom vào rồi chụp lại. | capturer |
| `NOT_CONVEX` | fail | `not is_convex` | Biên bị méo, thường do nếp gấp. Vuốt phẳng tài liệu rồi chụp lại. | capturer |
| `CONTENT_CLIPPED` | fail | `border_ink_ratio > 0.08`, **và chỉ khi có cắt thật** (`quad_area_ratio ≤ 0.90`) | Mất **chữ** chứ không chỉ mất viền. Lùi máy ra, chụp lại cả tờ kèm chút nền. | capturer |
| `NO_CROP_DETECTED` | fail | **hoặc** `quad_area_ratio > 0.90` + `touches_border ≥ 3` + detector thua; **hoặc** `conf < 0.9` **và** góc lọt > 8px ra ngoài ảnh (QC-20 — một tứ giác sai bét vẫn có thể nhỏ hơn khung) | Máy không tìm được biên tờ giấy. Đặt lên nền tối rồi chụp lại cả 4 mép. | capturer |
| `CLIPPED_EDGE` | warn | `touches_border ≥ 1` (và **không** phải ca trên) | Một phần tài liệu nằm ngoài khung. Lùi máy ra cho thấy trọn 4 mép. | capturer |
| `EXTREME_SKEW` | warn | `skew_ratio > 1.8` | Chụp quá nghiêng nên chữ bị kéo giãn. Chụp vuông góc từ trên xuống. | capturer |
| `MULTIPLE_DOCUMENTS` | warn | `contour_candidates ≥ 2` | Ảnh có nhiều tờ, máy chỉ lấy tờ lớn nhất. Chụp từng tờ một. | capturer |
| `FALLBACK_ORIGINAL` | fail | trả ảnh gốc không nắn | Ảnh trả về là ảnh gốc chưa xử lý. Đừng đưa thẳng vào OCR. | operator |

### Chất lượng ảnh (Giai đoạn 2)

| Mã | Sev | Điều kiện | Hướng xử lý | Ai |
|---|---|---|---|---|
| `BLURRY` | fail | `blur_score < 25` (đã chốt bằng số đo) | Ảnh mờ hoặc rung. Giữ máy vững, chạm lấy nét rồi chụp lại. | capturer |
| `GLARE` | warn | vùng bão hòa sáng > X% | Có vệt loá che chữ. Đổi hướng đèn hoặc nghiêng nhẹ máy. | capturer |
| `TOO_DARK` | warn | độ sáng trung vị thấp | Ảnh thiếu sáng. Chụp ở nơi sáng hơn. | capturer |
| `TEXT_NOT_LEVEL` | fail | `|text_skew_deg| > 8` — đo **sau** khi nắn | Ảnh nắn ra bị xiên, thường do gấp góc giấy. Vuốt phẳng cả 4 góc rồi chụp lại. | capturer |

### Hai ngưỡng đã chốt bằng số đo — và vì sao khác thiết kế ban đầu

**`LOW_RESOLUTION`: bỏ `est_dpi ≥ 150`, dùng cạnh dài ≥ 600px.** DPI chỉ tính được khi biết
khổ giấy thật, mà điều đó chưa xác nhận được với khách (EX-4). Đo trên 17 ảnh (8 mẫu + 9 ảnh
thật), ngưỡng DPI-theo-A4 loại nhầm **15/17** — toàn giấy tờ khổ nhỏ hoàn toàn đọc được. Số
pixel cạnh dài không phụ thuộc khổ giấy nên dùng làm chốt chặn được ngay; `est_dpi` vẫn được
báo cáo trong `metrics` nhưng **không dùng để phán quyết** cho tới khi chốt được khổ giấy.

**`BLURRY`: 25, không phải 100.** Ngưỡng 100 loại nhầm doc-1 (`blur_score` 42.7) — một ảnh đã
được duyệt mắt. Đo bản sắc nét 42.7–358 so với bản làm mờ nhân tạo (GaussianBlur k≥9) 2.7–9.4:
hai cụm tách bạch, ngưỡng 25 nằm gọn ở giữa.

Các ngưỡng còn lại (0.20 diện tích, 1.8 skew, 0.05/0.95 alpha, 0.02 glare, 60 độ sáng) **vẫn
là ước đoán** — cần tập vàng để chốt (QUAL-3, EX-2).

> Thêm mã mới: đặt mã **ổn định, viết HOA, không đổi về sau** (mã đi vào log/CSV của khách);
> ghi đủ cột trong bảng trên; bổ sung ca test trong [test_eval.md §3](test_eval.md).

---

## 8. Khảo sát: lõi thuật toán có còn hợp thời? (2026) {#khao-sat}

> Code lõi viết ~2019 (7 năm trước). Câu hỏi: công nghệ hiện nay có phương pháp luận nào tốt
> hơn không? Trả lời ngắn: **có, và khoảng cách khá lớn** — nhưng đúng một phần của lõi hiện tại
> vẫn nên giữ.

### 8.0 Đánh giá lõi hiện tại

Điểm **đúng** của thiết kế cũ, cần ghi nhận: qc_scanner chọn **segmentation-first** (rembg tách
chủ thể → dò biên trên mask) thay vì Canny+Hough thuần. Ở 2019 đó đã là lựa chọn tiến bộ —
mask sạch hơn hẳn dò cạnh trên nền lộn xộn. Đây cũng vẫn là xương sống của nhiều sản phẩm.

Điểm **đã lỗi thời**:

| Thành phần | Vấn đề cố hữu (không sửa bằng tinh chỉnh được) |
|---|---|
| **U²-Net (mặc định rembg)** | Là mô hình **salient object detection** — huấn luyện cho "vật thể nổi bật" nói chung, **không biết khái niệm tờ giấy**. Giấy trắng trên nền sáng → thua. |
| **contour → approxPolyDP** | Chỉ suy được góc **nhìn thấy được**. Góc bị tay che / nằm ngoài khung → mất hẳn. Không có khái niệm "độ tin cậy". |
| **Không có confidence** | Nguồn gốc trực tiếp của [vấn đề QC](features_issues.md#root-no-qc): thuật toán không có gì để báo cáo cả. |
| **four-point transform** | Chỉ sửa được biến dạng **phẳng** (phối cảnh). Giấy cong/gập/sách đóng gáy vẫn méo sau khi nắn. |

### 8.1 Các họ phương pháp hiện có

**A. Cổ điển thuần** — Canny → HoughLines → chọn 4 đường "mạch lạc" nhất → giao điểm.
Không model, vài ms, chạy mọi nơi. Thua trên nền lộn xộn và tài liệu có khung/bảng (bắt nhầm
đường kẻ trong tài liệu). *Giá trị hôm nay*: **đường lui**, không phải đường chính — đúng vai
trò đã thiết kế ở [§6](#6--fallback-dò-cạnh-khi-rembg-thất-bại).

**B. Segmentation-first** (họ của qc_scanner hiện tại) — mask chủ thể → contour → tứ giác.
Nâng cấp tại chỗ, rẻ nhất, **không đổi kiến trúc**:
- Đổi model trong rembg: `isnet-general-use` (đã có sẵn trong rembg, thường hơn u2net) —
  **đổi một tham số `session`**, không đổi code.
- **BiRefNet** — SOTA 2025 cho tách nền độ phân giải cao, giữ biên sắc hơn rõ rệt; rembg các
  bản mới đã hỗ trợ. Nặng hơn u2net.
- Hoặc **DeepLabV3 + MobileNetV3** fine-tune riêng cho *tài liệu* (có hướng dẫn công khai) —
  nhẹ hơn và **chuyên biệt** thay vì salient-object chung chung.

**C. Hồi quy 4 góc trực tiếp** ⭐ — mô hình nhận ảnh, **xuất thẳng toạ độ 4 góc** (point
regression hoặc heatmap). Đây là hướng các app scanner thương mại đã chuyển sang (CNN dò
landmark, >30fps trên thiết bị di động, kèm Kalman filter làm mượt giữa các khung hình).
- Mã nguồn mở dùng được ngay: **[DocAligner](https://github.com/DocsaidLab/DocAligner)**
  (Apache-2.0, `pip install docaligner-docsaid`, chạy **ONNXRuntime** — cùng runtime qc_scanner
  đã phụ thuộc sẵn). Hai biến thể: point regression (PP-LCNet, 128×128) và heatmap
  (FastViT/MobileNetV2 + BiFPN).
- **Vì sao hợp qc_scanner hơn hẳn**: (a) **suy được góc bị che hoặc nằm ngoài khung** — thứ
  contour không bao giờ làm được; (b) sinh **confidence tự nhiên** (đỉnh heatmap) → nạp thẳng
  vào `metrics`/`verdict` của [hợp đồng QC §2](#2--hợp-đồng-đầu-ra-qc); (c) thay được **cả**
  rembg lẫn contour → bỏ luôn chặng chiếm ~95% thời gian.
- Nhược: mỗi ảnh một tài liệu (đa tài liệu cần thêm bước định vị + ghép góc); chưa có số đo
  trên ảnh thật của khách; repo không công bố benchmark → **phải tự đo**.

**D. Dewarping (nắn cong)** — cấp độ cao hơn hẳn: dự đoán lưới biến dạng thay vì 4 điểm, sửa
được giấy cong/gập. SOTA hiện tại: **UVDoc** (grid-based, nhẹ, dẫn đầu benchmark DocUNet),
**DocTr++** (không ràng buộc kiểu biến dạng), **DocRes** (mô hình tổng quát cho nhiều tác vụ
phục hồi ảnh tài liệu), và các công trình 2025 (DocMatcher, D²Dewarp). *Chỉ đáng làm nếu ảnh
khách thật sự có giấy cong* — với GCN/hồ sơ ép phẳng thì phối cảnh là đủ. → câu hỏi
[EX-5](need_exchange.md).

**E. Promptable segmentation (SAM/SAM2)** — rất tổng quát nhưng nặng, cần prompt, và **không
có khái niệm "4 góc"**. Không hợp làm lõi tự động. *Chỗ dùng đúng*: **hỗ trợ gán nhãn tập
vàng** — click một cái ra mask, rút ngắn công gán nhãn ở [test_eval.md §5](test_eval.md).

**F. VLM hỏi toạ độ góc** — đắt, toạ độ không ổn định. Không dùng ở hot path. Có thể dùng
làm **trọng tài offline** để soi ca bất đồng khi eval.

### 8.2 Khuyến nghị (theo tỉ lệ lợi ích / công sức)

| # | Việc | Công | Kỳ vọng | Khi nào |
|---|---|---|---|---|
| **S-1** | Đổi model rembg | 🟡 **đã đo** | isnet chậm gấp 3, đổi 2 verdict — chưa đủ căn cứ đổi mặc định. Chờ EX-2 | — |
| **S-2** | Tách interface `Detector` | 🟢 **xong** | `rembg-contour` + `edge-hough`; chỗ cắm DocAligner đã sẵn | — |
| **S-3** | **Thêm DocAligner làm đường chính**, giữ pipeline cũ làm đối chứng | 1–2 ngày | **Bước nhảy chất lượng lớn nhất** + có confidence cho QC | GĐ 3, sau khi có tập vàng |
| **S-4** | Bộ lọc hình học + reason code ([QUAL-1](features_issues.md#qual-quad-filter)) | — | Giữ nguyên giá trị **dù chọn detector nào** | GĐ 1–3 |
| **S-5** | Dewarping (UVDoc) | 1 tuần+ | Chỉ có lợi nếu ảnh khách cong | Chờ EX-5 |

Kiến trúc để làm được S-2/S-3 mà không viết lại:

```python
class Detector(Protocol):
    def find_quad(self, img: np.ndarray) -> QuadCandidate | None: ...
    # QuadCandidate = 4 điểm + confidence + tên detector
```

Lõi QC (§2, §7) **không đổi** — nó nhận `QuadCandidate` từ bất kỳ detector nào rồi mới phán
quyết. Nhờ vậy đổi detector là thay một dòng cấu hình, và có thể **chạy hai detector song song
trên cùng tập vàng** để so bằng số thay vì bằng cảm tính.

### 8.3 Điều KHÔNG nên làm

- **Đừng thay detector trước khi có bộ đo.** Nguyên tắc này đã được **thi hành**: DocAligner
  nằm im sau cờ cấu hình cho tới khi có [SmartDoc 2015](https://zenodo.org/records/1230218) rồi
  mới thành mặc định ([S-3b](features_issues.md#s-docaligner)). Và nó tự chứng minh giá trị theo
  cách khó chịu: đo trên **một nền dễ** cho kết luận "rembg không thua", đủ 5 nền thì kết luận
  đó **sai hẳn**. Bộ đo chạy trên tập con dễ còn nguy hiểm hơn không có bộ đo.
- **Đừng bỏ hẳn đường cũ.** Nay có bằng chứng cứng thay cho lập luận: docaligner trả rỗng với
  ảnh **đã cắt sẵn** (7/30 ảnh thật + mọi trang PDF) còn rembg lấy được cả; ngược lại rembg sụp
  ở nền bàn bừa bộn còn docaligner giữ nguyên. Hai họ thuật toán thua ở hai chỗ **khác nhau**.
- **Đừng để một phép kiểm QC phụ thuộc detector.** `MULTIPLE_DOCUMENTS` từng đếm ứng viên của
  detector; đổi sang mô hình hồi quy góc (chỉ trả một tứ giác) là nó **tắt lặng lẽ**. Mất một
  phép kiểm vì đổi detector là cái giá không ai đồng ý trả, mà lại không có gì báo.
- **Đừng bê ngưỡng confidence từ detector này sang detector kia.** rembg trả hai giá trị rời rạc
  (0.9 / 0.6); docaligner trả số thực (trung vị 0.841 trên ảnh thật). Không cùng đơn vị.
- **Đừng nhảy thẳng lên dewarping.** Đắt, phức tạp, và có thể không giải quyết vấn đề nào của
  ảnh khách. Hỏi trước ([EX-5](need_exchange.md)), đo sau, làm sau cùng.
- **Đừng dựng lại phép dò nếp gấp theo kiểu edge-profile + tương quan chéo 2-D.** Patent Xerox
  [US10212299B2](https://patents.google.com/patent/US10212299B2/en) (cấp 2019-02-19) phủ đúng
  cách đó. Đường skew dòng chữ ([QC-18](features_issues.md#qc-text-level)) là kỹ thuật phổ
  thông, có tiền lệ công khai, và đã bắt được ca thật.
- **Đừng quảng cáo `cross_check_detectors` như một điểm mạnh trước khi hỏi pháp lý.** Adobe
  [US10970847B2](https://patents.google.com/patent/US10970847B2/en) (hiệu lực tới 2039) phủ đúng
  "sinh tứ giác bằng Hough + sinh tứ giác bằng CNN → quyết định dựa trên cả hai tập". Đó gần như
  là mô tả của S-6. Mặc định đang **tắt**; giữ nguyên như vậy.
- **Đừng thêm thủ thuật "chọn kênh màu tốt nhất"** (Kodak Alaris
  [US9122921B2](https://patents.google.com/patent/US9122921B2/en)) và **đừng làm preview dò biên
  realtime** (họ patent "live document detection").

### 8.4 Đối chiếu với bộ chỉ số của ngành (khảo sát 2026)

Ta không tự nghĩ ra bộ chỉ số này — kiểm lại thì nó gần trùng khít cái ngành đang dùng:

| Chỉ số | [Google Document AI][gdai] | qc_scanner |
|---|---|---|
| mờ | `defect_blurry` | `blur_score`, ngưỡng 25 |
| cháy sáng | `defect_glare` | `glare_ratio` + `median_brightness` |
| cắt mất nội dung | `defect_document_cutoff` / `defect_text_cutoff` | `CLIPPED_EDGE` / `CONTENT_CLIPPED` |
| chữ quá nhỏ | `defect_text_too_small` | `LOW_RESOLUTION` (xem [QC-24](features_issues.md#qc-text-height)) |
| nhiều tài liệu trong một ảnh | *(không có)* | `MULTIPLE_DOCUMENTS` |
| skew dòng chữ | *(không công bố)* | `text_skew_deg`, ngưỡng **8°** |

Taxonomy của Google trùng gần hết bộ mã của ta, và đó là **tài liệu sản phẩm thật** (1,50
USD/1.000 trang, kèm OCR). Ô ta hơn: đa tài liệu.

> **Hai chỗ bản trước của tài liệu này trích SAI, đã sửa:**
>
> 1. Cột đối chiếu cũ là **Dynamsoft**, lấy từ một [bài blog demo][dyn] — chính bài đó ghi các
>    ngưỡng là *"suggested starting values"*, và Dynamsoft không bán sản phẩm nào tên "DIQA".
>    Nó không đủ tư cách làm cột đối chứng.
> 2. Câu "[FADGI][fadgi] 4 sao đặt dung sai ±1° và **cấm** de-skew phần mềm" là quy tắc của bản
>    **2016**, trong khi link trỏ bản **2023**. Bản 3rd Edition (05/2023) đã **rút** quy tắc đó:
>    *"the guidelines now allow for rotation correction to be applied to images"*. Hệ quả:
>    lập luận của [EX-18](need_exchange.md#ex-archival) (tắt deskew cho bản lưu trữ) mất chỗ
>    dựa, và `deskew = True` mặc định vững hơn lúc đặt nó.

**Ngưỡng của tiêu chuẩn số hoá không bê sang được**: ISO 19264-1, FADGI và Metamorfoze đều đo
**thiết bị chụp qua bia kiểm chuẩn đặt trong khung hình**, không đo ảnh đơn lẻ. Ta nhận ảnh chụp
điện thoại, không có bia. Sẽ không bao giờ có ngưỡng cho ta ở đó.

**Mô hình đúng để bắt chước nằm ở sinh trắc học, không ở ngành scan**: ISO/IEC 29794 +
[NFIQ 2](https://github.com/usnistgov/nfiq2) — điểm chất lượng **hiệu chuẩn theo lỗi của hệ nhận
dạng phía sau**, kèm cài đặt tham chiếu mã nguồn mở. Áp vào ta: nhãn vàng nên là *"OCR đọc đủ
trường bắt buộc không"*, không phải *"người thấy ảnh xấu"*. Xem
[QUAL-5](features_issues.md#qual-ocr-truth).

Ngược lại, [Scanbot DQA][scanbot] — sản phẩm thương mại chuyên đúng việc này — chỉ chấm **độ sắc
nét chữ** thành 5 mức, không dò nếp gấp cũng không dò che khuất. Lỗ hổng [QC-18b](features_issues.md#qc-fold-residual)
là chuyện bình thường trong ngành; điều đó không làm nó bớt là lỗ hổng.

[gdai]: https://cloud.google.com/document-ai/docs/process-documents-ocr
[dyn]: https://www.dynamsoft.com/codepool/quality-evaluation-of-scanned-document-images.html
[fadgi]: https://www.digitizationguidelines.gov/guidelines/FADGI%20Technical%20Guidelines%20for%20Digitizing%20Cultural%20Heritage%20Materials_3rd%20Edition_05092023.pdf
[scanbot]: https://scanbot.io/blog/enhanced-document-quality-analyzer/

> Nguồn tham khảo: [Grizzly Labs — Document Detection](https://blog.thegrizzlylabs.com/2024/10/document-detection.html) ·
> [Scanner Pro — border detection](https://readdle.com/blog/scanner-pro-border-detection) ·
> [DocAligner](https://github.com/DocsaidLab/DocAligner) ·
> [UVDoc](https://arxiv.org/pdf/2302.02887) ·
> [DocRes](https://arxiv.org/pdf/2405.04408) ·
> [DocMatcher (WACV 2025)](https://openaccess.thecvf.com/content/WACV2025/papers/Hertlein_DocMatcher_Document_Image_Dewarping_via_Structural_and_Textual_Line_Matching_WACV_2025_paper.pdf) ·
> [LearnOpenCV — DeepLabV3 document segmentation](https://learnopencv.com/deep-learning-based-document-segmentation-using-semantic-segmentation-deeplabv3-on-custom-dataset/) ·
> [BiRefNet vs rembg/U²-Net](https://dev.to/om_prakash_3311f8a4576605/birefnet-vs-rembg-vs-u2net-which-background-removal-model-actually-works-in-production-4830)

---

## 9. Tài liệu liên quan

- [overall_roadmap.md](overall_roadmap.md) — dự án là gì, đi về đâu.
- [features_issues.md](features_issues.md) — issue tương ứng từng điểm yếu nêu ở §1, §3, §4.
- [test_eval.md](test_eval.md) — cách chạy thử và đo chất lượng phán quyết.
