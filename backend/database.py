"""PostgreSQL persistence; local SQLite remains available for rollback/rehearsal.
JSON columns intentionally remain TEXT so historical snapshots retain exact bytes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib,logging,re,threading,time
from . import config

POOLS={};POOL_LOCK=threading.Lock()
JOB=ContextVar('adventure_job',default=None)

class DatabaseUnavailable(RuntimeError):pass
class LeaseLost(RuntimeError):pass

class Row(dict):
    def __getitem__(self,key):return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)

class Cursor:
    def __init__(self,cursor):self.cursor=cursor
    def fetchone(self):
        row=self.cursor.fetchone();return Row(row) if row is not None else None
    def fetchall(self):return [Row(r) for r in self.cursor.fetchall()]
    @property
    def rowcount(self):return self.cursor.rowcount
    def __iter__(self):return iter(self.fetchall())


def parameters(sql):
    # Replace SQLite bind markers only outside quoted SQL literals/identifiers.
    output=[];quote=None;index=0
    while index<len(sql):
        ch=sql[index]
        if quote:
            output.append('%%' if ch=='%' else ch)
            if ch==quote:
                if index+1<len(sql) and sql[index+1]==quote:output.append(sql[index+1]);index+=1
                else:quote=None
        elif ch in ("'",'"'):quote=ch;output.append(ch)
        elif ch.isalpha() or ch=='_':
            end=index+1
            while end<len(sql) and (sql[end].isalnum() or sql[end]=='_'):end+=1
            token=sql[index:end];output.append('"offset"' if token=='offset' else token);index=end-1
        else:output.append('%s' if ch=='?' else '%%' if ch=='%' else ch)
        index+=1
    return ''.join(output)


class Connection:
    backend='postgres'
    def __init__(self,raw):self.raw=raw
    def execute(self,sql,args=()):
        if sql.strip().upper()=='BEGIN IMMEDIATE':return Cursor(self.raw.execute('SELECT 1')) # The transaction already owns the schema advisory lock.
        if sql.startswith('INSERT OR REPLACE INTO cache'):
            sql=sql.replace('INSERT OR REPLACE','INSERT',1)+' ON CONFLICT (key) DO UPDATE SET payload=EXCLUDED.payload'
        return Cursor(self.raw.execute(parameters(sql),args))
    def executemany(self,sql,args):
        cursor=self.raw.cursor();cursor.executemany(parameters(sql),args);return Cursor(cursor)
    def executescript(self,script):
        # This method is used for trusted schema DDL only, never user input.
        script=re.sub(r'\bREAL\b','DOUBLE PRECISION',script)
        for statement in script.split(';'):
            if statement.strip():self.raw.execute(parameters(statement))


def schema_name():return config.setting('ADVENTURE_PG_SCHEMA','english_ai')

def lock_id():return int.from_bytes(hashlib.sha256(('english-ai:'+schema_name()).encode()).digest()[:8],'big',signed=True)

def get_pool():
    dsn=config.setting('DATABASE_URL')
    if not config.configured(dsn):raise DatabaseUnavailable('PostgreSQL connection not configured')
    key=(dsn,schema_name())
    with POOL_LOCK:
        if key not in POOLS:
            from psycopg_pool import ConnectionPool
            from psycopg.rows import dict_row
            # Never permit driver retries/logging to expose connection strings.
            logging.getLogger('psycopg.pool').setLevel(logging.CRITICAL)
            POOLS[key]=ConnectionPool(dsn,min_size=0,max_size=min(5,max(1,int(config.setting('ADVENTURE_PG_POOL_MAX','3')))),timeout=12,max_idle=60,open=True,
                kwargs={'prepare_threshold':None,'row_factory':dict_row,'connect_timeout':8,'sslmode':config.setting('PGSSLMODE','require')})
        return POOLS[key]


@contextmanager
def connect():
    from psycopg import sql,Error
    from psycopg_pool import PoolTimeout
    try:
        with get_pool().connection() as raw:
            if config.setting('ADVENTURE_PG_READONLY','no')=='yes':raw.execute('SET TRANSACTION READ ONLY')
            raw.execute("SET LOCAL statement_timeout='15s'")
            raw.execute("SET LOCAL lock_timeout='10s'")
            raw.execute(sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(schema_name())))
            raw.execute('SELECT pg_advisory_xact_lock(%s)',(lock_id(),))
            job=JOB.get()
            if job:
                row=raw.execute("SELECT owner,expires,job_id FROM worker_lease WHERE name='worker'").fetchone()
                state=raw.execute('SELECT state FROM jobs WHERE id=%s',(job[0],)).fetchone()
                if not row or row['owner']!=job[1] or row['job_id']!=job[0] or row['expires']<=time.time() or not state or state['state']!='running':raise LeaseLost('Job lease expired; refusing late writes')
            yield Connection(raw)
    except (Error,PoolTimeout):raise DatabaseUnavailable('PostgreSQL unavailable; no secrets included in this diagnostic') from None


@contextmanager
def job_scope(ident,owner):
    token=JOB.set((ident,owner))
    try:yield
    finally:JOB.reset(token)

EXTRA_SCHEMA='''
CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS worker_lease(name TEXT PRIMARY KEY,owner TEXT,expires DOUBLE PRECISION,job_id TEXT);
'''


def media_in_attempt(c,ident):
    if getattr(c,'backend','sqlite')=='postgres':
        return bool(c.execute("SELECT 1 FROM attempts, jsonb_array_elements(attempts.questions::jsonb) q WHERE q->>'image_asset_id'=? AND (q->>'approved')='true' LIMIT 1",(ident,)).fetchone())
    return bool(c.execute("SELECT 1 FROM attempts,json_each(attempts.questions) q WHERE json_extract(q.value,'$.image_asset_id')=? AND json_extract(q.value,'$.approved')=1 LIMIT 1",(ident,)).fetchone())


def completed_upload_job(c,ident):
    if getattr(c,'backend','sqlite')=='postgres':return c.execute("SELECT id FROM jobs WHERE state='succeeded' AND payload::jsonb->>'upload_id'=? ORDER BY updated DESC LIMIT 1",(ident,)).fetchone()
    return c.execute("SELECT id FROM jobs WHERE state='succeeded' AND json_extract(payload,'$.upload_id')=? ORDER BY updated DESC LIMIT 1",(ident,)).fetchone()


def ready(c):
    try:
        row=c.execute("SELECT value FROM app_settings WHERE key='migration_ready'").fetchone()
        auth=c.execute("SELECT value FROM app_settings WHERE key='teacher_auth'").fetchone()
        if not row or row['value']!='yes' or not auth:raise DatabaseUnavailable('Cloud migration is not verified; refusing to create empty data')
    except Exception:raise DatabaseUnavailable('Cloud migration is not verified; refusing to create empty data') from None


def teacher_matches(c,value):
    import secrets
    row=c.execute("SELECT value FROM app_settings WHERE key='teacher_auth'").fetchone()
    if not row:return False
    data=row['value'].split(':')
    if len(data)!=3:return False
    actual=hashlib.pbkdf2_hmac('sha256',value.encode(),bytes.fromhex(data[0]),int(data[1])).hex()
    return secrets.compare_digest(actual,data[2])
