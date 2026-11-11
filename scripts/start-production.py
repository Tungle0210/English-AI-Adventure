"""One process owns SQLite and the durable queue; no trusted forwarded headers."""
import os,sys
port=int(os.environ.get('PORT','8000'))
if not 1<=port<=65535:raise SystemExit('Invalid PORT')
os.execv(sys.executable,[sys.executable,'-m','uvicorn','backend.main:app','--host','0.0.0.0','--port',str(port),'--workers','1','--no-access-log','--no-proxy-headers','--timeout-graceful-shutdown','65'])
