"""Optional official data fetch for reconstructing the historical curation steps."""
import argparse,hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
COMMIT='0f16e2867befa6840783e58be38c9efb9229d742'
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true');args=parser.parse_args()
    paths={'train':ROOT/'reproductions/relational-pilot/local/raw/train.json','test':ROOT/'reproductions/gbfr/data/raw/official/FinQA.json'}
    for split,path in paths.items():
        url=f'https://raw.githubusercontent.com/czyssrs/FinQA/{COMMIT}/dataset/{split}.json'
        if not args.download:print(json.dumps({'split':split,'url':url,'action':'not downloaded; pass --download'}));continue
        with urllib.request.urlopen(url,timeout=60) as response:data=response.read()
        if split=='train':assert hashlib.sha256(data).hexdigest()=='49f237eb9779b569473b26b08048867d04635a7cc39ad6a7a5664c55bb428db6'
        assert isinstance(json.loads(data),list);path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():assert path.read_bytes()==data,'Existing official file differs'
        else:path.write_bytes(data)
        print(json.dumps({'split':split,'records':len(json.loads(data)),'sha256':hashlib.sha256(data).hexdigest()}))
