"""Inspect/replay the exact saved generation requests. Default is offline dry-run."""
import argparse,collections,gzip,json,sys
from pathlib import Path
from _api import load_keys,submit

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',choices=['final','original'],default='final');parser.add_argument('--provider',choices=['openai','deepseek','qwen']);parser.add_argument('--limit',type=int);parser.add_argument('--execute',action='store_true');parser.add_argument('--out',default='work/model-replay');args=parser.parse_args()
    file=ROOT/('results/records/expanded/effective_outputs_2700.jsonl.gz' if args.snapshot=='final' else 'results/records/english150-20261116-v2/outputs.jsonl.gz')
    rows=[json.loads(line) for line in gzip.decompress(file.read_bytes()).decode().splitlines()]
    if args.provider:rows=[r for r in rows if r['provider']==args.provider]
    if args.limit is not None:
        assert args.limit>0;rows=rows[:args.limit]
    if not args.execute:
        print(json.dumps({'mode':'offline_dry_run','requests':len(rows),'conditions':dict(collections.Counter('/'.join((r['provider'],r['mode'],r['method'])) for r in rows)),'api_calls':0}));sys.exit(0)
    out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True);assert not (out/'outputs.jsonl').exists(),'Choose a new output directory'
    keys=load_keys(sorted({r['provider'] for r in rows}))
    sys.path.insert(0,str(ROOT/'reproductions/relational-pilot'));from run import execute_pot
    for r in rows:
        response=submit({'id':r['id'],'provider':r['provider'],'request':r['request']},keys,out)
        if r['method']=='pot' and response['status']=='completed':
            # Credential-free execution environment is enforced by execute_pot.
            result={'id':r['id'],'execution':execute_pot(response['content'],20)}
            with (out/'pot_execution.jsonl').open('a') as f:f.write(json.dumps(result)+'\n')
