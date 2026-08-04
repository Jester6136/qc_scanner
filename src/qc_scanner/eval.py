"""Bộ đo chất lượng — chạy qc_scanner trên một thư mục ảnh và báo cáo bằng số.

Hai chế độ, tuỳ có nhãn hay không:

* **Không nhãn** — đổ metric + verdict từng ảnh ra CSV, tổng hợp phân bố verdict
  và mã lý do. Đủ để so **hai cấu hình** với nhau (đổi model, đổi detector,
  đổi ngưỡng) qua `--baseline`.
* **Có nhãn** (`--labels`) — thêm ba con số nghiệm thu: crop rate, false pass,
  false fail, kèm ma trận nhầm lẫn mã lý do.

Định dạng nhãn, mỗi dòng một JSON object::

    {"file": "real-042.jpg",
     "corners": [[120,88],[1810,140],[1795,2480],[95,2410]],
     "expect_verdict": "pass", "expect_reasons": []}

`corners` theo thứ tự TL-TR-BR-BL trong hệ toạ độ ảnh gốc.

⚠️ Không có tập vàng của khách thì phần "ba con số" **không chạy được** — đó là
dữ liệu phải xin, không phải thứ suy ra được từ ảnh mẫu OSS.
"""

import argparse
import csv
import json
import pathlib
import sys
import time
from collections import Counter

import cv2
import numpy as np

from . import geometry as geo
from .config import Config
from .doc import scan_qc
from .qc import ScanError

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

#: IoU tối thiểu giữa tứ giác dự đoán và nhãn để tính là "nắn đúng".
CROP_IOU_THRESHOLD = 0.90

CSV_FIELDS = [
    "file",
    "verdict",
    "reasons",
    "seconds",
    "alpha_coverage",
    "contour_candidates",
    "quad_area_ratio",
    "skew_ratio",
    "is_convex",
    "touches_border",
    "est_dpi",
    "blur_score",
    "glare_ratio",
    "median_brightness",
    "fallback_used",
    "detector",
    "detector_confidence",
    "detector_iou",
    "iou_vs_label",
    "expect_verdict",
]


def iter_images(directory):
    for path in sorted(pathlib.Path(directory).iterdir()):
        if path.suffix.lower() in IMAGE_SUFFIXES and not path.name.endswith(".out.png"):
            yield path


def load_labels(path):
    if not path:
        return {}
    labels = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            record = json.loads(line)
            labels[record["file"]] = record
    return labels


def evaluate(directory, config, labels=None):
    labels = labels or {}
    rows = []
    for path in iter_images(directory):
        label = labels.get(path.name, {})
        started = time.perf_counter()
        try:
            result = scan_qc(path.read_bytes(), config=config)
            elapsed = time.perf_counter() - started
            row = dict(result.metrics.to_dict())
            row.update(
                file=path.name,
                verdict=result.verdict,
                reasons="|".join(result.codes),
                seconds=round(elapsed, 3),
            )
            if label.get("corners") and result.corners:
                image = cv2.imread(str(path))
                row["iou_vs_label"] = round(
                    geo.iou(
                        np.array(result.corners, dtype=np.float32),
                        np.array(label["corners"], dtype=np.float32),
                        image.shape,
                    ),
                    4,
                )
        except ScanError as err:
            row = {
                "file": path.name,
                "verdict": "fail",
                "reasons": err.code,
                "seconds": round(time.perf_counter() - started, 3),
            }
        if label.get("expect_verdict"):
            row["expect_verdict"] = label["expect_verdict"]
        rows.append(row)
    return rows


def summarize(rows):
    verdicts = Counter(r["verdict"] for r in rows)
    codes = Counter(c for r in rows for c in (r["reasons"] or "").split("|") if c)
    times = [r["seconds"] for r in rows if r.get("seconds")]
    summary = {
        "images": len(rows),
        "verdicts": dict(verdicts),
        "reason_codes": dict(codes.most_common()),
        "seconds_median": round(float(np.median(times)), 3) if times else None,
    }

    labelled = [r for r in rows if r.get("expect_verdict")]
    if labelled:
        summary["accuracy"] = _accuracy(labelled)
    return summary


def _accuracy(rows):
    """Ba con số nghiệm thu. False pass là chỉ số quan trọng nhất.

    Sai nguyên nhân (fail đúng nhưng chỉ sai đường) cũng là hỏng — người dùng
    làm theo hint sai sẽ chụp lại vẫn sai. Vì thế có cả ma trận nhầm lẫn.
    """
    cropped = [r for r in rows if r.get("iou_vs_label") is not None]
    good_crop = [r for r in cropped if r["iou_vs_label"] >= CROP_IOU_THRESHOLD]

    false_pass = [
        r for r in rows if r["expect_verdict"] != "pass" and r["verdict"] == "pass"
    ]
    false_fail = [
        r for r in rows if r["expect_verdict"] == "pass" and r["verdict"] == "fail"
    ]

    confusion = Counter(
        (r["expect_verdict"], r["verdict"])
        for r in rows
        if r["expect_verdict"] != r["verdict"]
    )

    return {
        "labelled": len(rows),
        "crop_rate": _pct(len(good_crop), len(cropped)),
        "false_pass_rate": _pct(len(false_pass), len(rows)),
        "false_pass_files": [r["file"] for r in false_pass],
        "false_fail_rate": _pct(len(false_fail), len(rows)),
        "false_fail_files": [r["file"] for r in false_fail],
        "confusion": {f"{k[0]}->{k[1]}": v for k, v in confusion.items()},
    }


def _pct(part, total):
    return round(100.0 * part / total, 2) if total else None


def compare(current, baseline_path):
    """So hai lần chạy — đây là cách duy nhất để nói 'thay đổi này tốt hơn'."""
    with open(baseline_path, newline="", encoding="utf-8") as fh:
        baseline = {r["file"]: r for r in csv.DictReader(fh)}

    moved = []
    for row in current:
        before = baseline.get(row["file"])
        if before and before["verdict"] != row["verdict"]:
            moved.append(
                {
                    "file": row["file"],
                    "from": before["verdict"],
                    "to": row["verdict"],
                    "reasons_before": before["reasons"],
                    "reasons_after": row["reasons"],
                }
            )
    return {
        "changed": len(moved),
        "moves": moved,
    }


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Đo chất lượng qc_scanner trên một thư mục ảnh.")
    ap.add_argument("directory", help="Thư mục chứa ảnh cần đo.")
    ap.add_argument("--labels", help="File JSONL nhãn vàng (tuỳ chọn).")
    ap.add_argument("--csv", help="Ghi metric từng ảnh ra CSV.")
    ap.add_argument("--baseline", help="CSV của lần chạy trước để so verdict.")
    ap.add_argument("--detector", choices=["rembg-contour", "edge-hough"])
    ap.add_argument("--model", help="Model nền của rembg.")
    ap.add_argument("--cross-check", action="store_true")
    args = ap.parse_args(argv)

    overrides = {}
    if args.detector:
        overrides["detector"] = args.detector
    if args.model:
        overrides["rembg_model"] = args.model
    if args.cross_check:
        overrides["cross_check_detectors"] = True

    rows = evaluate(args.directory, Config.from_env(**overrides), load_labels(args.labels))
    report = summarize(rows)
    if args.baseline:
        report["vs_baseline"] = compare(rows, args.baseline)
    if args.csv:
        write_csv(rows, args.csv)
        report["csv"] = args.csv

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
