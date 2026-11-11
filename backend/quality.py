"""Conservative, shared gate for generation, editing, publishing and gameplay."""
import re
from .media import asset_info

WORDS={'one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9','ten':'10'}
STOP={'the','a','an','is','are','it','there','at','of','in','on','to','what','which','how','many','color','colour','shape','does','do','look','picture','image','shown','this','that','its','with','where','s'}


def norm(value):
    return ' '.join(WORDS.get(t,t) for t in re.findall(r"[\w]+",value.casefold()))


def tokens(value):
    return {t.rstrip('s') if len(t)>3 else t for t in norm(value).split() if t not in STOP}


def attribute(prompt):
    p=prompt.casefold()
    if re.search(r'colou?r|màu',p):return 'color'
    if re.search(r'how many|đếm|bao nhiêu',p):return 'count'
    if re.search(r'shape|hình dạng',p):return 'shape'
    if re.search(r'where (?:is|are)|position|vị trí|next to|under|above|below',p):return 'position'
    if re.search(r'doing|action|hành động',p):return 'action'
    if re.search(r'look at|in the (?:picture|image)|shown|see in|nhìn|trong ảnh',p):return 'appearance'
    return ''


def evidence_valid(q, document):
    text=next((s['text'] for s in document.get('sections',[]) if s['number']==q.get('source')), '')
    evidence=q.get('source_evidence','')
    passages=[text]+[a.get('transcript','') for a in document.get('assets',[]) if a.get('source')==q.get('source') and a.get('reviewed') and a.get('transcript_confirmed') and a.get('document_hash')==document.get('sha256')]
    return bool(evidence and any(' '.join(evidence.split()) in ' '.join(p.split()) for p in passages) and tokens(q['answer']) <= tokens(evidence))


def assess(q, document, root):
    data=dict(q); issues=[]
    inferred=attribute(q['prompt'])
    supplied=q.get('question_type','language')
    speech_proof=q.get('kind')=='listen' and bool(tokens(q.get('answer',''))) and tokens(q['answer'])<=tokens(q.get('speech',''))
    reading_proof=supplied=='reading' and evidence_valid(q,document)
    reading_cue=bool(re.search(r'in the text|mentioned|according to|passage|being asked|whose school',q['prompt'],re.I)) and not speech_proof
    need=bool(q.get('requires_visual') or supplied=='visual' or (inferred and not reading_proof and not speech_proof))
    if supplied=='reading' and not reading_proof:issues.append('Đoạn đọc chưa đủ bằng chứng cho đáp án hoặc không khớp nguồn.')
    if reading_cue and not reading_proof:issues.append('Câu đọc hiểu chưa có đoạn nguồn hiển thị cho học sinh.')
    if q.get('kind')=='listen' and not speech_proof and not need:issues.append('Nội dung nghe chưa có dữ kiện đáp án.')
    source_text=next((s['text'] for s in document.get('sections',[]) if s['number']==q['source']),'')
    if re.search(r'\btrue\b.*\bfalse\b',source_text,re.I|re.S) and (inferred or supplied=='reading'):
        if not any(a.get('source')==q['source'] and a.get('reviewed') and a.get('transcript_confirmed') for a in document.get('assets',[])):
            issues.append('Nguồn có bài Đúng/Sai; cần kiểm định đoạn đọc gốc, không lấy mệnh đề của bài tập làm đáp án.')
    # A true/false statement or distractor is not an asserted source fact. A
    # teacher-confirmed source passage can expose a conflict even in listening.
    if inferred:
        for a in document.get('assets',[]):
            if a.get('source')!=q['source'] or not a.get('reviewed') or not a.get('transcript_confirmed'):continue
            for fact in a.get('facts',[]):
                subject=tokens(fact.get('subject',''))
                if fact.get('basis')=='source_text' and fact.get('attribute')==inferred and subject and subject<=tokens(q['prompt']):
                    expected=tokens(fact.get('value',''));actual=tokens(q['answer'])
                    if expected and actual not in (expected,expected|subject):issues.append('Đáp án mâu thuẫn đoạn đọc gốc đã kiểm định; không coi mệnh đề Đúng/Sai là sự thật.')
    ident=q.get('image_asset_id','')
    asset=asset_info(root,ident) if ident else None
    available={a['id']:a for a in document.get('assets',[])}
    if ident and (not asset or ident not in available):issues.append('Ảnh không tồn tại hoặc không thuộc tài liệu này.')
    if asset and (asset['source']!=q['source'] or asset['document_hash']!=document.get('sha256')):issues.append('Ảnh không thuộc đúng slide/trang nguồn.')
    if asset and not need:
        if not asset.get('reviewed') or asset.get('role')!='learning' or asset.get('answer_leak',True):issues.append('Ảnh minh họa chưa được duyệt hoặc có thể làm lộ đáp án.')
        identity=any(f.get('attribute')=='identity' and f.get('basis','pixels')=='pixels' and tokens(f.get('subject','')) and tokens(f['subject'])<=tokens(q['prompt']+' '+q.get('word','')) for f in asset.get('facts',[]))
        if not identity:issues.append('Ảnh minh họa không chứng minh đúng vật thể trong câu đọc/nghe.')
    if need:
        if not ident:issues.append('Câu cần quan sát nhưng chưa có ảnh nguồn.')
        if asset:
            if not asset.get('reviewed') or asset.get('role')!='learning':issues.append('Ảnh chưa được giáo viên xác nhận là học liệu.')
            if asset.get('answer_leak',True):issues.append('Ảnh có thể lộ đáp án; chọn vùng ảnh khác và kiểm tra lại.')
            if not q.get('visual_description'):issues.append('Thiếu mô tả dữ kiện quan sát.')
            attr=inferred or q.get('visual_attribute') or 'identity'
            if attr in ('count','position') and (asset.get('metadata',{}).get('grouped') or asset.get('metadata',{}).get('placement_uncertain')):
                issues.append('Ảnh tách khỏi nhóm/ngữ cảnh chưa đủ cho đếm hoặc vị trí; chọn bản render hoặc vùng ảnh có toàn bộ quan hệ.')
            if q.get('visual_attribute') and inferred and q['visual_attribute']!=inferred:issues.append('Thuộc tính quan sát không khớp câu hỏi.')
            facts=asset.get('facts',[])
            target=q.get('word') if attr=='identity' else q.get('answer','')
            proof=False
            for fact in facts:
                if fact.get('basis','pixels')!='pixels':continue
                subject=tokens(fact.get('subject',''))
                if fact.get('attribute')==attr and subject and subject<=tokens(q['prompt']+' '+q.get('word','')):
                    # Whole normalized tokens, never substring matching blue/bluebird.
                    expected=tokens(fact.get('value',''))
                    actual=tokens(target)
                    if expected and actual and (expected==actual or (attr!='identity' and expected==actual-subject)):
                        if not q.get('visual_subject') or tokens(q['visual_subject'])==subject:proof=True
            if not proof:issues.append('Ảnh chưa có bằng chứng đúng vật thể/thuộc tính/đáp án của câu này.')
    if q.get('source_slide') not in (None,q['source']):issues.append('Slide nguồn không khớp.')
    data.update(requires_visual=need,source_slide=q['source'],validation_status='blocked' if issues else 'valid',quality_issues=issues)
    if need:data['question_type']='visual'
    data['media_url']=asset['url'] if asset and not issues else ''
    return data


def persisted(q):
    return {k:v for k,v in q.items() if k not in ('quality_issues','media_url')}


def refresh_lesson(lesson, root):
    lesson['document']['assets']=[asset_info(root,a['id']) or a for a in lesson['document'].get('assets',[])]
    lesson['questions']=[assess(q,lesson['document'],root) for q in lesson['questions']]
    return lesson


def eligible(lesson,root):
    return [q for q in refresh_lesson(lesson,root)['questions'] if not q.get('hidden') and q['validation_status']=='valid' and q.get('approved')]
