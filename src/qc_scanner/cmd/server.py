import argparse
from io import BytesIO

from flask import Flask, jsonify, request, send_file
from waitress import serve

from ..config import Config
from ..doc import scan_qc
from ..qc import ScanError
from ..rembg_session import warmup

#: Giới hạn kích thước upload (OPS-1) — chặn ảnh khổng lồ làm cạn RAM worker.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


@app.route("/", methods=["POST"])
def index():
    # SEC-1: nhánh `GET /?url=` đã bị bỏ hẳn — nó fetch URL tùy ý (kể cả
    # file:// và metadata nội bộ). POST file đủ cho mọi ca dùng thật.
    if "file" not in request.files:
        return jsonify({"error": "missing post form param 'file'"}), 400

    file_content = request.files["file"].read()
    as_json = request.args.get("format") == "json"

    try:
        result = scan_qc(file_content, config=Config.from_env())
    except ScanError as err:
        return jsonify({"error": err.to_dict()}), 400

    # 200 cho pass/warn (ảnh dùng được, có thể kèm cảnh báo);
    # 422 cho fail — ảnh hợp lệ nhưng đầu ra không đáng tin cho OCR.
    status = 422 if result.verdict == "fail" else 200

    if as_json:
        return jsonify(result.to_dict(include_image=True)), status

    if result.verdict == "fail":
        return jsonify(result.to_dict()), status

    response = send_file(BytesIO(result.image), mimetype="image/png")
    response.headers["X-QC-Scanner-Verdict"] = result.verdict
    response.headers["X-QC-Scanner-Reasons"] = ",".join(result.codes)
    return response


@app.route("/healthz", methods=["GET"])
def healthz():
    return {"status": "ok"}


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "-a",
        "--addr",
        default="127.0.0.1",
        type=str,
        help="The IP address to bind to.",
    )

    ap.add_argument(
        "-p",
        "--port",
        default=5000,
        type=int,
        help="The port to bind to.",
    )

    ap.add_argument(
        "--no-warmup",
        action="store_true",
        help="Bỏ qua bước nạp sẵn model rembg lúc khởi động.",
    )

    args = ap.parse_args()

    # Nạp model trước khi mở cổng: request đầu tiên không phải gánh thời gian
    # tải/nạp model, vốn đủ lâu để timeout ở tầng proxy.
    if not args.no_warmup:
        warmup(Config.from_env().rembg_model)

    serve(app, host=args.addr, port=args.port)


if __name__ == "__main__":
    main()
