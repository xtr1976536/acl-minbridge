"""Recompute saved machine-judged statistics without calling any model API."""
import argparse,importlib.util,json,sys
from pathlib import Path
from materialize import materialize

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--figures',action='store_true');parser.add_argument('--report',action='store_true');args=parser.parse_args()
    materialize();pilot=ROOT/'reproductions/relational-pilot';sys.path.insert(0,str(pilot))
    from analyze_expanded import main
    computed=main();published=json.loads((ROOT/'results/tables/结果统计.json').read_text())
    assert computed==published,'Recomputed metrics differ from the published snapshot'
    if args.figures:
        from report_expanded import main as report
        report()
    if args.report:
        import make_chinese_briefing
        make_chinese_briefing.build()
    print(json.dumps({'published_statistics_reproduced':True,'network_requests':0,'output':str(ROOT/'output')}))
