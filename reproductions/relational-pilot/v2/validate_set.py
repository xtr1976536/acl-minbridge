"""Read-back checks and numerical alternative-path hints for every final case."""
import copy,json,re,sys
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from prepare import digest
from scan import alternate_paths


def main():
    data=json.loads((HERE/'final_150_review.json').read_text())
    records=data['records'];assert len(records)==150
    assert [r['number'] for r in records]==list(range(1,151))
    assert len({r['source_id'] for r in records})==150
    assert len({r['report_id'] for r in records})==150
    assert Counter(r['severity'] for r in records)=={'low':90,'medium':30,'high':30}
    raw=json.loads((HERE.parent/'local/raw/train.json').read_text())
    lookup={r['id']:r for r in raw}
    test=json.loads((HERE.parent/'local/raw/test.json').read_text())
    protected={'/'.join(r['filename'].split('/')[:2]) for r in test}
    scans=[];checks=[]
    for r in records:
        assert digest(lookup[r['source_id']])==r['source_sha256']
        assert r['original']['question']==r['modified']['question']
        assert r['report_id'] not in protected
        original=copy.deepcopy(r['original'])
        for edit in r['edits']:
            parts=edit['location'].split('/');parent=original[parts[0]]
            for bit in parts[1:-1]:parent=parent[int(bit)]
            i=int(parts[-1]);assert parent[i]==edit['original']
            parent[i]=edit['replacement']
        assert original==r['modified']
        assert digest(original)==r['modified_sha256']
        facts=r['facts'];ids={f['fact_id'] for f in facts};deleted=set(r['deleted_fact_ids'])
        assert len(ids)==len(facts)==r['original_fact_count']
        assert len(deleted)==r['deleted_fact_count'] and deleted<=ids
        assert abs(len(deleted)/len(facts)-r['deletion_ratio'])<1e-12
        positions=[]
        for f in facts:
            for loc in f['locations']:
                path=loc['location'];parent=r['original']
                for bit in path.split('/'):parent=parent[int(bit)] if isinstance(parent,list) else parent[bit]
                assert parent[loc['start']:loc['end']]==loc['original'],(r['number'],loc)
                positions.append((path,loc['start'],loc['end']))
                if path=='question':assert f['fact_id'] not in deleted
        assert len(positions)==len(set(positions)),('duplicate fact position',r['number'])
        base=[f for f in facts if f['fact_id'] in r['base_deleted_fact_ids']]
        assert base
        target=base[0]['value']
        hint=alternate_paths(r['modified'],target)
        scans.append({'number':r['number'],'source_id':r['source_id'],'target_numeric_hint':target,
                      'scan':hint,'semantic_assessment_zh':r['ai_direct_reason_zh'],
                      'caveat':'Matching values or arithmetic combinations are not accepted relations without metric/entity/period/unit support.'})
        checks.append({'number':r['number'],'source_id':r['source_id'],
                       'source_hash':True,'question_preserved':True,'all_edits_reproducible':True,
                       'no_other_edits':True,'distinct_fact_ledger':True,'ratio_recomputed':True,
                       'known_test_report_disjoint':True,'two_AI_review_records_present':bool(r['round1'] and r['round2']),
                       'human_independent_review_claimed':False})
    selected_reports={r['report_id'] for r in records}
    exclusion=sorted(r['id'] for r in raw if '/'.join(r['filename'].split('/')[:2]) in selected_reports)
    (HERE/'round2_program_checks.json').write_text(json.dumps({'passed':True,'cases':150,'checks':checks},ensure_ascii=False,indent=2))
    (HERE/'round2_numeric_hints.json').write_text(json.dumps(scans,ensure_ascii=False,indent=2))
    (HERE/'exclude_from_future_training.json').write_text(json.dumps({'report_ids':sorted(selected_reports),
        'finqa_train_source_ids':exclusion,'note':'Report-level exclusion; external-dataset source-family reconciliation remains subject to the final human-approved split protocol.'},ensure_ascii=False,indent=2))
    print(json.dumps({'cases_checked':150,'all_reproducibility_checks_passed':True,
                      'numerical_path_hints_present':sum(bool(s['scan']['witnesses']) for s in scans),
                      'excluded_future_train_source_ids':len(exclusion)},indent=2))


if __name__=='__main__':main()
