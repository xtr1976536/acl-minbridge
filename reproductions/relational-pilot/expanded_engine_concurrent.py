"""Append-only API attempts, bounded retries, non-echoed credentials and total budget."""
import concurrent.futures as cf
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import termios
import threading
import time
import urllib.error
import urllib.request
from prepare import digest
from pot_runtime import execute_pot

HERE=Path(__file__).resolve().parent
ROOT=HERE/'local/runs/english150-20261116-expanded'
OLD=HERE/'local/runs/english150-20261116-v2'
PROVIDERS={
 'openai':{'base':'https://api.openai.com/v1','model':'gpt-5.6-sol','rates':[5.,20.]},
 'deepseek':{'base':'https://api.deepseek.com','model':'deepseek-v4-pro','rates':[1.32,3.96]},
 'qwen':{'base':'https://dashscope.aliyuncs.com/compatible-mode/v1','model':'qwen3.8-27b','rates':[.5,3.]}}
NETWORK={'transport_error','incomplete_stream','empty','api_error'}

def save(path,obj):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));temp.replace(path)
def readlines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
def freeze(path,obj):
    if path.exists():assert json.loads(path.read_text())==obj,'Frozen file drift: '+path.name
    else:save(path,obj)
def credentials():
    previous=termios.tcgetattr(sys.stdin);hidden=list(previous);hidden[3]&=~termios.ECHO
    termios.tcsetattr(sys.stdin,termios.TCSANOW,hidden)
    print('READY_FOR_PRIVATE_STDIN',flush=True)
    try:return json.loads(sys.stdin.readline())
    finally:termios.tcsetattr(sys.stdin,termios.TCSANOW,previous)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class Engine:
    def __init__(self,phase,keys):
        ROOT.mkdir(parents=True,exist_ok=True);self.phase=phase;self.keys=keys;self.lock=threading.RLock()
        self.path=ROOT/(phase+'_attempts.jsonl');self.rows=readlines(self.path)
        self.spent=json.loads((OLD/'progress.json').read_text())['cost_upper_estimate_usd']
        for f in ROOT.glob('*_attempts.jsonl'):self.spent+=sum(r['cost_upper_estimate_usd'] for r in readlines(f))
        self.reserved=0.;self.halted={};self.stop=False
        self.semaphores={p:threading.Semaphore(2 if p=='openai' else 8) for p in PROVIDERS}
        if any(json.loads(f.read_text()).get('phase')==phase for f in ROOT.glob('*.pending.json')):raise RuntimeError('Unreconciled pending API call in this phase: inspect partial records before resuming')
        if not (ROOT/'budget.json').exists():save(ROOT/'budget.json',{'cumulative_budget_usd':100,'includes_prior_cost_usd':self.spent,'authorization':'Previous user cap; higher cap requires explicit user reply.'})
    def clean(self,obj):
        text=json.dumps(obj,ensure_ascii=False,default=str)
        for key in self.keys.values():
            if key:text=text.replace(key,'[REDACTED]')
        return json.loads(text)
    def status(self,state,jobs):
        latest={r['job_id']:r for r in self.rows};counts=collections.Counter(r['status'] for r in latest.values())
        obj={'phase':self.phase,'state':state,'jobs_with_records':len(latest),'planned_jobs':len(jobs),
             'attempts':len(self.rows),'status_counts':dict(counts),'cumulative_cost_upper_usd':round(self.spent,6),
             'inflight_reserved_usd':round(self.reserved,6),'budget':json.loads((ROOT/'budget.json').read_text()),
             'halted':self.halted,'updated_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
        save(ROOT/(self.phase+'_progress.json'),obj);return obj
    def one(self,job,number,jobs):
        provider=job['provider'];request=job['request'];rates=PROVIDERS[provider]['rates']
        cap=request.get('max_completion_tokens',request.get('max_tokens'))
        reserve=((len(json.dumps(request,ensure_ascii=False).encode())+4096)*rates[0]+(cap+16)*rates[1])/1e6
        attempt_id=digest([job['job_id'],number]);pending=ROOT/(attempt_id+'.pending.json');partial=ROOT/(attempt_id+'.partial.json')
        with self.lock:
            budget=json.loads((ROOT/'budget.json').read_text())['cumulative_budget_usd']
            if self.stop or provider in self.halted:return None
            if budget is not None and self.spent+self.reserved+reserve>budget:
                self.stop=True;self.status('budget_paused',jobs);return None
            self.reserved+=reserve
            save(pending,{'phase':self.phase,'job_id':job['job_id'],'attempt_id':attempt_id,'request_sha256':digest(request),'reserved_usd':reserve})
        row={'phase':self.phase,'job_id':job['job_id'],'attempt_id':attempt_id,'attempt_number':number,
             'provider':provider,'original_id':job.get('original_id'),'request':request,'request_sha256':digest(request),
             'content':'','reasoning_content':'','usage':None,'finish_reason':None,'returned_model':None,
             'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'meta':job.get('meta',{})}
        started=time.monotonic();saved=started;done=False
        try:
            req=urllib.request.Request(PROVIDERS[provider]['base']+'/chat/completions',data=json.dumps(request).encode(),
                 headers={'Authorization':'Bearer '+self.keys[provider],'Content-Type':'application/json'})
            with urllib.request.build_opener(NoRedirect).open(req,timeout=180) as response:
                row['http_status']=response.status;row['request_id']=response.headers.get('x-request-id')
                for line in response:
                    if time.monotonic()-started>5400:raise TimeoutError('Overall API deadline 5400 seconds')
                    line=line.decode('utf-8').strip()
                    if not line.startswith('data:'):continue
                    text=line[5:].strip()
                    if text=='[DONE]':done=True;break
                    chunk=json.loads(text)
                    if chunk.get('error'):raise ValueError(str(self.clean(chunk['error'])))
                    for key in ('id','model','system_fingerprint'):
                        if chunk.get(key):row[{'id':'response_id','model':'returned_model'}.get(key,key)]=chunk[key]
                    row['usage']=chunk.get('usage') or row['usage']
                    for choice in chunk.get('choices',[]):
                        delta=choice.get('delta',{});row['content']+=delta.get('content') or '';row['reasoning_content']+=delta.get('reasoning_content') or ''
                        row['finish_reason']=choice.get('finish_reason') or row['finish_reason']
                    if time.monotonic()-saved>15:
                        save(partial,self.clean(row));saved=time.monotonic()
            finish=row['finish_reason'];row['status']='truncated' if finish=='length' else 'completed' if finish=='stop' and row['content'].strip() else 'empty' if finish=='stop' else 'incomplete_stream'
            if row['returned_model']!=request['model']:row['status']='model_mismatch';self.halted[provider]='model_mismatch'
            if self.phase in ('repair','repair64') and job['meta']['method']=='pot' and row['status']=='completed':
                row['execution']=execute_pot(row['content'],20)
                if row['execution'].get('status')!='executed':row['status']='execution_failed'
        except urllib.error.HTTPError as exc:
            row.update(status='api_error',http_status=exc.code,error=self.clean(exc.read().decode('utf-8','replace'))[:2500])
            if exc.code in (400,401,402,403,404):self.halted[provider]='HTTP '+str(exc.code)
        except Exception as exc:
            row.update(status='transport_error',error_type=type(exc).__name__,error=self.clean(str(exc))[:1800],may_have_been_billed=True)
        usage=row.get('usage') or {}
        if isinstance(usage.get('prompt_tokens'),int) and isinstance(usage.get('completion_tokens'),int):cost=(usage['prompt_tokens']*rates[0]+usage['completion_tokens']*rates[1])/1e6
        elif row.get('http_status') in (400,401,402,403,404,429):cost=0.
        else:cost=reserve
        row.update(seconds=round(time.monotonic()-started,3),cost_upper_estimate_usd=cost,stream_done=done)
        row=self.clean(row)
        with self.lock:
            self.spent+=cost;self.reserved-=reserve
            with self.path.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
            self.rows.append(row);pending.unlink();partial.unlink(missing_ok=True)
            status=self.status('running',jobs)
            if len(self.rows)%5==0 or row['status'] in NETWORK:
                print(json.dumps({k:status[k] for k in ('phase','jobs_with_records','planned_jobs','attempts','status_counts','cumulative_cost_upper_usd','halted')}),flush=True)
        return row
    def worker(self,job,jobs,max_attempts):
        with self.semaphores[job['provider']]:
            previous=sorted([r for r in self.rows if r['job_id']==job['job_id']],key=lambda r:r['attempt_number'])
            if previous and previous[-1]['status'] not in NETWORK:return
            for number in range(len(previous)+1,max_attempts+1):
                if previous or number>1:time.sleep(5)
                row=self.one(job,number,jobs)
                if row is None or row['status'] not in NETWORK:return
                previous.append(row)
    def run(self,jobs,workers=18,max_attempts=3):
        assert len({j['job_id'] for j in jobs})==len(jobs)
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            for _ in pool.map(lambda job:self.worker(job,jobs,max_attempts),jobs):pass
        latest={r['job_id']:r for r in self.rows}
        state='complete' if len(latest)==len(jobs) and not self.stop and not self.halted else 'needs_review'
        with self.lock:result=self.status(state,jobs)
        print(json.dumps(result),flush=True);return result
