# Cần trao đổi / làm rõ với khách hàng

> Nơi ghi các điểm **cần dựa vào tài liệu / dữ liệu khách hàng cung cấp** để đặt câu hỏi và làm
> rõ trước khi quyết định thiết kế/nghiệm thu. Mỗi mục: **câu hỏi**, **vì sao cần**, **ảnh hưởng
> nếu chưa rõ**, **trạng thái** (❓ chờ hỏi · 💬 đã hỏi chờ trả lời · ✅ đã chốt).
>
> Bối cảnh: qc_scanner đang chuyển từ "hàm crop" sang **cổng QC** — không crop được thì phải nói rõ
> nguyên nhân + hướng xử lý ([overall_roadmap.md §1](overall_roadmap.md)). Phần lớn câu hỏi dưới
> đây tồn tại vì **QC chỉ định nghĩa được khi biết "đạt" nghĩa là gì với khách**.
>
> ⚠️ Cập nhật 2026-08-05: đã nhận **9 ảnh thật đầu tiên** (trong `tmp/`, không commit) — đủ để
> hiệu chỉnh hai ngưỡng bằng số đo và để so hai cấu hình với nhau, nhưng **chưa có nhãn** nên
> chưa chấm được đúng/sai. Các ngưỡng còn lại trong `algorithm.md §7` vẫn là **ước đoán**.
>
> **EX-2 (tập vàng có nhãn) nay là mục chặn nhiều việc nhất**: toàn bộ Giai đoạn 3 còn lại
> (QUAL-3 quét ngưỡng, S-1 đổi model, S-3 DocAligner) đang đứng chờ đúng một thứ này. Công cụ
> đo đã dựng xong và chạy được (`python -m qc_scanner.eval --labels`).

---

## A. Dữ liệu & bối cảnh sử dụng

### EX-1 · ❓ "Đạt" nghĩa là gì — tiêu chí nghiệm thu một ảnh
- **Hỏi**: Ảnh đầu ra thế nào thì khách coi là **đạt**? Được phép mất bao nhiêu mép giấy? Có
  bắt buộc thấy trọn 4 góc không? Nghiêng bao nhiêu độ thì vẫn chấp nhận? DPI tối thiểu?
- **Vì sao**: đây là **định nghĩa của toàn bộ hệ QC**. Mọi ngưỡng trong
  [algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes) (`TOO_SMALL` 0.20,
  `EXTREME_SKEW` 1.8, `LOW_RESOLUTION` 150 DPI) hiện là con số **ta tự đặt**.
- **Nếu chưa rõ**: chấm điểm theo chuẩn của mình, nghiệm thu theo chuẩn của khách → lệch.

### EX-2 · ❓ Tập ảnh thật + tập vàng có nhãn
- **Hỏi**: Xin **≥100 ảnh thật** đại diện, trong đó **≥30% là ca xấu** (mờ, nghiêng, nền lẫn,
  thiếu góc, nhiều tờ, lóa sáng). Khách gán nhãn được không, hay ta gán rồi khách duyệt?
- **Vì sao**: `examples/` là ảnh OSS, **không đại diện**. Không có tập vàng thì (a) không chứng
  minh được chất lượng lúc nghiệm thu, (b) **không dám đổi thuật toán** — kể cả nâng cấp rõ
  ràng như [S-1/S-3](features_issues.md#s-docaligner) cũng thành đánh bạc.
- **Nếu chưa rõ**: mọi con số trong `test_eval.md §5` không có đầu vào để chạy. **Đây là mục
  chặn nhiều việc nhất — ưu tiên hỏi trước tiên.**

### EX-3 · ❓ Ảnh vào từ đâu, đi đi đâu
- **Hỏi**: Nguồn ảnh là gì — chụp điện thoại tại chỗ, máy scan, hay ảnh tồn kho đã chụp sẵn?
  Đầu ra qc_scanner đi tiếp vào hệ nào (OCR/VLM nào, hay người đọc)? Có cần **PDF/đa trang** không?
- **Vì sao**: quyết định `audience` của mỗi reason code. Nếu người chụp **có mặt tại chỗ** →
  hint "chụp lại trên nền tối" là hành động được ngay, QC cực kỳ giá trị. Nếu là **ảnh tồn
  kho** → không ai chụp lại được, mọi hint phải chuyển sang vận hành (loại bỏ / xử lý tay).
- **Nếu chưa rõ**: viết hint sai đối tượng → QC ra thông điệp không ai làm gì được.

### EX-4 · ❓ Loại tài liệu & đặc điểm giấy
- **Hỏi**: Loại giấy tờ nào (sổ đỏ, CMND/CCCD, hoá đơn, biểu mẫu A4…)? Khổ cố định hay đa dạng?
  Giấy **màu** hay trắng? Có **khung viền in sẵn / bảng kẻ** không?
- **Vì sao**: (a) `est_dpi` hiện giả định khổ A4 — sai khổ thì sai ngưỡng; (b) tài liệu có
  **khung viền** làm contour bắt nhầm đường kẻ trong tài liệu thay vì mép giấy
  ([QUAL-1](features_issues.md#qual-quad-filter)); (c) giấy trắng cần nền tối để rembg tách được.
- **🔥 Đã thành vấn đề thật, không còn là giả định**: ngưỡng `LOW_RESOLUTION` theo DPI-A4 loại
  nhầm **15/17** ảnh đã thử — toàn giấy tờ khổ nhỏ đọc tốt. Đã phải bỏ chốt chặn theo DPI và
  chuyển sang số pixel cạnh dài. **Biết khổ giấy thật thì lấy lại được chốt chặn DPI**, vốn
  đúng hơn về mặt OCR. Đây là câu hỏi rẻ mà đổi được chất lượng phán quyết.

### EX-5 · ❓ Giấy có **cong/gập** không (quyết định có cần dewarping)
- **Hỏi**: Tài liệu được ép phẳng khi chụp, hay có nếp gấp / cong / đóng gáy (sổ, quyển)?
  Xin vài ảnh ví dụ ca cong nhất.
- **Vì sao**: `four_point_transform` chỉ sửa được biến dạng **phẳng**. Nếu giấy cong, ảnh sau
  nắn **vẫn méo** → OCR vẫn sai, và ta cần cả một họ công nghệ khác (dewarping — UVDoc/DocTr++,
  [S-5](features_issues.md#s-dewarp)), đắt hơn nhiều.
- **Nếu chưa rõ**: hoặc làm thừa (đầu tư dewarping không ai cần), hoặc thiếu (nghiệm thu mới
  phát hiện cả nhóm ảnh không bao giờ đạt).

## B. Chính sách QC

### EX-6 · ❓ Ảnh **không đạt** thì quy trình xử lý ra sao
- **Hỏi**: Khi qc_scanner báo `fail` — ai nhận thông báo? Chụp lại được không? Hay chuyển sang xử
  lý tay? Có hàng đợi/người phụ trách không? Ngưỡng bao nhiêu % fail thì coi là sự cố?
- **Vì sao**: quyết định hình thức đầu ra QC — chỉ cần exit code, hay cần **báo cáo CSV hàng
  loạt** ([N-01](features_issues.md#f-features--đề-xuất-backlog)), hay cần webhook/UI.
- **Nếu chưa rõ**: làm ra QC không ai tiêu thụ được.

### EX-7 · ❓ Cân bằng **false pass** vs **false fail**
- **Hỏi**: Khách sợ cái nào hơn — ảnh xấu lọt qua rồi sinh dữ liệu sai (*false pass*), hay ảnh
  dùng được bị bắt làm lại (*false fail*)? Chi phí mỗi bên ước chừng ra sao?
- **Vì sao**: mọi ngưỡng QC là một điểm đánh đổi trên đường cong này. Giả định làm việc hiện
  tại của ta: **false pass tệ hơn nhiều** (false pass ≤1%, false fail ≤10% —
  [test_eval.md §5](test_eval.md)). **Cần khách xác nhận.**
- **Nếu chưa rõ**: siết/nới ngưỡng theo cảm tính, cãi nhau lúc nghiệm thu.

### EX-8 · ❓ Ảnh `warn` thì được dùng hay phải soi
- **Hỏi**: Với ảnh "dùng được nhưng có rủi ro" (`CLIPPED_EDGE`, `EXTREME_SKEW`,
  `RECOVERED_BY_EDGE_FALLBACK`) — khách muốn tự động cho qua, hay bắt buộc người soi mắt thường?
- **Vì sao**: quyết định `warn` là **cảnh báo** hay thực chất là **chặn**; ảnh hưởng thẳng tới
  khối lượng công việc vận hành.

### EX-9 · ❓ Thông điệp QC bằng ngôn ngữ nào, cho ai đọc
- **Hỏi**: `hint` hiển thị cho ai — người dùng cuối (cần tiếng Việt, giọng hướng dẫn) hay kỹ sư
  tích hợp (cần mã ổn định + tài liệu)? Có cần đa ngôn ngữ không?
- **Vì sao**: mã (`code`) phải **ổn định vĩnh viễn** vì đi vào log/CSV; còn `message`/`hint` có
  thể dịch. Cần chốt sớm để không phải đổi mã về sau.

## C. Vận hành & phi chức năng

### EX-10 · ❓ Quy mô, tốc độ, hình thức triển khai
- **Hỏi**: Bao nhiêu ảnh/ngày? Xử lý **theo lô** hay **thời gian thực** lúc người dùng chụp?
  Chạy ở đâu — server nội bộ (CPU/GPU gì), Docker, hay nhúng vào ứng dụng di động?
- **Vì sao**: rembg (CPU) hiện chiếm ~95% thời gian. Nếu cần realtime trên di động thì hướng
  [S-3 (hồi quy 4 góc, mobile-friendly)](features_issues.md#s-docaligner) không còn là "nên
  làm" mà là **bắt buộc**. Cũng quyết định có cần GPU / Dockerfile / pre-warm model.

### EX-11 · ❓ Môi trường có mạng không (rembg tải model lần đầu)
- **Hỏi**: Máy chạy có ra được Internet không? Có cho phép tải model lần đầu (vài chục MB) không?
- **Vì sao**: rembg tải weight về `~/.u2net/` ở lần chạy đầu. Môi trường **air-gapped** sẽ chết
  ngay, phải nướng model sẵn vào Docker image ([N-04](features_issues.md#f-features--đề-xuất-backlog)).

### EX-12 · ❓ Bảo mật & lưu trữ ảnh tài liệu
- **Hỏi**: Ảnh chứa thông tin cá nhân (CMND/CCCD, địa chỉ, chữ ký)? Được lưu tạm không, bao lâu?
  HTTP server sẽ đặt ở mạng nội bộ hay public? Có yêu cầu xác thực?
- **Vì sao**: SSRF ([SEC-1](features_issues.md#sec-ssrf)) **đã vá** — nhánh `GET /?url=` bị bỏ
  hẳn, và bind mặc định chuyển về `127.0.0.1`. Nhưng server vẫn **không có xác thực**: nếu
  khách định đặt nó ở mạng có thể truy cập được từ ngoài thì cần thêm một lớp xác thực, và đó
  là việc chưa nằm trong roadmap.

### EX-13 · ❓ Giấy phép & phân phối
- **Hỏi**: Sản phẩm giao cho khách dưới dạng nào — thư viện PyPI, Docker image, hay mã nguồn?
  Có ràng buộc giấy phép nào không?
- **Vì sao**: qc_scanner là MIT (fork OSS), nhưng model đi kèm có giấy phép riêng — U²-Net và
  BiRefNet **không cùng điều khoản**; DocAligner là Apache-2.0. Đổi model
  ([S-1](features_issues.md#s-model-swap)) có thể kéo theo ràng buộc giấy phép mới, **kiểm
  trước khi chốt**.

---

## Cách dùng file này
- Trước mỗi buổi làm việc với khách: lọc mục ❓, chuẩn bị câu hỏi + **tài liệu/dữ liệu cần xin**.
- Ưu tiên hỏi trước: **EX-2** (tập vàng — nay là thứ chặn *toàn bộ* phần còn lại), **EX-4**
  (khổ giấy — đã thành vấn đề thật, xem trên), **EX-1** (định nghĩa "đạt"), **EX-7** (cân bằng
  false pass/fail), **EX-5** (có cần dewarping không).
- Sau khi có câu trả lời: đổi trạng thái ✅ + ghi **quyết định đã chốt** (kèm ngày, nguồn tài liệu).
- Quyết định chốt mà ảnh hưởng code → tạo issue/feature tương ứng trong
  [features_issues.md](features_issues.md); nếu chốt một **ngưỡng**, ghi thẳng vào
  [algorithm.md §7](algorithm.md#7--danh-mục-mã-lý-do-reason-codes) kèm nguồn.
