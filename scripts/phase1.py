"""Local checks by default; generation requires explicit Free-plan confirmation."""
import argparse
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
from datetime import datetime, timezone
from zipfile import ZipFile

from dotenv import dotenv_values
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'


def save(name, data):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def shapes(items):
    for shape in items:
        yield shape
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from shapes(shape.shapes)


def extract(path, lightweight=False):
    if lightweight:
        return extract_lightweight(path)
    slides = []
    for n, slide in enumerate(Presentation(path).slides, 1):
        texts, pictures, fills = [], 0, 0
        for shape in shapes(slide.shapes):
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
            if shape.has_table:
                texts.extend(' | '.join(c.text for c in row.cells) for row in shape.table.rows)
            pictures += shape.shape_type == MSO_SHAPE_TYPE.PICTURE
            fills += len(shape._element.xpath('.//a:blip'))
        slides.append({'slide': n, 'text': texts, 'picture_shapes': pictures, 'image_references': fills})
    with ZipFile(path) as archive:
        media = [x for x in archive.namelist() if x.startswith('ppt/media/') and not x.endswith('/')]
    try:
        source_name = path.relative_to(ROOT).as_posix()
    except ValueError:
        source_name = path.name
    return {'file': source_name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'slide_count': len(slides), 'picture_shape_count': sum(x['picture_shapes'] for x in slides),
            'media_parts': media, 'slides': slides,
            'scope': 'Editable text and table cells only; no OCR. Picture shapes exclude master/background artwork. Media may include audio/video.'}


def extract_lightweight(path):
    """Read slide XML without loading embedded images/audio into RAM."""
    import posixpath
    import xml.etree.ElementTree as ET
    ns = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main', 'a':'http://schemas.openxmlformats.org/drawingml/2006/main', 'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    def paragraphs(node):
        output = []
        for paragraph in node.findall('a:p', ns):
            output.append(''.join(('\v' if x.tag == '{'+ns['a']+'}br' else x.text or '') for x in paragraph.iter() if x.tag in ('{'+ns['a']+'}t','{'+ns['a']+'}br')))
        return '\n'.join(output)
    slides = []
    with ZipFile(path) as archive:
        presentation = ET.fromstring(archive.read('ppt/presentation.xml'))
        rels = {r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(archive.read('ppt/_rels/presentation.xml.rels'))}
        for n, sid in enumerate(presentation.findall('p:sldIdLst/p:sldId', ns), 1):
            target = rels[sid.attrib['{'+ns['r']+'}id']]
            name = target.lstrip('/') if target.startswith('/') else posixpath.normpath('ppt/'+target)
            root = ET.fromstring(archive.read(name))
            texts = [paragraphs(t) for t in root.findall('.//p:sp/p:txBody', ns)]
            for table in root.findall('.//a:tbl', ns):
                for row in table.findall('a:tr', ns):
                    texts.append(' | '.join(paragraphs(cell.find('a:txBody', ns)) for cell in row.findall('a:tc', ns)))
            slides.append({'slide':n, 'text':texts, 'picture_shapes':len(root.findall('.//p:pic', ns)), 'image_references':len(root.findall('.//a:blip', ns))})
        media = [x for x in archive.namelist() if x.startswith('ppt/media/') and not x.endswith('/')]
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            digest.update(chunk)
    try:
        name = path.relative_to(ROOT).as_posix()
    except ValueError:
        name = path.name
    return {'file':name, 'sha256':digest.hexdigest(), 'slide_count':len(slides), 'picture_shape_count':sum(s['picture_shapes'] for s in slides), 'media_parts':media, 'slides':slides, 'scope':'Editable text and table cells only; no OCR. Picture shapes exclude master/background artwork. Media may include audio/video.'}


def local_checks():
    cfg = dotenv_values(ROOT / 'backend/.env', interpolate=False)
    checks = {'python': sys.version.split()[0], 'packages': {p: importlib.metadata.version(p) for p in ['google-genai', 'python-dotenv', 'python-pptx']},
              'config': {'file_exists': (ROOT / 'backend/.env').is_file(), 'key_present': bool(cfg.get('GEMINI_API_KEY')), 'model': cfg.get('GEMINI_MODEL')},
              'tools': {}}
    for name, cmd in [('node', ['node', '--version']), ('npm', ['npm.cmd', '--version']), ('git', ['git', '--version'])]:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        checks['tools'][name] = {'exit_code': r.returncode, 'version': r.stdout.strip()}
    # Exercise Git's real ignore engine without creating a repository in the project.
    with tempfile.TemporaryDirectory(dir=ROOT / '.cache') as folder:
        subprocess.run(['git', 'init', '-q', folder], check=True)
        shutil.copyfile(ROOT / '.gitignore', Path(folder) / '.gitignore')
        checks['gitignore'] = {}
        for path in ['.env', 'backend/.env', 'backend/.env.local', 'backend/.venv/file', '.cache/file', 'backend/.env.example']:
            r = subprocess.run(['git', '-C', folder, 'check-ignore', '--no-index', path], capture_output=True, text=True)
            expected = path != 'backend/.env.example'
            checks['gitignore'][path] = {'ignored': r.returncode == 0, 'pass': (r.returncode == 0) == expected}
    decks = [extract(p) for p in sorted((ROOT / 'input').glob('*.pptx')) if not p.name.startswith('~$')]
    save('powerpoint.json', decks)
    checks['powerpoint'] = [{'file': d['file'], 'slides': d['slide_count'], 'picture_shapes': d['picture_shape_count'], 'media_parts': len(d['media_parts'])} for d in decks]
    checks['repository_exists'] = (ROOT / '.git').exists()
    checks['inventory'] = [p.relative_to(ROOT).as_posix() for p in sorted(ROOT.rglob('*')) if p.is_file() and not any(part in {'.venv', '.cache', '.git', '__pycache__'} for part in p.relative_to(ROOT).parts)]
    checks['pass'] = all(v['pass'] for v in checks['gitignore'].values()) and all(v['exit_code'] == 0 for v in checks['tools'].values()) and checks['config']['key_present'] and bool(checks['config']['model'])
    save('environment.json', checks)
    print(json.dumps({k: v for k, v in checks.items() if k != 'inventory'}, ensure_ascii=True, indent=2))
    return checks['pass']


def api_check():
    from google import genai
    from google.genai import types
    cfg = dotenv_values(ROOT / 'backend/.env', interpolate=False)
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'model': cfg.get('GEMINI_MODEL'), 'free_plan': 'user_confirmed', 'max_requests': 1, 'status': 'FAIL'}
    if not cfg.get('GEMINI_API_KEY') or not cfg.get('GEMINI_MODEL'):
        result['error'] = 'MISSING_CONFIG'
    else:
        try:
            with genai.Client(api_key=cfg['GEMINI_API_KEY'], http_options=types.HttpOptions(timeout=30000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
                response = client.models.generate_content(model=cfg['GEMINI_MODEL'], contents='Reply with exactly: ENGLISH_AI_ADVENTURE_OK', config=types.GenerateContentConfig(max_output_tokens=64, temperature=0))
            text = (response.text or '').replace(cfg['GEMINI_API_KEY'], '[REDACTED]')
            result.update(status='PASS' if text.strip() == 'ENGLISH_AI_ADVENTURE_OK' else 'FAIL', response=text,
                          usage=response.usage_metadata.model_dump(mode='json') if response.usage_metadata else None)
        except Exception as error:
            # Never log exception bodies, headers or request URLs that might contain credentials.
            result.update(error_type=type(error).__name__)
            code = getattr(error, 'code', None)
            if isinstance(code, int):
                result['http_code'] = code
            message = getattr(error, 'message', '')
            if isinstance(message, str):
                message = message.replace(cfg['GEMINI_API_KEY'], '[REDACTED]')
                result['message'] = re.sub(r'https?://\S+', '[URL omitted]', message)[:1000]
            result['diagnosis'] = {400: 'Invalid request/configuration', 401: 'Authentication failed', 403: 'Permission or regional restriction', 404: 'Configured model unavailable', 429: 'Quota exhausted/rate limit; no retry or billing upgrade', 503: 'Service unavailable'}.get(code, 'Connection/SDK error; inspect network without logging secrets')
            if code == 404 and 'no longer available to new users' in message:
                result['diagnosis'] = 'Configured model retired for new users; listModels presence does not guarantee generateContent access'
    save('gemini.json', result)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return result['status'] == 'PASS'


def list_models():
    from google import genai
    from google.genai import types
    cfg = dotenv_values(ROOT / 'backend/.env', interpolate=False)
    try:
        with genai.Client(api_key=cfg['GEMINI_API_KEY'], http_options=types.HttpOptions(timeout=30000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
            models = [{'name': m.name, 'supported_actions': m.supported_actions} for m in client.models.list()]
        save('models.json', models)
        print(json.dumps(models, indent=2))
        return True
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__}))
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', action='store_true')
    parser.add_argument('--free-plan-confirmed', action='store_true')
    parser.add_argument('--list-models', action='store_true')
    args = parser.parse_args()
    (ROOT / '.cache').mkdir(exist_ok=True)
    if args.api and not args.free_plan_confirmed:
        parser.error('API requires --free-plan-confirmed after verifying Plan = Free in AI Studio')
    sys.exit(0 if (list_models() if args.list_models else api_check() if args.api else local_checks()) else 1)
