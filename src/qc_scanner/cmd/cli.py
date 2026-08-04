import json
import sys

import click

from ..doc import scan
from ..qc import ScanError


@click.command()
@click.argument(
    "input", default=(None if sys.stdin.isatty() else "-"), type=click.File("rb")
)
@click.argument(
    "output",
    default=(None if sys.stdin.isatty() else "-"),
    type=click.File("wb", lazy=True),
)
def main(input, output):
    """Nắn phẳng tài liệu: qc-scanner [INPUT] [OUTPUT] (mặc định stdin/stdout)."""
    try:
        output.write(scan(input.read()))
    except ScanError as err:
        json.dump(err.to_dict(), sys.stderr, ensure_ascii=False, indent=2)
        sys.stderr.write("\n")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
