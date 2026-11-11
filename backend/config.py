"""Runtime settings; secrets never enter frontend configuration."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import dotenv_values

ENV = Path(__file__).with_name('.env')

def gemini_config(fallback=None):
    if fallback is None:fallback=dotenv_values(ENV,interpolate=False)
    return {name:os.environ.get(name,fallback.get(name,'')) for name in ('GEMINI_API_KEY','GEMINI_MODEL')}

def maintenance():return os.environ.get('ADVENTURE_MAINTENANCE','0')=='1'

def production():return os.environ.get('ADVENTURE_ENV','local')=='production'

def origins():return {s.strip().rstrip('/') for s in os.environ.get('ADVENTURE_ALLOWED_ORIGINS','').split(',') if s.strip()}

def hosts():return {s.strip().lower() for s in os.environ.get('ADVENTURE_ALLOWED_HOSTS','127.0.0.1,localhost,testserver').split(',') if s.strip()}

def validate():
    if production():
        data=os.environ.get('ADVENTURE_DATA_DIR','')
        if not data or not Path(data).is_absolute():raise RuntimeError('Production requires an absolute ADVENTURE_DATA_DIR')
        if not origins() or any(urlsplit(o).scheme!='https' or urlsplit(o).path or urlsplit(o).query or urlsplit(o).fragment or urlsplit(o).username for o in origins()):raise RuntimeError('Configure exact HTTPS ADVENTURE_ALLOWED_ORIGINS')
        if not os.environ.get('ADVENTURE_ALLOWED_HOSTS') or '*' in hosts():raise RuntimeError('Configure exact ADVENTURE_ALLOWED_HOSTS')
        if os.environ.get('WEB_CONCURRENCY','1')!='1':raise RuntimeError('SQLite/disk jobs require one process')
        if maintenance():return
        if os.environ.get('ADVENTURE_IMPORT_READY')!='yes':raise RuntimeError('Migrate/verify persistent data first, then set ADVENTURE_IMPORT_READY=yes')
        db=Path(data)/'adventure.sqlite3'
        if not db.is_file() or not (Path(data)/'teacher-access.txt').is_file():raise RuntimeError('Persistent database/teacher code missing; refusing to seed production')
