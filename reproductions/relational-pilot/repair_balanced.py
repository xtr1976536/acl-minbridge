"""Resume the frozen repair jobs with independent provider queues."""
import concurrent.futures as cf
import datetime,hashlib,json
from pathlib import Path
from expanded_engine import ROOT,Engine,credentials
from repair_expanded import build,merge

if __name__=='__main__':
    jobs,baseline=build()
    engine=Engine('repair',credentials())
    record={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'concurrency':{'openai':2,'deepseek':8,'qwen':8},
            'already_recorded_attempts':len(engine.rows),
            'change':'Provider queues separated to avoid one provider blocking another. Frozen prompts/models/caps unchanged; completed jobs never resent.'}
    with (ROOT/'repair_execution_sessions.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
    def family_run(provider):
        selected=[job for job in jobs if job['provider']==provider]
        with cf.ThreadPoolExecutor(max_workers=2 if provider=='openai' else 8) as pool:
            for _ in pool.map(lambda job:engine.worker(job,jobs,3),selected):pass
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        for _ in pool.map(family_run,('openai','deepseek','qwen')):pass
    print(json.dumps(engine.status('complete' if len({r['job_id'] for r in engine.rows})==len(jobs) else 'needs_review',jobs)),flush=True)
    merge(jobs,baseline)
