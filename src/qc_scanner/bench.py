"""Đo tốc độ trên máy đích — chạy thẳng trong container.

    docker exec qc-scanner qc-scanner-bench
    docker exec qc-scanner qc-scanner-bench --url http://127.0.0.1:5000

Mục đích: trả lời **hai** câu bằng số đo trên máy thật, không phải phỏng đoán.

1. *Máy khoẻ hơn thì còn lâu không?* → mục "CHẶNG" và "SONG SONG".
2. *Có đáng làm dynamic batching không?* → mục "BATCH". Xem docstring `bench_batch()`;
   câu trả lời nằm ở tỉ lệ giữa phần GPU và phần CPU, không ở tốc độ GPU.

Mặc định **tự sinh ảnh**, không cần dữ liệu gì trong container — ảnh khách hàng
không bao giờ được nướng vào image. Có ảnh thật thì trỏ `--images /duong/dan` để
số đo sát thực tế hơn (kích thước ảnh quyết định phần lớn chi phí CPU).
"""

import argparse
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from . import __version__
from .config import Config
from .doc import scan_qc
from .rembg_session import active_providers, get_session, warmup

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _hr(title):
    print(f"\n{'─' * 72}\n{title}\n{'─' * 72}", flush=True)


# --------------------------------------------------------------------------- #
# Ảnh thử


def synth_photo(seed, height=4032, width=3024):
    """Ảnh chụp tài liệu giả lập, cỡ ảnh điện thoại thật.

    Kích thước mới là thứ đáng giữ cho giống thật: chi phí CPU (giải mã JPEG, resize,
    mã hoá PNG) tỉ lệ với số pixel, và trên GPU thì **chính phần đó** thành nút cổ
    chai. Đo bằng ảnh 500px sẽ cho một con số đẹp và vô dụng.
    """
    rng = np.random.default_rng(seed)
    img = np.full((height, width, 3), 70, np.uint8)
    img += rng.integers(0, 40, (height, width, 3), dtype=np.uint8)  # vân mặt bàn

    # Tờ giấy trắng, nghiêng một chút như ảnh chụp tay
    sheet = np.full((int(height * 0.78), int(width * 0.72), 3), 246, np.uint8)
    for i in range(14):  # vài dòng "chữ" cho ảnh có nội dung tần số cao
        y = int(sheet.shape[0] * (0.08 + i * 0.062))
        cv2.line(sheet, (40, y), (sheet.shape[1] - 40, y), (35, 35, 35), 9)

    corners = np.float32(
        [[0, 0], [sheet.shape[1], 0], [sheet.shape[1], sheet.shape[0]], [0, sheet.shape[0]]]
    )
    ox, oy = int(width * 0.14), int(height * 0.11)
    jitter = rng.integers(-60, 60, (4, 2))
    dst = np.float32(
        [[ox, oy], [width - ox, oy], [width - ox, height - oy], [ox, height - oy]]
    )
    dst += jitter
    matrix = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(sheet, matrix, (width, height))
    mask = warped.any(axis=2)
    img[mask] = warped[mask]
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def load_images(directory, count):
    if directory:
        import pathlib

        paths = sorted(
            p
            for p in pathlib.Path(directory).iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
        )
        if not paths:
            sys.exit(f"không có ảnh nào trong {directory}")
        chosen = paths[:count]
        return [p.read_bytes() for p in chosen], f"{directory} ({len(chosen)} ảnh)"
    print(f"đang sinh {count} ảnh thử…", flush=True)
    return [synth_photo(i) for i in range(count)], f"tự sinh ({count} ảnh 3024×4032)"


# --------------------------------------------------------------------------- #
# Các phép đo


def bench_stages(blobs, cfg):
    """Tách thời gian thành GIẢI MÃ / SUY LUẬN / PHẦN CÒN LẠI.

    Đây là mục quan trọng nhất của cả script. Trên CPU, suy luận chiếm ~80% nên mọi
    thứ khác không đáng bàn. Trên GPU tỉ lệ **đảo ngược**, và lúc đó "phần còn lại"
    (giải mã ảnh, resize, mã hoá PNG) mới là thứ quyết định thông lượng — nó chạy
    trên CPU và **dynamic batching không chạm được vào nó**.
    """
    from PIL import Image

    sess = get_session(cfg.rembg_model, cfg.onnx_providers)
    dec, inf, rest = [], [], []
    for b in blobs:
        t0 = time.perf_counter()
        orig = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
        t1 = time.perf_counter()
        sess.predict(Image.fromarray(cv2.cvtColor(orig, cv2.COLOR_BGR2RGB)))
        t2 = time.perf_counter()
        scan_qc(b, config=cfg)
        t3 = time.perf_counter()
        dec.append(t1 - t0)
        inf.append(t2 - t1)
        rest.append((t3 - t2) - (t2 - t1) - (t1 - t0))

    total = statistics.median(dec) + statistics.median(inf) + max(statistics.median(rest), 0)
    for name, xs in (("giải mã ảnh", dec), ("suy luận (rembg)", inf), ("phần còn lại", rest)):
        med = max(statistics.median(xs), 0)
        print(f"  {name:22} {med * 1000:7.1f} ms/ảnh   {med / total * 100:5.1f}%")
    print(f"  {'TỔNG':22} {total * 1000:7.1f} ms/ảnh")

    cpu_share = 1 - statistics.median(inf) / total
    print(
        f"\n  Phần chạy trên CPU (không batch được): **{cpu_share * 100:.0f}%**"
        f"  ≈ {(total - statistics.median(inf)) * 1000:.0f} ms/ảnh"
    )
    return total, statistics.median(inf), total - statistics.median(inf)


def bench_parallel(blobs, cfg, jobs_list):
    """Thông lượng thật của `scan_qc()` theo số luồng.

    Luồng (không phải tiến trình) vì onnxruntime và cv2 đều nhả GIL. Con số cao nhất
    ở đây là trần thông lượng của **một tiến trình** — vượt qua nó thì phải chạy
    nhiều container.
    """
    best = 0.0
    for jobs in jobs_list:
        t = time.perf_counter()
        if jobs == 1:
            for b in blobs:
                scan_qc(b, config=cfg)
        else:
            with ThreadPoolExecutor(jobs) as ex:
                list(ex.map(lambda b: scan_qc(b, config=cfg), blobs))
        d = time.perf_counter() - t
        rate = len(blobs) / d
        best = max(best, rate)
        print(
            f"  jobs={jobs:3d}  {d:6.2f}s  "
            f"{d / len(blobs) * 1000:7.1f} ms/ảnh  {rate:6.2f} ảnh/s"
        )
    return best


def bench_batch(cfg, sizes):
    """Đo lợi ích của dynamic batching — **trực tiếp trên GPU của máy này**.

    ⚠️ File ONNX u2net xuất ra với batch **đóng cứng bằng 1**; chạy batch>1 là lỗi
    `INVALID_ARGUMENT`. Hàm này vá trục batch thành động ngay trong bộ nhớ (U²-Net
    toàn tích chập nên chấp nhận được — đã kiểm). Đây chỉ là phép đo; đường chạy
    thật **không** dùng bản vá này.

    Cách đọc kết quả: batching chỉ nén được phần suy luận. Nếu mục CHẶNG cho thấy
    suy luận là 10ms còn phần CPU là 80ms, thì batching giỏi lắm cắt được 10ms →
    tổng cải thiện ~10%. Con số cần so là **ms/ảnh tiết kiệm được** với **ms CPU
    mỗi ảnh**, chứ không phải "batch nhanh gấp mấy lần".

    Chạy mục này **trên CPU thì vô nghĩa** — CPU đã bão hoà từ batch=1 nên số đo chỉ
    là nhiễu. Nó sinh ra để chạy trên GPU.
    """
    try:
        import onnx
    except ImportError:
        print("  BỎ QUA: cần `pip install onnx` (có sẵn trong requirements-gpu.txt).")
        return None

    import tempfile

    import onnxruntime as ort

    session = get_session(cfg.rembg_model, cfg.onnx_providers)
    model = onnx.load(str(type(session).download_models()))
    model.graph.input[0].type.tensor_type.shape.dim[0].dim_param = "N"
    for out in model.graph.output:
        out.type.tensor_type.shape.dim[0].dim_param = "N"

    with tempfile.TemporaryDirectory() as tmp:
        patched = os.path.join(tmp, "dyn.onnx")
        onnx.save(model, patched, save_as_external_data=False)
        sess = ort.InferenceSession(patched, providers=session.inner_session.get_providers())
        name = sess.get_inputs()[0].name

        per_image = {}
        for n in sizes:
            x = np.random.rand(n, 3, 320, 320).astype(np.float32)
            sess.run(None, {name: x})  # làm nóng
            runs = [_timed(sess, name, x) for _ in range(5)]
            d = statistics.median(runs)
            per_image[n] = d / n
            print(f"  batch={n:3d}  {d * 1000:7.1f} ms tổng  {d / n * 1000:7.2f} ms/ảnh")
    return per_image


def _timed(sess, name, x):
    t = time.perf_counter()
    sess.run(None, {name: x})
    return time.perf_counter() - t


def bench_http(url, blobs, levels):
    """Đo API thật: kèm multipart, mã hoá PNG, và hàng đợi của server.

    Khác `scan_qc()` trực tiếp ở chỗ nó bao gồm cả `MAX_CONCURRENCY` — nếu con số ở
    đây thấp hơn hẳn mục SONG SONG thì thủ phạm thường là biến môi trường đó.
    """
    import threading
    import urllib.error
    import urllib.request

    def post(blob):
        body = (
            b'--X\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\n\r\n'
            + blob
            + b"\r\n--X--\r\n"
        )
        req = urllib.request.Request(
            url.rstrip("/") + "/",
            data=body,
            headers={"Content-Type": "multipart/form-data; boundary=X"},
        )
        try:
            urllib.request.urlopen(req, timeout=300).read()
        except urllib.error.HTTPError as exc:
            exc.read()  # 422 = ảnh bị fail, vẫn là một request hoàn tất

    post(blobs[0])  # làm nóng
    for n in levels:
        t = time.perf_counter()
        threads = [
            threading.Thread(target=post, args=(blobs[i % len(blobs)],)) for i in range(n)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        d = time.perf_counter() - t
        print(
            f"  {n:3d} request song song  {d:6.2f}s  "
            f"{d / n * 1000:7.1f} ms/req  {n / d:6.2f} req/s"
        )


def ccu_table(rate):
    """Đổi ảnh/s thành số người dùng đồng thời — con số khách thật sự hỏi.

    "700 CCU" tự nó **chưa phải một yêu cầu về tải**: 700 người mỗi phút gửi một ảnh
    là 11.7 ảnh/s, còn 700 người gửi liên tục là hàng trăm ảnh/s. Chênh nhau hai bậc.
    Bảng này để chốt lại con số đó với khách trước khi thiết kế cho nó.
    """
    print(f"\n  Với {rate:.1f} ảnh/s mỗi tiến trình, một tiến trình gánh được:\n")
    print(f"  {'người dùng gửi 1 ảnh mỗi':32} {'CCU chịu được':>14}")
    for think in (5, 10, 30, 60, 120):
        print(f"  {think:>3}s{'':28} {rate * think:>14.0f}")
    print("\n  Cần 700 CCU thì tuỳ nhịp gửi mà số tiến trình cần là:\n")
    for think in (10, 30, 60):
        need = math.ceil(700 / think / rate)
        print(
            f"    mỗi {think:>3}s một ảnh → {700 / think:6.1f} ảnh/s "
            f"→ **{max(1, need)} tiến trình**"
        )
    print("\n  (Số tiến trình = số container. Mỗi container nạp một bản model riêng;")
    print("   u2net ~176MB nên nhiều tiến trình dùng chung một GPU là được về bộ nhớ.)")


# --------------------------------------------------------------------------- #


def main(argv=None):
    ap = argparse.ArgumentParser(description="Đo tốc độ qc-scanner trên máy đích.")
    ap.add_argument("--images", help="Thư mục ảnh thật. Không có thì tự sinh ảnh.")
    ap.add_argument("-n", "--count", type=int, default=16, help="Số ảnh dùng để đo.")
    ap.add_argument("--url", help="Đo thêm qua HTTP, ví dụ http://127.0.0.1:5000")
    ap.add_argument("--jobs", default="1,2,4,8,16", help="Các mức luồng cần quét.")
    ap.add_argument("--batch", default="1,2,4,8,16,32", help="Các cỡ batch cần quét.")
    ap.add_argument("--skip-batch", action="store_true")
    args = ap.parse_args(argv)

    cfg = Config.from_env()

    _hr("MÔI TRƯỜNG")
    print(f"  qc-scanner       {__version__}")
    print(f"  model            {cfg.rembg_model}")
    warmup(cfg.rembg_model, cfg.onnx_providers)
    providers = active_providers(cfg.rembg_model, cfg.onnx_providers)
    print(f"  providers        {providers}")
    if not any("CUDA" in p or "TensorRT" in p or "ROCM" in p for p in providers):
        print("  ⚠️  ĐANG CHẠY TRÊN CPU. Cài onnxruntime-gpu và đặt")
        print("      QC_SCANNER_ONNX_PROVIDERS=CUDAExecutionProvider,CPUExecutionProvider")
        print("      (onnxruntime tụt về CPU trong im lặng — đây là chỗ nhìn ra).")
    print(f"  CPU              {os.cpu_count()} nhân")
    concurrency = os.environ.get("QC_SCANNER_MAX_CONCURRENCY", "2")
    print(f"  MAX_CONCURRENCY  {concurrency} (chỉ ảnh hưởng đường HTTP)")

    blobs, source = load_images(args.images, args.count)
    sizes = [
        cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR).shape[:2] for b in blobs[:3]
    ]
    print(f"  ảnh thử          {source}, ví dụ {sizes}")

    _hr("CHẶNG — thời gian đi đâu")
    total, infer, cpu = bench_stages(blobs, cfg)

    _hr("SONG SONG — thông lượng một tiến trình")
    rate = bench_parallel(blobs, cfg, [int(j) for j in args.jobs.split(",")])

    if not args.skip_batch:
        _hr("BATCH — dynamic batching đáng bao nhiêu")
        per_image = bench_batch(cfg, [int(b) for b in args.batch.split(",")])
        if per_image:
            best_n = min(per_image, key=per_image.get)
            saved = per_image[1] - per_image[best_n]
            print(
                f"\n  Batch tốt nhất: {best_n} → "
                f"tiết kiệm {saved * 1000:.1f} ms/ảnh so với batch=1."
            )
            print(f"  Phần CPU mỗi ảnh (batching KHÔNG chạm tới): {cpu * 1000:.1f} ms.")
            gain = saved / total if total else 0
            print(f"  → Cải thiện tối đa cho cả pipeline: **{gain * 100:.1f}%**")
            if gain < 0.15:
                print("  → Chưa đáng làm. Nút cổ chai nằm ở phần CPU; nhân số tiến trình")
                print("    lên sẽ hiệu quả hơn nhiều mà không phải viết hàng đợi batching.")
            else:
                print("  → Đáng cân nhắc. Nhưng đọc kỹ ghi chú SPD-5 trước khi làm.")

    if args.url:
        _hr(f"HTTP — {args.url}")
        bench_http(args.url, blobs, [1, 2, 4, 8, 16, 32])

    _hr("QUY RA CCU")
    ccu_table(rate)
    print()


if __name__ == "__main__":
    main()
