# Neon + Render Free + Netlify: hướng dẫn cho HARRY

Ngày kiểm thử:11/11/2026. Đây là chuẩn bị chuyển đổi, **chưa được phép chạy migration production**. Không có push/deploy/bật billing nào đã được thực hiện.

## 1. Kết quả kết nối hiện có

- DATABASE_URL pooled và DATABASE_DIRECT_URL direct: kết nối thật, TLS, giao dịch READ ONLY thành công. Adapter/pool mới cũng đã thử SELECT trong READ ONLY, không tạo schema/bảng/row.
- Neon S3 Private:940 byte và PPTX70.396.372 byte upload/download thật, SHA-256 khớp. Đọc ẩn danh bị chặn. Hai object QA có namespace ngẫu nhiên đã được xóa; không sửa object/bucket policy hiện hữu. Không dùng PutBucketAcl.
- Gemini:models.get thành công và model trả đúng tên cấu hình. Không gọi generate_content, không sinh token; metadata API vẫn là một API request, không khẳng định miễn mọi rate-limit.
- URL Render và Netlify `/api/health` đều200/ok, `/api/lessons` không đăng nhập đều401. Health không chứng minh dữ liệu đã ở Neon. Có một lần HTTP qua Netlify đo tổng44,18 giây; số đo gồm mạng/TLS/proxy, chưa xác định thành phần gây chậm.

Tuyệt đối không đưa connection string/mật khẩu/access key vào issue, ảnh chụp, terminal hoặc chat. Mật khẩu đã từng xuất hiện trong chat nên cần rotate trên Neon và cập nhật các biến liên quan trước cutover; chưa xác minh việc rotate đã hoàn tất. Báo cáo không chứa lại giá trị đó.

## 2. Vai trò các cấu hình

| Cấu hình | Ý nghĩa |
|---|---|
| DATABASE_URL | URL pooled dùng cho request/job; giữ sslmode=require |
| DATABASE_DIRECT_URL | URL direct cho migration/backup; không dùng để vô tình ghi production khi test |
| AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY | Credential của Neon Object Storage, không phải bắt buộc IAM AWS |
| S3_ENDPOINT_URL | Endpoint HTTPS của đúng branch Neon; bắt buộc path-style, không ghép bucket vào hostname |
| AWS_REGION | us-east-2 theo hạ tầng HARRY |
| S3_BUCKET | english-ai-files, giữ Private |
| S3_PREFIX | Namespace riêng của bộ dữ liệu; phải là namespace MỚI và TRỐNG khi migration |
| ADVENTURE_PG_SCHEMA | Schema riêng của bộ dữ liệu, ví dụ english_ai_v1; không dùng schema đã có dữ liệu |
| ADVENTURE_CLOUD_ENABLE | Guard kích hoạt runtimecloud; mặc định no cho tới khi được phép |
| ADVENTURE_DATABASE_BACKEND | postgres khi cutover được phê duyệt; sqlite cho local/rollback |
| ADVENTURE_STORAGE_BACKEND | s3 khi cutover; local cho local/rollback |
| ADVENTURE_ALLOW_MIGRATION | Guard CLI, mặc định không cho phép ghi production |

Không tự thay file backend/.env của HARRY trong giai đoạn kiểm thử này. Environment variables ưu tiên hơn .env local. Mẫu công khai ở backend/.env.example chỉ có placeholder. Không có key nào ở frontend/VITE_*.

## 3. Những phần mã đã chuẩn bị

- PostgreSQL qua psycopg và connection pool nhỏ, JSON giữ kiểu TEXT để không đổi byte của câu hỏi/snapshot/lịch sử. Giữ nguyên UUID, mã bài, revision, đáp án, approved/hidden, điểm trong responses và idempotency key.
- SQL tương thích PostgreSQL: quote cột offset, bind parameter an toàn, cache upsert, JSON queries. Không dùng SQLite như shadow database trong cloudmode.
- Neon pooler không chấp nhận startup options như bản thử đầu: đã chuyển statement/lock timeout sang SET LOCAL trong transaction. Prepared statement cache tắt để hợp với pooler.
- Nguồn/media/render cache/QA trace lưu S3, filelocal chỉ là cache có SHA-256. Metadata giáo viên/ảnh và pixels giữ nguyên. Khi cold start chỉ nạp cái cần dùng; dashboard dùng thư viện summary, chọn bài mới tải chi tiết.
- Upload chia2 MB: mỗi phần ack sau khi S3 lưu; offset/session ởPG. File nhỏ/ảnh/hash không cần publicbucket. Job ráp tệp xuống cache tạm để trích xuất, stream có giới hạn bộ đệm; không nạp nguyên70 MB chỉ để upload/download.
- Job ởPG có lease90 s, heartbeat khi đang chạy, fencing chặn ghi muộn sau mất lease. Không poll DB liên tục lúc không có việc để không giữ compute Neon thức vô ích. Queued job giữ nguyên; running job mất lease thành interrupted, không tự gọi Gemini lại vì không biết lượt trước đã xử lý tới đâu.
- Mã giáo viên cũ được kiểm bằng hash PBKDF2 từ bản sao, không tạo mã mới khi cloudstartup. Cookie/Origin/Host/CSRF và quyền giáo viên giữ nguyên. Bài đã lưu vẫn chơi khi Gemini lỗi.

## 4. Diễn tập đã chạy và phạm vi

Bản sao hiện tại đã kiểm tra ổn định trước/sau đọc, gồm7 bảng:18 lessons,135 sessions,8 cache,20 calls,157 attempts,1 jobs,0 upload_sessions. Đã nhập sang PostgreSQL WASM/PGlite local, đọc lại từng bảng theo checksum chuẩn hóa giữ JSON string nguyên vẹn.998 tệp gồm ảnh/nguồn và asset indexes đã đi qua boto3 với S3 mô phỏng cô lập và kiểm SHA-256. Đã đọc ngược tạo một thư mục SQLite/media rollback mới, không ghi đè bản gốc.

**Đây không phải migration vào Neon production, không phải PostgreSQL native trên Linux, cũng không phải upload toàn bộ media thật lên S3 production.** Bằng chứng local:reports/neon/migration-rehearsal.json. PGlite dùng Postgres engine WASM và PostgreSQL wire, có giới hạn single-connection; không thay thế kiểm thử tải native.

Dữ liệu gốc vẫn tại backend/data. Bản sao/bằng chứng nhạy cảm ở private-production-data/neon-current-rehearsal, không đưa lênGitHub. Bản backup cũ production-offline-20261111.data-bundle.zip vẫn giữ nguyên; plan từ backup cũ cũng đã được kiểm nhưng bản này chưa có job, nên diễn tập cuối dùng bản sao hiện tại đủ7 bảng.

## 5. Các lệnh an toàn có thể chạy trước khi được phép cutover

Mở PowerShell tại E:\English-AI-Adventure. **Không cần chạy lại các probe thật liên tục**, vì mỗi lần S3 có truyền dữ liệu/quota.

```powershell
backend/.venv/Scripts/python.exe scripts/probe_neon.py
backend/.venv/Scripts/python.exe scripts/probe_s3.py
```

Probe SQL chỉ đọc; S3 chỉ dùng prefix QA riêng và cleanup. Test file lớn chỉ chạy khi nhận diện endpointNeon và thấy bucket còn khoảng trống theo giới hạn Free. Không đọc được số quota còn lại toàn tài khoản/allbranches từ credential S3, nên cần đối chiếu Usage trên Neon Console trước mọi migration thật.

Tạo plan từ một backup đã có, dùng tên work MỚI:

```powershell
backend/.venv/Scripts/python.exe scripts/cloud_migration.py plan --bundle private-backups/production-offline-20261111.data-bundle.zip --work private-production-data/plan-v2
```

Hoặc tạo bản sao SQLite hiện tại chỉ đọc, kiểm tra không có job đang running và DB/files không đổi trong lúc copy:

```powershell
backend/.venv/Scripts/python.exe scripts/cloud_migration.py snapshot-plan --data backend/data --work private-production-data/current-plan-v2
```

Nếu có người dùng/job đang ghi và checksum thay đổi, tool dừng; không ép bỏ qua. Chốt thời gian tạm ngừng ghi trước bản snapshot dùng để cutover.

Bản rehearsallocal cần loopback Postgres riêng. Các dependency test đã cài trong cache ở máy này; cho máy mới:

```powershell
npm install --prefix .cache/pg-rehearsal @electric-sql/pglite @electric-sql/pglite-socket
```

Cửa sổ1:

```powershell
node scripts/local_pglite.mjs
```

Cửa sổ2, với plan/work mới chưa có rollback-copy:

```powershell
backend/.venv/Scripts/python.exe scripts/cloud_migration.py rehearse --work private-production-data/current-plan-v2
```

Lệnh rehearse luôn dùng localhost55432 và credential S3 giả; không lấy DATABASE_URL production để ghi. `moto[s3]` nằm trong requirements-dev.txt, không đưa vào dependency runtimeCloud. Không gọi dữ liệu giả lập là migration thật.

## 6. Cutover thật — CHỈ SAU KHI HARRY CHO PHÉP

Các bước dưới đây chưa được thực hiện. Không chạy apply bây giờ.

1. Rotate mật khẩu đã lộ, xác nhận cả hai URL PostgreSQL và credential S3 cùng đúng productionbranch. Xem Usage Free của Neon:storage/database/network/compute còn đủ cho plan. Check account-level usage, không chỉ bucket rỗng.
2. Dừng ghi trên bản local cũ và production đang dùng trước khi chốt snapshot. Nếu cloud đang có dữ liệu riêng khác local, backup cả hai và đối chiếu; tool không tự merge hay thay thế schema hiện hữu. Đợi job hoàn tất, không tạo request Gemini trùng.
3. Giữ bản SQLite/source/media nguyên vẹn, thêm backup ngoài máy, tạo plan mới. Xem số bài/lượt/job/file/hash trong plan-summary và manifest. Không đưa work/source/manifest private lênGitHub.
4. Chọn schema MỚI và prefix MỚI/TRỐNG. Sửa S3_PREFIX của **tiến trình migration riêng** theo namespace đã chọn; không trỏ tool vào prefix đang phục vụ website. Tool từ chối schema/prefix không trống, không truncate/drop/merge dữ liệu cũ.
5. Chỉ sau phê duyệt, người vận hành mới bật ADVENTURE_ALLOW_MIGRATION=yes và ADVENTURE_CLOUD_ENABLE=yes/ADVENTURE_STORAGE_BACKEND=s3 cho lệnh migration. Apply còn cần cờ --permit-production-write; thiếu bất kỳ guard nào đều bị chặn. Ví dụ câu lệnh tương lai:

```powershell
backend/.venv/Scripts/python.exe scripts/cloud_migration.py apply --work private-production-data/PLAN_DA_CHOT --schema SCHEMA_MOI --permit-production-write
```

Không dán DATABASE_URL/secret vào dòng lệnh; đọc từ env/.env. Cần đủ quyền tạo schema trong DB và ghi vào đúng S3 prefix, không cần quyền bật billing hoặc tạo project. Upload/verify S3 xong mới chạy transaction SQL nhập toàn bộ bảng; marker ready chỉ ghi sau khi bảng và file đã đối chiếu. Nếu SQL fail sau upload, có thể còn prefix mới chưa được sử dụng: giữ lại để đối soát, không xóa prefix khác hay âm thầm bật app.
6. Đọc báo cáo apply; checksum từng bảng/tệp phải khớp, mã GV cũ dùng được, bài xuất bản/điểm/ảnh/job đúng. Không bật app chỉ vì /health200.
7. Chuẩn bị GitHub source-only bằng scripts/prepare_release.py, chỉ upload thư mục release mới. Không push tự động. CI Linux mới trong .github/workflows/check.yml khai báo Postgres18 nội bộ runner và Moto; chưa chạy CI từ xa trong phiên này.
8. Render: dùng render.yaml Free mới, **khôngdisk**, mộtinstance/worker, autoDeployOff. ADVENTURE_DATA_DIR=/tmp/english-ai-cache chỉ để cache. Copy các secret bằng Environment UI, không buildarg/VITE/log. Đặt ADVENTURE_PG_SCHEMA/S3_PREFIX khớp bộ migration đã verify, PGSSLMODE=require. Maintenancemode=1 và IMPORT_READY=no ban đầu. Không dùng Render Shell/SCP cho Free: Free không có tính năng đó.
9. Netlify:base frontend, build npm run build:netlify, publish dist; BACKEND_ORIGIN=https://english-ai-adventure.onrender.com. APIproxy trước SPA fallback. Không đặt S3/Gemini/DB secrets ở Netlify. Domain thật phải khớp exact Origin/Host allowlist trên Render, không dùng wildcard preview.
10. HARRY tự quyết định push/deploy phiên bản đã kiểm. Sau khi cloud trỏ đúng schema/prefix verified mới đặt IMPORT_READY=yes và MAINTENANCE=0. Không xóa bản local, schema/prefix cũ hoặc backup. Kiểm tra cookieSecure/HttpOnly, refresh/logout, upload nhỏ, AI job, duyệt/xuất bản, ẩn danh chơi cả5 môn và điểm/history. Mọi lần gọi Gemini thật ở cloud cần tính vào quota; chưa làm ở phiên này.
11. Restart/spindown để kiểm thử dữ liệu/job/partialupload vẫn có ởPG/S3. Đây là nghiệm thu thực trên Render Free, chưa được thay bằng kết quả local.

## 7. Backup/rollback sau cutover

- Không backup `/tmp` và cho rằng đó là dữ liệu chính. PG+S3 mới là nguồn bền vững.
- Neon S3 có APIversioning/lifecycle nhưng tài liệu nói các cơ chế đó không được thực thi đầy đủ; không dựa vào versioning để phục hồi ảnh/metadata đã ghi đè.
- Bật maintenance ở **dịch vụ thật**, đợi mọi writer/job ngừng; không có SDK/Gemini đang running. Chốt quota trước khi tải toàn bộ ảnh về.
- Script cloud_backup.py mở transaction PostgreSQL REPEATABLE READ READ ONLY, ghi vào thư mục local MỚI, stream tệp S3 và kiểm checksum. Cờ --writers-stopped chỉ là xác nhận của người vận hành, không tự đóng production:

```powershell
backend/.venv/Scripts/python.exe scripts/cloud_backup.py --into private-backups/cloud-YYYYMMDD --writers-stopped
```

Cấu hình tiến trình backup trỏ đúng schema/S3 prefix và cloudguard, không truyền secret trên CLI. Script này mới được kiểm thử với PGloopback/S3 mô phỏng, chưa chạy đọc toàn bộ Neon production vì chưa có cutover.

- Sau khi backup PASS, có thể đóng gói thư mục SQLite/media đó bằng data_bundle.py để giữ offline, kiểm tra integrity và copy ngoài máy chủ. Bản này chứa session/mã GV/tài liệu riêng, phải bảo vệ như secret.
- Nếu rollbackcode: chọn phiên bản tương thích với schema, giữ nguyên dữ liệu. Nếu rollbackdata: import bản tốt vào schema+prefix mới hoặc thư mục local mới, verify trước khi đổi con trỏ. Không ghi đè/xóa schema đang dùng.
- Nếu sau cutover có lượt học mới, backup mới phải giữ chúng; không đưa snapshot cũ lên rồi làm mất các lượt mới. Tool rollback rehearsal cố ý kiểm checksum, không tự merge điểm từ hai phiên bản.
- Quay lại SQLitelocal chỉ khi đã chuyển người dùng khỏi cloud để tránh hai nơi cùng ghi; đặt CLOUD_ENABLE=no, DATABASE_BACKEND=sqlite, STORAGE_BACKEND=local và ADVENTURE_DATA_DIR trỏ thư mục rollback đã verify. Không sửa bản gốc để che lỗi.

## 8. Giới hạn thật và những mục chưa nghiệm thu

Theo tài liệu hiện hành, [Render Free](https://render.com/docs/compute-plans) là0,1 CPU/512 MB, cóspindown15 phút, khôngPersistentDisk/Shell và có thểrestart. [Render Free limitations](https://render.com/docs/free) còn giới hạn traffic khởi tạo tớiDB/API/objectstorage. Không tự nâng gói nếu chạm giới hạn.

[Neon ObjectStorage](https://neon.com/docs/storage/overview) Free có5 GB/project; object singlePUT tối đa5 GiB/multipart10 GiB. [Compatibility](https://neon.com/docs/storage/s3-compatibility):path-style, SigV4; bucket gắn branch, không chỉ region; versioning/lifecycle không được thực thi nhưAWSS3. Bucket visible0 byte trước probe không chứng minh toàn project còn đủ quota khác.

LocalWindows đoPPTX70 MB:10 slide/18 ảnh, khoảng305 MB RSS tiếntrình con+cảlauncher,2,3 CPUgiây/2,73 wallgiây. Đo ở local storage/renderCOMtắt, **không phải số đo của Linux hoặc cloudruntimeS3**, không suy ra Free chắc chắn đủRAM/CPU. Máy có đăng ký Ubuntu nhưng không boot được do HCS feature thiếu; không tự cài/tắt/bật tính năngWindows.

Chưa triển khai code mới nên chưa đoRAM/CPU/coldstart/throughput thật trên Render Free, chưa chạy70 MB qua endpointupload production, chưa chạy job PostgreSQL trên cloud hay restart/cloudrollback. Các mục này là NOT_TESTED, không phải PASS vì healthok.

PPTX chữ/ảnh nhúng vẫn đọc; PowerPointCOM không có trên Linux. Giữ mọi rendercache/PNG đã tạo khi migration. Filemới có nhóm/vector/mấtngữcảnh cần giáo viên kiểm duyệt; có thể xuấtPDFtrênWindows để làm tài liệu mới, không đổi nguồn/đáp án để ép câu qua kiểm định. DOCX chưa renderWord/OCR tổng quát. Giao diện/5 hoạtđộng giữ nguyên và đã regressionlocal; tải đủ nội dung khi chọn bài, không tải hết media chỉ để hiện thư viện.
