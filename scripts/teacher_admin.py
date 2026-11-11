"""Offline administrator CLI. Never exposes an HTTP reset endpoint or prints a code."""
import argparse, hashlib, json, os, re, secrets, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import config, database
from backend.schema import CORE, QUEUE

def credential():
    code=secrets.token_urlsafe(24)
    salt=secrets.token_bytes(16); rounds=600000
    return code, salt.hex()+':'+str(rounds)+':'+hashlib.pbkdf2_hmac('sha256',code.encode(),salt,rounds).hex()

def bootstrap(schema, output):
    """Create an EMPTY demo namespace only; never merges with an existing schema."""
    import psycopg
    from psycopg import sql
    if not re.fullmatch(r'demo_[a-z0-9_]{1,50}',schema):
        raise ValueError('A fresh demo_ schema is required')
    output=Path(output).resolve()
    private=(ROOT/'private-backups').resolve()
    if private not in output.parents or output.exists():
        raise ValueError('Choose a new file in private-backups, outside every Git checkout')
    code, hashed=credential()
    output.parent.mkdir(parents=True,exist_ok=True)
    # Reserve the delivery file BEFORE changing the database. No overwrite permitted.
    fd=os.open(str(output),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(code+'\n')
    try:
        with psycopg.connect(config.setting('DATABASE_DIRECT_URL'),sslmode='require',connect_timeout=10,prepare_threshold=None) as pg:
            if pg.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s',(schema,)).fetchone():
                raise ValueError('Schema already exists; no data changed')
            pg.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            pg.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog').format(sql.Identifier(schema)))
            database.Connection(pg).executescript(CORE+QUEUE+database.EXTRA_SCHEMA)
            pg.execute('INSERT INTO app_settings VALUES(%s,%s)',('teacher_auth',hashed))
            pg.execute('INSERT INTO app_settings VALUES(%s,%s)',('migration_ready','yes'))
            pg.execute('INSERT INTO app_settings VALUES(%s,%s)',('dataset_kind','empty-demo-no-real-migration'))
        return {'status':'PASS','schema':schema,'teacher_file':str(output),'real_data_migrated':False,'lessons':0}
    except Exception:
        # The reserved file remains private for diagnosis; never log code/driver details.
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--new-demo-schema',required=True);p.add_argument('--private-output',required=True)
    a=p.parse_args()
    try:print(json.dumps(bootstrap(a.new_demo_schema,a.private_output)))
    except Exception as e:raise SystemExit(json.dumps({'status':'FAIL','error_type':type(e).__name__}))
