"""§1 — bốn mặt tiền (lib / CLI file / CLI pipe / server) phải cho CÙNG kết quả.

Đây chính là bài kiểm chặn [BUG-1]: khi CLI còn gọi rembg lần thứ hai, đường CLI
cho byte khác đường library. Sau khi sửa, cả bốn phải trùng **byte-for-byte** —
cùng một máy, cùng một build, nên md5 là hợp lệ ở đây (khác §2 so giữa các máy).
"""

import subprocess
import sys

import pytest

from conftest import EXAMPLES, PAIRS

SAMPLE = PAIRS[0]


@pytest.fixture(scope="module")
def lib_output():
    from qc_scanner.doc import scan

    return scan(SAMPLE.input_bytes)


def _cli(args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "qc_scanner.cmd.cli", *args],
        input=stdin,
        capture_output=True,
    )


#: 0 pass · 1 warn — cả hai đều nghĩa là có ảnh dùng được ở đầu ra.
OK_EXITS = {0, 1}


def test_cli_file_matches_library(lib_output, tmp_path):
    out = tmp_path / "out.png"
    proc = _cli([str(SAMPLE.input_path), str(out), "--quiet"])
    assert proc.returncode in OK_EXITS, proc.stderr.decode()
    assert out.read_bytes() == lib_output


def test_cli_pipe_matches_library(lib_output):
    proc = _cli(["--quiet"], stdin=SAMPLE.input_bytes)
    assert proc.returncode in OK_EXITS, proc.stderr.decode()
    assert proc.stdout == lib_output


def test_server_matches_library(lib_output):
    from qc_scanner.cmd.server import app

    client = app.test_client()
    resp = client.post(
        "/", data={"file": (SAMPLE.input_path.open("rb"), SAMPLE.input_path.name)}
    )
    assert resp.status_code == 200
    assert resp.data == lib_output


def test_rembg_runs_once_per_scan(monkeypatch):
    """BUG-1 hồi quy: một lần scan() = đúng một lần gọi rembg.

    Chặng này chiếm ~95% thời gian, nên gọi thừa một lần là chậm gấp đôi —
    và lần thứ hai chạy trên ảnh đã tách nền nên còn cho biên khác.
    """
    import qc_scanner.doc as doc

    calls = []
    real = doc.remove_background

    def counting(data, *a, **kw):
        calls.append(1)
        return real(data, *a, **kw)

    monkeypatch.setattr(doc, "remove_background", counting)
    doc.scan(SAMPLE.input_bytes)
    assert len(calls) == 1


def test_cli_exit_code_follows_verdict(tmp_path):
    """Script gọi qc-scanner phân biệt được pass/warn/fail bằng `$?`."""
    import json

    out = tmp_path / "out.png"
    proc = _cli([str(SAMPLE.input_path), str(out)])
    report = json.loads(proc.stderr.decode())
    expected = {"pass": 0, "warn": 1, "fail": 2}[report["verdict"]]
    assert proc.returncode == expected


def test_cli_report_to_file(tmp_path):
    import json

    out = tmp_path / "out.png"
    report_path = tmp_path / "qc.json"
    proc = _cli([str(SAMPLE.input_path), str(out), "--report", str(report_path)])
    assert proc.stderr == b""
    payload = json.loads(report_path.read_text())
    assert payload["verdict"] in {"pass", "warn", "fail"}
    assert "metrics" in payload


def test_server_exposes_verdict_headers():
    from qc_scanner.cmd.server import app

    client = app.test_client()
    resp = client.post(
        "/", data={"file": (SAMPLE.input_path.open("rb"), SAMPLE.input_path.name)}
    )
    assert resp.status_code == 200
    assert resp.headers["X-QC-Scanner-Verdict"] in {"pass", "warn"}
    assert "X-QC-Scanner-Reasons" in resp.headers


def test_server_json_format_returns_full_result():
    import base64

    from qc_scanner.cmd.server import app

    client = app.test_client()
    resp = client.post(
        "/?format=json",
        data={"file": (SAMPLE.input_path.open("rb"), SAMPLE.input_path.name)},
    )
    payload = resp.get_json()
    assert payload["verdict"] in {"pass", "warn", "fail"}
    assert payload["metrics"]["alpha_coverage"] > 0
    assert base64.b64decode(payload["image"]).startswith(b"\x89PNG")


def test_library_returns_scan_result():
    from qc_scanner import scan_qc

    result = scan_qc(SAMPLE.input_bytes)
    assert result.verdict in {"pass", "warn", "fail"}
    assert isinstance(result.codes, list)
