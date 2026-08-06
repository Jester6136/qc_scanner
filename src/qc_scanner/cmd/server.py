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
import sys
import threading
from typing import Optional

import starlette.formparsers
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .. import __version__, auth
from ..config import Config
from ..doc import scan_document
from ..limits import MAX_CONCURRENCY, MAX_IN_FLIGHT, default_concurrency
from ..pdf import build_pdf
from ..qc import ScanError
from ..rembg_session import active_providers, warmup

#: Giới hạn kích thước upload (OPS-1) — chặn ảnh khổng lồ làm cạn RAM worker.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024

# Starlette mặc định đổ phần upload vượt 1MB xuống **file tạm trên đĩa**
# (`SpooledTemporaryFile`). Với service này đó là hai chuyện xấu cùng lúc:
#
# * [EX-12] chốt "không lưu ảnh" — mà ảnh vào là giấy tờ tuỳ thân, và gần như ảnh
#   nào cũng vượt 1MB. Ghi xuống đĩa là đúng thứ đã hứa không làm.
# * Ghi rồi đọc lại vài MB cho mỗi request là chi phí thuần tuý phí phạm.
#
# Nâng ngưỡng bằng đúng trần upload → mọi request hợp lệ nằm trọn trong RAM.
#
# ⚠️ Trần RAM là `MAX_UPLOAD_BYTES` × số request **đang bay**, và `MAX_CONCURRENCY`
# KHÔNG chặn con số đó. Chỗ này trước đây ghi ngược lại, và ghi sai: FastAPI phân
# tích multipart **trước khi** hàm xử lý chạy, nên thân request đã nằm trong RAM từ
# lâu trước khi ai đó xin suất ở `_scan_slots`. Đo được: 24 client gọi cùng lúc với
# `MAX_CONCURRENCY=2` → đúng 2 request đang xử lý, nhưng **24 thân request trong RAM**.
#
# Chốt chặn thật là threadpool của Starlette (mặc định 40 luồng), tức trần thật
# ≈ 40 × 32MB = **1.28 GB**, không phải `MAX_CONCURRENCY` × 32MB. Xem OPS-4.
starlette.formparsers.MultiPartParser.spool_max_size = MAX_UPLOAD_BYTES

# Hai van sống ở `limits.py`, không phải ở đây: `bench.py` cũng cần đúng con số này,
# và bản sao thứ hai của nó đã từng trôi khỏi bản gốc — công cụ đo báo cáo
# `MAX_CONCURRENCY 2` trong khi service đang chạy 16. Xem docstring của module đó.
#
# Giữ tên cũ trong không gian tên này để mã và test đang trỏ vào `server.MAX_*` không
# gãy; middleware bên dưới đọc biến toàn cục của module này nên monkeypatch vẫn ăn.
def _default_concurrency():
    """Giữ lại tên cũ; nguồn sự thật là `limits.default_concurrency()`."""
    return default_concurrency()


_scan_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)


#: Không cần khoá: middleware là `async def` nên chạy trên **một** vòng lặp sự kiện,
#: và giữa chỗ đọc và chỗ tăng không có `await` nào để nhường lượt.
_in_flight = 0

app = FastAPI(
    title="qc-scanner",
    version=__version__,
    summary="Nắn phẳng tài liệu và chấm điểm chất lượng.",
    description=(
        "Mỗi lần xử lý trả về một **phán quyết** (`pass`/`warn`/`fail`) kèm mã lý do "
        "và hướng xử lý, không chỉ trả ảnh.\n\n"
        "Xác thực: `Authorization: Bearer <key>` — xem `QC_SCANNER_API_KEYS`."
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
    expose_headers=[
        "X-QC-Scanner-Verdict",
        "X-QC-Scanner-Reasons",
        "X-QC-Scanner-Pages",
    ],
    # Không bật `allow_credentials`: service không có phiên đăng nhập nào để gửi
    # kèm, và bật lên thì `allow_origins=["*"]` bị trình duyệt từ chối.
    allow_credentials=False,
)


@app.middleware("http")
async def limit_in_flight(request: Request, call_next):
    """Đẩy lùi khi kín tải — **trước khi** thân request được đọc vào RAM.

    Đây là chỗ duy nhất chặn được: middleware chạy trước khi FastAPI phân tích
    multipart, nên từ chối ở đây nghĩa là 32MB kia không bao giờ vào bộ nhớ. Mọi van
    đặt bên trong hàm xử lý đều đã muộn.

    Vì sao máy chủ phải tự đẩy lùi thay vì dặn bên gọi tự giới hạn: bên gọi không nhìn
    thấy tải của những bên gọi khác. Một client cư xử đúng mực vẫn có thể là giọt nước
    cuối cùng khi có năm client khác đang gửi. Bảo vệ bộ nhớ là việc của phía sở hữu
    bộ nhớ.

    `503` chứ không phải `429`: đây là "hết chỗ ngay lúc này", không phải "bạn đã dùng
    quá hạn mức của mình" — không có hạn mức nào theo client cả, và request bị từ chối
    **chưa hề được xử lý**, nên gửi lại là việc đúng.
    """
    global _in_flight
    if request.method != "POST":
        return await call_next(request)
    if _in_flight >= MAX_IN_FLIGHT:
        return JSONResponse(
            {"error": ScanError("SERVER_BUSY").to_dict()},
            status_code=503,
            headers={"Retry-After": "2"},
        )
    _in_flight += 1
    try:
        return await call_next(request)
    finally:
        _in_flight -= 1


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


#: Cấu hình xác thực, đọc **một lần** lúc nạp module. Đọc lại mỗi request thì một
#: lần sửa biến môi trường hụt tay là đổi trạng thái bảo mật của service đang chạy.
#:
#: Cấu hình sai thì **khoá hết**, không phải mở hết: `keys` rỗng mà `enabled` bật
#: nghĩa là không key nào khớp được. Ngã theo hướng an toàn quan trọng nhất đúng lúc
#: ta không biết cấu hình đúng là gì. `main()` in lỗi rồi thoát; nhưng nếu ai đó chạy
#: app này qua uvicorn/gunicorn trực tiếp — bỏ qua `main()` — thì cửa vẫn khoá.
try:
    AUTH = auth.load()
    AUTH_ERROR = None
except auth.AuthConfigError as exc:
    AUTH = {"enabled": True, "keys": {}}
    AUTH_ERROR = exc

#: Đường không cần key. Chỉ `/healthz`, và nó phải mở: healthcheck của Docker chạy
#: bằng `urllib` trần bên trong container, không có chỗ nào nhét key vào; bắt nó
#: xác thực là container tự báo unhealthy rồi restart vòng vo. Đổi lại, `/healthz`
#: không được trả về bất cứ thứ gì nhạy cảm — xem `healthz()`.
PUBLIC_PATHS = frozenset({"/healthz"})


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """Chặn request không có key — **trước** mọi middleware khác.

    Thứ tự là phần quan trọng nhất ở đây, và nó ngược trực giác: Starlette gọi
    middleware theo **chiều ngược** thứ tự đăng ký, nên cái khai báo SAU cùng chạy
    TRƯỚC. Hàm này đứng cuối file middleware để nó bọc ngoài cùng.

    Vì sao phải ngoài cùng: một request không có key mà đi qua được `limit_in_flight`
    là nó đã chiếm một suất trong hạn mức đồng thời, và qua `limit_upload_size` là
    32MB đã vào RAM. Người lạ trong LAN không cần key hợp lệ vẫn làm nghẽn được
    service. Chặn ở lớp ngoài cùng thì họ chỉ tốn được của ta một dòng log.

    `OPTIONS` đi thẳng: đó là preflight CORS của trình duyệt, mà preflight **không
    mang header tuỳ biến** — chặn nó thì `fetch()` phía client hỏng trước khi kịp
    gửi key. Preflight không đọc được dữ liệu gì.
    """
    if not AUTH["enabled"] or request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    client = auth.client_for(request.headers.get("authorization", ""), AUTH["keys"])
    if client is None:
        return JSONResponse(
            {"error": ScanError("UNAUTHORIZED").to_dict()},
            status_code=401,
            # RFC 6750: 401 phải nói bằng cách nào thì xác thực được.
            headers={"WWW-Authenticate": 'Bearer realm="qc-scanner"'},
        )

    # Tên client, KHÔNG PHẢI key. Log là thứ được chép đi khắp nơi — đưa key vào đó
    # là biến mọi bản sao log thành một bản sao bí mật.
    request.state.client = client
    return await call_next(request)


@app.post("/", summary="Chấm QC một ảnh")
def scan_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
):
    # SPD-2: **`def`, không phải `async def`** — và đó là cả vấn đề. `scan_qc()` là
    # code đồng bộ nặng (~0.4s CPU); gọi nó trong một `async def` thì nó chạy thẳng
    # trên vòng lặp sự kiện và **chặn toàn bộ tiến trình**, kể cả `/healthz`. Đo được:
    # 8 request song song → `/healthz` trễ trung vị **617ms**, đủ để healthcheck của
    # Docker nhấp nháy và container bị restart oan giữa lúc đang tải.
    #
    # Khai báo `def` thì Starlette tự đẩy hàm này sang threadpool, vòng lặp sự kiện
    # rảnh trở lại. Đây là lý do `/healthz` để `async def` còn hàm này thì không.
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
    out_format = params.get("format")
    if out_format not in (None, "json", "pdf"):
        return JSONResponse(
            {"error": "format phải là 'json' hoặc 'pdf'"}, status_code=400
        )
    as_json = out_format == "json"

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

    content = file.file.read()  # `.file`, không `await`: đây là endpoint đồng bộ
    try:
        with _scan_slots:
            document = scan_document(content, config=Config.from_env(**overrides))
    except ScanError as err:
        # `400` nói "đầu vào của bạn sai, sửa rồi hãy gửi lại" — đúng cho ảnh hỏng,
        # **sai hoàn toàn** cho lỗi tài nguyên máy chủ. Trên máy H100 (GPU dùng chung
        # với một service vLLM) gặp `CUBLAS_STATUS_ALLOC_FAILED`, và nếu trả `400` thì
        # phía gọi sẽ loại vĩnh viễn một tấm ảnh hoàn toàn tốt. `503` nói đúng chuyện
        # đang xảy ra: máy chủ đang quá tải, **thử lại**.
        status = 503 if err.code == "INFERENCE_FAILED" else 400
        headers = {"Retry-After": "5"} if status == 503 else None
        return JSONResponse({"error": err.to_dict()}, status_code=status, headers=headers)

    # 200 cho pass/warn (ảnh dùng được, có thể kèm cảnh báo);
    # 422 cho fail — ảnh hợp lệ nhưng đầu ra không đáng tin cho OCR.
    # Với PDF nhiều trang, `verdict` là **trang tệ nhất**: một hồ sơ có 1 trang không
    # đọc được thì chưa dùng được, dù 11 trang kia hoàn hảo.
    status = 422 if document.verdict == "fail" else 200

    # `?format=pdf` là hình dạng đầu ra duy nhất chứa được nhiều trang trong **một
    # file**, nên nó theo cùng quy tắc của PNG: `fail` thì trả JSON lý do, không trả
    # file — đưa ra một PDF trông bình thường cho một tài liệu không đọc được là cách
    # chắc chắn nhất để nó bị dùng tiếp.
    if out_format == "pdf" and document.verdict != "fail":
        cfg = Config.from_env(**overrides)
        try:
            content = build_pdf([p.image for p in document.pages], cfg)
        except ScanError as err:
            return JSONResponse({"error": err.to_dict()}, status_code=400)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "X-QC-Scanner-Verdict": document.verdict,
                "X-QC-Scanner-Reasons": ",".join(
                    dict.fromkeys(c for p in document.pages for c in p.codes)
                ),
                "X-QC-Scanner-Pages": str(document.page_count),
            },
        )

    # N-08: PDF nhiều trang không có hình dạng "một file PNG" nào để trả về, nên nó
    # **luôn** ra JSON, kể cả khi không có `?format=json`. Ảnh rời và PDF một trang
    # giữ nguyên hợp đồng cũ từng byte — phía tích hợp hiện tại không phải sửa gì.
    if document.page_count != 1:
        return JSONResponse(document.to_dict(include_image=True), status_code=status)

    result = document.pages[0]

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
    """`async def` có chủ đích: chạy thẳng trên vòng lặp sự kiện nên vẫn trả lời
    ngay cả khi mọi luồng xử lý ảnh đang bận. Đó mới đúng nghĩa liveness.

    `providers` báo cáo execution provider onnxruntime **thực sự** đang chạy, không
    phải cái được yêu cầu. Thiếu thư viện CUDA thì onnxruntime tụt về CPU mà không
    báo lỗi gì — chỉ chậm hơn vài chục lần. Đây là chỗ duy nhất nhìn ra điều đó.
    """
    cfg = Config.from_env()
    return {
        "status": "ok",
        "version": __version__,
        "model": cfg.rembg_model,
        "providers": active_providers(cfg.rembg_model, cfg.onnx_providers),
        "max_concurrency": MAX_CONCURRENCY,
        # Bên gọi đọc hai số này để tự chỉnh mức song song mà không phải ghi cứng con
        # số nào: `max_concurrency` là mức gửi tối ưu, `in_flight`/`max_in_flight` cho
        # biết còn chỗ hay sắp bị đẩy lùi.
        "max_in_flight": MAX_IN_FLIGHT,
        "in_flight": _in_flight,
        # Chỉ bật/tắt, KHÔNG bao giờ số lượng key hay tên client: đây là đường duy
        # nhất không cần xác thực, nên mọi thứ nó trả về đều là công khai. Người
        # vận hành cần đúng một bit ở đây — "cửa có khoá không" — và đó cũng là bit
        # dễ tưởng nhầm nhất sau một lần deploy.
        "auth": "on" if AUTH["enabled"] else "off",
    }


#: Provider được coi là "chạy trên phần cứng tăng tốc".
ACCELERATED = ("CUDA", "TensorRT", "ROCM", "MIGraphX", "OpenVINO", "CoreML", "DML")


def _enforce_gpu(cfg: Config, providers):
    """`QC_SCANNER_REQUIRE_GPU=1` → không có GPU thì **chết hẳn**, đừng chạy tiếp.

    Vì sao đáng có: một service chạy **đúng** mà chậm gấp 30 lần là kiểu hỏng tệ hơn
    một service không lên. Nó không báo gì, healthcheck vẫn xanh, và có thể sống như
    thế nhiều tháng cho tới khi ai đó tình cờ đọc `/healthz`. Container dựng riêng
    cho GPU thì "chạy được bằng CPU" **không phải** đường lui hợp lệ — nó là lỗi cấu
    hình đang giả trang thành thành công.
    """
    if not cfg.require_gpu or any(p.startswith(ACCELERATED) for p in providers):
        return
    print(
        "\n"
        "╭──────────────────────────────────────────────────────────────────────╮\n"
        "│ DỪNG: QC_SCANNER_REQUIRE_GPU đang bật nhưng KHÔNG có provider GPU.   │\n"
        "╰──────────────────────────────────────────────────────────────────────╯\n"
        f"  yêu cầu : {cfg.onnx_providers or '(tự dò)'}\n"
        f"  thực tế : {providers}\n"
        "\n"
        "  Chẩn đoán theo thứ tự — dừng ở lệnh đầu tiên cho kết quả sai:\n"
        "    nvidia-smi                                    # trong container: có thấy GPU?\n"
        "    python -c \"import ctypes; ctypes.CDLL('libcuda.so.1')\"\n"
        "                                                  # driver có nạp được?\n"
        "    pip list | grep -i onnxruntime                # phải là onnxruntime-gpu\n"
        "\n"
        "  Hay gặp nhất: container không được cấp GPU (thiếu NVIDIA Container Toolkit,\n"
        "  hoặc thiếu `deploy.resources.reservations.devices` trong compose).\n"
        "\n"
        "  Chấp nhận chạy CPU thì bỏ QC_SCANNER_REQUIRE_GPU.\n",
        file=sys.stderr,
        flush=True,
    )
    raise SystemExit(3)


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

    if AUTH_ERROR is not None:
        print(f"✗ {AUTH_ERROR}", file=sys.stderr, flush=True)
        return 2

    # Chạy mở là lựa chọn hợp lệ, nhưng phải là lựa chọn CÓ Ý THỨC. Dòng này in ra
    # mỗi lần khởi động để không ai vô tình sống nhiều tháng trong trạng thái đó —
    # đúng kiểu hỏng mà `/healthz` báo `ok` suốt.
    if not AUTH["enabled"]:
        print(
            "⚠️  CẢNH BÁO BẢO MẬT: xác thực đang TẮT (QC_SCANNER_AUTH=off).\n"
            "    Bất kỳ ai gọi tới được cổng này đều gửi/nhận được dữ liệu, mà ảnh\n"
            "    vào là giấy tờ tuỳ thân. Chỉ chấp nhận được nếu cổng bị chặn ở\n"
            "    firewall và LAN là mạng tin được.",
            file=sys.stderr,
            flush=True,
        )

    # Nạp model TRƯỚC khi mở cổng: request đầu tiên không phải gánh thời gian
    # tải/nạp model, vốn đủ lâu để timeout ở tầng proxy. Đây cũng là lý do
    # `/healthz` trả lời được nghĩa là model đã sẵn sàng.
    cfg = Config.from_env()
    if not args.no_warmup:
        warmup(cfg.rembg_model, cfg.onnx_providers)
        # In ra provider THẬT SỰ dùng. Đường GPU hỏng âm thầm: thiếu CUDA thì
        # onnxruntime lặng lẽ chạy CPU, không lỗi, chỉ chậm. Dòng log này là thứ
        # phân biệt "GPU đang chạy" với "tưởng là GPU đang chạy".
        providers = active_providers(cfg.rembg_model, cfg.onnx_providers)
        print(
            f"qc-scanner {__version__} · model={cfg.rembg_model} · "
            f"providers={providers} · max_concurrency={MAX_CONCURRENCY} · "
            f"auth={'on' if AUTH['enabled'] else 'OFF'}",
            flush=True,
        )
        _enforce_gpu(cfg, providers)

    import uvicorn

    # Một tiến trình, không `workers`: mỗi worker nạp một bản model vào RAM, và
    # phần nặng (onnxruntime) vốn đã dùng nhiều luồng. Cần thông lượng cao hơn thì
    # chạy nhiều container sau một bộ cân bằng tải, đo trước rồi hãy làm.
    uvicorn.run(app, host=args.addr, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    main()
