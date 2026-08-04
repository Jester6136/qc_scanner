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
                         ┌──────────────────────────────────────────────┐
 ảnh chụp (bytes)  ────►  │  rembg: tách chủ thể  →  RGBA (alpha = giấy) │
   jpg/png                └───────────────────┬──────────────────────────┘
                                              │  kênh alpha
                         ┌────────────────────▼──────────────────────────┐
                         │  resize H=500 · threshold · medianBlur 15     │  ảnh nhị phân
                         │  findContours → sort theo diện tích          │
                         │  approxPolyDP → tìm đa giác 4 đỉnh           │
                         └───────────────────┬──────────────────────────┘
                                             │ 4 điểm × ratio
                         ┌───────────────────▼──────────────────────────┐
                         │  four_point_transform trên ảnh GỐC           │
                         │  imencode(".png")                            │
                         └───────────────────┬──────────────────────────┘
                                             ▼
                                        PNG bytes
```

Toàn bộ nằm trong **một hàm** `scan()` — [src/qc_scanner/doc.py:14-71](../src/qc_scanner/doc.py#L14-L71).
Không state, không I/O ngoài (trừ rembg tải model lần đầu), không song song.

Ba mặt tiền gọi cùng hàm này:
- CLI — [src/qc_scanner/cmd/cli.py:20-21](../src/qc_scanner/cmd/cli.py#L20-L21)
- HTTP server — [src/qc_scanner/cmd/server.py:14-41](../src/qc_scanner/cmd/server.py#L14-L41)
- Library — `from qc_scanner.doc import scan`

---

## 1. `scan()` — thuật toán **ban đầu** (giữ để đối chiếu)

```
scan(data: bytes) -> bytes | None
 1. processed = rembg(data)                       # tách chủ thể → PNG RGBA
 2. img = cv2.imdecode(frombuffer(processed), IMREAD_UNCHANGED)
    nếu img is None: raise ValueError             # không decode được
 3. orig  = img.copy()                            # giữ ảnh GỐC độ phân giải đầy đủ
    ratio = img.height / 500.0                    # hệ số quy đổi ngược
    img   = imutils.resize(img, height=500)       # làm việc trên ảnh nhỏ cho nhanh
 4. nếu img.shape[2] == 4:                        # có kênh alpha
        _, img = threshold(img[:,:,3], 0, 255, THRESH_BINARY)   # alpha → mask nhị phân
    ngược lại: raise ValueError                   # "lacks an alpha channel"
 5. img = medianBlur(img, 15)                     # khử răng cưa / lỗ nhỏ trong mask
 6. cnts = findContours(img, RETR_EXTERNAL, CHAIN_APPROX_SIMPLE)
    cnts = sort(cnts, key=contourArea, desc)      # to nhất trước
 7. outline = None
    với mỗi c trong cnts:                         # LẤY TỨ GIÁC ĐẦU TIÊN GẶP
        peri    = arcLength(c, closed=True)
        polygon = approxPolyDP(c, 0.02 * peri, closed=True)
        nếu len(polygon) == 4: outline = polygon.reshape(4,2); break
 8. nếu outline is None: result = orig            # ⚠️ FALLBACK IM LẶNG
    ngược lại:            result = four_point_transform(orig, outline * ratio)
 9. _, buf = imencode(".png", result); return buf.tobytes()

 mọi exception  → print(stderr) + return None     # ⚠️ NUỐT LỖI
```

### Vì sao từng lựa chọn

| Bước | Lựa chọn | Lý do |
|---|---|---|
| 1 | Dùng **rembg** thay vì dò cạnh Canny | Ảnh chụp thật có nền lộn xộn (bàn gỗ, vân, chữ in trên tờ khác). Mask chủ thể cho biên **sạch hơn nhiều** so với dò cạnh, vốn bắt cả đường kẻ trong tài liệu. |
| 3 | Dò biên trên ảnh **500px**, warp trên ảnh **gốc** | Dò trên ảnh nhỏ nhanh và **ổn định hơn** (nhiễu tần số cao bị dập). Nắn trên ảnh gốc để **không mất độ phân giải** — ảnh này còn phải đi vào OCR. `ratio` quy đổi 4 điểm ngược về hệ tọa độ gốc. |
| 4 | Lấy **kênh alpha**, không lấy màu | Alpha do rembg sinh chính là "đâu là tờ giấy". Không phụ thuộc màu giấy / ánh sáng. |
| 5 | `medianBlur` (không phải Gaussian) | Median giữ **cạnh sắc** trong khi xóa đốm — đúng nhu cầu mask nhị phân. Gaussian sẽ làm nhòe góc, hỏng approxPolyDP. |
| 7 | `approxPolyDP` với ε = **2% chu vi** | Ramer–Douglas–Peucker: giản lược đa giác tới khi mọi điểm nằm trong ε. 2% đủ lớn để nuốt gợn sóng mép giấy, đủ nhỏ để giữ 4 góc thật. |
| 8 | Warp bằng `four_point_transform` | Sắp 4 điểm theo thứ tự TL-TR-BR-BL rồi `getPerspectiveTransform` + `warpPerspective`; kích thước đích suy từ cạnh dài nhất mỗi chiều. |

### Điểm yếu đã biết của thuật toán này

- **B7 lấy tứ giác ĐẦU TIÊN**, không kiểm lồi / diện tích tối thiểu / tỉ lệ cạnh → một vệt
  nhiễu vuông vắn có thể thắng. → [QUAL-1](features_issues.md#qual-quad-filter)
- **B8 fallback im lặng**: không tìm được biên → trả ảnh gốc, caller **không biết**. Đây là
  nguồn *false pass* lớn nhất. → [QC-1/QC-2](features_issues.md#qc-contract)
- **Nuốt exception → `None`**: xóa sạch nguyên nhân. → [BUG-2](features_issues.md#bug-swallow)
- **Hằng số cứng** (500px, ksize 15, 2%) không scale theo kích thước ảnh. → [QUAL-2](features_issues.md#qual-scale)
- **Chỉ lấy 1 tứ giác** — nhiều tờ trong khung thì âm thầm mất tờ. → [QC-9](features_issues.md#qc-multi)

---

## 1b. `scan_qc()` — luồng đang chạy

```
scan_qc(data, config) -> ScanResult
 1. data rỗng                         → ScanError(FILE_EMPTY)
 2. orig = imdecode(data)             → None thì ScanError(DECODE_FAILED)
 3. rgba = rembg(data, session dùng lại)          # gọi ĐÚNG MỘT LẦN, mọi mặt tiền
 4. work  = hạ mẫu về work_height (KHÔNG phóng to ảnh nhỏ hơn)
    mask  = threshold(alpha) → medianBlur(ksize ≈ 3% chiều cao)
    metrics.alpha_coverage = tỉ lệ pixel alpha > 0
 5. candidates = detector.all_candidates(work, mask)   # contour ≥ 5% diện tích
    quad       = best_candidate(...)                   # LỌC rồi mới chọn, không lấy cái đầu
 6. nếu quad None HOẶC alpha_coverage ngoài [0.05, 0.95]:
        thử đường lui edge-hough → qua lọc thì dùng + RECOVERED_BY_EDGE_FALLBACK (warn)
 7. vẫn không có quad → trả ảnh GỐC + QUAD_NOT_FOUND/SUBJECT_NOT_FOUND + FALLBACK_ORIGINAL
    (fail).  Khác bản cũ ở đúng một chỗ: **có nhãn**.
 8. metric hình học → reasons: NOT_CONVEX · TOO_SMALL · EXTREME_SKEW · CLIPPED_EDGE · NO_CROP_DETECTED
    tứ giác chạm mép ảnh mà chỗ chạm CÓ MỰC → CONTENT_CLIPPED (thay CLIPPED_EDGE)
    ≥2 ứng viên → MULTIPLE_DOCUMENTS
    cross-check bật → IoU hai detector thấp → DETECTOR_DISAGREEMENT
 9. warp trên ảnh GỐC, PNG
10. metric chất lượng → LOW_RESOLUTION · BLURRY · GLARE · TOO_DARK
11. verdict suy từ reasons; pass ⟺ reasons rỗng
```

`scan()` cũ vẫn còn, là lớp bọc mỏng trả `result.image` — không phá người dùng hiện tại,
nhưng cũng **không mang phán quyết**, nên mã mới nên gọi `scan_qc()`.

Mọi ngưỡng nằm trong [`config.py`](../src/qc_scanner/config.py), override được bằng biến môi
trường `QC_SCANNER_*`.

---

## 2. ✅ Hợp đồng đầu ra QC (đã cài)

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
| `alpha_coverage` | % pixel alpha > 0 sau rembg | bắt `SUBJECT_NOT_FOUND` |
| `fallback_used` | `none` / `edge_detect` / `original` | minh bạch đường đi |

`scan()` cũ giữ nguyên chữ ký (`bytes -> bytes`) như lớp bọc mỏng quanh `scan_qc()`, để không
phá người dùng PyPI hiện tại.

---

## 3. Luồng CLI — [cmd/cli.py](../src/qc_scanner/cmd/cli.py)

```
input  = stdin nếu là pipe, ngược lại đối số file
output = stdout nếu là pipe, ngược lại đối số file
output.write( scan( rembg.remove( input.read() ) ) )
```

✅ **Đã sửa**: `rembg` chỉ còn được gọi bên trong `scan_qc()`. CLI nay trả **exit code theo
verdict** (0 pass · 1 warn · 2 fail · 3 đầu vào hỏng) và in báo cáo JSON (reason + hint) ra
stderr, hoặc ra file với `--report`. Ảnh vẫn ra stdout như cũ nên pipe hiện có không vỡ.

Thêm `qc-scanner-batch` cho cả thư mục, xuất CSV báo cáo QC.

---

## 4. Luồng HTTP server — [cmd/server.py](../src/qc_scanner/cmd/server.py)

```
POST /  form-data "file"     → file_content = file.read()
GET  /  ?url=<url-encoded>   → file_content = urlopen(unquote_plus(url)).read()   🔴 SSRF
nếu file_content == "":  400                                    🔴 so bytes với str
send_file(BytesIO(scan(file_content)), mimetype="image/png")
lỗi → log + {"error": "oops, something went wrong!"}, 500        🔴 phản-QC
```

✅ **Đã sửa cả ba**. Nhánh `GET /?url=` bị bỏ hẳn (405). Chốt chặn rỗng chuyển vào
`scan_qc()` nên cả ba mặt tiền cùng được bảo vệ. `?format=json` trả `ScanResult` (ảnh base64
+ verdict + reasons + metrics); mặc định trả PNG kèm header `X-QC-Scanner-Verdict` /
`X-QC-Scanner-Reasons`. HTTP status theo verdict: 200 pass/warn, **422** fail, 400 đầu vào hỏng.

Lưu ý về hành vi cũ: mô tả "500 oops" **chưa đúng**. Đo thực tế cho thấy server cũ trả
**200 OK + PNG rỗng 0 byte** với ảnh hỏng, vì `BytesIO(None)` hợp lệ nên `send_file` không
ném gì để rơi vào `except`. Đó là hỏng âm thầm — tệ hơn 500.

---

## 5. Chi phí thời gian

| Chặng | Tỉ trọng | Ghi chú |
|---|---|---|
| `rembg` (U²-Net, onnxruntime CPU) | **~95%+** | Lần chạy đầu còn cộng thời gian **tải model** |
| resize + threshold + blur + contour | vài chục ms | không đáng tối ưu |
| `warpPerspective` trên ảnh gốc | ~10–50ms | tỉ lệ với megapixel |
| `imencode(".png")` | ~10–100ms | PNG nén chậm hơn JPEG — chấp nhận (xem nguyên tắc §3.3 roadmap) |

Hệ quả: **mọi tối ưu tốc độ đều nằm ở rembg** — tái dùng session, GPU provider.

✅ **Đã đo** (9 ảnh thật, Apple Silicon, model đã cache):

| Cấu hình | Thời gian/ảnh (median) |
|---|---|
| Bản đầu (tạo session mới mỗi lần gọi) | ~3.0s |
| **Tái dùng session (N-06, hiện tại)** | **0.395s** |
| Tái dùng session + model `isnet-general-use` | 1.198s |

Giả thuyết "rembg chiếm ~95%" **được xác nhận**: bỏ được phần nạp lại model là đủ để nhanh
hơn ~7 lần, trong khi phần OpenCV không đổi. Đừng tối ưu OpenCV.

---

## 6. ✅ Fallback dò cạnh (đã cài)

Ca thường gặp nhất mà rembg chịu thua: **giấy trắng trên nền trắng/sáng** → `alpha_coverage`
gần 0 hoặc gần 1 (nuốt cả ảnh). Khi đó thay vì `fail` ngay, chạy đường lui:

```
nếu alpha_coverage < 0.05 hoặc > 0.95:
    gray  = cvtColor(orig_resized, GRAY); GaussianBlur; Canny(75, 200)
    lines = HoughLinesP(...)
    gom line theo hướng → 2 cụm (ngang / dọc) → lấy 2 line ngoài cùng mỗi cụm
    4 giao điểm → tứ giác ứng viên
    nếu qua được bộ lọc §7 (lồi, diện tích, tỉ lệ):
        dùng tứ giác này; verdict = warn
        reasons += RECOVERED_BY_EDGE_FALLBACK   # minh bạch: kết quả kém tin cậy hơn
    ngược lại:
        verdict = fail; reasons += SUBJECT_NOT_FOUND
```

Đây là mức 3 của mục tiêu QC ("hơn cả thế"): **tự khắc phục trước, rồi mới báo** — nhưng
không bao giờ giấu việc đã phải dùng đường lui.

---

## 7. ✅ Danh mục mã lý do (đã cài)

Nguyên tắc bất biến: **mã nào cũng phải có `hint` và `audience`**. Mã không hành động được
là mã vô dụng.

### Đầu vào

| Mã | Sev | Điều kiện phát hiện | Hướng xử lý (hint) | Ai |
|---|---|---|---|---|
| `DECODE_FAILED` | fail | `imdecode` trả None | File không phải ảnh hợp lệ (hoặc đã hỏng). Kiểm tra định dạng: JPG/PNG. | system |
| `FILE_EMPTY` | fail | `len(data) == 0` | Không nhận được dữ liệu. Kiểm tra lại bước tải/upload. | system |
| `LOW_RESOLUTION` | fail | **cạnh dài ảnh đã nắn < 600px** (xem ghi chú) | Ảnh quá nhỏ để OCR đọc được. Chụp lại ở độ phân giải cao hơn, hoặc lại gần tài liệu hơn. | capturer |

### Tách chủ thể

| Mã | Sev | Điều kiện | Hướng xử lý | Ai |
|---|---|---|---|---|
| `SUBJECT_NOT_FOUND` | fail | `alpha_coverage < 0.05` (và fallback §6 cũng thua) | Không tách được tờ giấy khỏi nền. Đặt tài liệu lên **nền tối, tương phản** (bàn sẫm màu) rồi chụp lại. | capturer |
| `SUBJECT_FILLS_FRAME` | warn | `alpha_coverage > 0.95` | Tờ giấy chiếm gần hết khung, có thể đã bị cắt mất mép. Lùi ra để lộ viền nền quanh tài liệu. | capturer |
| `RECOVERED_BY_EDGE_FALLBACK` | warn | dùng đường lui §6 | Đã nắn được bằng phương án dự phòng — độ tin cậy thấp hơn, nên soi mắt thường trước khi dùng. | operator |

### Hình học biên

| Mã | Sev | Điều kiện | Hướng xử lý | Ai |
|---|---|---|---|---|
| `QUAD_NOT_FOUND` | fail | không contour nào cho đúng 4 đỉnh | Không thấy đủ 4 góc tờ giấy. Mở phẳng tài liệu, đừng để tay/vật che góc, chụp lại toàn bộ tờ. | capturer |
| `TOO_SMALL` | fail | `quad_area_ratio < 0.20` | Tài liệu chiếm quá ít khung hình. Lại gần hơn hoặc zoom vào tài liệu. | capturer |
| `NOT_CONVEX` | fail | `not is_convex` | Biên phát hiện bị méo (có thể do nếp gấp/bóng đổ). Vuốt phẳng tài liệu và chụp lại. | capturer |
| `CONTENT_CLIPPED` | fail | `border_ink_ratio > 0.08` (có mực sát mép ở cạnh bị khung cắt) | Một phần CHỮ nằm ngoài khung hình, không phải chỉ mất viền trắng. Lùi máy ra, chụp lại sao cho thấy trọn tài liệu kèm chút nền quanh mép. | capturer |
| `NO_CROP_DETECTED` | fail | `quad_area_ratio > 0.90` **và** `touches_border == 4` | Không tìm được biên tờ giấy, ảnh ra gần như ảnh vào. Đặt tài liệu lên nền tối, tương phản và chụp lại sao cho thấy trọn 4 mép. | capturer |
| `CLIPPED_EDGE` | warn | `touches_border ≥ 1` (và **không** phải ca trên) | Một phần tài liệu nằm ngoài khung hình. Lùi máy ra để thấy trọn 4 mép. | capturer |
| `EXTREME_SKEW` | warn | `skew_ratio > 1.8` | Góc chụp quá nghiêng — chữ sẽ bị kéo giãn sau khi nắn. Chụp vuông góc từ trên xuống. | capturer |
| `MULTIPLE_DOCUMENTS` | warn | `contour_candidates ≥ 2` | Thấy nhiều hơn một tờ trong ảnh; chỉ tờ lớn nhất được xử lý. Chụp **từng tờ một**. | capturer |
| `FALLBACK_ORIGINAL` | fail | trả ảnh gốc không nắn | Không nắn được, ảnh trả về là ảnh gốc chưa xử lý. Không đưa thẳng vào OCR. | operator |

### Chất lượng ảnh (Giai đoạn 2)

| Mã | Sev | Điều kiện | Hướng xử lý | Ai |
|---|---|---|---|---|
| `BLURRY` | fail | `blur_score < 25` (đã chốt bằng số đo) | Ảnh mờ/rung, OCR sẽ đọc sai. Giữ máy vững, chạm để lấy nét rồi chụp lại. | capturer |
| `GLARE` | warn | vùng bão hòa sáng > X% | Có vệt lóa/phản quang che chữ. Đổi hướng đèn hoặc nghiêng nhẹ máy tránh phản chiếu. | capturer |
| `TOO_DARK` | warn | độ sáng trung vị thấp | Ảnh thiếu sáng. Chụp nơi sáng hơn hoặc bật đèn. | capturer |

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

## 8. Khảo sát: lõi thuật toán có còn hợp thời? (2026)

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

- **Đừng thay detector trước khi có bộ đo.** Không có tập vàng thì "mô hình mới xịn hơn" chỉ là
  niềm tin — và ta sẽ không phát hiện được nó tệ hơn ở đúng nhóm ảnh của khách.
- **Đừng bỏ hẳn đường cũ.** Hai detector bất đồng chính là **tín hiệu QC miễn phí**: cùng chỉ
  một tứ giác → tin cao; lệch nhau → `warn` và cho người soi.
- **Đừng nhảy thẳng lên dewarping.** Đắt, phức tạp, và có thể không giải quyết vấn đề nào của
  ảnh khách. Hỏi trước ([EX-5](need_exchange.md)), đo sau, làm sau cùng.

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
