"""Production-only regression; generated sources, isolated data, no Google calls."""
import io,json,sqlite3,threading,time,zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from . import main,ai,config
from .jobs import Queue
from .schemas import Generated
from scripts.data_bundle import export_data,inspect_bundle

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('ADVENTURE_ENV','local');monkeypatch.setenv('ADVENTURE_MAINTENANCE','0')
    monkeypatch.setenv('ADVENTURE_RENDER_PPTX','0');monkeypatch.setenv('ADVENTURE_AUDIT_IMAGES','0')
    monkeypatch.setattr(main,'DATA',tmp_path/'data');monkeypatch.setattr(main,'DB',tmp_path/'data/adventure.sqlite3')
    monkeypatch.setattr(main,'seed',lambda:None)
    main.login_attempts.clear()
    with TestClient(main.app) as c:yield c

def login(c,headers=None):
    r=c.post('/api/login',json={'code':(main.DATA/'teacher-access.txt').read_text().strip()},headers=headers or {})
    assert r.status_code==200,r.text
    return r

def source(c):
    login(c);r=c.post('/api/upload',files={'file':('fruit.txt',b'apple table')});assert r.status_code==200,r.text
    return r.json()

def generated():
    return Generated(questions=[dict(kind='quiz',prompt='Choose a fruit.',answer='apple',options=['apple','table'],explanation='Apple là quả táo.',source=1,quote='apple',word='',meaning='',speech='')])

def poll(c,id,seconds=8):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        r=c.get('/api/jobs/'+id);assert r.status_code==200,r.text
        result=r.json()
        if result['state'] not in ('queued','running'):return result
        time.sleep(.05)
    pytest.fail('Job did not finish')

def test_env_precedence_and_explicit_empty(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-runtime-secret');monkeypatch.setenv('GEMINI_MODEL','test-runtime-model')
    with patch.object(ai,'dotenv_values',return_value={'GEMINI_API_KEY':'test-local-secret','GEMINI_MODEL':'test-local-model'}):
        assert ai.configuration()=={'GEMINI_API_KEY':'test-runtime-secret','GEMINI_MODEL':'test-runtime-model'}
        monkeypatch.setenv('GEMINI_API_KEY','');assert ai.configuration()['GEMINI_API_KEY']==''
        monkeypatch.delenv('GEMINI_API_KEY');assert ai.configuration()['GEMINI_API_KEY']=='test-local-secret'

def test_production_origin_host_cookie_and_auth(client,monkeypatch):
    monkeypatch.setenv('ADVENTURE_ENV','production');monkeypatch.setenv('ADVENTURE_ALLOWED_ORIGINS','https://class.example.netlify.app')
    monkeypatch.setenv('ADVENTURE_ALLOWED_HOSTS','api.example.onrender.com')
    client.base_url='https://api.example.onrender.com'
    good={'Origin':'https://class.example.netlify.app'}
    assert client.get('/api/lessons').status_code==401
    assert client.get('/api/jobs/unknown').status_code==401
    for headers in ({},{'Origin':'https://evil.example'},{'Origin':'https://class.example.netlify.app.evil.example'},{'Origin':'https://api.example.onrender.com'}):
        assert client.post('/api/login',json={'code':'not-secret'},headers=headers).status_code==403
    assert client.get('/api/health',headers={'Host':'evil.example','X-Forwarded-Host':'api.example.onrender.com'}).status_code==400
    r=login(client,good);cookie=r.headers['set-cookie'].lower()
    assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie and 'path=/api' in cookie and 'domain=' not in cookie
    assert client.get('/api/lessons').status_code==200
    assert client.post('/api/logout',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/lessons').status_code==200
    assert client.post('/api/logout',headers=good).status_code==200
    assert client.get('/api/lessons').status_code==401
    assert 'access-control-allow-origin' not in r.headers

def test_production_guard_and_maintenance(tmp_path,monkeypatch):
    monkeypatch.setenv('ADVENTURE_ENV','production');monkeypatch.setenv('ADVENTURE_ALLOWED_ORIGINS','https://class.example.netlify.app');monkeypatch.setenv('ADVENTURE_ALLOWED_HOSTS','testserver')
    monkeypatch.setenv('ADVENTURE_DATA_DIR',str(tmp_path/'persistent'));monkeypatch.setenv('ADVENTURE_IMPORT_READY','no');monkeypatch.setenv('ADVENTURE_MAINTENANCE','0')
    with pytest.raises(RuntimeError,match='Migrate'):config.validate()
    monkeypatch.setenv('ADVENTURE_MAINTENANCE','1');monkeypatch.setattr(main,'DATA',tmp_path/'persistent')
    with TestClient(main.app) as c:
        assert c.get('/api/health').json()['status']=='maintenance'
        assert c.get('/api/lessons').status_code==503
        assert not (main.DATA/'adventure.sqlite3').exists()
    monkeypatch.setenv('ADVENTURE_ALLOWED_ORIGINS','http://unsafe.example')
    with pytest.raises(RuntimeError,match='HTTPS'):config.validate()

def test_async_submit_idempotent_and_persisted(client):
    l=source(client);started=threading.Event();release=threading.Event()
    def slow(*args,**kwargs):started.set();assert release.wait(5);return generated(),{'model':'test-only'}
    headers={'Prefer':'respond-async','Idempotency-Key':'same-submit'};url='/api/lessons/'+l['id']+'/generate'
    with patch.object(ai,'generate',side_effect=slow) as call:
        begin=time.monotonic();r=client.post(url,json={'count':1,'kinds':['quiz']},headers=headers)
        assert r.status_code==202 and time.monotonic()-begin<2
        assert started.wait(2)
        again=client.post(url,json={'count':1,'kinds':['quiz']},headers=headers)
        assert again.json()['job_id']==r.json()['job_id']
        assert client.get('/api/jobs/'+r.json()['job_id']).json()['state']=='running'
        release.set();result=poll(client,r.json()['job_id'])
        assert result['state']=='succeeded' and len(result['result']['questions'])==1
        assert call.call_count==1
    with main.db() as c:assert c.execute('SELECT state FROM jobs WHERE id=?',(r.json()['job_id'],)).fetchone()[0]=='succeeded'

def test_job_exceeds_26s_without_long_http(client):
    l=source(client);entered=threading.Event();release=threading.Event()
    def slow(*a,**k):entered.set();assert release.wait(32);return generated(),{}
    with patch.object(ai,'generate',side_effect=slow) as call:
        start=time.monotonic();r=client.post('/api/lessons/'+l['id']+'/generate',json={'count':1,'kinds':['quiz']},headers={'Prefer':'respond-async','Idempotency-Key':'latency-27s'})
        assert r.status_code==202 and time.monotonic()-start<2
        assert entered.wait(2);time.sleep(27)
        check=time.monotonic();assert client.get('/api/jobs/'+r.json()['job_id']).json()['state']=='running';assert time.monotonic()-check<2
        release.set();assert poll(client,r.json()['job_id'])['state']=='succeeded';assert call.call_count==1

def test_job_failure_preserves_document(client):
    l=source(client)
    with patch.object(ai,'generate',side_effect=ai.GenerationError(6,'INVALID_JSON','JSON không hợp lệ')):
        r=client.post('/api/lessons/'+l['id']+'/generate',json={'count':1,'kinds':['quiz']},headers={'Prefer':'respond-async','Idempotency-Key':'bad-json'})
        result=poll(client,r.json()['job_id']);assert result['state']=='failed' and result['error']['status']==422
    assert client.get('/api/lessons/'+l['id']).json()['document']['sections'][0]['text']=='apple table'

def test_queue_restarts_queued_and_never_retries_running(tmp_path):
    path=tmp_path/'jobs.sqlite3'
    @contextmanager
    def db():
        c=sqlite3.connect(path);c.row_factory=sqlite3.Row
        try:yield c;c.commit()
        finally:c.close()
    calls=[];q=Queue(db,lambda *args:calls.append(args) or {'ok':True});q.initialize()
    one=q.submit('generate','one',{},'queued-key')
    two=q.submit('generate','two',{},'running-key')
    with db() as c:c.execute("UPDATE jobs SET state='running' WHERE id=?",(two['job_id'],))
    restarted=Queue(db,q.dispatch);restarted.initialize()
    assert restarted.get(two['job_id'])['state']=='interrupted'
    assert restarted.once() and not restarted.once() and len(calls)==1
    assert restarted.get(one['job_id'])['state']=='succeeded'
    assert restarted.submit('generate','one',{},'queued-key')['job_id']==one['job_id']
    with pytest.raises(HTTPException):restarted.submit('generate','one',{'changed':True},'queued-key')

def test_chunk_upload_resume_limits_and_extract(client):
    login(client);data=b'apple table'
    r=client.post('/api/uploads',json={'filename':'chunk.txt','size':len(data)});ident=r.json()['upload_id'];url='/api/uploads/'+ident
    assert client.post(url+'/complete').status_code==409
    assert client.put(url+'?offset=0',content=data[:5]).status_code==200
    assert client.put(url+'?offset=0',content=data[:5]).status_code==409
    # Simulate a power loss between fsync and the offset transaction commit.
    with (main.DATA/'uploads'/(ident+'.part')).open('ab') as f:f.write(data[5:7])
    assert client.get(url).json()['offset']==7
    assert client.put(url+'?offset=7',content=data[7:]).status_code==200
    r=client.post(url+'/complete');assert r.status_code==202
    result=poll(client,r.json()['job_id']);assert result['state']=='succeeded'
    assert result['result']['document']['sections'][0]['text']=='apple table'
    assert list((main.DATA/'sources').glob('*.txt'))
    big=client.post('/api/uploads',json={'filename':'large.txt','size':3*1024*1024}).json()['upload_id']
    assert client.put('/api/uploads/'+big+'?offset=0',content=b'a'*(2*1024*1024+1)).status_code==413
    assert client.post('/api/uploads',json={'filename':'bad.exe','size':10}).status_code==415
    assert client.post('/api/uploads',json={'filename':'big.txt','size':101*1024*1024}).status_code==422

def test_chunk_restore_validates_original_hash(client):
    l=source(client);text=b'apple table'
    created=client.post('/api/uploads',json={'filename':'original.txt','size':len(text)}).json();id=created['upload_id']
    assert client.put('/api/uploads/'+id+'?offset=0',content=text).status_code==200
    r=client.post('/api/uploads/'+id+'/complete?restore_ident='+l['id']);result=poll(client,r.json()['job_id'])
    assert result['state']=='succeeded' and result['result']['id']==l['id']

def test_bundle_roundtrip_and_refuse_overwrite(client,tmp_path):
    l=source(client);bundle=tmp_path/'private.data-bundle.zip';target=tmp_path/'restored'
    exported=export_data(main.DATA,bundle,offline=True);verified=inspect_bundle(bundle)
    assert exported['database']==verified['database']
    assert inspect_bundle(bundle,target)['status']=='PASS'
    with sqlite3.connect(target/'adventure.sqlite3') as c:assert c.execute('SELECT id FROM lessons').fetchone()[0]==l['id']
    assert (target/'teacher-access.txt').read_bytes()==(main.DATA/'teacher-access.txt').read_bytes()
    assert list((target/'sources').glob('*.txt'))
    with pytest.raises(ValueError,match='not empty'):inspect_bundle(bundle,target)
    assert (target/'teacher-access.txt').exists()
    bad=tmp_path/'unsafe.zip'
    with zipfile.ZipFile(bad,'w') as z:z.writestr('../escape','bad')
    with pytest.raises(ValueError,match='Unsafe'):inspect_bundle(bad,tmp_path/'no-escape')
    assert not (tmp_path/'escape').exists()

def test_30_seconds_budget_and_daily_limit(client):
    with main.db() as c,patch('backend.main.time.time',return_value=100000):
        c.execute('INSERT INTO calls VALUES(?)',(99971,))
        with pytest.raises(HTTPException) as error:main.check_ai_budget(c)
        assert '30 giây' in str(error.value.detail)
        c.execute('UPDATE calls SET at=?',(99970,));main.check_ai_budget(c)
        c.executemany('INSERT INTO calls VALUES(?)',[(99000,)]*19)
        with pytest.raises(HTTPException) as error:main.check_ai_budget(c)
        assert '20 lượt/24 giờ' in str(error.value.detail)


def test_unpublished_media_is_teacher_only(client):
    from PIL import Image
    from . import media
    login(client);image=io.BytesIO();Image.new('RGB',(12,12),'red').save(image,format='PNG')
    asset=media.store_image(image.getvalue(),main.DATA,'a'*64,1,'private-preview')
    assert client.get('/api/media/'+asset['id']).status_code==200
    client.post('/api/logout')
    assert client.get('/api/media/'+asset['id']).status_code==404

def test_production_ai_routes_always_enqueue(client,monkeypatch):
    l=source(client)
    monkeypatch.setenv('ADVENTURE_ENV','production');monkeypatch.setenv('ADVENTURE_ALLOWED_ORIGINS','https://class.example.netlify.app');monkeypatch.setenv('ADVENTURE_ALLOWED_HOSTS','testserver')
    with patch.object(ai,'generate',return_value=(generated(),{})) as call:
        r=client.post('/api/lessons/'+l['id']+'/generate',json={'count':1,'kinds':['quiz']},headers={'Origin':'https://class.example.netlify.app','Idempotency-Key':'production-route'})
        assert r.status_code==202
        assert poll(client,r.json()['job_id'])['state']=='succeeded'
        assert call.call_count==1

def test_cache_reuses_identical_source_despite_upload_timings(client):
    first=source(client)
    second=client.post('/api/upload',files={'file':('renamed.txt',b'apple table')}).json()
    with patch.object(ai,'generate',return_value=(generated(),{})) as call:
        one=client.post('/api/lessons/'+first['id']+'/generate',json={'count':1,'kinds':['quiz']})
        two=client.post('/api/lessons/'+second['id']+'/generate',json={'count':1,'kinds':['quiz']})
    assert one.status_code==200 and two.status_code==200,two.text
    assert two.json()['generation']['cached'] and call.call_count==1


def test_single_writer_lock(tmp_path):
    from .storage import single_writer
    with single_writer(tmp_path):
        with pytest.raises(RuntimeError,match='Another process'):
            with single_writer(tmp_path):pass
    with single_writer(tmp_path):pass
