from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .content import ROOT, MAX_BYTES, EXTENSIONS, read_document
from .schemas import Item, Editable, LessonUpdate, GenerateRequest, verify_sources
from . import ai
from . import media, quality, config, database, objects
from .jobs import Queue
from .storage import single_writer

DATA = Path(os.environ.get('ADVENTURE_DATA_DIR', ROOT / 'backend/data'))
DB = DATA / 'adventure.sqlite3'
generation_lock = threading.Lock()
login_attempts = {}
job_queue = None
upload_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    if config.postgres():
        with database.connect() as connection:yield connection
        return
    connection = sqlite3.connect(DB, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def check_ai_budget(c):
    stamp=time.time()
    if c.execute('SELECT COUNT(*) FROM calls WHERE at>?',(stamp-86400,)).fetchone()[0]>=20:raise HTTPException(429,'Giới hạn bảo vệ local 20 lượt/24 giờ, không phải quota Google.')
    if c.execute('SELECT COUNT(*) FROM calls WHERE at>?',(stamp-30,)).fetchone()[0]>=1:raise HTTPException(429,'Vui lòng chờ đủ 30 giây từ lần gọi AI gần nhất. Giới hạn local 1 lượt/30 giây; không phải quota Google.')


def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'uploads').mkdir(exist_ok=True)
    if config.postgres():
        with db() as c:database.ready(c)
        return
    codefile = DATA / 'teacher-access.txt'
    with db() as c:
        from .schema import CORE
        c.executescript(CORE)
        c.executescript(database.EXTRA_SCHEMA)
        has_hash=c.execute("SELECT 1 FROM app_settings WHERE key='teacher_auth'").fetchone()
    if not codefile.exists() and not has_hash:
        codefile.write_text(secrets.token_urlsafe(18), encoding='utf-8')


def lesson_dict(row):
    data = dict(row)
    data['document'] = json.loads(data['document'])
    data['questions'] = json.loads(data['questions'])
    return data


def get_lesson(c, ident):
    row = c.execute('SELECT * FROM lessons WHERE id=?', (ident,)).fetchone()
    if not row:
        raise HTTPException(404, 'Không tìm thấy bài học.')
    return quality.refresh_lesson(lesson_dict(row), DATA)


def insert_lesson(c, title, document, questions=None, origin='manual'):
    ident = uuid.uuid4().hex
    c.execute('INSERT INTO lessons VALUES(?,?,?,?,?,?,?,?,?,?)', (ident, title, 3, 'draft', secrets.token_hex(4).upper(), 1, json.dumps(document, ensure_ascii=False), json.dumps(questions or [], ensure_ascii=False), origin, now()))
    return get_lesson(c, ident)


def seed():
    with db() as c:
        if c.execute('SELECT COUNT(*) FROM lessons').fetchone()[0]:
            return
        source = ROOT / 'input/Unit 6 Lesson 2 Period 3.pptx'
        if not source.exists():
            return
        saved_extraction = ROOT / 'reports/powerpoint.json'
        if saved_extraction.exists():
            deck = json.loads(saved_extraction.read_text(encoding='utf-8'))[0]
            document = {'label': 'Slide', 'sections': [{'number':s['slide'], 'text':'\n'.join(t.strip() for t in s['text'] if t.strip()), 'images':s['picture_shapes']} for s in deck['slides']], 'warnings':['Bản trích xuất PowerPoint đã lưu từ giai đoạn 1. Không OCR chữ trong ảnh.']}
        else:
            document = read_document(source)
        # Reviewed-source demonstration, never automatically approved/published.
        facts = [
            ('vocabulary', 'What does “school” mean?', 'trường học', ['trường học', 'ngôi nhà', 'công viên'], 'school', 'trường học', 'school', 4, 'Where’s Bill’s school?'),
            ('quiz', 'Where is Bill’s school?', 'In the town', ['In the town', 'In the city', 'In the village'], '', '', '', 4, 'It’s in the town.'),
            ('match', 'Match: school', 'trường học', [], 'school', 'trường học', '', 4, 'Where’s Bill’s school?'),
            ('match', 'Match: three', 'số ba', [], 'three', 'số ba', '', 5, 'There are three.'),
            ('listen', 'How many buildings are there?', 'Three', ['Two', 'Three', 'Four'], '', '', 'There are three buildings at Bill’s school.', 5, 'There are three.'),
            ('fill', 'There are ___ buildings at Bill’s school.', 'three', [], '', '', '', 5, 'There are three.'),
        ]
        questions = []
        for kind, prompt, answer, options, word, meaning, speech, source_n, quote in facts:
            q = Item(kind=kind, prompt=prompt, answer=answer, options=options, word=word, meaning=meaning, speech=speech, source=source_n, quote=quote, explanation=f'Đối chiếu nguồn: “{quote}”')
            questions.append(dict(q.model_dump(), id=uuid.uuid4().hex, approved=False))
        verify_sources([Item.model_validate({k:v for k,v in q.items() if k not in ('id','approved')}) for q in questions], document)
        # Also reuse the successful phase-1 AI response as editable quiz items.
        saved = ROOT / 'reports/gemini-recovery.json'
        if saved.exists():
            for q in json.loads(saved.read_text(encoding='utf-8')).get('quiz', {}).get('questions', []):
                questions.append(dict(Item(kind='quiz', prompt=q['question'], answer=q['answer'], options=[q['answer'], 'Not stated in the text'], explanation='Câu hỏi AI đã lưu từ giai đoạn 1. Giáo viên cần kiểm duyệt lại.', source=5, quote=q['source_quote'], word='', meaning='', speech='').model_dump(), id=uuid.uuid4().hex, approved=False))
        insert_lesson(c, 'Our school facilities', document, questions, 'saved_demo')


@asynccontextmanager
async def lifespan(app):
    global job_queue
    config.validate()
    if config.production() and config.maintenance():
        DATA.mkdir(parents=True,exist_ok=True)
        yield
        return
    from contextlib import nullcontext
    with (nullcontext() if config.postgres() else single_writer(DATA)):
        init_db()
        if not config.production() and not config.postgres():
            seed()
            from .migration import audit_legacy
            audit_legacy(DATA, DB)
        from .pgjobs import PostgresQueue
        job_queue=(PostgresQueue if config.postgres() else Queue)(db,dispatch_job)
        job_queue.start()
        try:yield
        finally:job_queue.close()



app = FastAPI(title='English AI Adventure', lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Pydantic errors can echo inputs; keep secrets and submitted content out of logs/responses.
    return JSONResponse(status_code=422, content={'detail': 'Dữ liệu không hợp lệ. Kiểm tra trường bắt buộc, số câu và cấu trúc đáp án.'})


@app.middleware('http')
async def boundaries(request, call_next):
    if config.maintenance() and request.url.path.startswith('/api') and request.url.path!='/api/health':
        return JSONResponse(status_code=503,content={'detail':'Máy chủ đang bảo trì/chuyển dữ liệu. Không có dữ liệu bị thay thế.'})
    if request.url.path.startswith('/api'):
        hostname=urlsplit('http://'+request.headers.get('host','')).hostname
        if not hostname or hostname.lower() not in config.hosts():
            return JSONResponse(status_code=400,content={'detail':'Host không được phép.'})
        origin = request.headers.get('origin')
        if config.production() and request.method not in ('GET','HEAD','OPTIONS') and not origin:
            return JSONResponse(status_code=403,content={'detail':'Thiếu Origin cho yêu cầu thay đổi dữ liệu.'})
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            if (origin not in config.origins()) if config.production() else (urlsplit(origin).scheme not in ('http','https') or urlsplit(origin).netloc != request.headers.get('host')):
                return JSONResponse(status_code=403, content={'detail': 'Nguồn yêu cầu không hợp lệ.'})
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return JSONResponse(status_code=400, content={'detail': 'Độ dài yêu cầu không hợp lệ.'})
        if length > MAX_BYTES + 1024 * 1024:
            return JSONResponse(status_code=413, content={'detail': 'File tối đa 100 MB.'})
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def teacher(request: Request):
    token = request.cookies.get('teacher_session', '')
    with db() as c:
        row = c.execute('SELECT token FROM sessions WHERE token=? AND expires>?', (token, time.time())).fetchone()
    if not row:
        raise HTTPException(401, 'Vui lòng đăng nhập khu vực giáo viên.')


class Login(BaseModel):
    code: str = Field(max_length=100)


@app.post('/api/login')
def login(body: Login, request: Request, response: Response):
    host = request.client.host if request.client else 'unknown'
    recent = [t for t in login_attempts.get(host, []) if time.time() - t < 60]
    login_attempts[host] = recent
    if len(recent) >= 5:
        raise HTTPException(429, 'Thử quá nhiều lần. Hãy chờ một phút.')
    if config.postgres():
        with db() as c:matches=database.teacher_matches(c,body.code)
    else:
        with db() as c:has_hash=c.execute("SELECT 1 FROM app_settings WHERE key='teacher_auth'").fetchone()
        if has_hash:
            with db() as c:matches=database.teacher_matches(c,body.code)
        else:matches=secrets.compare_digest(body.code,(DATA/'teacher-access.txt').read_text(encoding='utf-8').strip())
    if not matches:
        recent.append(time.time())
        raise HTTPException(401, 'Mã giáo viên chưa đúng.')
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        c.execute('INSERT INTO sessions VALUES(?,?)', (token, time.time()+12*3600))
    response.set_cookie('teacher_session', token, httponly=True, secure=config.production(), samesite='strict', path='/api' if config.production() else '/', max_age=12*3600)
    return {'ok': True}


@app.post('/api/logout')
def logout(request: Request, response: Response):
    with db() as c:
        c.execute('DELETE FROM sessions WHERE token=?', (request.cookies.get('teacher_session', ''),))
    response.delete_cookie('teacher_session',path='/api' if config.production() else '/',secure=config.production(),httponly=True,samesite='strict')
    return {'ok': True}


@app.get('/api/health')
def health():
    return {'status':'maintenance' if config.maintenance() else 'ok','app':'English AI Adventure'}


@app.get('/api/teacher', dependencies=[Depends(teacher)])
def teacher_info():
    from dotenv import dotenv_values
    cfg = ai.configuration()
    return {'ai_configured': bool(cfg.get('GEMINI_API_KEY')), 'model': cfg.get('GEMINI_MODEL'), 'max_upload_mb': 100}


@app.get('/api/lessons', dependencies=[Depends(teacher)])
def lessons(summary: bool = False):
    with db() as c:
        rows = c.execute('SELECT * FROM lessons ORDER BY updated DESC').fetchall()
    if summary:
        result=[]
        for row in rows:
            item=lesson_dict(row);doc=item['document']
            item['document']={'label':doc.get('label','Phần'),'sections':[{'number':s['number'],'text':'','images':s.get('images',0)} for s in doc.get('sections',[])],'assets':[],'warnings':[]}
            item['detail_loaded']=False;result.append(item)
        return result
    return [quality.refresh_lesson(lesson_dict(r),DATA) for r in rows]


@app.post('/api/upload', dependencies=[Depends(teacher)])
def upload(file: UploadFile = File(...)):
    upload_started=time.perf_counter()
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in EXTENSIONS:
        raise HTTPException(415, 'Chỉ hỗ trợ PPTX, PDF, DOCX và TXT.')
    path = DATA / 'uploads' / (uuid.uuid4().hex + suffix)
    size = 0
    digest = hashlib.sha256()
    with path.open('wb') as stream:
        for chunk in iter(lambda:file.file.read(1024*1024), b''):
            size += len(chunk)
            if size > MAX_BYTES:
                break
            digest.update(chunk)
            stream.write(chunk)
    if not size or size > MAX_BYTES:
        path.unlink(missing_ok=True)
        raise HTTPException(413, 'File trống hoặc vượt quá 100 MB.')
    saved_at=time.perf_counter()
    import shutil
    (DATA/'sources').mkdir(exist_ok=True)
    shutil.copyfile(path,DATA/'sources'/(digest.hexdigest()+suffix))
    objects.publish(DATA,'sources/'+digest.hexdigest()+suffix)
    retained_at=time.perf_counter()
    try:
        document = read_document(path,media_root=DATA)
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else 'Không đọc được file. Kiểm tra đúng định dạng và không hỏng/mã hóa.'
        raise HTTPException(422, message) from None
    finally:
        path.unlink(missing_ok=True)
    extracted_at=time.perf_counter()
    document['intake_trace']=[{'stage':1,'name':'Upload và kiểm tra định dạng','status':'PASS','duration_ms':round((saved_at-upload_started)*1000,2),'bytes':size},{'stage':2,'name':'Lưu file nguồn','status':'PASS','duration_ms':round((retained_at-saved_at)*1000,2),'note':'Bản gốc giữ trong sources'},{'stage':3,'name':'Trích xuất văn bản và ảnh','status':'PASS','duration_ms':round((extracted_at-retained_at)*1000,2),'sections':len(document['sections']),'assets':len(document.get('assets',[]))}]
    document['filename'] = Path(file.filename or 'Tài liệu').name
    document['sha256'] = digest.hexdigest()
    document['quality_schema']=3;document['reading_gate']=1
    with db() as c:
        return insert_lesson(c, Path(file.filename or 'Bài học').stem[:120], document)


@app.get('/api/lessons/{ident}', dependencies=[Depends(teacher)])
def lesson(ident: str):
    with db() as c:
        return get_lesson(c, ident)


@app.post('/api/lessons/{ident}/restore-source',dependencies=[Depends(teacher)])
def restore_source(ident: str,file: UploadFile=File(...)):
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in EXTENSIONS:raise HTTPException(415,'Chỉ nhận tài liệu nguồn đúng định dạng.')
    with db() as c:lesson=get_lesson(c,ident)
    path=DATA/'uploads'/(uuid.uuid4().hex+suffix)
    try:
        size=0
        with path.open('wb') as stream:
            for chunk in iter(lambda:file.file.read(1024*1024),b''):
                size+=len(chunk)
                if size>MAX_BYTES:raise HTTPException(413,'Tối đa 100 MB.')
                stream.write(chunk)
        if not size:raise HTTPException(422,'Tài liệu trống.')
        expected=lesson['document'].get('sha256')
        if not expected or media.digest_file(path)!=expected:raise HTTPException(422,'File không trùng SHA-256 tài liệu gốc. Không gán ảnh từ tài liệu khác; hãy chọn đúng file gốc.')
        document=read_document(path,media_root=DATA)
        with db() as c:
            latest=get_lesson(c,ident)
            if latest['revision']!=lesson['revision']:raise HTTPException(409,'Bài vừa thay đổi; tải lại trước khi khôi phục.')
            for key in ['assets','sha256','source_retained']:latest['document'][key]=document[key]
            for section in latest['document']['sections']:
                restored=next((s for s in document['sections'] if s['number']==section['number']),None)
                if restored:
                    section['asset_ids']=restored.get('asset_ids',[]);section['images']=restored.get('images',0)
            latest['document']['warnings']=[w for w in latest['document'].get('warnings',[]) if 'đã bị xóa' not in w]
            for q in latest['questions']:q['approved']=False
            return persist_document(c,latest)
    finally:path.unlink(missing_ok=True)


def ai_error(error):
    code = getattr(error, 'code', None)
    if code == 429:
        return 429, 'Gemini đã hết hạn mức hoặc đang giới hạn tốc độ. Không tự thử lại hoặc bật thanh toán.'
    if code == 404:
        return 502, 'Model Gemini không khả dụng (404). Bài đã lưu vẫn dùng được.'
    if code == 503:
        return 503, 'Gemini đang quá tải (503). Bài học đã lưu vẫn chơi được; không tự thử lại hoặc đổi model.'
    if code in (400, 401, 403):
        return 502, 'Gemini từ chối yêu cầu/cấu hình. Kiểm tra quyền API và model; không bật billing.'
    if isinstance(error, RuntimeError):
        return 503, 'Thiếu API Key hoặc model chưa được xác minh Free Tier. Kiểm tra cấu hình backend.'
    if isinstance(error, ValueError):
        return 422, str(error)[:1000] if isinstance(error, ai.GenerationError) else 'Kiểm định câu hỏi thất bại: ' + str(error)[:600]
    return 504 if 'timeout' in type(error).__name__.lower() else 502, 'Lỗi kết nối từ backend tới Gemini; chưa có bằng chứng Gemini trả HTTP 503. Bản nháp được giữ nguyên.'


def generate_lesson(ident: str, settings: GenerateRequest):
    if not generation_lock.acquire(blocking=False):
        raise HTTPException(409, 'Đang tạo câu hỏi. Vui lòng chờ, không gửi lặp.')
    try:
        with db() as c:
            current = get_lesson(c, ident)
            if current['state'] == 'published':
                raise HTTPException(409, 'Chuyển bài về bản nháp trước khi tạo lại.')
            if current['questions'] and not settings.append:
                raise HTTPException(409, 'Bài đã có câu hỏi. Hãy sửa hoặc xóa và lưu trước khi tạo bộ mới.')
            cache_key = hashlib.sha256((json.dumps({k:v for k,v in current['document'].items() if k not in ('intake_trace','filename')}, sort_keys=True) + settings.model_dump_json() + 'schema-v3-visual').encode()).hexdigest()
            cached = None if settings.force_refresh else c.execute('SELECT payload FROM cache WHERE key=?', (cache_key,)).fetchone()
            if cached:
                payload = json.loads(cached['payload'])
                origin = 'ai_cache'
            else:
                check_ai_budget(c)
                c.execute('INSERT INTO calls VALUES(?)', (time.time(),))
        if not cached:
            try:
                generated, meta = ai.generate(current['document'], settings, media_root=DATA)
            except Exception as error:
                status, message = ai_error(error)
                # A bounded diagnostic, redacted before persistence; never stringify request/headers.
                import re
                from dotenv import dotenv_values
                secret = ai.configuration().get('GEMINI_API_KEY') or ''
                detail = str(error) if isinstance(error,ValueError) else getattr(error, 'message', '')
                safe = detail.replace(secret, '[REDACTED]') if secret and isinstance(detail, str) else ''
                diagnostic = {'type':type(error).__name__, 'http_code':getattr(error,'code',None), 'message':re.sub(r'https?://\S+', '[URL omitted]', safe)[:2000]}
                (DATA / 'last-ai-error.json').write_text(json.dumps(diagnostic), encoding='utf-8')
                raise HTTPException(status, {'message':message,'stage':getattr(error,'stage',5),'origin':'gemini' if getattr(error,'code',None) else 'validation' if isinstance(error,ValueError) else 'backend','provider_http_status':getattr(error,'code',None),'reason_code':getattr(error,'reason_code',type(error).__name__),'diagnostics':getattr(error,'diagnostics',{}),'metrics':getattr(error,'pipeline_metrics',{})}) from None
            payload = {'questions': [q.model_dump() for q in generated.questions], 'meta': meta}
            origin = 'ai_live'
            with db() as c:
                c.execute('INSERT OR REPLACE INTO cache VALUES(?,?)', (cache_key, json.dumps(payload)))
        questions = [quality.persisted(quality.assess(dict(q,id=uuid.uuid4().hex,approved=False),current['document'],DATA)) for q in payload['questions']]
        if any(q['validation_status']!='valid' for q in questions):
            raise HTTPException(422,{'message':'Kết quả AI/cache chưa đủ dữ kiện hoặc ảnh không hợp lệ. Không thêm câu thiếu bằng chứng vào bài.','stage':7,'reason_code':'CACHE_EVIDENCE_INVALID','origin':'validation'})
        if settings.append:
            keys={(q['kind'],q['prompt']) for q in current['questions']}
            questions=current['questions']+[q for q in questions if (q['kind'],q['prompt']) not in keys]
            if len(questions)>40:raise HTTPException(422,'Bài tối đa 40 câu; các câu đã lưu được giữ nguyên.')
        save_started=time.perf_counter()
        with db() as c:
            latest = get_lesson(c, ident)
            if latest['revision'] != current['revision']:
                raise HTTPException(409, {'message':'Bài đã thay đổi trong lúc tạo. Không ghi đè; kết quả AI được lưu cache.','stage':8,'reason_code':'REVISION_CONFLICT','origin':'backend'})
            c.execute('UPDATE lessons SET questions=?,grade=?,origin=?,revision=revision+1,updated=? WHERE id=?', (json.dumps(questions, ensure_ascii=False), settings.grade, origin, now(), ident))
            result = get_lesson(c, ident)
        return dict(result, generation={'cached': bool(cached), **payload['meta'],'save_ms':round((time.perf_counter()-save_started)*1000,2)})
    finally:
        generation_lock.release()


def traced_generate_core(ident: str, settings: GenerateRequest):
    started=time.perf_counter();run_id=uuid.uuid4().hex
    with db() as c:document=get_lesson(c,ident)['document']
    events=[dict(e,reused=True) for e in document.get('intake_trace',[])]
    if not events:events=[{'stage':n,'status':'REUSED','duration_ms':0,'note':'Tài liệu đã lưu trước khi có đo thời gian'} for n in (1,2,3)]
    record={'run_id':run_id,'lesson_id':ident,'at':now(),'events':events,'cache_requested':not settings.force_refresh}
    folder=DATA/'qa/generation';folder.mkdir(parents=True,exist_ok=True)
    try:
        result=generate_lesson(ident,settings)
        meta=result['generation'];cached=meta['cached']
        events.extend([{'stage':4,'name':'Xây dựng nội dung Gemini','status':'REUSED' if cached else 'PASS','duration_ms':meta.get('prompt_ms',0),'prompt_chars':meta.get('prompt_chars'),'prompt_sha256':meta.get('prompt_sha256')},
                       {'stage':5,'name':'Gọi Gemini','status':'REUSED' if cached else 'PASS','duration_ms':meta.get('api_ms',0),'provider_http_status':None if cached else meta.get('provider_http_status'),'cached':cached},
                       {'stage':6,'name':'Phân tích JSON','status':'PASS','duration_ms':meta.get('parse_ms',0)},
                       {'stage':7,'name':'Kiểm định từng câu','status':meta.get('validation',{}).get('status','PASS'),'duration_ms':meta.get('validation_ms',0),'details':meta.get('validation',{})},
                       {'stage':8,'name':'Lưu SQLite','status':'PASS','duration_ms':meta.get('save_ms',0),'questions':len(result['questions'])},
                       {'stage':9,'name':'Hiển thị giáo viên','status':'PENDING','duration_ms':None}])
        result['generation']['run_id']=run_id
        return result
    except HTTPException as error:
        detail=error.detail if isinstance(error.detail,dict) else {'message':error.detail,'stage':5,'reason_code':'REQUEST_REJECTED'}
        stage=detail.get('stage',5)
        metrics=detail.get('metrics',{})
        for n in range(4,10):
            completed=n<stage and bool(metrics)
            events.append({'stage':n,'status':'FAIL' if n==stage else 'PASS' if completed else 'SKIP','duration_ms':metrics.get('prompt_ms') if n==4 else metrics.get('api_ms') if n==5 else None,'details':detail if n==stage else metrics if n==4 else {}})
        detail['run_id']=run_id
        raise HTTPException(error.status_code,detail) from None
    finally:
        record['total_ms']=round((time.perf_counter()-started)*1000,2)
        (folder/(run_id+'.json')).write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
        objects.publish(DATA,'qa/generation/'+run_id+'.json')


@app.get('/api/lessons/{ident}/generation-status',dependencies=[Depends(teacher)])
def generation_status(ident: str):
    with db() as c:get_lesson(c,ident)
    folder=DATA/'qa/generation'
    if config.object_storage():
        for name in objects.list_names('qa/generation/'):
            path=objects.ensure(DATA,name)
    files=sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True) if folder.exists() else []
    for path in files:
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['lesson_id']==ident:return data
    return {'events':[]}


@app.post('/api/lessons/{ident}/generation-status/{run_id}/displayed',dependencies=[Depends(teacher)])
def generation_displayed(ident: str,run_id: str):
    if len(run_id)!=32 or any(c not in '0123456789abcdef' for c in run_id):raise HTTPException(422,'Run ID không hợp lệ.')
    path=DATA/'qa/generation'/(run_id+'.json')
    if config.object_storage() and objects.head('qa/generation/'+run_id+'.json'):objects.ensure(DATA,'qa/generation/'+run_id+'.json')
    if not path.exists():raise HTTPException(404,'Không có lượt tạo này.')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data['lesson_id']!=ident:raise HTTPException(404,'Không có lượt tạo này.')
    for e in data['events']:
        if e['stage']==9 and e['status']=='PENDING':e.update(status='PASS',duration_ms=0,note='Trình duyệt xác nhận đã render danh sách câu hỏi')
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    objects.publish(DATA,'qa/generation/'+run_id+'.json')
    return {'status':'ok'}


@app.put('/api/lessons/{ident}', dependencies=[Depends(teacher)])
def edit_lesson(ident: str, body: LessonUpdate):
    with db() as c:
        current = get_lesson(c, ident)
        if current['revision'] != body.revision:
            raise HTTPException(409, 'Bài đã thay đổi. Tải lại trước khi lưu.')
        if len({q.id for q in body.questions}) != len(body.questions):
            raise HTTPException(422, 'ID câu hỏi bị trùng.')
        try:
            verify_sources(body.questions, current['document'])
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        old = {q['id']: q for q in current['questions']}
        questions = []
        for q in body.questions:
            data = q.model_dump()
            previous = old.get(q.id)
            content = {k:v for k,v in data.items() if k != 'approved'}
            # A changed/new item cannot be approved in the same save; review after saving.
            if not previous or content != {k:v for k,v in quality.persisted(previous).items() if k != 'approved'}:
                data['approved'] = False
            checked=quality.assess(data,current['document'],DATA)
            if checked['validation_status']!='valid':checked['approved']=False
            questions.append(quality.persisted(checked))
        c.execute('UPDATE lessons SET title=?,grade=?,questions=?,state=?,revision=revision+1,updated=? WHERE id=?', (body.title.strip(), body.grade, json.dumps(questions, ensure_ascii=False), 'draft', now(), ident))
        return get_lesson(c, ident)


@app.post('/api/lessons/{ident}/publish', dependencies=[Depends(teacher)])
def publish(ident: str):
    with db() as c:
        current = get_lesson(c, ident)
        questions = current['questions']
        visible=[q for q in questions if not q.get('hidden')]
        if not visible or not all(q['approved'] and q['validation_status']=='valid' for q in visible):
            raise HTTPException(422, 'Cần giáo viên duyệt tất cả câu hỏi trước khi xuất bản.')
        pairs = [q for q in visible if q['kind'] == 'match']
        if pairs and (len(pairs) < 2 or len({q['word'] for q in pairs}) != len(pairs) or len({q['meaning'] for q in pairs}) != len(pairs)):
            raise HTTPException(422, 'Ghép từ cần ít nhất 2 cặp từ/nghĩa khác nhau.')
        c.execute('UPDATE lessons SET state=?,revision=revision+1,updated=? WHERE id=?', ('published', now(), ident))
        return get_lesson(c, ident)


@app.post('/api/lessons/{ident}/unpublish', dependencies=[Depends(teacher)])
def unpublish(ident: str):
    with db() as c:
        get_lesson(c, ident)
        c.execute('UPDATE lessons SET state=?,revision=revision+1,updated=? WHERE id=?', ('draft', now(), ident))
        return get_lesson(c, ident)


@app.get('/api/play/{code}')
def public_lesson(code: str):
    with db() as c:
        row = c.execute('SELECT * FROM lessons WHERE code=? AND state=?', (code.upper(), 'published')).fetchone()
    if not row:
        raise HTTPException(404, 'Mã bài học chưa đúng hoặc bài chưa xuất bản.')
    data = lesson_dict(row)
    questions=quality.eligible(data,DATA)
    if not questions:raise HTTPException(404,'Bài đang được kiểm định học liệu, chưa có câu đủ dữ kiện.')
    modes = {q['kind']:sum(x['kind']==q['kind'] for x in questions) for q in questions}
    if modes.get('match',0)<2:modes.pop('match',None)
    return {k:data[k] for k in ['id','title','grade','code']} | {'modes': modes, 'delivery': 'saved', 'question_count': len(questions)}


class Start(BaseModel):
    mode: str = Field(default='all', max_length=20)


def public_questions(questions, document=None):
    allowed = ['id', 'kind', 'prompt', 'options', 'word', 'speech']
    output=[]
    for q in questions:
        checked=quality.assess(q,document or {},DATA)
        output.append(dict({k:q[k] for k in allowed}, image=q.get('image',''),requires_visual=checked['requires_visual'],image_asset_id=q.get('image_asset_id',''),media_url=checked['media_url'],visual_description=q.get('visual_description',''),source_evidence=q.get('source_evidence',''),question_type=checked.get('question_type','language'),validation_status=checked['validation_status'],quality_issues=checked['quality_issues']))
    return output


@app.post('/api/play/{code}/start')
def start(code: str, body: Start):
    public = public_lesson(code)
    with db() as c:
        lesson = get_lesson(c, public['id'])
        questions = [quality.persisted(q) for q in quality.eligible(lesson,DATA) if body.mode == 'all' or q['kind'] == body.mode]
        if body.mode=='all' and sum(q['kind']=='match' for q in questions)<2:questions=[q for q in questions if q['kind']!='match']
        if not questions:
            raise HTTPException(422, 'Hoạt động chưa có dữ liệu được duyệt.')
        ident = secrets.token_urlsafe(24)
        c.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?)', (ident, lesson['id'], lesson['title'], body.mode, json.dumps(questions, ensure_ascii=False), '{}', now(), None))
    # Matching requires a shuffled bank of meanings, not per-word answers.
    bank = [q['meaning'] for q in questions if q['kind'] == 'match']
    secrets.SystemRandom().shuffle(bank)
    return {'id': ident, 'title': lesson['title'], 'questions': public_questions(questions,lesson['document']), 'match_bank': bank}


class Answer(BaseModel):
    question_id: str = Field(max_length=64)
    answer: str = Field(max_length=300)


def result_data(row):
    questions = json.loads(row['questions'])
    responses = json.loads(row['responses'])
    correct = sum(r['correct'] for r in responses.values())
    skipped=sum(bool(r.get('skipped')) for r in responses.values());graded_total=len(questions)-skipped
    return {'attempt_id': row['id'], 'title': row['title'], 'mode': row['mode'], 'answered': len(responses), 'total': len(questions), 'graded_total':graded_total,'skipped':skipped,'correct': correct, 'score': round(100*correct/graded_total) if graded_total else None, 'completed': bool(row['completed']), 'started': row['started'], 'responses': responses}


@app.post('/api/attempts/{ident}/answer')
def answer(ident: str, body: Answer):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM attempts WHERE id=?', (ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Không tìm thấy lượt chơi.')
        questions = json.loads(row['questions'])
        q = next((q for q in questions if q['id'] == body.question_id), None)
        if not q:
            raise HTTPException(422, 'Câu hỏi không thuộc lượt chơi.')
        responses = json.loads(row['responses'])
        if body.question_id not in responses:
            document=get_lesson(c,row['lesson_id'])['document']
            checked=quality.assess(q,document,DATA)
            if checked['requires_visual'] and checked['validation_status']!='valid':
                raise HTTPException(409,'Ảnh không đủ dữ kiện hoặc không tải được. Bỏ qua câu này không trừ điểm.')
            norm = lambda text: ' '.join(text.strip().casefold().rstrip('.!?').split())
            correct = norm(body.answer) == norm(q['answer'])
            responses[body.question_id] = {'correct': correct, 'answer': q['answer'], 'submitted': body.answer, 'explanation': q['explanation']}
            completed = now() if len(responses) == len(questions) else None
            c.execute('UPDATE attempts SET responses=?,completed=? WHERE id=?', (json.dumps(responses, ensure_ascii=False), completed, ident))
        fresh = c.execute('SELECT * FROM attempts WHERE id=?', (ident,)).fetchone()
    return {'feedback': responses[body.question_id], 'result': result_data(fresh)}


@app.get('/api/attempts/{ident}')
def get_attempt(ident: str):
    with db() as c:
        row = c.execute('SELECT * FROM attempts WHERE id=?', (ident,)).fetchone()
    if not row:
        raise HTTPException(404, 'Không tìm thấy lượt chơi.')
    result = result_data(row)
    with db() as c:document=get_lesson(c,row['lesson_id'])['document']
    result['questions'] = public_questions(json.loads(row['questions']),document)
    result['match_bank'] = sorted(q['meaning'] for q in json.loads(row['questions']) if q['kind'] == 'match')
    return result


@app.get('/api/results', dependencies=[Depends(teacher)])
def results():
    with db() as c:
        rows = c.execute('SELECT * FROM attempts ORDER BY started DESC LIMIT 300').fetchall()
    return [result_data(row) for row in rows]


@app.get('/api/media/{ident}')
def get_media(ident: str,request: Request):
    authorized=False
    try:teacher(request);authorized=True
    except HTTPException:pass
    if not authorized:
        with db() as c:
            published=c.execute("SELECT * FROM lessons WHERE state='published'").fetchall()
            authorized=any(any(q.get('image_asset_id')==ident for q in quality.eligible(lesson_dict(row),DATA)) for row in published)
            if not authorized:
                authorized=database.media_in_attempt(c,ident)
        if not authorized:raise HTTPException(404,'Ảnh chưa được xuất bản cho học sinh.')
    if not media.asset_info(DATA,ident):raise HTTPException(404,'Ảnh không tồn tại hoặc đã thay đổi.')
    return FileResponse(DATA/'media'/(ident+'.png'),media_type='image/png',headers={'Cache-Control':'private, max-age=0','Content-Security-Policy':"default-src 'none'"})


def regenerate_question_core(ident: str,question_id: str):
    if not generation_lock.acquire(blocking=False):raise HTTPException(409,'Đang gọi AI; vui lòng chờ.')
    try:
        with db() as c:
            lesson=get_lesson(c,ident)
            if lesson['state']=='published':raise HTTPException(409,'Thu hồi về bản nháp trước khi tạo lại câu.')
            question=next((q for q in lesson['questions'] if q['id']==question_id),None)
            if not question:raise HTTPException(404,'Không tìm thấy câu hỏi.')
            settings=GenerateRequest(grade=lesson['grade'],count=2 if question['kind']=='match' else 1,kinds=[question['kind']],evidence_mode='visual' if question.get('requires_visual') else 'auto')
            document=dict(lesson['document'],sections=[s for s in lesson['document']['sections'] if s['number']==question['source']],assets=[a for a in lesson['document'].get('assets',[]) if a['source']==question['source']])
            key='regenerate-v3:'+hashlib.sha256((json.dumps(document,sort_keys=True)+settings.model_dump_json()).encode()).hexdigest()
            cached=c.execute('SELECT payload FROM cache WHERE key=?',(key,)).fetchone()
            if not cached:
                check_ai_budget(c)
                c.execute('INSERT INTO calls VALUES(?)',(time.time(),))
        if cached:payload=json.loads(cached['payload'])
        else:
            try:
                generated,meta=ai.generate(document,settings,media_root=DATA)
                payload={'questions':[q.model_dump() for q in generated.questions],'meta':meta}
            except Exception as error:
                status,message=ai_error(error);raise HTTPException(status,message) from None
            with db() as c:c.execute('INSERT OR REPLACE INTO cache VALUES(?,?)',(key,json.dumps(payload)))
        with db() as c:
            latest=get_lesson(c,ident)
            if latest['revision']!=lesson['revision']:raise HTTPException(409,'Bài vừa thay đổi; kết quả đã lưu cache, không ghi đè.')
            # Retain the rejected item for audit instead of deleting evidence.
            for q in latest['questions']:
                if q['id']==question_id or (question['kind']=='match' and q['kind']=='match'):q.update(hidden=True,approved=False)
            for q in payload['questions']:
                checked=quality.assess(dict(q,id=uuid.uuid4().hex,approved=False,hidden=False),latest['document'],DATA)
                if checked['validation_status']!='valid':raise HTTPException(422,'AI chưa tạo được câu đủ dữ kiện; giữ bản nháp.')
                latest['questions'].append(quality.persisted(checked))
            if len(latest['questions'])>40:raise HTTPException(422,'Bài tối đa 40 câu, kể cả câu tạm ẩn; xóa câu cũ không cần giữ trước.')
            result=persist_document(c,latest)
        return dict(result,generation={'cached':bool(cached)})
    finally:generation_lock.release()


class VisualFact(BaseModel):
    subject: str = Field(min_length=1,max_length=120)
    attribute: str = Field(pattern='^(color|count|position|shape|action|appearance|identity)$')
    value: str = Field(min_length=1,max_length=200)
    basis: str = Field(default='pixels',pattern='^(pixels|source_text)$')


class AssetReview(BaseModel):
    role: str = Field(pattern='^(learning|decoration|icon|background|context)$')
    description: str = Field(min_length=10,max_length=800)
    facts: list[VisualFact] = Field(default_factory=list,max_length=30)
    answer_leak: bool = True
    confirmed: bool = False
    transcript: str = Field(default='',max_length=1800)
    transcript_confirmed: bool = False


def owned_asset(lesson, ident):
    asset=media.asset_info(DATA,ident)
    if not asset or not any(a['id']==ident for a in lesson['document'].get('assets',[])) or asset['document_hash']!=lesson['document'].get('sha256'):
        raise HTTPException(422,'Ảnh không tồn tại hoặc không thuộc tài liệu này.')
    return asset


def persist_document(c, lesson):
    questions=[]
    for q in lesson['questions']:
        assessed=quality.assess(q,lesson['document'],DATA)
        if assessed['validation_status']!='valid':assessed['approved']=False
        questions.append(quality.persisted(assessed))
    c.execute('UPDATE lessons SET document=?,questions=?,state=?,revision=revision+1,updated=? WHERE id=?', (json.dumps(lesson['document'],ensure_ascii=False),json.dumps(questions,ensure_ascii=False),'draft',now(),lesson['id']))
    return get_lesson(c,lesson['id'])


@app.put('/api/lessons/{ident}/assets/{asset_id}',dependencies=[Depends(teacher)])
def review_asset(ident: str,asset_id: str,body: AssetReview):
    if not body.confirmed:raise HTTPException(422,'Cần xem ảnh thật và xác nhận dữ kiện trước khi duyệt.')
    with db() as c:
        lesson=get_lesson(c,ident);asset=owned_asset(lesson,asset_id)
        asset.update(role=body.role,description=body.description,facts=[f.model_dump() for f in body.facts],answer_leak=body.answer_leak,reviewed=True,verified_by='teacher',transcript=body.transcript,transcript_confirmed=body.transcript_confirmed)
        media.write_info(DATA,asset)
        lesson['document']['assets']=[asset if a['id']==asset_id else a for a in lesson['document']['assets']]
        # Re-review questions selecting a modified asset, even if its facts still fit.
        for q in lesson['questions']:
            if q.get('image_asset_id')==asset_id:q['approved']=False
        return persist_document(c,lesson)


class Crop(BaseModel):
    left: float = Field(default=0,ge=0,lt=1)
    top: float = Field(default=0,ge=0,lt=1)
    right: float = Field(default=1,gt=0,le=1)
    bottom: float = Field(default=1,gt=0,le=1)


@app.post('/api/lessons/{ident}/assets/{asset_id}/crop',dependencies=[Depends(teacher)])
def crop_asset(ident: str,asset_id: str,body: Crop):
    if body.right<=body.left or body.bottom<=body.top:raise HTTPException(422,'Vùng cắt không hợp lệ.')
    with db() as c:
        lesson=get_lesson(c,ident);asset=owned_asset(lesson,asset_id)
        derived=media.store_image((DATA/'media'/(asset_id+'.png')).read_bytes(),DATA,asset['document_hash'],asset['source'],'teacher_crop',picture_crop=[body.left,body.top,1-body.right,1-body.bottom],parent_asset_id=asset_id,context='teacher_selected_region')
        if not any(a['id']==derived['id'] for a in lesson['document']['assets']):lesson['document']['assets'].append(derived)
        return persist_document(c,lesson)


class AnalyzeRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1,max_length=6)


def analyze_images_core(ident: str,body: AnalyzeRequest):
    if not generation_lock.acquire(blocking=False):raise HTTPException(409,'Đang gọi AI; vui lòng chờ.')
    try:
        with db() as c:
            lesson=get_lesson(c,ident)
            assets=[owned_asset(lesson,a) for a in body.asset_ids]
            cache_key='vision-v1:'+hashlib.sha256(json.dumps([(a['id'],a['pixel_hash']) for a in assets]).encode()).hexdigest()
            cached=c.execute('SELECT payload FROM cache WHERE key=?',(cache_key,)).fetchone()
            if not cached:
                check_ai_budget(c)
                c.execute('INSERT INTO calls VALUES(?)',(time.time(),))
        if cached:payload=json.loads(cached['payload'])
        else:
            try:payload=ai.analyze_images(assets,DATA)
            except Exception as error:
                import re
                from dotenv import dotenv_values
                key=ai.configuration().get('GEMINI_API_KEY') or ''
                detail=getattr(error,'message',str(error))
                safe=detail.replace(key,'[REDACTED]') if key and isinstance(detail,str) else ''
                (DATA/'qa/last-vision-error.json').write_text(json.dumps({'type':type(error).__name__,'code':getattr(error,'code',None),'message':re.sub(r'https?://\S+','[URL omitted]',safe)[:1600]}),encoding='utf-8')
                status,message=ai_error(error);raise HTTPException(status,message) from None
            with db() as c:c.execute('INSERT OR REPLACE INTO cache VALUES(?,?)',(cache_key,json.dumps(payload)))
        with db() as c:
            lesson=get_lesson(c,ident)
            for analysis in payload['assets']:
                asset=owned_asset(lesson,analysis['id'])
                if asset.get('reviewed'):continue
                asset.update(**{k:v for k,v in analysis.items() if k!='id'},reviewed=False,verified_by='gemini_pending_teacher')
                media.write_info(DATA,asset)
                lesson['document']['assets']=[asset if a['id']==asset['id'] else a for a in lesson['document']['assets']]
            updated=persist_document(c,lesson)
        return dict(updated,analysis={'cached':bool(cached),'usage':payload.get('usage')})
    finally:generation_lock.release()


class Skip(BaseModel):
    question_id: str = Field(max_length=64)
    reason: str = Field(default='image_unavailable',pattern='^image_unavailable$')


@app.post('/api/attempts/{ident}/skip')
def skip_question(ident: str,body: Skip):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM attempts WHERE id=?',(ident,)).fetchone()
        if not row:raise HTTPException(404,'Không tìm thấy lượt chơi.')
        questions=json.loads(row['questions']);q=next((q for q in questions if q['id']==body.question_id),None)
        if not q:raise HTTPException(422,'Câu hỏi không thuộc lượt chơi.')
        document=get_lesson(c,row['lesson_id'])['document']
        if not quality.assess(q,document,DATA)['requires_visual']:raise HTTPException(422,'Chỉ bỏ qua không tính điểm khi câu phụ thuộc hình ảnh.')
        responses=json.loads(row['responses'])
        if q['id'] not in responses:
            responses[q['id']]={'correct':False,'skipped':True,'answer':'','submitted':'','explanation':'Không tải được dữ kiện hình ảnh. Câu này không tính vào điểm.'}
            c.execute('UPDATE attempts SET responses=?,completed=? WHERE id=?',(json.dumps(responses,ensure_ascii=False),now() if len(responses)==len(questions) else None,ident))
        fresh=c.execute('SELECT * FROM attempts WHERE id=?',(ident,)).fetchone()
    return {'feedback':responses[q['id']],'result':result_data(fresh)}



def queue_response(request,operation,ident,payload):
    if not job_queue:raise HTTPException(503,'Hàng đợi chưa sẵn sàng.')
    with db() as c:get_lesson(c,ident)
    data=job_queue.submit(operation,ident,payload,request.headers.get('idempotency-key',''))
    return JSONResponse(status_code=202,content=data)


@app.post('/api/lessons/{ident}/generate',dependencies=[Depends(teacher)])
def traced_generate(ident: str,settings: GenerateRequest,request: Request):
    if config.production() or request.headers.get('prefer')=='respond-async':return queue_response(request,'generate',ident,settings.model_dump())
    return traced_generate_core(ident,settings)


@app.post('/api/lessons/{ident}/questions/{question_id}/regenerate',dependencies=[Depends(teacher)])
def regenerate_question(ident: str,question_id: str,request: Request):
    if config.production() or request.headers.get('prefer')=='respond-async':return queue_response(request,'regenerate',ident,{'question_id':question_id})
    return regenerate_question_core(ident,question_id)


@app.post('/api/lessons/{ident}/analyze-images',dependencies=[Depends(teacher)])
def analyze_images(ident: str,body: AnalyzeRequest,request: Request):
    if config.production() or request.headers.get('prefer')=='respond-async':return queue_response(request,'analyze',ident,body.model_dump())
    return analyze_images_core(ident,body)


@app.get('/api/jobs/{ident}',dependencies=[Depends(teacher)])
def job_status(ident: str):
    return job_queue.get(ident)


class UploadStart(BaseModel):
    filename: str = Field(min_length=1,max_length=160)
    size: int = Field(gt=0,le=MAX_BYTES)


@app.post('/api/uploads',dependencies=[Depends(teacher)])
def start_upload(body: UploadStart):
    filename=Path(body.filename).name
    if Path(filename).suffix.lower() not in EXTENSIONS:raise HTTPException(415,'Chỉ hỗ trợ PPTX/PDF/DOCX/TXT.')
    with db() as c:
        if c.execute("SELECT COUNT(*) FROM upload_sessions WHERE state='uploading'").fetchone()[0]>=10:raise HTTPException(429,'Có 10 file tải dở. Hoàn thành file đang tải trước.')
        ident=uuid.uuid4().hex
        (DATA/'uploads'/(ident+'.part')).touch(exist_ok=False)
        c.execute('INSERT INTO upload_sessions VALUES(?,?,?,?,?,?)',(ident,filename,body.size,0,'uploading',time.time()))
    return {'upload_id':ident,'offset':0,'chunk_bytes':2*1024*1024}


def upload_state(ident,c):
    row=c.execute('SELECT * FROM upload_sessions WHERE id=?',(ident,)).fetchone()
    if not row:raise HTTPException(404,'Không tìm thấy file tải dở.')
    path=DATA/'uploads'/(row['id']+'.part')
    state=dict(row)
    # A crash after fsync but before the SQLite commit can leave acknowledged bytes ahead.
    if state['state']=='uploading' and not config.object_storage():
        if not path.exists():raise HTTPException(409,'File tạm không tồn tại; cần chọn tải lại.')
        actual=path.stat().st_size
        if actual>state['size']:raise HTTPException(409,'File tạm sai kích thước; không tiếp tục trích xuất.')
        if actual!=state['offset']:
            state['offset']=actual;c.execute('UPDATE upload_sessions SET offset=? WHERE id=?',(actual,ident))
    return state,path


@app.get('/api/uploads/{ident}',dependencies=[Depends(teacher)])
def get_upload(ident: str):
    with upload_lock,db() as c:state,path=upload_state(ident,c)
    return {'upload_id':ident,'offset':state['offset'],'size':state['size'],'state':state['state']}


@app.put('/api/uploads/{ident}',dependencies=[Depends(teacher)])
async def upload_chunk(ident: str,offset: int,request: Request):
    chunk=bytearray()
    async for part in request.stream():
        chunk.extend(part)
        if len(chunk)>2*1024*1024:raise HTTPException(413,'Mỗi phần tải tối đa 2 MB.')
    if not chunk:raise HTTPException(422,'Phần tải trống.')
    with upload_lock,db() as c:
        c.execute('BEGIN IMMEDIATE');state,path=upload_state(ident,c)
        if state['state']!='uploading' or state['offset']!=offset:raise HTTPException(409,'Vị trí tải đã thay đổi; đọc trạng thái để tiếp tục, không gửi lặp dữ liệu.')
        if offset+len(chunk)>state['size']:raise HTTPException(413,'Dữ liệu vượt kích thước đã khai báo.')
        if config.object_storage():objects.put_bytes('upload-chunks/'+ident+'/'+str(offset),bytes(chunk))
        else:
            with path.open('ab') as f:f.write(chunk);f.flush();os.fsync(f.fileno())
        c.execute('UPDATE upload_sessions SET offset=? WHERE id=?',(offset+len(chunk),ident))
    return {'upload_id':ident,'offset':offset+len(chunk)}


@app.post('/api/uploads/{ident}/complete',dependencies=[Depends(teacher)])
def complete_upload(ident: str,request: Request,restore_ident: str = ""):
    with upload_lock,db() as c:
        state,path=upload_state(ident,c)
        if state['offset']!=state['size']:raise HTTPException(409,'File chưa tải đủ; tiếp tục từ offset đã lưu.')
        if state['state']=='complete':
            done=database.completed_upload_job(c,ident)
            if done:return JSONResponse(status_code=202,content={'job_id':done['id'],'state':'succeeded'})
            raise HTTPException(409,'File đã xử lý nhưng job bị gián đoạn. Kiểm tra thư viện, không tự tạo bản sao.')
    if restore_ident:
        with db() as c:get_lesson(c,restore_ident)
    task=job_queue.submit('restore' if restore_ident else 'upload',restore_ident or 'upload:'+ident,{'upload_id':ident},request.headers.get('idempotency-key','upload:'+ident))
    return JSONResponse(status_code=202,content=task)


def dispatch_job(operation,ident,payload):
    if operation=='generate':return traced_generate_core(ident,GenerateRequest.model_validate(payload))
    if operation=='regenerate':return regenerate_question_core(ident,payload['question_id'])
    if operation=='analyze':return analyze_images_core(ident,AnalyzeRequest.model_validate(payload))
    if operation in ('upload','restore'):
        upload_id=payload.get('upload_id',ident.removeprefix('upload:'))
        with db() as c:state,path=upload_state(upload_id,c)
        try:
            if config.object_storage():path=objects.materialize_upload(DATA,upload_id,state['size'])
            with path.open('rb') as f:
                file=UploadFile(file=f,filename=state['filename'])
                result=restore_source(ident,file) if operation=='restore' else upload(file)
        except Exception:
            with db() as c:c.execute("UPDATE upload_sessions SET state='failed' WHERE id=?",(upload_id,))
            raise
        with db() as c:c.execute("UPDATE upload_sessions SET state='complete' WHERE id=?",(upload_id,))
        path.unlink(missing_ok=True) # Only this newly received staging file; original survives in sources/.
        return result
    raise HTTPException(422,'Loại tác vụ không hợp lệ.')


DIST = ROOT / 'frontend/dist'
if DIST.exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

    @app.get('/{path:path}')
    def index(path: str):
        if path.startswith('api/'):
            raise HTTPException(404, 'Không tìm thấy API.')
        return FileResponse(DIST / 'index.html')
