"""Xử lý hàng loạt + báo cáo QC tổng hợp (N-01).

Đây là hình thức QC mà vận hành cần nhất: một thư mục ảnh vào, một thư mục ảnh
ra, và **một file CSV** nói ảnh nào đạt, ảnh nào không, vì sao. Không có báo cáo
gộp thì QC ở quy mô hàng vạn ảnh không tiêu thụ được.

Model rembg được nạp một lần và dùng lại cho cả lô — đây là khác biệt tốc độ
lớn nhất so với gọi CLI trong vòng lặp shell.
"""

import argparse
import pathlib
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from ..config import Config
from ..doc import scan_qc
from ..eval import IMAGE_SUFFIXES, write_csv
from ..qc import ScanError
from ..rembg_session import warmup

EXIT_CODES = {"pass": 0, "warn": 1, "fail": 2}


def iter_inputs(directory, recursive):
    root = pathlib.Path(directory)
    paths = root.rglob("*") if recursive else root.iterdir()
    for path in sorted(paths):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path


def run(directory, out_dir, config, recursive=False, skip_fail=False, quiet=False, jobs=1):
    out_path = pathlib.Path(out_dir) if out_dir else None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)

    warmup(config.rembg_model, config.onnx_providers)

    def process(path):
        started = time.perf_counter()
        try:
            result = scan_qc(path.read_bytes(), config=config)
            row = dict(result.metrics.to_dict())
            row.update(
                file=str(path),
                verdict=result.verdict,
                reasons="|".join(result.codes),
                seconds=round(time.perf_counter() - started, 3),
            )
            # Ảnh fail vẫn được ghi ra theo mặc định: chính người vận hành phải
            # nhìn được nó mới quyết định được. `--skip-fail` cho ai muốn ngược lại.
            if out_path and result.image and not (skip_fail and result.verdict == "fail"):
                (out_path / f"{path.stem}.png").write_bytes(result.image)
        except ScanError as err:
            row = {
                "file": str(path),
                "verdict": "fail",
                "reasons": err.code,
                "seconds": round(time.perf_counter() - started, 3),
            }
        return path, row

    paths = list(iter_inputs(directory, recursive))

    # SPD-3: luồng (không phải tiến trình) — onnxruntime, cv2.imencode/imdecode đều
    # **nhả GIL**, nên luồng chồng được phần OpenCV lên phần suy luận. Tiến trình thì
    # mỗi cái nạp một bản model vào RAM, đắt hơn nhiều mà không nhanh hơn.
    #
    # `ex.map` trả kết quả **đúng thứ tự đầu vào**, nên dòng log và CSV vẫn xếp theo
    # tên file như khi chạy tuần tự — chạy song song không được làm báo cáo xáo trộn.
    if jobs > 1:
        pool = ThreadPoolExecutor(jobs)
        results = pool.map(process, paths)
    else:
        pool, results = None, map(process, paths)

    rows = []
    try:
        for path, row in results:
            rows.append(row)
            if not quiet:
                line = f"{row['verdict']:5} {row['reasons'] or '-':40} {path.name}"
                print(line, file=sys.stderr)
    finally:
        if pool is not None:
            pool.shutdown()

    return rows


def build_parser():
    ap = argparse.ArgumentParser(
        description="Nắn phẳng cả một thư mục ảnh và xuất báo cáo QC dạng CSV."
    )
    ap.add_argument("input_dir")
    ap.add_argument("output_dir", nargs="?", help="Thư mục ghi ảnh PNG đã nắn.")
    ap.add_argument("--report", help="Đường dẫn CSV báo cáo QC.")
    ap.add_argument("-r", "--recursive", action="store_true")
    ap.add_argument("--skip-fail", action="store_true", help="Không ghi ảnh bị fail.")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=2,
        # Mặc định 2 chứ không phải số nhân CPU: onnxruntime **vốn đã dùng hết nhân**
        # cho một lần suy luận, nên thêm luồng không chia được thêm việc tính toán —
        # nó chỉ chồng phần OpenCV (giải mã, mã hoá PNG) lên phần suy luận. Đo trên
        # 37 ảnh: 1→14.2s · 2→11.8s · 3→12.0s · 4→12.7s. Qua 2 là bắt đầu tệ đi.
        # Máy có GPU thì tỉ lệ đảo ngược (phần CPU thành nút cổ chai) — lúc đó nâng lên.
        help="Số ảnh xử lý song song (mặc định 2; đo trên CPU thì quá 2 không nhanh thêm).",
    )
    ap.add_argument("--detector", choices=["rembg-contour", "edge-hough"])
    ap.add_argument("--model", help="Model nền của rembg.")
    ap.add_argument(
        "--pre-cropped",
        action="store_true",
        help="Cả lô là ảnh đã cắt sát từ trước → bỏ qua kiểm tra về biên (QC-14).",
    )
    ap.add_argument(
        "--audience",
        choices=["capturer", "operator"],
        # Khác CLI ở mặc định: chạy lô là chạy trên kho ảnh, không ai chụp lại được
        # nữa, nên hint phải nói cho người soi. [EX-3] · QC-13
        default="operator",
        help="Ai đọc hint. Mặc định `operator` — chạy lô thường là xử lý ảnh tồn kho.",
    )
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    overrides = {"hint_audience": args.audience, "pre_cropped": args.pre_cropped}
    if args.detector:
        overrides["detector"] = args.detector
    if args.model:
        overrides["rembg_model"] = args.model

    rows = run(
        args.input_dir,
        args.output_dir,
        Config.from_env(**overrides),
        recursive=args.recursive,
        skip_fail=args.skip_fail,
        quiet=args.quiet,
        jobs=args.jobs,
    )

    if args.report:
        write_csv(rows, args.report)

    counts = Counter(r["verdict"] for r in rows)
    print(
        f"\n{len(rows)} ảnh: "
        f"{counts.get('pass', 0)} pass · {counts.get('warn', 0)} warn · "
        f"{counts.get('fail', 0)} fail",
        file=sys.stderr,
    )

    # Exit code phản ánh ca tệ nhất trong lô — script gọi biết có phải soi không.
    if counts.get("fail"):
        return EXIT_CODES["fail"]
    return EXIT_CODES["warn"] if counts.get("warn") else EXIT_CODES["pass"]


if __name__ == "__main__":
    raise SystemExit(main())
