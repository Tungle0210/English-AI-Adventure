"""Isolated temporary SQLite; network calls mocked except dedicated live smoke."""
import copy
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from . import main, ai
from .schemas import Generated


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('ADVENTURE_RENDER_PPTX','0')
    monkeypatch.setenv('ADVENTURE_AUDIT_IMAGES','0')
    monkeypatch.setattr(main, 'DATA', tmp_path)
    monkeypatch.setattr(main, 'DB', tmp_path / 'test.sqlite3')
    main.login_attempts.clear()
    with TestClient(main.app) as c:
        yield c


def login(c):
    code = (main.DATA / 'teacher-access.txt').read_text()
    assert c.post('/api/login', json={'code': code}).status_code == 200


def sample(c):
    login(c)
    return c.get('/api/lessons').json()[0]


def save(c, l):
    return c.put('/api/lessons/'+l['id'], json={k:l[k] for k in ['title','grade','revision','questions']})


def published(c):
    l = sample(c)
    for q in l['questions']:
        q['approved'] = True
    l = save(c, l).json()
    response = c.post('/api/lessons/'+l['id']+'/publish')
    assert response.status_code == 200, response.text
    return response.json()


def test_health_and_auth(client):
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/api/lessons').status_code == 401
    assert client.post('/api/login', json={'code':'wrong'}).status_code == 401
    login(client)
    assert client.get('/api/teacher').status_code == 200
    assert 'GEMINI_API_KEY' not in client.get('/api/teacher').text
    client.post('/api/logout')
    assert client.get('/api/lessons').status_code == 401


def test_real_pptx_upload_and_sections(client):
    login(client)
    path = main.ROOT / 'input/Unit 6 Lesson 2 Period 3.pptx'
    response = client.post('/api/upload', files={'file': (path.name, path.read_bytes())})
    assert response.status_code == 200, response.text
    lesson = response.json()
    assert len(lesson['document']['sections']) == 10
    assert 'There are three.' in lesson['document']['sections'][4]['text']
    assert sum(s['images'] for s in lesson['document']['sections']) == 18
    assert not lesson['questions'] and lesson['state'] == 'draft'


@pytest.mark.parametrize('name,content,status',[('bad.exe',b'hi',415),('fake.pptx',b'not zip',422),('fake.pdf',b'not pdf',422),('empty.txt',b'',413),('binary.txt',b'\0abc',422)])
def test_invalid_uploads(client, name, content, status):
    login(client)
    assert client.post('/api/upload', files={'file':(name,content)}).status_code == status


def test_pdf_docx_txt(client):
    from docx import Document
    login(client)
    doc = Document();doc.add_paragraph('Our school has three buildings.')
    stream = io.BytesIO();doc.save(stream)
    for name, content in [('lesson.docx',stream.getvalue()),('lesson.txt',b'Our school has three buildings.')]:
        response = client.post('/api/upload',files={'file':(name,content)})
        assert response.status_code == 200
        assert 'three buildings' in response.json()['document']['sections'][0]['text']
        assert response.json()['document']['label'] == 'Đoạn'
    path = main.ROOT/'input/KẾ HOẠCH THIẾT KẾ SP DẠY HỌC SỬ DỤNG CNS-AI_2026-2027.pdf'
    response = client.post('/api/upload', files={'file':(path.name,path.read_bytes())})
    assert response.status_code == 200, response.text
    assert len(response.json()['document']['sections']) == 5


def test_edit_review_publish_and_stale_revision(client):
    l = sample(client)
    assert client.get('/api/play/'+l['code']).status_code == 404
    assert client.post('/api/lessons/'+l['id']+'/publish').status_code == 422
    for q in l['questions']:q['approved']=True
    l['questions'][0]['explanation'] += ' Reviewed edit.'
    saved=save(client,l).json()
    assert not saved['questions'][0]['approved']
    assert save(client,l).status_code == 409
    saved['questions'][0]['approved']=True
    saved=save(client,saved).json()
    response=client.post('/api/lessons/'+l['id']+'/publish')
    assert response.status_code==200
    assert client.get('/api/play/'+l['code']).status_code==200
    saved=response.json(); saved['questions'][0]['answer']='not in options'
    assert save(client,saved).status_code==422
    client.post('/api/lessons/'+l['id']+'/unpublish')
    assert client.get('/api/play/'+l['code']).status_code==404


def test_add_delete_and_invalid_source(client):
    l=sample(client)
    q=copy.deepcopy(l['questions'][0]);q['id']='new-item';q['prompt']='Which word means trường học?';q['approved']=True
    l['questions'].append(q)
    l=save(client,l).json()
    assert not l['questions'][-1]['approved']
    l['questions'].pop()
    l=save(client,l).json()
    l['questions'][0]['quote']='This quote was invented.'
    assert save(client,l).status_code==422


@pytest.mark.parametrize('mode',['all','vocabulary','quiz','match','listen','fill'])
def test_student_games_score_idempotence_and_persistence(client,mode):
    l=published(client)
    answers={q['id']:q['answer'] for q in l['questions']}
    started=client.post('/api/play/'+l['code']+'/start',json={'mode':mode})
    assert started.status_code==200
    a=started.json()
    assert all('answer' not in q and 'explanation' not in q for q in a['questions'])
    for q in a['questions']:
        response=client.post('/api/attempts/'+a['id']+'/answer',json={'question_id':q['id'],'answer':answers[q['id']]})
        assert response.status_code==200
        assert response.json()['feedback']['correct']
    result=response.json()['result']
    assert result['completed'] and result['score']==100
    retry=client.post('/api/attempts/'+a['id']+'/answer',json={'question_id':q['id'],'answer':'wrong'})
    assert retry.json()['result']['score']==100
    assert client.get('/api/attempts/'+a['id']).json()['score']==100
    assert client.get('/api/results').json()[0]['completed']


def test_wrong_answer_and_published_snapshot(client):
    l=published(client)
    a=client.post('/api/play/'+l['code']+'/start',json={'mode':'fill'}).json()
    client.post('/api/lessons/'+l['id']+'/unpublish')
    r=client.post('/api/attempts/'+a['id']+'/answer',json={'question_id':a['questions'][0]['id'],'answer':'four'})
    assert r.json()['result']['score']==0 and r.json()['result']['completed']
    assert r.json()['feedback']['answer']=='three'
    assert client.post('/api/play/'+l['code']+'/start',json={'mode':'fill'}).status_code==404


@pytest.mark.parametrize('code,expected',[(429,429),(404,502),(403,502),(503,503)])
def test_ai_error_mapping_and_no_retry(client,code,expected):
    login(client)
    l=client.post('/api/upload',files={'file':('school.txt',b'Our school has three buildings. There are three.')}).json()
    class APIError(Exception): pass
    error=APIError();error.code=code
    with patch.object(main.ai,'generate',side_effect=error) as mocked:
        response=client.post('/api/lessons/'+l['id']+'/generate',json={'count':1,'kinds':['quiz']})
        assert response.status_code==expected
        assert mocked.call_count==1
    assert not client.get('/api/lessons/'+l['id']).json()['questions']


def test_missing_key_timeout_bad_json(client):
    assert main.ai_error(RuntimeError('MISSING_KEY'))[0]==503
    assert main.ai_error(TimeoutError())[0]==504
    assert main.ai_error(ValueError())[0]==422
    with patch.object(ai,'dotenv_values',return_value={}):
        with pytest.raises(RuntimeError,match='MISSING_KEY'):
            ai.generate({},None)


def test_ai_cache_and_duplicate_request(client):
    login(client)
    l=client.post('/api/upload',files={'file':('school.txt',b'Our school has three buildings.')}).json()
    q={'kind':'quiz','prompt':'How many buildings are there?','answer':'Three','options':['Three','Four'],'explanation':'Nguồn có three buildings.','source':1,'quote':'three buildings','word':'','meaning':'','speech':'','question_type':'reading','source_evidence':'Our school has three buildings.'}
    with patch.object(main.ai,'generate',return_value=(Generated(questions=[q]),{'model':'test','usage':{}})) as mocked:
        settings={'count':1,'kinds':['quiz']}
        r=client.post('/api/lessons/'+l['id']+'/generate',json=settings)
        assert r.status_code==200, r.text
        assert not r.json()['generation']['cached']
        assert client.post('/api/lessons/'+l['id']+'/generate',json=settings).status_code==409
        l=r.json();l['questions']=[];l=save(client,l).json()
        r=client.post('/api/lessons/'+l['id']+'/generate',json=settings)
        assert r.json()['generation']['cached']
        assert mocked.call_count==1


def test_csrf_and_rate_limit(client):
    assert client.post('/api/login',json={'code':'x'},headers={'origin':'https://other.example'}).status_code==403
    for _ in range(5):client.post('/api/login',json={'code':'x'})
    assert client.post('/api/login',json={'code':'x'}).status_code==429


def test_no_single_pair_publish(client):
    l=sample(client)
    l['questions']=[next(q for q in l['questions'] if q['kind']=='match')]
    l['questions'][0]['approved']=True
    l=save(client,l).json()
    assert client.post('/api/lessons/'+l['id']+'/publish').status_code==422


def test_oversize_request_header(client):
    login(client)
    assert client.post('/api/upload', content=b'', headers={'content-length':str(102*1024*1024)}).status_code==413


def test_generation_lock_and_request_validation(client):
    l=sample(client)
    main.generation_lock.acquire()
    try:
        assert client.post('/api/lessons/'+l['id']+'/generate',json={'count':6}).status_code==409
    finally:
        main.generation_lock.release()
    assert client.post('/api/lessons/'+l['id']+'/generate',json={'count':1,'kinds':['quiz','match']}).status_code==422


def test_saved_lesson_works_without_ai(client):
    l=published(client)
    with patch.object(main.ai,'generate',side_effect=RuntimeError('MISSING_KEY')) as mocked:
        assert client.get('/api/play/'+l['code']).status_code==200
        a=client.post('/api/play/'+l['code']+'/start',json={'mode':'fill'}).json()
        r=client.post('/api/attempts/'+a['id']+'/answer',json={'question_id':a['questions'][0]['id'],'answer':'three'})
        assert r.json()['result']['completed'] and r.json()['result']['score']==100
        mocked.assert_not_called()


def test_illustration_must_match_word(client):
    l=sample(client)
    l['questions'][0]['image']='school'
    r=save(client,l)
    assert r.status_code==200
    l=r.json();l['questions'][0]['image']='town'
    assert save(client,l).status_code==422
