"""N-08 — đầu vào PDF.

PDF vào đây gần như luôn là **ảnh scan đóng gói lại**, nên phần lớn rủi ro không nằm
ở "đọc được file hay không" mà ở hai chỗ lặng lẽ hơn:

* khâu đọc file tự tay làm hỏng ảnh (resample) rồi lõi QC chấm trượt vì thế;
* PDF nhiều trang bị xử lý như một trang, các trang còn lại biến mất không báo gì.

Bộ test này khoá cả hai.
"""

import io
import json
import subprocess
import sys

import pypdfium2 as pdfium
import pytest
from PIL import Image

from conftest import EXAMPLES
from qc_scanner import geometry as geo
from qc_scanner.config import Config
from qc_scanner.doc import scan_document, scan_qc
from qc_scanner.pdf import is_pdf, page_images
from qc_scanner.qc import ScanError


def build_pdf(paths, dpi=300, margin_pt=0.0) -> bytes:
    """PDF với mỗi ảnh đặt lên một trang, ở đúng `dpi` khai báo.

    `margin_pt=0` cho hình dạng của một bản scan thật: ảnh phủ kín trang. Chừa lề thì
    độ phủ tụt xuống dưới `pdf_page_image_coverage` và trang rẽ sang đường render —
    đúng hình dạng của PDF sinh từ máy tính có ảnh minh hoạ.
    """
    doc = pdfium.PdfDocument.new()
    for path in paths:
        image = Image.open(path).convert("RGB")
        width, height = image.width / dpi * 72, image.height / dpi * 72
        page = doc.new_page(width + 2 * margin_pt, height + 2 * margin_pt)
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=95)
        buf.seek(0)
        obj = pdfium.PdfImage.new(doc)
        obj.load_jpeg(buf)
        obj.set_matrix(
            pdfium.PdfMatrix().scale(width, height).translate(margin_pt, margin_pt)
        )
        page.insert_obj(obj)
        page.gen_content()
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


@pytest.fixture(scope="session")
def one_page():
    return build_pdf([EXAMPLES / "doc-1.out.png"])


@pytest.fixture(scope="session")
def three_pages():
    return build_pdf([EXAMPLES / f"doc-{i}.out.png" for i in (1, 2, 3)])


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from qc_scanner.cmd.server import app

    return TestClient(app)


# --------------------------------------------------------------------------- #
# Nhận dạng


def test_pdf_is_told_apart_from_images(one_page):
    assert is_pdf(one_page)
    for name in ("doc-1.jpg", "doc-1.out.png"):
        assert not is_pdf((EXAMPLES / name).read_bytes())


def test_leading_junk_before_the_header_still_counts_as_pdf(one_page):
    """Spec cho phép PDF có rác đứng trước `%PDF-`, và pdfium mở được. Đòi đúng
    byte 0 thì những file đó rơi xuống nhánh ảnh và ăn `DECODE_FAILED` — mã sai."""
    assert is_pdf(b"rac" * 40 + one_page)


# --------------------------------------------------------------------------- #
# Khâu đọc file không được tự tay làm hỏng ảnh


def test_full_page_scan_is_read_without_a_single_resample(one_page):
    """Đường `embedded`: đúng điểm ảnh máy scan ghi, không qua render lần nào."""
    pages = list(page_images(one_page, Config()))
    assert [p.source for p in pages] == ["embedded"]

    original = Image.open(EXAMPLES / "doc-1.out.png")
    assert pages[0].image.shape[:2] == (original.height, original.width)


def test_rendering_at_the_wrong_dpi_would_have_failed_every_page_as_blurry(one_page):
    """Vì sao `pdf.py` không chỉ đơn giản render ở một DPI chọn sẵn.

    Đo được: cùng một trang, render gấp đôi DPI thật thì `blur_score` rơi từ ~44
    xuống ~3.5 — dưới `min_blur_score` (25) tới 7 lần. Đó là một lớp false-fail
    sinh ra hoàn toàn từ khâu đọc file. Test này đóng đinh con số đó, để ai định
    đổi sang đường render đọc được cái giá trước khi đổi.
    """
    page = pdfium.PdfDocument(one_page)[0]
    native = page_images(one_page, Config()).__next__().image

    doubled = page.render(scale=2 * 300 / 72).to_numpy()

    assert geo.blur_score(native) > Config().min_blur_score
    assert geo.blur_score(doubled) < Config().min_blur_score / 5


def test_a_page_that_is_not_a_full_bleed_scan_falls_back_to_rendering():
    """Ảnh chỉ là một phần của trang (PDF có bố cục) thì lấy riêng bitmap ra là **mất
    nội dung** — phải render cả trang, ở `pdf_render_dpi`."""
    data = build_pdf([EXAMPLES / "doc-1.out.png"], margin_pt=200)
    pages = list(page_images(data, Config(pdf_render_dpi=150)))
    assert pages[0].source == "render@150"


def test_pages_survive_the_document_being_closed(three_pages):
    """`to_numpy()` trả *view* vào bộ nhớ pdfium; không copy thì mảng trỏ vào vùng đã
    giải phóng sau khi đóng tài liệu — hỏng ngẫu nhiên, không exception nào."""
    pages = list(page_images(three_pages, Config()))  # generator đã chạy hết, doc đã đóng
    for page in pages:
        assert page.image.mean() > 0


# --------------------------------------------------------------------------- #
# Trang PDF là tờ giấy, không phải ảnh chụp tờ giấy


def test_full_bleed_page_is_not_failed_for_having_nothing_to_crop(one_page):
    """Không có `pdf_pre_cropped` thì **mọi** trang PDF scan đều `NO_CROP_DETECTED`:
    tứ giác trùm gần kín khung và chạm cả 4 mép là mô tả đúng theo nghĩa đen của
    một trang scan. Xem `Config.pdf_pre_cropped` để biết số đo."""
    default = scan_document(one_page)
    assert "NO_CROP_DETECTED" not in default.pages[0].codes

    off = scan_document(one_page, Config(pdf_pre_cropped=False))
    assert "NO_CROP_DETECTED" in off.pages[0].codes


def test_pre_cropped_is_recorded_in_metrics(one_page):
    assert scan_document(one_page).pages[0].metrics.pre_cropped is True


# --------------------------------------------------------------------------- #
# Nhiều trang: không trang nào được biến mất trong im lặng


def test_every_page_is_scored_and_numbered(three_pages):
    document = scan_document(three_pages)
    assert document.source == "pdf"
    assert document.page_count == 3
    assert [p.metrics.page for p in document.pages] == [1, 2, 3]


def test_document_verdict_is_the_worst_page_not_the_first(three_pages):
    document = scan_document(three_pages)
    verdicts = [p.verdict for p in document.pages]
    assert document.verdict == "fail"
    assert verdicts[0] == "pass"  # trang đầu tốt — gộp bằng trang đầu là gộp sai


def test_single_result_api_refuses_a_multipage_pdf_instead_of_dropping_pages(
    three_pages,
):
    """`scan_qc()` trả đúng một `ScanResult`. Lặng lẽ chấm trang 1 rồi bỏ 2 trang kia
    là kiểu hỏng tệ nhất: phía gọi tưởng đã soi hết hồ sơ."""
    with pytest.raises(ScanError) as exc:
        scan_qc(three_pages)
    assert exc.value.code == "PDF_MULTIPAGE"


def test_single_page_pdf_works_through_the_old_single_result_api(one_page):
    assert scan_qc(one_page).verdict in {"pass", "warn", "fail"}


def test_page_cap_refuses_the_file_instead_of_truncating_it(three_pages):
    with pytest.raises(ScanError) as exc:
        scan_document(three_pages, Config(pdf_max_pages=2))
    assert exc.value.code == "PDF_TOO_MANY_PAGES"
    assert "3 trang" in exc.value.to_dict()["detail"]


# --------------------------------------------------------------------------- #
# File hỏng


def test_corrupt_pdf_gets_a_pdf_specific_code_not_decode_failed():
    """`DECODE_FAILED` khuyên "kiểm tra định dạng: JPG/PNG" — vô nghĩa với một PDF
    hỏng, và bỏ sót cách hỏng hay gặp nhất: file đặt mật khẩu."""
    with pytest.raises(ScanError) as exc:
        scan_document(b"%PDF-1.7\nkhong phai pdf that" * 8)
    assert exc.value.code == "PDF_DECODE_FAILED"
    assert "mật khẩu" in exc.value.to_dict()["hint"]


# --------------------------------------------------------------------------- #
# HTTP


def test_single_page_pdf_keeps_the_existing_image_contract(client, one_page):
    """Hợp đồng cũ không được đổi: một trang vào, một PNG ra, kèm hai header."""
    resp = client.post("/", files={"file": ("a.pdf", one_page, "application/pdf")})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["X-QC-Scanner-Verdict"] in {"pass", "warn"}


def test_multipage_pdf_always_answers_with_the_document_shape(client, three_pages):
    """Nhiều trang không có hình dạng "một file PNG" nào để trả, nên JSON là mặc
    định — không cần `?format=json`."""
    resp = client.post("/", files={"file": ("a.pdf", three_pages, "application/pdf")})
    body = resp.json()
    assert resp.status_code == 422  # trang tệ nhất là fail
    assert body["source"] == "pdf"
    assert body["page_count"] == 3
    assert [p["page"] for p in body["pages"]] == [1, 2, 3]
    assert all("verdict" in p and "metrics" in p for p in body["pages"])


def test_multipage_response_carries_every_page_image(client, three_pages):
    body = client.post(
        "/", files={"file": ("a.pdf", three_pages, "application/pdf")}
    ).json()
    assert all(p["image"] for p in body["pages"])


def test_corrupt_pdf_over_http_is_400(client):
    resp = client.post("/", files={"file": ("a.pdf", b"%PDF-1.7 rac" * 20)})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PDF_DECODE_FAILED"


# --------------------------------------------------------------------------- #
# CLI


def _cli(args, stdin=b""):
    return subprocess.run(
        [sys.executable, "-m", "qc_scanner.cmd.cli", *args],
        input=stdin,
        capture_output=True,
    )


def test_cli_writes_one_file_per_page(tmp_path, three_pages):
    src = tmp_path / "in.pdf"
    src.write_bytes(three_pages)
    out = tmp_path / "out.png"
    proc = _cli([str(src), str(out), "--quiet"])
    assert proc.returncode == 2  # trang tệ nhất là fail
    assert out.exists()
    assert (tmp_path / "out.p2.png").exists()
    assert (tmp_path / "out.p3.png").exists()


def test_cli_page_option_selects_one_page(tmp_path, three_pages):
    src = tmp_path / "in.pdf"
    src.write_bytes(three_pages)
    out = tmp_path / "out.png"
    proc = _cli([str(src), str(out), "--page", "1"])
    assert proc.returncode == 0
    assert not (tmp_path / "out.p2.png").exists()
    assert json.loads(proc.stderr.decode())["verdict"] == "pass"


def test_cli_refuses_to_stream_a_multipage_pdf_to_stdout(tmp_path, three_pages):
    """Ghi 3 trang chồng lên stdout thì người dùng nhận một ảnh và tưởng đã xong."""
    src = tmp_path / "in.pdf"
    src.write_bytes(three_pages)
    proc = _cli([str(src), "-", "--quiet"])
    assert proc.returncode != 0
    assert b"--page" in proc.stderr
    assert not proc.stdout  # và không rò byte ảnh nào ra trước khi báo lỗi


def test_cli_report_keeps_the_old_shape_for_a_single_page(tmp_path, one_page):
    src = tmp_path / "in.pdf"
    src.write_bytes(one_page)
    proc = _cli([str(src), str(tmp_path / "o.png")])
    report = json.loads(proc.stderr.decode())
    assert set(report) >= {"verdict", "reasons", "metrics"}
    assert "pages" not in report


# --------------------------------------------------------------------------- #
# Batch


def test_batch_reports_one_row_per_page(tmp_path, three_pages):
    from qc_scanner.cmd.batch import run

    src = tmp_path / "in"
    src.mkdir()
    (src / "hoso.pdf").write_bytes(three_pages)
    out = tmp_path / "out"

    rows = run(str(src), str(out), Config(), quiet=True)

    assert len(rows) == 3
    assert [r["page"] for r in rows] == [1, 2, 3]
    assert {r["file"] for r in rows} == {str(src / "hoso.pdf")}
    # Nhiều trang thì MỌI trang đều mang số — không trang nào trông như "bản chính".
    assert sorted(p.name for p in out.iterdir()) == [
        "hoso.p1.png",
        "hoso.p2.png",
        "hoso.p3.png",
    ]


def test_batch_picks_up_pdf_files(tmp_path, one_page):
    from qc_scanner.cmd.batch import iter_inputs

    (tmp_path / "a.pdf").write_bytes(one_page)
    (tmp_path / "b.jpg").write_bytes((EXAMPLES / "doc-1.jpg").read_bytes())
    (tmp_path / "c.txt").write_text("bo qua")

    assert sorted(p.name for p in iter_inputs(tmp_path, False)) == ["a.pdf", "b.jpg"]


def test_csv_has_a_page_column(tmp_path, three_pages):
    from qc_scanner.cmd.batch import run
    from qc_scanner.eval import write_csv

    src = tmp_path / "in"
    src.mkdir()
    (src / "hoso.pdf").write_bytes(three_pages)
    rows = run(str(src), None, Config(), quiet=True)

    report = tmp_path / "qc.csv"
    write_csv(rows, str(report))
    header = report.read_text(encoding="utf-8").splitlines()[0]
    assert "page" in header.split(",")
    assert "pdf_source" in header.split(",")
