# QC Scanner

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.txt)

**Take a photo of a document and get back a flat, cropped scan.**

QC Scanner finds the sheet of paper in a photo — shot at an angle, on a cluttered desk — detects its
four corners, and applies a perspective transform so the page comes out flat and trimmed. It is a
**pre-processing step** for OCR / document-understanding pipelines: flatter page, sharper glyphs,
better extraction downstream.

<p style="display: flex;align-items: center;justify-content: center;">
  <img src="examples/doc-1.jpg" width="100" />
  <img src="examples/doc-1.out.png" width="100" />
  <img src="examples/doc-2.png" width="100" />
  <img src="examples/doc-2.out.png" width="100" />
  <img src="examples/doc-3.jpg" width="100" />
  <img src="examples/doc-3.out.png" width="100" />
  <img src="examples/doc-4.jpg" width="100" />
  <img src="examples/doc-4.out.png" width="100" />
  <img src="examples/doc-5.jpg" width="100" />
  <img src="examples/doc-5.out.png" width="100" />
  <img src="examples/doc-6.jpg" width="100" />
  <img src="examples/doc-6.out.png" width="100" />
  <img src="examples/doc-7.jpg" width="100" />
  <img src="examples/doc-7.out.png" width="100" />
  <img src="examples/doc-8.jpg" width="100" />
  <img src="examples/doc-8.out.png" width="100" />
</p>

### How it works

```
photo ──► rembg (U²-Net)  ──►  alpha mask  ──►  findContours + approxPolyDP  ──►  4 corners
                                                                                    │
                                        PNG  ◄── four-point perspective transform ◄──┘
```

One core function, three front-ends (CLI, HTTP server, Python library) — all calling the same
`scan()`. No database, no queue, no configuration. Full walkthrough with rationale:
[docs/algorithm.md](docs/algorithm.md).

Output is **always PNG** — deliberately. The result feeds OCR/VLM downstream, and lossy JPEG
artefacts around small glyphs cost accuracy.

### Installation

Not published to PyPI yet — install from source:

```bash
pip install -r requirements.txt
pip install .
```

> ⚠️ The **first run downloads the rembg model** (tens of MB, into `~/.u2net/`). Machines without
> internet access will fail there, not in the code. Pre-warm before benchmarking or shipping.

### Usage as a CLI

Scan from a remote image
```bash
curl -s http://input.png | qc-scanner > output.png
```

Scan from a local file
```bash
qc-scanner path/to/input.png path/to/output.png
```

### Usage as a library

In `app.py`

```python
import sys
from qc_scanner.doc import scan

sys.stdout.buffer.write(scan(sys.stdin.buffer.read()))
```

Then run
```bash
cat input.png | python app.py > out.png
```

### Usage as an HTTP server

```bash
qc-scanner-server -a 0.0.0.0 -p 5000
curl -F "file=@input.jpg" http://127.0.0.1:5000/ -o out.png
```

> ⚠️ The server has **no authentication**, and its `GET /?url=` endpoint fetches arbitrary URLs
> (SSRF — see [SEC-1](docs/features_issues.md#sec-ssrf)). Do **not** expose it publicly as-is.

---

## Status & direction

The core is small (~164 lines) and works, but it was written years ago and has known gaps. Read
this before relying on it:

| | |
|---|---|
| ✅ Works | Perspective correction on photos with a reasonably contrasting background |
| ⚠️ Silent failures | If no quadrilateral is found it returns the **original image** and tells you nothing |
| ⚠️ Errors swallowed | Any exception becomes `None` + one stderr line — CLI then crashes, server returns `500 "oops"` |
| 🔴 CLI bug | `rembg` runs **twice** on the CLI path — twice as slow, and results differ from the library path |
| 🔴 Not measured | No tests, no CI, no labelled ground truth. Detection accuracy is currently **unknown** |

**Where this is going: qc_scanner becomes a QC gate, not just a crop function.**

Every call should return a *verdict* — pass / warn / fail — and when it cannot crop, say **why**
(a stable reason code such as `QUAD_NOT_FOUND`, `SUBJECT_NOT_FOUND`, `BLURRY`) and **what to do
about it** (an actionable hint aimed at the right person: whoever took the photo, the operator,
or the calling system). Better still: recover automatically where possible — then report that it
had to. At scale, a wrong crop that stays silent is worse than an honest failure: it flows into
OCR and nobody notices until acceptance testing.

See [docs/overall_roadmap.md](docs/overall_roadmap.md) for the plan, and
[docs/algorithm.md §8](docs/algorithm.md) for a 2026 survey of what modern approaches
(direct 4-corner regression, newer segmentation backbones, neural dewarping) would buy us.

## Documentation · Tài liệu

Tài liệu dự án viết bằng tiếng Việt, đặt trong [docs/](docs/):

| File | Nội dung |
|---|---|
| [overall_roadmap.md](docs/overall_roadmap.md) | Tổng quan dự án, nguyên tắc thiết kế, roadmap chi tiết theo giai đoạn |
| [algorithm.md](docs/algorithm.md) | Thuật toán từng bước, hợp đồng đầu ra QC, danh mục mã lý do, **khảo sát công nghệ 2026** |
| [features_issues.md](docs/features_issues.md) | Sổ tính năng + issue (BUG-\*/SEC-\*/QC-\*/QUAL-\*/S-\*/N-\*) kèm bằng chứng `path:line` |
| [test_eval.md](docs/test_eval.md) | Smoke test, bộ regression, cách eval chất lượng & độ chính xác phán quyết |
| [need_exchange.md](docs/need_exchange.md) | Câu hỏi cần làm rõ với khách hàng trước khi chốt thiết kế/nghiệm thu |

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Kiểm nhanh sau khi sửa (chi tiết: [docs/test_eval.md](docs/test_eval.md)):

```bash
# lib / CLI / pipe / server phải cho CÙNG kết quả trên cùng ảnh
qc-scanner examples/doc-1.jpg /tmp/out.png && open /tmp/out.png
```

Trước khi gửi thay đổi: chạy §1 và §2 của `test_eval.md`; thay đổi thuật toán phải kèm **số đo
trước/sau**; thêm reason code phải kèm `hint` + `audience`.

## License

MIT — xem [LICENSE.txt](LICENSE.txt). Lõi bắt nguồn từ
[danielgatis/docscan](https://github.com/danielgatis/docscan) (MIT); bước tách nền dùng
[rembg](https://github.com/danielgatis/rembg).
