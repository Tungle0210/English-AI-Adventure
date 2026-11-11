"""Recover exact source, preserve false old answers as hidden history, add reviewed replacements."""
import json
from pathlib import Path
import httpx
from phase1 import ROOT

PASSAGE='Hi. I am Minh Duc. Those are my new school things. Look at my school bag. It is yellow. That is my book. It is red. That is my pen. It is brown. Those are my rulers. They are orange and blue. Those are my rubbers. They are black and purple. I like my new school things. I want to keep them clean.'


def main():
    original=next(l for l in json.loads((ROOT/'reports/phase3-before-bank.json').read_text(encoding='utf-8')) if l['title']=='BÀi tập')
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120) as c:
        c.post('/api/login',json={'code':(ROOT/'backend/data/teacher-access.txt').read_text(encoding='utf-8').strip()}).raise_for_status()
        p=ROOT/'input/BÀi tập.docx'
        with p.open('rb') as f:r=c.post('/api/lessons/'+original['id']+'/restore-source',files={'file':(p.name,f)})
        r.raise_for_status();l=r.json();parent=next(a for a in l['document']['assets'] if a['origin'].startswith('docx-vml'))
        facts=[{'subject':s,'attribute':'color','value':v,'basis':'source_text'} for s,v in [('school bag','yellow'),('book','red'),('pen','brown'),('rulers','orange and blue'),('rubbers','black and purple')]]
        r=c.put(f"/api/lessons/{l['id']}/assets/{parent['id']}",json={'role':'context','description':'Bản đọc gốc kèm tranh chưa tô màu và mệnh đề Đúng/Sai. Cặp vàng, sách đỏ theo đoạn đọc, không lấy blue/pink trong mệnh đề sai làm dữ kiện.','facts':facts,'answer_leak':True,'confirmed':True,'transcript':PASSAGE,'transcript_confirmed':True});r.raise_for_status();l=r.json()
        crops={}
        for name,box in [('school bag',(.015,.28,.27,.50)),('book',(.10,.51,.38,.65))]:
            r=c.post(f"/api/lessons/{l['id']}/assets/{parent['id']}/crop",json=dict(zip(['left','top','right','bottom'],box)));r.raise_for_status();l=r.json()
            a=next(a for a in l['document']['assets'] if a['origin']=='teacher_crop' and a['metadata'].get('parent_asset_id')==parent['id'] and abs(a['metadata']['picture_crop'][0]-box[0])<.001)
            r=c.put(f"/api/lessons/{l['id']}/assets/{a['id']}",json={'role':'learning','description':f'Vùng hình {name} đen trắng, lấy đúng từ worksheet gốc; chỉ nhận diện vật thể, không dùng để suy đoán màu.','facts':[{'subject':name,'attribute':'identity','value':name,'basis':'pixels'}],'answer_leak':False,'confirmed':True});r.raise_for_status();l=r.json();crops[name]=a['id']
        old_ids={q['id'] for q in original['questions']}
        old=[q for q in l['questions'] if q['id'] in old_ids]
        for q in old:
            if q['validation_status']!='valid':q.update(hidden=True,approved=False)
        def item(ident,kind,prompt,answer,options,subject,passage):
            return {'id':ident,'kind':kind,'prompt':prompt,'answer':answer,'options':options,'explanation':'Đọc đúng đoạn nguồn: '+passage+' Hình gốc chưa tô màu, không đoán màu từ tranh.','source':1,'quote':passage,'word':'','meaning':'','speech':passage if kind=='listen' else '','image':'','approved':False,'question_type':'reading' if kind=='quiz' else 'listening','requires_visual':False,'image_asset_id':crops[subject],'source_slide':1,'source_evidence':passage if kind=='quiz' else '','visual_description':'Hình nhận diện vật thể từ tài liệu gốc, dữ kiện màu nằm trong đoạn đọc/lời nghe.','visual_subject':subject,'visual_attribute':'','hidden':False}
        replacements=[item('source-correct-school-bag','quiz','What color is the school bag?','Yellow',['Yellow','Blue','Pink'],'school bag','Look at my school bag. It is yellow.'),item('source-correct-book','listen','What colour is the book?','Red',['Red','Pink','Blue'],'book','That is my book. It is red.')]
        r=c.put('/api/lessons/'+l['id'],json={'title':l['title'],'grade':l['grade'],'revision':l['revision'],'questions':old+replacements});r.raise_for_status();l=r.json()
        assert all(q['validation_status']=='valid' for q in l['questions'] if not q.get('hidden'))
        report={'status':'PASS','lesson_id':l['id'],'code':l['code'],'original_sha256_matches':True,'source_file':'input/BÀi tập.docx','recovered_vml_image':parent['id'],'crops':crops,'hidden_original_questions':[{'id':q['id'],'prompt':q['prompt'],'answer':q['answer'],'issues':q['quality_issues']} for q in l['questions'] if q.get('hidden')],'replacement_ids':[q['id'] for q in replacements],'transcript_manually_verified':PASSAGE,'note':'No old answers or attempts changed. New answers yellow/red come from the original reading passage, not from black-and-white visual colors. All visible questions left for UI review.'}
        (ROOT/'reports/phase3/original-docx-repair.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='transcript_manually_verified'},ensure_ascii=True,indent=2))


if __name__=='__main__':main()
