"""Xác thực API key. Bài quan trọng nhất ở đây là bài về **thứ tự middleware**.

Nạp lại `cmd.server` với biến môi trường riêng cho từng ca, vì module đó đọc cấu
hình đúng một lần lúc nạp — đó là chủ ý (trạng thái bảo mật không được đổi giữa
chừng), nên test phải đi theo cách đó thay vì monkeypatch `AUTH`.
"""

import importlib
import os

import pytest
from fastapi.testclient import TestClient

import synthetic as S
from qc_scanner import auth

GOOD = "qcs-" + "a" * 64
OTHER = "qcs-" + "b" * 64


def _server(monkeypatch, **env):
    for name in ("QC_SCANNER_AUTH", "QC_SCANNER_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import qc_scanner.cmd.server as server

    return importlib.reload(server)


@pytest.fixture
def secured(monkeypatch):
    return _server(monkeypatch, QC_SCANNER_API_KEYS=f"app-web:{GOOD},batch:{OTHER}")


def _post(client, key=None):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return client.post(
        "/",
        files={"file": ("a.png", S.document_on_dark_background(), "image/png")},
        headers=headers,
    )


# --- Cấu hình -------------------------------------------------------------- #


def test_missing_config_refuses_to_run_open():
    """Không đặt gì cả = **không** chạy mở. Quên đặt key phải là lỗi ồn ào.

    Đây là lựa chọn thiết kế trung tâm: kiểu hỏng "quên bật xác thực" không tự
    biểu hiện ra ngoài — service vẫn chạy, `/healthz` vẫn `ok`, ảnh vẫn được chấm.
    Nó chỉ lộ ra khi có người lạ đã đọc được giấy tờ tuỳ thân của khách.
    """
    with pytest.raises(auth.AuthConfigError) as exc:
        auth.load({})
    assert "QC_SCANNER_API_KEYS" in str(exc.value)


def test_running_open_has_to_be_spelled_out():
    """Chạy mở là hợp lệ, nhưng phải khai báo — không có đường vô tình rơi vào."""
    assert auth.load({"QC_SCANNER_AUTH": "off"})["enabled"] is False


def test_keys_together_with_auth_off_is_refused():
    """Đặt key mà lại tắt xác thực gần như luôn là nhầm, và nhầm theo hướng tệ:
    người đặt key tưởng mình đã khoá cửa."""
    with pytest.raises(auth.AuthConfigError):
        auth.load({"QC_SCANNER_AUTH": "off", "QC_SCANNER_API_KEYS": f"a:{GOOD}"})


def test_duplicate_keys_are_refused():
    """Hai client dùng chung một key thì log quy sai người gọi — thu hồi cũng sai."""
    with pytest.raises(auth.AuthConfigError):
        auth.parse_keys(f"app:{GOOD},batch:{GOOD}")


def test_short_keys_are_refused():
    """Key ngắn đoán được. Chặn ở lúc cấu hình, không chờ tới lúc bị dò."""
    with pytest.raises(auth.AuthConfigError):
        auth.parse_keys("app:1234")


def test_generated_keys_are_unique_and_prefixed():
    keys = {auth.generate_key() for _ in range(50)}
    assert len(keys) == 50
    assert all(k.startswith(auth.KEY_PREFIX) for k in keys)


# --- Đường HTTP ------------------------------------------------------------ #


def test_request_without_key_is_rejected(secured):
    response = _post(TestClient(secured.app))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_wrong_key_is_rejected(secured):
    assert _post(TestClient(secured.app), "qcs-" + "c" * 64).status_code == 401


def test_valid_key_gets_through(secured):
    assert _post(TestClient(secured.app), GOOD).status_code == 200


def test_each_client_key_works_on_its_own(secured):
    """Nhiều key là để **xoay** được: thêm key mới, chuyển client, bỏ key cũ.
    Hai key cùng sống một lúc là trạng thái bình thường, không phải ngoại lệ."""
    assert _post(TestClient(secured.app), OTHER).status_code == 200


def test_the_401_says_how_to_authenticate(secured):
    """RFC 6750. Không có header này thì phía tích hợp phải đi đoán."""
    response = _post(TestClient(secured.app))
    assert "bearer" in response.headers.get("www-authenticate", "").lower()


def test_health_check_stays_open(secured):
    """Healthcheck của Docker chạy `urllib` trần bên trong container, không có chỗ
    nhét key. Bắt nó xác thực là container tự báo unhealthy rồi restart vòng vo."""
    response = TestClient(secured.app).get("/healthz")
    assert response.status_code == 200
    assert response.json()["auth"] == "on"


def test_health_check_never_leaks_the_keys(secured):
    """`/healthz` là đường DUY NHẤT không cần xác thực, nên mọi thứ nó trả về đều
    coi như công khai. Nó chỉ được nói cửa có khoá hay không."""
    body = TestClient(secured.app).get("/healthz").text
    assert GOOD not in body and OTHER not in body
    assert "app-web" not in body


def test_broken_config_locks_everything_instead_of_opening_it(monkeypatch):
    """Cấu hình sai → khoá hết, không phải mở hết.

    `main()` in lỗi rồi thoát, nhưng ai đó chạy thẳng `uvicorn qc_scanner.cmd.server:app`
    là bỏ qua `main()`. Lúc đó cửa vẫn phải khoá.
    """
    server = _server(monkeypatch, QC_SCANNER_API_KEYS="app:ngắn")
    assert server.AUTH_ERROR is not None
    assert _post(TestClient(server.app), GOOD).status_code == 401


# --- Thứ tự middleware ----------------------------------------------------- #


def test_unauthenticated_requests_never_reach_the_capacity_limiter(secured, monkeypatch):
    """Bài quan trọng nhất file này: xác thực phải bọc NGOÀI van tải.

    Starlette gọi middleware ngược thứ tự đăng ký, nên đặt nhầm chỗ là chuyện rất
    dễ xảy ra và **không có triệu chứng** ở đường chạy đúng: mọi bài trên vẫn xanh.
    Triệu chứng chỉ xuất hiện khi bị tấn công — người lạ không có key vẫn chiếm
    được suất trong hạn mức đồng thời, và vẫn đẩy được 32MB vào RAM. Chặn ở lớp
    ngoài cùng thì họ chỉ tốn của ta một dòng log.

    Đo bằng cách hạ trần xuống 0: nếu van tải chạy trước, request không key sẽ ra
    `503`; đúng thứ tự thì nó ra `401`.
    """
    monkeypatch.setattr(secured, "MAX_IN_FLIGHT", 0)
    client = TestClient(secured.app)

    # Chốt chặn cho chính phép đo: với key HỢP LỆ thì van tải phải chặn được. Không
    # có dòng này, bài trên vẫn xanh kể cả khi van tải đã hỏng hoàn toàn — lúc đó
    # `401` chẳng chứng minh điều gì về thứ tự.
    assert _post(client, GOOD).status_code == 503

    assert _post(client).status_code == 401


def test_cors_preflight_is_not_blocked(secured):
    """Preflight của trình duyệt **không mang header tuỳ biến** — chặn nó thì
    `fetch()` phía client hỏng trước cả khi kịp gửi key. Preflight không đọc được
    dữ liệu gì nên cho qua là an toàn."""
    response = TestClient(secured.app).options(
        "/",
        headers={
            "Origin": "http://app.noi-bo",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code < 400


def test_comparison_is_constant_time():
    """So sánh chuỗi thường thoát ở byte đầu khác nhau, nên thời gian phản hồi rò
    rỉ việc đoán đúng được bao nhiêu ký tự đầu. Đọc mã thay vì đo đồng hồ: đo thời
    gian trong CI là bài hay đỏ ngẫu nhiên."""
    import inspect

    source = inspect.getsource(auth.client_for)
    assert "compare_digest" in source
    assert "return name" not in source, "thoát sớm khi khớp là lộ thời gian"


def test_the_key_never_appears_in_the_client_name(secured):
    """Tên client đi vào log; key thì không bao giờ."""
    assert set(secured.AUTH["keys"].values()) == {"app-web", "batch"}
    assert all(not name.startswith("qcs-") for name in secured.AUTH["keys"].values())


@pytest.fixture(autouse=True)
def _restore_server_module():
    """Trả `cmd.server` về trạng thái của phần còn lại trong bộ test.

    Không có bước này thì file nào chạy sau sẽ dùng module đang bật xác thực và
    nhận `401` — một kiểu phụ thuộc thứ tự chạy, tức là bài đỏ tuỳ hôm.
    """
    yield
    os.environ["QC_SCANNER_AUTH"] = "off"
    os.environ.pop("QC_SCANNER_API_KEYS", None)
    import qc_scanner.cmd.server as server

    importlib.reload(server)
