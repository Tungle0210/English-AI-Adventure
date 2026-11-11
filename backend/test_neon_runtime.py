"""Isolated PostgreSQL-wire/S3 tests, never use DATABASE_URL from local secrets."""
import hashlib,io,json,os,sqlite3,uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from backend import main,objects,database,config
from backend.schema import CORE,QUEUE
from scripts.cloud_migration import build_plan,apply_copy

@pytest.fixture
def cloud(tmp_path,monkeypatch):
    if os.environ.get('EAA_REHEARSAL_TESTS')!='yes':pytest.skip('Needs separately started loopback PostgreSQL WASM; never falls back to Neon')
    schema='test_'+uuid.uuid4().hex[:16];work=tmp_path/'work';source=work/'source';source.mkdir(parents=True)
    (source/'teacher-access.txt').write_text('rehearsal-teacher-only',encoding='utf-8')
    (source/'sources').mkdir();(source/'sources/source.txt').write_text('apple table',encoding='utf-8')
    doc={'label':'Đoạn','sections':[{'number':1,'text':'apple table','images':0}],'assets':[],'warnings':[],'quality_schema':3,'reading_gate':1,'source_retained':True}
    with closing(sqlite3.connect(source/'adventure.sqlite3')) as c:
        c.executescript(CORE+QUEUE)
        c.execute('INSERT INTO lessons VALUES(?,?,?,?,?,?,?,?,?,?)',('lesson-kept','Rehearsal lesson',3,'draft','TESTCODE',1,json.dumps(doc),'[]','manual','2026-11-11'))
        c.commit()
    build_plan(work)
    assert 'teacher-access.txt' not in [f['path'] for f in json.loads((work/'manifest.json').read_text())['files']]
    values={'ADVENTURE_CLOUD_ENABLE':'yes','ADVENTURE_DATABASE_BACKEND':'postgres','ADVENTURE_STORAGE_BACKEND':'s3','DATABASE_URL':'postgresql://postgres@127.0.0.1:55432/postgres','ADVENTURE_PG_SCHEMA':schema,'ADVENTURE_PG_POOL_MAX':'1','PGSSLMODE':'disable','ADVENTURE_ENV':'local','ADVENTURE_MAINTENANCE':'0','AWS_ACCESS_KEY_ID':'test-only','AWS_SECRET_ACCESS_KEY':'test-only-secret','AWS_SESSION_TOKEN':'','AWS_REGION':'us-east-2','S3_ENDPOINT_URL':'','S3_BUCKET':'rehearsal-private','S3_PREFIX':schema}
    for k,v in values.items():monkeypatch.setenv(k,v)
    monkeypatch.setattr(main,'DATA',tmp_path/'cache');monkeypatch.setattr(main,'DB',tmp_path/'cache/unused.sqlite3')
    with mock_aws():
        objects.client().create_bucket(Bucket=objects.bucket(),CreateBucketConfiguration={'LocationConstraint':'us-east-2'})
        apply_copy(work,values['DATABASE_URL'],schema)
        with TestClient(main.app) as c:
            r=c.post('/api/login',json={'code':'rehearsal-teacher-only'});assert r.status_code==200,r.text
            yield c
    with database.POOL_LOCK:
        for pool in database.POOLS.values():pool.close()
        database.POOLS.clear()

def test_sql_translation():
    assert database.parameters("SELECT offset, '?' AS text, a=?")=="SELECT \"offset\", '?' AS text, a=%s"
    assert database.parameters("SELECT '50%' WHERE a=?")=="SELECT '50%%' WHERE a=%s"

def test_cloud_activation_is_explicit(monkeypatch):
    monkeypatch.setenv('ADVENTURE_DATABASE_BACKEND','postgres');monkeypatch.setenv('ADVENTURE_STORAGE_BACKEND','s3');monkeypatch.setenv('ADVENTURE_CLOUD_ENABLE','no')
    assert not config.postgres() and not config.object_storage()

def test_s3_checksum_and_cold_cache(tmp_path,monkeypatch):
    vals={'ADVENTURE_CLOUD_ENABLE':'yes','ADVENTURE_STORAGE_BACKEND':'s3','AWS_ACCESS_KEY_ID':'test-only','AWS_SECRET_ACCESS_KEY':'test-only-secret','AWS_SESSION_TOKEN':'','AWS_REGION':'us-east-2','S3_ENDPOINT_URL':'','S3_BUCKET':'rehearsal-checksums','S3_PREFIX':'test'}
    for k,v in vals.items():monkeypatch.setenv(k,v)
    with mock_aws():
        objects.client().create_bucket(Bucket=objects.bucket(),CreateBucketConfiguration={'LocationConstraint':'us-east-2'})
        root=tmp_path/'first';(root/'sources').mkdir(parents=True);(root/'sources/a.txt').write_bytes(b'private source')
        objects.publish(root,'sources/a.txt')
        assert objects.ensure(tmp_path/'cold','sources/a.txt').read_bytes()==b'private source'
        objects.client().put_object(Bucket=objects.bucket(),Key=objects.key('sources/bad'),Body=b'wrong',Metadata={'sha256':'0'*64})
        with pytest.raises(objects.ObjectFailure):objects.ensure(tmp_path/'cold','sources/bad')
        with pytest.raises(objects.ObjectFailure):objects.key('../escape')

def test_postgres_teacher_upload_resume_queue_and_play(cloud,tmp_path):
    c=cloud
    assert not (main.DATA/'adventure.sqlite3').exists()
    assert not (main.DATA/'teacher-access.txt').exists()
    data=b'apple table';r=c.post('/api/uploads',json={'filename':'new.txt','size':len(data)});assert r.status_code==200,r.text
    id=r.json()['upload_id'];assert c.put('/api/uploads/'+id+'?offset=0',content=data[:5]).status_code==200
    # Simulate Free ephemeral disk loss; acknowledged parts must survive in S3.
    (main.DATA/'uploads'/(id+'.part')).unlink(missing_ok=True)
    assert c.get('/api/uploads/'+id).json()['offset']==5
    assert c.put('/api/uploads/'+id+'?offset=5',content=data[5:]).status_code==200
    r=c.post('/api/uploads/'+id+'/complete');assert r.status_code==202,r.text
    import time
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        status=c.get('/api/jobs/'+r.json()['job_id']).json()
        if status['state'] not in ('queued','running'):break
        time.sleep(.1)
    assert status['state']=='succeeded',status
    l=status['result'];assert l['document']['sections'][0]['text']=='apple table'
    # Real mutation/edit/review/publish/score pipeline, no Gemini request.
    q={'id':'question-kept','kind':'quiz','prompt':'Choose a fruit.','answer':'apple','options':['apple','table'],'explanation':'Apple là quả táo.','source':1,'quote':'apple','word':'','meaning':'','speech':'','approved':False}
    body={k:l[k] for k in ['title','grade','revision']};body['questions']=[q]
    r=c.put('/api/lessons/'+l['id'],json=body);assert r.status_code==200,r.text
    l=r.json();body={k:l[k] for k in ['title','grade','revision','questions']};body['questions'][0]['approved']=True
    r=c.put('/api/lessons/'+l['id'],json=body);assert r.status_code==200,r.text
    l=r.json();assert l['questions'][0]['id']=='question-kept'
    assert c.post('/api/lessons/'+l['id']+'/publish').status_code==200
    attempt=c.post('/api/play/'+l['code']+'/start',json={'mode':'quiz'}).json()
    r=c.post('/api/attempts/'+attempt['id']+'/answer',json={'question_id':'question-kept','answer':'apple'});assert r.status_code==200,r.text
    assert r.json()['result']['score']==100
    assert any(x['attempt_id']==attempt['id'] for x in c.get('/api/results').json())

def test_postgres_failed_ai_and_idempotency(cloud):
    c=cloud;headers={'Prefer':'respond-async','Idempotency-Key':'no-duplicate-google'}
    from backend import ai
    with patch.object(ai,'generate',side_effect=RuntimeError('MISSING_KEY')) as call:
        a=c.post('/api/lessons/lesson-kept/generate',json={'count':1,'kinds':['quiz']},headers=headers)
        b=c.post('/api/lessons/lesson-kept/generate',json={'count':1,'kinds':['quiz']},headers=headers)
        assert a.status_code==b.status_code==202
        assert a.json()['job_id']==b.json()['job_id']
        import time
        for _ in range(100):
            state=c.get('/api/jobs/'+a.json()['job_id']).json()
            if state['state'] not in ('queued','running'):break
            time.sleep(.1)
        assert state['state']=='failed',state
        assert call.call_count==1
        assert c.get('/api/lessons/lesson-kept').json()['document']['sections'][0]['text']=='apple table'


@pytest.mark.parametrize('mode',['vocabulary','quiz','match','listen','fill','all'])
def test_all_games_on_postgres(cloud,mode):
    c=cloud;l=c.get('/api/lessons/lesson-kept').json()
    definitions=[('vocabulary','What does apple mean?','táo',['táo','bàn'],'apple','táo',''),('quiz','Choose a fruit.','apple',['apple','table'],'','',''),('match','Match apple.','táo',[],'apple','táo',''),('match','Match table.','bàn',[],'table','bàn',''),('listen','Which word do you hear?','apple',['apple','table'],'','','The word is apple.'),('fill','I can see an ___.','apple',[],'','','')]
    questions=[]
    for i,(kind,prompt,answer,options,word,meaning,speech) in enumerate(definitions):questions.append(dict(id='stable-'+str(i),kind=kind,prompt=prompt,answer=answer,options=options,word=word,meaning=meaning,speech=speech,explanation='Đối chiếu từ trong nguồn.',source=1,quote='table' if word=='table' else 'apple',approved=False))
    body={k:l[k] for k in ['title','grade','revision']};body['questions']=questions
    r=c.put('/api/lessons/lesson-kept',json=body);assert r.status_code==200,r.text
    l=r.json();body={k:l[k] for k in ['title','grade','revision','questions']}
    for q in body['questions']:q['approved']=True
    r=c.put('/api/lessons/lesson-kept',json=body);assert r.status_code==200,r.text
    assert c.post('/api/lessons/lesson-kept/publish').status_code==200
    a=c.post('/api/play/TESTCODE/start',json={'mode':mode}).json();answers={q['id']:q['answer'] for q in questions}
    for q in a['questions']:
        r=c.post('/api/attempts/'+a['id']+'/answer',json={'question_id':q['id'],'answer':answers[q['id']]});assert r.status_code==200,r.text
    result=r.json()['result'];assert result['completed'] and result['score']==100


def test_readonly_cloud_backup_and_refuse_overwrite(cloud,tmp_path):
    from scripts.cloud_backup import export_cloud
    target=tmp_path/'cloud-backup'
    # PGliteSocket uses one physical connection; release the idle test pool before a separate backup connection.
    for pool in database.POOLS.values():pool.close()
    database.POOLS.clear()
    result=export_cloud(target,'postgresql://postgres@127.0.0.1:55432/postgres',database.schema_name(),writers_stopped=True)
    assert result['status']=='PASS' and result['tables']['lessons']==1
    with closing(sqlite3.connect(target/'adventure.sqlite3')) as c:assert c.execute('SELECT id FROM lessons').fetchone()[0]=='lesson-kept'
    assert (target/'sources/source.txt').read_text()=='apple table'
    assert not (target/'teacher-access.txt').exists()
    with closing(sqlite3.connect(target/'adventure.sqlite3')) as c:
        c.row_factory=sqlite3.Row
        assert database.teacher_matches(c,'rehearsal-teacher-only')
    with pytest.raises(ValueError):export_cloud(target,writers_stopped=True)

def test_partial_object_namespace_is_detected(tmp_path,monkeypatch):
    vals={'ADVENTURE_CLOUD_ENABLE':'yes','ADVENTURE_STORAGE_BACKEND':'s3','AWS_ACCESS_KEY_ID':'test-only','AWS_SECRET_ACCESS_KEY':'test-only-secret','AWS_SESSION_TOKEN':'','AWS_REGION':'us-east-2','S3_ENDPOINT_URL':'','S3_BUCKET':'rehearsal-existing','S3_PREFIX':'do-not-overwrite'}
    for k,v in vals.items():monkeypatch.setenv(k,v)
    with mock_aws():
        objects.client().create_bucket(Bucket=objects.bucket(),CreateBucketConfiguration={'LocationConstraint':'us-east-2'})
        objects.put_bytes('media/existing',b'keep')
        assert objects.list_names('')==['media/existing']


def test_library_summary_avoids_eager_objects(cloud):
    with patch('backend.quality.refresh_lesson',side_effect=AssertionError('Must not fetch all media')):
        r=cloud.get('/api/lessons?summary=1')
    assert r.status_code==200 and r.json()[0]['detail_loaded'] is False
    assert r.json()[0]['document']['sections'][0]['text']==''
    assert cloud.get('/api/lessons/lesson-kept').json()['document']['sections'][0]['text']=='apple table'


def test_s3_media_cold_cache_requires_teacher_if_unpublished(cloud):
    from PIL import Image
    from backend import media
    data=io.BytesIO();Image.new('RGB',(24,24),'red').save(data,format='PNG')
    asset=media.store_image(data.getvalue(),main.DATA,'b'*64,1,'synthetic-test-only')
    (main.DATA/'media'/(asset['id']+'.png')).unlink();(main.DATA/'media'/(asset['id']+'.json')).unlink()
    r=cloud.get('/api/media/'+asset['id']);assert r.status_code==200
    assert hashlib.sha256(r.content).hexdigest()==asset['pixel_hash']
    cloud.post('/api/logout');assert cloud.get('/api/media/'+asset['id']).status_code==404
