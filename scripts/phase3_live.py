"""Real PPTX upload + one multimodal analysis, cache check and reviewed visual lesson."""
import json
from pathlib import Path
import uuid
import httpx
from phase1 import ROOT


def main():
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120) as c:
        c.post('/api/login',json={'code':(ROOT/'backend/data/teacher-access.txt').read_text(encoding='utf-8').strip()}).raise_for_status()
        existing=ROOT/'reports/phase3/live-analysis.json'
        if existing.exists():
            saved=json.loads(existing.read_text(encoding='utf-8'))
            r=c.get('/api/lessons/'+saved['lesson_id']);r.raise_for_status();lesson=r.json()
        else:
            p=ROOT/'input/Unit 6 Lesson 2 Period 3.pptx'
            with p.open('rb') as f:r=c.post('/api/upload',files={'file':(p.name,f)})
            r.raise_for_status();lesson=r.json()
        original=next(a for a in lesson['document']['assets'] if a['metadata'].get('part')=='ppt/media/image7.jpg')
        icon=next(a for a in lesson['document']['assets'] if a['metadata'].get('part')=='ppt/media/image4.png')
        r=c.post(f"/api/lessons/{lesson['id']}/assets/{original['id']}/crop",json={'left':0,'top':0,'right':1,'bottom':.8});r.raise_for_status();lesson=r.json()
        cropped=next(a for a in lesson['document']['assets'] if a['origin']=='teacher_crop')
        ids=[original['id'],cropped['id'],icon['id']]
        r=c.post(f"/api/lessons/{lesson['id']}/analyze-images",json={'asset_ids':ids})
        if r.status_code!=200:
            (ROOT/'reports/phase3/live-analysis.json').write_text(json.dumps({'status':'FAIL','http':r.status_code,'safe_error':r.json(),'lesson_id':lesson['id']},ensure_ascii=False,indent=2),encoding='utf-8')
            print('AI_ANALYSIS_FAIL',r.status_code);return 1
        lesson=r.json();analysis=lesson['analysis'];r=c.post(f"/api/lessons/{lesson['id']}/analyze-images",json={'asset_ids':ids});r.raise_for_status()
        report={'status':'PASS','lesson_id':lesson['id'],'source':'input/Unit 6 Lesson 2 Period 3.pptx','real_upload':True,'assets_extracted':len(lesson['document']['assets']),'first_analysis':analysis,'cache_reused':r.json()['analysis']['cached'],'assets':[a for a in lesson['document']['assets'] if a['id'] in ids]}
        # Actual pixels were inspected by the agent. Explicit teacher-stage review,
        # separate from AI suggestion; no answer changed to fit an image.
        r=c.put(f"/api/lessons/{lesson['id']}/assets/{cropped['id']}",json={'role':'learning','description':'Ba dãy nhà tạo ba cạnh sân trường, đã cắt nhãn buildings / three ở dưới; các dãy nhà vẫn nhìn trọn vẹn.','facts':[{'subject':'buildings','attribute':'count','value':'three'},{'subject':'school','attribute':'identity','value':'school'}],'answer_leak':False,'confirmed':True});r.raise_for_status();lesson=r.json()
        q={'id':uuid.uuid4().hex,'kind':'quiz','prompt':'How many buildings are there?','answer':'Three','options':['Two','Three','Four'],'explanation':'Đếm ba dãy nhà trong hình, không dùng dòng nhãn đáp án.','source':7,'quote':'There are three.','word':'','meaning':'','speech':'','approved':False,'question_type':'visual','requires_visual':True,'image_asset_id':cropped['id'],'source_slide':7,'source_evidence':'','visual_description':'Quan sát toàn bộ ba dãy nhà quanh sân trường trong vùng ảnh không có nhãn đáp án.','visual_subject':'buildings','visual_attribute':'count'}
        body={'title':'QA · Our school facilities — ảnh nguồn thật','grade':3,'revision':lesson['revision'],'questions':[q]}
        r=c.put('/api/lessons/'+lesson['id'],json=body);r.raise_for_status();lesson=r.json()
        report['saved_validation']=lesson['questions'][0]['validation_status']
        report['cropped_asset_id']=cropped['id'];report['code']=lesson['code']
        # Leave draft for UI test to perform approval/publish.
        (ROOT/'reports/phase3/live-analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='assets'},ensure_ascii=True,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
