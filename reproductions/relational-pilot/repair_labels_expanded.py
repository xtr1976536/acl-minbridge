"""Targeted repair of mechanically invalid annotations; preserve all prior labels."""
import json,threading
from expanded_engine_evaluation import ROOT,Engine,credentials,freeze,readlines,save
from judge_expanded import judge_request
from judging_validation import validate_annotation
from prepare import digest

def build():
    annotations=readlines(ROOT/'machine_annotations_final.jsonl');jobs={j['original_id']:j for j in json.loads((ROOT/'judge_jobs.json').read_text())['jobs']};selected=[]
    for item in annotations:
        if not item['validation_issues'] or item.get('provider_content_rejection'):continue
        payload=json.loads(jobs[item['id']]['request']['messages'][1]['content']);payload['fallible_annotation']=item['annotation'];payload['mechanical_problems_to_resolve']=item['validation_issues']
        request=judge_request(payload,effort='medium',cap=16384)
        request['messages'][0]['content']+='\nVALIDATION REPAIR: Reassess truth from the original evidence. Resolve invalid quotations by copying exact original substrings, not paraphrases. Resolve label contradictions honestly, not by fabricating witnesses or forcing a desired category. If genuinely uncertain, report low confidence. A valid conditional can decline to assert an actual value; distinguish its response category from pure refusal. Do not change an uncertain factual issue into a confident claim just to satisfy mechanical checks.'
        selected.append({'job_id':digest(['label-validation-repair-v1',item['id'],request]),'original_id':item['id'],'provider':'openai',
                         'request':request,'meta':{'prior_validation_issues':item['validation_issues']}})
    freeze(ROOT/'label_repair_jobs.json',{'jobs':selected,'purpose':'Mechanical quote/label consistency repair only; prior opinions remain archived.'})
    return selected

def finish():
    path=ROOT/'machine_annotations_final.jsonl';backup=ROOT/'machine_annotations_final.before_validation_repair.jsonl'
    if not backup.exists():backup.write_bytes(path.read_bytes())
    annotations=readlines(path);jobs={j['original_id']:j for j in json.loads((ROOT/'label_repair_jobs.json').read_text())['jobs']};latest={r['job_id']:r for r in readlines(ROOT/'label_repair_attempts.jsonl')};resolved=[];unresolved=[]
    for item in annotations:
        job=jobs.get(item['id'])
        if not job:continue
        row=latest.get(job['job_id']);a=None;problems=['label_repair_missing_or_unavailable']
        if row and row['status']=='completed':
            try:a=json.loads(row['content']);problems=validate_annotation(a,json.loads(job['request']['messages'][1]['content']))
            except (ValueError,KeyError,TypeError):problems=['invalid_label_repair_json']
        item['validation_repair']={'attempt_id':row['attempt_id'] if row else None,'validation_issues':problems,'previous_annotation_preserved_in':backup.name}
        if a and not problems:
            item.update(annotation=a,validation_issues=[],selected_annotation_source='validation_repair',review_unresolved=False);resolved.append(item['id'])
        else:unresolved.append(item['id'])
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in annotations));save(ROOT/'label_repair_summary.json',{'selected':len(jobs),'resolved':len(resolved),'unresolved':len(unresolved),'resolved_ids':resolved,'unresolved_ids':unresolved})
    print('LABEL_REPAIR_FINISHED',len(resolved),'resolved;',len(unresolved),'unresolved',flush=True)

if __name__=='__main__':
    jobs=build()
    if jobs:
        engine=Engine('label_repair',credentials());engine.semaphores['openai']=threading.Semaphore(8);engine.run(jobs,workers=8,max_attempts=2)
    finish()
