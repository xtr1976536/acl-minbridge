"""Mechanical quote validation v2: accepts verbatim serialized JSON rows too."""
import json
from judge_expanded import validate_annotation as original_validate,normalized,strings
from expanded_engine_concurrent import ROOT,readlines,save

def validate_annotation(annotation,payload):
    problems=original_validate(annotation,payload)
    # A conditional response can correctly abstain from an ACTUAL value while
    # supplying a valid scenario/formula. Keep both raw flags; count categories
    # separately instead of inventing an inconsistency or changing labels.
    labels=annotation.get('labels',{})
    if ('refusal_inconsistent' in problems and annotation.get('response_type')=='conditional_answer'
        and labels.get('correct_refusal') and not labels.get('wrong_answer')):
        problems.remove('refusal_inconsistent')
    raw=normalized(json.dumps(payload['question_and_evidence'],ensure_ascii=False))
    decoded=normalized('\n'.join(strings(payload['question_and_evidence'])))
    for kind in ('numeric_witnesses','relation_witnesses'):
        tag=kind+'_evidence_quote_not_found'
        if tag in problems:
            valid=all(not w['evidence_quote'] or normalized(w['evidence_quote']) in raw or normalized(w['evidence_quote']) in decoded for w in annotation[kind])
            if valid:problems.remove(tag)
    return problems

def revalidate_initial():
    path=ROOT/'machine_annotations_initial.jsonl'
    backup=ROOT/'machine_annotations_initial.checker_v1.jsonl'
    if not backup.exists():backup.write_bytes(path.read_bytes())
    jobs={j['original_id']:j for j in json.loads((ROOT/'judge_jobs.json').read_text())['jobs']}
    rows=readlines(path);changed=0
    attempts={r['attempt_id']:r for r in readlines(ROOT/'judge_attempts.jsonl')}
    for row in rows:
        if row.get('annotation') is None:
            attempt=attempts.get(row.get('judge_attempt_id'),{})
            if 'invalid_prompt' in str(attempt.get('error','')):
                row['validation_issues']=['provider_invalid_prompt'];row['provider_content_rejection']=True
            continue
        payload=json.loads(jobs[row['id']]['request']['messages'][1]['content'])
        flags=validate_annotation(row['annotation'],payload)
        if flags!=row['validation_issues']:changed+=1
        row['validation_issues']=flags;row['quote_checker_version']='v2_serialized_JSON_and_decoded_text'
    path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    save(ROOT/'quote_checker_revision.json',{'mechanical_flags_changed':changed,'annotation_labels_changed':0,
        'reason':'Evidence supplied to the judge is serialized JSON. Verbatim complete JSON rows must be accepted alongside decoded cell/text quotations. Raw annotations preserved.'})
    print('QUOTE_REVALIDATION',changed,'mechanical flag sets changed; labels unchanged')
