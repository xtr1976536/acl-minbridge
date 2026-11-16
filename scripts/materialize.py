"""Expand the public compressed records into the ignored historical code layout."""
import argparse,gzip,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def materialize():
    mapping=json.loads((ROOT/'publication/materialization.json').read_text())['files']
    written=0
    for item in mapping:
        source=(ROOT/item['source']).resolve();target=(ROOT/item['target']).resolve()
        if not source.is_relative_to(ROOT) or not target.is_relative_to(ROOT):raise ValueError('Unsafe materialization path')
        data=source.read_bytes()
        if item['gzip']:data=gzip.decompress(data)
        assert hashlib.sha256(data).hexdigest()==item['sha256'],item['source']
        if target.exists():
            if target.read_bytes()!=data:raise RuntimeError('Refusing to replace modified local file: '+item['target'])
        else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);written+=1
    print(json.dumps({'materialized_paths':len(mapping),'new_files':written,'network_requests':0}))
    return mapping
if __name__=='__main__':materialize()
