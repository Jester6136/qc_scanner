"""Đổi bộ SmartDoc 2015 Challenge 1 thành tập vàng chạy được với `qc-scanner-eval`.

    qc-scanner-smartdoc tmp_smartdoc/sampleDataset --out tmp_smartdoc/goldens

Vì sao cần: mọi ngưỡng trong `config.py` tới giờ chốt trên 38 ảnh của **một**
khách hàng, do chính tôi dán nhãn. Số đo trên tập mình tự chấm thì chứng minh
được tính nhất quán, không chứng minh được tính đúng. SmartDoc là bộ công khai,
**CC-BY-4.0** (dùng thương mại được — đã kiểm trên bản ghi Zenodo 1230218), có
nhãn 4 góc do người khác dựng.

Đầu vào là video preview điện thoại + XML toạ độ 4 góc từng khung. Ta rút khung
thành ảnh rời vì nhãn vàng của bộ eval gắn theo *tấm ảnh*, không theo luồng video.

⚠️ Số chấm ra ở đây **không so thẳng được** với bảng xếp hạng SmartDoc: thước đo
chính thức của họ là Jaccard tính trong hệ toạ độ **tài liệu** (nắn cả dự đoán
lẫn nhãn về khổ giấy rồi mới chồng), còn `qc_scanner.eval` tính IoU trong hệ toạ
độ **ảnh**. Cùng tên "diện tích chồng nhau", khác mẫu số. Dùng nó để so hai
detector với nhau — mục đích thật sự ở đây — thì hợp lệ; dùng để khoe ngang
SOTA thì không.
"""

import argparse
import json
import pathlib
import xml.etree.ElementTree as ET

import cv2

#: Thứ tự 4 điểm bộ eval chờ đợi. XML của SmartDoc ghi theo tên nên không phụ
#: thuộc thứ tự xuất hiện — nhưng vẫn phải đổi sang TL-TR-BR-BL cho đúng hợp đồng.
_ORDER = ("tl", "tr", "br", "bl")


def read_ground_truth(xml_path):
    """`{chỉ số khung: [[x,y] × 4]}`, bỏ những khung bộ dữ liệu đánh dấu loại."""
    root = ET.parse(xml_path).getroot()
    frames = {}
    for frame in root.iter("frame"):
        if frame.get("rejected", "false").lower() == "true":
            continue
        points = {p.get("name"): (float(p.get("x")), float(p.get("y"))) for p in frame}
        if not all(name in points for name in _ORDER):
            continue
        frames[int(frame.get("index"))] = [list(points[name]) for name in _ORDER]
    return frames


def extract(video_path, truth, out_dir, stride=10, prefix=""):
    """Rút mỗi `stride` khung một tấm. Trả danh sách bản ghi nhãn.

    Lấy thưa là có chủ ý: các khung liền nhau của cùng một video gần như trùng
    nhau, nên đếm cả 300 khung chỉ làm mẫu số phồng lên chứ không thêm bằng chứng
    gì — và một `crop_rate` tính trên mẫu số phồng thì dễ đọc nhầm thành đã kiểm
    kỹ hơn thực tế.
    """
    capture = cv2.VideoCapture(str(video_path))
    records, index = [], 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            index += 1  # XML đánh số khung từ 1
            if index % stride or index not in truth:
                continue
            name = f"{prefix}{video_path.stem}-{index:04d}.png"
            cv2.imwrite(str(out_dir / name), frame)
            records.append({"file": name, "corners": truth[index]})
    finally:
        capture.release()
    return records


def _ground_truth_for(video, dataset_dir):
    """Tìm XML nhãn của **đúng** video này. Hai bố cục, và một cái bẫy.

    Bản test để nhãn ngay cạnh video; bản mẫu để ở `<nền>_gt/` nằm dưới một nhánh
    khác hẳn (`input_sample/` và `input_sample_groundtruth/`), nên không tìm được
    bằng cách dò thư mục anh em — phải quét từ gốc bộ dữ liệu.

    Bẫy: tên video **trùng nhau giữa các nền** — `datasheet001.avi` có mặt ở cả
    background01..05. Bản đầu của hàm này gom nhãn vào một `dict` khoá theo mỗi
    tên file, nên 5 nền đè lên nhau còn 1, và cả 912 ảnh rút ra đều đeo nhãn của
    **một** nền duy nhất.

    Kiểu hỏng đó không kêu một tiếng: vẫn đủ ảnh, vẫn đủ nhãn, IoU vẫn ra số đọc
    được — chỉ là số đó đo sai vật. Vì thế tra nhãn phải đi từ *đường dẫn* của
    video, không đi từ tên nó.
    """
    beside = video.with_suffix(".gt.xml")
    if beside.exists():
        return beside
    wanted = f"{video.stem}.gt.xml"
    for candidate in pathlib.Path(dataset_dir).rglob(wanted):
        if candidate.parent.name == f"{video.parent.name}_gt":
            return candidate
    return None


def build(dataset_dir, out_dir, stride=10):
    dataset_dir = pathlib.Path(dataset_dir)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for video in sorted(dataset_dir.rglob("*.avi")):
        xml_path = _ground_truth_for(video, dataset_dir)
        if xml_path is None:
            continue
        # Nền là biến khó nhất của bộ này (background01..05, từ trơn tới lộn xộn),
        # nên nó phải nằm trong tên file — gộp hết vào một rổ thì lúc kết quả xấu
        # sẽ không biết xấu ở nền nào.
        prefix = f"{video.parent.name}-"
        records += extract(video, read_ground_truth(xml_path), out_dir, stride, prefix)

    labels_path = out_dir / "labels.jsonl"
    with open(labels_path, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records), labels_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dataset", help="Thư mục đã giải nén của SmartDoc.")
    ap.add_argument("--out", required=True, help="Nơi ghi ảnh + labels.jsonl.")
    ap.add_argument("--stride", type=int, default=10, help="Lấy 1 khung mỗi N khung.")
    args = ap.parse_args(argv)

    count, path = build(args.dataset, args.out, args.stride)
    print(f"{count} ảnh có nhãn → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
