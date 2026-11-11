"""Offline release checks without printing a key, hash or credential value."""
import hashlib
import json
from pathlib import Path
from dotenv import dotenv_values
from phase1 import ROOT, extract

cfg = dotenv_values(ROOT/'backend/.env', interpolate=False)
key = cfg.get('GEMINI_API_KEY')
assert key and cfg.get('GEMINI_MODEL')=='gemini-3.5-flash-lite'
files=[]
for p in ROOT.rglob('*'):
    if not p.is_file() or set(p.relative_to(ROOT).parts) & {'.venv','.cache','.git','node_modules','__pycache__','test-results','data','private-backups','private-production-data','deploy'} or p.name=='.env':
        continue
    if p.suffix.lower() in {'.png','.pptx','.pdf','.sqlite3'}:
        continue
    assert key.encode() not in p.read_bytes(), 'Secret found in deliverable'
    files.append(p.relative_to(ROOT).as_posix())
old=json.loads((ROOT/'reports/powerpoint.json').read_text(encoding='utf-8'))[0]
new=extract(ROOT/old['file'],lightweight=True)
assert new['sha256']==old['sha256']
assert new['picture_shape_count']==old['picture_shape_count']
assert new['slide_count']==old['slide_count']
for a,b in zip(new['slides'],old['slides']):
    assert ' '.join(' '.join(a['text']).split())==' '.join(' '.join(b['text']).split())
report={'status':'PASS','files_scanned':len(files),'key_in_deliverables':False,'configured_model':cfg['GEMINI_MODEL'],'pptx_source_unchanged':True,'lightweight_reader_matches_phase1_text_images':True}
(ROOT/'reports/delivery-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
