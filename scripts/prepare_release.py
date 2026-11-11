"""Prepare a code-only folder for manual GitHub upload; never push or deploy."""
import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.ai import configuration


def prepare(target):
    target=Path(target).resolve()
    if target.exists():raise ValueError('Release folder already exists; choose a new folder')
    selected=[]
    for folder in ['backend','frontend/src','frontend/tests','docs','.github']:
        selected.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and not any(x in p.relative_to(ROOT/folder).parts for x in ['data','.venv','__pycache__','.pytest_cache']))
    for folder in ['frontend','scripts']:
        selected.extend(p for p in (ROOT/folder).iterdir() if p.is_file() and p.suffix in ['.py','.ps1','.mjs','.json','.html','.ts'])
    selected.extend(ROOT/name for name in ['README.md','PLAN.md','STATUS.md','.gitignore','.dockerignore','Dockerfile','render.yaml','netlify.toml','START-WEBSITE.cmd'])
    selected=sorted(set(p for p in selected if p.name not in ['.env','tsconfig.tsbuildinfo'] and (not p.name.startswith('.env.') or p.name=='.env.example')))
    key=configuration().get('GEMINI_API_KEY') or ''
    for p in selected:
        relative=p.relative_to(ROOT)
        if p.stat().st_size>10*1024*1024:raise ValueError('Unexpected large source file: '+str(relative))
        if key and key.encode() in p.read_bytes():raise ValueError('Secret detected; release not created')
    target.mkdir(parents=True)
    for p in selected:
        dest=target/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    return {'status':'PASS','files':len(selected),'data_included':False,'api_key_included':False}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default=str(ROOT/'deploy/release'))
    try:print(json.dumps(prepare(parser.parse_args().output)))
    except ValueError as error:raise SystemExit(str(error))
