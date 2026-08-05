import json
import pathlib
import sys

import click

from ..config import Config
from ..doc import scan_document
from ..pdf import build_pdf
from ..qc import ScanError

#: Exit code theo verdict — script gọi qc-scanner phân biệt được bằng `$?`.
EXIT_CODES = {"pass": 0, "warn": 1, "fail": 2}
EXIT_INPUT_ERROR = 3


@click.command()
@click.argument(
    "input", default=(None if sys.stdin.isatty() else "-"), type=click.File("rb")
)
@click.argument(
    "output",
    default=(None if sys.stdin.isatty() else "-"),
    type=click.File("wb", lazy=True),
)
@click.option(
    "--report",
    type=click.File("w", lazy=True),
    help="Ghi báo cáo QC (JSON) ra file thay vì stderr.",
)
@click.option("--quiet", is_flag=True, help="Không in báo cáo QC ra stderr.")
@click.option("--debug-dir", type=click.Path(), help="Xuất ảnh trung gian để soi ca sai.")
@click.option(
    "--detector",
    type=click.Choice(["rembg-contour", "edge-hough"]),
    help="Detector đường chính.",
)
@click.option("--model", help="Model nền của rembg (u2net, isnet-general-use…).")
@click.option(
    "--pre-cropped",
    is_flag=True,
    help="Ảnh vào đã cắt sát từ trước → bỏ qua các kiểm tra về biên (QC-14).",
)
@click.option(
    "--audience",
    type=click.Choice(["capturer", "operator"]),
    help="Ai đọc hint: người chụp (chụp lại được) hay người soi hàng chờ. "
    "Mặc định: người chụp.",
)
@click.option(
    "--cross-check", is_flag=True, help="Chạy detector thứ hai và báo nếu hai bên lệch."
)
@click.option(
    "--page",
    type=int,
    help="Chỉ xử lý một trang của PDF (đánh số từ 1). Mặc định: mọi trang.",
)
@click.option(
    "--format",
    "out_format",
    type=click.Choice(["png", "pdf"]),
    help="Định dạng đầu ra. Mặc định suy từ đuôi OUTPUT (`.pdf` → pdf, còn lại → png).",
)
def main(
    input, output, report, quiet, debug_dir, detector, model, pre_cropped,
    audience, cross_check, page, out_format,
):
    """Nắn phẳng tài liệu và chấm điểm chất lượng.

    Nhận ảnh (JPG/PNG/…) hoặc PDF. Ảnh vẫn ra stdout như cũ; phán quyết đi theo exit
    code (0 pass · 1 warn · 2 fail · 3 đầu vào hỏng) và báo cáo JSON ra stderr.

    PDF nhiều trang: trang đầu ghi vào OUTPUT, các trang sau ghi cạnh nó thành
    `OUTPUT.p2.png`, `OUTPUT.p3.png`… Exit code là **trang tệ nhất**.

    Đầu ra là PDF nếu OUTPUT có đuôi `.pdf` (hoặc `--format pdf`) — khi đó mọi trang
    nằm gọn trong một file, không sinh file `.p2` nào.
    """
    overrides = {}
    if detector:
        overrides["detector"] = detector
    if model:
        overrides["rembg_model"] = model
    if pre_cropped:
        overrides["pre_cropped"] = True
    if audience:
        overrides["hint_audience"] = audience
    if cross_check:
        overrides["cross_check_detectors"] = True
    config = Config.from_env(**overrides)

    try:
        document = scan_document(input.read(), config=config, debug=debug_dir)
    except ScanError as err:
        _emit(err.to_dict(), report, quiet)
        raise SystemExit(EXIT_INPUT_ERROR) from err

    if page is not None:
        if not 1 <= page <= document.page_count:
            _emit(
                {"code": "PAGE_OUT_OF_RANGE",
                 "message": f"--page {page} nhưng file chỉ có {document.page_count} trang"},
                report,
                quiet,
            )
            raise SystemExit(EXIT_INPUT_ERROR)
        document.pages = [document.pages[page - 1]]

    _write_pages(document, output, out_format or _infer_format(output), config)

    # Một trang thì báo cáo giữ nguyên hình dạng cũ (`{verdict, reasons, metrics}`),
    # không bọc thêm tầng `pages` — mọi script đang parse stderr vẫn chạy.
    payload = (
        document.pages[0].to_dict()
        if document.page_count == 1
        else document.to_dict()
    )
    _emit(payload, report, quiet)
    raise SystemExit(EXIT_CODES[document.verdict])


def _infer_format(output):
    """`out.pdf` → pdf, còn lại → png. Đuôi file là chỗ người dùng đã nói ý định rồi."""
    name = getattr(output, "name", None) or ""
    return "pdf" if name.lower().endswith(".pdf") else "png"


def _write_pages(document, output, out_format, config):
    """Trang đầu vào OUTPUT; các trang sau ra file cạnh bên (PNG), hoặc gộp cả vào
    một file (PDF).

    Ghi mọi trang chồng lên cùng một đích sẽ để lại đúng trang cuối và **không báo gì**
    — người dùng nhận một file, tưởng đã xử lý xong cả hồ sơ.
    """
    if out_format == "pdf":
        # PDF chứa được nhiều trang trong một file, nên không có ràng buộc stdout nào
        # và cũng không sinh file `.p2` nào.
        output.write(build_pdf([p.image for p in document.pages], config))
        return

    name = getattr(output, "name", None)
    # Kiểm TRƯỚC khi ghi byte nào: báo lỗi sau khi trang 1 đã ra stdout thì đầu ra
    # vừa hỏng vừa lẫn với thông báo lỗi.
    if document.page_count > 1 and (not name or name == "-"):
        raise click.UsageError(
            f"File có {document.page_count} trang nhưng đầu ra là stdout — "
            "stdout chỉ chứa được một ảnh. Ghi ra file, hoặc chọn `--page N`."
        )

    for index, result in enumerate(document.pages, start=1):
        if result.image is None:
            continue
        if index == 1:
            output.write(result.image)
        else:
            path = pathlib.Path(name)
            target = path.with_name(f"{path.stem}.p{index}{path.suffix}")
            target.write_bytes(result.image)


def _emit(payload, report, quiet):
    if report is not None:
        json.dump(payload, report, ensure_ascii=False, indent=2)
        report.write("\n")
    elif not quiet:
        json.dump(payload, sys.stderr, ensure_ascii=False, indent=2)
        sys.stderr.write("\n")


if __name__ == "__main__":
    main()
