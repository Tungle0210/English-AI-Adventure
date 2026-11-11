import json
from unittest.mock import patch
from .test_app import client,login
from . import ai,main
from .schemas import GenerateRequest
from pathlib import Path

def fixture_question():
    return dict(kind='quiz',prompt='Choose the English word for a fruit.',answer='apple',options=['apple','table'],explanation='Apple nghĩa là quả táo.',source=1,quote='apple',word='',meaning='',speech='')

def test_partial_and_bad_items():
    q=fixture_question(); doc={'sections':[{'number':1,'text':'apple table'}]}
    data,meta=ai.validate_output(json.dumps({'questions':[q,dict(q,source=9)]}),doc,GenerateRequest(count=2,kinds=['quiz']),Path('.'))
    assert len(data.questions)==1 and meta['status']=='PARTIAL' and meta['rejected']
    assert meta['accepted']==1

def test_invalid_json():
    import pytest
    with pytest.raises(ai.GenerationError) as error:ai.validate_output('{bad',{},GenerateRequest(count=1,kinds=['quiz']),Path('.'))
    assert error.value.stage==6

def test_upload_failure_retry_and_provider_origin(client):
    login(client)
    l=client.post('/api/upload',files={'file':('retry.txt',b'apple table')}).json()
    url='/api/lessons/'+l['id']
    class Busy(Exception):code=503
    for error,status,origin in [(Busy(),503,'gemini'),(ConnectionError(),502,'backend'),(ai.GenerationError(6,'INVALID_JSON','JSON không hợp lệ'),422,'validation')]:
        with patch('backend.ai.generate',side_effect=error):
            r=client.post(url+'/generate',json={'count':1,'kinds':['quiz'],'force_refresh':True})
        assert r.status_code==status,r.text
        assert r.json()['detail']['origin']==origin
        assert client.get(url).json()['document']['sections'][0]['text']=='apple table'
        with main.db() as c:c.execute('DELETE FROM calls')
    generated,validation=ai.validate_output(json.dumps({'questions':[fixture_question()]}),l['document'],GenerateRequest(count=2,kinds=['quiz']),main.DATA)
    with patch('backend.ai.generate',return_value=(generated,{'validation':validation})) as call:
        r=client.post(url+'/generate',json={'count':2,'kinds':['quiz'],'force_refresh':True})
    assert r.status_code==200,r.text
    assert call.call_count==1 and len(r.json()['questions'])==1
    assert r.json()['generation']['validation']['status']=='PARTIAL'
    trace=client.get(url+'/generation-status').json()
    assert [e['stage'] for e in trace['events']]==list(range(1,10))
    assert trace['events'][8]['status']=='PENDING'
    assert client.post(url+'/generation-status/'+trace['run_id']+'/displayed').status_code==200
    assert client.get(url+'/generation-status').json()['events'][8]['status']=='PASS'
    assert list((main.DATA/'sources').glob('*.txt'))


def test_append_keeps_existing_ids_and_requires_review(client):
    login(client)
    lesson=client.post('/api/upload',files={'file':('append.txt',b'apple table')}).json()
    settings={'count':1,'kinds':['quiz'],'force_refresh':True}
    from .schemas import Generated
    first=Generated(questions=[fixture_question()])
    with patch('backend.ai.generate',return_value=(first,{})):
        saved=client.post('/api/lessons/'+lesson['id']+'/generate',json=settings).json()
    original=saved['questions'][0]
    with main.db() as c:c.execute('UPDATE calls SET at=at-31')
    q=fixture_question();q['prompt']='Which word is a fruit in this lesson?'
    with patch('backend.ai.generate',return_value=(Generated(questions=[q]),{})):
        response=client.post('/api/lessons/'+lesson['id']+'/generate',json=dict(settings,append=True))
    assert response.status_code==200,response.text
    rows=response.json()['questions']
    assert len(rows)==2 and rows[0]['id']==original['id']
    assert all(not q['approved'] for q in rows)

def test_schema_reason_is_specific_without_input_payload():
    q=fixture_question();q['options']=['table','chair']
    import pytest
    with pytest.raises(ai.GenerationError) as error:
        ai.validate_output(json.dumps({'questions':[q]}),{'sections':[{'number':1,'text':'apple'}]},GenerateRequest(count=1,kinds=['quiz']),Path('.'))
    reason=error.value.diagnostics['rejected'][0]['reason'][0]
    assert 'đáp án nằm trong lựa chọn' in reason['message']
    assert 'input' not in reason
