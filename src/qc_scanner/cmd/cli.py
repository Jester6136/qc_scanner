import json
import sys

import click

from ..config import Config
from ..doc import scan_qc
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
    "--cross-check", is_flag=True, help="Chạy detector thứ hai và báo nếu hai bên lệch."
)
def main(input, output, report, quiet, debug_dir, detector, model, cross_check):
    """Nắn phẳng tài liệu và chấm điểm chất lượng.

    Ảnh vẫn ra stdout như cũ; phán quyết đi theo exit code (0 pass · 1 warn ·
    2 fail · 3 đầu vào hỏng) và báo cáo JSON ra stderr.
    """
    overrides = {}
    if detector:
        overrides["detector"] = detector
    if model:
        overrides["rembg_model"] = model
    if cross_check:
        overrides["cross_check_detectors"] = True
    config = Config.from_env(**overrides)

    try:
        result = scan_qc(input.read(), config=config, debug=debug_dir)
    except ScanError as err:
        _emit(err.to_dict(), report, quiet)
        raise SystemExit(EXIT_INPUT_ERROR)

    if result.image is not None:
        output.write(result.image)

    _emit(result.to_dict(), report, quiet)
    raise SystemExit(EXIT_CODES[result.verdict])


def _emit(payload, report, quiet):
    if report is not None:
        json.dump(payload, report, ensure_ascii=False, indent=2)
        report.write("\n")
    elif not quiet:
        json.dump(payload, sys.stderr, ensure_ascii=False, indent=2)
        sys.stderr.write("\n")


if __name__ == "__main__":
    main()
