import os,json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend import main
from docx import Document
out=main.ROOT/'reports/phase4';out.mkdir(exist_ok=True)
fixtures=out/'fixtures';fixtures.mkdir(exist_ok=True)
text='Our school has a library and three classrooms. The library has books. We read books in the library. Apple means quả táo. A book means quyển sách.'
(fixtures/'simple.txt').write_text(text,encoding='utf-8')
d=Document();d.add_heading('Our school',0);d.add_paragraph(text);d.save(fixtures/'simple.docx')
production=main.DATA
all_results=[]
for group in ('production','isolated'):
    if group=='isolated':
        main.DATA=production/'qa/phase4-live';main.DB=main.DATA/'adventure.sqlite3'
        os.environ['ADVENTURE_RENDER_PPTX']='0';os.environ['ADVENTURE_AUDIT_IMAGES']='0'
    paths=[main.ROOT/'input/Unit 6 Lesson 2 Period 3.pptx',next((main.ROOT/'input').glob('de-thi-hoc-ki-1*.pdf'))] if group=='production' else [fixtures/'simple.docx',fixtures/'simple.txt']
    with TestClient(main.app) as c:
        c.post('/api/login',json={'code':(main.DATA/'teacher-access.txt').read_text().strip()})
        for path in paths:
            result={'file':path.name,'group':group,'bytes':path.stat().st_size,'cache':False}
            start=time.perf_counter()
            with path.open('rb') as f:r=c.post('/api/upload',files={'file':('QA phase4 '+path.name,f)})
            result['upload_http']=r.status_code;result['upload_ms']=round((time.perf_counter()-start)*1000,2)
            if r.status_code!=200:result['status']='FAIL';all_results.append(result);continue
            l=r.json();result.update(lesson_id=l['id'],sections=len(l['document']['sections']),assets=len(l['document'].get('assets',[])),characters=sum(len(s['text']) for s in l['document']['sections']))
            settings={'count':6,'force_refresh':True} if group=='production' else {'count':2,'kinds':['quiz','fill'],'force_refresh':True}
            r=c.post('/api/lessons/'+l['id']+'/generate',json=settings)
            result['generation_http']=r.status_code
            if r.status_code==200:
                data=r.json();result['generation']=data['generation'];result['question_count']=len(data['questions']);result['status']='PASS' if data['generation'].get('validation',{}).get('status')=='PASS' else 'PARTIAL'
                (out/('lesson-'+path.suffix[1:]+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            else:result['status']='FAIL';result['error']=r.json()
            result['trace']=c.get('/api/lessons/'+l['id']+'/generation-status').json();result['total_ms']=round((time.perf_counter()-start)*1000,2)
            all_results.append(result)
            (out/'live-files.json').write_text(json.dumps(all_results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:result[k] for k in ('file','status','generation_http','lesson_id')},ensure_ascii=True),flush=True)
