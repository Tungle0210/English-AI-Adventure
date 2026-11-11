# Triển khai English AI Adventure: GitHub → Netlify + Render

Tài liệu dành cho HARRY. Đây là **bản chuẩn bị**, chưa có website production được triển khai. Không có thao tác push, tạo dịch vụ, mua gói hay bật billing được thực hiện tự động.

## 1. Kiến trúc và chi phí cần hiểu trước

- Người dùng mở `https://TEN-TRANG.netlify.app`. React gọi `/api/...` cùng tên miền đó.
- Netlify chuyển `/api/*` tới `https://TEN-API.onrender.com/api/*`. Trình duyệt không gọi chéo miền Render, không cần bật CORS.
- Render chạy một tiến trình FastAPI, một worker nội bộ và một SQLite. SQLite, nguồn tài liệu, ảnh, render cache, job, mã giáo viên đều ở `ADVENTURE_DATA_DIR=/var/data/adventure`, bên trong disk mount `/var/data`.
- Render Persistent Disk **không có trên Free Web Service**, cần gói trả phí. `render.yaml` có `plan: starter`, disk5GB: đây là mẫu, **không phải cam kết giá hoặc đã kích hoạt**. Chỉ tiếp tục tạo dịch vụ khi HARRY chấp nhận chi phí hiển thị trong tài khoản. Không có phương án SQLite bền vững tương đương nếu bỏ disk và dùng filesystem tạm.
- Không tăng số instance hoặc Uvicorn workers. Disk chỉ gắn một instance; job worker không phải một Render Background Worker riêng vì không thể chia sẻ disk đó. Deploy có thời gian gián đoạn. Không chạy hai phiên bản cùng ghi một SQLite.
- Không chuyển GEMINI_API_KEY sang Netlify, GitHub hay biến VITE_*. Gemini vẫn dùng dự án/model hiện có; không tự đổi model/tier/billing.

Nguồn đã đối chiếu: [Render Persistent Disks](https://render.com/docs/disks), [Render Free limitations](https://render.com/docs/free), [Netlify proxy26s](https://docs.netlify.com/manage/routing/redirects/rewrites-proxies/), [Render Blueprint](https://render.com/docs/blueprint-spec).

## 2. Chuẩn bị mã nguồn để đưa lên GitHub

1. Mở PowerShell tại thư mục dự án. Chạy:

```powershell
Set-Location E:\English-AI-Adventure
backend/.venv/Scripts/python.exe scripts/prepare_release.py
```

Bản bàn giao đã chuẩn bị ở `deploy/release-ready`; không sửa trong đó rồi bỏ qua kiểm thử. Các lệnh trên dùng khi tạo lại một bản mới.

2. Chỉ dùng **nội dung bên trong `deploy/release-ready` (bản bàn giao) hoặc thư mục release mới do script tạo** để upload GitHub. Script từ chối ghi đè thư mục release có sẵn; lần tạo mới có thể thêm `--output deploy/release-v2`. Script kiểm tra key trước khi tạo bản mã nguồn.
3. Tạo một repository **Private** trên GitHub, tên ví dụ `English-AI-Adventure`. Chọn **Add file → Upload files**, tải nội dung release, giữ nguyên cây thư mục. Đừng upload cả thư mục dự án gốc. Không upload file ZIP dữ liệu, `backend/.env`, `backend/data`, `input`, `reports`, `private-backups` hoặc `private-production-data`.
4. Kiểm tra repository có `Dockerfile`, `render.yaml`, `netlify.toml`, `backend`, `frontend`, `scripts`, `docs`. Các file bắt đầu bằng dấu chấm như `.dockerignore` cũng cần có. Không upload một file ZIP và kỳ vọng GitHub tự giải nén.
5. GitHub Actions `Production checks (no deployment)` chỉ kiểm thử, không có deploy token/action triển khai. Chờ kiểm thử Linux xanh **trên tài khoản thật** trước khi vận hành. Các test cần bài giảng riêng không chạy trong CI public-code; bộ production dùng tài liệu tự tạo, không gọi Gemini.

Không có repository Git hiện hữu được cấu hình trong thư mục làm việc tại thời điểm chuẩn bị, nên chưa thể kiểm tra lịch sử commit từ xa. Nếu sử dụng repo khác đã có lịch sử, kiểm tra toàn bộ lịch sử secret trước khi cấp quyền Render/Netlify.

## 3. Backup dữ liệu thật trên Windows — không bỏ qua

1. Đợi các tác vụ AI hoàn tất, không cho giáo viên/học sinh thao tác trong lúc backup. Dừng backend bằng Ctrl+C trong cửa sổ đang chạy. Đừng chỉ đóng tab trình duyệt. Kiểm tra không còn tiến trình backend khác đang ghi cùng thư mục.
2. Trong PowerShell:

```powershell
Set-Location E:\English-AI-Adventure
New-Item -ItemType Directory -Force private-backups
backend/.venv/Scripts/python.exe scripts/data_bundle.py export --data backend/data --output private-backups/production.data-bundle.zip --offline
backend/.venv/Scripts/python.exe scripts/data_bundle.py verify --bundle private-backups/production.data-bundle.zip
```

Tên output phải chưa tồn tại. `--offline` là xác nhận của người vận hành rằng mọi writer đã dừng, không phải chức năng tự tắt server. Không dùng gói đang ghi dở; chỉ dùng khi verify PASS.

3. Gói có SQLite snapshot qua SQLite backup API, toàn bộ source/media/render-cache/jobs/upload tạm và mã giáo viên; có SHA-256 từng file, kiểm tra integrity và số bài/lượt/cache. Không có file `.env`. **Gói vẫn chứa dữ liệu và mã đăng nhập riêng tư**, không đưa lên GitHub/Netlify hoặc URL công khai. Lưu thêm một bản ngoài máy chủ production ở nơi chỉ HARRY truy cập.
4. Diễn tập nhập vào thư mục mới trước:

```powershell
backend/.venv/Scripts/python.exe scripts/data_bundle.py import --bundle private-backups/production.data-bundle.zip --into private-production-data/migration-test
```

Script từ chối thư mục đích đã có dữ liệu. Không xóa dữ liệu cũ để vượt qua chặn đó. Nếu tên đích đã tồn tại, dùng một tên mới. Đây cũng là nguyên tắc rollback.
5. Giữ nguyên bản local gốc và backup. Sau khi chốt bản backup để cutover, không tiếp tục cho người dùng ghi vào local và production đồng thời: các lượt phát sinh thêm ở local sẽ không tự đồng bộ lên cloud.

## 4. Tạo frontend Netlify và ghi lại tên miền

HARRY thực hiện trên tài khoản của mình khi sẵn sàng triển khai:

1. Netlify → Add new project / Import from Git → chọn repo Private đã chuẩn bị. Ghi lại/chọn tên site cố định, ví dụ `english-adventure-harry.netlify.app`.
2. Build base: `frontend`; command: `npm run build:netlify`; publish: `dist`. `netlify.toml` đã khai báo các giá trị này. Node22.
3. Chưa có API Render URL thì chưa cần công bố site cho học sinh. Build sẽ **fail rõ ràng** nếu thiếu `BACKEND_ORIGIN`; không tự trỏ về localhost hay API mẫu.
4. Chỉ khai báo `BACKEND_ORIGIN=https://TEN-API.onrender.com` ở Netlify khi đã có URL thật ở bước5. Không có `/api` ở cuối. Không đặt key Gemini tại Netlify. Script build sinh `frontend/dist/_redirects` với API proxy đứng trước SPA fallback.
5. Giới hạn bản production này vào một site/domain rõ ràng. Deploy Preview từ URL khác bị CSRF chặn theo thiết kế. Nếu muốn staging, dùng backend/data/teacher-code riêng và allowlist chính xác domain staging; không dùng wildcard `*.netlify.app` hay cho preview tùy ý truy cập dữ liệu thật.

## 5. Tạo Render ở chế độ bảo trì trước

1. Render → New → Blueprint → chọn repo và file `render.yaml`. Xem kỹ chi phí service+disk trước khi đồng ý tạo. Không chọn Free vì không có disk. Có thể cấu hình thủ công Docker service theo các giá trị trong mẫu thay cho Blueprint.
2. Giữ một instance. Dockerfile ở root. Health endpoint `/api/health`. Auto deploy **Off**. Disk mount `/var/data`,5GB là giá trị ban đầu; tăng theo dung lượng giải nén+backup+ảnh phát sinh, không chỉ kích thước ZIP. Chưa có load test RAM trên cloud nên không khẳng định gói Starter đủ cho mọi file100MB.
3. Environment trên Render:

| Biến | Giá trị cần đặt |
|---|---|
| ADVENTURE_ENV | production |
| ADVENTURE_DATA_DIR | /var/data/adventure |
| ADVENTURE_MAINTENANCE | 1 |
| ADVENTURE_IMPORT_READY | no |
| ADVENTURE_ALLOWED_ORIGINS | https://TEN-TRANG.netlify.app — chính xác, không dấu / cuối |
| ADVENTURE_ALLOWED_HOSTS | TEN-API.onrender.com — chỉ hostname, không https:// |
| WEB_CONCURRENCY | 1 |
| ADVENTURE_RENDER_PPTX | 0 |
| GEMINI_API_KEY | sao chép **khóa hiện có** bằng giao diện Environment; không dán vào terminal/log/tài liệu |
| GEMINI_MODEL | model đang dùng trong backend/.env, hiện gemini-3.5-flash-lite |

Nếu có custom domain, thêm chính xác origin HTTPS vào ALLOWED_ORIGINS, các hostname backend hợp lệ vào ALLOWED_HOSTS, ngăn cách bằng dấu phẩy. Không đặt domain Netlify vào cookie Domain.

4. Khi service ở maintenance, `/api/health` trả `status=maintenance`, API khác trả503. App chỉ tạo thư mục trống, **không tạo DB rỗng/mã giáo viên mới/bài mẫu**. Chưa cho học sinh sử dụng.
5. Ghi lại Render URL thật; cập nhật `BACKEND_ORIGIN` của Netlify rồi build lại bằng nút Trigger deploy. Netlify sẽ phục vụ frontend, nhưng API vẫn maintenance cho tới khi migrate xong.

## 6. Chuyển và nhập dữ liệu vào disk

1. Trong Render, thiết lập SSH key theo [hướng dẫn SSH chính thức](https://render.com/docs/ssh). Dùng thông tin SSH của **đúng service** trong Connect. Giữ private key trên máy của HARRY, không upload lên repo.
2. Dùng SCP/SFTP theo [hướng dẫn chuyển file vào disk](https://render.com/docs/disks#transferring-files). Ví dụ PowerShell — thay USER/HOST bằng thông tin Connect, không chạy nguyên placeholder:

```powershell
scp "E:\English-AI-Adventure\private-backups\production.data-bundle.zip" USER@HOST:/var/data/production.data-bundle.zip
```

Nếu client cần giao thức SFTP, dùng tùy chọn theo tài liệu Render/phiên bản OpenSSH hoặc mở `sftp USER@HOST`, rồi `put` gói vào `/var/data`. Không upload ZIP lên đường dẫn public để dùng wget. Bước truyền SSH/SCP chưa được chạy trên tài khoản thật trong phiên chuẩn bị.

3. Mở Shell của **service đang chạy** (disk chỉ có ở runtime; không dùng build/pre-deploy/one-off job để nhập disk). Chạy:

```sh
cd /app
python scripts/data_bundle.py verify --bundle /var/data/production.data-bundle.zip
python scripts/data_bundle.py import --bundle /var/data/production.data-bundle.zip --into /var/data/adventure
```

Đích được phép chưa tồn tại hoặc trống; nếu đã có dữ liệu, script từ chối. Không xóa DB có sẵn. Chọn `/var/data/adventure-migrated-v2` rồi cập nhật ADVENTURE_DATA_DIR nếu cần một lần nhập mới, giữ nguyên thư mục cũ.

4. Đối chiếu số lessons/attempts/cache với kết quả backup local. Mở site ở môi trường kiểm tra và đối chiếu ảnh, bài xuất bản, lịch sử điểm. Không gửi lại yêu cầu Gemini cũ để “khôi phục” bài: dữ liệu đã nằm trong SQLite và media.
5. Trong Render Environment, đổi `ADVENTURE_IMPORT_READY=yes`, `ADVENTURE_MAINTENANCE=0`, giữ data path đúng thư mục vừa nhập, rồi deploy thủ công. App sẽ từ chối startup nếu DB/mã giáo viên thiếu. Không tự seed/audit sửa học liệu trong production.
6. Đăng nhập bằng **mã giáo viên local cũ** vì đã được chuyển cùng dữ liệu. Lấy mã từ file local bằng trình soạn thảo riêng, không dán mã vào issue/log/public screenshot.

## 7. Kiểm tra trước khi công bố cho lớp

- Mở từ URL Netlify thật; login, reload vẫn giữ phiên; logout chặn lại thư viện/kết quả/job. Cookie ở tên miền Netlify có Secure/HttpOnly/SameSite=Strict/Path=/api, không có Domain. Không gọi trực tiếp Render từ JavaScript, không đổi SameSite=None để chữa lỗi proxy.
- Nếu403: kiểm tra Origin chính xác ở Render, Host backend, không dùng URL Preview khác allowlist. Không tin X-Forwarded-Host/Proto gửi từ client; server không dùng chúng để bỏ qua CSRF.
- Tải TXT, DOCX, PDF6 trang và PPTX thật. Frontend chia2MB/request, file tổng tối đa100MB, trích xuất trong job; kiểm tra giới hạn body/time thực của Netlify ở tài khoản đang dùng. Chưa đo thông lượng mạng/upload100MB trên cloud.
- Tạo AI: HTTP202 trong vài giây, sau đó GET `/api/jobs/{id}` ngắn. Poll không gọi Gemini lại. Reload trang sẽ tiếp tục theo dõi job. Job lưu queued/running/succeeded/failed/interrupted trên disk. Job queued có thể chạy sau restart; job đang running lúc crash được đánh dấu interrupted, **không tự retry** vì chưa biết Google đã xử lý/ghi bài hay chưa. Kiểm tra bản nháp trước khi bấm lại.
- Gửi trùng cùng Idempotency-Key trả cùng job; một bài chỉ có một job đang chờ/chạy. Hoàn tất AI vẫn cần giáo viên duyệt/xuất bản. Bài đã lưu chơi không gọi Gemini.
- Mở cửa sổ ẩn danh, chơi cả5 hoạt động, kiểm tra ảnh, điểm và kết quả giáo viên. Kiểm tra điện thoại/tablet. Chỉ sau đó cho lớp truy cập.
- Restart/deploy Render và kiểm tra lại lessons/attempts/media/jobs. Đây là bước cloud quan trọng **chưa thể PASS trước khi HARRY triển khai thật**.

## 8. Khác biệt Windows/Linux

| Tính năng | Render Linux |
|---|---|
| PPTX chữ, ảnh raster nhúng/crop/metadata | Có cùng reader; cần kiểm thử file thật sau deploy |
| PowerPoint COM xuất toàn slide mới | **Không có** trên Linux; không cài PowerPoint qua script |
| Render cache/ảnh đã tạo trên Windows | Được chuyển nguyên cùng data, tái dùng theo hash nguồn; không render lại tùy tiện |
| Nhóm/vector/EMF/ảnh mất ngữ cảnh | Có thể không chuyển được; giữ cảnh báo và chặn câu thiếu dữ kiện |
| PDF chữ+render trang/raster | PyMuPDF/pypdf; PDF scan chưa OCR |
| DOCX | Trích đoạn/ảnh DrawingML/VML; không có phân trang/render Word tương đương |
| Nghe Web Speech API | Phụ thuộc trình duyệt/thiết bị và giọng cài đặt; vẫn có thông báo khi không hỗ trợ |

Nếu cần giữ bố cục một bài PPTX mới trên Linux, xuất bản PDF từ PowerPoint trên Windows rồi tải **PDF như một tài liệu mới**. Không dùng PDF để khôi phục nguồn PPTX theo hash và không gán ảnh khác nguồn. Không khẳng định bản render PDF và PowerPoint giống tuyệt đối; giáo viên vẫn kiểm duyệt.

## 9. Backup định kỳ và rollback

Không có lịch backup tự động/offsite được bật trong phiên này. HARRY cần quy trình định kỳ sau deploy:

1. Đợi job hoàn tất. Bật ADVENTURE_MAINTENANCE=1 và deploy thủ công; worker cũ có thể bị shutdown khi đang gọi Google nên phải kiểm tra job trước. Dừng mọi writer khác. Maintenance vẫn cho health, chặn học sinh/giáo viên ghi thêm.
2. Trong Shell runtime:

```sh
python /app/scripts/data_bundle.py export --data /var/data/adventure --output /var/data/backup-YYYYMMDD.data-bundle.zip --offline
python /app/scripts/data_bundle.py verify --bundle /var/data/backup-YYYYMMDD.data-bundle.zip
```

Thay ngày/tên mới mỗi lần. Tải gói về máy riêng qua SSH/SFTP, verify lại ở máy nhận. Bản backup trên cùng disk **không phải** bản sao ngoài máy chủ.
3. Nếu chỉ lỗi frontend/code: rollback commit/deploy đã biết tốt, giữ nguyên data. Kiểm tra code cũ có tương thích schema mới không; bảng jobs/upload_sessions là thay đổi cộng thêm, không drop bảng cũ. Chưa có code rollback nào chạy trên Render thật.
4. Nếu cần rollback data: giữ maintenance, backup **hiện trạng đang lỗi** trước; import gói tốt vào `/var/data/adventure-rollback-YYYYMMDD` (thư mục mới). Verify counts/images, đổi ADVENTURE_DATA_DIR sang thư mục mới, deploy đúng phiên bản code tương ứng, rồi tắt maintenance. Không ghi đè/xóa thư mục hiện tại.
5. Data rollback không tự merge các lượt học phát sinh sau thời điểm backup. Giữ nguyên thư mục hiện trạng để đối soát/phục hồi có chủ đích; không âm thầm làm mất các lượt mới. Việc chuyển con trỏ path là thao tác HARRY quyết định sau khi xem chênh lệch.
6. Render có snapshot disk nhưng dùng backup ứng dụng/SQLite nhất quán ở đây, không coi snapshot disk là phép phục hồi database đã kiểm chứng. Không xóa disk/service để khắc phục lỗi deploy.

## 10. Những gì chưa được kiểm chứng trên cloud

Chưa push GitHub, chưa chạy CI Ubuntu thật, chưa build Docker trên Linux tại máy này, chưa cấp phát disk, chưa truyềnSCP, chưa kiểm tra header/cookie/body-limit/26s của Netlify thật, chưa đoRAM/CPU/tải đồng thời hoặc restart/rollback Render thật. ProxyHTTPS local và các test là bằng chứng chuẩn bị, không thay thế nghiệm thu production. Xem `docs/PRODUCTION_QA.md` và báo cáo chi tiết local trong `reports/production`.
