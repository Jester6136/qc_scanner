"""Bước tải mô hình lúc build image. Không chạm mạng — giả lập `urlopen`.

Bài ở đây canh đúng một kiểu hỏng, và là kiểu hỏng đắt nhất trong cả dự án: thứ
tải về **sai** mà `docker build` vẫn báo thành công. Khi ấy lỗi chỉ lộ ra trên
máy khách, với một image đã bàn giao, dưới dạng thông báo parse ONNX khó hiểu.
"""

import io
import pathlib

import pytest

from qc_scanner import docaligner as da

PAYLOAD = b"fake-onnx-bytes"


@pytest.fixture
def fake_model(monkeypatch):
    """Ghi đè `MODELS` bằng một mục giả có băm đúng của `PAYLOAD`."""
    import hashlib

    real = hashlib.sha256(PAYLOAD).hexdigest()
    monkeypatch.setitem(da.MODELS, "test", ("test.onnx", "fake-id", real))
    return real


def _serve(monkeypatch, body):
    def fake_urlopen(url):
        return io.BytesIO(body)

    monkeypatch.setattr(da.urllib.request, "urlopen", fake_urlopen)


def test_good_download_lands_on_disk(monkeypatch, tmp_path, fake_model):
    _serve(monkeypatch, PAYLOAD)
    path = da.fetch("test", tmp_path)
    assert path.read_bytes() == PAYLOAD


def test_google_drive_quota_page_is_not_saved_as_a_model(monkeypatch, tmp_path, fake_model):
    """Ca thật đáng sợ nhất: Drive trả **HTTP 200** kèm một trang HTML khi bị giới
    hạn lượt tải. Không kiểm thì trang đó thành `model.onnx` và build vẫn xanh."""
    _serve(monkeypatch, b"<html><body>Quota exceeded</body></html>")

    with pytest.raises(RuntimeError) as exc:
        da.fetch("test", tmp_path)

    assert "HTML" in str(exc.value), "thông báo phải chỉ ra nguyên nhân thật"
    assert not list(tmp_path.glob("*.onnx")), "không được để lại file rác"


def test_truncated_download_leaves_nothing_behind(monkeypatch, tmp_path, fake_model):
    """Tải đứt giữa chừng không được để lại thứ trông như đã tải xong — lần chạy
    sau sẽ thấy file, tưởng đủ, và dùng luôn."""
    _serve(monkeypatch, PAYLOAD[:5])

    with pytest.raises(RuntimeError):
        da.fetch("test", tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_an_existing_but_wrong_file_is_replaced(monkeypatch, tmp_path, fake_model):
    """`Đã có file` không phải là `đã có model`."""
    stale = pathlib.Path(tmp_path) / "test.onnx"
    stale.write_bytes("rác từ lần trước".encode())

    _serve(monkeypatch, PAYLOAD)
    assert da.fetch("test", tmp_path).read_bytes() == PAYLOAD


def test_an_existing_good_file_is_not_downloaded_again(monkeypatch, tmp_path, fake_model):
    """Build lại image không nên tải lại 83MB nếu cache còn dùng được."""
    (pathlib.Path(tmp_path) / "test.onnx").write_bytes(PAYLOAD)

    def explode(url):
        raise AssertionError("không được gọi mạng khi file đã đúng băm")

    monkeypatch.setattr(da.urllib.request, "urlopen", explode)
    assert da.fetch("test", tmp_path).read_bytes() == PAYLOAD


def test_every_shipped_model_declares_a_hash():
    """Thêm mô hình mới mà quên ghim băm là mở lại đúng lỗ hổng này."""
    for head, entry in da.MODELS.items():
        assert len(entry) == 3, head
        assert len(entry[2]) == 64, f"{head}: băm không phải SHA-256"
