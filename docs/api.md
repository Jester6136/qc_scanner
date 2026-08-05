# Hợp đồng API — qc-scanner-server

> Đây là **bề mặt bàn giao chính** ([EX-13](need_exchange.md)): khách nhận một Docker image,
> bên trong chạy sẵn HTTP service này để hệ khác gọi vào.
>
> Mọi thứ trong tài liệu này được **test giữ** ở `tests/test_api_contract.py`. Đổi hình dạng
> phản hồi thì test đỏ, chứ không phải tích hợp của khách đỏ.

---

## 1. Chạy

```bash
docker compose up --build -d                  # cách bàn giao cho khách
qc-scanner-server -a 0.0.0.0 -p 5000          # chạy trực tiếp, không qua Docker
```

`docker-compose.yml` mở cổng `5000` trên mọi giao diện mạng (service ở máy A, ứng dụng gọi từ
máy B qua LAN) và bật healthcheck vào `/healthz`.

Mặc định bind `127.0.0.1`. Model rembg được nạp sẵn lúc khởi động (`--no-warmup` để tắt) nên
request đầu tiên không phải gánh thời gian nạp model.

> ⚠️ **Service KHÔNG có xác thực.** Theo [EX-12](need_exchange.md) nó chạy trong mạng nội bộ,
> nên **bất cứ máy nào trong LAN cũng gọi được** — chỉ an toàn chừng nào LAN là mạng tin được.
> Đừng phơi ra Internet; máy chạy có IP public hoặc bị NAT port-forward thì chặn ở firewall.
> Ảnh chỉ đi qua RAM, **không ghi xuống đĩa**.

---

## 2. `POST /` — chấm QC một file

**Request**: `multipart/form-data`, đúng một trường `file`.

Nhận **ảnh** (JPG · PNG · WebP · BMP · TIFF) hoặc **PDF**. Định dạng nhận ra từ nội dung
file, không từ tên file hay `Content-Type`.

| Tham số query | Giá trị | Mặc định | Ý nghĩa |
|---|---|---|---|
| `format` | `json` · `pdf` | *(không có)* | `json` = phán quyết đầy đủ; `pdf` = một file PDF chứa mọi trang |
| `audience` | `capturer` · `operator` | `capturer` | Hint viết cho ai ([QC-13](features_issues.md#qc-two-tier-hint)) |
| `pre_cropped` | `1` · `true` · `yes` | tắt | Ảnh **đã cắt sát từ trước** → bỏ qua kiểm tra về biên ([QC-14](features_issues.md#qc-precropped)) |

Giới hạn kích thước upload: **32 MB** (vượt → `413`).

### HTTP status

| Status | Khi nào | Thân phản hồi |
|---|---|---|
| `200` | `verdict` là `pass` hoặc `warn` | PNG đã nắn, hoặc JSON nếu `?format=json` |
| `422` | `verdict` là `fail` — ảnh hợp lệ nhưng đầu ra **không đáng tin cho OCR** | Luôn là JSON |
| `400` | Đầu vào không đánh giá được (thiếu `file`, ảnh hỏng, tham số sai) | JSON `{"error": {...}}` |
| `413` | File vượt 32 MB | `{"error": "payload quá lớn"}` |
| `503` | Lỗi tài nguyên máy chủ (`INFERENCE_FAILED`, hay gặp: hết bộ nhớ GPU) | JSON, kèm header `Retry-After` |

`503` là mã duy nhất **nên retry**: ảnh không có vấn đề gì, máy chủ mới có. Trả `400` cho ca
này thì phía gọi loại vĩnh viễn một tấm ảnh tốt.

**`422` không phải lỗi hệ thống.** Nó nghĩa là "đã xử lý xong, và kết luận là ảnh này không
dùng được". Đừng retry — chụp lại hoặc đưa người soi mới là hành động đúng.

### Phản hồi mặc định (không có `?format=json`)

`200` → thân là **PNG bytes**, kèm hai header:

```
X-QC-Scanner-Verdict:  pass | warn
X-QC-Scanner-Reasons:  CLIPPED_EDGE,GLARE      (rỗng nếu pass)
```

Dùng dạng này khi chỉ cần ảnh. Cần lý do đầy đủ thì dùng `?format=json`.

### Phản hồi `?format=json`

```jsonc
{
  "verdict": "warn",                  // "pass" | "warn" | "fail"
  "reasons": [                        // RỖNG khi và chỉ khi verdict == "pass"
    {
      "code": "CLIPPED_EDGE",         // mã ỔN ĐỊNH VĨNH VIỄN — khoá để đối chiếu
      "severity": "warn",             // "warn" | "fail"
      "message": "Có góc tài liệu nằm sát/ngoài mép ảnh.",
      "hint": "Một phần tài liệu nằm ngoài khung hình. Lùi máy ra...",
      "audience": "capturer",         // hint ở trên viết cho ai
      "hints": {                      // CẢ HAI tầng, để tự hiển thị lại theo vai
        "capturer": "...",
        "operator": "..."
      },
      "detail": "touches_border=1"    // tuỳ chọn: số đo đã kích hoạt mã này
    }
  ],
  "metrics": { "quad_area_ratio": 0.6724, "blur_score": 48.4, ... },
  "corners": [[208.9, 114.7], [884.7, 73.7], [1138.7, 1908.7], [94.2, 1957.9]],
  "image": "iVBORw0KGgo..."           // PNG mã hoá base64
}
```

**Bất biến của hợp đồng** (có test giữ):

- `verdict == "pass"` ⟺ `reasons == []`. Không có "pass kèm cảnh báo".
- `verdict == "fail"` ⟺ có ít nhất một reason `severity == "fail"`.
- Mọi reason **luôn** có `code`, `severity`, `message`, `hint`, `audience`, `hints`.
- `code` là **ổn định vĩnh viễn** — nó đi vào log/CSV của khách. `message` và `hint` có thể
  sửa hoặc dịch, nên **đừng so khớp chuỗi**, hãy so `code`.
- `corners` theo thứ tự **TL-TR-BR-BL** trong hệ toạ độ **ảnh gốc**; `null` khi không dựng
  được tứ giác.

### Phản hồi cho PDF nhiều trang

Ảnh rời và PDF **một trang** dùng đúng hợp đồng ở trên, không đổi một byte nào.

PDF **nhiều trang** thì không có hình dạng "một file PNG" nào để trả về, nên nó **luôn** ra
JSON — kể cả khi không có `?format=json`:

```jsonc
{
  "source": "pdf",                    // "image" | "pdf"
  "verdict": "fail",                  // TRANG TỆ NHẤT, không phải trang đầu
  "page_count": 3,
  "pages": [
    {"page": 1, "verdict": "pass", "reasons": [], "metrics": {...}, "image": "iVBO..."},
    {"page": 2, "verdict": "fail", "reasons": [...], "metrics": {...}, "image": "iVBO..."},
    {"page": 3, "verdict": "warn", "reasons": [...], "metrics": {...}, "image": "iVBO..."}
  ]
}
```

Mỗi phần tử `pages[]` có đúng hình dạng của phản hồi `?format=json` một trang, cộng thêm khoá
`page` (đánh số từ 1). HTTP status suy từ `verdict` gộp, theo đúng bảng trên.

**`verdict` gộp là trang tệ nhất.** Một bộ hồ sơ có 1 trang mờ không đọc được thì chưa dùng
được, dù 11 trang kia hoàn hảo. Cần xử lý từng trang riêng thì đọc `pages[].verdict`.

Phân biệt hai dạng phản hồi bằng `page_count` (hoặc bằng `Content-Type`: `image/png` với một
trang, `application/json` với nhiều trang).

### `?format=pdf` — nhận về một file PDF

Dùng được cho **cả ảnh lẫn PDF** đầu vào: ảnh rời ra PDF một trang (gộp giấy tờ chụp rời thành
một file nộp), PDF nhiều trang ra PDF nhiều trang.

```
Content-Type:          application/pdf
X-QC-Scanner-Verdict:  pass | warn
X-QC-Scanner-Reasons:  CLIPPED_EDGE,GLARE      (gộp mọi trang, không lặp)
X-QC-Scanner-Pages:    3
```

Theo đúng quy tắc của PNG: `verdict` là `fail` thì trả **JSON lý do**, không trả file. Đưa ra
một PDF trông bình thường cho một tài liệu không đọc được là cách chắc chắn nhất để nó bị dùng
tiếp.

Ảnh vào PDF **không bị nén mất dữ liệu** (pdfium nén Flate), vì lý do y hệt lý do đầu ra mặc
định là PNG chứ không phải JPEG: file đi tiếp vào OCR/VLM và nhiễu nén quanh nét chữ nhỏ làm
giảm độ chính xác bóc dữ liệu. Ở đây gần như không có gì để đánh đổi — đo trên một trang
1053×1852: PNG 1276 KB · **PDF lossless 988 KB** (nhỏ hơn PNG) · JPEG q92 166 KB. Cần file nhỏ
thì bật `QC_SCANNER_PDF_OUT_JPEG_QUALITY`.

Khổ trang suy từ `QC_SCANNER_PDF_OUT_DPI` (mặc định 300) và là **phỏng đoán**: từ một ảnh đã
cắt thì không biết tờ giấy thật to bao nhiêu ([EX-4](need_exchange.md)). Nó chỉ đổi con số
"trang này to bằng chừng nào giấy" — **số điểm ảnh không đổi**, và đó mới là thứ OCR dùng.

### PDF được đọc như thế nào

Trang PDF **chính là** tờ giấy — máy scan cắt xong mới đóng thành PDF — nên mọi trang đều
được chấm với `pre_cropped` bật sẵn ([QC-14](features_issues.md#qc-precropped)). Không có nó
thì "tứ giác trùm gần kín khung và chạm cả 4 mép" đúng theo nghĩa đen với **mọi** trang scan,
và mọi trang đều `fail` vì `NO_CROP_DETECTED`. Tắt bằng `QC_SCANNER_PDF_PRE_CROPPED=0`.

Trang scan được lấy **thẳng bitmap nhúng** ra, không render, không resample lần nào. Lý do
nằm ở số đo (`blur_score`, ngưỡng 25):

| Đường đọc | `blur_score` |
|---|---|
| lấy thẳng bitmap nhúng | 44.4 |
| render đúng DPI thật | 36.9 |
| render gấp đôi DPI thật | **3.5** |

Chọn sẵn một DPI để render thì gần như không bao giờ trùng DPI thật của ảnh bên trong, và
lệch lên trên là **mọi trang đều `BLURRY`**. Trang không phải bản scan (PDF sinh từ máy tính)
mới render, ở `QC_SCANNER_PDF_RENDER_DPI` (mặc định 200).

`metrics.pdf_source` nói mỗi trang đã đi đường nào: `embedded` hay `render@<DPI>`.

Trần **50 trang** một file (`QC_SCANNER_PDF_MAX_PAGES`). Vượt trần thì trả `400` +
`PDF_TOO_MANY_PAGES` và **không xử lý trang nào** — trả về 50 trang đầu của một file 200
trang mà không nói gì sẽ khiến phía gọi tưởng đã soi hết.

### Lỗi `400`

```jsonc
{"error": {
  "code": "DECODE_FAILED",
  "severity": "fail",
  "message": "Không giải mã được dữ liệu thành ảnh.",
  "hint": "...", "audience": "system", "hints": {...},
  "detail": "cv2.imdecode không đọc được dữ liệu vào"
}}
```

Mọi `400` dùng **cùng một hình dạng** — `error` luôn là object có `code`, không bao giờ là
chuỗi trần. Hay gặp: `MISSING_FILE`, `FILE_EMPTY`, `DECODE_FAILED`, và với PDF thì
`PDF_DECODE_FAILED` (file hỏng **hoặc có mật khẩu**), `PDF_NO_PAGES`, `PDF_TOO_MANY_PAGES`.

### CORS — gọi từ trình duyệt

Bật sẵn, mặc định cho **mọi origin** (`*`), vì ca dùng chính là app chạy ở máy B gọi service ở
máy A. Thu hẹp bằng biến môi trường:

```bash
QC_SCANNER_CORS_ORIGINS=http://app.noi-bo,http://192.168.1.50:3000
```

Hai header phán quyết được khai báo trong `Access-Control-Expose-Headers`. **Đây là chỗ dễ sót
nhất**: thiếu nó thì `fetch()` vẫn trả `200` và vẫn có ảnh, nhưng
`res.headers.get('X-QC-Scanner-Verdict')` ra `null` — hỏng **âm thầm**, không thông báo lỗi nào.

```js
const res = await fetch(`http://<IP-máy-A>:5000/?format=json`, { method: 'POST', body: form });
const { verdict, reasons } = await res.json();     // hoặc đọc header nếu không dùng format=json
```

> `allow_credentials` **tắt**: service không có phiên đăng nhập nào để gửi kèm, và bật lên thì
> trình duyệt từ chối `allow_origins=["*"]`.
>
> CORS **không phải** lớp bảo vệ service — nó chỉ chi phối trình duyệt. Thứ đang bảo vệ API này
> là việc nó nằm trong mạng nội bộ ([EX-12](need_exchange.md)), không phải danh sách origin.

---

## 3. `GET /docs` — thử API bằng trình duyệt

FastAPI dựng sẵn Swagger UI ở `/docs` (và OpenAPI JSON ở `/openapi.json`). Mở
`http://<IP-máy-chạy>:5000/docs` là gọi thử được `POST /` ngay trên trình duyệt, không cần
`curl`.

> Trang này **mô tả** hợp đồng chứ không **định nghĩa** nó. Nguồn sự thật vẫn là tài liệu bạn
> đang đọc, vì nhiều điều quan trọng nhất — `422` nghĩa là gì, bất biến `pass ⟺ reasons rỗng`,
> mã nào ổn định vĩnh viễn — là quy ước, không suy ra được từ chữ ký hàm.
>
> Nó cũng công khai toàn bộ bề mặt API cho bất cứ ai gọi được vào cổng. Trong mạng nội bộ
> (EX-12) thì chấp nhận được; đặt ở chỗ khác thì tắt bằng `FastAPI(docs_url=None)`.

---

## 4. `GET /healthz`

```json
{
  "status": "ok",
  "version": "0.2.0",
  "model": "u2net",
  "providers": ["CPUExecutionProvider"],
  "max_concurrency": 2
}
```

Dùng cho liveness probe. Nó **không** kiểm model đã nạp xong chưa — nhưng server nạp model
*trước khi* mở cổng, nên cổng mở được đã có nghĩa là model sẵn sàng (trừ khi chạy `--no-warmup`).

Endpoint này trả lời **kể cả khi mọi luồng xử lý ảnh đang bận** ([SPD-2](features_issues.md#spd-event-loop)):
đo dưới tải 8 request song song, độ trễ trung vị 2ms.

`providers` là execution provider onnxruntime **thật sự đang chạy**, không phải cái được yêu
cầu trong cấu hình. Đây là chỗ duy nhất kiểm được đường GPU: thiếu thư viện CUDA thì
onnxruntime **không báo lỗi**, chỉ lặng lẽ tụt về `CPUExecutionProvider` và chạy chậm hơn vài
chục lần. Thấy `CUDAExecutionProvider` ở đây thì GPU mới thật sự đang chạy.

### Tốc độ và số ảnh xử lý cùng lúc

Một ảnh tốn ~0.4s CPU, trong đó ~80% là bản thân model u2net.

`QC_SCANNER_MAX_CONCURRENCY` (mặc định `2`) chặn số ảnh xử lý cùng lúc; request thứ N+1 **xếp
hàng** thay vì cùng chậm đi. Đặt 2 vì onnxruntime vốn đã dùng hết số nhân CPU cho một lần suy
luận — đo trên 8 request song song: 1→3.19s · **2→2.83s** · 4→2.93s · 8→3.10s. Máy có GPU thì
nút cổ chai đảo sang phần CPU (giải mã ảnh, mã hoá PNG) nên nên nâng lên.

Ảnh upload nằm **trọn trong RAM**, không qua file tạm — trần bộ nhớ là 32MB × `MAX_CONCURRENCY`.

Muốn biết máy đích chịu được bao nhiêu, **đo chứ đừng suy**:

```bash
docker exec qc-scanner qc-scanner-bench --url http://127.0.0.1:5000
```

Nó in luôn bảng quy đổi ảnh/s → CCU. Về câu hỏi 700 CCU và dynamic batching, xem
[SPD-5](features_issues.md#spd-batching) và [EX-16](need_exchange.md#ex-throughput).

### Chạy trên GPU NVIDIA

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
curl -s http://localhost:5000/healthz          # providers phải có CUDAExecutionProvider
```

⚠️ Đường GPU **chưa từng chạy thử** — xem [SPD-4](features_issues.md#spd-gpu).

---

## 5. `GET /` → `405`

Nhánh `GET /?url=` cũ **đã bị bỏ hẳn** ([SEC-1](features_issues.md#sec-ssrf)): nó tải URL tuỳ ý
do người dùng cung cấp, kể cả `file:///etc/passwd` và metadata nội bộ của cloud. Đừng khôi
phục. Có test chặn.

---

## 6. Danh mục mã lý do

25 mã, kèm điều kiện phát hiện và hướng xử lý:
[algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes). Danh mục đó được test giữ
cho khớp với code — mã nào chạy được thì chắc chắn có dòng trong đó.

Nhóm theo hành động của phía gọi:

| Nhóm | Mã | Phía gọi nên làm gì |
|---|---|---|
| Lỗi tích hợp / đầu vào | `MISSING_FILE` `FILE_EMPTY` `DECODE_FAILED` `PDF_DECODE_FAILED` `PDF_NO_PAGES` `PDF_TOO_MANY_PAGES` `PDF_MULTIPAGE` | Sửa phía gọi, đừng retry |
| Sự cố máy chủ | `INFERENCE_FAILED` | **Retry** — ảnh không có vấn đề gì |
| Ảnh không dùng được (`fail`) | `NO_CROP_DETECTED` `CONTENT_CLIPPED` `QUAD_NOT_FOUND` `SUBJECT_NOT_FOUND` `TOO_SMALL` `NOT_CONVEX` `FALLBACK_ORIGINAL` `LOW_RESOLUTION` `BLURRY` | Chụp lại, hoặc đưa người soi |
| Dùng được nhưng có rủi ro (`warn`) | `CLIPPED_EDGE` `EXTREME_SKEW` `GLARE` `TOO_DARK` `MULTIPLE_DOCUMENTS` `RECOVERED_BY_EDGE_FALLBACK` `DETECTOR_DISAGREEMENT` | Vào hàng chờ người soi ([EX-8](need_exchange.md)) |

---

## 7. Ví dụ

```bash
# Chỉ lấy ảnh
curl -f -X POST -F file=@anh.jpg http://localhost:5000/ -o out.png

# Lấy phán quyết đầy đủ
curl -X POST -F file=@anh.jpg 'http://localhost:5000/?format=json' | jq .verdict,.reasons

# Luồng xử lý kho ảnh: ảnh đã cắt sẵn, hint viết cho người soi
curl -X POST -F file=@anh.jpg \
  'http://localhost:5000/?format=json&pre_cropped=1&audience=operator'

# PDF: cùng một endpoint, không cần tham số gì thêm
curl -X POST -F file=@hoso.pdf http://localhost:5000/ | jq '.verdict, .page_count'

# Nhận về PDF: ảnh vào cũng được, PDF vào cũng được
curl -f -X POST -F file=@hoso.pdf 'http://localhost:5000/?format=pdf' -o daxuly.pdf
curl -f -X POST -F file=@anh.jpg  'http://localhost:5000/?format=pdf' -o daxuly.pdf

# Chỉ lấy những trang không đạt
curl -X POST -F file=@hoso.pdf http://localhost:5000/ \
  | jq '.pages[] | select(.verdict != "pass") | {page, codes: [.reasons[].code]}'
```

Phân biệt bằng exit status thay vì đọc thân phản hồi:

```bash
code=$(curl -s -o out.png -w '%{http_code}' -X POST -F file=@anh.jpg http://localhost:5000/)
case "$code" in
  200) echo "dùng được" ;;
  422) echo "ảnh không đạt — xem reasons" ;;
  400) echo "lỗi đầu vào — sửa phía gọi" ;;
esac
```

---

## 8. Chưa có, và biết là chưa có

- **Không có xác thực** — dựa hoàn toàn vào việc chỉ chạy trong mạng nội bộ (EX-12).
- **Không có giới hạn tần suất**; một request nặng ~0.4s CPU.
- **Một tiến trình, không `workers`** — mỗi worker nạp một bản model vào RAM, và onnxruntime
  vốn đã dùng nhiều luồng. Trong tiến trình đó, `MAX_CONCURRENCY` ảnh chạy song song trên
  threadpool. Cần thông lượng cao hơn thì đổi sang GPU trước (đó là 80% thời gian), rồi mới
  tính nhiều container sau một bộ cân bằng tải — **đo trước rồi hãy làm**.
- ⚠️ **Đường GPU chưa từng chạy thử** — [SPD-4](features_issues.md#spd-gpu). Bản CPU thì đã
  build và chạy được trên máy server.
- **Mỗi request một ảnh.** Không có khái niệm "hồ sơ nhiều trang" — một giấy chứng nhận chụp
  hai mặt là **hai** request độc lập. Việc ghép và kiểm đủ mặt thuộc hệ gọi, xem
  [EX-15](need_exchange.md#ex-multipage).
- **Không có endpoint xử lý lô.** Chạy lô dùng CLI `qc-scanner-batch`, không qua HTTP.
- ⚠️ **Docker image chưa từng build thử** — xem [OPS-3](features_issues.md#ops-docker-unverified).
  Phần hợp đồng trong tài liệu này thì đã có test giữ và chạy được ngoài Docker.
