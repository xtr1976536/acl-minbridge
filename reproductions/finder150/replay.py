"""Replay the frozen, reviewed FinDER deletion plan using only the standard library.

The reviewed plan is the authority for source replacements, semantic decisions,
and deleted fact IDs. This does not regenerate those decisions with a model.
"""
import argparse
import collections
import copy
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/finder150'


def load(name):
    data = (DATA / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith('.gz') else data)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def replay():
    bundle = load('construction_plan.json.gz')
    sources = {r['source_index']: r['source'] for r in load('selected_sources.json.gz')}
    output = copy.deepcopy(bundle)
    records = []
    for plan in bundle['records']:
        r = copy.deepcopy(plan)
        raw = sources[r['source_index']]
        assert raw['_id'] == r['source_id']
        assert digest(raw) == r['source_sha256']
        original = {'question': raw['text'], 'references': raw['references']}
        modified = copy.deepcopy(original)
        removed = set(r['deleted_fact_ids'])
        spans = collections.defaultdict(dict)
        for fact in r['facts']:
            if fact['fact_id'] not in removed:
                continue
            assert not fact.get('protected'), r['source_id']
            for loc in fact['locations']:
                assert not loc.get('question'), r['source_id']
                spans[loc['reference_index']][(loc['start'], loc['end'])] = loc
        edits = []
        for ri, positions in spans.items():
            s = original['references'][ri]
            previous_start = len(s) + 1
            for (start, end), loc in sorted(positions.items(), reverse=True):
                assert end <= previous_start
                assert s[start:end] == loc['original']
                previous_start = start
                edits.append({**loc, 'replacement': '[not disclosed]'})
                s = s[:start] + '[not disclosed]' + s[end:]
            modified['references'][ri] = s
        r.update(original=original, modified=modified,
                 edits=sorted(edits, key=lambda e: (e['reference_index'], e['start'])),
                 modified_sha256=digest(modified))
        assert r['deleted_fact_count'] == len(removed)
        assert r['original_fact_count'] == len(r['facts'])
        assert r['deletion_ratio'] == len(removed) / len(r['facts'])
        records.append(r)
    output['records'] = records
    expected = load('final_150_review.json.gz')
    assert output == expected, 'Frozen construction replay differs from the published review data'
    drafts = [{'source_id': r['source_id'], 'family_id': r['report_fingerprint'],
               'visible': {'question': r['modified']['question'],
                           'pre_text': r['modified']['references'], 'table': [], 'post_text': []}}
              for r in records]
    inputs = {'status': output['status'], 'count': len(records),
              'model_input_language': 'English only', 'drafts': drafts}
    assert inputs == load('model_inputs_150.json')
    assert len(records) == len({r['source_id'] for r in records}) == 150
    assert collections.Counter(r['severity'] for r in records) == {'low': 90, 'medium': 30, 'high': 30}
    return output, inputs


def verify_files():
    manifest = load('release_manifest.json')
    for relative, expected in manifest['files'].items():
        data = (ROOT / relative).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected['sha256'], relative
        assert len(data) == expected['bytes'], relative


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--materialize', action='store_true', help='Write ignored local JSONs for PDF rebuilding')
    args = parser.parse_args()
    output, inputs = replay()
    verify_files()
    if args.materialize:
        dest = DATA / 'local'
        dest.mkdir(exist_ok=True)
        (dest / 'final_150_review.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
        for name in ['translations_zh.json', 'table_terms_zh.json', 'finqa_terminology_zh.json']:
            (dest / name).write_text(json.dumps(load(name + '.gz'), ensure_ascii=False, indent=2) + '\n')
        for name in ['questions_zh.txt', 'narratives_zh.json']:
            (dest / name).write_bytes((DATA / name).read_bytes())
    print(json.dumps({'passed': True, 'source_records': 150, 'mutation_replays': 150,
                      'input_records': len(inputs['drafts']), 'groups': output['groups'],
                      'model_calls': 0, 'human_confirmation': 'pending',
                      'files_checked': len(load('release_manifest.json')['files'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
