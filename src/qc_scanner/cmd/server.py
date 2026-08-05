"""HTTP service (FastAPI + uvicorn) — bề mặt bàn giao chính cho khách.

Hợp đồng đầy đủ: [docs/api.md](../../../docs/api.md), và `tests/test_api_contract.py`
giữ đúng những gì tài liệu đó hứa.

**Vì sao tự kiểm tham số thay vì để FastAPI kiểm**: FastAPI trả `422` cho lỗi
validate, mà `422` trong hợp đồng này đã mang nghĩa khác hẳn — "ảnh hợp lệ nhưng
đầu ra không đáng tin cho OCR". Để mặc định thì hai chuyện rất khác nhau (phía gọi
truyền sai tham số / ảnh chụp hỏng) đội chung một mã, và phía tích hợp không phân
biệt được nên retry hay sửa code. Nên tham số khai báo lỏng rồi tự kiểm, để mọi lỗi
đầu vào rơi về `400` đúng như tài liệu.
"""

import argparse
import os
from typing import Optional

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .. import __version__
from ..config import Config
from ..doc import scan_qc
from ..qc import ScanError
from ..rembg_session import warmup

#: Giới hạn kích thước upload (OPS-1) — chặn ảnh khổng lồ làm cạn RAM worker.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024

app = FastAPI(
    title="qc-scanner",
    version=__version__,
    summary="Nắn phẳng tài liệu và chấm điểm chất lượng.",
    description=(
        "Mỗi lần xử lý trả về một **phán quyết** (`pass`/`warn`/`fail`) kèm mã lý do "
        "và hướng xử lý, không chỉ trả ảnh.\n\n"
        "⚠️ Service **không có xác thực** — chỉ chạy trong mạng nội bộ."
    ),
)


#: Origin được phép gọi từ trình duyệt. `*` = mọi origin.
#: Đặt `QC_SCANNER_CORS_ORIGINS=https://app.noi-bo,https://khac` để thu hẹp.
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("QC_SCANNER_CORS_ORIGINS", "*").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
    # ⚠️ BẮT BUỘC. Trình duyệt **không cho JS đọc** header tuỳ biến nếu không được
    # liệt kê ở đây — `fetch()` sẽ chạy thành công mà `X-QC-Scanner-Verdict` là
    # `null`, và phía gọi tưởng ảnh nào cũng không có phán quyết. Đây là kiểu hỏng
    # âm thầm, không có thông báo lỗi nào cả.
    expose_headers=["X-QC-Scanner-Verdict", "X-QC-Scanner-Reasons"],
    # Không bật `allow_credentials`: service không có phiên đăng nhập nào để gửi
    # kèm, và bật lên thì `allow_origins=["*"]` bị trình duyệt từ chối.
    allow_credentials=False,
)


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """Chặn theo `Content-Length` TRƯỚC khi đọc thân request.

    Đọc rồi mới đo thì ảnh 2GB đã nằm trong RAM mất rồi — đúng thứ giới hạn này
    sinh ra để tránh.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": "payload quá lớn"}, status_code=413)
    return await call_next(request)


@app.post("/", summary="Chấm QC một ảnh")
async def scan_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
):
    # SEC-1: nhánh `GET /?url=` đã bị bỏ hẳn — nó fetch URL tùy ý (kể cả file://
    # và metadata nội bộ). POST file đủ cho mọi ca dùng thật.
    #
    # Mọi lỗi 400 trả CÙNG một hình dạng: `{"error": {code, message, hint, …}}`.
    # Trước đây ca thiếu `file` trả `{"error": "<chuỗi>"}` còn ca ảnh hỏng trả
    # `{"error": {…}}` — cùng một khoá, hai kiểu dữ liệu, phía tích hợp phải đoán.
    if file is None:
        return JSONResponse(
            {"error": ScanError("MISSING_FILE").to_dict()}, status_code=400
        )

    params = request.query_params
    as_json = params.get("format") == "json"

    # QC-13: hệ gọi vào khai báo ai sẽ đọc hint. Luồng realtime (người dùng vừa
    # chụp) để mặc định `capturer`; luồng xử lý kho ảnh truyền `?audience=operator`
    # để không nhận những lời khuyên kiểu "chụp lại" mà không ai thực hiện được.
    audience = params.get("audience")
    if audience not in (None, "capturer", "operator"):
        return JSONResponse(
            {"error": "audience phải là 'capturer' hoặc 'operator'"}, status_code=400
        )

    overrides = {"hint_audience": audience} if audience else {}

    # QC-14: ảnh đã cắt sẵn thì "giấy chạm mép khung" là đương nhiên. Không đoán
    # được từ pixel (đo trên 37 ảnh: hai nhóm trùng dải), nên phía gọi phải nói.
    if params.get("pre_cropped", "").lower() in {"1", "true", "yes"}:
        overrides["pre_cropped"] = True

    content = await file.read()
    try:
        result = scan_qc(content, config=Config.from_env(**overrides))
    except ScanError as err:
        return JSONResponse({"error": err.to_dict()}, status_code=400)

    # 200 cho pass/warn (ảnh dùng được, có thể kèm cảnh báo);
    # 422 cho fail — ảnh hợp lệ nhưng đầu ra không đáng tin cho OCR.
    status = 422 if result.verdict == "fail" else 200

    if as_json:
        return JSONResponse(result.to_dict(include_image=True), status_code=status)

    if result.verdict == "fail":
        return JSONResponse(result.to_dict(), status_code=status)

    return Response(
        content=result.image,
        media_type="image/png",
        headers={
            "X-QC-Scanner-Verdict": result.verdict,
            "X-QC-Scanner-Reasons": ",".join(result.codes),
        },
    )


@app.get("/healthz", summary="Liveness probe")
async def healthz():
    return {"status": "ok"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="HTTP service chấm QC ảnh tài liệu.")
    ap.add_argument(
        "-a", "--addr", default="127.0.0.1", type=str, help="Địa chỉ IP để bind."
    )
    ap.add_argument("-p", "--port", default=5000, type=int, help="Cổng để bind.")
    ap.add_argument(
        "--no-warmup",
        action="store_true",
        help="Bỏ qua bước nạp sẵn model rembg lúc khởi động.",
    )
    args = ap.parse_args(argv)

    # Nạp model TRƯỚC khi mở cổng: request đầu tiên không phải gánh thời gian
    # tải/nạp model, vốn đủ lâu để timeout ở tầng proxy. Đây cũng là lý do
    # `/healthz` trả lời được nghĩa là model đã sẵn sàng.
    if not args.no_warmup:
        warmup(Config.from_env().rembg_model)

    import uvicorn

    # Một tiến trình, không `workers`: mỗi worker nạp một bản model vào RAM, và
    # phần nặng (onnxruntime) vốn đã dùng nhiều luồng. Cần thông lượng cao hơn thì
    # chạy nhiều container sau một bộ cân bằng tải, đo trước rồi hãy làm.
    uvicorn.run(app, host=args.addr, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
