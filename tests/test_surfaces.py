"""§1 — bốn mặt tiền (lib / CLI file / CLI pipe / server) phải cho CÙNG kết quả.

Đây chính là bài kiểm chặn [BUG-1]: khi CLI còn gọi rembg lần thứ hai, đường CLI
cho byte khác đường library. Sau khi sửa, cả bốn phải trùng **byte-for-byte** —
cùng một máy, cùng một build, nên md5 là hợp lệ ở đây (khác §2 so giữa các máy).
"""

import subprocess
import sys

import pytest

from conftest import PAIRS

SAMPLE = PAIRS[0]

#: Ảnh chắc chắn sinh ra lý do — cần cho bài kiểm hint hai tầng, vì ảnh `pass`
#: không có `reasons` nào để so hint.
CLIPPED = next(p for p in PAIRS if p.name == "doc-1")


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


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def _file(pair):
    return {"file": (pair.input_path.name, pair.input_path.read_bytes())}


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

    client = _client(app)
    resp = client.post("/", files=_file(SAMPLE))
    assert resp.status_code == 200
    assert resp.content == lib_output


def test_rembg_runs_once_per_scan(monkeypatch):
    """BUG-1 hồi quy: một lần scan() = đúng một lần gọi rembg.

    Chặng này chiếm ~90% thời gian, nên gọi thừa một lần là chậm gấp đôi —
    và lần thứ hai chạy trên ảnh đã tách nền nên còn cho biên khác.
    """
    import qc_scanner.doc as doc

    calls = []
    real = doc.segment_mask

    def counting(image, *a, **kw):
        calls.append(1)
        return real(image, *a, **kw)

    monkeypatch.setattr(doc, "segment_mask", counting)
    doc.scan(SAMPLE.input_bytes)
    assert len(calls) == 1


def test_image_is_decoded_only_once(monkeypatch):
    """SPD-1: một lần scan = đúng một lần `cv2.imdecode`.

    Đường cũ giải mã hai lần (OpenCV cho ảnh gốc, PIL bên trong rembg) rồi còn giải
    mã lại lần nữa cái PNG RGBA mà rembg trả về. Bài này chốt chuyện đó không quay lại.
    """
    import cv2

    import qc_scanner.doc as doc

    calls = []
    real = cv2.imdecode

    def counting(*a, **kw):
        calls.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(doc.cv2, "imdecode", counting)
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

    client = _client(app)
    resp = client.post("/", files=_file(SAMPLE))
    assert resp.status_code == 200
    assert resp.headers["X-QC-Scanner-Verdict"] in {"pass", "warn"}
    assert "X-QC-Scanner-Reasons" in resp.headers


def test_server_json_format_returns_full_result():
    import base64

    from qc_scanner.cmd.server import app

    client = _client(app)
    resp = client.post("/?format=json", files=_file(SAMPLE))
    payload = resp.json()
    assert payload["verdict"] in {"pass", "warn", "fail"}
    assert payload["metrics"]["alpha_coverage"] > 0
    assert base64.b64decode(payload["image"]).startswith(b"\x89PNG")


def test_server_selects_hint_tier_per_request():
    """QC-13: hệ gọi vào khai báo vai người đọc, cùng một ảnh ra hai lời khuyên."""
    from qc_scanner.cmd.server import app

    client = _client(app)
    hints = {}
    for who in ("capturer", "operator"):
        resp = client.post(f"/?format=json&audience={who}", files=_file(CLIPPED))
        reasons = resp.json()["reasons"]
        assert reasons, "cần một ảnh CÓ lý do thì bài này mới kiểm được gì"
        assert all(r["audience"] == who for r in reasons)
        hints[who] = [r["hint"] for r in reasons]
    assert hints["capturer"] != hints["operator"]


def test_server_rejects_unknown_audience():
    from qc_scanner.cmd.server import app

    client = _client(app)
    resp = client.post("/?audience=nobody", files=_file(SAMPLE))
    assert resp.status_code == 400


def test_server_accepts_pre_cropped_flag():
    """QC-14: phía gọi khai báo ảnh đã cắt sẵn thì mã về biên phải biến mất."""
    from qc_scanner.cmd.server import app

    client = _client(app)
    codes = {}
    for query in ("", "&pre_cropped=1"):
        resp = client.post(f"/?format=json{query}", files=_file(CLIPPED))
        codes[query] = {r["code"] for r in resp.json()["reasons"]}
    assert "CLIPPED_EDGE" in codes[""]
    assert "CLIPPED_EDGE" not in codes["&pre_cropped=1"]


def test_batch_defaults_to_the_operator_tier():
    """Chạy lô = xử lý kho ảnh; ở đó không ai chụp lại được nữa [EX-3]."""
    from qc_scanner.cmd.batch import build_parser

    assert build_parser().parse_args(["in_dir"]).audience == "operator"


def test_library_returns_scan_result():
    from qc_scanner import scan_qc

    result = scan_qc(SAMPLE.input_bytes)
    assert result.verdict in {"pass", "warn", "fail"}
    assert isinstance(result.codes, list)


def test_batch_parallel_matches_serial(tmp_path):
    """SPD-3: `--jobs` chỉ được đổi *tốc độ*, không đổi kết quả lẫn thứ tự.

    Chạy song song mà báo cáo xáo trộn thì không so được hai lần chạy với nhau, và
    CSV mất giá trị đúng ở chỗ nó có ích nhất: đối chiếu trước/sau khi đổi ngưỡng.
    """
    from qc_scanner.cmd.batch import run
    from qc_scanner.config import Config

    src = tmp_path / "in"
    src.mkdir()
    for pair in PAIRS[:3]:
        (src / pair.input_path.name).write_bytes(pair.input_bytes)

    cfg = Config()
    serial = run(str(src), None, cfg, quiet=True, jobs=1)
    parallel = run(str(src), None, cfg, quiet=True, jobs=3)

    def strip(rows):  # `seconds` đương nhiên khác giữa hai lần chạy
        return [{k: v for k, v in r.items() if k != "seconds"} for r in rows]

    assert strip(serial) == strip(parallel)
