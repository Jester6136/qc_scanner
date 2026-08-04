import argparse
from io import BytesIO

from flask import Flask, jsonify, request, send_file
from waitress import serve

from ..doc import scan
from ..qc import ScanError

#: Giới hạn kích thước upload (OPS-1) — chặn ảnh khổng lồ làm cạn RAM worker.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def _error(reason_dict, status):
    return jsonify({"error": reason_dict}), status


@app.route("/", methods=["POST"])
def index():
    # SEC-1: nhánh `GET /?url=` đã bị bỏ hẳn — nó fetch URL tùy ý (kể cả
    # file:// và metadata nội bộ). POST file đủ cho mọi ca dùng thật.
    if "file" not in request.files:
        return {"error": "missing post form param 'file'"}, 400

    file_content = request.files["file"].read()

    try:
        image = scan(file_content)
    except ScanError as err:
        # 400 cho lỗi đầu vào, 422 cho ảnh hợp lệ nhưng không xử lý được.
        status = 400 if err.code in {"FILE_EMPTY", "DECODE_FAILED"} else 422
        return _error(err.to_dict(), status)

    return send_file(BytesIO(image), mimetype="image/png")


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

    args = ap.parse_args()
    serve(app, host=args.addr, port=args.port)


if __name__ == "__main__":
    main()
