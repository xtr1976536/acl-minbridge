"""English exploratory pilot. Secrets enter through non-echoed stdin, never files."""
from __future__ import annotations
import argparse
import concurrent.futures as futures
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import termios
import threading
import time
import urllib.error
import urllib.request

from prepare import digest
from prompts import METHODS, messages
from run import execute_pot

HERE=Path(__file__).resolve().parent
OUT=HERE/'local/runs/english150-20261116-v2'
MAX_TOKENS=8192
BUDGET=100.0
INITIAL_ALLOWANCE_USD=0.11046299999999999
PROVIDERS={
 'openai':{'base':'https://api.openai.com/v1','model':'gpt-5.6-sol','rates':[5.0,20.0]},
 'deepseek':{'base':'https://api.deepseek.com','model':'deepseek-v4-pro','rates':[1.32,3.96]},
 'qwen':{'base':'https://dashscope.aliyuncs.com/compatible-mode/v1','model':'qwen3.8-27b','rates':[0.5,3.0]},
}

def write_json(path,value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2))
    temp.replace(path)

def request_for(task):
    family,mode=task['provider'],task['mode']
    req={'model':PROVIDERS[family]['model'],'messages':task['messages'],
         'stream':True,'stream_options':{'include_usage':True}}
    if family=='openai': req.update(max_completion_tokens=MAX_TOKENS,reasoning_effort=mode,store=False)
    elif family=='deepseek':
        req.update(max_tokens=MAX_TOKENS,thinking={'type':'disabled' if mode=='low' else 'enabled'})
        if mode=='high':req['reasoning_effort']='high'
    else:req.update(max_completion_tokens=MAX_TOKENS,enable_thinking=mode=='high')
    return req

def build():
    data_path=HERE/'v2/final_150_review.json'
    exported=HERE.parents[1]/'output/data/MinBridge_150_MODEL_INPUTS_仅英文删后材料.json'
    records=json.loads(data_path.read_text())['records']
    views=json.loads(exported.read_text())['drafts']
    assert len(records)==len(views)==150
    assert len({r['source_id'] for r in records})==150
    tasks=[]
    for row,view in zip(records,views):
        visible=row['modified']
        assert set(visible)=={'question','pre_text','post_text','table'}
        assert visible==view['visible'] and digest(visible)==row['modified_sha256']==view['variant_sha256']
        assert not re.search(r'[\u3400-\u9fff]',json.dumps(visible,ensure_ascii=False))
        for family in PROVIDERS:
            for mode in ('low','high'):
                for method in METHODS:
                    task={'case_number':row['number'],'source_id':row['source_id'],
                          'severity_original':row['severity'],'variant_sha256':row['modified_sha256'],
                          'provider':family,'model':PROVIDERS[family]['model'],'mode':mode,'method':method,
                          'messages':messages(method,visible)}
                    task['id']=digest({k:v for k,v in task.items() if k!='messages'})
                    task['request_sha256']=digest(request_for(task))
                    tasks.append(task)
    assert len(tasks)==len({t['id'] for t in tasks})==2700
    bundle={'status':'exploratory_human_review_pending','source_count':150,'task_count':2700,
            'source_sha256':hashlib.sha256(data_path.read_bytes()).hexdigest(),
            'english_export_sha256':hashlib.sha256(exported.read_bytes()).hexdigest(),'tasks':tasks}
    config={'providers':PROVIDERS,'output_token_limit':MAX_TOKENS,'budget_upper_bound_usd':BUDGET,
            'initial_probe_allowance_usd':INITIAL_ALLOWANCE_USD,'requests_per_design_cell':1,
            'modes':{'openai':{'low':'reasoning_effort=low','high':'reasoning_effort=high'},
                     'deepseek':{'low':'thinking disabled','high':'thinking enabled; reasoning_effort=high'},
                     'qwen':{'low':'enable_thinking=false','high':'enable_thinking=true'}},
            'qwen_budget_correction':'max_completion_tokens limits reasoning plus answer; verified with a forced 64-token truncated calibration. Prior six Qwen calibration calls excluded; unchanged twelve OpenAI/DeepSeek outputs carried forward.',
            'budget_accounting':'Conservative undiscounted usage estimates; upper reservation before dispatch; no exchange rate required. OpenAI input includes 25% cache-write reserve. Qwen rates exceed Beijing list rates. No retries.',
            'notes':['No cross-question history, tools, retrieval, original evidence, gold answers or review explanations are sent.',
                     'Q2 fact-count correction is recorded separately in v3_cn/data_count_errata.json; unchanged English inputs and original severity labels retained.',
                     'Provider-exposed reasoning_content is saved when available. OpenAI hidden reasoning is not exposed; requested visible explanations/code remain available.',
                     'Model aliases are user-specified, not claimed to be immutable weight snapshots.'],
            'documentation':[
             'https://developers.openai.com/api/docs/models/gpt-5.6-sol',
             'https://api-docs.deepseek.com/guides/thinking_mode/',
             'https://api-docs.deepseek.com/quick_start/pricing/',
             'https://www.alibabacloud.com/help/en/model-studio/deep-thinking',
             'https://www.alibabacloud.com/help/en/model-studio/model-pricing']}
    OUT.mkdir(parents=True,exist_ok=True)
    for name,value in [('tasks.json',bundle),('config.json',config)]:
        path=OUT/name
        if path.exists(): assert json.loads(path.read_text())==value, 'Run configuration changed'
        else: write_json(path,value)
    identity={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'prompts.py',HERE/'run.py',OUT/'tasks.json',OUT/'config.json']}
    path=OUT/'identity.json'
    if path.exists():assert json.loads(path.read_text())==identity,'Runtime changed; use a different run directory'
    else:write_json(path,identity)
    return tasks

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class Runner:
    def __init__(self,keys,tasks):
        self.keys=keys;self.tasks=tasks;self.lock=threading.Lock();self.reserved=0
        self.spent=INITIAL_ALLOWANCE_USD;self.halted={};self.results=[];self.done=set()
        self.output=OUT/'outputs.jsonl'
        if self.output.exists():
            for line in self.output.read_text().splitlines():
                r=json.loads(line);assert r['id'] not in self.done
                self.results.append(r);self.done.add(r['id']);self.spent+=r['cost_upper_estimate_usd']
        assert self.done<={t['id'] for t in tasks}
        if list(OUT.glob('*.pending.json')):raise RuntimeError('Unresolved interrupted request; inspect before resuming')
    def clean(self,value):
        s=json.dumps(value,ensure_ascii=False,default=str)
        for key in self.keys.values():s=s.replace(key,'[REDACTED]')
        return json.loads(s)
    def summary(self,state):
        groups=collections.defaultdict(collections.Counter)
        for r in self.results:groups['/'.join([r['provider'],r['mode'],r['method']])][r['status']]+=1
        return {'state':state,'updated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                'completed_requests':len(self.results),'planned_requests':len(self.tasks),
                'status_counts':dict(collections.Counter(r['status'] for r in self.results)),
                'cost_upper_estimate_usd':round(self.spent,6),'inflight_reserved_usd':round(self.reserved,6),
                'budget_usd':BUDGET,'halted_providers':self.halted,'conditions':{k:dict(v) for k,v in groups.items()}}
    def save_summary(self,state):write_json(OUT/'progress.json',self.summary(state))
    def call(self,task):
        family=task['provider'];req=request_for(task);rates=PROVIDERS[family]['rates']
        # UTF-8 byte count plus ample message framing is a conservative token bound.
        input_bound=len(json.dumps(req['messages'],ensure_ascii=False).encode())+4096
        reserve=(input_bound*rates[0]+(MAX_TOKENS+16)*rates[1])/1e6
        with self.lock:
            if task['id'] in self.done or family in self.halted:return
            if self.spent+self.reserved+reserve>BUDGET:
                self.halted[family]='budget_reservation_limit';self.save_summary('budget_paused');return
            self.reserved+=reserve
            pending=OUT/(task['id']+'.pending.json')
            write_json(pending,{'id':task['id'],'request_sha256':task['request_sha256']})
        record={k:v for k,v in task.items() if k!='messages'}
        record.update(request=req,content='',reasoning_content='',finish_reason=None,usage=None,
                      returned_model=None,response_id=None,system_fingerprint=None,
                      started_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        started=time.monotonic();done_event=False;fatal=None
        try:
            request=urllib.request.Request(PROVIDERS[family]['base']+'/chat/completions',
                       data=json.dumps(req).encode(),headers={'Authorization':'Bearer '+self.keys[family],
                       'Content-Type':'application/json'})
            with urllib.request.build_opener(NoRedirect).open(request,timeout=180) as response:
                record['http_status']=response.status
                record['request_id']=response.headers.get('x-request-id')
                for line in response:
                    if time.monotonic()-started>600:raise TimeoutError('Overall request duration exceeded 600 seconds')
                    line=line.decode('utf-8').strip()
                    if not line.startswith('data:'):continue
                    line=line[5:].strip()
                    if line=='[DONE]':done_event=True;break
                    chunk=json.loads(line)
                    if chunk.get('error'):raise ValueError(self.clean(chunk['error']))
                    record['returned_model']=chunk.get('model') or record['returned_model']
                    record['response_id']=chunk.get('id') or record['response_id']
                    record['system_fingerprint']=chunk.get('system_fingerprint') or record['system_fingerprint']
                    record['usage']=chunk.get('usage') or record['usage']
                    for choice in chunk.get('choices',[]):
                        delta=choice.get('delta',{})
                        record['content']+=delta.get('content') or ''
                        record['reasoning_content']+=delta.get('reasoning_content') or ''
                        record['finish_reason']=choice.get('finish_reason') or record['finish_reason']
            finish=record['finish_reason']
            record['status']='truncated' if finish=='length' else 'completed' if finish=='stop' and record['content'].strip() else 'empty' if finish=='stop' else 'incomplete_stream'
            if record['returned_model']!=task['model']:
                record['status']='model_mismatch';fatal='returned model differs from requested model'
            if not record['usage']:
                fatal='usage missing; reconcile billing before continuing'
            if task['method']=='pot' and record['status']=='completed':
                record['execution']=execute_pot(record['content'],20)
                if record['execution'].get('status')!='executed':record['status']='execution_failed'
        except urllib.error.HTTPError as exc:
            record.update(status='api_error',http_status=exc.code,error=self.clean(exc.read().decode('utf-8','replace'))[:2000])
            fatal='HTTP '+str(exc.code)+'; no automatic retries'
        except Exception as exc:
            record.update(status='transport_or_parse_error',error_type=type(exc).__name__,error=self.clean(str(exc))[:2000],may_have_been_billed=True)
            fatal='uncertain or interrupted response; no automatic retries'
        usage=record.get('usage') or {}
        if isinstance(usage.get('prompt_tokens'),int) and isinstance(usage.get('completion_tokens'),int):
            cost=(usage['prompt_tokens']*rates[0]+usage['completion_tokens']*rates[1])/1e6
        elif record.get('http_status') in (400,401,402,403,404,429):cost=0.0
        else:cost=reserve
        record.update(seconds=round(time.monotonic()-started,3),stream_done_received=done_event,
                      cost_upper_estimate_usd=cost,billing_confirmed_by_invoice=False)
        record=self.clean(record)
        with self.lock:
            self.reserved-=reserve;self.spent+=cost
            with self.output.open('a') as file:
                file.write(json.dumps(record,ensure_ascii=False)+'\n');file.flush();os.fsync(file.fileno())
            self.results.append(record);self.done.add(task['id']);pending.unlink()
            if fatal:self.halted[family]=fatal
            self.save_summary('running')
            if len(self.results)%18==0 or fatal:
                print(json.dumps({'completed':len(self.results),'last_provider':family,'last_status':record['status'],
                                  'cost_upper_usd':round(self.spent,4),'halted':self.halted}),flush=True)
    def stage(self,tasks,workers):
        # A fixed small pool bounds concurrency and all in-flight cost reservations.
        with futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(self.call,tasks):pass

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--build-only',action='store_true');args=parser.parse_args()
    tasks=build()
    if args.build_only:
        print(json.dumps({'tasks':len(tasks),'path':str(OUT),'input_checks':'passed'}));return
    check=execute_pot('ans = 12 / 261',20)
    if check.get('status')!='executed':raise RuntimeError('PoT runtime preflight failed: '+str(check))
    old=termios.tcgetattr(sys.stdin);hidden=list(old);hidden[3]&=~termios.ECHO
    termios.tcsetattr(sys.stdin,termios.TCSANOW,hidden)
    print('READY_FOR_PRIVATE_STDIN',flush=True)
    try:
        keys=json.loads(sys.stdin.readline());assert set(keys)==set(PROVIDERS)
        runner=Runner(keys,tasks)
        # All 18 conditions on the same first question precede the full batch.
        runner.stage([t for t in tasks if t['case_number']==1],6)
        initial=[r for r in runner.results if r['case_number']==1]
        if len(initial)!=18 or runner.halted or any(r['status'] not in ('completed','execution_failed','truncated') for r in initial):
            runner.save_summary('preflight_needs_review');print(json.dumps(runner.summary('preflight_needs_review')));return
        runner.save_summary('preflight_passed')
        print('BENCHMARK_PREFLIGHT_PASSED; continuing all remaining tasks',flush=True)
        runner.stage([t for t in tasks if t['case_number']!=1],36)
        state='complete' if len(runner.done)==len(tasks) else 'paused_needs_review'
        runner.save_summary(state);print(json.dumps(runner.summary(state)),flush=True)
    finally:termios.tcsetattr(sys.stdin,termios.TCSANOW,old)

if __name__=='__main__':main()
