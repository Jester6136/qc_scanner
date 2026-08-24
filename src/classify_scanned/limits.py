"""Hai van chặn tải, ở **một** chỗ duy nhất.

Tách thành module riêng vì cùng một lớp lỗi đã xảy ra hai lần, và cả hai lần đều là
một bản sao của con số `2` sống ở nơi khác:

1. `docker-compose.yml` ghi cứng `QC_SCANNER_MAX_CONCURRENCY: "2"` — số đo trên máy dev
   10 nhân lọt vào file bàn giao. Máy server 64 nhân chạy ở mức của máy 10 nhân, mất
   ~64% năng lực **trong im lặng**.
2. `bench.py` tự đọc lại biến môi trường với default `"2"` của riêng nó, nên báo cáo
   `MAX_CONCURRENCY 2` trong khi service thật đang chạy 16. Công cụ đo nói dối về
   chính thứ nó đang đo.

Cả hai đều không phải lỗi logic — chỉ là con số đúng bị chép ra nhiều bản rồi các bản
trôi khỏi nhau. Nên nay chỉ có một bản.

**Hai van, hai tài nguyên, không suy ra được từ nhau:**

| Van | Chặn | Vì sao riêng |
|---|---|---|
| `MAX_CONCURRENCY` | ảnh đang **xử lý** | bảo vệ CPU |
| `MAX_IN_FLIGHT` | request đang **trong RAM** | bảo vệ bộ nhớ (OPS-4) |

Van thứ hai không suy ra được từ van thứ nhất: thân request vào bộ nhớ **trước khi**
ai xin được suất xử lý, vì FastAPI phân tích multipart trước khi hàm xử lý chạy.
"""

import os


def default_concurrency() -> int:
    """Số ảnh xử lý cùng lúc, suy theo số nhân của **máy đích**.

    Vì sao phải chặn thay vì thả threadpool 40 luồng của Starlette chạy thoải mái:
    phần nặng là onnxruntime, và thả tự do thì không tăng thông lượng mà chỉ làm mọi
    request cùng chậm và ngốn 40 × ảnh RAM. Chặn lại thì request thứ N+1 **xếp hàng** —
    chậm nhưng đoán được.

    Nhưng "onnxruntime đã dùng hết nhân" chỉ đúng một nửa, và số đo trên máy 64 nhân
    nói rõ nửa còn lại — `scan_qc` trực tiếp:

        jobs= 1  1.73 ảnh/s     jobs= 4  4.16 ảnh/s     jobs=16  7.64 ảnh/s
        jobs= 2  2.84 ảnh/s     jobs= 8  5.80 ảnh/s

    Tăng 4.4x từ 1 lên 16 luồng, và **vẫn chưa bão hoà ở 16**. Một lần suy luận không
    hề dùng hết 64 nhân.

    Quy tắc `cpu/4`, chặn trong [2, 32] — khớp cả hai điểm đã đo:

    * 10 nhân → **2**, đúng mức tốt nhất trên máy dev (37 ảnh: 1→14.2s · **2→11.8s** ·
      3→12.0s · 4→12.7s);
    * 64 nhân → **16**, mức cao nhất đo được trên máy server.

    Trần cũ là 16 với lý do "mỗi ảnh đang xử lý giữ tới 32MB". Lý do đó không đứng
    được: máy server có 231 GB RAM, 16 × 32MB = 512MB. Trần bộ nhớ nay là
    `MAX_IN_FLIGHT`, đúng chỗ của nó; trần ở đây chỉ còn chặn ca bệnh lý.
    """
    return max(2, min(32, (os.cpu_count() or 4) // 4))


#: ⚠️ Đây là giá trị **tự suy theo máy đích**. Đặt `QC_SCANNER_MAX_CONCURRENCY` là vô
#: hiệu hoá nó hoàn toàn — đừng ghi biến đó vào file dùng chung; cần ép tay thì đặt
#: lúc chạy.
MAX_CONCURRENCY = max(
    1, int(os.environ.get("QC_SCANNER_MAX_CONCURRENCY") or default_concurrency())
)

#: Trần **request đang bay** — đã nhận nhưng chưa trả lời xong.
#:
#: Sinh ra để chặn *bộ nhớ* (OPS-4): đo trước khi có nó, `MAX_CONCURRENCY=2` với 24
#: client gọi cùng lúc cho đúng 2 request đang xử lý nhưng **24 thân request trong
#: RAM**. Van hoạt động đúng — bắn 200 request vào máy server, nhận đúng 64 `200` và
#: 136 `503`, không rò một suất nào.
#:
#: **Nhưng bộ nhớ hoá ra không phải thứ quyết định con số này.** Máy server có 231 GB;
#: kể cả `MAX_IN_FLIGHT=64` thì trần RAM chỉ 2 GB. Thứ quyết định là **thời gian chờ**:
#: request cuối hàng đợi chờ `MAX_IN_FLIGHT / thông lượng` giây trước khi được đụng tới.
#:
#: Đo trên máy 64 nhân (đỉnh 8.43 req/s, đạt được từ mức **32** request song song):
#:
#:     MAX_IN_FLIGHT   chờ tệ nhất   thêm thông lượng?
#:                16         1.9s    có
#:                32         3.8s    có
#:                64         7.6s    KHÔNG — đỉnh đã đạt ở 32
#:               128        15.2s    KHÔNG
#:
#: Nhận quá mức đạt đỉnh là **thêm thời gian chờ mà không thêm một req/s nào**. Nên
#: `× 2` chứ không `× 4`: vẫn còn hàng đợi thật để nuốt một đợt dồn ngắn, nhưng chờ
#: tệ nhất ~3.8s thay vì 7.6s. Với luồng realtime (người vừa chụp đang đứng chờ) thì
#: nhận `503` ngay rồi thử lại còn hơn chờ 7.6s rồi mới biết, và [EX-3] chốt là có cả
#: luồng realtime.
#:
#: Không có van này thì trần là threadpool của Starlette: 40 × 32MB = 1.28 GB, một con
#: số không ai cố ý chọn.
MAX_IN_FLIGHT = max(
    1, int(os.environ.get("QC_SCANNER_MAX_IN_FLIGHT") or MAX_CONCURRENCY * 2)
)
