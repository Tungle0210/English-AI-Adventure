"""Read-only database/model probes. Never print DSNs, keys or exception messages."""
import json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import config,ai

def probe_db(name):
    dsn=config.setting(name)
    if not config.configured(dsn):return {'status':'NOT_TESTED','reason':'MISSING_OR_PLACEHOLDER'}
    started=time.perf_counter()
    try:
        import psycopg
        with psycopg.connect(dsn,sslmode='require',connect_timeout=12,autocommit=True) as c:
            c.execute('BEGIN READ ONLY')
            c.execute("SET LOCAL statement_timeout='10s'")
            value=c.execute('SHOW transaction_read_only').fetchone()[0]
            read_only=value.decode() if isinstance(value,bytes) else value
            version=c.execute('SHOW server_version_num').fetchone()[0]
            if isinstance(version,bytes):version=version.decode()
            tls=bool(c.pgconn.ssl_in_use)
            c.execute('ROLLBACK')
            assert read_only=='on' and tls
        return {'status':'PASS','read_only':True,'tls':True,'server_version_num':version,'ms':round((time.perf_counter()-started)*1000,2)}
    except Exception as e:return {'status':'FAIL','error_type':type(e).__name__,'sqlstate':getattr(e,'sqlstate',None),'reason':next((tag for phrase,tag in [('password authentication failed','AUTHENTICATION_FAILED'),('could not translate host','DNS_FAILED'),('timeout','CONNECTION_TIMEOUT'),('connection string','INVALID_DSN')] if phrase in str(e).lower()),'CONNECTION_OR_VALIDATION_FAILED'),'ms':round((time.perf_counter()-started)*1000,2)}

def model_probe():
    cfg=ai.configuration();started=time.perf_counter()
    if not all(config.configured(cfg.get(k)) for k in ('GEMINI_API_KEY','GEMINI_MODEL')):return {'status':'NOT_TESTED','reason':'MISSING_CONFIG'}
    try:
        from google import genai
        from google.genai import types
        with genai.Client(api_key=cfg['GEMINI_API_KEY'],http_options=types.HttpOptions(timeout=15000,retry_options=types.HttpRetryOptions(attempts=1))) as c:
            model=c.models.get(model=cfg['GEMINI_MODEL'])
        return {'status':'PASS','method':'models.get','model_name_matches':model.name.split('/')[-1]==cfg['GEMINI_MODEL'],'generation_requests':0,'ms':round((time.perf_counter()-started)*1000,2)}
    except Exception as e:return {'status':'FAIL','method':'models.get','generation_requests':0,'error_type':type(e).__name__,'http_code':getattr(e,'code',None)}

if __name__=='__main__':
    result={'DATABASE_URL':probe_db('DATABASE_URL'),'DATABASE_DIRECT_URL':probe_db('DATABASE_DIRECT_URL'),'gemini':model_probe()}
    (ROOT/'reports/neon/connections.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
