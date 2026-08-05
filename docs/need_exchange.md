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

### EX-1 · ✅ "Đạt" nghĩa là gì — tiêu chí nghiệm thu một ảnh

> **✅ Chốt 2026-08-05**: **Mất viền trắng thì chấp nhận, mất CHỮ thì không.** Ngưỡng không nằm ở hình học tờ giấy mà ở nội dung: `CLIPPED_EDGE` giữ mức `warn`, nhưng phải thêm phép kiểm *có pixel chữ nào chạm mép cắt không* — có thì `fail`.
- **Hỏi**: Ảnh đầu ra thế nào thì khách coi là **đạt**? Được phép mất bao nhiêu mép giấy? Có
  bắt buộc thấy trọn 4 góc không? Nghiêng bao nhiêu độ thì vẫn chấp nhận? DPI tối thiểu?
- **Vì sao**: đây là **định nghĩa của toàn bộ hệ QC**. Mọi ngưỡng trong
  [algorithm.md §7](algorithm.md#ma-ly-do) (`TOO_SMALL` 0.20,
  `EXTREME_SKEW` 1.8, `LOW_RESOLUTION` 150 DPI) hiện là con số **ta tự đặt**.
- **Nếu chưa rõ**: chấm điểm theo chuẩn của mình, nghiệm thu theo chuẩn của khách → lệch.

### EX-2 · ✅ Tập ảnh thật + tập vàng có nhãn

> **✅ Chốt 2026-08-05**: **Khách cấp ảnh, bên làm gán nhãn, khách duyệt.** Cần ≥100 ảnh, ≥30% là ca xấu. Việc tiếp theo: dựng công cụ hỗ trợ gán nhãn + quy trình duyệt. **Đang chờ ảnh.**
- **Hỏi**: Xin **≥100 ảnh thật** đại diện, trong đó **≥30% là ca xấu** (mờ, nghiêng, nền lẫn,
  thiếu góc, nhiều tờ, lóa sáng). Khách gán nhãn được không, hay ta gán rồi khách duyệt?
- **Vì sao**: `examples/` là ảnh OSS, **không đại diện**. Không có tập vàng thì (a) không chứng
  minh được chất lượng lúc nghiệm thu, (b) **không dám đổi thuật toán** — kể cả nâng cấp rõ
  ràng như [S-1/S-3](features_issues.md#s-docaligner) cũng thành đánh bạc.
- **Nếu chưa rõ**: mọi con số trong `test_eval.md §5` không có đầu vào để chạy. **Đây là mục
  chặn nhiều việc nhất — ưu tiên hỏi trước tiên.**

### EX-3 · ✅ Ảnh vào từ đâu, đi đi đâu {#ex-3}

> **✅ Chốt 2026-08-05**: **Cả hai luồng**: batch cho kho ảnh cũ (không chụp lại được) + realtime cho ảnh chụp mới (chụp lại được). Hệ quả: mỗi mã lý do cần **hai tầng hint** — một cho người chụp, một cho vận hành — chứ không phải một `audience` duy nhất như hiện nay.
- **Hỏi**: Nguồn ảnh là gì — chụp điện thoại tại chỗ, máy scan, hay ảnh tồn kho đã chụp sẵn?
  Đầu ra qc_scanner đi tiếp vào hệ nào (OCR/VLM nào, hay người đọc)? Có cần **PDF/đa trang** không?
- **Vì sao**: quyết định `audience` của mỗi reason code. Nếu người chụp **có mặt tại chỗ** →
  hint "chụp lại trên nền tối" là hành động được ngay, QC cực kỳ giá trị. Nếu là **ảnh tồn
  kho** → không ai chụp lại được, mọi hint phải chuyển sang vận hành (loại bỏ / xử lý tay).
- **Nếu chưa rõ**: viết hint sai đối tượng → QC ra thông điệp không ai làm gì được.

### EX-4 · ✅ Loại tài liệu & đặc điểm giấy

> **✅ Chốt 2026-08-05**: **Cả bốn loại**: sổ đỏ/GCN · hoá đơn (khổ dài hẹp) · CCCD (khổ thẻ) · biểu mẫu A4. Khổ giấy **không đồng nhất** → không lấy lại được chốt chặn DPI toàn cục; giữ chốt theo số pixel. Có thể thêm tham số `--paper-size` tuỳ chọn cho luồng biết trước loại. Hoá đơn giấy trắng là **ca hỏng chính**, không phải ngoại lệ.
- **Hỏi**: Loại giấy tờ nào (sổ đỏ, CMND/CCCD, hoá đơn, biểu mẫu A4…)? Khổ cố định hay đa dạng?
  Giấy **màu** hay trắng? Có **khung viền in sẵn / bảng kẻ** không?
- **Vì sao**: (a) `est_dpi` hiện giả định khổ A4 — sai khổ thì sai ngưỡng; (b) tài liệu có
  **khung viền** làm contour bắt nhầm đường kẻ trong tài liệu thay vì mép giấy
  ([QUAL-1](features_issues.md#qual-quad-filter)); (c) giấy trắng cần nền tối để rembg tách được.
- **🔥 Đã thành vấn đề thật, không còn là giả định**: ngưỡng `LOW_RESOLUTION` theo DPI-A4 loại
  nhầm **15/17** ảnh đã thử — toàn giấy tờ khổ nhỏ đọc tốt. Đã phải bỏ chốt chặn theo DPI và
  chuyển sang số pixel cạnh dài. **Biết khổ giấy thật thì lấy lại được chốt chặn DPI**, vốn
  đúng hơn về mặt OCR. Đây là câu hỏi rẻ mà đổi được chất lượng phán quyết.

### EX-5 · ✅ Giấy có cong/gập không

> **✅ Chốt 2026-08-05**: **Có — hoá đơn thường cong/nhăn.** Đây là thay đổi phạm vi lớn nhất từ đợt trao đổi này: `four_point_transform` chỉ sửa được biến dạng phẳng, nên nhóm hoá đơn cong sẽ **vẫn méo sau khi nắn**. S-5 (dewarping) chuyển từ "chờ chốt" sang **trong phạm vi**. Nhưng đắt (1 tuần+) → đo mức độ cong trên tập ảnh thật trước khi cam kết.
- **Hỏi**: Tài liệu được ép phẳng khi chụp, hay có nếp gấp / cong / đóng gáy (sổ, quyển)?
  Xin vài ảnh ví dụ ca cong nhất.
- **Vì sao**: `four_point_transform` chỉ sửa được biến dạng **phẳng**. Nếu giấy cong, ảnh sau
  nắn **vẫn méo** → OCR vẫn sai, và ta cần cả một họ công nghệ khác (dewarping — UVDoc/DocTr++,
  [S-5](features_issues.md#s-dewarp)), đắt hơn nhiều.
- **Nếu chưa rõ**: hoặc làm thừa (đầu tư dewarping không ai cần), hoặc thiếu (nghiệm thu mới
  phát hiện cả nhóm ảnh không bao giờ đạt).

## B. Chính sách QC

### EX-6 · ✅ Ảnh không đạt thì quy trình xử lý ra sao

> **✅ Chốt 2026-08-05**: Ảnh `warn` **vào hàng chờ người soi** (không tự động cho qua). Ảnh `fail`: luồng realtime thì báo người chụp chụp lại; luồng kho thì đẩy sang xử lý tay. Báo cáo CSV của `qc-scanner-batch` là đầu vào cho hàng chờ này.
- **Hỏi**: Khi qc_scanner báo `fail` — ai nhận thông báo? Chụp lại được không? Hay chuyển sang xử
  lý tay? Có hàng đợi/người phụ trách không? Ngưỡng bao nhiêu % fail thì coi là sự cố?
- **Vì sao**: quyết định hình thức đầu ra QC — chỉ cần exit code, hay cần **báo cáo CSV hàng
  loạt** ([N-01](features_issues.md#f-features--đề-xuất-backlog)), hay cần webhook/UI.
- **Nếu chưa rõ**: làm ra QC không ai tiêu thụ được.

### EX-7 · ✅ Cân bằng false pass vs false fail {#ex-7}

> **✅ Chốt 2026-08-05**: **Cân bằng, không bên nào trội.** Khác giả định đang dùng (false pass ≤1% / false fail ≤10%). Ngưỡng phải tối ưu **tổng số lỗi** thay vì siết một chiều — và chỉ chốt được khi có tập vàng (EX-2).
- **Hỏi**: Khách sợ cái nào hơn — ảnh xấu lọt qua rồi sinh dữ liệu sai (*false pass*), hay ảnh
  dùng được bị bắt làm lại (*false fail*)? Chi phí mỗi bên ước chừng ra sao?
- **Vì sao**: mọi ngưỡng QC là một điểm đánh đổi trên đường cong này. Giả định làm việc hiện
  tại của ta: **false pass tệ hơn nhiều** (false pass ≤1%, false fail ≤10% —
  [test_eval.md §5](test_eval.md)). **Cần khách xác nhận.**
- **Nếu chưa rõ**: siết/nới ngưỡng theo cảm tính, cãi nhau lúc nghiệm thu.

### EX-8 · ✅ Ảnh warn thì được dùng hay phải soi

> **✅ Chốt 2026-08-05**: **Phải soi.** `warn` là cảnh báo cho người, không phải nhãn cho máy bỏ qua. Củng cố lý do cần tách `NO_CROP_DETECTED` ra mức `fail`: hiện có ca crop sai hoàn toàn mà vẫn chỉ ra `warn`.
- **Hỏi**: Với ảnh "dùng được nhưng có rủi ro" (`CLIPPED_EDGE`, `EXTREME_SKEW`,
  `RECOVERED_BY_EDGE_FALLBACK`) — khách muốn tự động cho qua, hay bắt buộc người soi mắt thường?
- **Vì sao**: quyết định `warn` là **cảnh báo** hay thực chất là **chặn**; ảnh hưởng thẳng tới
  khối lượng công việc vận hành.

### EX-9 · 🟡 Thông điệp QC bằng ngôn ngữ nào, cho ai đọc

> **✅ Chốt 2026-08-05**: Suy ra một phần từ EX-3: cần hint cho **cả** người chụp lẫn vận hành. Chưa hỏi: có cần đa ngôn ngữ không. Mã (`code`) giữ nguyên tiếng Anh viết HOA, ổn định vĩnh viễn.
- **Hỏi**: `hint` hiển thị cho ai — người dùng cuối (cần tiếng Việt, giọng hướng dẫn) hay kỹ sư
  tích hợp (cần mã ổn định + tài liệu)? Có cần đa ngôn ngữ không?
- **Vì sao**: mã (`code`) phải **ổn định vĩnh viễn** vì đi vào log/CSV; còn `message`/`hint` có
  thể dịch. Cần chốt sớm để không phải đổi mã về sau.

## C. Vận hành & phi chức năng

### EX-10 · ✅ Quy mô, tốc độ, hình thức triển khai

> **✅ Chốt 2026-08-05**: Batch + realtime, **ngân sách độ trễ < 1s/ảnh**. Hiện đạt **~0.4s/ảnh** trên CPU sau khi nạp sẵn model → **không cần đổi thuật toán vì tốc độ**, không cần GPU. Đây là lý do S-3 (DocAligner) vẫn chỉ là "nên làm" chứ chưa bắt buộc.
- **Hỏi**: Bao nhiêu ảnh/ngày? Xử lý **theo lô** hay **thời gian thực** lúc người dùng chụp?
  Chạy ở đâu — server nội bộ (CPU/GPU gì), Docker, hay nhúng vào ứng dụng di động?
- **Vì sao**: rembg (CPU) hiện chiếm ~95% thời gian. Nếu cần realtime trên di động thì hướng
  [S-3 (hồi quy 4 góc, mobile-friendly)](features_issues.md#s-docaligner) không còn là "nên
  làm" mà là **bắt buộc**. Cũng quyết định có cần GPU / Dockerfile / pre-warm model.

### EX-11 · ✅ Môi trường có mạng không

> **✅ Chốt 2026-08-05**: Giao bằng **Docker image có nướng sẵn model** → câu hỏi này không còn chặn: image chạy được cả khi máy đích không ra Internet.
- **Hỏi**: Máy chạy có ra được Internet không? Có cho phép tải model lần đầu (vài chục MB) không?
- **Vì sao**: rembg tải weight về `~/.u2net/` ở lần chạy đầu. Môi trường **air-gapped** sẽ chết
  ngay, phải nướng model sẵn vào Docker image ([N-04](features_issues.md#f-features--đề-xuất-backlog)).

### EX-12 · ✅ Bảo mật & lưu trữ ảnh tài liệu

> **✅ Chốt 2026-08-05**: **Mạng nội bộ, không lưu ảnh.** Khớp với thiết kế hiện tại: server xử lý trong RAM, không ghi đĩa. SSRF đã vá. **Vẫn cần ghi rõ trong tài liệu vận hành**: server không có xác thực, nên đừng để lộ ra ngoài mạng nội bộ.
- **Hỏi**: Ảnh chứa thông tin cá nhân (CMND/CCCD, địa chỉ, chữ ký)? Được lưu tạm không, bao lâu?
  HTTP server sẽ đặt ở mạng nội bộ hay public? Có yêu cầu xác thực?
- **Vì sao**: SSRF ([SEC-1](features_issues.md#sec-ssrf)) **đã vá** — nhánh `GET /?url=` bị bỏ
  hẳn, và bind mặc định chuyển về `127.0.0.1`. Nhưng server vẫn **không có xác thực**: nếu
  khách định đặt nó ở mạng có thể truy cập được từ ngoài thì cần thêm một lớp xác thực, và đó
  là việc chưa nằm trong roadmap.

### EX-13 · ✅ Giấy phép & phân phối {#ex-13}

> **✅ Chốt 2026-08-05**: **Docker image, và bên trong có sẵn HTTP service để hệ khác gọi vào** (`qc-scanner-server`, đã là CMD mặc định của image). Nghĩa là bàn giao một thứ duy nhất: `docker run -p 5000:5000 qc-scanner` là hệ khác gọi được ngay. Kèm theo đó, hợp đồng API (`POST /`, `?format=json`, header verdict, HTTP status theo verdict) trở thành **bề mặt bàn giao chính**, không còn là tiện ích phụ — phải có tài liệu API và test hợp đồng. Kiểm giấy phép model trước khi chốt: U²-Net (mặc định hiện tại) khác điều khoản với BiRefNet; DocAligner là Apache-2.0. Đổi model kéo theo ràng buộc giấy phép mới → kiểm trước khi đổi.
- **Hỏi**: Sản phẩm giao cho khách dưới dạng nào — thư viện PyPI, Docker image, hay mã nguồn?
  Có ràng buộc giấy phép nào không?
- **Vì sao**: qc_scanner là MIT (fork OSS), nhưng model đi kèm có giấy phép riêng — U²-Net và
  BiRefNet **không cùng điều khoản**; DocAligner là Apache-2.0. Đổi model
  ([S-1](features_issues.md#s-model-swap)) có thể kéo theo ràng buộc giấy phép mới, **kiểm
  trước khi chốt**.

### EX-14 · ✅ Ảnh tồn kho là ảnh CHỤP THÔ hay ảnh ĐÃ CẮT SẴN? {#ex-precropped}

*(Mở 2026-08-05, phát sinh khi làm [QC-12](features_issues.md#qc-content-clipped).)*

> **✅ Chốt 2026-08-05**: **có cả ảnh đã cắt sẵn** truyền vào. Đã cài cờ `pre_cropped`
> ([QC-14](features_issues.md#qc-precropped)) — phía gọi khai báo, hệ thống **không tự đoán**
> (đo 37 ảnh: `alpha_coverage` của hai nhóm trùng dải gần như hoàn toàn, không tách được).
>
> **Việc còn lại thuộc phía tích hợp**: hệ gọi phải biết ảnh nào đã cắt để đặt cờ. Nếu kho ảnh
> không có thông tin đó thì phải chọn một mặc định cho cả kho — và chọn "đã cắt" nghĩa là chấp
> nhận qc_scanner không bắt được crop hụt trên các ảnh chụp thô lẫn trong đó.

### EX-15 · ❓ Một hồ sơ gồm NHIỀU ảnh — ai chịu trách nhiệm ghép và kiểm đủ? {#ex-multipage}

*(Mở 2026-08-05, từ ảnh đợt 2: giấy chứng nhận quyền sử dụng đất chụp **từng mặt một**, mỗi mặt
là một ảnh riêng và **cả hai mặt đều có thông tin**.)*

- **Hỏi**: Ai ghép các ảnh của cùng một hồ sơ lại, và ai kiểm "hồ sơ này đã đủ mặt chưa"?
  Hệ gọi đã có mã hồ sơ / thứ tự trang khi gửi ảnh chưa?
- **Đề xuất trả lời**: **hệ gọi giữ việc này**, qc_scanner không đụng vào.
- **Vì sao**:
  1. Chụp từng mặt là **cách chụp đúng**, không phải lỗi. Bắt chụp lại là vô nghĩa — chụp lại
     vẫn ra hai ảnh. Xem quyết định dưới đây.
  2. qc_scanner **không có state**: mỗi lần gọi là một ảnh, không có khái niệm "hồ sơ". Thêm nó
     là thêm phiên/hàng đợi/định danh — đổi hẳn kiến trúc, phá
     [nguyên tắc §3.1](overall_roadmap.md).
  3. Muốn biết "đủ mặt chưa" phải biết **loại giấy tờ** có mấy mặt. Đó là tri thức nghiệp vụ
     của hệ gọi, không suy ra được từ một tấm ảnh.

> **✅ Quyết định 2026-08-05 (bên làm đề xuất, chờ khách xác nhận)**: **KHÔNG bắt chụp lại.**
> Giấy chứng nhận chụp hai mặt thành hai ảnh là hợp lệ; qc_scanner chấm **từng ảnh** như bình
> thường, mỗi mặt nhận verdict riêng. Việc kiểm "hồ sơ đủ 2 mặt chưa" là kiểm ở **mức bản ghi**,
> nằm ở hệ gọi.
>
> Đã kiểm trên ảnh thật đợt 2: ảnh chụp **cả tờ mở đôi** (hai nửa cùng khung, có nếp gấp giữa)
> không sinh mã lạ nào — không `MULTIPLE_DOCUMENTS`, `skew_ratio` 1.00–1.33. Nghĩa là dù khách
> chụp mở đôi hay chụp từng mặt, lõi QC đều xử lý được; khác biệt duy nhất là **khung hình có
> lấy trọn tờ giấy không**, và cái đó đã có mã lý do rồi.

- **Hỏi**: Trong phần "phần lớn tồn kho" ở [EX-3](#ex-3), ảnh là **ảnh chụp thô** (còn thấy mặt
  bàn quanh tờ giấy) hay đã qua một bước **cắt sát** nào đó rồi? Nếu có cả hai, phân biệt được
  từ metadata/thư mục không?
- **Đề xuất trả lời**: nếu không chắc, gửi ~20 ảnh lấy ngẫu nhiên từ kho là đủ để tự nhìn ra.
- **Vì sao**: `CONTENT_CLIPPED` bắt ca "có chữ chạy tới sát mép ảnh". Với ảnh **đã cắt sát**,
  chữ sát mép là chuyện bình thường — nhưng từ một tấm ảnh đơn lẻ thì **không phân biệt được**
  nó là bản cắt đẹp hay bản đã mất mất một dòng. Đo trên `examples/*.out.png` (ảnh đã cắt):
  `border_ink_ratio` 0.124–0.891, tức toàn bộ sẽ bị báo `fail`.
- **Ảnh hưởng nếu là ảnh đã cắt**: cần thêm bối cảnh đầu vào (`--pre-cropped` / một trường trong
  request) để tắt mã này cho luồng kho, thay vì để hệ thống đoán →
  [QC-14](features_issues.md#qc-precropped).

---

### EX-16 · ❓ "700 CCU" nghĩa là bao nhiêu ảnh mỗi giây? {#ex-throughput}

*(Mở 2026-08-05, từ trao đổi về dynamic batching.)*

- **Hỏi**: Con số 700 CCU là **700 người đang mở ứng dụng**, hay **700 ảnh đang được xử lý cùng
  lúc**? Mỗi người gửi ảnh cách nhau bao lâu — vài giây một lần, hay vài phút một lần? Có giờ
  cao điểm không, và cao gấp mấy lần trung bình?
- **Vì sao**: đây là chênh lệch **hai bậc độ lớn**, và nó quyết định kiến trúc chứ không chỉ
  quyết định cấu hình:

  | Cách hiểu | Tải thật | Hướng xử lý |
  |---|---|---|
  | 700 người, mỗi phút một ảnh | ~11.7 ảnh/s | Vài container sau một bộ cân bằng tải |
  | 700 người, mỗi 10s một ảnh | ~70 ảnh/s | Hàng chục container, cần GPU |
  | 700 ảnh đồng thời thật sự | hàng trăm ảnh/s | Kiến trúc khác hẳn: hàng đợi bất đồng bộ, API trả job-id thay vì trả ảnh |

  Cách thứ ba **phá hợp đồng API hiện tại** ([docs/api.md](api.md)): `POST /` đang trả thẳng ảnh
  đã nắn trong cùng một request. Chịu tải kiểu đó thì phải đổi sang nhận-rồi-trả-sau, tức là
  đổi cả phía tích hợp của khách. Đó là quyết định của khách, không phải chi tiết kỹ thuật.

- **Trong lúc chờ**: [`qc-scanner-bench`](../src/qc_scanner/bench.py) đo thông lượng thật trên
  máy đích và in bảng "bấy nhiêu ảnh/s thì gánh được bấy nhiêu CCU ở mỗi nhịp gửi". Chạy nó
  trước rồi mang **bảng đó** đi hỏi khách — hỏi bằng số dễ chốt hơn hỏi bằng chữ.
- **Chặn**: [SPD-5](features_issues.md#spd-batching) (có làm dynamic batching không) và mọi
  quyết định về số container.

---

### EX-17 · ❓ PDF của khách là bản SCAN hay là ảnh chụp bọc lại? {#ex-pdfkind}

*(Mở 2026-08-05, khi thêm đầu vào PDF — [N-08](features_issues.md#n-pdf).)*

- **Hỏi**: PDF trong luồng của khách sinh ra từ đâu? Máy scan / app scan trên điện thoại (trang
  PDF **chính là** tờ giấy), hay là ảnh chụp được bọc vào PDF (trang rộng hơn tờ giấy, còn thấy
  mặt bàn quanh mép)? Có cả hai thì tỉ lệ thế nào, và phân biệt được từ đâu?
- **Vì sao**: nó quyết định `pdf_pre_cropped`, và hai lựa chọn hỏng theo hai kiểu **không cùng
  giá**:

  | | `pdf_pre_cropped` bật *(mặc định)* | tắt |
  |---|---|---|
  | PDF là bản scan | đúng | **mọi trang `fail`** vì `NO_CROP_DETECTED` |
  | PDF là ảnh chụp bọc lại | mất cảnh báo `CLIPPED_EDGE` | đúng |

  Đo trên một trang scan đặt kín khổ: tắt cờ thì `quad_area_ratio` 0.994 và chạm đủ 4/4 mép —
  tức dấu hiệu "không cắt được gì" đúng theo nghĩa đen với **mọi** trang PDF scan. Nên mặc định
  là **bật**: bên tắt là false fail trên ca phổ biến (ảnh tốt bị loại hẳn), bên bật là thiếu
  một cảnh báo trên ca hiếm. Đây là cùng một cân nhắc đã chốt ở
  [EX-7](#ex-7) và [EX-14](#ex-precropped).
- **Ảnh hưởng nếu là ảnh chụp bọc lại**: đặt `QC_SCANNER_PDF_PRE_CROPPED=0` cho luồng đó. Nếu
  **lẫn cả hai trong cùng một luồng** thì cần một tham số request như `pre_cropped` hiện có,
  chứ không đoán được từ pixel (đã đo ở [EX-14](#ex-precropped): hai nhóm trùng dải).
- **Trong lúc chờ**: xin ~10 file PDF thật là nhìn ra ngay. Cột `pdf_source` trong CSV của
  `qc-scanner-batch` cũng nói luôn mỗi trang được đọc bằng đường nào.

---

### EX-18 · ❓ Ảnh ra là **bản đọc máy** hay **bản gốc lưu trữ**? {#ex-archival}

- **Hỏi gì**: ảnh qc_scanner trả về sẽ đi đâu — chỉ vào OCR/bóc dữ liệu rồi bỏ, hay được **lưu
  lại làm bản số hoá chính thức** của hồ sơ?
- **Vì sao**: quyết định `QC_SCANNER_DESKEW`. Từ QC-19, ảnh ra được **xoay về ngang** theo phần
  dư đo được — 18/38 ảnh thật lệch > 0.5°, sau khi xoay còn 2. Với OCR thì rõ ràng có lợi.
  Nhưng xoay một góc khác bội số 90° buộc **nội suy lại mọi điểm ảnh**, và
  [FADGI](https://www.digitizationguidelines.gov/guidelines/FADGI%20Technical%20Guidelines%20for%20Digitizing%20Cultural%20Heritage%20Materials_3rd%20Edition_05092023.pdf)
  mức 4 sao **cấm** de-skew bằng phần mềm với bản gốc lưu trữ, đúng vì lý do đó.
- **Ảnh hưởng**: bản đọc máy → giữ mặc định (bật). Bản gốc lưu trữ → `QC_SCANNER_DESKEW=0`, và
  khi ấy `text_skew_deg` vẫn được báo cáo để bên nhận tự quyết từng ảnh.
- **Đang mặc định**: **bật**, chọn theo [EX-13](#ex-13) (bàn giao phục vụ luồng bóc dữ liệu).
  Đây là suy đoán từ bối cảnh, **chưa hỏi**.
- **Trong lúc chờ**: không chặn gì — đổi một biến môi trường là xong, không phải đổi code.

---

## Cách dùng file này
- Trước mỗi buổi làm việc với khách: lọc mục ❓, chuẩn bị câu hỏi + **tài liệu/dữ liệu cần xin**.
- **Trạng thái 2026-08-05: 12/13 mục đã chốt.** Còn lại EX-9 (đa ngôn ngữ) — không chặn việc gì.
  Thứ duy nhất còn chặn là **dữ liệu của EX-2**, không phải câu trả lời.
- Ưu tiên hỏi trước: **EX-2** (tập vàng — nay là thứ chặn *toàn bộ* phần còn lại), **EX-4**
  (khổ giấy — đã thành vấn đề thật, xem trên), **EX-1** (định nghĩa "đạt"), **EX-7** (cân bằng
  false pass/fail), **EX-5** (có cần dewarping không).
- Sau khi có câu trả lời: đổi trạng thái ✅ + ghi **quyết định đã chốt** (kèm ngày, nguồn tài liệu).
- Quyết định chốt mà ảnh hưởng code → tạo issue/feature tương ứng trong
  [features_issues.md](features_issues.md); nếu chốt một **ngưỡng**, ghi thẳng vào
  [algorithm.md §7](algorithm.md#ma-ly-do) kèm nguồn.
