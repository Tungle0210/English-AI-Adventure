# QA chuẩn bị production — 11/11/2026

**Kết luận: PASS cho bản chuẩn bị đã kiểm thử local; production cloud CHƯA NGHIỆM THU.** Không push GitHub, không triển khai Netlify/Render, không bật billing hoặc gọi Gemini thêm trong giai đoạn DevOps này.

## Đã hoàn thành

- Environment variables Gemini ưu tiên hơn `backend/.env`; fallback chỉ ở backend. Không thay key/model đã có. `.env`, data, input, reports, backup và bản migrate riêng được loại khỏi Git/Docker/release. Có công cụ tạo thư mục mã nguồn để upload thủ công.
- Persistent data path thống nhất qua ADVENTURE_DATA_DIR; Docker/Render mẫu dùng `/var/data/adventure`. Chế độ bảo trì bootstrap không seed DB/mã giáo viên/bài mẫu. Chỉ mở production sau nhập dữ liệu và đặt IMPORT_READY=yes. Production không tự audit/sửa học liệu cũ lúc startup.
- SQLite job queue bền vững cho tạo bài, tạo lại câu, phân tích ảnh và trích xuất upload/khôi phục source. HTTP202 + poll ngắn, Idempotency-Key, giới hạn job trên một bài; kết quả riêng tư trong DB. Queued job tiếp tục sau restart; running job bị gián đoạn được đánh dấu interrupted, không tự gọi lại AI. Giữ draft/nguồn/partial validation hiện có.
- OS lock ngăn hai tiến trình cùng sở hữu data directory. Chạy một instance và một Uvicorn worker. Không dùng background service thứ hai chia sẻ disk.
- Frontend giữ bố cục/giao diện, có theo dõi job và khôi phục sau refresh. File chia từng2MB, tổng100MB; có offset/resume. Source/media giữ lâu dài; chỉ xóa staging mới nhận sau xử lý thành công, không xóa tài liệu gốc/bài/điểm đã có.
- Netlify build/proxy same-origin và security headers/CSP. Origin HTTPS exact allowlist, Host exact allowlist, không tin forwarded headers của client; production mutation thiếu/sai Origin bị403. Cookie Secure/HttpOnly/SameSite=Strict/Path=/api, không Domain; quản trị/job cần mã giáo viên. Media chưa xuất bản cần quyền giáo viên; học sinh ẩn danh vẫn tải ảnh câu đủ dữ kiện đã xuất bản/lượt chơi.
- Theo yêu cầu HARRY trước đó: một lượt AI mỗi30giây, giữ20lượt/24h local; dùng chung cho ba lệnhAI, không phải quota Google. Cache bỏ các metadata filename/intake timing để cùng nội dung không gọi lại chỉ vì đổi tên/tải lại.
- Dockerfile, render.yaml (autoDeploy Off), netlify.toml, workflow GitHub chỉtest và hướng dẫn migrate/backup/rollback từng bước. Không thay kiến trúc database hoặc tự thay dữ liệu.

## Kết quả đã chạy

| Hạng mục | Kết quả | Bằng chứng local |
|---|---|---|
| Backend toàn bộ | PASS69/69 | reports/production/backend-tests.xml |
| Bản mã nguồn release độc lập | PASS15/15 không có.env/data/input riêng | reports/production/release-tests.xml |
| Bộ production riêng | 15 test gồm môi trường, Origin/Host/CSRF/cookie, queue/restart/idempotency, upload, media, backup/restore, single-writer và30s | backend/test_production.py |
| Gemini chậm vượt proxy | PASS: mock SDK bị giữ27giây; enqueue/poll vẫn trả dưới2giây, chỉ1lần gọi stub | test_job_exceeds_26s_without_long_http |
| Frontend TypeScript/Vite + Netlify build | PASS | npm run build:netlify; _redirects sinh đúng thứ tự |
| Cấu hình YAML/TOML | PASS cấu trúc local, không có key | reports/production/config-check.json |
| Chrome regression local | PASS20/20 trên bản sao, cổng8001 | reports/production/browser-local.json |
| Chrome qua HTTPSproxy26s, production flags | PASS25/25 | reports/production/browser-https-final.json |
| PPTX thật70.396.372byte qua HTTPS | PASS34request, tối đa2.097.152byte/part, đủ10slide, extraction job/poll | reports/production/https-upload.json, proxy-metrics.json |
| Login/refresh/logout và năm hoạt động | PASS, có ảnh thật desktop/tablet/mobile; học sinh riêng không có cookie GV vẫn xem ảnh và đạt100điểm | Chrome suite và ảnh |
| Khôi phục theo dõi job sau refresh | PASS client logic với HTTP fixture; queue/restart thật kiểm tra riêng bằng SQLite | browser production.spec.ts + backend tests |
| Backup dữ liệu thật | PASS991file, ZIP216.208.645byte, giải nén241.041.931byte | private-backups/production-offline-20261111.data-bundle.zip |
| Nhập dữ liệu thật vào thư mục mới | PASS18lessons/157attempts/8cache; checksum từng file + SQLite integrity | reports/production/migration-rehearsal.json |
| Chặn restore đè thư mục có dữ liệu/ZIP traversal | PASS | test_bundle_roundtrip_and_refuse_overwrite |
| Dữ liệu gốc | Không mất/sửa155lượt cũ; không mất lesson/question ID hoặc đổi đáp án | reports/production/preservation.json |
| Secret | PASS scan: không thấy API key trong deliverable; sourcePPTX không đổi | reports/delivery-check.json + release-check.json |

### Ghi nhận minh bạch khi kiểm thử

Một lần chạy đầu bị nối vào server local cũ do xung đột cổng; đã dừng và chạy lại toàn bộ trên cổng8001 với bản sao riêng. Lần đó thêm2lượt QA vào bản gốc (155→157) và tăng revision/updated của1bài; câu hỏi, đáp án, trạng thái xuất bản và155lượt lịch sử không đổi. Không xóa/rollback những bản ghi này để che kết quả. Đã chốt backup offline sau đó và dùng bản sao cho các lượt còn lại.

Các lỗi kỹ thuật đã gặp và sửa trước kết quả cuối: SQLite handle chưa đóng khiến Windows không dọn được snapshot; hard-link không được sandbox cho phép nên đổi sang ghi backup mới bằng chế độ exclusive; URI path cần encode đúng khi có khoảng trắng; Playwright không nhận buffer>50MB nên chọn file thật; Chrome không cung cấp body size của Blob nên đo byte thực ở proxy. Không coi các lần kiểm thử thất bại ban đầu là PASS.

### Phân biệt AI và bài lưu

Không gọi Gemini thật thêm trong giai đoạn chuẩn bịproduction để tiết kiệm quota. TestSDK cho môi trường/job/lỗi dùng stub có kiểm soát; trò chơi dùng bàiAI đã lưu thật, không được gọi là AI trực tuyến. Bằng chứng Gemini thật từ PPTX/PDF/DOCX/TXT ở giai đoạn trước nằm trong reports/phase4; chưa kiểm chứng gọi Gemini bằng environment trên Render thật.

## Chưa kiểm chứng / không tương đương

| Hạng mục | Trạng thái |
|---|---|
| GitHub push, CI Ubuntu từ xa | NOT_RUN theo phạm vi khôngpush |
| Docker build/run Linux, package wheels/system libraries/RAM | NOT_RUN: máy hiện không có Docker, WSL không khả dụng |
| Render service/Persistent Disk, import quaSSH/SCP, restart giữ data | NOT_RUN: chưa tạo tài nguyên |
| Netlify rewrite/cookie/header/body limit/thông lượng thực | NOT_RUN: proxy local không thay thế Netlify thật |
| Xác thực Blueprint bằng RenderCLI/API của tài khoản | NOT_RUN; mới kiểm tra YAML/các ràng buộc local |
| Backup offsite tự động, lịch backup, cảnh báo disk-full | NOT_CONFIGURED; đã có quy trình thủ công |
| PowerPoint COM render toàn slide mới trên Linux | KHÔNG TƯƠNG ĐƯƠNG: chỉ ảnh/chữ gốc hoặc cachemigrated; có cảnh báo, không suy đoán |
| Word phân trang/render và OCR | CHƯA CÓ, giữ giới hạn cũ |
| Đồng thời nhiều lớp/tải nặng, HA/multi-instance | NOT_RUN/không thiết kế cho nhiều writer |
| Tách tài khoản từng giáo viên/tenant | Chưa có; giữ cơ chế mã GV dùng chung của dự án, không phải SaaS nhiều trường |

Render disk là dịch vụ trả phí, Free không đáp ứng giữ SQLite qua deploy. Không khẳng định góiStarter đủ bộ file100MB/lưu lượng bất kỳ. Disk có gián đoạn khi deploy; giới hạn shutdown có thể kết thúc SDK đang chạy nên trạng thái interrupted và kiểm tra draft là bắt buộc. Không tự retry để tránh gọi phí/quota trùng.

## File chính

- backend/config.py, ai.py, main.py, jobs.py, storage.py, media.py, test_production.py.
- frontend/src/main.tsx; package.json; playwright.config.ts; tests/production.spec.ts.
- Dockerfile, .dockerignore, render.yaml, netlify.toml, .github/workflows/check.yml.
- scripts/data_bundle.py, prepare_release.py, netlify-redirects.mjs, start-production.py, check_production_config.py, local_https_proxy.py.
- Bản upload mã nguồn: deploy/release-ready (62 file, không có dữ liệu/key).
- Hướng dẫn: docs/DEPLOYMENT.md. Bằng chứng chi tiết chỉ ở máylocal, không upload lênGitHub.
