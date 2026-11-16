"""Re-run only the 190 user-selected incomplete conditions, preserving baseline."""
import argparse,copy,hashlib,json
from expanded_engine import HERE,ROOT,OLD,Engine,credentials,freeze,readlines,save
from prepare import digest

def build():
    ROOT.mkdir(parents=True,exist_ok=True)
    baseline=readlines(OLD/'outputs.jsonl');assert len(baseline)==2700
    selected=[r for r in baseline if r['status']=='truncated' or r['status'] in ('transport_or_parse_error','incomplete_stream')]
    assert len(selected)==190
    jobs=[]
    for row in selected:
        req=copy.deepcopy(row['request'])
        if row['provider']=='deepseek':req['max_tokens']=24576
        elif row['provider']=='qwen':req['max_completion_tokens']=24576
        else:assert row['status']!='truncated' and req['max_completion_tokens']==8192
        meta={k:row[k] for k in ('case_number','source_id','provider','model','mode','method','variant_sha256')}
        jobs.append({'job_id':digest(['repair-expanded-v1',row['id'],req]),'original_id':row['id'],
                     'provider':row['provider'],'request':req,'meta':meta})
    freeze(ROOT/'repair_jobs.json',{'status':'user_authorized_repair','jobs':jobs,
       'original_outputs_sha256':hashlib.sha256((OLD/'outputs.jsonl').read_bytes()).hexdigest(),
       'selection':'8 OpenAI connection issues + 182 DeepSeek/Qwen length cutoffs; no other cells rerun',
       'runtime_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'expanded_engine.py',HERE/'repair_expanded.py')},
       'selection_policy':'latest completed attempt; network errors may retry at most three logged attempts; a second length cutoff at 24576 is retained, not silently enlarged'})
    return jobs,baseline
def merge(jobs,baseline):
    attempts=readlines(ROOT/'repair_attempts.jsonl');by={}
    for row in attempts:by[row['original_id']]=row
    assert set(by)<={job['original_id'] for job in jobs}
    merged=[]
    for original in baseline:
        if original['id'] not in by:merged.append(original);continue
        attempt=by[original['id']];new={k:v for k,v in original.items() if k not in ('content','reasoning_content','execution','usage','finish_reason','returned_model','response_id','request_id','system_fingerprint','error','error_type','http_status')}
        for key,value in attempt.items():
            if key not in ('meta','job_id','original_id','phase'):new[key]=value
        new.update(id=original['id'],repair_provenance={'original_status':original['status'],'original_request_sha256':original['request_sha256'],'selected_attempt_id':attempt['attempt_id'],'new_token_cap':attempt['request'].get('max_completion_tokens',attempt['request'].get('max_tokens'))})
        merged.append(new)
    assert len(merged)==2700 and len({r['id'] for r in merged})==2700
    (ROOT/'updated_outputs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in merged))
    from collections import Counter
    report={'conditions':2700,'selected_for_repair':190,'selected_with_attempts':len(by),
            'status_counts':dict(Counter(r['status'] for r in merged)),
            'still_unfinished':[r['id'] for r in merged if r.get('finish_reason')!='stop' or not r.get('content','').strip()],
            'generation_budget_policy':'Only originally truncated cells receive 24576; the other original cells remain at 8192. Results are adaptive-budget exploratory outputs.',
            'updated_outputs_sha256':hashlib.sha256((ROOT/'updated_outputs.jsonl').read_bytes()).hexdigest()}
    save(ROOT/'repair_merge_summary.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--build-only',action='store_true');parser.add_argument('--merge-only',action='store_true');args=parser.parse_args();jobs,baseline=build()
    if args.build_only:print('REPAIR_JOBS_READY',len(jobs))
    elif args.merge_only:merge(jobs,baseline)
    else:Engine('repair',credentials()).run(jobs);merge(jobs,baseline)
