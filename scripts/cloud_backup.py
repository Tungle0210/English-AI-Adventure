"""Read-only cloud backup to a NEW local SQLite/media directory. No restore/deploy."""
import argparse,json,sqlite3,sys
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import config,objects,database
from backend.schema import CORE,QUEUE,TABLES
from scripts.cloud_migration import canonical


def export_cloud(target,dsn=None,schema=None,writers_stopped=False):
    import psycopg
    from psycopg import sql
    if not writers_stopped:raise ValueError('Confirm writers are stopped; this flag does not enable remote maintenance')
    if not config.object_storage():raise ValueError('S3 mode must be explicitly enabled for this backup command')
    target=Path(target).resolve()
    if target.exists():raise ValueError('Backup target must be NEW; never overwrite')
    target.mkdir(parents=True);dsn=dsn or config.setting('DATABASE_DIRECT_URL');schema=schema or database.schema_name()
    from urllib.parse import urlsplit
    ssl='disable' if urlsplit(dsn).hostname in ('127.0.0.1','localhost','::1') else 'require'
    expected={}
    with psycopg.connect(dsn,sslmode=ssl,autocommit=True,prepare_threshold=None,connect_timeout=10) as pg,closing(sqlite3.connect(target/'adventure.sqlite3')) as local:
        pg.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        pg.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog').format(sql.Identifier(schema)))
        if pg.execute("SELECT count(*) FROM jobs WHERE state='running'").fetchone()[0]:raise ValueError('Running jobs prevent a consistent cross-service backup')
        local.executescript(CORE+QUEUE)
        for name in TABLES:
            cursor=pg.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(name)));columns=[col.name for col in cursor.description];rows=cursor.fetchall()
            if any(not __import__('re').fullmatch('[a-z_]+',col) for col in columns):raise ValueError('Unsupported columns')
            local.executemany('INSERT INTO '+name+' ('+','.join('"'+col+'"' for col in columns)+') VALUES('+','.join('?' for _ in columns)+')',rows)
            if canonical(local.execute('SELECT '+','.join('"'+col+'"' for col in columns)+' FROM '+name).fetchall())!=canonical(rows):raise ValueError('SQLite backup row mismatch')
            expected[name]={'rows':len(rows),'sha256':canonical(rows)}
        auth=pg.execute("SELECT value FROM app_settings WHERE key='teacher_auth'").fetchone()
        if not auth:raise ValueError('Teacher hash is missing')
        local.execute('CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        local.execute('INSERT INTO app_settings VALUES(?,?)',('teacher_auth',auth[0]))
        local.commit();pg.execute('ROLLBACK')
    files=[]
    for name in objects.list_names(''):
        path=objects.ensure(target,name,refresh=True)
        files.append({'path':name,'sha256':objects.checksum(path),'bytes':path.stat().st_size})
    with closing(sqlite3.connect(target/'adventure.sqlite3')) as local:
        for ident,offset,state in local.execute('SELECT id,"offset",state FROM upload_sessions'):
            if state in ('uploading','failed') and offset>0:objects.materialize_upload(target,ident,offset)
        if local.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity mismatch')
    manifest={'status':'PASS','read_only_postgres':True,'new_directory_only':True,'tables':expected,'files':files}
    (target/'cloud-backup-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return {'status':'PASS','tables':{k:v['rows'] for k,v in expected.items()},'files_verified':len(files),'original_data_modified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--into',required=True);p.add_argument('--writers-stopped',action='store_true');a=p.parse_args()
    try:print(json.dumps(export_cloud(a.into,writers_stopped=a.writers_stopped)))
    except Exception as e:raise SystemExit(json.dumps({'status':'FAIL','error_type':type(e).__name__}))
