"""Recheck source-only ambiguity flags; retain both machine opinions."""
import copy,json,random,threading
from expanded_engine_concurrent import ROOT,Engine,credentials,freeze,readlines,save
from answerability_expanded import GUIDE
from judge_expanded import normalized,strings
from prepare import digest

def source_quote_issues(annotation,view):
    if not annotation:return ['missing_annotation']
    raw=normalized(json.dumps(view,ensure_ascii=False));decoded=normalized('\n'.join(strings(view)))
    return ['source_quote_not_found'] if any(normalized(q) not in raw and normalized(q) not in decoded for q in annotation['evidence_quotes'] if q) else []

def main():
    initial=json.loads((ROOT/'source_answerability.json').read_text());lookup={j['original_id']:j for j in json.loads((ROOT/'answerability_jobs.json').read_text())['jobs']}
    random_ids=set(random.Random(20261118).sample(sorted(lookup),5));jobs=[]
    for item in initial['items']:
        job=lookup[item['source_id']];view=json.loads(job['request']['messages'][1]['content']);a=item['annotation'];flags=source_quote_issues(a,view)
        if a and a['answerability']=='insufficient' and a['confidence']!='low' and not flags and item['source_id'] not in random_ids:continue
        request=copy.deepcopy(job['request']);request['max_completion_tokens']=16384
        request['messages'][0]['content']+='\nRECHECK: A prior machine opinion is fallible. Match every entity, segment/region, period and requested aggregation scope. In a balance reconciliation, additions/deductions between two ending balances belong to the interval ending at the FOLLOWING balance. A single-year amount is not a total over multiple years; an overall segment value is not automatically a regional value. If the question is genuinely underspecified, report uncertainty, not an invisible gold interpretation. Recompute any claimed sufficient derivation and examine whether it actually answers the stated question. Return the same schema.'
        payload={'question_and_evidence':view}
        if item['source_id'] not in random_ids:payload['fallible_prior_opinion']=a;payload['quote_validation_flags']=flags
        request['messages'][1]['content']=json.dumps(payload,ensure_ascii=False)
        jobs.append({'job_id':digest(['source-review-v1',item['source_id'],request]),'original_id':item['source_id'],
                     'provider':'openai','request':request,'meta':{'case_number':item['case_number']}})
    freeze(ROOT/'source_review_jobs.json',{'jobs':jobs,'random_diagnostic_ids':sorted(random_ids),'random_seed':20261118})
    engine=Engine('source_review',credentials());engine.semaphores['openai']=threading.Semaphore(4);engine.run(jobs,workers=4,max_attempts=3)
    latest={r['original_id']:r for r in readlines(ROOT/'source_review_attempts.jsonl')};jobindex={j['original_id']:j for j in jobs};changed=[]
    backup=ROOT/'source_answerability_initial.json'
    if not backup.exists():save(backup,initial)
    for item in initial['items']:
        prior=item['annotation'];view=json.loads(lookup[item['source_id']]['request']['messages'][1]['content']);flags=source_quote_issues(prior,view)
        row=latest.get(item['source_id'])
        if row and row['status']=='completed':
            try:review=json.loads(row['content']);errors=source_quote_issues(review,view)
            except (ValueError,KeyError):review=None;errors=['invalid_source_review']
            item['initial_annotation']=prior;item['internal_review_annotation']=review;item['internal_review_attempt_id']=row['attempt_id']
            if review and not errors:
                if not prior or prior['answerability']!=review['answerability']:changed.append(item['case_number'])
                item['annotation']=review;flags=[]
            else:flags+=errors
        item['validation_issues']=flags
    initial.update(internal_machine_recheck_count=len(jobs),changed_answerability_cases=changed,
                   interpretation='Diagnostic machine opinions only, not independent human answerability certificates; no source questions are changed or removed.')
    save(ROOT/'source_answerability.json',initial)
    print('SOURCE_REVIEW_COMPLETE',len(jobs),'changed',changed,flush=True)

if __name__=='__main__':main()
