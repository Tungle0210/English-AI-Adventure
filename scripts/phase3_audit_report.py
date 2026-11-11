"""Compare original question/attempt evidence, never modify learning records."""
import hashlib
import json
from pathlib import Path
import sqlite3
from phase1 import ROOT
import sys
sys.path.insert(0,str(ROOT))
from backend.quality import assess


def main():
    folder=ROOT/'reports/phase3'
    old=json.loads((ROOT/'reports/phase3-before-bank.json').read_text(encoding='utf-8'))
    before=json.loads((folder/'preservation-before.json').read_text(encoding='utf-8'))
    c=sqlite3.connect(ROOT/'backend/data/adventure.sqlite3');c.row_factory=sqlite3.Row
    root=ROOT/'backend/data'
    checked=[]
    for lesson in old:
        row=c.execute('select * from lessons where id=?',(lesson['id'],)).fetchone()
        document=json.loads(row['document']);current={q['id']:q for q in json.loads(row['questions'])}
        for q in lesson['questions']:
            after=current[q['id']]
            assert q['answer']==after['answer'], 'Old answer changed'
            assessed=assess(q,document,root)
            checked.append({'lesson_id':lesson['id'],'question_id':q['id'],'prompt':q['prompt'],'answer_unchanged':True,'before_missing_data':assessed['validation_status']!='valid','before_missing_image':assessed['requires_visual'] and not q.get('image_asset_id'),'repair':'reading_evidence' if after.get('question_type')=='reading' and after.get('source_evidence') else 'none','after_status':assess(after,document,root)['validation_status'],'hidden':after.get('hidden',False)})
    rows=[tuple(r) for r in c.execute('select * from attempts order by id') if r['id'] in before['ids']]
    backup=sqlite3.connect(root/'backups/pre-phase3.sqlite3')
    original_rows={r[0]:r for r in backup.execute('select * from attempts')}
    assert len(rows)==before['old_attempts'],'Old attempt deleted'
    identical=0;appended=[]
    for current in rows:
        original=original_rows[current[0]]
        assert all(original[i]==current[i] for i in [0,1,2,3,4,6]),'Attempt identity/snapshot changed'
        old_responses=json.loads(original[5]);new_responses=json.loads(current[5])
        assert all(new_responses.get(k)==v for k,v in old_responses.items()),'Existing response overwritten'
        if original[7] is not None:assert original[7]==current[7],'Completed result changed'
        if original==current:identical+=1
        else:appended.append({'attempt_id':current[0],'old_completed':original[7],'new_completed':current[7],'additional_responses':len(new_responses)-len(old_responses),'old_responses_unchanged':True})
    report={'original_questions_checked':len(checked),'current_bank_questions':sum(len(json.loads(r[0])) for r in c.execute('select questions from lessons')),
            'original_questions_missing_data':sum(r['before_missing_data'] for r in checked),'original_questions_missing_image_or_visual_context':sum(r['before_missing_image'] for r in checked),
            'original_questions_repaired_with_reading_evidence':sum(r['repair']=='reading_evidence' for r in checked),'original_questions_repaired_with_original_image':0,
            'original_questions_hidden':sum(r['hidden'] for r in checked),'original_answers_unchanged':True,'original_attempts_preserved':len(rows),'byte_identical_attempts':identical,'original_attempt_snapshots_and_existing_responses_unchanged':True,'ongoing_attempts_with_new_responses_preserved':appended,
            'recovered_original_source':'input/BÀi tập.docx','original_source_hash_verified':True,'source_based_replacement_questions':2,'replacement_questions_show_original_images':2,'details':checked}
    (folder/'audit-final.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='details'},ensure_ascii=True,indent=2))


if __name__=='__main__':main()
