"""Postgres-backed job lease; no idle polling, no duplicate retry of interrupted AI."""
import json,threading,time,uuid
from .jobs import Queue
from . import database

class PostgresQueue(Queue):
    ttl=90
    def __init__(self,*args):super().__init__(*args);self.owner=uuid.uuid4().hex;self.blocked=False
    def reap(self,c):
        lease=c.execute("SELECT * FROM worker_lease WHERE name='worker'").fetchone()
        live=lease and lease['expires']>time.time()
        c.execute("UPDATE jobs SET state='interrupted',error=?,updated=? WHERE state='running' AND id<>?",(json.dumps({'status':409,'detail':'Tác vụ gián đoạn; kiểm tra bản nháp trước khi thử lại. Không tự gọi AI lại.'}),time.time(),lease['job_id'] if live else ''))
        return lease if live else None
    def initialize(self):
        with self.db() as c:database.ready(c);self.reap(c)
    def heartbeat(self,ident,stop):
        while not stop.wait(20):
            try:
                with self.db() as c:c.execute("UPDATE worker_lease SET expires=? WHERE name='worker' AND owner=? AND job_id=? AND expires>?",(time.time()+self.ttl,self.owner,ident,time.time()))
            except Exception:return # Fence will stop late writes if the lease expires.
    def once(self):
        with self.db() as c:
            live=self.reap(c);self.blocked=bool(live)
            if live:return False
            row=c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:return False
            ident=row['id'];c.execute("INSERT INTO worker_lease VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET owner=EXCLUDED.owner,expires=EXCLUDED.expires,job_id=EXCLUDED.job_id",('worker',self.owner,time.time()+self.ttl,ident))
            c.execute("UPDATE jobs SET state='running',updated=? WHERE id=?",(time.time(),ident))
        stop=threading.Event();heartbeat=threading.Thread(target=self.heartbeat,args=(ident,stop),daemon=True);heartbeat.start()
        value=None;error=None
        try:
            with database.job_scope(ident,self.owner):value=self.dispatch(row['operation'],row['lesson_id'],json.loads(row['payload']))
        except Exception as e:
            from fastapi import HTTPException
            error={'status':e.status_code,'detail':e.detail} if isinstance(e,HTTPException) else {'status':500,'detail':'Tác vụ không hoàn tất. Nguồn/bản nháp được giữ; kiểm tra trước khi thử lại.'}
        finally:stop.set();heartbeat.join(2)
        try:
            with database.job_scope(ident,self.owner),self.db() as c:
                c.execute('UPDATE jobs SET state=?,result=?,error=?,updated=? WHERE id=?',('failed' if error else 'succeeded',None if error else json.dumps(value,ensure_ascii=False),json.dumps(error,ensure_ascii=False) if error else None,time.time(),ident))
                c.execute("DELETE FROM worker_lease WHERE name='worker' AND owner=?",(self.owner,))
        except database.LeaseLost:pass # Another startup has already recorded the interrupted outcome.
        return True
    def get(self,ident):
        result=super().get(ident)
        if result['state'] in ('queued','running'):self.wake.set()
        return result
    def loop(self):
        while not self.stop.is_set():
            self.wake.clear()
            try:worked=self.once()
            except database.DatabaseUnavailable:
                self.wake.wait(30);continue
            if not worked:self.wake.wait(30 if self.blocked else None)
