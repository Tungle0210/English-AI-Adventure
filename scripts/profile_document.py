"""Windows resource sample, never presented as a Render/Linux benchmark."""
import json,os,subprocess,time
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1]
code='''import sys,json,uuid\nfrom pathlib import Path\nfrom backend import main\np=Path('input/Unit 6 Lesson 2 Period 3.pptx')\nroot=Path('.cache/resource-probe')/uuid.uuid4().hex;root.mkdir(parents=True)\nd=main.read_document(p,media_root=root,render=False)\nprint(json.dumps({'platform':sys.platform,'bytes':p.stat().st_size,'sections':len(d['sections']),'assets':len(d['assets'])}))'''
env=dict(os.environ);env['ADVENTURE_CLOUD_ENABLE']='no'
start=time.monotonic();p=subprocess.Popen([str(ROOT/'backend/.venv/Scripts/python.exe'),'-c',code],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
proc=psutil.Process(p.pid);peak=0;cpu=0;cpu_by_pid={};seen=set()
while p.poll() is None:
 try:
  rss=0
  for child in [proc]+proc.children(recursive=True):
   try:
    seen.add(child.pid);rss+=child.memory_info().rss;t=child.cpu_times();cpu_by_pid[child.pid]=max(cpu_by_pid.get(child.pid,0),t.user+t.system)
   except psutil.Error:pass
  peak=max(peak,rss);cpu=sum(cpu_by_pid.values())
 except psutil.Error:pass
 time.sleep(.05)
out,err=p.communicate();result={'status':'PASS' if p.returncode==0 else 'FAIL','platform':'Windows local only','wall_seconds':round(time.monotonic()-start,2),'sampled_peak_rss_bytes':peak,'sampled_cpu_seconds':round(cpu,2),'monitored_processes':len(seen),'render_free_limit_compliance':'NOT_TESTED'}
if p.returncode==0:result.update(json.loads(out))
(ROOT/'reports/neon/resource-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
