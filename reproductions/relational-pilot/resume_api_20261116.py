"""Resume only never-recorded cells at reduced concurrency; no failed-cell retries."""
import datetime
import hashlib
import json
from pathlib import Path
import run_api_20261116_v2 as pilot

original_stage=pilot.Runner.stage
def reduced_stage(self,tasks,workers):
    return original_stage(self,tasks,min(workers,8))
pilot.Runner.stage=reduced_stage

if __name__=='__main__':
    rows=[json.loads(line) for line in (pilot.OUT/'outputs.jsonl').read_text().splitlines()]
    record={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'max_concurrent_requests':8,'already_recorded_cells_not_resent':len(rows),
            'including_failed_or_truncated_cells':sum(r['status'] not in ('completed','execution_failed') for r in rows),
            'reason':'Resume only unsubmitted cells after provider connection failures. HTTP parameters and task identities unchanged. Uncertain requests retained and costed at reserved upper bound.'}
    with (pilot.OUT/'resume_sessions.jsonl').open('a') as file:file.write(json.dumps(record)+'\n')
    pilot.main()
