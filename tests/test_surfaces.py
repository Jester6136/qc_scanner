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


def test_cli_file_matches_library(lib_output, tmp_path):
    out = tmp_path / "out.png"
    proc = _cli([str(SAMPLE.input_path), str(out)])
    assert proc.returncode == 0, proc.stderr.decode()
    assert out.read_bytes() == lib_output


def test_cli_pipe_matches_library(lib_output):
    proc = _cli([], stdin=SAMPLE.input_bytes)
    assert proc.returncode == 0, proc.stderr.decode()
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
    """BUG-1 hồi quy: một lần scan() = đúng một lần gọi rembg."""
    import qc_scanner.doc as doc

    calls = []
    real = doc.rembg

    def counting(data, *a, **kw):
        calls.append(1)
        return real(data, *a, **kw)

    monkeypatch.setattr(doc, "rembg", counting)
    doc.scan(SAMPLE.input_bytes)
    assert len(calls) == 1
