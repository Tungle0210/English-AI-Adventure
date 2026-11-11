# Dùng thử cloud — 11/11/2026

Bản mã cloud đã Push lên main: 0da6cd453b9cf23cc91951c1ed3b5578c437b482. CI Linux tích hợp PostgreSQL/S3 mô phỏng, frontend build và Docker khởi động maintenance đã PASS ở run 42951383976. Bộ 84 test với tài liệu riêng chạy local PASS; chúng không được suy diễn là 84 test Linux.

## Mã giáo viên

Mã mới tạo bằng secrets.token_urlsafe(24); PostgreSQL chỉ lưu PBKDF2 SHA-256 với salt riêng và 600000 vòng. Không có API reset công khai. Tệp giao mã riêng: `E:\English-AI-Adventure\private-backups\teacher-final-20261111.txt`, ngoài checkout Git, đã hạn chế ACL cho tài khoản hiện tại. Không đưa tệp này lên S3 hoặc GitHub.

CLI `scripts/teacher_admin.py --new-demo-schema demo_TEN_MOI --private-output private-backups/TEN_MOI.txt` chỉ tạo namespace demo mới, từ chối schema hoặc tệp đã tồn tại. Không dùng để ghi đè giáo viên/dữ liệu cũ.

## Dữ liệu

Schema demo riêng: demo_harry_20261111; S3 prefix: demo-harry-20261111. Hai bài DEMO: một bài xuất bản và một bản nháp tạo trực tiếp qua Netlify/Render bằng Gemini thật. Bài xuất bản có 2 câu quiz tạo bởi Gemini thật, được đối chiếu TXT rồi duyệt/xuất bản. Mã bài: 2926CE34. Đây là dữ liệu thử nghiệm, không phải 18 bài thật được migration. Backend local đã kiểm tra cold cache ở tiến trình mới, chơi 100 điểm, backup thực từ Neon/S3 sang thư mục riêng.

Nguồn local giữ nguyên 18 bài, 135 phiên, 157 lượt, 8 cache, 20 calls, 1 job; checksum 7 bảng và 992 file nguồn đối chiếu khớp. Không tự migration dữ liệu thật.

## Triển khai

Giữ Render Free Docker một worker, cloud PostgreSQL/S3; `/tmp/english-ai-cache` chỉ là cache. Không dùng SQLite tạm cho dữ liệu cloud. Netlify giữ API cùng origin tới Render, backend cho đúng hostname Render và origin Netlify. Khởi tạo ở maintenance=1, chỉ chuyển 0 sau xác minh schema demo và backup. IMPORT_READY=yes chỉ áp dụng schema demo đã kiểm chứng.

Website: https://english-ai-adventure.netlify.app
Bài học: https://english-ai-adventure.netlify.app/#/play/2926CE34

Vào giáo viên ở trang chủ, lấy mã từ tệp riêng, nhập ô Mã truy cập giáo viên. Học sinh không cần mã giáo viên, dùng mã bài. Render Free có thể khởi động chậm; giữ trang mở trong lúc tải.

## Bảo mật và giới hạn

HARRY quyết định giữ credential cũ; thay mới/thu hồi CHƯA THỰC HIỆN. Có sự cố đầu ra công cụ UI hiển thị nội dung .env trong lúc nhập cấu hình; không đưa giá trị vào báo cáo hay Git. Secret scanning lịch sử 2 commit cũ và staged source không tìm thấy credential cấu hình hiện có hoặc mã giáo viên mới; đây không phải chứng nhận mọi secret lịch sử đều sạch.

Linux không có PowerPoint COM: không tương đương render toàn slide trên Windows. Giữ trích xuất chữ/ảnh, không suy đoán ngữ cảnh; PDF phù hợp hơn khi cần bố cục. Chưa nghiệm thu RAM/CPU upload 70 MB trên Render Free, restart cloud, responsive điện thoại vật lý hoặc đủ 5 game qua trình duyệt production. Xem báo cáo QA riêng để biết trạng thái kiểm thử mới nhất.

## Nghiệm thu Internet đã thực hiện

PASS: đăng nhập mã mới qua Netlify, thư viện/kết quả, cookie Secure/HttpOnly/SameSite Strict, mã sai401, thiếuOrigin403, đăng xuất200 rồi thư viện401. Upload TXT mới qua Netlify200, tạo job202, Gemini thật thành công, hai câu đúng nguồn ở trạng thái cần duyệt. Chơi quiz trong Chrome thực tế:100/100,2/2 câu, màn hình xác nhận đã lưu. Bằng chứng riêng trong reports/neon/netlify-login.json, netlify-real-generation.json, netlify-student-result.png.

NOT_TESTED: đủ5game trên trình duyệt production, PDF/DOCX/PPTX mới trênRender,70MB quaRender, RAM/CPU thực tế và điện thoại vật lý. Không suy diễn kết quả local thành PASSproduction. Thu hồi credential cũ chưa thực hiện theo lựa chọn HARRY.
