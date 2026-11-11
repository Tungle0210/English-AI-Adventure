# QA kết nối và chuẩn bị migration Neon — 11/11/2026

**Kết luận:** các kết nối thật chỉ đọc, S3 QA nhỏ/70 MB và diễn tập bản sao đã PASS. **Chưa migrate/deploy production.** Không có push GitHub, không bật billing, không sửa dữ liệu ứng dụng PostgreSQL production. S3 chỉ tạo/xóa2 object QA riêng được phép; không đổi bucket policy/ACL hoặc object hiện hữu.

## Kết quả thật và phạm vi

| Hạng mục | PASS/FAIL/NOT_TESTED | Bằng chứng |
|---|---|---|
| DATABASE_URL pooled | PASS:TLS,READONLY, PostgreSQL18.6 | reports/neon/connections.json |
| DATABASE_DIRECT_URL | PASS:TLS,READONLY, PostgreSQL18.6 | connections.json |
| Adapter/Pool thật trên Neon | PASS:READONLY,SELECT1,0 schema/row tạo mới | adapter-readonly.json |
| S3 file nhỏ | PASS940 byte,SHA-256 khớp,anonymous bị chặn | s3-probe.json |
| PPTXthật70.396.372 byte quaS3 | PASS:upload11.610,49 ms/download12.810,03 ms,1 MiB/read,concurrency1 | s3-probe.json |
| CleanupS3 | PASS:2 QAobject đã xóa, prefixQA hiện0 object | s3-cleanup-verification.json |
| Gemini key/model | PASS models.get,model khớpcấu hình;0 generate_content | connections.json |
| Gemini sinh nội dung ở cloudstackmới | NOT_TESTED:không dùng generationquota trong phiên này | — |
| Render/Netlifyhealth | PASS:hai/api/health200/ok | cloud-http.json |
| Quyền GV trênURLthật | PASS:GET/api/lessonsẩn danh401 ở cả haiURL | cloud-http.json |
| CSRF/cookie trênphiênproduction thật | NOT_TESTED:khôngPOST/login/chỉnhdữ liệu production;localđãtest | local suites |
| Fullmigrationbản sao | PASS7 bảng,IDs/JSON/history/checksumgiữ nguyên | migration-rehearsal.json |
| FullS3 copy | PASS998 tệp với Moto cô lập, không phải998 uploadthật vàoNeon | migration-rehearsal.json |
| Rollbackbản sao | PASS:newSQLite/media,7 bảng/998 tệp khớp | migration-rehearsal.json |
| Toànbộbackend | PASS84/84 | all-backend-tests.xml |
| PostgreSQL/S3 runtime tests | PASS15 testcases trongtổng84:5 tròchơi+all,queue/auth/media/cache/backup | backend/test_neon_runtime.py |
| FrontendbuildNetlify | PASS:TypeScript/Vite,_redirects đúngRenderURL | buildđã chạy |
| ChromeHTTPSlocal | PASS25/25:teacher/student,3 viewport,5 activities,chunk 70 MB,jobrefresh,ảnh | browser-tests.json |
| NativeLinux | NOT_TESTED:UbuntuWSL khôngkhởiđộng vìHCSfeaturethiếu | không tựbậttínhnăngWindows |
| RAM/CPU trên Render Free | NOT_TESTED:không cóquyềnmetrics/Shellvàchưa deploybản mới | khôngsuytừhealth |
| Profilelocal | PASSsốđoWindows:peakRSS~305 MB,cpu2,3 s,wall2,73 s,10 slide/18 ảnh | resource-probe.json |
| 70 MBquaRender Free/Netlifythật | NOT_TESTED:không upload productionkhi chưa được phépchuyểnđổi | S3 trực tiếplàphépđokhác |
| NativePostgreSQL trên Neonvớimigrationghi | NOT_TESTED:khôngđược phépghi production | chỉreadonlyprobe |
| LinuxCI/DockerBuild | NOT_TESTED:chưapush/chạyCIremote | workflowđãchuẩnbị |
| OriginalSQLite/media | PASS:7 bảng checksumkhông đổi,0 filegốcthayđổi | preservation.json |
| Guardmigration | PASS:applythiếuquyền bị chặntrướckết nối | migration-guard.json |

Một HTTPhealth quaNetlify mất44,18 s tổng cộng, dùtrả200; chưa táchDNS/TLS/proxy/backendnên khôngkếtluậnnguyênnhân hoặc camkếtthời gianthực tế. Frontendjob/polling tránhgiữHTTPchờ Gemini nhưng khôngloại bỏcoldstart/mạngchậm.

## Dữ liệu diễn tập

Nguồn là bản sao mới đã kiểm tính ổn định trong lúc đọc từ backend/data, không chỉnh source.18 lessons,135 sessions,8 cache,20 calls,157 attempts,1 jobs,0 upload_sessions. Dữ liệu JSON được giữ TEXT, checksum từng bảng dựa trên đầy đủ giá trị nguyên gốc.998 object gồm nguồn/ảnh/metadata/QA/cache và indexes phát sinh, không re-render ảnh hoặc đổi ID/đáp án.

PostgreSQL diễn tập là **PGlite/WASM quaPGwire trênWindows**, không phải Postgres native Linux hoặc branchproduction. S3 toàn bộdữ liệu dùng **Moto** và credentialgiả, không phải bucketproduction. Kết nối nativeNeon thật chỉREADONLY; S3 thật chỉ haiQAobjectsmall/PPTX, đã cleanup.

Đã đọc ngược PG/S3 mô phỏng tạo rollbackSQLite mới và đối chiếu checksum. RuntimePostgres đã kiểm tạo bài/upload, giữchunk saumatcache, teacheredit/approve/publish,6 chếđộplay đạt100 điểm,lưu/history,jobidempotency/AIerror,dữ liệumedia,cloudbackupREADONLY vànooverwrite. Bài đãlưu không gọiGemini. Ảnhunit synthetic đượcgắnnhãnriêng, khônggánvàohọc liệuthật.

## Lỗi đã tìm và xử lý

1. PostgreSQL coi `offset` làkeyword:quote đúng cột, vẫngiữtên/giátrị nguồn.
2. Neon pooler từchối startup `options`:dời statement/lock timeout sangSETLOCAL, kết nốithậtREADONLY đãPASS sau sửa.
3. Preparedstatement caching vướngpooler/WASM:sửdụngprepare_threshold=None. Runtimepool nhỏ,tốiđa3 mặcđịnh.
4. Full/thư việnlúc đầu sẽ gây tải nhiềuS3:thêm summary vàloadchi tiết khi chọn bài, giữbố cục. Chỉảnhcần dùng mới kéo vềcache.
5. Snapshotbackup cũ chưa cójob:diễntập cuối dùngbản sao đủ7 bảng, có1 jobhiện hữu.
6. PGWASM chỉ1 connection:harness cầnnhảpool trước mộtkết nối backup riêng. Đây làgiới hạn củaengine diễn tập, không phảisửa quotaluồngNeon.
7. ĐoRAMWindows banđầuchỉnhìnvenvlauncher vàrasố5 MBsai:đãđổiđo cảcâytiếntrình, kếtquả305 MB. Không dùngsốlauncherđểnghiệmthuFree.

## Guard và giới hạn

- Cloudruntime cần ADVENTURE_CLOUD_ENABLE=yes, PostgreSQL/S3 flags vàmarker migration_ready; giữlocal mặcđịnh. Phiênkiểm thử chưa bật cloud guard trong.env vàkhông sửa.env của HARRY.
- CLIplan/rehearse không ghi cloud. Apply thật cầncả --permit-production-write và ADVENTURE_ALLOW_MIGRATION=yes, schema/prefixMỚI; khôngtruncate/merge/drop. Khônggọiapply được phép trong phiên này.
- Joblease/fence hạnchế duplicate/ghi muộn;running bịmấtlease thànhinterrupted, không tựretryGemini. Không dùngidleDBpoll đểgiữNeoncompute thức.
- NeonPrivate S3 dùngpathstyle/SigV4. ETagkhôngcoilàSHA-256; kiểmSHA256 tệp tải lại. Khôngdựavàoversioning/lifecycle vìNeon hiệnkhôngthực thichúngnhưAWSS3.
- FreeRender0,1 CPU/512 MB theo tài liệu,spindown15 phút;khôngdisk/SSH/Shell,externaltraffic cógiới hạn. Cácgiới hạn côngbốkhông phảisốđoprocesshiện tại. Localprofile chếđộlocalkhôngbao gồmcácảnh/dữ liệulớn tùyý hoặcchi phícloudthực.
- Cònthiếu:loadtestLinux,cloudRAM/CPU,coldstart/job/resume/rollbacktrên Renderthật,rolloverquota,backupoffsiteđịnhkỳvàcảnhbáoquotalive.
- Mật khẩuđã xuấthiệntrongchat:khônglặplạigiátrị; cầnrotate/cậpnhậtconfigtrước cutover. Chưaxác minhđãrotate.

Hướngdẫntừngbước:docs/NEON_MIGRATION.md. Filecấu hìnhmớirender.yaml làFree/khôngdisk; mẫuSQLiteDisk cũ giữởdeploy/render-sqlite-disk.yaml. Khôngfilecấu hìnhnàotựtriểnkhai. Không gọi healthPASS làmigration/productionacceptancePASS.
