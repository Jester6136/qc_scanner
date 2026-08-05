"""Hợp đồng HTTP — thứ khách tích hợp vào, nên nó phải gãy ở ĐÂY chứ không gãy ở họ.

Khác `test_surfaces.py`: file kia hỏi "bốn mặt tiền có cho cùng kết quả không";
file này hỏi "hình dạng phản hồi có đúng như [docs/api.md](../docs/api.md) không".
Sửa API mà quên sửa tài liệu → test đỏ.

Không dựng cổng thật: `TestClient` của FastAPI đi qua đúng lớp ASGI của ứng dụng,
không cần process riêng, chạy được trong CI không mạng.

Bộ test này **không đổi khi đổi framework**. Nó viết theo `docs/api.md` chứ không
theo Flask hay FastAPI — và chính vì thế nó là thứ chứng minh việc chuyển sang
FastAPI không làm gãy tích hợp của khách.
"""

import base64

import pytest

from conftest import PAIRS
from qc_scanner.qc import REASONS

SAMPLE = PAIRS[0]
CLIPPED = next(p for p in PAIRS if p.name == "doc-1")

REQUIRED_REASON_FIELDS = {"code", "severity", "message", "hint", "audience", "hints"}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from qc_scanner.cmd.server import app

    return TestClient(app)


def _files(pair=SAMPLE):
    return {"file": (pair.input_path.name, pair.input_path.read_bytes())}


def _post(client, pair=SAMPLE, query="", files=None):
    return client.post(f"/{query}", files=files if files is not None else _files(pair))


# --- Hình dạng phản hồi thành công ------------------------------------------ #


def test_json_response_has_the_documented_top_level_keys(client):
    payload = _post(client, query="?format=json").json()
    assert set(payload) >= {"verdict", "reasons", "metrics", "image"}
    assert payload["verdict"] in {"pass", "warn", "fail"}


def test_image_field_is_base64_png(client):
    payload = _post(client, query="?format=json").json()
    assert base64.b64decode(payload["image"]).startswith(b"\x89PNG")


def test_default_response_is_a_png_with_verdict_headers(client):
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.content.startswith(b"\x89PNG")
    assert resp.headers["X-QC-Scanner-Verdict"] in {"pass", "warn"}
    assert "X-QC-Scanner-Reasons" in resp.headers


def test_every_reason_carries_every_documented_field(client):
    payload = _post(client, CLIPPED, "?format=json").json()
    assert payload["reasons"], "cần ảnh CÓ lý do thì bài này mới kiểm được gì"
    for reason in payload["reasons"]:
        assert REQUIRED_REASON_FIELDS <= set(reason)
        assert reason["code"] in REASONS, "mã lạ không có trong danh mục"
        assert set(reason["hints"]) == {"capturer", "operator"}


def test_corners_are_four_points_in_original_coordinates(client):
    payload = _post(client, query="?format=json").json()
    corners = payload["corners"]
    assert len(corners) == 4 and all(len(p) == 2 for p in corners)


# --- Bất biến của phán quyết ------------------------------------------------ #


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.name)
def test_pass_iff_no_reasons_over_http(client, pair):
    """Bất biến lõi phải sống sót qua tầng JSON, không chỉ đúng trong Python."""
    payload = _post(client, pair, "?format=json").json()
    assert (payload["verdict"] == "pass") == (payload["reasons"] == [])


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.name)
def test_status_code_follows_verdict(client, pair):
    resp = _post(client, pair, "?format=json")
    expected = 422 if resp.json()["verdict"] == "fail" else 200
    assert resp.status_code == expected


def test_fail_verdict_returns_json_even_without_format_json(client):
    """Ảnh fail thì không trả PNG trần — trả PNG là mời phía gọi dùng nhầm nó."""
    resp = client.post("/", files={"file": ("x.png", _tiny_unusable_png())})
    assert resp.status_code == 422, "ảnh 40x40 toàn đen phải fail — nếu không, ca này vô nghĩa"
    assert resp.headers["content-type"].startswith("application/json")
    assert not resp.content.startswith(b"\x89PNG")


# --- Lỗi đầu vào: MỘT hình dạng duy nhất ------------------------------------ #


def test_missing_file_returns_the_same_error_shape_as_a_bad_image(client):
    """Cùng khoá `error` thì phải cùng kiểu dữ liệu.

    Trước đây ca thiếu `file` trả `{"error": "<chuỗi>"}` còn ca ảnh hỏng trả
    `{"error": {...}}` — phía tích hợp phải đoán xem lần này nhận được cái gì.
    """
    missing = client.post("/").json()
    broken = client.post("/", files={"file": ("x.jpg", b"not an image")}).json()

    for payload in (missing, broken):
        assert isinstance(payload["error"], dict)
        assert REQUIRED_REASON_FIELDS <= set(payload["error"])
        assert payload["error"]["code"] in REASONS


@pytest.mark.parametrize(
    "files,code",
    [
        (None, "MISSING_FILE"),
        ({"file": ("empty.jpg", b"")}, "FILE_EMPTY"),
        ({"file": ("x.jpg", b"not an image")}, "DECODE_FAILED"),
    ],
)
def test_input_errors_are_400_with_their_documented_code(client, files, code):
    resp = client.post("/", files=files) if files else client.post("/")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == code


def test_unknown_audience_is_rejected_not_ignored(client):
    """Lặng lẽ bỏ qua tham số sai thì phía gọi tưởng đã bật, mà thực ra chưa."""
    assert _post(client, query="?audience=nobody").status_code == 400


# --- Bề mặt endpoint -------------------------------------------------------- #


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.json()["status"] == "ok"


def test_get_root_is_gone_for_good(client):
    """SEC-1: nhánh `GET /?url=` từng đọc được `file:///etc/passwd`. Không quay lại."""
    assert client.get("/?url=file:///etc/passwd").status_code == 405


def test_upload_limit_is_enforced(client):
    from qc_scanner.cmd.server import MAX_UPLOAD_BYTES

    oversized = b"\x00" * (MAX_UPLOAD_BYTES + 1024)
    resp = client.post("/", files={"file": ("big.jpg", oversized)})
    assert resp.status_code == 413


def _tiny_unusable_png():
    import cv2
    import numpy as np

    return cv2.imencode(".png", np.zeros((40, 40, 3), np.uint8))[1].tobytes()


# --- CORS: app chạy trên trình duyệt ở máy khác gọi vào được ------------------ #


def test_preflight_is_allowed(client):
    """Không có bước này thì `fetch()` từ trình duyệt chết ngay ở OPTIONS."""
    resp = client.options(
        "/",
        headers={
            "Origin": "http://may-b.noi-bo",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] in {"*", "http://may-b.noi-bo"}


def test_verdict_headers_are_readable_from_the_browser(client):
    """`expose_headers` thiếu thì JS đọc header tuỳ biến ra `null` — hỏng ÂM THẦM.

    Request vẫn 200, ảnh vẫn về, chỉ có phán quyết là biến mất. Không có bài này
    thì không gì phát hiện được.
    """
    resp = client.post("/", files=_files(), headers={"Origin": "http://may-b.noi-bo"})
    assert resp.status_code == 200
    exposed = resp.headers.get("access-control-expose-headers", "")
    assert "X-QC-Scanner-Verdict" in exposed
    assert "X-QC-Scanner-Reasons" in exposed
