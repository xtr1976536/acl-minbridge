"""Inspect/replay frozen metadata-blinded GPT requests; no automatic API calls."""
import argparse,gzip,json,sys
from pathlib import Path
from _api import load_keys,submit

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);parser.add_argument('--execute',action='store_true');parser.add_argument('--out',default='work/judge-replay');args=parser.parse_args()
    jobs=json.loads(gzip.decompress((ROOT/'results/records/expanded/judge_jobs.json.gz').read_bytes()))['jobs']
    if args.limit is not None:assert args.limit>0;jobs=jobs[:args.limit]
    if not args.execute:print(json.dumps({'mode':'offline_dry_run','judge_requests':len(jobs),'model':'gpt-5.6-sol','metadata_blinded':True,'api_calls':0}));sys.exit(0)
    out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True);assert not (out/'outputs.jsonl').exists(),'Choose a new output directory'
    keys=load_keys(['openai'])
    for job in jobs:submit({'id':job['job_id'],'provider':'openai','request':job['request']},keys,out)
