"""Explicit one-call Gemini integration smoke, preserving teacher review gate."""
import json
from pathlib import Path
import httpx
from phase1 import ROOT, save


def main():
    evidence = {'status':'FAIL', 'actual_gemini_requests':0}
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=65) as c:
        code = (ROOT/'backend/data/teacher-access.txt').read_text(encoding='utf-8').strip()
        r = c.post('/api/login',json={'code':code});r.raise_for_status()
        source=ROOT/'input/Unit 6 Lesson 2 Period 3.pptx'
        with source.open('rb') as stream:
            r=c.post('/api/upload',files={'file':(source.name,stream,'application/vnd.openxmlformats-officedocument.presentationml.presentation')})
        r.raise_for_status();l=r.json()
        evidence.update(lesson_id=l['id'], uploaded_pptx=True, extracted_sections=len(l['document']['sections']), source_sha256=l['document']['sha256'])
        r=c.post('/api/lessons/'+l['id']+'/generate',json={'grade':3,'count':6,'difficulty':'easy','kinds':['vocabulary','quiz','match','listen','fill']})
        evidence['generation_http_status']=r.status_code
        evidence['actual_gemini_requests']=1
        if r.status_code!=200:
            evidence['safe_error']=r.json()
        else:
            l=r.json()
            evidence.update(status='PASS', generation=l['generation'], lesson=l, all_pending_review=all(not q['approved'] for q in l['questions']))
    save('phase2-live.json',evidence)
    print(json.dumps({k:v for k,v in evidence.items() if k!='lesson'},ensure_ascii=True,indent=2))
    return 0 if evidence['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
