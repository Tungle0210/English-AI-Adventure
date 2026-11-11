"""Single-process durable queue. Never automatically retry an uncertain AI call."""
import hashlib,json,threading,time,uuid
from fastapi import HTTPException

class Queue:
    def __init__(self,db,dispatch):
        self.db,self.dispatch=db,dispatch
        self.stop=threading.Event();self.wake=threading.Event()
        self.thread=None

    def initialize(self):
        with self.db() as c:
            from .schema import QUEUE
            c.executescript(QUEUE)
            c.execute("UPDATE jobs SET state='interrupted',error=?,updated=? WHERE state='running'",(json.dumps({'status':409,'detail':'Máy chủ khởi động lại khi tác vụ đang chạy. Kiểm tra bản nháp trước khi gửi lại; hệ thống không tự gọi AI lần nữa.'}),time.time()))

    def start(self):
        self.initialize()
        self.thread=threading.Thread(target=self.loop,name='adventure-jobs',daemon=True);self.thread.start()

    def close(self):
        self.stop.set();self.wake.set()
        if self.thread:self.thread.join(timeout=120)

    def submit(self,operation,lesson_id,payload,key):
        if not key or len(key)>100:raise HTTPException(422,'Cần Idempotency-Key tối đa 100 ký tự.')
        body=json.dumps(payload,sort_keys=True,ensure_ascii=False)
        fingerprint=hashlib.sha256((operation+lesson_id+body).encode()).hexdigest()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
            if old:
                if old['fingerprint']!=fingerprint:raise HTTPException(409,'Idempotency-Key đã dùng cho dữ liệu khác.')
                return {'job_id':old['id'],'state':old['state']}
            active=c.execute("SELECT * FROM jobs WHERE lesson_id=? AND state IN ('queued','running')",(lesson_id,)).fetchone()
            if active:
                if active['fingerprint']==fingerprint:return {'job_id':active['id'],'state':active['state']}
                raise HTTPException(409,'Bài này đang có tác vụ. Chờ hoàn tất trước khi gửi tác vụ khác.')
            if c.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]>=20:raise HTTPException(429,'Hàng đợi đầy. Không gửi thêm yêu cầu.')
            ident=uuid.uuid4().hex;stamp=time.time()
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,operation,lesson_id,body,fingerprint,key,'queued',None,None,stamp,stamp))
        self.wake.set()
        return {'job_id':ident,'state':'queued'}

    def get(self,ident):
        with self.db() as c:row=c.execute('SELECT id,state,result,error FROM jobs WHERE id=?',(ident,)).fetchone()
        if not row:raise HTTPException(404,'Không tìm thấy tác vụ.')
        result={'job_id':row['id'],'state':row['state']}
        if row['result']:result['result']=json.loads(row['result'])
        if row['error']:result['error']=json.loads(row['error'])
        return result

    def once(self):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:return False
            c.execute("UPDATE jobs SET state='running',updated=? WHERE id=?",(time.time(),row['id']))
        try:
            value=self.dispatch(row['operation'],row['lesson_id'],json.loads(row['payload']))
            # The result and source data stay on the private disk, never in access logs.
            with self.db() as c:c.execute("UPDATE jobs SET state='succeeded',result=?,updated=? WHERE id=?",(json.dumps(value,ensure_ascii=False),time.time(),row['id']))
        except Exception as error:
            safe={'status':error.status_code,'detail':error.detail} if isinstance(error,HTTPException) else {'status':500,'detail':'Tác vụ lỗi nội bộ; bản nháp được giữ. Kiểm tra máy chủ trước khi thử lại.'}
            with self.db() as c:c.execute("UPDATE jobs SET state='failed',error=?,updated=? WHERE id=?",(json.dumps(safe,ensure_ascii=False),time.time(),row['id']))
        return True

    def loop(self):
        while not self.stop.is_set():
            if not self.once():self.wake.wait(1);self.wake.clear()
