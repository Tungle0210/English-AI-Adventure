import copy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from . import main,media,quality
from .test_app import client,login,save

FIX=main.ROOT/'reports/phase3/fixtures'


def upload_visual(c):
    login(c)
    p=FIX/'visual-regression.pptx'
    r=c.post('/api/upload',files={'file':(p.name,p.read_bytes())});assert r.status_code==200,r.text
    lesson=r.json()
    source=[a for a in lesson['document']['assets'] if a['source']==1]
    assert len(source)==3
    facts=[('school bag','color','blue'),('apples','count','three'),('ball','position','under the table')]
    for asset,(subject,attr,value) in zip(source,facts):
        r=c.put(f"/api/lessons/{lesson['id']}/assets/{asset['id']}",json={'role':'learning','description':f'QA fixture showing {subject}. Manually checked against actual pixels.','facts':[{'subject':subject,'attribute':attr,'value':value},{'subject':subject,'attribute':'identity','value':subject}],'answer_leak':False,'confirmed':True})
        assert r.status_code==200,r.text;lesson=r.json()
    return lesson,source


def question(asset,**patches):
    q={'id':'visual-q','kind':'quiz','prompt':'What color is the school bag?','answer':'blue','options':['blue','pink','orange'],'explanation':'Hình chiếc cặp có màu xanh dương.','source':1,'quote':'Visual QA regression fixtures.','word':'','meaning':'','speech':'','image':'','approved':False,'question_type':'visual','requires_visual':True,'image_asset_id':asset['id'],'source_evidence':'','visual_description':'Quan sát chiếc cặp trong hình học liệu.','visual_subject':'school bag','visual_attribute':'color'}
    return dict(q,**patches)


def publish(c,l):
    for q in l['questions']:q['approved']=True
    l=save(c,l).json()
    r=c.post('/api/lessons/'+l['id']+'/publish');assert r.status_code==200,r.text
    return r.json()


def test_multiple_images_wrong_object_and_bad_id_blocked(client):
    l,a=upload_visual(client)
    for ident in [a[1]['id'],'f'*64]:
        l['questions']=[question(a[0],image_asset_id=ident,approved=True)]
        r=save(client,l);assert r.status_code==200;l=r.json()
        assert l['questions'][0]['validation_status']=='blocked'
        assert not l['questions'][0]['approved']
        assert client.post('/api/lessons/'+l['id']+'/publish').status_code==422
    l['questions']=[question(a[0])];l=save(client,l).json();assert l['questions'][0]['validation_status']=='valid'


@pytest.mark.parametrize('kind',['quiz','vocabulary','match','listen','fill'])
def test_image_visible_and_missing_asset_safe_skip_all_kinds(client,kind):
    l,a=upload_visual(client);q=question(a[0],kind=kind)
    if kind in ('vocabulary','match'):q.update(prompt='Match the word school bag to its meaning.',word='school bag',meaning='cặp sách',answer='cặp sách',visual_attribute='identity',options=['cặp sách','quyển sách'] if kind=='vocabulary' else [])
    if kind=='listen':q['speech']='The school bag is blue.'
    if kind=='fill':q.update(prompt='The school bag is ___.',options=[])
    l['questions']=[q]
    if kind=='match':l['questions'].append(question(a[1],id='match-apple',kind='match',prompt='Match apples to the meaning.',word='apples',meaning='những quả táo',answer='những quả táo',options=[],visual_subject='apples',visual_attribute='identity'))
    l=save(client,l).json();l=publish(client,l)
    started=client.post('/api/play/'+l['code']+'/start',json={'mode':kind}).json();q=started['questions'][0]
    assert q['requires_visual'] and q['media_url']
    assert client.get(q['media_url']).headers['content-type'].startswith('image/png')
    path=main.DATA/'media'/(a[0]['id']+'.png');path.unlink()
    assert client.post('/api/attempts/'+started['id']+'/answer',json={'question_id':q['id'],'answer':'blue'}).status_code==409
    r=client.post('/api/attempts/'+started['id']+'/skip',json={'question_id':q['id']})
    assert r.status_code==200
    result=r.json()['result'];assert result['skipped']==1 and (result['score'] is None if kind!='match' else result['graded_total']==1)
    if kind=='match':
        r=client.post('/api/attempts/'+started['id']+'/answer',json={'question_id':'match-apple','answer':'những quả táo'})
        assert r.json()['result']['score']==100


def test_leaking_answer_decorative_and_cross_slide_rejected(client):
    l,a=upload_visual(client)
    for flags in [{'answer_leak':True,'role':'learning'},{'answer_leak':False,'role':'icon'},{'answer_leak':False,'role':'background'}]:
        r=client.put(f"/api/lessons/{l['id']}/assets/{a[0]['id']}",json={**flags,'description':'QA actual picture, reviewed for negative test.','facts':[{'subject':'school bag','attribute':'color','value':'blue'}],'confirmed':True});l=r.json()
        l['questions']=[question(a[0])];l=save(client,l).json();assert l['questions'][0]['validation_status']=='blocked'
    l['questions']=[question(a[0],source=2,source_slide=2)];l=save(client,l).json();assert l['questions'][0]['validation_status']=='blocked'


def test_text_question_shows_proof_without_image(client):
    login(client);l=client.post('/api/upload',files={'file':('read.txt',b'The school bag is blue.')}).json()
    q=question({'id':''},question_type='reading',requires_visual=False,source_evidence='The school bag is blue.',quote='The school bag is blue.')
    l['questions']=[q];l=save(client,l).json();assert l['questions'][0]['validation_status']=='valid' and not l['questions'][0]['requires_visual']
    l=publish(client,l)
    with patch.object(main.ai,'generate',side_effect=RuntimeError('MISSING_KEY')) as mock:
        a=client.post('/api/play/'+l['code']+'/start',json={'mode':'quiz'}).json()
        assert a['questions'][0]['source_evidence']=='The school bag is blue.'
        assert not a['questions'][0]['requires_visual'];mock.assert_not_called()


def test_false_flag_cannot_bypass_visual_gate(client):
    l,a=upload_visual(client)
    l['questions']=[question(a[0],requires_visual=False,question_type='language',image_asset_id='')]
    l=save(client,l).json();assert l['questions'][0]['requires_visual'] and l['questions'][0]['validation_status']=='blocked'


def test_crop_group_provenance_and_immutable_pixels(client):
    l,a=upload_visual(client)
    grouped=[a for a in l['document']['assets'] if a['source']==2]
    assert grouped and grouped[0]['metadata']['grouped'] and grouped[0]['metadata']['picture_crop'][0]==.1
    r=client.post(f"/api/lessons/{l['id']}/assets/{a[0]['id']}/crop",json={'left':0,'top':0,'right':1,'bottom':.8});assert r.status_code==200
    derived=next(a for a in r.json()['document']['assets'] if a['origin']=='teacher_crop')
    assert derived['metadata']['parent_asset_id']==a[0]['id'] and not derived['reviewed']
    path=main.DATA/'media'/(derived['id']+'.png');path.write_bytes(b'changed')
    assert client.get(derived['url']).status_code==404


def test_docx_pdf_image_mapping(client):
    login(client)
    for name in ['visual-regression.docx','visual-regression.pdf']:
        p=FIX/name;r=client.post('/api/upload',files={'file':(name,p.read_bytes())});assert r.status_code==200,r.text
        d=r.json()['document'];assert d['assets'] and all(a['source']==1 for a in d['assets'])
        assert all(client.get(a['url']).status_code==200 for a in d['assets'])


def test_actual_input_pptx_images_have_occurrence_sources(client):
    login(client);p=main.ROOT/'input/Unit 6 Lesson 2 Period 3.pptx'
    with p.open('rb') as f:r=client.post('/api/upload',files={'file':(p.name,f)})
    assert r.status_code==200,r.text
    d=r.json()['document'];assert len(d['sections'])==10 and len(d['assets'])==18
    assert next(a for a in d['assets'] if a['metadata']['part']=='ppt/media/image7.jpg')['source']==7
    assert next(a for a in d['assets'] if a['metadata']['part']=='ppt/media/image4.png')['source']==3
    assert (main.DATA/'sources'/(d['sha256']+'.pptx')).exists()


def test_regenerate_preserves_old_question_and_requires_review(client):
    from .schemas import Generated
    login(client);l=client.post('/api/upload',files={'file':('read.txt',b'The school bag is blue.')}).json()
    q=question({'id':''},question_type='reading',requires_visual=False,source_evidence='The school bag is blue.',quote='The school bag is blue.')
    l['questions']=[q];l=save(client,l).json()
    new={k:v for k,v in q.items() if k not in ('id','approved')};new['prompt']='Which color is the school bag?'
    with patch.object(main.ai,'generate',return_value=(Generated(questions=[new]),{})) as mocked:
        r=client.post(f"/api/lessons/{l['id']}/questions/visual-q/regenerate")
        assert r.status_code==200,r.text
        questions=r.json()['questions'];assert questions[0]['hidden'] and not questions[1]['approved'];assert mocked.call_count==1


def test_restore_source_requires_same_hash_and_keeps_answers(client):
    l,a=upload_visual(client)
    l['questions']=[question(a[0])];l=save(client,l).json();answer=l['questions'][0]['answer']
    wrong=client.post('/api/lessons/'+l['id']+'/restore-source',files={'file':('other.txt',b'other source')})
    assert wrong.status_code==422
    p=FIX/'visual-regression.pptx'
    with p.open('rb') as f:r=client.post('/api/lessons/'+l['id']+'/restore-source',files={'file':(p.name,f)})
    assert r.status_code==200,r.text
    q=r.json()['questions'][0]
    assert q['answer']==answer and not q['approved']
    assert r.json()['document']['source_retained']


def test_answer_with_extra_unproved_color_is_rejected(client):
    l,a=upload_visual(client)
    l['questions']=[question(a[0],answer='blue and pink',options=['blue and pink','orange'])]
    l=save(client,l).json();assert l['questions'][0]['validation_status']=='blocked'


def test_visual_generation_without_verified_images_stops_before_network(client):
    from .ai import generate
    from .schemas import GenerateRequest
    with patch('backend.ai.genai.Client') as mocked:
        with pytest.raises(ValueError):generate({'sections':[],'assets':[]},GenerateRequest(count=1,kinds=['quiz'],evidence_mode='visual'),media_root=main.DATA)
        mocked.assert_not_called()


def test_corrupt_cached_or_mocked_ai_cannot_insert_unsupported_question(client):
    from .schemas import Generated
    login(client);l=client.post('/api/upload',files={'file':('school.txt',b'The school bag is blue.')}).json()
    bad=question({'id':''},requires_visual=False,question_type='language')
    data={k:v for k,v in bad.items() if k not in ('id','approved')}
    with patch.object(main.ai,'generate',return_value=(Generated(questions=[data]),{})):
        r=client.post('/api/lessons/'+l['id']+'/generate',json={'count':1,'kinds':['quiz']})
        assert r.status_code==422
    assert not client.get('/api/lessons/'+l['id']).json()['questions']


def test_derived_crop_survives_reextracting_identical_source(client):
    l,a=upload_visual(client)
    r=client.post(f"/api/lessons/{l['id']}/assets/{a[0]['id']}/crop",json={'left':0,'top':0,'right':1,'bottom':.8})
    derived=next(a for a in r.json()['document']['assets'] if a['origin']=='teacher_crop')
    p=FIX/'visual-regression.pptx'
    with p.open('rb') as f:again=client.post('/api/upload',files={'file':(p.name,f)})
    assert again.status_code==200
    assert derived['id'] in [a['id'] for a in again.json()['document']['assets']]


def test_actual_original_docx_vml_and_false_statement_conflicts(client):
    login(client);p=main.ROOT/'input/BÀi tập.docx'
    with p.open('rb') as f:r=client.post('/api/upload',files={'file':(p.name,f)})
    assert r.status_code==200,r.text;l=r.json()
    assert len(l['document']['assets'])==1 and l['document']['assets'][0]['origin'].startswith('docx-vml')
    a=l['document']['assets'][0]
    r=client.put(f"/api/lessons/{l['id']}/assets/{a['id']}",json={'role':'context','description':'Đoạn đọc gốc: cặp vàng, sách đỏ; dưới đó là mệnh đề sai blue/pink.','facts':[{'subject':'school bag','attribute':'color','value':'yellow','basis':'source_text'},{'subject':'book','attribute':'color','value':'red','basis':'source_text'}],'answer_leak':True,'confirmed':True,'transcript':'Look at my school bag. It is yellow. That is my book. It is red.','transcript_confirmed':True});assert r.status_code==200;l=r.json()
    q=question({'id':''},requires_visual=False,question_type='reading',source_evidence='The school bag is blue.',quote='The school bag is blue.')
    l['questions']=[q];l=save(client,l).json();assert l['questions'][0]['validation_status']=='blocked'
    assert any('mâu thuẫn' in x for x in l['questions'][0]['quality_issues'])
    q.update(answer='Yellow',options=['Yellow','Blue'],source_evidence='Look at my school bag. It is yellow.',quote='Look at my school bag. It is yellow.')
    l['questions']=[q];l=save(client,l).json();assert l['questions'][0]['validation_status']=='valid'


def test_text_fact_cannot_claim_uncoloured_image_proves_color(client):
    l,a=upload_visual(client)
    # Teacher text annotation alone must not qualify as pixel evidence.
    r=client.put(f"/api/lessons/{l['id']}/assets/{a[0]['id']}",json={'role':'learning','description':'Teacher text statement, not an observation of pixels.','facts':[{'subject':'school bag','attribute':'color','value':'blue','basis':'source_text'}],'answer_leak':False,'confirmed':True});l=r.json()
    l['questions']=[question(a[0])];l=save(client,l).json();assert l['questions'][0]['validation_status']=='blocked'
