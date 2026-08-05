"""OPS-4 — máy chủ tự bảo vệ bộ nhớ của mình.

Hai van, hai tài nguyên, và trước đây chỉ có một:

* `MAX_CONCURRENCY` chặn **số ảnh đang xử lý** — bảo vệ CPU.
* `MAX_IN_FLIGHT` chặn **số ảnh đang nằm trong RAM** — bảo vệ bộ nhớ.

Van thứ hai không suy ra được từ van thứ nhất, vì thân request vào bộ nhớ **trước
khi** ai xin được suất xử lý: FastAPI phân tích multipart trước khi hàm xử lý chạy.
Đo trước khi có van: `MAX_CONCURRENCY=2`, 24 client cùng lúc → đúng 2 request đang xử
lý, nhưng **24 thân request trong RAM**.

Chuyện này từng được ghi ngược trong comment của `server.py` ("MAX_CONCURRENCY là thứ
chặn số nhân đó"), nên bộ test ở đây đo thẳng con số thay vì tin vào lời kể.
"""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import EXAMPLES


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from qc_scanner.cmd.server import app

    return TestClient(app)


@pytest.fixture(scope="session")
def photo():
    return (EXAMPLES / "doc-1.jpg").read_bytes()


class _CountingSlots:
    """Bọc `_scan_slots` để đếm luồng ĐÃ giữ thân request và đang chờ suất xử lý.

    Đếm ở `__enter__` (trước `acquire`) chứ không phải sau: chỗ đó mới là lúc thân
    request đã tốn bộ nhớ thật, và đó là con số bài test này quan tâm.
    """

    def __init__(self, inner):
        self.inner = inner
        self.lock = threading.Lock()
        self.holding = 0
        self.peak = 0

    def __enter__(self):
        with self.lock:
            self.holding += 1
            self.peak = max(self.peak, self.holding)
        self.inner.acquire()
        return self

    def __exit__(self, *exc):
        with self.lock:
            self.holding -= 1
        self.inner.release()


def _blast(client, photo, n):
    def one(_):
        resp = client.post("/", files={"file": ("a.jpg", photo)})
        return resp.status_code, resp.headers.get("Retry-After")

    with ThreadPoolExecutor(n) as pool:
        return list(pool.map(one, range(n)))


def test_memory_is_bounded_by_max_in_flight_not_by_max_concurrency(
    client, photo, monkeypatch
):
    """Bài quan trọng nhất file này: đo **bộ nhớ**, không đo thông lượng."""
    from qc_scanner.cmd import server

    counter = _CountingSlots(server._scan_slots)
    monkeypatch.setattr(server, "_scan_slots", counter)
    monkeypatch.setattr(server, "MAX_IN_FLIGHT", 4)

    _blast(client, photo, 20)

    assert counter.peak <= 4, (
        f"{counter.peak} thân request trong RAM cùng lúc, trần khai báo là 4 — "
        "van chặn bộ nhớ không hoạt động"
    )


def test_overload_is_refused_with_503_and_retry_after(client, photo, monkeypatch):
    from qc_scanner.cmd import server

    monkeypatch.setattr(server, "MAX_IN_FLIGHT", 2)
    results = _blast(client, photo, 16)
    codes = Counter(code for code, _ in results)

    assert codes[503] > 0, "gửi 16 request với trần 2 mà không có cái nào bị đẩy lùi"
    assert all(retry for code, retry in results if code == 503), "503 thiếu Retry-After"


def test_busy_says_it_is_not_the_image_s_fault(client, photo, monkeypatch):
    """`SERVER_BUSY` phải nói rõ ảnh chưa được xử lý lần nào.

    Không nói thì hệ gọi rất dễ đối xử với nó như `fail` và **loại một ảnh tốt** —
    đúng lỗi đã sửa cho `INFERENCE_FAILED` ở SPD-6.
    """
    from qc_scanner.cmd import server

    # Ép kín tải một cách xác định thay vì đua nhiều luồng rồi hy vọng trúng — bài này
    # nói về *nội dung* thông báo, không về thời điểm nó xuất hiện.
    monkeypatch.setattr(server, "MAX_IN_FLIGHT", 1)
    monkeypatch.setattr(server, "_in_flight", 1)

    resp = client.post("/", files={"file": ("a.jpg", photo)})
    assert resp.status_code == 503
    body = resp.json()["error"]
    assert body["code"] == "SERVER_BUSY"
    assert "không phải lỗi ảnh" in body["hint"].lower()


def test_the_counter_is_released_on_every_path(client, photo, monkeypatch):
    """Rò bộ đếm là kiểu hỏng tệ nhất có thể ở đây: service tự khoá mình vĩnh viễn
    và chỉ khởi động lại mới cứu được. Nhánh lỗi phải trả suất y như nhánh thành công.
    """
    from qc_scanner.cmd import server

    client.post("/", files={"file": ("junk.png", b"junk" * 40)})  # 400
    client.post("/")  # 400, thiếu file
    client.post("/?format=tiff", files={"file": ("a.jpg", photo)})  # 400, tham số sai
    _blast(client, photo, 8)  # 200 + có thể vài 503

    assert server._in_flight == 0


def test_healthz_answers_while_the_server_is_saturated(client, photo, monkeypatch):
    """Liveness probe phải sống sót qua lúc quá tải, nếu không Docker restart oan
    container **đúng lúc nó đang bận nhất**."""
    from qc_scanner.cmd import server

    monkeypatch.setattr(server, "MAX_IN_FLIGHT", 2)
    with ThreadPoolExecutor(9) as pool:
        load = [
            pool.submit(client.post, "/", files={"file": ("a.jpg", photo)})
            for _ in range(8)
        ]
        assert pool.submit(client.get, "/healthz").result().status_code == 200
        for future in load:
            future.result()


def test_healthz_publishes_the_numbers_a_caller_needs_to_self_tune(client):
    """Bên gọi không phải ghi cứng con số nào — trần suy theo số nhân của máy chạy."""
    body = client.get("/healthz").json()
    assert body["max_concurrency"] >= 1
    assert body["max_in_flight"] >= body["max_concurrency"]
    assert body["in_flight"] >= 0


def test_default_concurrency_matches_both_machines_it_was_measured_on():
    """Neo phép tự suy vào **số đo**, không vào cảm giác.

    Hai điểm đã đo thật:

    * máy dev 10 nhân — 37 ảnh: 1 luồng 14.2s · **2 luồng 11.8s** · 3 luồng 12.0s ·
      4 luồng 12.7s → tốt nhất ở **2**;
    * máy server 64 nhân — `scan_qc` trực tiếp: 1→1.73 · 2→2.84 · 4→4.16 · 8→5.80 ·
      **16→7.64** ảnh/s → tốt nhất trong dải đã quét là **16**.

    Quy tắc cũ (`cpu/8`) cho 8 trên máy 64 nhân, tức bỏ phí mức 16 đo được là tốt hơn.
    """
    from unittest import mock

    from qc_scanner.cmd.server import _default_concurrency

    for cores, expected in ((10, 2), (64, 16)):
        with mock.patch("os.cpu_count", return_value=cores):
            assert _default_concurrency() == expected, f"{cores} nhân"


def test_compose_does_not_hardcode_concurrency():
    """`docker-compose.yml` từng ghi cứng `QC_SCANNER_MAX_CONCURRENCY: "2"`.

    Đó là con số đo trên máy dev 10 nhân, lọt vào file bàn giao. Trên máy server 64
    nhân nó khoá đường HTTP ở 2.86 req/s trong khi lõi chạy được 7.64 ảnh/s — **mất
    ~64% năng lực**, và mất trong im lặng: service vẫn chạy đúng, healthcheck vẫn
    xanh, chỉ mục HTTP của bench là phẳng lì.

    Biến môi trường **đè lên** giá trị tự suy, nên đặt nó trong file dùng chung là vô
    hiệu hoá hoàn toàn phép suy theo số nhân.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in compose.splitlines()
        if "QC_SCANNER_MAX_CONCURRENCY" in line and not line.strip().startswith("#")
    ]
    assert not offenders, (
        f"docker-compose.yml ghi cứng {offenders} — để trống cho máy đích tự suy, "
        "cần ép tay thì đặt lúc chạy"
    )
