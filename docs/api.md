# Hợp đồng API — qc-scanner-server

> Đây là **bề mặt bàn giao chính** ([EX-13](need_exchange.md)): khách nhận một Docker image,
> bên trong chạy sẵn HTTP service này để hệ khác gọi vào.
>
> Mọi thứ trong tài liệu này được **test giữ** ở `tests/test_api_contract.py` và
> `tests/test_auth.py`. Đổi hình dạng phản hồi thì test đỏ, chứ không phải tích hợp của khách
> đỏ.

**Đọc nhanh**: [xác thực](#xac-thuc) · [gọi thử](#vi-du) · [mã lý do](#ma-ly-do) ·
[gọi song song](#song-song) · [chưa có gì](#chua-co)

---

## 1. Chạy

```bash
QC_SCANNER_API_KEYS="app-web:qcs-…" docker compose up --build -d   # cách bàn giao cho khách
qc-scanner-server -a 0.0.0.0 -p 5000                               # chạy trực tiếp
```

`docker-compose.yml` mở cổng `5000` trên mọi giao diện mạng (service ở máy A, ứng dụng gọi từ
máy B qua LAN) và bật healthcheck vào `/healthz`. Chạy trực tiếp thì mặc định bind `127.0.0.1`.

**Hai model, đều nướng sẵn vào image lúc build** nên container chạy được khi máy đích không ra
Internet:

| Model | Vai trò | Nơi chứa |
|---|---|---|
| DocAligner (~83 MB) | detector chính — hồi quy thẳng 4 góc | `DOCALIGNER_HOME` |
| rembg / U²-Net (~176 MB) | đường lui khi detector chính trả rỗng | `U2NET_HOME` |

Chạy ngoài Docker thì tải một lần: `qc-scanner-fetch-models --head heatmap`. Thiếu file này thì
mọi request trả `MODEL_MISSING` — đó là lỗi **cài đặt máy chủ**, không phải lỗi ảnh.

Model được nạp sẵn lúc khởi động (`--no-warmup` để tắt) nên request đầu tiên không phải gánh
thời gian nạp.

Ảnh chỉ đi qua RAM, **không ghi xuống đĩa** ([EX-12](need_exchange.md)).

---

## 2. Xác thực {#xac-thuc}

Mọi request cần một API key ở header `Authorization`, kiểu Bearer token:

```bash
curl -s http://<IP>:5000/ \
  -H "Authorization: Bearer qcs-a1b2c3…" \
  -F "file=@anh.jpg"
```

**Sinh key** — in ra dòng cấu hình dán được ngay:

```bash
qc-scanner-apikey app-web
# QC_SCANNER_API_KEYS="app-web:qcs-9f3a…"
```

**Cấu hình** — nhiều key, mỗi client một cái, ngăn cách bằng dấu phẩy:

```yaml
environment:
  QC_SCANNER_API_KEYS: "app-web:qcs-9f3a…,batch:qcs-77c1…"
```

Mỗi key gắn một **tên client**. Nhờ vậy thu hồi được từng client mà không đụng client khác, và
log biết ai đang gọi — lộ key thì còn truy được nguồn. **Xoay key không cần dừng service**:
thêm key mới → chuyển client sang → bỏ key cũ; hai key cùng sống một lúc là bình thường.

| | |
|---|---|
| Thiếu key / key sai | `401` + `{"error": {"code": "UNAUTHORIZED", …}}` + header `WWW-Authenticate` |
| `/healthz` | **Không** cần key — healthcheck của Docker chạy `urllib` trần bên trong container, không có chỗ nhét key. Đổi lại nó chỉ trả `auth: "on"/"off"`, không bao giờ trả key hay tên client |
| Preflight `OPTIONS` | Không cần key — trình duyệt không gửi header tuỳ biến ở bước preflight, và bước đó không đọc được dữ liệu gì |

**Chưa đặt key thì server không khởi động.** Muốn chạy mở phải khai báo tường minh
`QC_SCANNER_AUTH=off`, và mỗi lần khởi động sẽ in một cảnh báo ra `stderr`.

Không có đường vô tình rơi vào trạng thái mở, vì "quên bật xác thực" là kiểu hỏng **không tự
biểu hiện**: service vẫn chạy, `/healthz` vẫn `ok`, ảnh vẫn được chấm — nó chỉ lộ ra khi đã có
người lạ đọc được giấy tờ của khách. Cùng lý do đó, cấu hình sai thì service **khoá hết** chứ
không mở hết.

> ⚠️ **Giới hạn thật, đừng hiểu nhầm lớp này mạnh hơn nó có.** Key đi qua HTTP thuần là **gửi
> mật khẩu dạng chữ rõ**: ai bắt được gói tin trong LAN là đọc được key và dùng lại vô thời
> hạn. Nó chặn được người gọi nhầm và người dò cổng, **không** chặn được người nghe lén trên
> chính đường truyền. Muốn kín thật thì đặt một reverse proxy có TLS (Caddy/nginx) trước
> container.
>
> Vẫn giữ nguyên: đừng phơi ra Internet; máy chạy có IP public hoặc bị NAT port-forward thì
> chặn ở firewall.

---

## 3. `POST /` — chấm QC một file

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
| `401` | Thiếu hoặc sai API key (`UNAUTHORIZED`) — xem [§2](#xac-thuc) | JSON, kèm `WWW-Authenticate` |
| `413` | File vượt 32 MB | `{"error": "payload quá lớn"}` |
| `503` | Máy chủ kín tải (`SERVER_BUSY`) hoặc lỗi tài nguyên (`INFERENCE_FAILED`, `MODEL_MISSING`) | JSON, kèm header `Retry-After` |

`503` là mã duy nhất **nên retry**: ảnh không có vấn đề gì, máy chủ mới có. Trả `400` cho ca
này thì phía gọi loại vĩnh viễn một tấm ảnh tốt.

**`422` không phải lỗi hệ thống.** Nó nghĩa là "đã xử lý xong, và kết luận là ảnh này không
dùng được". Đừng retry — chụp lại hoặc đưa người soi mới là hành động đúng.

**`401` cũng đừng retry cùng key đó.** Nó là lỗi cấu hình phía gọi; gửi lại nguyên xi chỉ tốn
một vòng mạng. Ảnh **chưa được xử lý lần nào**, nên đừng đánh dấu nó là ảnh hỏng.

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
      "message": "Có góc tài liệu nằm sát hoặc ngoài mép ảnh.",
      "hint": "Một phần tài liệu nằm ngoài khung. Lùi máy ra cho thấy trọn 4 mép.",
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

### Biên tờ giấy được tìm thế nào {#detector}

Ba tầng, và `metrics.detector` nói tầng nào đã ra kết quả:

1. **`docaligner`** — mô hình hồi quy thẳng 4 góc. Đường chính.
2. **`rembg-contour`** — tách nền rồi lần contour. Chạy khi tầng 1 trả rỗng, kèm
   `RECOVERED_BY_MASK_FALLBACK` (`warn`). Hay gặp với **ảnh đã cắt sẵn**: không còn nền quanh
   tờ giấy nên tầng 1 không nhận ra "có một tài liệu ở đây".
3. **`edge-hough`** — dò cạnh cổ điển, kèm `RECOVERED_BY_EDGE_FALLBACK` (`warn`).

Hết ba tầng thì trả ảnh **gốc chưa nắn** + `FALLBACK_ORIGINAL` (`fail`) — có nhãn rõ ràng, chứ
không im lặng trả một ảnh trông như đã xử lý.

`metrics.detector_confidence` **không so được giữa các tầng**: `rembg-contour` trả hai giá trị
rời rạc (0.9 / 0.6), `docaligner` trả một số thực. Đừng đặt ngưỡng của riêng bạn lên nó; đọc
`verdict` và mã lý do.

### Ảnh trả về đã được nắn thẳng

Ngoài phép nắn phối cảnh, ảnh ra còn được **xoay về ngang** theo phần dư đo được. Hai metric đi
kèm, và chúng **khác nhau có chủ đích**:

| Metric | Nghĩa |
|---|---|
| `text_skew_deg` | góc dòng chữ **đo được**, trước khi sửa. `null` = trang quá ít mực để đo |
| `deskew_applied_deg` | góc đã thật sự xoay. `null` = không xoay |

`text_skew_deg` giữ nguyên số **trước** khi sửa để bên gọi còn biết ảnh vào lệch bao nhiêu — gộp
làm một thì mọi ảnh đều báo ~0 và chỉ số mất hết giá trị chẩn đoán.

Lệch quá `8°` thì **không xoay**, mà phát `TEXT_NOT_LEVEL` (`fail`): mức đó không phải "hơi
nghiêng" mà là dấu hiệu phép nắn đã hỏng — thường do tờ giấy bị gấp góc làm máy nhận nhầm mép.
Xoay nó về 0 chỉ làm một ảnh đã mất nội dung trông như hợp lệ.

Ảnh ra vì thế **to hơn** khung nắn một chút (trung vị +1.7%, do bốn nêm góc). Tắt bằng
`QC_SCANNER_DESKEW=0` nếu cần bản gốc lưu trữ — xem
[QC-19b](features_issues.md#qc-deskew-default).

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
giảm độ chính xác bóc dữ liệu. Đo trên một trang 1053×1852: PNG 1276 KB · **PDF lossless 988
KB** · JPEG q92 166 KB. Cần file nhỏ thì bật `QC_SCANNER_PDF_OUT_JPEG_QUALITY`.

Khổ trang suy từ `QC_SCANNER_PDF_OUT_DPI` (mặc định 300) và là **phỏng đoán**: từ một ảnh đã
cắt thì không biết tờ giấy thật to bao nhiêu ([EX-4](need_exchange.md)). Nó chỉ đổi con số
"trang này to bằng chừng nào giấy" — **số điểm ảnh không đổi**, và đó mới là thứ OCR dùng.

### PDF được đọc như thế nào

Trang PDF **chính là** tờ giấy — máy scan cắt xong mới đóng thành PDF — nên mọi trang đều
được chấm với `pre_cropped` bật sẵn ([QC-14](features_issues.md#qc-precropped)). Không có nó
thì "tứ giác trùm gần kín khung và chạm cả 4 mép" đúng theo nghĩa đen với **mọi** trang scan,
và mọi trang đều `fail` vì `NO_CROP_DETECTED`. Tắt bằng `QC_SCANNER_PDF_PRE_CROPPED=0`.

Cờ đó cũng che `RECOVERED_BY_MASK_FALLBACK`: trang PDF không có nền quanh tờ giấy nên detector
chính **luôn** trả rỗng và đường lui **luôn** chạy. Báo điều đó ở mọi trang PDF là đẩy cả kho
vào hàng chờ người soi mà không thêm thông tin nào.

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

### Lỗi `400` và `401`

```jsonc
{"error": {
  "code": "DECODE_FAILED",
  "severity": "fail",
  "message": "Không giải mã được dữ liệu thành ảnh.",
  "hint": "...", "audience": "system", "hints": {...},
  "detail": "cv2.imdecode không đọc được dữ liệu vào"
}}
```

Mọi lỗi dùng **cùng một hình dạng** — `error` luôn là object có `code`, không bao giờ là chuỗi
trần. Hay gặp: `MISSING_FILE`, `FILE_EMPTY`, `DECODE_FAILED`, `UNAUTHORIZED`, và với PDF thì
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
const res = await fetch(`http://<IP-máy-A>:5000/?format=json`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${key}` },
  body: form,
});
const { verdict, reasons } = await res.json();
```

> ⚠️ Gọi từ trình duyệt nghĩa là **API key nằm trong mã chạy ở máy người dùng** — ai mở
> DevTools cũng đọc được. Với app nội bộ trong LAN thì có thể chấp nhận; nếu không, để một
> backend giữ key và gọi hộ, đừng đưa key xuống trình duyệt.
>
> `allow_credentials` **tắt**: service không có phiên đăng nhập nào để gửi kèm, và bật lên thì
> trình duyệt từ chối `allow_origins=["*"]`. Key đi ở header `Authorization` nên không cần.
>
> CORS **không phải** lớp bảo vệ service — nó chỉ chi phối trình duyệt. `curl` không quan tâm
> tới nó. Thứ chặn người lạ là API key, không phải danh sách origin.

---

## 4. `GET /docs` — thử API bằng trình duyệt

FastAPI dựng sẵn Swagger UI ở `/docs` (và OpenAPI JSON ở `/openapi.json`). Mở
`http://<IP-máy-chạy>:5000/docs` là gọi thử được `POST /` ngay trên trình duyệt, không cần
`curl` — nhớ bấm **Authorize** và dán key vào trước.

> Trang này **mô tả** hợp đồng chứ không **định nghĩa** nó. Nguồn sự thật vẫn là tài liệu bạn
> đang đọc, vì nhiều điều quan trọng nhất — `422` nghĩa là gì, bất biến `pass ⟺ reasons rỗng`,
> mã nào ổn định vĩnh viễn — là quy ước, không suy ra được từ chữ ký hàm.
>
> Nó cũng công khai toàn bộ bề mặt API cho bất cứ ai gọi được vào cổng. Tắt bằng
> `FastAPI(docs_url=None)` nếu không muốn.

---

## 5. `GET /healthz` {#healthz}

```json
{
  "status": "ok",
  "version": "0.2.0",
  "model": "u2net",
  "providers": ["CPUExecutionProvider"],
  "max_concurrency": 16,
  "max_in_flight": 32,
  "in_flight": 0,
  "auth": "on"
}
```

Dùng cho liveness probe, và là đường **duy nhất không cần key**. Vì thế nó chỉ nói `auth` là
`on` hay `off` — không bao giờ nói có bao nhiêu key hay tên client nào.

Nó **không** kiểm model đã nạp xong chưa — nhưng server nạp model *trước khi* mở cổng, nên cổng
mở được đã có nghĩa là model sẵn sàng (trừ khi chạy `--no-warmup`).

Endpoint này trả lời **kể cả khi mọi luồng xử lý ảnh đang bận**
([SPD-2](features_issues.md#spd-event-loop)): đo dưới tải 8 request song song, độ trễ trung vị
2ms.

`providers` là execution provider onnxruntime **thật sự đang chạy**, không phải cái được yêu
cầu trong cấu hình. Đây là chỗ duy nhất kiểm được đường GPU: thiếu thư viện CUDA thì
onnxruntime **không báo lỗi**, chỉ lặng lẽ tụt về `CPUExecutionProvider` và chạy chậm hơn vài
chục lần.

Ba thứ đáng kiểm ngay sau mỗi lần deploy:

```bash
curl -s http://localhost:5000/healthz | jq '.auth, .providers, .max_concurrency'
```

### Tốc độ và số ảnh xử lý cùng lúc

Một ảnh tốn ~0.44s trên máy dev CPU. Chặng dò biên chính chỉ ~42ms; phần lớn thời gian còn lại
là rembg — nó **vẫn chạy mỗi ảnh** để lấy `alpha_coverage`, làm đường lui, và đếm đa tài liệu.

`QC_SCANNER_MAX_CONCURRENCY` chặn số ảnh xử lý cùng lúc; request thứ N+1 **xếp hàng** thay vì
cùng chậm đi. Mặc định **suy theo số nhân của máy đích** — đừng ghi cứng nó vào
`docker-compose.yml`, một con số đo trên máy dev lọt vào file bàn giao đã từng làm mất ~64%
năng lực máy server, và mất im lặng.

Ảnh upload nằm **trọn trong RAM**, không qua file tạm.

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

## 6. `GET /` → `405`

Nhánh `GET /?url=` cũ **đã bị bỏ hẳn** ([SEC-1](features_issues.md#sec-ssrf)): nó tải URL tuỳ ý
do người dùng cung cấp, kể cả `file:///etc/passwd` và metadata nội bộ của cloud. Đừng khôi
phục. Có test chặn.

---

## 7. Danh mục mã lý do {#ma-ly-do}

**30 mã**, kèm điều kiện phát hiện và hướng xử lý: [algorithm.md §7](algorithm.md#ma-ly-do).
Danh mục đó được test giữ cho khớp với code — mã nào chạy được thì chắc chắn có dòng trong đó.

Nhóm theo hành động của phía gọi:

| Nhóm | Mã | Phía gọi nên làm gì |
|---|---|---|
| Lỗi tích hợp / đầu vào | `MISSING_FILE` `FILE_EMPTY` `DECODE_FAILED` `PDF_DECODE_FAILED` `PDF_NO_PAGES` `PDF_TOO_MANY_PAGES` `PDF_MULTIPAGE` | Sửa phía gọi, đừng retry |
| Xác thực | `UNAUTHORIZED` | Sửa key phía gọi. **Đừng retry** cùng key đó, và đừng đánh dấu ảnh là hỏng |
| Sự cố / quá tải máy chủ | `SERVER_BUSY` `INFERENCE_FAILED` `MODEL_MISSING` | **Retry** — ảnh không có vấn đề gì (`MODEL_MISSING` phải sửa image trước) |
| Ảnh không dùng được (`fail`) | `NO_CROP_DETECTED` `CONTENT_CLIPPED` `QUAD_NOT_FOUND` `SUBJECT_NOT_FOUND` `TOO_SMALL` `NOT_CONVEX` `FALLBACK_ORIGINAL` `LOW_RESOLUTION` `BLURRY` `TEXT_NOT_LEVEL` | Chụp lại, hoặc đưa người soi |
| Dùng được nhưng có rủi ro (`warn`) | `CLIPPED_EDGE` `EXTREME_SKEW` `GLARE` `TOO_DARK` `MULTIPLE_DOCUMENTS` `RECOVERED_BY_MASK_FALLBACK` `RECOVERED_BY_EDGE_FALLBACK` `DETECTOR_DISAGREEMENT` | Vào hàng chờ người soi ([EX-8](need_exchange.md)) |
| **Đã ngừng phát** | `SUBJECT_FILLS_FRAME` | Không xuất hiện nữa từ QC-15. Mã vẫn được giữ vì `code` là ổn định vĩnh viễn và log cũ còn tham chiếu — đừng viết nhánh xử lý mới cho nó |

---

## 8. Ví dụ {#vi-du}

```bash
KEY="qcs-9f3a…"

# Chỉ lấy ảnh
curl -f -X POST -H "Authorization: Bearer $KEY" \
  -F file=@anh.jpg http://localhost:5000/ -o out.png

# Lấy phán quyết đầy đủ
curl -X POST -H "Authorization: Bearer $KEY" \
  -F file=@anh.jpg 'http://localhost:5000/?format=json' | jq .verdict,.reasons

# Luồng xử lý kho ảnh: ảnh đã cắt sẵn, hint viết cho người soi
curl -X POST -H "Authorization: Bearer $KEY" -F file=@anh.jpg \
  'http://localhost:5000/?format=json&pre_cropped=1&audience=operator'

# PDF: cùng một endpoint, không cần tham số gì thêm
curl -X POST -H "Authorization: Bearer $KEY" \
  -F file=@hoso.pdf http://localhost:5000/ | jq '.verdict, .page_count'

# Nhận về PDF: ảnh vào cũng được, PDF vào cũng được
curl -f -X POST -H "Authorization: Bearer $KEY" \
  -F file=@hoso.pdf 'http://localhost:5000/?format=pdf' -o daxuly.pdf

# Chỉ lấy những trang không đạt
curl -X POST -H "Authorization: Bearer $KEY" -F file=@hoso.pdf http://localhost:5000/ \
  | jq '.pages[] | select(.verdict != "pass") | {page, codes: [.reasons[].code]}'
```

Phân biệt bằng HTTP status thay vì đọc thân phản hồi:

```bash
code=$(curl -s -o out.png -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $KEY" -F file=@anh.jpg http://localhost:5000/)
case "$code" in
  200) echo "dùng được" ;;
  422) echo "ảnh không đạt — xem reasons" ;;
  401) echo "sai API key — lỗi cấu hình, không phải lỗi ảnh" ;;
  400) echo "lỗi đầu vào — sửa phía gọi" ;;
esac
```

> Đừng để key trong lịch sử shell hay trong file commit lên git. Đọc từ biến môi trường của
> tiến trình gọi, hoặc từ một secret store.

---

## 9. Gọi song song {#song-song}

**Có, gọi nhiều request cùng lúc được, và nên làm.** Service không có phiên, không có state
giữa các request, không có thứ tự nào phải giữ — mỗi request độc lập hoàn toàn. Gửi tuần tự là
bỏ phí phần lớn năng lực máy chủ.

### Nên gửi bao nhiêu request cùng lúc

Đọc `max_concurrency` ở [`/healthz`](#healthz) và dùng đúng con số đó. Nó suy theo số nhân CPU
của máy chạy, nên khác nhau giữa các lần triển khai — **đừng ghi cứng trong code phía gọi**.

Đo trên máy server 64 nhân (`max_concurrency` = 16) xác nhận con số đó là đúng chỗ:

| Song song | req/s | p50 |
|---|---|---|
| 8 | 5.14 | 1.16s |
| **16** | **7.69** | **1.75s** |
| 32 | 8.43 | 2.55s |

Gửi 32 thay vì 16 mua thêm 9.6% thông lượng và trả bằng **46% độ trễ** — món lỗ cho mọi người
đang chờ. `qc-scanner-bench --url …` in thẳng mức nên khuyên cho từng máy.

### Vượt quá thì sao

Hai nấc, theo thứ tự:

1. **Xếp hàng** — quá `max_concurrency`, request chờ đến lượt và vẫn trả `200`/`422` bình
   thường. Thông lượng đứng yên, độ trễ dâng gần như tuyến tính theo số request đang chờ.
2. **Bị đẩy lùi** — quá `max_in_flight`, request nhận `503` + `SERVER_BUSY` + `Retry-After`.

`SERVER_BUSY` nghĩa là **ảnh chưa được xử lý lần nào** — không phải phán quyết về ảnh. Gửi lại
là việc đúng; đối xử với nó như `fail` là loại nhầm một ảnh tốt.

Vì sao có nấc thứ hai: thân request nằm trong RAM ngay khi tới, **trước khi** xin được suất xử
lý. `max_concurrency` chặn *số ảnh đang xử lý*, không chặn *số ảnh đang chiếm bộ nhớ*. Xem
[OPS-4](features_issues.md#ops-inflight).

`max_in_flight` mặc định là `2 × max_concurrency`, và con số 2 đến từ số đo chứ không từ RAM:
thông lượng đạt đỉnh 8.43 req/s ở mức 32 request song song, nên nhận nhiều hơn thế chỉ thêm
thời gian chờ. Với `max_in_flight` = 32 thì request cuối hàng đợi chờ tối đa ~3.8s; để 64 thì
7.6s mà **không thêm một req/s nào**. Bắn 200 request vào máy server cho đúng
`max_in_flight` mã `200` và phần còn lại `503` — van không rò suất nào.

Request **không có key hợp lệ bị chặn trước cả hai nấc trên**, nên nó không chiếm suất xử lý và
không đẩy 32MB nào vào RAM.

### Giới hạn phải tôn trọng

Máy chủ tự bảo vệ bộ nhớ của mình, nên phía gọi **không** cần tính toán gì để tránh làm sập nó.
Nhưng gửi vượt trần vẫn lãng phí: request bị từ chối là một vòng mạng không mang lại gì.

Cách gọi đúng: giữ số request đang bay quanh `max_concurrency`, và khi gặp `503` thì **lùi rồi
thử lại** (`Retry-After` nói chờ bao lâu) thay vì gửi dồn tiếp.

### Những thứ an toàn khi gọi song song

- **Không có thứ tự**: kết quả không phụ thuộc request nào tới trước.
- **Retry an toàn**: không có tác dụng phụ nào, không ghi gì xuống đĩa ([EX-12](need_exchange.md)).
  Cùng một ảnh gửi lại cho cùng một kết quả.
- **`503` là mã duy nhất nên retry** — kèm `Retry-After`. `400`/`401`/`422` thì retry vô ích.
- **Không có timeout phía máy chủ.** Một request xếp hàng lâu sẽ chờ lâu chứ không bị cắt; phía
  gọi tự đặt timeout, và đặt rộng hơn `max_concurrency` lần thời gian xử lý một ảnh.

Cần thông lượng cao hơn trần một tiến trình thì chạy nhiều container sau một bộ cân bằng tải —
service không chia sẻ gì nên nhân bản là chuyện thuần hạ tầng. Cùng bộ key dùng được cho mọi
container; không có state nào phải đồng bộ.

---

## 10. Chưa có, và biết là chưa có {#chua-co}

- **Không có TLS.** API key đi qua HTTP thuần là gửi mật khẩu dạng chữ rõ — xem cảnh báo ở
  [§2](#xac-thuc). Cần kín thật thì đặt reverse proxy có TLS trước container.
- **Không có giới hạn tần suất theo client.** Key phân biệt được ai gọi, nhưng chưa có hạn mức
  riêng cho từng client. Chỉ có đẩy lùi khi kín tải (`503` + `SERVER_BUSY`, xem
  [§9](#song-song)), và đó là trần chung cho cả service.
- **Không có thu hồi key lúc đang chạy.** Danh sách key đọc một lần lúc khởi động; đổi key phải
  khởi động lại service. Đó là chủ ý — trạng thái bảo mật không nên đổi giữa chừng vì một lần
  sửa biến môi trường hụt tay.
- **Không có log kiểm toán.** Tên client có sẵn trong request nhưng chưa được ghi ra đâu cả.
- **Một tiến trình, không `workers`** — mỗi worker nạp một bản model vào RAM, và onnxruntime
  vốn đã dùng nhiều luồng. Cần thông lượng cao hơn thì **đo trước rồi hãy làm**.
- **Đường GPU đã chạy được** trên máy H100 ([SPD-4](features_issues.md#spd-gpu)), nhưng trên máy
  đó nó cho thông lượng *thấp hơn* bản CPU vì VRAM dùng chung với một service khác.
- **Mỗi request một ảnh.** Không có khái niệm "hồ sơ nhiều trang" — một giấy chứng nhận chụp
  hai mặt là **hai** request độc lập. Việc ghép và kiểm đủ mặt thuộc hệ gọi, xem
  [EX-15](need_exchange.md#ex-multipage).
- **Không có endpoint xử lý lô.** Chạy lô dùng CLI `qc-scanner-batch`, không qua HTTP.
- **Docker image chưa build lại sau khi thêm DocAligner + xác thực.** Bước tải mô hình trong
  `Dockerfile` chưa chạy thử lần nào. Còn lại của [OPS-3](features_issues.md#ops-docker-unverified):
  chưa kiểm gọi từ máy khác qua LAN, chưa kiểm khi ngắt mạng, chưa build trong CI.
