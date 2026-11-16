"""Run ONLY after the user confirms API credits are restored."""
import concurrent.futures as cf,json,threading
from expanded_engine_evaluation import ROOT,Engine,credentials,readlines,save
from audit_expanded import finalize
from repair_labels_expanded import build as build_label_repairs,finish as finish_label_repairs

if __name__=='__main__':
    keys=credentials();jobs=json.loads((ROOT/'audit_jobs.json').read_text())['jobs'];old=readlines(ROOT/'audit_attempts.jsonl');by={r['job_id']:r for r in old}
    selected=[j for j in jobs if j['job_id'] in by and 'credit_balance_exhausted' in str(by[j['job_id']].get('error',''))]
    freeze_record={'scope':'Only user-confirmed credit-exhausted audit jobs; completed outputs and completed audits not resent.',
        'selected_jobs':[j['job_id'] for j in selected]}
    save(ROOT/'credit_resume_selection.json',freeze_record)
    if selected:
        engine=Engine('audit',keys);engine.semaphores['openai']=threading.Semaphore(12)
        def work(job):
            used=sum(r['job_id']==job['job_id'] for r in old)
            engine.worker(job,jobs,used+3)
        with cf.ThreadPoolExecutor(max_workers=12) as pool:
            for _ in pool.map(work,selected):pass
        engine.status('complete',jobs)
    finalize()
    jobs=build_label_repairs()
    if jobs:
        engine=Engine('label_repair',keys);engine.semaphores['openai']=threading.Semaphore(8);engine.run(jobs,workers=8,max_attempts=2)
    finish_label_repairs()
