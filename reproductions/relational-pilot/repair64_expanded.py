"""User-approved 65,536-token followup only for still-truncated records."""
import concurrent.futures as cf,copy,hashlib,json
from expanded_engine_long import HERE,ROOT,Engine,credentials,freeze,readlines,save
from prepare import digest

def build():
    snapshot=ROOT/'updated_outputs_24576.jsonl'
    if not snapshot.exists():snapshot.write_bytes((ROOT/'updated_outputs.jsonl').read_bytes())
    rows=readlines(snapshot);jobs=[]
    for row in rows:
        if row['status']!='truncated':continue
        assert row['provider'] in ('deepseek','qwen','openai')
        request=copy.deepcopy(row['request'])
        request['max_tokens' if row['provider']=='deepseek' else 'max_completion_tokens']=24576 if row['provider']=='openai' else 65536
        jobs.append({'job_id':digest(['repair-65536-v1',row['id'],request]),'original_id':row['id'],'provider':row['provider'],
                     'request':request,'meta':{k:row[k] for k in ('case_number','source_id','provider','model','mode','method','variant_sha256')}})
    freeze(ROOT/'repair64_jobs.json',{'jobs':jobs,'authorization':'User explicitly allowed 65536 for records still truncated at 24576.',
         'parent_snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),
         'engine_sha256':hashlib.sha256((HERE/'expanded_engine_long.py').read_bytes()).hexdigest()})
    return jobs

def finalize():
    original=readlines(ROOT/'updated_outputs_24576.jsonl');attempts=readlines(ROOT/'repair64_attempts.jsonl')
    by={}
    for row in attempts:by[row['original_id']]=row
    final=[]
    identity_fields=('id','case_number','source_id','severity_original','variant_sha256','provider','model','mode','method')
    for base in original:
        chosen=by.get(base['id'])
        if chosen and chosen['status'] in ('completed','execution_failed','truncated'):
            row={k:base[k] for k in identity_fields};row.update({k:v for k,v in chosen.items() if k not in ('meta','job_id','original_id','phase')})
            row['id']=base['id'];row['repair_provenance']={'parent_cap':base['request'].get('max_tokens',base['request'].get('max_completion_tokens')),
                 'parent_attempt_id':base.get('attempt_id'),'selected_attempt_id':chosen['attempt_id'],'stage':'65536'}
        else:row=copy.deepcopy(base)
        if row.get('started_utc'):row['started_at_utc']=row['started_utc']
        if 'stream_done' in row:row['stream_done_received']=row['stream_done']
        if row.get('finish_reason')=='stop':row.pop('may_have_been_billed',None)
        final.append(row)
    assert len(final)==2700 and len({r['id'] for r in final})==2700
    blob=''.join(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n' for row in final)
    path=ROOT/'effective_outputs_2700.jsonl'
    if path.exists():assert path.read_text()==blob,'Effective dataset is already frozen with different contents'
    else:path.write_text(blob)
    from collections import Counter
    report={'count':2700,'generation_status':dict(Counter(r['status'] for r in final)),
            'token_caps':dict(Counter(str(r['request'].get('max_tokens',r['request'].get('max_completion_tokens'))) for r in final)),
            'still_unfinished_ids':[r['id'] for r in final if r.get('finish_reason')!='stop' or not r.get('content','').strip()],
            'effective_outputs_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    save(ROOT/'effective_outputs_manifest.json',report);print(json.dumps(report),flush=True);return report

if __name__=='__main__':
    jobs=build()
    budget=json.loads((ROOT/'budget.json').read_text());budget.update(cumulative_budget_usd=None,unlimited=True);budget.pop('legacy_numeric_sentinel_note',None);save(ROOT/'budget.json',budget)
    if jobs:
        engine=Engine('repair64',credentials())
        def provider_run(provider):
            selected=[j for j in jobs if j['provider']==provider]
            with cf.ThreadPoolExecutor(max_workers=8) as pool:
                for _ in pool.map(lambda j:engine.worker(j,jobs,3),selected):pass
        active=sorted({job['provider'] for job in jobs})
        with cf.ThreadPoolExecutor(max_workers=len(active)) as pool:
            for _ in pool.map(provider_run,active):pass
        engine.status('complete',jobs)
    finalize()
