# Kế hoạch triển khai

## Neon/PostgreSQL + S3 — kiểm thử và chuẩn bị migration (11/11/2026)

**Chưa chuyển production, chưa push/deploy/bật billing.** Kết nối pooled/direct thật TLS READONLY PASS; adapterpoolNeon PASS sau sửa startupoptions. S3 QA940 byte vàPPTX70 MB thật SHA256 khớp/Private/cleanupPASS. Gemini models.getPASS, khôngsinh nội dung.

Diễn tập:7 bảng/18 bài/157 lượt/1 job,998 tệp, PostgreSQL WASMlocal + S3 mô phỏng, rollbackSQLite/filechecksumPASS; khônggiảlàmNeonproduction.84 backendtests và25 ChromeHTTPSlocalPASS, buildNetlifyPASS. OriginalSQLite/media7 bảngkhông đổi.

[Hướng dẫn Neon và cutover có guard](docs/NEON_MIGRATION.md) · [QA PASS/FAIL/NOT_TESTED](docs/NEON_QA.md). NativeLinux/RenderRAMCPU/migrationghi/jobcloud/70 MBquaRenderthật:NOT_TESTED. Render Freekhông cóDisk/Shell;render.yamlđãchuẩnbịFree/PG/S3 nhưngchưaápdụng. Cloudruntime mặcđịnh tắt chođến khiHARRYphê duyệt. CácphầnDisk/SQLitecũ bên dưới làlịch sử, không dùngchúngđể cutoverNeon.



## Chuẩn bị production GitHub + Netlify + Render — 11/11/2026

Đã chuẩn bị cấu hình environment/fallback, disk path, cookie/Origin/Host/CSRF, jobSQLite+polling, upload2MB/phần, backup/restore không ghi đè và release mã nguồn. Giữ giao diện, bài học và lịch sử; chưa push/triển khai/bật billing.

**Bằng chứng local:**69/69backend,25/25Chrome quaHTTPSproxy mô phỏng26s; buildNetlifyPASS; PPTXthật70MB tải34phần→10slide; backup/restore18bài/157lượt/8cache. BộSDKchậm27s dùngstub, không gọiGemini thêm. Một lượt đầu thêm2lượtQA và đổi revision/updated1bài trước khi táchcổng;155lượt cũ/câu hỏi/đáp án không đổi. Sau đó toàn bộE2E dùngbản sao.

[Hướng dẫn triển khai từng bước](docs/DEPLOYMENT.md) · [QA và giới hạn](docs/PRODUCTION_QA.md). RenderPersistentDisk cần gói trả phí, không tự kích hoạt. Cloud/LinuxDocker/SSH/Netlifythật vẫn NOT_RUN; không khẳng định production đã PASS. Linux không renderPPTX bằngPowerPointCOM; giữcache đãmigrate, cảnh báo filemới và đề xuấtPDF khi cần bố cục.

Giới hạnAI hiện tại theo HARRY: **1lượt/30giây**, giữ20lượt/24giờ local, không phải quotaGoogle. Không reset counter cũ.


## Sửa khẩn cấp tạo bài mới — 11/11/2026

Đã kiểm thử Gemini thật, không cache: PDF mới6 trang tạo/lưu/hiển thị6/6 câu; DOCX và TXT2/2 câu mỗi file. PPTX gốc gặp503 thật tại bước5; thử một lần từ bản nháp giữ nguyên nhận6, lưu5 câu hợp lệ (**PARTIAL**, không nhận câu sai). Không thay .env/model/billing.

Bổ sung timeline9 công đoạn, lỗi có origin/stage/reason, kiểm định từng câu, lưu phần hợp lệ, retry không upload lại và tạo bổ sung giữ ID cũ. File và nội dung nguồn giữ trước khi gọiAI. Mạng502, timeout504 được tách khỏi upstreamGemini503. Giáo viên vẫn cần duyệt.

Kiểm thử: build PASS;54/54 backend;20/20 Chrome,5 hoạt động,3 viewport;118 lượt học cũ không đổi. Bằng chứng và giới hạn: [QA sửa tạo bài mới](reports/phase4/QA_REPORT.md). Website: http://127.0.0.1:8000/ → Thư viện → `QA phase4 de-thi-hoc-ki…` để kiểm duyệt bàiPDF mới. `QA phase4 Unit6…` còn thiếu1 câu vocabulary; xem PARTIAL và dùng tạo bổ sung khi phù hợp.


## Giai đoạn 3 — đã thực hiện

Đã sửa P1 từ nguồn tới trình duyệt: khôi phục đúng DOCX theo hash; xử lý VML và mệnh đề Đúng/Sai; lưu ảnh gắn nguồn; render PPTX/PDF; kiểm định vai trò, nhãn đáp án và subject/attribute/value; schema hình ảnh dùng chung; preview/chọn/crop/duyệt ảnh; chặn xuất bản câu thiếu dữ kiện; skip không trừ điểm khi ảnh lỗi ở cả 5 hoạt động. Giữ nguyên ID/đáp án cũ và kết quả lịch sử, tạo bản thay thế đúng nguồn khi cần.

Đã kiểm tra 21 câu gốc, sửa ngữ cảnh 5 câu, tạm ẩn 2 câu sai và tạo 2 câu thay thế đúng ảnh/đoạn đọc. Có Gemini đa phương thức thật và kiểm thử Chrome với PowerPoint/DOCX gốc; 49 backend + 18 E2E + build PASS. Chi tiết `reports/phase3/QA_REPORT.md`.

Tiếp theo: HARRY đối chiếu học liệu trên thiết bị/lớp thật; ưu tiên ảnh có đủ ngữ cảnh và nguồn. Mọi OCR/renderer Word tổng quát hoặc mở rộng hosting là công việc tiếp theo, không nằm trong kết quả PASS hiện tại.

## Giai đoạn 1

Đã kiểm kê đầu vào, kiểm tra công cụ, tạo môi trường, cài SDK, kiểm chứng Git ignore và trích xuất PowerPoint. Đã khắc phục HTTP 404 bằng `gemini-3.5-flash-lite`; kiểm thử thật sinh 3 câu hỏi JSON từ slide 5 và đối chiếu nội dung PASS. Giai đoạn 1 hoàn tất trong phạm vi đã ghi tại STATUS.md.

## Giải quyết chặn API

Đã hoàn thành với model 3.5 Flash-Lite. Quy trình dưới đây dùng khi cần đổi model lần sau.

1. Kiểm tra model thay thế trong Google AI Studio và bảng giá chính thức, đảm bảo dùng được trong Plan Free của dự án HARRY.
2. Cập nhật duy nhất `GEMINI_MODEL` sau khi xác nhận model miễn phí; không thay khóa hoặc bật billing.
3. Chạy một smoke test; nghiệm thu khi nhận đúng phản hồi mong đợi. Nếu 429, chờ/reset quota, không nâng cấp trả phí.

## Giai đoạn 2 — đã triển khai và kiểm thử

Hoàn thành React + TypeScript + Vite, FastAPI, SQLite, xác thực giáo viên local, tải PPTX/PDF/DOCX/TXT, xem nguồn, tạo AI, sửa/thêm/xóa, duyệt từng câu, xuất bản/thu hồi, mã/liên kết học sinh, 5 hoạt động và lưu điểm ẩn danh. Tái sử dụng reader giai đoạn 1 với đường XML tiết kiệm RAM; giữ nguyên `.env` và tài liệu gốc.

Gemini thật tạo 6 câu đủ 5 loại từ PowerPoint mẫu. Schema truyền tải được thu gọn cho Gemini; Pydantic và kiểm tra nguồn vẫn đầy đủ tại backend. Kết quả được kiểm duyệt: sửa dấu tiếng Việt và nội dung nghe trước khi xuất bản. Có bài mẫu bản nháp và một bài trình diễn đã xuất bản, chơi được khi AI không khả dụng.

Kiểm chứng: build production, 29 kiểm thử backend, 4 kiểm thử Chrome E2E, ảnh ở 1440×1000 / 768×1024 / 390×844, và dữ liệu sau restart. Chi tiết bằng chứng tại STATUS.md. Không triển khai hosting hoặc bật thanh toán.

## Hướng tiếp theo ngoài phạm vi đã nghiệm thu

1. Giáo viên HARRY duyệt lại nội dung trình diễn và chọn khối lớp phù hợp chương trình; thử tại lớp/thiết bị thực tế, kiểm tra loa và giọng tiếng Anh.
2. Bổ sung ảnh từ vựng có nguồn phù hợp và được duyệt; OCR nếu có yêu cầu cho bài giảng chỉ gồm ảnh.
3. Nếu cần chia sẻ rộng: thiết kế nhiều tài khoản, HTTPS, sao lưu tự động, giới hạn theo tài khoản và kiểm thử LAN/tải trước khi triển khai internet.
4. Chuẩn bị minh chứng vận dụng/bản thuyết minh theo PDF đầu vào của trường; chưa tạo hồ sơ nộp hoặc gửi tài liệu cho bên ngoài.

## Kế hoạch giai đoạn 2 ban đầu (lịch sử)

1. Đọc PDF yêu cầu và chuyển 10 slide mẫu thành dữ liệu bài học có mục tiêu, từ vựng, câu hỏi và đáp án được giáo viên duyệt.
2. Xây frontend React + TypeScript + Vite: trang hành trình, bài học, luyện tập và kết quả. Ưu tiên giao diện tiếng Việt, hoạt động tốt trên điện thoại.
3. Xây backend FastAPI: health check, lesson API và AI feedback. Giữ khóa phía server; xác thực dữ liệu, giới hạn độ dài và số lượt gọi, xử lý timeout/404/429, không tự fallback sang model trả phí.
4. Dùng bài tập tĩnh làm luồng học nền; hiển thị rõ khi AI chưa khả dụng. Lưu tiến độ cục bộ cho bản thử nghiệm, xác định nhu cầu tài khoản trước khi thêm cơ sở dữ liệu.
5. Kiểm thử hoàn thành bài học, chấm đáp án, mất mạng/quota, bảo vệ khóa trong frontend và luồng AI thật. Chỉ triển khai hosting sau khi có cấu hình và phạm vi được thống nhất.

Tiêu chí nghiệm thu website: học sinh mở bài, làm bài, nhận kết quả, tiếp tục tiến độ; AI phản hồi đúng định dạng hoặc báo lỗi rõ ràng; khóa không xuất hiện trong bundle hay log; kiểm soát hạn mức Free đã được thử.
