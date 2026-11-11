"""Offline-copy migration rehearsal. Real cloud writes require explicit future authorization."""
import argparse,base64,hashlib,json,os,re,sqlite3,sys,time,uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import config,database,objects
from backend.schema import CORE,QUEUE,TABLES
from scripts.data_bundle import inspect_bundle

def canonical(rows):
    def default(value):
        if isinstance(value,(bytes,memoryview)):return {'bytes':base64.b64encode(bytes(value)).decode()}
        raise TypeError('Unsupported persisted type')
    lines=sorted(json.dumps(list(row),ensure_ascii=False,separators=(',',':'),default=default) for row in rows)
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()

def sqlite_tables(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        if set(names)-set(TABLES)-{'app_settings'}:raise ValueError('Unrecognized tables; refusing to silently omit data')
        result={}
        for name in names:
            cols=[r[1] for r in c.execute('PRAGMA table_info('+name+')')]
            if any(not re.fullmatch('[a-z_]+',x) for x in cols):raise ValueError('Unsupported column name')
            rows=c.execute('SELECT * FROM '+name).fetchall()
            result[name]={'columns':cols,'rows':rows,'sha256':canonical(rows),'sqlite_ddl':c.execute("SELECT sql FROM sqlite_master WHERE name=?",(name,)).fetchone()[0]}
        return result

def plan(bundle,work):
    work=Path(work).resolve()
    if work.exists():raise ValueError('Work directory must be new; no overwrites')
    work.mkdir(parents=True);source=work/'source'
    inspect_bundle(bundle,source)
    return build_plan(work)

def plan_local(data,work):
    import shutil
    data=Path(data).resolve();work=Path(work).resolve()
    if work.exists() or data==work or data in work.parents:raise ValueError('Choose a new work directory outside source data')
    work.mkdir(parents=True);source=work/'source';source.mkdir()
    with closing(sqlite3.connect((data/'adventure.sqlite3').as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(source/'adventure.sqlite3')) as dst:
        if src.execute("SELECT count(*) FROM jobs WHERE state='running'").fetchone()[0]:raise ValueError('Active jobs: wait before taking a cross-file copy')
        src.backup(dst)
    before=sqlite_tables(source/'adventure.sqlite3')
    for path in data.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(data).as_posix()
        if relative in ('adventure.sqlite3','adventure.sqlite3-wal','adventure.sqlite3-shm','.runtime.lock'):continue
        if path.is_symlink() or path.name.startswith('.env'):raise ValueError('Unsafe/secret source file')
        target=source/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        if objects.checksum(path)!=objects.checksum(target):raise ValueError('Source files changed during copy; do not use this plan')
    after=sqlite_tables(data/'adventure.sqlite3')
    if set(before)!=set(after) or any(before[k]['sha256']!=after[k]['sha256'] for k in before):raise ValueError('Live SQLite changed during copy; retry only during a quiet window')
    return build_plan(work)

def build_plan(work):
    source=work/'source';tables=sqlite_tables(source/'adventure.sqlite3')
    files=[p for p in source.rglob('*') if p.is_file() and p.relative_to(source).as_posix() not in ('adventure.sqlite3','adventure.sqlite3-wal','adventure.sqlite3-shm','.runtime.lock','teacher-access.txt')]
    manifest={'format':1,'tables':{k:{'rows':len(v['rows']),'sha256':v['sha256'],'columns':v['columns']} for k,v in tables.items()},'files':[{'path':p.relative_to(source).as_posix(),'bytes':p.stat().st_size,'sha256':objects.checksum(p)} for p in files]}
    indexes={}
    for p in (source/'media').glob('*.json'):
        a=json.loads(p.read_text(encoding='utf-8'));indexes.setdefault(a['document_hash'],[]).append(a['id'])
    for sha,ids in indexes.items():
        relative='indexes/'+sha+'.json';p=source/relative;p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(ids),encoding='utf-8')
        manifest['files'].append({'path':relative,'bytes':p.stat().st_size,'sha256':objects.checksum(p)})
    (work/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'status':'PASS','mode':'PLAN_ONLY','production_writes':False,'tables':manifest['tables'],'files':len(manifest['files']),'object_bytes':sum(f['bytes'] for f in manifest['files'])}
    (work/'plan-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary

def apply_copy(work,dsn,schema):
    """Only called against loopback in rehearsal, or by the gated future apply command."""
    import psycopg
    from psycopg import sql
    work=Path(work);source=work/'source';manifest=json.loads((work/'manifest.json').read_text(encoding='utf-8'));tables=sqlite_tables(source/'adventure.sqlite3')
    if not re.fullmatch('[a-z][a-z0-9_]{0,62}',schema):raise ValueError('Invalid target schema')
    ssl='disable' if urlsplit(dsn).hostname in ('127.0.0.1','localhost','::1') else 'require'
    # Check existing schema before writing any object; never merge/overwrite a populated schema.
    with psycopg.connect(dsn,sslmode=ssl,connect_timeout=10,prepare_threshold=None) as pg:
        if pg.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s',(schema,)).fetchone():raise ValueError('Target schema already exists; choose a fresh namespace')
    if objects.list_names(''):raise ValueError('S3 target prefix is not empty; choose a fresh namespace')
    objects_verified=0
    for entry in manifest['files']:
        if entry['path']=='teacher-access.txt':raise ValueError('Rebuild this legacy plan: plaintext teacher credentials must never enter object storage')
        path=source/entry['path']
        if objects.checksum(path)!=entry['sha256']:raise ValueError('Local file changed since plan')
        objects.publish(source,entry['path'])
        fetched=objects.ensure(work/'verify-cache',entry['path'],refresh=True)
        if objects.checksum(fetched)!=entry['sha256']:raise ValueError('Object readback checksum mismatch')
        objects_verified+=1
    with psycopg.connect(dsn,sslmode=ssl,connect_timeout=10,prepare_threshold=None) as pg:
        pg.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        pg.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog').format(sql.Identifier(schema)))
        wrapped=database.Connection(pg);wrapped.executescript(CORE+QUEUE+database.EXTRA_SCHEMA)
        for name,data in tables.items():
            columns=sql.SQL(',').join(map(sql.Identifier,data['columns']))
            command=sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(name),columns,sql.SQL(',').join([sql.Placeholder()]*len(data['columns'])))
            with pg.cursor() as cursor:
                for row in data['rows']:cursor.execute(command,row)
        checked={}
        for name,data in tables.items():
            rows=pg.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(map(sql.Identifier,data['columns'])),sql.Identifier(name))).fetchall()
            if len(rows)!=len(data['rows']) or canonical(rows)!=data['sha256']:raise ValueError('PostgreSQL checksum mismatch: '+name)
            checked[name]={'rows':len(rows),'sha256_match':True}
        existing=pg.execute("SELECT value FROM app_settings WHERE key='teacher_auth'").fetchone()
        if not existing:
            salt=os.urandom(16);rounds=600000
            code=(source/'teacher-access.txt').read_text(encoding='utf-8').strip()
            auth=salt.hex()+':'+str(rounds)+':'+hashlib.pbkdf2_hmac('sha256',code.encode(),salt,rounds).hex()
            pg.execute('INSERT INTO app_settings VALUES(%s,%s)',('teacher_auth',auth))
        for key,value in [('migration_ready','yes'),('migration_manifest',json.dumps(manifest))]:
            pg.execute('INSERT INTO app_settings VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value',(key,value))
    return {'status':'PASS','tables':checked,'objects_verified':objects_verified,'ids_json_history_preserved':True,'target_schema':schema}

def rollback_copy(work,dsn,schema):
    import psycopg
    from psycopg import sql
    work=Path(work);target=work/'rollback-copy';target.mkdir(exist_ok=False)
    manifest=json.loads((work/'manifest.json').read_text(encoding='utf-8'));tables=sqlite_tables(work/'source/adventure.sqlite3')
    ssl='disable' if urlsplit(dsn).hostname in ('127.0.0.1','localhost','::1') else 'require'
    with psycopg.connect(dsn,sslmode=ssl,autocommit=True,connect_timeout=10,prepare_threshold=None) as pg,closing(sqlite3.connect(target/'adventure.sqlite3')) as local:
        pg.execute('BEGIN READ ONLY');pg.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog').format(sql.Identifier(schema)))
        for name,data in tables.items():
            local.execute(data['sqlite_ddl'])
            rows=pg.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(map(sql.Identifier,data['columns'])),sql.Identifier(name))).fetchall()
            local.executemany('INSERT INTO '+name+' VALUES('+','.join('?' for _ in data['columns'])+')',rows)
        local.commit();pg.execute('ROLLBACK')
    count=0
    for entry in manifest['files']:
        path=objects.ensure(target,entry['path'])
        if objects.checksum(path)!=entry['sha256']:raise ValueError('Rollback file mismatch')
        count+=1
    restored=sqlite_tables(target/'adventure.sqlite3')
    if any(restored[k]['sha256']!=data['sha256'] for k,data in tables.items()):raise ValueError('Rollback row mismatch')
    return {'status':'PASS','new_directory_only':True,'tables_match':True,'files_verified':count,'original_sqlite_changed':False}

def rehearse(work):
    from moto import mock_aws
    dsn='postgresql://postgres@127.0.0.1:55432/postgres';schema='qa_'+uuid.uuid4().hex[:16]
    # Rehearsal credentials intentionally replace all real S3 settings, including endpoint.
    env={'ADVENTURE_CLOUD_ENABLE':'yes','ADVENTURE_STORAGE_BACKEND':'s3','AWS_ACCESS_KEY_ID':'test-only-key','AWS_SECRET_ACCESS_KEY':'test-only-secret','AWS_SESSION_TOKEN':'','AWS_REGION':'us-east-2','S3_ENDPOINT_URL':'','S3_BUCKET':'eaa-rehearsal','S3_PREFIX':schema}
    from unittest.mock import patch
    with patch.dict(os.environ,env),mock_aws():
        objects.client().create_bucket(Bucket=objects.bucket(),CreateBucketConfiguration={'LocationConstraint':'us-east-2'})
        forward=apply_copy(work,dsn,schema);back=rollback_copy(work,dsn,schema)
    result={'engine':'PostgreSQL WASM/PGlite on Windows, NOT native Linux/Neon','production_sql_writes':False,'real_s3_migration':False,'object_store':'moto isolated S3 simulation','forward':forward,'rollback':back}
    (Path(work)/'rehearsal-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('plan');a.add_argument('--bundle',required=True);a.add_argument('--work',required=True)
    a=sub.add_parser('snapshot-plan');a.add_argument('--data',required=True);a.add_argument('--work',required=True)
    a=sub.add_parser('rehearse');a.add_argument('--work',required=True)
    a=sub.add_parser('apply');a.add_argument('--work',required=True);a.add_argument('--schema',required=True);a.add_argument('--permit-production-write',action='store_true')
    args=p.parse_args()
    try:
        if args.command=='plan':result=plan(args.bundle,args.work)
        elif args.command=='snapshot-plan':result=plan_local(args.data,args.work)
        elif args.command=='rehearse':result=rehearse(args.work)
        else:
            if not args.permit_production_write or config.setting('ADVENTURE_ALLOW_MIGRATION')!='yes':raise ValueError('Production migration is blocked; explicit operator authorization and ADVENTURE_ALLOW_MIGRATION=yes required')
            result=apply_copy(args.work,config.setting('DATABASE_DIRECT_URL'),args.schema)
        print(json.dumps(result,ensure_ascii=True))
    except Exception as e:
        # Never print library exception strings; they can include credentials or private SQL values.
        print(json.dumps({'status':'FAIL','error_type':type(e).__name__,'sqlstate':getattr(e,'sqlstate',None)}));sys.exit(1)
