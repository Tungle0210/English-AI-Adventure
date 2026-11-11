"""Bounded document extraction, reusing the phase-1 PPTX reader."""
from pathlib import Path
import sys
from zipfile import ZipFile, BadZipFile
from pypdf import PdfReader
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from phase1 import extract

MAX_BYTES = 100 * 1024 * 1024
MAX_TEXT = 60000
EXTENSIONS = {'.pptx', '.pdf', '.docx', '.txt'}


def read_document(path: Path, media_root=None, render=True):
    suffix = path.suffix.lower()
    if suffix not in EXTENSIONS or path.stat().st_size > MAX_BYTES:
        raise ValueError('Chỉ nhận PPTX/PDF/DOCX/TXT tối đa 100 MB.')
    if suffix in {'.pptx', '.docx'}:
        with ZipFile(path) as archive:
            items = archive.infolist()
            if len(items) > 3000 or sum(i.file_size for i in items) > 250 * 1024 * 1024:
                raise ValueError('Tài liệu giải nén quá lớn.')
            if any(i.file_size > 5*1024*1024 for i in items if i.filename.endswith('.xml')):
                raise ValueError('Phần văn bản XML quá lớn; hãy chia tài liệu nhỏ hơn.')
            if suffix == '.pptx' and sum(i.filename.startswith('ppt/slides/slide') and i.filename.endswith('.xml') for i in items)>100:
                raise ValueError('Tối đa 100 slide.')
            required = 'ppt/presentation.xml' if suffix == '.pptx' else 'word/document.xml'
            if required not in archive.namelist():
                raise ValueError('Nội dung không đúng định dạng file.')
    warnings = []
    if suffix == '.pptx':
        deck = extract(path, lightweight=True)
        sections = [{'number': s['slide'], 'text': '\n'.join(t.strip() for t in s['text'] if t.strip()), 'images': s['picture_shapes']} for s in deck['slides']]
        label = 'Slide'
    elif suffix == '.pdf':
        with path.open('rb') as stream:
            header = stream.read(5)
        if header != b'%PDF-':
            raise ValueError('File không có định dạng PDF hợp lệ.')
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError('Hãy bỏ mật khẩu PDF trước khi tải lên.')
        if len(reader.pages) > 100:
            raise ValueError('Tối đa 100 trang PDF.')
        sections = [{'number': n, 'text': page.extract_text() or '', 'images': 0} for n, page in enumerate(reader.pages, 1)]
        label = 'Trang'
        warnings.append('Trang PDF được render để kiểm tra ngữ cảnh; chưa OCR tự động, cần kiểm định ảnh trước khi dùng.')
    elif suffix == '.docx':
        doc = Document(path)
        # DOCX has no reliable page boundaries without a layout engine.
        text = '\n'.join([p.text for p in doc.paragraphs] + [' | '.join(c.text for c in row.cells) for table in doc.tables for row in table.rows])
        chunks = [text[i:i+3000] for i in range(0, len(text), 3000)]
        sections = [{'number': n, 'text': text, 'images': 0} for n, text in enumerate(chunks, 1)] or [{'number':1,'text':'','images':0}]
        label = 'Đoạn'
        warnings.append('DOCX được chia theo đoạn văn bản, không suy đoán số trang in; không OCR ảnh.')
    else:
        text = path.read_text(encoding='utf-8-sig')
        if '\x00' in text:
            raise ValueError('TXT phải là văn bản UTF-8.')
        sections = [{'number': n, 'text': text[i:i+3000], 'images': 0} for n, i in enumerate(range(0, len(text), 3000), 1)]
        label = 'Đoạn'
    if len(sections) > 100 or sum(len(s['text']) for s in sections) > MAX_TEXT:
        raise ValueError('Tối đa 100 phần và 60.000 ký tự; hãy chia tài liệu nhỏ hơn.')
    if not any(s['text'].strip() for s in sections) and suffix=='.txt':
        raise ValueError('Không tìm thấy chữ có thể trích xuất. Hãy dùng bản có văn bản hoặc TXT; chưa hỗ trợ OCR.')
    result={'label':label,'sections':sections,'warnings':warnings}
    if media_root is not None:
        from .media import extract_media
        result=extract_media(path,result,media_root,render=render)
    elif not any(s['text'].strip() for s in sections):
        raise ValueError('Không có chữ; cần trích ảnh nguồn để kiểm định.')
    return result
