# Test & Eval — qc_scanner

> Ghi chú **cách smoke test + eval**. Nguyên tắc house-style: **PURE** (thuần, không hạ tầng)
> chạy được mọi nơi; qc_scanner may mắn là **PURE toàn bộ** — không DB, không hàng đợi, không
> service ngoài. Rào cản duy nhất là cài được dependency và tải được model rembg lần đầu.
>
> **401 bài** trong `tests/`, chạy bằng `pytest`, kèm CI. §5 (eval trên tập vàng) là phần
> **chưa chạy được** — công cụ đã sẵn (`python -m qc_scanner.eval`), chỉ thiếu ảnh có nhãn của
> khách ([EX-2](need_exchange.md)).

---

## 0. Chuẩn bị môi trường

```bash
conda create -n qc_scanner python=3.12 && conda activate qc_scanner
pip install -r requirements-dev.txt
pip install -e .                 # để có lệnh `qc-scanner` / `qc-scanner-batch` / `-server`
```

Chạy toàn bộ bộ test (~25s sau khi model đã cache):

```bash
pytest          # 401 bài
ruff check src tests
```

⚠️ **Lần chạy đầu tiên tải model rembg** (U²-Net, vài chục MB, về `~/.u2net/`). Máy không có
mạng sẽ **fail ở đây**, không phải ở code. Pre-warm trước khi đo thời gian:

```bash
python3 -c "import rembg; rembg.remove(open('examples/doc-1.jpg','rb').read())" >/dev/null
```

| | Máy cá nhân | CI | Docker (N-04) |
|---|---|---|---|
| Test PURE (không cần model) | ✅ | ✅ | ✅ |
| Test E2E (cần rembg + model) | ✅ nếu có mạng lần đầu | ✅ (cache `~/.u2net`) | ✅ (model nướng sẵn trong image) |
| Đo thời gian | ⚠️ chỉ so tương đối (CPU khác nhau) | ❌ máy CI nhiễu | ✅ |

Kiểm nhanh môi trường đã sẵn sàng:

```bash
python3 -c "import cv2, rembg, imutils, numpy; print('deps ok', cv2.__version__)"
```

---

## 1. Smoke test tay

Ba mặt tiền phải cho **cùng một kết quả** trên cùng ảnh. ✅ Nay **đúng** — BUG-1 đã sửa, và
`tests/test_surfaces.py` giữ chốt chặn này tự động. Cách kiểm tay:

```bash
# 1. Library
python3 -c "
from qc_scanner.doc import scan
open('/tmp/out-lib.png','wb').write(scan(open('examples/doc-1.jpg','rb').read()))
"

# 2. CLI — file vào, file ra
qc-scanner examples/doc-1.jpg /tmp/out-cli.png

# 3. CLI — pipe
cat examples/doc-1.jpg | qc-scanner > /tmp/out-pipe.png

# 4. Server
qc-scanner-server -p 5000 &
curl -s -F "file=@examples/doc-1.jpg" http://127.0.0.1:5000/ -o /tmp/out-srv.png

# So sánh: BỐN file này phải giống hệt nhau
md5 /tmp/out-lib.png /tmp/out-cli.png /tmp/out-pipe.png /tmp/out-srv.png
```

✅ **Kết quả hiện tại**: cả bốn trùng md5. (Trước khi sửa: `out-cli`/`out-pipe` khác
`out-lib`/`out-srv` vì rembg chạy hai lần.)

### Kiểm mắt thường trên toàn bộ mẫu

```bash
for f in examples/doc-*.jpg examples/doc-*.png; do
  case "$f" in *.out.png) continue;; esac
  qc-scanner "$f" "/tmp/$(basename "${f%.*}").mine.png"
done
open /tmp/*.mine.png       # macOS — so với examples/doc-N.out.png
```

Mỗi ảnh, tự hỏi: có nắn phẳng không · có mất mép/góc nào không · có cắt nhầm vào vùng nền
không · chữ có bị kéo giãn bất thường không.

### Kiểm các ca hỏng (quan trọng nhất cho mục tiêu QC)

```bash
echo -n "" > /tmp/empty.png                 # file rỗng
head -c 100 /dev/urandom > /tmp/junk.png    # không phải ảnh
qc-scanner /tmp/empty.png /tmp/o1.png; echo "exit=$?"
qc-scanner /tmp/junk.png  /tmp/o2.png; echo "exit=$?"
curl -s -F "file=@/tmp/junk.png" http://127.0.0.1:5000/ -i | head -5
```

✅ **Kết quả hiện tại**: CLI exit code **3** + JSON `{"code":"DECODE_FAILED", "hint":"File
không phải ảnh hợp lệ…", "audience":"system"}` ra stderr; server **400** + cùng nội dung JSON.

Hành vi cũ **tệ hơn tài liệu mô tả**: không phải `500 "oops"` mà là **200 OK + PNG rỗng 0
byte** — `BytesIO(None)` hợp lệ nên `send_file` không ném gì. Caller nhận HTTP thành công với
file rỗng. `tests/test_failures.py::test_server_junk_returns_400_not_200` chặn đường lùi.

Exit code CLI: **0** pass · **1** warn · **2** fail · **3** đầu vào không đánh giá được.

---

## 2. Bộ regression trên `examples/`

✅ **Đã dựng**. 8 cặp `doc-N.{jpg,png}` → `doc-N.out.png` trong [examples/](../examples/) là
đầu ra đã được người kiểm mắt chấp nhận, nay dùng làm chốt chặn hồi quy.

```
tests/
  conftest.py            # fixture: cặp (input, expected); cache scan theo session
  synthetic.py           # dựng ảnh ca hỏng bằng OpenCV
  test_regression.py     # §2 — đầu ra không được trôi so với ảnh mẫu
  test_surfaces.py       # §1 — lib/CLI/pipe/server ra cùng kết quả
  test_failures.py       # §3 — ca hỏng ra đúng mã lý do
  test_qc_contract.py    # §3a — bất biến của ScanResult
  test_reason_codes.py   # §3b/§3c — mỗi mã có ca kích hoạt; KHÔNG false pass
  test_detectors.py      # S-2 — lõi QC không phụ thuộc detector nào
  test_pdf.py            # N-08 — PDF vào/ra: đọc không resample, ghép không mất dữ liệu
  test_concurrency.py    # OPS-4 — hai van: MAX_CONCURRENCY (CPU) và MAX_IN_FLIGHT (RAM)
  test_api_contract.py   # docs/api.md hứa gì thì giữ đúng thế
  test_packaging.py      # requirements CPU/GPU khớp nhau, guard đặt đúng chỗ
```

**KHÔNG so bằng md5**: nén PNG khác version, `warpPerspective` khác build OpenCV → sai lệch
vài pixel là bình thường và vô hại.

Đo **hai thứ tách bạch** vì chúng hỏng theo cách khác nhau: **tỉ lệ khung** bắt lỗi *chọn sai
tứ giác* (crop lệch → khung méo); **tương quan nội dung** bắt lỗi *nội dung* (mất mép, xoay
nhầm, nắn sai).

⚠️ **Đề xuất ban đầu dùng SSIM > 0.95 đã bị số đo bác bỏ.** SSIM tụt xuống tận **0.36** trên
các ảnh **đúng** (doc-5, doc-8): đó là ảnh chụp có **nhiễu hạt**, và một lệch dưới một pixel
trong phép nắn làm xô toàn bộ vân nhiễu → SSIM sập, dù mắt thường không phân biệt nổi hai ảnh.
Hạ mẫu rồi vẫn vậy (0.55 ở bề ngang 128px).

Thay bằng **NCC** (tương quan chéo chuẩn hoá) trên ảnh xám đã hạ mẫu về 256px + làm mờ nhẹ:

| doc | Δ tỉ lệ khung | NCC |
|---|---|---|
| 1 | 0.0135 | 0.879 |
| 2 | 0.0026 | 0.980 |
| 3 | 0.0055 | 0.994 |
| 4 | 0.0000 | 0.946 |
| 5 | 0.0075 | 0.810 |
| 6 | 0.0052 | 0.965 |
| 7 | 0.0000 | 0.926 |
| 8 | 0.0281 | 0.849 |

Ngưỡng chốt: **Δ tỉ lệ khung < 0.04**, **NCC > 0.70**. Hai tài liệu **khác nhau** cho NCC ≈
0.0, nên metric vẫn bắt được hồi quy thật mà không báo động giả vì nhiễu.

Kèm `test_metric_rejects_wrong_document`: **phép đo cũng phải được kiểm**. Không có bài đó thì
một metric quá dễ dãi sẽ cho mọi thứ đi qua và cả bộ regression thành vô dụng.

> Khi nâng `rembg`/`opencv-python` ([DEP-1](features_issues.md#dep-pin)), bộ test này là thứ
> duy nhất phát hiện chất lượng **trôi thầm lặng**. Đừng nâng dependency mà không chạy nó.

---

## 3. Test cho luồng QC

QC chỉ đáng tin nếu **chính nó** được test. Ba nhóm:

### 3a. Bất biến hợp đồng
```python
def test_pass_iff_no_reasons(result):
    assert (result.verdict == "pass") == (result.reasons == [])

def test_every_reason_is_actionable(result):
    for r in result.reasons:
        assert r.hint and r.audience in {"capturer", "operator", "system"}
```
Bài test thứ hai **thực thi nguyên tắc §3.4 của roadmap** ở mức code: không ai merge được
reason code thiếu hướng xử lý.

### 3b. Mỗi mã lý do có ít nhất một ca kích hoạt được
Dựng ảnh tổng hợp bằng OpenCV thay vì đi xin ảnh thật — nhanh, tất định, chạy được ở CI.
Đã cài trong `tests/synthetic.py`:

| Mã | Cách dựng ảnh test |
|---|---|
| `DECODE_FAILED` | 100 byte ngẫu nhiên |
| `FILE_EMPTY` | `b""` |
| `TOO_SMALL` | tờ giấy trắng 100×140 dán giữa nền đen 2000×2000 |
| `CLIPPED_EDGE` | tờ giấy tràn ra ngoài mép ảnh |
| `EXTREME_SKEW` | warp ảnh mẫu bằng ma trận phối cảnh nghiêng mạnh |
| `MULTIPLE_DOCUMENTS` | ghép 2 tờ giấy vào một nền |
| `SUBJECT_NOT_FOUND` | giấy trắng trên nền trắng |
| `BLURRY` | `GaussianBlur` ảnh mẫu với ksize lớn |

Hai lưu ý rút ra khi dựng bộ ảnh này:

- **`TOO_SMALL` khó dựng hơn tưởng.** Tờ giấy quá nhỏ thì rembg không tách nổi và kết quả ra
  `SUBJECT_NOT_FOUND` — một ca khác hẳn. Diện tích phải nằm giữa `candidate_area_ratio` (0.05)
  và `min_quad_area_ratio` (0.20).
- **`SUBJECT_NOT_FOUND` bằng giấy trắng trên nền trắng lại KHÔNG kích hoạt được**: rembg đời
  này tách được ca đó (alpha_coverage 0.71). Tin tốt cho chất lượng, nhưng nghĩa là ca test
  phải dựng bằng đường khác (tắt fallback + siết `candidate_area_ratio`).

### 3c. Không có false pass trên các ca trên
Kiểm quan trọng nhất: với mọi ảnh hỏng, `verdict != "pass"`. False pass là chế độ hỏng đắt
nhất — ảnh xấu trôi xuống OCR và chỉ lộ ra lúc nghiệm thu.

✅ `test_reason_codes.py::test_no_false_pass_on_bad_input` — 9 ca hỏng, không ca nào lọt.
Bài này cố ý **không đòi đúng mã**: một ảnh hỏng bị bắt vì lý do khác vẫn tốt hơn nhiều so
với việc nó được cho qua.

Kèm `test_clean_document_passes` làm **đối chứng**: không có nó thì một hệ thống fail-mọi-thứ
cũng xanh toàn bộ §3c.

---

## 4. Benchmark thời gian

Chỉ có **một** con số đáng quan tâm: rembg chiếm bao nhiêu phần tổng thời gian (giả thuyết:
~95%, [algorithm.md §5](algorithm.md#chi-phi) — **chưa đo lần nào**).

```bash
python3 - <<'PY'
import time, rembg, cv2, numpy as np
data = open("examples/doc-1.jpg","rb").read()
rembg.remove(data)                                   # pre-warm, KHÔNG tính vào phép đo
t0=time.perf_counter(); out=rembg.remove(data);       t1=time.perf_counter()
img=cv2.imdecode(np.frombuffer(out,np.uint8), cv2.IMREAD_UNCHANGED)
t2=time.perf_counter()
print(f"rembg   {t1-t0:.3f}s\ndecode  {t2-t1:.3f}s")
PY

# tổng đầu-cuối, 8 ảnh
time bash -c 'for f in examples/doc-*.jpg; do qc-scanner "$f" /dev/null; done'
```

Kết luận rút ra:
- rembg > 90% tổng → **đừng tối ưu OpenCV**. Đòn bẩy: tái dùng session
  ([N-06](features_issues.md#f-features--đề-xuất-backlog)) hoặc GPU provider (N-10).
- Nếu không → đo lại từng chặng trước khi kết luận; có thể `imencode` PNG mới là thủ phạm
  (nhưng **không đổi sang JPEG** — xem nguyên tắc §3.3 roadmap).

Luôn **pre-warm** trước khi bấm giờ, nếu không sẽ đo nhầm thời gian tải model.

✅ **Đã đo** (Apple Silicon, 9 ảnh thật): ~3.0s/ảnh khi tạo session mới mỗi lần → **0.395s/ảnh**
sau khi tái dùng session (N-06). Giả thuyết "rembg > 90%" được xác nhận. Cách đo nhanh nhất
hiện nay là dùng thẳng bộ eval, nó đã báo `seconds_median`:

```bash
python -m qc_scanner.eval tmp --csv /tmp/run.csv
```

---

## 5. Eval chất lượng trên tập vàng (khi có ảnh thật của khách)

`examples/` là ảnh OSS, **không đại diện** cho ảnh thật của khách. Nghiệm thu cần tập vàng riêng —
xem [need_exchange.md EX-1/EX-2](need_exchange.md).

⚠️ **Đây là phần duy nhất của tài liệu này chưa chạy được**, và không phải vì thiếu công cụ.
`python -m qc_scanner.eval` đã tính đủ ba con số + ma trận nhầm lẫn khi có `--labels`. Thứ
thiếu là **ảnh có nhãn**. 9 ảnh thật trong `tmp/` mới là mẫu đầu tiên, chưa gán nhãn, nên hiện
chỉ dùng để **so hai cấu hình với nhau** (`--baseline`), chưa chấm được đúng/sai.

```bash
# so hai cấu hình khi chưa có nhãn
python -m qc_scanner.eval tmp --csv /tmp/a.csv
python -m qc_scanner.eval tmp --model isnet-general-use --csv /tmp/b.csv --baseline /tmp/a.csv

# ba con số nghiệm thu — khi đã có nhãn
python -m qc_scanner.eval anh-khach --labels golden.jsonl --csv /tmp/eval.csv
```

### Cách gán nhãn
Mỗi ảnh: 4 điểm góc thật của tờ giấy (thứ tự TL-TR-BR-BL) + verdict kỳ vọng
(`pass`/`warn`/`fail`) + reason kỳ vọng nếu không pass.

```json
{"file": "real-042.jpg",
 "corners": [[120,88],[1810,140],[1795,2480],[95,2410]],
 "expect_verdict": "pass", "expect_reasons": []}
```

Cỡ tối thiểu dùng được: **~100 ảnh**, trong đó **≥30% là ca xấu** (mờ, nghiêng, nền lẫn, thiếu
góc, nhiều tờ). Tập toàn ảnh đẹp không đo được gì về QC — nó chỉ đo được crop.

### Ba con số phải báo cáo

| Chỉ số | Công thức | Ngưỡng khởi điểm |
|---|---|---|
| **Crop rate** | % ảnh `pass` có IoU(tứ giác dự đoán, nhãn) ≥ 0.90 | ≥ 95% |
| **False pass** | % ảnh nhãn `fail`/`warn` nhưng hệ thống báo `pass` | **≤ 1%** — chỉ số quan trọng nhất |
| **False fail** | % ảnh nhãn `pass` nhưng hệ thống báo `fail` | ≤ 10% (đắt hơn về công, rẻ hơn về hậu quả) |

Kèm **ma trận nhầm lẫn reason code**: fail đúng nhưng **sai nguyên nhân** cũng là hỏng —
người dùng làm theo hint sai sẽ chụp lại vẫn sai. Đây là phần dễ bị bỏ sót nhất khi đánh giá.

### Quy trình eval một thay đổi thuật toán
1. Ghi **baseline** ba con số trên + dump metric từng ảnh ra CSV (N-01).
2. Sửa (vd QUAL-1 bộ lọc tứ giác, QUAL-2 ngưỡng scale).
3. Chạy lại **cùng tập, cùng lệnh**, so ba con số.
4. Với thay đổi **ngưỡng QC**: bắt buộc nhìn cả false-pass **và** false-fail — siết ngưỡng luôn
   đánh đổi giữa hai bên, đừng khoe mỗi một chiều.
5. Ca **hồi quy** (trước đúng, sau sai) phải soi từng ảnh — đây là nơi bug thật sự lộ ra.

---

## 6. Checklist trước khi release / nghiệm thu

- [x] `pytest` xanh (401 bài) — CI chạy trên môi trường sạch, có cache model.
- [x] Bốn mặt tiền (lib / CLI file / CLI pipe / server) cho **cùng kết quả** — §1.
- [x] Ca hỏng (file rỗng, rác, ảnh không có tài liệu) trả **mã lý do + hint** — §1.
- [x] Regression `examples/` không trôi — §2.
- [x] Không false pass trên bộ ảnh hỏng tổng hợp — §3c.
- [ ] **Với thay đổi thuật toán: số đo trước/sau trên tập vàng — §5. CHƯA LÀM ĐƯỢC (thiếu EX-2).**
- [x] Với nâng dependency: chạy §2 và ghi version cũ/mới trong commit.
- [x] `pip install dist/*.whl` trên môi trường sạch chạy được cả ba lệnh — CI cài lại wheel
      vừa build vào venv riêng rồi gọi thử `qc-scanner` / `-batch` / `-server`.
