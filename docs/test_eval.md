# Test & Eval — qc_scanner

> Ghi chú **cách smoke test + eval**. Nguyên tắc house-style: **PURE** (thuần, không hạ tầng)
> chạy được mọi nơi; qc_scanner may mắn là **PURE toàn bộ** — không DB, không hàng đợi, không
> service ngoài. Rào cản duy nhất là cài được dependency và tải được model rembg lần đầu.
>
> ⚠️ Trạng thái hiện tại: **chưa có test nào** trong repo ([PKG-4](features_issues.md#pkg-notest)).
> Tài liệu này vừa mô tả cách kiểm tay **ngay bây giờ** (§1), vừa là **đặc tả bộ test cần dựng**
> (§2–§5).

---

## 0. Chuẩn bị môi trường

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                 # để có lệnh `qc-scanner` / `qc-scanner-server`
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

## 1. Smoke test tay (làm được ngay hôm nay)

Ba mặt tiền phải cho **cùng một kết quả** trên cùng ảnh. Hiện tại **KHÔNG** — vì
[BUG-1](features_issues.md#bug-double-rembg) làm CLI chạy rembg hai lần. Chính bài kiểm này
là cách phát hiện lại lỗi đó:

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

🔴 **Kỳ vọng hiện tại**: `out-cli`/`out-pipe` **khác** `out-lib`/`out-srv` (double rembg).
Sau khi sửa BUG-1, cả bốn phải trùng md5. Đây là **tiêu chí đóng BUG-1**.

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

🔴 **Kỳ vọng hiện tại**: `TypeError` khó hiểu ở CLI, `500 {"error":"oops, something went
wrong!"}` ở server — [BUG-2](features_issues.md#bug-swallow).
🟢 **Sau QC-2/QC-4**: CLI exit code **2** + JSON `{"code":"DECODE_FAILED", "hint":"File không
phải ảnh hợp lệ…"}` ra stderr; server **400** + cùng nội dung JSON.

---

## 2. Bộ regression trên `examples/` (cần dựng — ưu tiên 1)

8 cặp `doc-N.{jpg,png}` → `doc-N.out.png` trong [examples/](../examples/) là **tài sản chưa
dùng**: chúng là đầu ra đã được người kiểm mắt chấp nhận. Dùng làm chốt chặn hồi quy.

```
tests/
  conftest.py            # fixture: đọc cặp (input, expected) từ examples/
  test_regression.py     # §2 — đầu ra không được trôi so với ảnh mẫu
  test_surfaces.py       # §1 — lib/CLI/pipe/server ra cùng kết quả
  test_failures.py       # §3 — ca hỏng ra đúng mã lý do
  test_qc_contract.py    # §3 — bất biến của ScanResult
```

**KHÔNG so bằng md5**: nén PNG khác version, `warpPerspective` khác build OpenCV → sai lệch
vài pixel là bình thường và vô hại. So bằng **ngưỡng tương tự**:

```python
# tests/test_regression.py — ý tưởng
def test_matches_reference(pair):
    got = cv2.imdecode(np.frombuffer(scan(pair.input_bytes), np.uint8), cv2.IMREAD_COLOR)
    ref = cv2.imread(str(pair.expected_path))
    assert abs(got.shape[0]/got.shape[1] - ref.shape[0]/ref.shape[1]) < 0.02   # tỉ lệ khung
    got_r = cv2.resize(got, (ref.shape[1], ref.shape[0]))
    assert ssim(gray(got_r), gray(ref)) > 0.95                                 # nội dung
```

Đo **hai thứ tách bạch** vì chúng hỏng theo cách khác nhau: **tỉ lệ khung** bắt lỗi *chọn sai
tứ giác* (crop lệch → khung méo); **SSIM** bắt lỗi *nội dung* (mất mép, xoay nhầm, nắn sai).
Ngưỡng 0.95/0.02 là điểm khởi đầu — chốt lại sau lần chạy đầu trên máy sạch.

> Khi nâng `rembg`/`opencv-python` ([DEP-1](features_issues.md#dep-pin)), bộ test này là thứ
> duy nhất phát hiện chất lượng **trôi thầm lặng**. Đừng nâng dependency mà không chạy nó.

---

## 3. Test cho luồng QC (cần dựng — song song với QC-1/QC-2)

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
Dựng ảnh tổng hợp bằng OpenCV thay vì đi xin ảnh thật — nhanh, tất định, chạy được ở CI:

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

### 3c. Không có false pass trên các ca trên
Kiểm quan trọng nhất: với mọi ảnh hỏng, `verdict != "pass"`. False pass là chế độ hỏng đắt
nhất — ảnh xấu trôi xuống OCR và chỉ lộ ra lúc nghiệm thu.

---

## 4. Benchmark thời gian

Chỉ có **một** con số đáng quan tâm: rembg chiếm bao nhiêu phần tổng thời gian (giả thuyết:
~95%, [algorithm.md §5](algorithm.md#5-chi-phí-thời-gian) — **chưa đo lần nào**).

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

---

## 5. Eval chất lượng trên tập vàng (khi có ảnh thật của khách)

`examples/` là ảnh OSS, **không đại diện** cho ảnh thật của khách. Nghiệm thu cần tập vàng riêng —
xem [need_exchange.md EX-1/EX-2](need_exchange.md).

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

- [ ] `pytest` xanh trên **venv sạch** (không dùng model cache của máy dev).
- [ ] Bốn mặt tiền (lib / CLI file / CLI pipe / server) cho **cùng kết quả** — §1.
- [ ] Ca hỏng (file rỗng, rác, ảnh không có tài liệu) trả **mã lý do + hint**, không phải
      "oops" hay `None` — §1.
- [ ] Regression `examples/` không trôi — §2.
- [ ] Với thay đổi thuật toán: có số đo trước/sau trên tập vàng — §5.
- [ ] Với nâng dependency: chạy §2 và ghi rõ version cũ/mới trong commit.
- [ ] `pip install dist/*.whl` trên môi trường sạch chạy được cả `qc-scanner` lẫn `qc-scanner-server`.
