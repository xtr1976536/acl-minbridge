"""Explicit opt-in model API calls; credentials never enter result records."""
import datetime as dt,getpass,hashlib,json,os,time,urllib.error,urllib.request
from pathlib import Path

ENV={'openai':'OPENAI_API_KEY','deepseek':'DEEPSEEK_API_KEY','qwen':'DASHSCOPE_API_KEY'}
BASE={'openai':'https://api.openai.com/v1','deepseek':'https://api.deepseek.com','qwen':'https://dashscope.aliyuncs.com/compatible-mode/v1'}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def load_keys(providers):
    return {p:os.environ.get(ENV[p]) or getpass.getpass(ENV[p]+': ') for p in providers}
def safe(value,keys):
    s=json.dumps(value,ensure_ascii=False,default=str)
    for key in keys.values():
        if key:s=s.replace(key,'[REDACTED]')
    return json.loads(s)
def submit(job,keys,out):
    # This is a new run. Existing published results are never overwritten.
    request=job['request'];provider=job['provider'];ident=job['id']
    pending=out/(ident+'.pending.json');assert not pending.exists(),'Unresolved previous API submission'
    pending.write_text(json.dumps({'id':ident,'request_sha256':hashlib.sha256(json.dumps(request,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}))
    row={'id':ident,'provider':provider,'request':request,'content':'','reasoning_content':'','usage':None,
         'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'finish_reason':None,'returned_model':None}
    start=time.monotonic()
    try:
        req=urllib.request.Request(BASE[provider]+'/chat/completions',data=json.dumps(request).encode(),
            headers={'Authorization':'Bearer '+keys[provider],'Content-Type':'application/json'})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=180) as response:
            row['http_status']=response.status
            for line in response:
                line=line.decode().strip()
                if not line.startswith('data:'):continue
                value=line[5:].strip()
                if value=='[DONE]':break
                chunk=json.loads(value)
                if chunk.get('error'):row['provider_error']=safe(chunk['error'],keys);break
                row['returned_model']=chunk.get('model') or row['returned_model'];row['usage']=chunk.get('usage') or row['usage']
                for choice in chunk.get('choices',[]):
                    d=choice.get('delta',{});row['content']+=d.get('content') or '';row['reasoning_content']+=d.get('reasoning_content') or ''
                    row['finish_reason']=choice.get('finish_reason') or row['finish_reason']
        row['status']='provider_error' if row.get('provider_error') else 'truncated' if row['finish_reason']=='length' else 'completed' if row['finish_reason']=='stop' and row['content'].strip() else 'incomplete'
    except urllib.error.HTTPError as exc:
        row.update(status='api_error',http_status=exc.code,error=safe(exc.read().decode('utf-8','replace'),keys))
    except Exception as exc:row.update(status='transport_error',error_type=type(exc).__name__,error=safe(str(exc),keys),billing_uncertain=True)
    row['seconds']=round(time.monotonic()-start,3);row=safe(row,keys)
    with (out/'outputs.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    pending.unlink()
    print(json.dumps({'id':ident,'status':row['status']}),flush=True)
    # A policy or quota rejection is terminal here, never bypassed/retried.
    if row['status'] in ('api_error','provider_error','transport_error','incomplete'):raise RuntimeError('API request did not finish; inspect the saved sanitized record before proceeding')
    return row
