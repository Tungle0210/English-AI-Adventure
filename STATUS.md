# Trạng thái English AI Adventure

## Chuẩn bị production GitHub + Netlify + Render — 11/11/2026

Đã chuẩn bị cấu hình environment/fallback, disk path, cookie/Origin/Host/CSRF, jobSQLite+polling, upload2MB/phần, backup/restore không ghi đè và release mã nguồn. Giữ giao diện, bài học và lịch sử; chưa push/triển khai/bật billing.

**Bằng chứng local:**69/69backend,25/25Chrome quaHTTPSproxy mô phỏng26s; buildNetlifyPASS; PPTXthật70MB tải34phần→10slide; backup/restore18bài/157lượt/8cache. BộSDKchậm27s dùngstub, không gọiGemini thêm. Một lượt đầu thêm2lượtQA và đổi revision/updated1bài trước khi táchcổng;155lượt cũ/câu hỏi/đáp án không đổi. Sau đó toàn bộE2E dùngbản sao.

[Hướng dẫn triển khai từng bước](docs/DEPLOYMENT.md) · [QA và giới hạn](docs/PRODUCTION_QA.md). RenderPersistentDisk cần gói trả phí, không tự kích hoạt. Cloud/LinuxDocker/SSH/Netlifythật vẫn NOT_RUN; không khẳng định production đã PASS. Linux không renderPPTX bằngPowerPointCOM; giữcache đãmigrate, cảnh báo filemới và đề xuấtPDF khi cần bố cục.

Giới hạnAI hiện tại theo HARRY: **1lượt/30giây**, giữ20lượt/24giờ local, không phải quotaGoogle. Không reset counter cũ.


## Sửa khẩn cấp tạo bài mới — 11/11/2026

Đã kiểm thử Gemini thật, không cache: PDF mới6 trang tạo/lưu/hiển thị6/6 câu; DOCX và TXT2/2 câu mỗi file. PPTX gốc gặp503 thật tại bước5; thử một lần từ bản nháp giữ nguyên nhận6, lưu5 câu hợp lệ (**PARTIAL**, không nhận câu sai). Không thay .env/model/billing.

Bổ sung timeline9 công đoạn, lỗi có origin/stage/reason, kiểm định từng câu, lưu phần hợp lệ, retry không upload lại và tạo bổ sung giữ ID cũ. File và nội dung nguồn giữ trước khi gọiAI. Mạng502, timeout504 được tách khỏi upstreamGemini503. Giáo viên vẫn cần duyệt.

Kiểm thử: build PASS;54/54 backend;20/20 Chrome,5 hoạt động,3 viewport;118 lượt học cũ không đổi. Bằng chứng và giới hạn: [QA sửa tạo bài mới](reports/phase4/QA_REPORT.md). Website: http://127.0.0.1:8000/ → Thư viện → `QA phase4 de-thi-hoc-ki…` để kiểm duyệt bàiPDF mới. `QA phase4 Unit6…` còn thiếu1 câu vocabulary; xem PARTIAL và dùng tạo bổ sung khi phù hợp.


Phiên kiểm định: 10–11/11/2026 (Asia/Saigon).

## Giai đoạn 3 — P1 dữ kiện hình ảnh đã sửa và kiểm thử

**PASS trong phạm vi QA thực tế:** frontend build, 49/49 backend tests, 18/18 Chrome E2E; đã xem ảnh chụp thật. Báo cáo đầy đủ: [QA giai đoạn 3](reports/phase3/QA_REPORT.md), số liệu máy đọc được: `reports/phase3/audit-final.json`.

- Root cause: pipeline cũ chỉ lưu chữ/số ảnh và xóa file gốc; frontend không có ảnh nguồn chung; schema không chứng minh đủ dữ kiện. DOCX dùng ảnh VML bị bỏ sót, gồm đoạn đọc trong ảnh. AI còn hiểu mệnh đề Đúng/Sai blue/pink thành sự thật.
- Đã tìm đúng `E:\BÀi tập.docx`, hash trùng bản upload cũ, giữ nguyên và bổ sung vào `input/`. Đoạn đọc thực nói cặp **yellow**, sách **red**; tranh đen trắng để tô màu, không suy ra màu từ pixel.
- Kiểm tra 21 câu gốc: 7 câu thiếu/sai dữ kiện, gồm 4 câu thiếu ảnh/ngữ cảnh quan sát. Sửa 5 câu bằng đoạn đọc hiển thị có nguồn; 2 câu blue/pink cũ tạm ẩn, giữ nguyên đáp án/ID. Tạo 2 câu thay thế có ID mới, đúng đoạn đọc và ảnh gốc (Yellow/Red), đã duyệt và chơi thật. Ngân hàng hiện 33 câu gồm câu ẩn và fixture QA.
- 19 lượt cũ được bảo toàn snapshot và câu trả lời cũ: 18 giống từng byte; một lượt đang dở có thêm một câu rồi hoàn thành trong thời gian làm việc, giữ nguyên cập nhật đó. Không rollback hoặc chấm lại điểm lịch sử.
- Lưu ảnh/source lâu dài, provenance theo hash và slide/trang/đoạn, hỗ trợ DrawingML/VML, ảnh raster và render trang PDF. PowerPoint thật có 18 ảnh theo lần xuất hiện và 10 bản render. Có phân loại, kiểm định dữ kiện, crop vùng ảnh không lộ đáp án, preview/chọn ảnh và khôi phục file gốc đúng hash.
- Bổ sung schema hình ảnh, phân biệt bằng chứng pixel/đoạn đọc. Backend kiểm định lại ở AI/cache, lưu, xuất bản và chơi; không tin cờ valid từ client. Chặn ảnh sai, mất, khác nguồn, icon/nền, nhãn đáp án, mệnh đề bài tập sai. AI tạo lại giữ câu cũ ẩn, câu mới cần duyệt.
- Cả 5 hoạt động hiển thị ảnh đúng tỷ lệ; ảnh bắt buộc lỗi thì khóa trả lời và skip không trừ điểm, toàn bộ skip thì không chấm 0. Đã sửa race ảnh cache. Bài lưu không gọi Gemini khi học sinh chơi.
- Gemini thật phân tích ảnh và tạo câu quan sát từ crop trường học; đã kiểm chứng trong Chrome. Có 2 lượt HTTP 503 trong quá trình kiểm thử, sau đó hai yêu cầu thủ công thành công; không tự retry/fallback/bật billing, không sửa `.env`. Bằng chứng `vision-direct.json`, `live-visual-generation.json`.

Mở bài đã sửa nguồn gốc: **http://127.0.0.1:8000/#/play/764F4A78**. Bài AI quan sát từ PPTX thật: **http://127.0.0.1:8000/#/play/1410BBC7**. Fixture QA cặp xanh/táo/vị trí được gắn nhãn riêng, không gán vào bài gốc.

Giới hạn: chưa OCR tự động, chưa render trang DOCX tổng quát hoặc nghiệm thu hiệu quả tại lớp/loa thiết bị. Nhóm/ảnh mất ngữ cảnh phải được kiểm tra hoặc chặn. Các phần giai đoạn 1–2 dưới đây là lịch sử trước sửa P1.

## Giai đoạn 2 — PASS luồng local đã kiểm thử

Ngày thực hiện: 10/11/2026 (Asia/Saigon). Website độc lập với ChatGPT tại **http://127.0.0.1:8000/**, học sinh tại **http://127.0.0.1:8000/#/play**. Hướng dẫn Windows trong README.md và START-WEBSITE.cmd. Không triển khai internet.

### Chức năng đã hoàn thành

- React + TypeScript, FastAPI, SQLite; dashboard giáo viên tiếng Việt và giao diện học sinh riêng với linh vật Ollie bằng SVG, responsive, nút cảm ứng, hỗ trợ giảm animation.
- Mã giáo viên local và phiên HttpOnly; endpoint quản trị/AI yêu cầu xác thực. Học sinh không cần đăng nhập hoặc cung cấp thông tin cá nhân.
- Tải PPTX/PDF/DOCX/TXT tối đa 100 MB, kiểm tra định dạng, kích thước, cấu trúc ZIP và giới hạn nội dung. File tạm xóa sau khi đọc. PowerPoint thật 70.396.372 byte được tải qua backend thành công.
- PPTX theo slide, PDF theo trang, DOCX/TXT theo đoạn (không giả định phân trang DOCX). Xem văn bản nguồn và cảnh báo phần ảnh chưa được phân tích.
- Chọn lớp 3–5, số câu, độ khó, loại hoạt động. Tạo Gemini thật, schema JSON, kiểm tra số lượng/nguồn, cache và khóa chống gọi đồng thời; không tự retry/fallback. Lỗi 404/429/timeout/mất mạng có thông báo, không bật billing.
- Sửa/thêm/xóa câu hỏi, đáp án, giải thích, nguồn và nội dung đọc. Câu mới/sửa bỏ duyệt, phải lưu rồi duyệt lại. Xuất bản yêu cầu tất cả câu được duyệt và dữ liệu chơi hợp lệ. Có thu hồi bài và bảo vệ revision chống ghi đè.
- Mã/liên kết học sinh, Learn Vocabulary, Quiz Challenge, Match the Words, Listen & Choose, Fill in the Blanks. Hướng dẫn, phản hồi đúng/sai, tính điểm phía server, kết quả và tiếp tục lượt gần nhất. Snapshot lượt chơi không bị sửa theo bài học.
- Thư viện và kết quả ẩn danh lưu SQLite, còn nguyên sau restart. Các bài lưu chơi được khi không có AI; ghi rõ là bài đã lưu.

### Kết quả kiểm thử thực tế

| Yêu cầu | Kết quả | Bằng chứng |
| --- | --- | --- |
| Frontend production build / TypeScript | PASS | `reports/frontend-build.txt` |
| Backend khởi động, health, phục vụ React | PASS | server thật port 8000, `reports/restart-check.json` |
| Upload PowerPoint gốc, trích xuất 10 slide và 18 picture shape | PASS | pytest + `reports/phase2-live.json` |
| PDF gốc 5 trang, DOCX/TXT và file sai/trống/quá giới hạn | PASS | `backend/test_app.py`, `reports/backend-tests.txt` |
| Gemini tạo 6 câu đủ 5 hoạt động thực tế qua backend | PASS | `reports/phase2-live.json`, `phase2-generated-response.json` |
| Sửa câu hỏi, duyệt từng câu, xuất bản | PASS | Chrome E2E, `reports/browser-published-lesson.json` |
| Học sinh mở và hoàn thành đủ 5 trò chơi, nhận 100/100 | PASS | Chrome E2E + ảnh student-result-desktop |
| Điểm lưu và hiển thị trong dashboard giáo viên | PASS | E2E + ảnh teacher-results-desktop |
| Laptop/tablet/mobile | PASS ở 1440×1000, 768×1024, 390×844 | `reports/screenshots/`, kiểm tra không tràn; menu và trình duyệt bài trên mobile |
| Thiếu key, lỗi AI 404/429/403/503, timeout, JSON/schema sai, nguồn sai | PASS với giả lập lỗi | 29 kiểm thử backend, không gọi Gemini để gây lỗi |
| Lỗi mạng, mã sai, upload hỏng qua giao diện | PASS | Chrome E2E |
| Trình duyệt không hỗ trợ giọng đọc, bản chữ thay thế | PASS (giả lập thiếu Web Speech API) | Chrome E2E + ảnh student-listen-mobile |
| Dữ liệu còn nguyên sau restart thật | PASS | 2 bài, 6 lượt (3 hoàn thành) ở thời điểm kiểm tra; `reports/restart-check.json` |

**Tổng: 29/29 backend tests và 4/4 Chrome E2E PASS; frontend build PASS.** Các lỗi AI giả lập không được gọi là bằng chứng API lỗi thật. Có một yêu cầu Gemini thành công trong lượt tích hợp, usage trả về 600 input + 516 output = 1.116 token. Trước đó có hai yêu cầu HTTP 400 khi sửa schema truyền tải, tổng 3 yêu cầu generate có kiểm soát, không SDK retry. Không gọi lại để chụp ảnh/chơi bài. Không bật billing; Plan Free theo xác nhận của HARRY, quota còn lại/hóa đơn chưa xác minh qua dashboard.

### Sửa lỗi và kiểm duyệt đã thực hiện

Đã sửa SQL INSERT, tăng giới hạn từ 15 lên 100 MB cho file mẫu, ghi upload theo khối và thêm đọc XML nhẹ để giảm RAM. Văn bản/số ảnh đối chiếu reader cũ. Schema gửi Gemini dùng tập con tương thích; schema đầy đủ kiểm tra tại backend. AI ban đầu trả tiếng Việt không dấu và câu nghe thiếu thông tin đáp án; đã sửa qua giao diện giáo viên, lưu, duyệt từng câu rồi xuất bản. Đã sửa sidebar mobile che nội dung khi đổi kích thước và các locator kiểm thử trước khi ghi nhận PASS. Máy ít RAM từng làm build lỗi; build tuần tự giới hạn heap đã PASS.

### Bài trình diễn và phần còn lại

- `Our school facilities` vẫn là bản nháp 9 câu từ tài liệu gốc và kết quả AI giai đoạn 1, để HARRY xem và tự duyệt.
- `Unit 6 Lesson 2 Period 3`: 6 câu Gemini thật, đã sửa/duyệt/xuất bản trong kiểm thử. Mã **7C320B63**, đường dẫn **http://127.0.0.1:8000/#/play/7C320B63**. Điểm hiện tại gồm dữ liệu kiểm thử ẩn danh, chưa phải minh chứng học sinh thực.
- Chưa OCR, chưa phân tích ảnh/âm thanh nhúng. Có minh họa SVG cho school/building/town/three để giáo viên chọn và duyệt; backend từ chối hình không khớp từ. Bài trình diễn đã duyệt hình school. Từ khác dùng thẻ chữ/giọng đọc; ghép từ với nghĩa tiếng Việt, chưa ghép ảnh tự tải.
- Phát giọng gọi Web Speech API; đã kiểm tra fallback giao diện, **chưa nghiệm thu chất lượng âm thanh qua loa/giọng tiếng Anh trên thiết bị thật**. Bản chữ là phương án đọc hiểu thay thế.
- Khi AI mất mạng vẫn cần backend hoạt động. Chưa có service worker hoặc chế độ tắt cả server mà vẫn chơi.
- Chưa nhiều tài khoản, hosting/HTTPS, thiết bị LAN thật, kiểm thử tải/xâm nhập hoặc thử tại lớp. Đây là bản local dùng chung một mã giáo viên. Không khẳng định đã triển khai production hay đã chứng minh hiệu quả sư phạm.
- Đã đọc PDF yêu cầu của trường để giữ đúng luồng kiểm duyệt, bảo vệ thông tin học sinh và khả năng trình diễn; chưa viết hồ sơ đăng ký/thuyết minh hoặc nộp lên Drive.

Giữ nguyên API Key/model `.env` từ giai đoạn 1 và tài liệu gốc. Mã giáo viên/database nằm trong `backend/data` được ignore. Quét khóa vào file bàn giao và đối chiếu nguồn tại `reports/delivery-check.json`. Các báo cáo giai đoạn 1 phía dưới giữ làm lịch sử.

## Giai đoạn 1 — bằng chứng giữ nguyên

Ngày kiểm tra: 10/11/2026 (Asia/Saigon). Chủ dự án: HARRY.

**Kết quả hiện tại: PASS giai đoạn 1 trong phạm vi môi trường, bảo vệ khóa, trích xuất PowerPoint và Gemini sinh JSON từ slide.**

## Khắc phục Gemini — 10/11/2026, 21:57 (Asia/Saigon)

- Đã đổi duy nhất `GEMINI_MODEL` thành `gemini-3.5-flash-lite` sau khi gọi generate_content và kiểm tra JSON thành công. Giữ nguyên API Key; kiểm tra lại giá trị sau ghi file. Không in khóa hoặc lưu fingerprint của khóa.
- SDK liệt kê 26 model; `gemini-3.5-flash-lite` có `generateContent`. Bằng chứng mới: `reports/models-recovery.json`.
- Bảng giá chính thức xác nhận Standard text input/output của model có Free Tier: [Google pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite). Bản tải để đối chiếu: `reports/google-pricing.md`. HARRY đã xác nhận Plan = Free trong chat; không bật billing hoặc thay đổi tài khoản.
- Hạn mức RPM/TPM/RPD tùy dự án và phải xem tại [AI Studio](https://aistudio.google.com/usage?tab=rate-limit), theo [Google rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Chưa truy cập dashboard riêng để xác minh con số quota còn lại; không suy ra quota từ listModels hay một lần gọi thành công. Thực tế model đã chấp nhận yêu cầu ngắn trong phiên này.
- Tổng trong lượt khắc phục: 2 thao tác liệt kê model, 2 yêu cầu generate_content; SDK retry tắt. Yêu cầu đầu HTTP 400 do `additional_properties` khi dùng response_schema với Pydantic. Đã sửa sang `response_json_schema`. Yêu cầu thứ hai thành công, 96 input + 163 output = 259 token theo usage trả về. Không cần gọi model dự phòng.
- Dùng văn bản trích trực tiếp slide 5 của PowerPoint gốc: “How many buildings are there at Bill’s school? There are three.” Chỉ gửi văn bản slide này, không gửi toàn bộ tài liệu.
- JSON có đúng 3 câu hỏi tiếng Anh, mỗi câu có answer và source_quote. Schema, số lượng, không trùng câu hỏi, số slide và trích dẫn nguồn đều PASS. Chuẩn hóa khoảng trắng để chấp nhận xuống dòng của PowerPoint; tái kiểm tra phản hồi đã lưu, không gọi API lần ba.
- Đã đọc đối chiếu từng câu/đáp án: chủ đề là số tòa nhà, trường của Bill, số lượng là three. Nội dung PASS cho mẫu này; đây không phải bằng chứng mọi phản hồi tương lai đều đúng.
- 2/2 kiểm thử recovery PASS (gồm 7 biến thể JSON sai bị từ chối); 4/4 kiểm thử offline cũ PASS, bao gồm quét khóa trong file bàn giao. Không chạy lại toàn bộ giai đoạn 1 hoặc lập trình website.

Bằng chứng chính: `reports/gemini-recovery.json`, `reports/recovery-tests.txt`; lỗi trung gian giữ tại `reports/gemini-recovery-schema-error.json` và `reports/gemini-recovery-whitespace-check.json`. Các file `gemini.json` và `environment.json` bên dưới là bằng chứng lịch sử, không đại diện model hiện tại.

Chạy kiểm thử offline: `backend/.venv/Scripts/python.exe scripts/test_recovery.py`. Chạy API có kiểm soát khi cần: `backend/.venv/Scripts/python.exe scripts/recover_gemini.py --free-plan-confirmed` (một lần list + một lần generate; không tự fallback).

## Kết quả lịch sử trước khắc phục

**Thời điểm ban đầu: CHƯA PASS toàn bộ — Gemini generateContent FAIL.**

| Hạng mục | Kết quả thực tế |
| --- | --- |
| Cấu trúc dự án | PASS, kiểm kê nguồn và đầu ra trong `reports/environment.json` |
| Git ignore | PASS, 6 trường hợp qua `git check-ignore` thật trong repository tạm |
| Git repository chính | Chưa khởi tạo; không có lịch sử/index để kiểm tra |
| Python | PASS, CPython 3.11.16 trong `backend/.venv`; PATH mặc định chỉ có alias Store |
| Node / npm / Git | PASS, 22.23.2 / 12.0.2 / 2.50.0.windows.1 |
| Thư viện | PASS, google-genai 3.0.0, python-dotenv 1.2.4, python-pptx 1.0.2 |
| Cấu hình | PASS, đọc được key và `gemini-2.5-flash`, không hiển thị key |
| Gemini sinh nội dung | FAIL, 2 yêu cầu thật đều HTTP 404; không nhận được nội dung |
| Gemini listModels | PASS, đọc danh sách thật; model có tên trong danh sách nhưng generateContent bị từ chối |
| PowerPoint | PASS, 1 file, 10 slide, 18 picture shape, 19 media part |
| PDF | Đã kiểm kê, chưa phân tích nội dung |
| Website | NOT RUN, ngoài giai đoạn 1 |

Lỗi máy chủ: `models/gemini-2.5-flash` không còn khả dụng cho người dùng mới. Máy chủ gợi ý `models/gemini-3.8-flash`, nhưng chưa kiểm chứng hạn mức miễn phí của model thay thế nên chưa đổi `.env` hoặc gọi model đó. Không thể sửa quyền cung cấp model chỉ bằng thay đổi mã client.

HARRY đã xác nhận Plan = Free. Không mở billing hoặc thay đổi tài khoản. Hai yêu cầu sinh nội dung thất bại và một thao tác liệt kê model; không tự retry. Không có bằng chứng phản hồi sinh nội dung thành công, không tuyên bố API PASS hoặc xác minh hóa đơn từ xa.

Đã xử lý lỗi cache uv bằng `.cache/uv` trong workspace và lỗi DNS sandbox bằng quyền mạng cho cài đặt/API. Không thay tài liệu đầu vào hoặc nội dung `backend/.env`.

Bằng chứng: `reports/environment.json`, `reports/powerpoint.json`, `reports/gemini-first-attempt.json`, `reports/gemini.json`, `reports/models.json`. Kiểm thử offline và kiểm tra dependency được ghi riêng trong `reports/verification.txt`.

Việc còn lại: chọn và xác nhận một model được cấp trong Free tier, cập nhật GEMINI_MODEL, kiểm thử lại có kiểm soát. PowerPoint đã có, không cần bổ sung mẫu cho bước này.
