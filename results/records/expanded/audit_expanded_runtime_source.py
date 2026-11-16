"""Internal GPT recheck, explicitly distinct from independent human annotation."""
import collections,json,random
from expanded_engine import ROOT,freeze,readlines,save
from judge_expanded import judge_request
from judging_validation import validate_annotation
from prepare import digest

def build():
    initial=readlines(ROOT/'machine_annotations_initial.jsonl')
    outputs={r['id']:r for r in readlines(ROOT/'effective_outputs_2700.jsonl')}
    source_jobs={j['original_id']:j for j in json.loads((ROOT/'judge_jobs.json').read_text())['jobs']}
    source_audit=json.loads((ROOT/'source_answerability.json').read_text())
    source_judgements={r['source_id']:(r['annotation'] or {}).get('answerability','uncertain') for r in source_audit['items']}
    sign_cases=set()
    for row in outputs.values():
        payload=json.loads(source_jobs[row['id']]['request']['messages'][1]['content'])
        question=payload['question_and_evidence']['question'].lower()
        if any(term in question for term in ('percent','percentage','percentual')) and any(term in question for term in ('decrease','decline','reduction')):
            sign_cases.add(row['case_number'])
    by_cell=collections.defaultdict(list)
    for item in initial:
        row=outputs[item['id']];by_cell[(row['provider'],row['mode'],row['method'])].append(item['id'])
    rng=random.Random(20261117);random_ids=set()
    for key in sorted(by_cell):random_ids.update(rng.sample(sorted(by_cell[key]),5))
    selected=[]
    for item in initial:
        if item.get('provider_content_rejection'):continue
        ann=item['annotation'];reasons=[]
        if item['validation_issues']:reasons.append('mechanical_validation')
        if ann and (ann['confidence']=='low' or ann['answerability']!='insufficient' or ann['definition_ambiguous']):reasons.append('uncertainty_or_answerability')
        if ann and source_judgements.get(outputs[item['id']]['source_id'],'uncertain')!=ann['answerability']:reasons.append('source_only_answerability_disagreement')
        if item['id'] in random_ids:reasons.append('stratified_random_recheck')
        if outputs[item['id']]['case_number'] in sign_cases:reasons.append('percentage_sign_and_definition_consistency')
        if not reasons:continue
        original_job=source_jobs[item['id']];payload=json.loads(original_job['request']['messages'][1]['content'])
        # Random rechecks see the same evidence afresh, without the first label.
        if 'stratified_random_recheck' not in reasons:
            payload['prior_machine_annotation_for_critique']=ann
            payload['mechanical_validation_flags']=item['validation_issues']
        request=judge_request(payload,effort='high',cap=16384)
        request['messages'][0]['content']+='\nINTERNAL RECHECK: Reassess independently from the evidence. A prior annotation, if supplied, may be wrong; correct it rather than defend it. Exact response/evidence quotations are mandatory. Return the same schema.'
        request['messages'][0]['content']+='\nPercent changes may conventionally express a decrease with a negative sign. Do not call a sign convention alone a bridging hallucination absent an explicit incompatible definition. If only arithmetic or wording is wrong, distinguish it from an unsupported factual relation. Rounded figures may support an explicitly approximate answer even if an exact hidden table amount was removed; evaluate the stated precision honestly.'
        request['messages'][0]['content']+='\nCheck time and scope rigorously: in a multi-year balance reconciliation, additions/deductions between two balance rows belong to the interval ending at the following balance, not automatically the year on the preceding row. A total across several years is not a single-year amount. Overall company/segment amounts do not automatically stand for one region or subsegment. Conversely an underspecified question must not be silently forced to an invisible original gold interpretation: flag genuine scope ambiguity. Assess only what the supplied question/evidence reasonably establishes.'
        selected.append({'job_id':digest(['internal-recheck-v1',item['id'],request]),'original_id':item['id'],
                         'provider':'openai','request':request,'meta':{'reasons':reasons,'random_recheck':item['id'] in random_ids}})
    rng.shuffle(selected)
    freeze(ROOT/'audit_jobs.json',{'jobs':selected,'random_seed':20261117,'random_sample_per_cell':5,
        'random_sample_ids':sorted(random_ids),'scope':'Internal repeat GPT assessment, not two human raters or independent-family adjudication.'})
    return selected

def finalize():
    initial=readlines(ROOT/'machine_annotations_initial.jsonl');jobs=json.loads((ROOT/'audit_jobs.json').read_text())
    task_index={j['original_id']:j for j in jobs['jobs']}
    attempts={r['job_id']:r for r in readlines(ROOT/'audit_attempts.jsonl')}
    final=[];changes=[];unresolved=[];random_pairs=[]
    for item in initial:
        out=dict(item);job=task_index.get(item['id'])
        if job:
            row=attempts.get(job['job_id']);ann=None;errors=[]
            if not row or row['status']!='completed':errors=['audit_missing_or_incomplete']
            else:
                try:ann=json.loads(row['content']);errors=validate_annotation(ann,json.loads(job['request']['messages'][1]['content']))
                except (ValueError,TypeError,KeyError):errors=['invalid_audit_json']
            out['internal_recheck']={'attempt_id':row['attempt_id'] if row else None,'validation_issues':errors,'reasons':job['meta']['reasons']}
            if not errors:
                if item['annotation'] and (ann['labels'],ann['response_type'])!=(item['annotation']['labels'],item['annotation']['response_type']):changes.append(item['id'])
                if job['meta']['random_recheck'] and item['annotation'] and not item['validation_issues']:random_pairs.append((item['annotation'],ann))
                out.update(annotation=ann,validation_issues=[],selected_annotation_source='internal_gpt_recheck')
            else:
                unresolved.append(item['id']);out['review_unresolved']=True
        final.append(out)
    agreement={key:{'n':len(random_pairs),'same':sum(a['labels'][key]==b['labels'][key] for a,b in random_pairs),
                     'agreement':sum(a['labels'][key]==b['labels'][key] for a,b in random_pairs)/len(random_pairs) if random_pairs else None}
               for key in ('wrong_answer','correct_refusal','numeric_hallucination','relational_hallucination')}
    (ROOT/'machine_annotations_final.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in final))
    save(ROOT/'internal_recheck_summary.json',{'selected':len(task_index),'random_selected':len(jobs['random_sample_ids']),
        'label_or_response_type_changed':len(changes),'changed_ids':changes,'unresolved_review_ids':unresolved,
        'random_machine_recheck_agreement':agreement,'human_reviewers':0,'human_cohen_kappa':None})
    print('FINAL_MACHINE_ANNOTATIONS',len(final),'recheck changes',len(changes),'unresolved',len(unresolved))
