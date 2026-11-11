# English AI Adventure

## Chuẩn bị production GitHub + Netlify + Render — 11/11/2026

Đã chuẩn bị cấu hình environment/fallback, disk path, cookie/Origin/Host/CSRF, jobSQLite+polling, upload2MB/phần, backup/restore không ghi đè và release mã nguồn. Giữ giao diện, bài học và lịch sử; chưa push/triển khai/bật billing.

**Bằng chứng local:**69/69backend,25/25Chrome quaHTTPSproxy mô phỏng26s; buildNetlifyPASS; PPTXthật70MB tải34phần→10slide; backup/restore18bài/157lượt/8cache. BộSDKchậm27s dùngstub, không gọiGemini thêm. Một lượt đầu thêm2lượtQA và đổi revision/updated1bài trước khi táchcổng;155lượt cũ/câu hỏi/đáp án không đổi. Sau đó toàn bộE2E dùngbản sao.

[Hướng dẫn triển khai từng bước](docs/DEPLOYMENT.md) · [QA và giới hạn](docs/PRODUCTION_QA.md). RenderPersistentDisk cần gói trả phí, không tự kích hoạt. Cloud/LinuxDocker/SSH/Netlifythật vẫn NOT_RUN; không khẳng định production đã PASS. Linux không renderPPTX bằngPowerPointCOM; giữcache đãmigrate, cảnh báo filemới và đề xuấtPDF khi cần bố cục.

Giới hạnAI hiện tại theo HARRY: **1lượt/30giây**, giữ20lượt/24giờ local, không phải quotaGoogle. Không reset counter cũ.


## Sửa khẩn cấp tạo bài mới — 11/11/2026

Đã kiểm thử Gemini thật, không cache: PDF mới6 trang tạo/lưu/hiển thị6/6 câu; DOCX và TXT2/2 câu mỗi file. PPTX gốc gặp503 thật tại bước5; thử một lần từ bản nháp giữ nguyên nhận6, lưu5 câu hợp lệ (**PARTIAL**, không nhận câu sai). Không thay .env/model/billing.

Bổ sung timeline9 công đoạn, lỗi có origin/stage/reason, kiểm định từng câu, lưu phần hợp lệ, retry không upload lại và tạo bổ sung giữ ID cũ. File và nội dung nguồn giữ trước khi gọiAI. Mạng502, timeout504 được tách khỏi upstreamGemini503. Giáo viên vẫn cần duyệt.

Kiểm thử: build PASS;54/54 backend;20/20 Chrome,5 hoạt động,3 viewport;118 lượt học cũ không đổi. Bằng chứng và giới hạn: [QA sửa tạo bài mới](reports/phase4/QA_REPORT.md). Website: http://127.0.0.1:8000/ → Thư viện → `QA phase4 de-thi-hoc-ki…` để kiểm duyệt bàiPDF mới. `QA phase4 Unit6…` còn thiếu1 câu vocabulary; xem PARTIAL và dùng tạo bổ sung khi phù hợp.


Website tiếng Anh lớp 3–5 cho giáo viên và học sinh 8–11 tuổi, chạy độc lập với ChatGPT. React + TypeScript + FastAPI + SQLite. Chủ dự án: HARRY.

**Đã có luồng hoạt động thật:** tải tài liệu → Gemini tạo hoạt động → sửa/duyệt từng câu → xuất bản → học sinh chơi → lưu điểm → giáo viên xem kết quả. Kết quả và giới hạn tại `STATUS.md`.

## Giai đoạn 3: học liệu có đủ dữ kiện

Đã sửa pipeline ảnh và kiểm định lại ngân hàng. Báo cáo: [QA giai đoạn 3](reports/phase3/QA_REPORT.md). Bài DOCX gốc đã được tìm lại đúng hash, gồm ảnh VML bị reader cũ bỏ sót. Các mệnh đề Đúng/Sai blue/pink từng bị hiểu sai thành sự thật; đoạn đọc gốc nói **cặp yellow, sách red**. Hai câu cũ giữ lịch sử và tạm ẩn; hai bản thay thế có ảnh gốc, đoạn đọc/lời nghe đúng nguồn. Chơi bài đã sửa: http://127.0.0.1:8000/#/play/764F4A78.

Tài liệu tải lên nay được giữ tại `backend/data/sources`, ảnh PNG tại `backend/data/media`, render PPTX tại `backend/data/render-cache`; các thư mục đều nằm trong vùng private đã ignore. Không xóa media/source nếu muốn bài đã lưu tiếp tục có đủ ảnh.

Quy trình giáo viên bổ sung:

1. Xem gallery ảnh theo đúng phần nguồn. Ảnh chưa phân loại/duyệt chưa được dùng làm bằng chứng.
2. Có thể bấm AI phân tích tối đa 6 ảnh của phần nguồn; kết quả cache, vẫn cần giáo viên xác nhận. Phân loại học liệu/trang trí/icon/nền/ngữ cảnh, kiểm tra ảnh có nhãn đáp án.
3. Gán bằng chứng JSON subject/attribute/value. `basis=pixels` cho điều nhìn thấy; `basis=source_text` cho sự thật trong đoạn đọc đã kiểm định. Không dùng mệnh đề Đúng/Sai làm sự thật. Có ô nhập và xác nhận đoạn đọc trong ảnh.
4. Nếu ảnh lộ đáp án hoặc có nhiều đối tượng, tạo vùng cắt bằng tọa độ trái/trên/phải/dưới từ 0 đến 1, giữ trọn đối tượng. Ảnh cắt mới cần kiểm định lại; quan hệ nhóm/vị trí thiếu ngữ cảnh không tự được chấp nhận.
5. Trong từng câu, chọn loại dữ kiện, đúng ảnh nguồn, vật thể/thuộc tính, mô tả và đoạn đọc nếu cần. Server kiểm tra lại, không tin cờ valid của client. Câu đọc hiểu hiển thị đoạn nguồn; hình đen trắng không tự chứng minh màu sắc.
6. Preview ảnh/cảnh báo, lưu và duyệt từng câu. Có tạm ẩn và yêu cầu AI tạo lại từ nguồn; câu cũ giữ ẩn, câu mới cần duyệt. Chế độ “Chỉ tạo câu từ ảnh đã kiểm định” không thay bằng câu chữ khi thiếu ảnh.
7. Bài cũ thiếu source có nút **Khôi phục đúng tài liệu gốc**; server so hash, không gán ảnh từ file khác.

Cả năm hoạt động hiển thị ảnh gần câu hỏi với đúng tỷ lệ. Ảnh bắt buộc lỗi thì khóa nút/input, cho bỏ qua không trừ điểm. Toàn bộ câu bỏ qua thì không chấm 0. Ảnh minh họa tùy chọn cho câu đọc/nghe không thay thế bằng chứng từ chữ/âm thanh. Native PPTX render cần PowerPoint trên Windows; nếu không có, giữ ảnh trích được và cảnh báo, không đoán ngữ cảnh. DOCX dùng đoạn, chưa render trang Word tổng quát; chưa OCR tự động.

## Chạy nhanh trên Windows

Mở `START-WEBSITE.cmd`, giữ cửa sổ server hoạt động. Hoặc chạy PowerShell:

```powershell
Set-Location E:\English-AI-Adventure
backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

- Giáo viên: http://127.0.0.1:8000/
- Học sinh: http://127.0.0.1:8000/#/play
- Health check: http://127.0.0.1:8000/api/health

Mở `backend/data/teacher-access.txt` để lấy mã đăng nhập giáo viên. File được tạo trong lần khởi động đầu. Đây là mã quản trị local, khác API Key; không đưa cho học sinh. Phiên cookie HttpOnly/SameSite Strict hết hạn sau 12 giờ.

Backend phục vụ cả bản build React, không cần chạy Node/npm thường trực. Nhấn Ctrl+C để dừng. Nếu port 8000 đã được dùng, dừng server cũ trước khi mở lần nữa.

## Cài lại và phát triển

Đã có `.venv`, `node_modules`, `dist`. Nếu cài lại, cần Python 3.11+, Node.js 22+, npm và uv. Không dùng alias Python Windows Store.

```powershell
Set-Location E:\English-AI-Adventure
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
uv venv backend/.venv --python 3.11
uv pip sync --python backend/.venv/Scripts/python.exe backend/requirements.lock.txt
Set-Location frontend
npm.cmd ci
npm.cmd run build
```

Chế độ phát triển: giữ backend chạy, mở terminal thứ hai tại `frontend`, chạy `npm.cmd run dev`, truy cập http://127.0.0.1:5173. Vite proxy `/api` tới port 8000. Nếu máy ít RAM, build tuần tự:

```powershell
$env:NODE_OPTIONS = '--max-old-space-size=192 --max-semi-space-size=4'
npm.cmd run build
```

Giữ `backend/.env` hiện có. Model đang dùng `gemini-3.5-flash-lite`. Không đưa khóa vào frontend, log, database hoặc GitHub; ứng dụng không sửa `.env`, tự đổi model, bật billing hoặc dùng tool trả phí.

## Giáo viên

1. Đăng nhập, chọn **Tạo bài học**, tải PPTX/PDF/DOCX/TXT tối đa 100 MB. PowerPoint mẫu khoảng 67 MB.
2. Kiểm tra nội dung nguồn: PPTX theo slide, PDF theo trang, DOCX/TXT theo đoạn. Giữ ảnh và render PDF scan để kiểm định; chưa OCR tự động. DOCX không suy đoán số trang in.
3. Chọn lớp 3–5, độ khó, 1–20 câu và loại hoạt động. Đủ 5 hoạt động cần tối thiểu 6 câu vì ghép từ cần 2 cặp.
4. Bấm **Tạo bằng Gemini AI**. Mỗi lượt một yêu cầu, timeout 45 giây, không tự retry. Yêu cầu giống nhau dùng cache. Giới hạn local 1 lượt/30 giây, 20 lượt/24 giờ, không phải quota Google.
5. Đối chiếu câu hỏi, đáp án, giải thích, nguồn. Có thể sửa/xóa/thêm câu. Kiểm tra tiếng Việt đủ dấu và câu nghe có thông tin đáp án, không chỉ đọc câu hỏi.
6. **Lưu thay đổi**, đánh dấu từng câu đã kiểm tra rồi lưu tiếp. Câu mới/vừa sửa tự bỏ dấu duyệt. Nguồn, schema và dữ liệu chơi được backend kiểm tra.
7. **Xuất bản**, chia sẻ mã/liên kết. Bài chưa duyệt hết không thể xuất bản. Muốn sửa bài đã xuất bản: **Thu hồi bài** trước.
8. Xem **Kết quả học sinh**, bấm **Làm mới**. Điểm được backend chấm, không nhận điểm tự khai từ frontend.

Muốn tạo bộ AI khác: xóa các câu hiện tại và lưu trước. Hệ thống không tự ghi đè nội dung đang soạn. Kiểm tra schema/trích dẫn không thay thế kiểm duyệt sư phạm.

## Học sinh

Nhập mã hoặc mở liên kết, chơi cả hành trình hoặc từng hoạt động. Không cần tài khoản, tên, email, ngày sinh.

- Learn Vocabulary: thẻ từ, minh họa được giáo viên chọn, giọng đọc, chọn nghĩa.
- Quiz Challenge: chọn đáp án.
- Match the Words: ghép từ với nghĩa tiếng Việt.
- Listen & Choose: nghe câu tiếng Anh rồi chọn đáp án.
- Fill in the Blanks: điền từ vào `___`.

Mỗi câu/cặp tính lần trả lời đầu, có đúng/sai, giải thích và điểm. Điểm = số đúng / tổng số × 100. Lượt gần nhất lưu mã trong localStorage để tiếp tục. Mỗi lượt có snapshot riêng, không bị sửa theo bài học về sau.

Giọng đọc dùng Web Speech API của trình duyệt/hệ điều hành. Khi không hỗ trợ/phát lỗi, có thông báo và bản chữ để tiếp tục. Dùng bản chữ là đọc hiểu, không nghiệm thu kỹ năng nghe. Cần thử chất lượng âm thanh trên thiết bị trình diễn. Có minh họa SVG giới hạn và gallery ảnh nguồn thực; giáo viên chọn/duyệt hình phù hợp. Không tự lấy hình trên Internet hoặc suy ra vật thể từ filename.

## Trình diễn khi mất Gemini

- `Our school facilities`: bản nháp từ PowerPoint gốc, đủ 5 hoạt động và câu AI đã lưu giai đoạn 1; giáo viên có thể xem, duyệt và xuất bản.
- Bài mang tên PowerPoint gốc được Gemini tạo thật qua backend, sửa tiếng Việt/nội dung nghe, duyệt và xuất bản trong kiểm thử Chrome. Mã xem tại dashboard hoặc `reports/browser-published-lesson.json`.
- Các bài xuất bản vẫn chơi được khi Gemini/internet mất kết nối, miễn backend còn chạy. Giao diện ghi **Bài học đã lưu**, không coi đây là AI trực tuyến. Chưa hỗ trợ chơi khi cả backend bị tắt.
- Trên máy mới chưa có database, bài mẫu được tạo ở trạng thái nháp; cần duyệt/xuất bản, không cần gọi AI mới.

## Dữ liệu và phạm vi vận hành

`backend/data/adventure.sqlite3` lưu bài học, câu hỏi, cache, lượt chơi ẩn danh, điểm và phiên giáo viên. `teacher-access.txt` chứa mã quản trị. File upload trung gian được xóa, nhưng bản nguồn và media được giữ riêng để kiểm định/phục hồi. Chỉ khi giáo viên bấm tạo/phân tích, chữ và các ảnh đã chọn/kiểm định mới được gửi tới Gemini. Sao lưu cả `backend/data` khi đã dừng server, giữ bản sao riêng tư.

`.env`, `backend/data/`, `.venv`, cache, node_modules và dist được Git ignore. Thư mục dự án hiện chưa có Git repository. Không dùng `git add -f` cho dữ liệu riêng.

Bản hiện tại phục vụ local/một giáo viên. Chưa triển khai internet, HTTPS, nhiều tài khoản, kiểm thử tải lớn hay xâm nhập. Muốn dùng LAN cần cấu hình host/firewall và chia sẻ IP máy chủ; `127.0.0.1` chỉ dùng trên máy đang chạy. Chưa nghiệm thu thiết bị LAN thực tế.

## Kiểm thử và bằng chứng

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/test_app.py backend/test_visual.py -q
backend/.venv/Scripts/python.exe scripts/check_delivery.py
Set-Location frontend
npm.cmd run build
npm.cmd run test:e2e
```

Pytest dùng database tạm và Gemini giả lập cho lỗi, không gọi AI. Playwright cần Chrome đã cài và server port 8000. E2E sửa/xuất bản bài có ID trong `reports/phase2-live.json`; chạy trên dữ liệu trình diễn. `scripts/live_phase2.py` có một yêu cầu Gemini thật, chỉ chạy khi cần và còn Free Tier, không nằm trong pytest.

Bằng chứng mới nhất: `reports/phase3/QA_REPORT.md`, `reports/phase3/backend-tests.txt`, `reports/phase3/browser-run.txt`, `reports/phase3/audit-final.json`. Bằng chứng giai đoạn 2 giữ làm lịch sử: `reports/backend-tests.txt`, `frontend-build.txt`, `phase2-live.json`, `browser-tests.json`, `browser-run.txt`, `delivery-check.json`. Ảnh giao diện thật tại `reports/screenshots/`.

## Cấu trúc

```text
backend/             FastAPI, AI, schema, đọc tài liệu, kiểm thử
frontend/            React + TypeScript + CSS + Playwright
scripts/             Công cụ và kiểm thử giai đoạn 1–2
input/               PowerPoint và PDF gốc giữ nguyên
reports/             Bằng chứng kiểm thử, ảnh giao diện
START-WEBSITE.cmd    Chạy bản local Windows
PLAN.md / STATUS.md  Kế hoạch và kết quả thực tế
```

Kết quả giai đoạn 1 giữ nguyên. Parser PPTX bổ sung đường đọc XML tiết kiệm RAM và đối chiếu với văn bản/số ảnh trước đó. [Google pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite) xác nhận Free Tier input/output; [hạn mức](https://ai.google.dev/gemini-api/docs/rate-limits) phụ thuộc dự án. HARRY đã xác nhận Plan Free; không suy ra quota còn lại hay hóa đơn từ API Key.
