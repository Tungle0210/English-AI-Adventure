"""Prepare a clearly labelled QA lesson from locally authored PPTX fixtures, no AI calls."""
import json
from pathlib import Path
import uuid
import httpx
from phase1 import ROOT


def main():
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120) as c:
        c.post('/api/login',json={'code':(ROOT/'backend/data/teacher-access.txt').read_text(encoding='utf-8').strip()}).raise_for_status()
        p=ROOT/'reports/phase3/fixtures/visual-regression.pptx'
        with p.open('rb') as f:r=c.post('/api/upload',files={'file':(p.name,f)})
        r.raise_for_status();l=r.json()
        assets=[a for a in l['document']['assets'] if a['source']==1 and a['origin'].startswith('picture-')]
        assert len(assets)==3
        for a,subject,attr,value in zip(assets,['school bag','apples','ball'],['color','count','position'],['blue','three','under the table']):
            r=c.put(f"/api/lessons/{l['id']}/assets/{a['id']}",json={'role':'learning','description':f'QA regression illustration: {subject}. Artwork created locally for this test; not the original missing DOCX.','facts':[{'subject':subject,'attribute':attr,'value':value},{'subject':subject,'attribute':'identity','value':subject}],'answer_leak':False,'confirmed':True});r.raise_for_status();l=r.json()
        def q(n,kind,prompt,answer,options,asset,subject,attr,**extras):
            return dict({'id':'qa-visual-'+str(n),'kind':kind,'prompt':prompt,'answer':answer,'options':options,'explanation':'Đối chiếu hình học liệu QA đã được kiểm định.','source':1,'quote':'Visual QA regression fixtures.','word':'','meaning':'','speech':'','image':'','approved':False,'question_type':'visual','requires_visual':True,'image_asset_id':asset['id'],'source_slide':1,'source_evidence':'','visual_description':'Quan sát đúng hình học liệu của câu hỏi, không dựa vào tên file.','visual_subject':subject,'visual_attribute':attr},**extras)
        questions=[
            q(1,'vocabulary','What does school bag mean?','cặp sách',['cặp sách','quyển sách'],assets[0],'school bag','identity',word='school bag',meaning='cặp sách'),
            q(2,'quiz','What color is the school bag?','blue',['blue','pink','orange'],assets[0],'school bag','color'),
            q(3,'quiz','How many apples are there?','Three',['Two','Three','Four'],assets[1],'apples','count'),
            q(4,'quiz','Where is the ball?','Under the table',['Under the table','On the table','Next to the table'],assets[2],'ball','position'),
            q(5,'match','Match: school bag','cặp sách',[],assets[0],'school bag','identity',word='school bag',meaning='cặp sách'),
            q(6,'match','Match: apples','những quả táo',[],assets[1],'apples','identity',word='apples',meaning='những quả táo'),
            q(7,'listen','What color is the school bag?','blue',['blue','pink','orange'],assets[0],'school bag','color',speech='The school bag is blue.'),
            q(8,'fill','The school bag is ___.','blue',[],assets[0],'school bag','color'),
        ]
        # Duplicate wording across kinds is intentional; backend keys include kind.
        r=c.put('/api/lessons/'+l['id'],json={'title':'QA · Hình học liệu — regression only','grade':3,'revision':l['revision'],'questions':questions});r.raise_for_status();l=r.json()
        assert all(q['validation_status']=='valid' for q in l['questions']), [(q['prompt'],q['quality_issues']) for q in l['questions']]
        report={'status':'PASS','lesson_id':l['id'],'code':l['code'],'assets':[a['id'] for a in assets],'questions':len(l['questions']),'fixture_only':True,'source_pptx':str(p.relative_to(ROOT))}
        (ROOT/'reports/phase3/fixture-lesson.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':main()
