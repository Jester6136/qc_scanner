"""§3 — ca hỏng phải ra **mã lý do + hint**, không phải None / "oops" / traceback."""

import json
import subprocess
import sys

import pytest

from qc_scanner.doc import scan
from qc_scanner.qc import ScanError


def test_empty_input_raises_file_empty():
    with pytest.raises(ScanError) as exc:
        scan(b"")
    assert exc.value.code == "FILE_EMPTY"


def test_junk_input_raises_decode_failed():
    with pytest.raises(ScanError) as exc:
        scan(b"\x00\x01\x02not-an-image" * 8)
    assert exc.value.code == "DECODE_FAILED"


def test_scan_never_returns_none():
    """Bất biến sau BUG-2: hoặc bytes, hoặc ScanError. Không bao giờ None."""
    try:
        result = scan(b"garbage")
    except ScanError:
        return
    assert result is not None


def test_cli_exits_nonzero_with_json_reason(tmp_path):
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"\x00\x01\x02not-an-image" * 8)
    proc = subprocess.run(
        [sys.executable, "-m", "qc_scanner.cmd.cli", str(junk), str(tmp_path / "o.png")],
        capture_output=True,
    )
    assert proc.returncode != 0
    report = json.loads(proc.stderr.decode())
    assert report["code"] == "DECODE_FAILED"
    assert report["hint"]
    assert report["audience"] in {"capturer", "operator", "system"}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from qc_scanner.cmd.server import app

    return TestClient(app)


def test_server_junk_returns_400_not_200(client):
    """Trước đây trả 200 + PNG rỗng 0 byte — hỏng âm thầm, tệ nhất."""
    resp = client.post("/", files={"file": ("junk.png", b"junk" * 40)})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DECODE_FAILED"


def test_server_empty_file_returns_400(client):
    """BUG-3: `b"" == ""` luôn False nên chốt chặn cũ không bao giờ kích hoạt."""
    resp = client.post("/", files={"file": ("empty.png", b"")})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FILE_EMPTY"


def test_server_missing_file_param_returns_400(client):
    assert client.post("/").status_code == 400


def test_server_url_fetch_endpoint_is_gone(client):
    """SEC-1: `GET /?url=` đọc được file nội bộ — nhánh này phải biến mất hẳn."""
    resp = client.get("/?url=file:///etc/passwd")
    assert resp.status_code == 405
