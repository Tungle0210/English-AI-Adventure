"""Schema shared by new cloud rehearsal and runtime; JSON stays byte-preserving TEXT."""
CORE='''
CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY, title TEXT, grade INTEGER, state TEXT, code TEXT UNIQUE, revision INTEGER, document TEXT, questions TEXT, origin TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL);
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS calls(at REAL);
CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, lesson_id TEXT, title TEXT, mode TEXT, questions TEXT, responses TEXT, started TEXT, completed TEXT);
'''
QUEUE='''
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,operation TEXT,lesson_id TEXT,payload TEXT,fingerprint TEXT,idempotency_key TEXT UNIQUE,state TEXT,result TEXT,error TEXT,created REAL,updated REAL);
CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state,created);
CREATE TABLE IF NOT EXISTS upload_sessions(id TEXT PRIMARY KEY,filename TEXT,size INTEGER,offset INTEGER,state TEXT,created REAL);
'''
TABLES=['lessons','sessions','cache','calls','attempts','jobs','upload_sessions']
