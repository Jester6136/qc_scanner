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

## 2. `POST /` — chấm QC một ảnh

**Request**: `multipart/form-data`, đúng một trường `file`.

| Tham số query | Giá trị | Mặc định | Ý nghĩa |
|---|---|---|---|
| `format` | `json` | *(không có)* | Trả JSON đầy đủ thay vì file PNG |
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
chuỗi trần. Ba mã hay gặp: `MISSING_FILE`, `FILE_EMPTY`, `DECODE_FAILED`.

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

Trả `200` và `{"status": "ok"}`. Dùng cho liveness probe.

> Nó **không** kiểm model đã nạp xong chưa. Vì server nạp model *trước khi* mở cổng, nên cổng
> mở được đã có nghĩa là model sẵn sàng — trừ khi chạy với `--no-warmup`.

---

## 5. `GET /` → `405`

Nhánh `GET /?url=` cũ **đã bị bỏ hẳn** ([SEC-1](features_issues.md#sec-ssrf)): nó tải URL tuỳ ý
do người dùng cung cấp, kể cả `file:///etc/passwd` và metadata nội bộ của cloud. Đừng khôi
phục. Có test chặn.

---

## 6. Danh mục mã lý do

20 mã, kèm điều kiện phát hiện và hướng xử lý:
[algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes).

Nhóm theo hành động của phía gọi:

| Nhóm | Mã | Phía gọi nên làm gì |
|---|---|---|
| Lỗi tích hợp / đầu vào | `MISSING_FILE` `FILE_EMPTY` `DECODE_FAILED` | Sửa phía gọi, đừng retry |
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
  vốn đã dùng nhiều luồng. Cần thông lượng cao hơn thì chạy nhiều container sau một bộ cân
  bằng tải, **đo trước rồi hãy làm**.
- **Mỗi request một ảnh.** Không có khái niệm "hồ sơ nhiều trang" — một giấy chứng nhận chụp
  hai mặt là **hai** request độc lập. Việc ghép và kiểm đủ mặt thuộc hệ gọi, xem
  [EX-15](need_exchange.md#ex-multipage).
- **Không có endpoint xử lý lô.** Chạy lô dùng CLI `qc-scanner-batch`, không qua HTTP.
- ⚠️ **Docker image chưa từng build thử** — xem [OPS-3](features_issues.md#ops-docker-unverified).
  Phần hợp đồng trong tài liệu này thì đã có test giữ và chạy được ngoài Docker.
