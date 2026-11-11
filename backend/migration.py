"""Idempotent bank audit. Never edits attempt snapshots, results or answers."""
import json
from pathlib import Path
import sqlite3
from .content import ROOT, read_document
from .schemas import Item
from . import quality


def audit_legacy(root, database):
    report={'version':3,'questions_checked':0,'legacy_questions_checked':0,'missing_context_before':0,'missing_image_before':0,'repaired_with_reading_evidence':0,'repaired_with_source_image':0,'hidden':0,'details':[]}
    with sqlite3.connect(database) as c:
        c.row_factory=sqlite3.Row
        rows=c.execute('SELECT * FROM lessons').fetchall()
        for row in rows:
            doc=json.loads(row['document']);questions=json.loads(row['questions']);report['questions_checked']+=len(questions)
            if doc.get('quality_schema')==3 and doc.get('reading_gate')==1:continue
            source=None
            for path in (ROOT/'input').iterdir():
                if path.is_file() and (path.name==doc.get('filename') or (not doc.get('filename') and path.name=='Unit 6 Lesson 2 Period 3.pptx')):
                    from .media import digest_file
                    if not doc.get('sha256') or digest_file(path)==doc['sha256']:source=path;break
            if source:
                import os
                if os.environ.get('ADVENTURE_AUDIT_IMAGES','1')=='0':
                    from .media import digest_file
                    new={'assets':[],'sha256':digest_file(source),'source_retained':True}
                else:new=read_document(source,media_root=root)
                # Do not silently replace edited source text. Restore pixels only.
                for k in ['assets','sha256','source_retained']:doc[k]=new[k]
                for section in doc['sections']:
                    section['asset_ids']=[a['id'] for a in new['assets'] if a['source']==section['number']]
            else:
                doc.setdefault('assets',[]);doc['source_retained']=False
                doc.setdefault('warnings',[]).append('Tài liệu gốc đã bị xóa ở pipeline cũ. Cần tải lại để xác minh ảnh; không tự gán ảnh ngoài.')
            updated=[]
            for q in questions:
                report['legacy_questions_checked']+=1
                before=quality.assess(q,doc,root)
                missing=before['requires_visual'] and before['validation_status']!='valid'
                if missing:
                    report['missing_context_before']+=1
                    report['missing_image_before']+=not bool(q.get('image_asset_id'))
                if source and (missing or any('đọc hiểu' in x for x in before['quality_issues'])):
                    section=next((s['text'] for s in doc['sections'] if s['number']==q['source']),'')
                    for passage in [q.get('quote',''),section[:1800]]:
                        probe=dict(q,question_type='reading',requires_visual=False,source_evidence=passage)
                        if quality.evidence_valid(probe,doc):
                            q=probe;report['repaired_with_reading_evidence']+=1;break
                checked=quality.assess(q,doc,root)
                if checked['validation_status']!='valid':
                    checked.update(hidden=True,approved=False);report['hidden']+=1
                # Normalize new defaults without changing IDs, answers or legacy score data.
                raw=quality.persisted(checked)
                normalized=Item.model_validate({k:v for k,v in raw.items() if k not in ('id','approved')}).model_dump()
                normalized.update(id=q['id'],approved=raw.get('approved',False))
                updated.append(normalized)
                report['details'].append({'lesson_id':row['id'],'question_id':q['id'],'prompt':q['prompt'],'before_missing_visual_context':missing,'after':normalized['validation_status'],'hidden':normalized['hidden'],'repair':'reading_evidence' if normalized['question_type']=='reading' else 'none','issues':checked['quality_issues']})
            doc['quality_schema']=3;doc['reading_gate']=1
            c.execute('UPDATE lessons SET document=?,questions=?,revision=revision+1 WHERE id=?',(json.dumps(doc,ensure_ascii=False),json.dumps(updated,ensure_ascii=False),row['id']))
    folder=root/'qa';folder.mkdir(exist_ok=True,parents=True)
    # Preserve the first migration report, rather than replacing findings with 0 on restart.
    if not (folder/'migration-v3.json').exists():(folder/'migration-v3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
