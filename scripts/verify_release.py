"""Offline integrity checks for the complete released first-stage snapshot."""
import collections,csv,gzip,hashlib,io,json,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(path):
    path=ROOT/path;data=path.read_bytes()
    if path.suffix=='.gz':data=gzip.decompress(data)
    return data
def jsonl(path):return [json.loads(line) for line in load(path).decode().splitlines()]
def digest(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def main():
    excluded=['reproductions/relational-pilot/analyze.py','reproductions/relational-pilot/annotations.py',
       'reproductions/relational-pilot/providers.example.json','reproductions/relational-pilot/repair_labels_expanded.py',
       'reproductions/relational-pilot/resume_credit_expanded.py','reproductions/pot/vendor/run_finqa.py',
       'reproductions/pot/vendor/data/finqa_test.json']
    assert all(not (ROOT/name).exists() for name in excluded),'Unused scope material reintroduced'
    final=jsonl('results/records/expanded/effective_outputs_2700.jsonl.gz')
    initial=jsonl('results/records/english150-20261116-v2/outputs.jsonl.gz')
    labels=jsonl('results/records/expanded/machine_annotations_final.jsonl.gz')
    assert len(final)==len(initial)==len(labels)==2700
    assert len({r['id'] for r in final})==2700
    assert {r['id'] for r in final}=={r['id'] for r in initial}=={r['id'] for r in labels}
    inputs=json.loads(load('data/model_inputs_150.json'))['drafts']
    assert len(inputs)==150 and len({r['source_id'] for r in inputs})==150
    kset=json.loads(load('data/final_150_review.json.gz'))['records']
    nset=json.loads((ROOT/'reproductions/relational-pilot/v2/final_150_n_control.json').read_text())
    assert len(kset)==len(nset['records'])==150
    assert {r['source_id'] for r in kset}=={r['source_id'] for r in nset['records']}
    for k,n in zip(kset,nset['records']):
        assert k['source_id']==n['source_id'] and k['modified_sha256']==n['paired_k_variant_sha256']
        assert set(k['deleted_fact_ids']).isdisjoint(n['n_deleted_fact_ids'])
        assert n['deleted_fact_count']<=k['deleted_fact_count']
        assert n['round1']['all_standard_program_literal_support_preserved']
        replay=json.loads(json.dumps(k['original']))
        for edit in n['edits']:
            parts=edit['location'].split('/');parent=replay[parts[0]]
            for part in parts[1:-1]:parent=parent[int(part)]
            index=int(parts[-1]);assert parent[index]==edit['original'];parent[index]=edit['replacement']
        assert replay==n['modified']
    assert nset['unmatched_deletion_dose_cases']==[
        {'case':20,'target_deletions':1,'available_nonessential_facts':0,'N_equals_O':True},
        {'case':103,'target_deletions':2,'available_nonessential_facts':0,'N_equals_O':True}]
    evidence={r['source_id']:r for r in inputs};original={r['id']:r for r in initial};annotations={r['id']:r for r in labels}
    groups=collections.defaultdict(list)
    for r in final:
        assert r['finish_reason']=='stop' and r['content'].strip()
        assert r['returned_model']==r['model']==r['request']['model']
        assert r['request']['messages']==original[r['id']]['request']['messages']
        assert digest(r['request'])==r['request_sha256']
        assert r['variant_sha256']==digest(evidence[r['source_id']]['visible'])
        assert annotations[r['id']]['judged_output_sha256']==digest(r)
        assert (r.get('usage') or {}).get('completion_tokens',0)<=r['request'].get('max_tokens',r['request'].get('max_completion_tokens'))+10
        groups[(r['provider'],r['mode'],r['method'])].append(r)
    assert len(groups)==18
    assert all(len(v)==150 and {r['case_number'] for r in v}==set(range(1,151)) for v in groups.values())
    sys.path.insert(0,str(ROOT/'reproductions/relational-pilot'))
    import prompts
    for r in final:
        assert prompts.messages(r['method'],evidence[r['source_id']]['visible'])==r['request']['messages'], 'Public prompt adapter drift'
    # Independent implementation of point counts, not a call to the analysis code.
    sums={policy:collections.Counter() for policy in ('numeric_provenance_exclusive','independent_overlapping')}
    for r in final:
        item=annotations[r['id']];a=item.get('annotation')
        if not a or item['validation_issues'] or a['response_type']=='unfinished':continue
        lab=a['labels'];wrong=lab['wrong_answer']
        for policy in sums:
            numeric=bool(wrong and (lab['outside_document_input_number'] if policy=='numeric_provenance_exclusive' else lab['numeric_hallucination']))
            relation=bool(wrong and (not lab['outside_document_input_number'] if policy=='numeric_provenance_exclusive' else lab['relational_hallucination']))
            sums[policy].update(wrong_answer=int(wrong),numeric=int(numeric),relation=int(relation),both=int(numeric and relation))
    stats=json.loads(load('results/tables/结果统计.json'))
    for policy,counts in sums.items():
        m=stats['label_policies'][policy]['overall']
        for key,value in counts.items():assert m[key]==value,(policy,key,value,m[key])
        assert m['n_all_nominal_unanswerable']==2700
    assert sums['independent_overlapping']['numeric']==227 and sums['independent_overlapping']['relation']==379
    assert len(jsonl('results/records/expanded/repair_attempts.jsonl.gz'))==190
    assert len(jsonl('results/records/expanded/repair64_attempts.jsonl.gz'))==8
    judge=jsonl('results/records/expanded/judge_attempts.jsonl.gz');audits=jsonl('results/records/expanded/audit_attempts.jsonl.gz')
    latest_judge={r['job_id']:r for r in judge};latest_audit={r['job_id']:r for r in audits}
    assert len(latest_judge)==2700 and sum(r['status']=='completed' for r in latest_judge.values())==2698
    assert len(latest_audit)==682 and sum(r['status']=='completed' for r in latest_audit.values())==656
    assert len(jsonl('results/records/expanded/answerability_attempts.jsonl.gz'))==150
    assert len(jsonl('results/records/expanded/source_review_attempts.jsonl.gz'))==22
    for path in ('results/tables/2700条更新模型输出.csv.gz','results/tables/2700条逐项评审.csv.gz'):
        assert len(list(csv.DictReader(io.StringIO(load(path).decode('utf-8-sig')))))==2700
    from pypdf import PdfReader
    pdf=ROOT/'reports/MinBridge_关系幻觉预研_中文汇报.pdf';reader=PdfReader(pdf)
    assert len(reader.pages)==17
    text='\n'.join(p.extract_text() or '' for p in reader.pages)
    assert 'RQ1' in text and '14.04%' in text and '8.41%' in text and '附录D' not in text
    expected=json.loads((ROOT/'publication/expected_results.json').read_text())
    assert hashlib.sha256(pdf.read_bytes()).hexdigest()==expected['report_pdf_sha256']
    manifest=ROOT/'publication/files.json'
    if manifest.exists():
        for name,meta in json.loads(manifest.read_text())['files'].items():
            f=ROOT/name
            blob=f.read_bytes() if f.is_file() else subprocess.check_output(['git','-C',str(ROOT),'show',':'+name])
            assert hashlib.sha256(blob).hexdigest()==meta['sha256'],name
    result={'passed':True,'sources':150,'outputs':2700,'conditions':18,'records_per_condition':150,
       'complete_generations':2700,'model_output_duplicates_or_missing':0,'judge_records':2700,'valid_main_responses':2698,
       'internal_review_completed':656,'internal_review_selected':682,
       'unresolved_annotation_markers':sum(bool(r['validation_issues'] or r.get('review_unresolved')) for r in labels),
       'independent_counts':dict(sums['independent_overlapping']),'report_pages':17,'network_requests':0,
       'N_control':{'records':150,'paired_sources':150,'same_K_N_deletion_count':148,
          'N_equals_O_no_other_quantified_facts':[20,103],'K_N_deletion_sets_disjoint':True,
          'original_program_inputs_preserved':True,'N_model_runs':0,'human_semantic_review_completed':0},
       'scope':'Actual three-API first-stage FinQA study plus paired E3 N-control candidate and direct replay/integrity utilities',
       'unused_pipelines_and_test_dataset_absent':True}
    print(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':main()
