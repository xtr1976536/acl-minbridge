"""Descriptive machine-judged rates, both definitions, paired source bootstrap."""
import collections,csv,hashlib,json
from pathlib import Path
import numpy as np
from expanded_engine import HERE,ROOT,OLD,readlines,save

POLICIES=('numeric_provenance_exclusive','independent_overlapping')
METHODS=('cot_paired_4shot','pot','cot_existing_abstention')
PROVIDERS=('openai','deepseek','qwen')

def flags(output,item,policy):
    ann=item.get('annotation') if item else None
    generation_complete=output.get('finish_reason')=='stop' and bool(output.get('content','').strip())
    valid=bool(ann) and not item.get('validation_issues') if item else False
    usable=generation_complete and valid and ann['response_type']!='unfinished'
    lab=ann['labels'] if ann else {}
    wrong=bool(usable and lab.get('wrong_answer'))
    if policy==POLICIES[0]:numeric=wrong and lab['outside_document_input_number'];relation=wrong and not lab['outside_document_input_number']
    else:numeric=wrong and lab['numeric_hallucination'];relation=wrong and lab['relational_hallucination']
    uncertain=not usable or bool(ann and (ann['confidence']=='low' or ann['definition_ambiguous'] or ann['answerability']=='uncertain')) or bool(item and item.get('review_unresolved'))
    return {k:int(v) for k,v in {
       'wrong_answer':wrong,'numeric':numeric,'relation':relation,'both':numeric and relation,
       'correct_refusal':usable and lab.get('correct_refusal') and ann['response_type']=='refusal' and not ann['valid_declared_conditional'],
       'abstains_actual_value':usable and lab.get('correct_refusal'),
       'valid_conditional':usable and ann['valid_declared_conditional'],
       'other_error':usable and lab.get('other_error'),'arithmetic_error':usable and ann['arithmetic_error'],
       'abandoned_numeric':usable and ann['abandoned_numeric_issue'],
       'abandoned_relation':usable and ann['abandoned_relational_issue'],
       'abandoned_any':usable and (ann['abandoned_numeric_issue'] or ann['abandoned_relational_issue']),
       'unfinished_generation':not generation_complete,'judge_unusable':generation_complete and not usable,
       'uncertain':uncertain,
       'numeric_all_endorsed':usable and lab.get('numeric_hallucination'),
       'relation_all_endorsed':usable and lab.get('relational_hallucination'),
       'confident_wrong':wrong and not uncertain,'confident_numeric':numeric and not uncertain,
       'confident_relation':relation and not uncertain}.items()}

def ci(values):
    arr=np.asarray(values,dtype=float);bad=int(np.isnan(arr).sum())
    return {'ci95':np.quantile(arr,[.025,.975]).tolist() if not bad and len(arr) else None,'undefined_replicates':bad}
def division(a,b):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    return np.divide(a,b,out=np.full(np.broadcast_shapes(a.shape,b.shape),np.nan),where=b!=0)

def summarize(rows,items,draws,policy,case_index):
    vals=[flags(row,items.get(row['id']),policy) for row in rows];n=len(rows)
    counts={key:sum(v[key] for v in vals) for key in vals[0]}
    summary={'n_all_nominal_unanswerable':n,**counts,
        'numeric_rate':counts['numeric']/n,'relation_rate':counts['relation']/n,
        'both_rate':counts['both']/n,'wrong_answer_rate':counts['wrong_answer']/n,
        'h1_relation_share_among_wrong':counts['relation']/counts['wrong_answer'] if counts['wrong_answer'] else None,
        'numeric_annotation_uncertainty_envelope':[counts['confident_numeric']/n,(counts['confident_numeric']+counts['uncertain'])/n],
        'relation_annotation_uncertainty_envelope':[counts['confident_relation']/n,(counts['confident_relation']+counts['uncertain'])/n]}
    vectors={key:np.zeros(150) for key in ('denominator','numeric','relation','wrong_answer')}
    for row,value in zip(rows,vals):
        idx=case_index[row['source_id']];vectors['denominator'][idx]+=1
        for key in ('numeric','relation','wrong_answer'):vectors[key][idx]+=value[key]
    resampled={key:vec[draws].sum(axis=1) for key,vec in vectors.items()}
    boots={key+'_rate':division(resampled[key],resampled['denominator']) for key in ('numeric','relation')}
    boots['h1_relation_share_among_wrong']=division(resampled['relation'],resampled['wrong_answer'])
    summary['confidence']={key:ci(value) for key,value in boots.items()}
    return summary,boots

def main():
    outputs=readlines(ROOT/'effective_outputs_2700.jsonl');labels=readlines(ROOT/'machine_annotations_final.jsonl')
    assert len(outputs)==len(labels)==2700 and len({r['id'] for r in outputs})==2700
    items={r['id']:r for r in labels};assert set(items)=={r['id'] for r in outputs}
    source=json.loads((HERE/'v2/final_150_review.json').read_text())['records'];source_map={r['source_id']:r for r in source}
    assert len(source_map)==150
    case_ids=sorted(source_map);case_index={key:i for i,key in enumerate(case_ids)}
    for row in outputs:assert items[row['id']]['judged_output_sha256']==hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    strata={severity:[case_index[key] for key in case_ids if source_map[key]['severity']==severity] for severity in ('low','medium','high')}
    assert [len(strata[x]) for x in ('low','medium','high')]==[90,30,30]
    rng=np.random.default_rng(20261116)
    draws=np.concatenate([rng.choice(idx,size=(2000,len(idx)),replace=True) for idx in strata.values()],axis=1)
    groups={'overall':outputs}
    for provider in PROVIDERS:
        groups['model/'+provider]=[r for r in outputs if r['provider']==provider]
        for mode in ('low','high'):
            for method in METHODS:groups['cell/'+provider+'/'+mode+'/'+method]=[r for r in outputs if (r['provider'],r['mode'],r['method'])==(provider,mode,method)]
    for method in METHODS:groups['method/'+method]=[r for r in outputs if r['method']==method]
    groups['core/paired_cot_and_pot']=[r for r in outputs if r['method'] in ('cot_paired_4shot','pot')]
    groups['supplementary/existing_cot']=[r for r in outputs if r['method']=='cot_existing_abstention']
    for severity in strata:groups['severity/'+severity]=[r for r in outputs if source_map[r['source_id']]['severity']==severity]
    summaries={};all_boot={}
    for policy in POLICIES:
        summaries[policy]={};all_boot[policy]={}
        for key,rows in groups.items():summaries[policy][key],all_boot[policy][key]=summarize(rows,items,draws,policy,case_index)
    comparisons={}
    for policy in POLICIES:
        comparisons[policy]={'h2':{},'h3':{}}
        for provider in PROVIDERS:
            for mode in ('low','high'):
                pot='cell/'+provider+'/'+mode+'/pot'
                for cot_method in ('cot_paired_4shot','cot_existing_abstention'):
                    cot='cell/'+provider+'/'+mode+'/'+cot_method;point={};boots={}
                    for rate in ('numeric_rate','relation_rate'):
                        point[rate+'_difference_pot_minus_cot']=summaries[policy][pot][rate]-summaries[policy][cot][rate]
                        boots[rate+'_difference_pot_minus_cot']=all_boot[policy][pot][rate]-all_boot[policy][cot][rate]
                    denom=summaries[policy][cot]['relation_rate']
                    if denom:
                        point['relation_rate_ratio_pot_over_cot']=summaries[policy][pot]['relation_rate']/denom
                        boots['relation_rate_ratio_pot_over_cot']=division(all_boot[policy][pot]['relation_rate'],all_boot[policy][cot]['relation_rate'])
                    comparisons[policy]['h2'][provider+'/'+mode+'/pot_vs_'+cot_method]={k:{'estimate':v,**ci(boots[k])} for k,v in point.items()}
            for method in METHODS:
                high='cell/'+provider+'/high/'+method;low='cell/'+provider+'/low/'+method
                comparisons[policy]['h3'][provider+'/'+method]={'relation_rate_difference_high_minus_low':summaries[policy][high]['relation_rate']-summaries[policy][low]['relation_rate'],
                     **ci(all_boot[policy][high]['relation_rate']-all_boot[policy][low]['relation_rate'])}
    original=readlines(OLD/'outputs.jsonl');original_items={r['id']:items[r['id']] for r in original if r.get('finish_reason')=='stop' and r.get('content','').strip()}
    original_sensitivity={policy:summarize(original,original_items,draws,policy,case_index)[0] for policy in POLICIES}
    source_audit=json.loads((ROOT/'source_answerability.json').read_text())
    source_decisions={r['source_id']:r for r in source_audit['items']}
    insufficient={sid for sid,r in source_decisions.items() if r['annotation'] and r['annotation']['answerability']=='insufficient' and not r.get('validation_issues')}
    diagnostic_subset=[r for r in outputs if r['source_id'] in insufficient]
    subset_rates={policy:summarize(diagnostic_subset,items,draws,policy,case_index)[0] for policy in POLICIES} if diagnostic_subset else {}
    result={'status':'exploratory_GPT_machine_judged_not_human_adjudicated','records':2700,'source_questions':150,
       'label_policies':summaries,'h1_h2_h3_comparisons':comparisons,'original_uniform_8192_sensitivity':original_sensitivity,
       'bootstrap':{'replicates':2000,'seed':20261116,'unit':'source_question, paired across conditions, stratified by fixed 90/30/30 deletion groups',
                    'distinct_source_reports':len({r['report_id'] for r in source}),
                    'reviewed_family_clustering_available':False,'label_error_included_in_ci':False},
       'answerability_challenge_case_numbers':sorted({r['case_number'] for r in outputs if items[r['id']].get('annotation') and items[r['id']]['annotation']['answerability']!='insufficient'}),
       'generation_budget_note':'190 selected conditions rerun; 182 original cutoff cells receive 24576, with user-approved 65536 only for remaining cutoffs. Other cells retain 8192. Mixed adaptive budgets and resampling preclude a clean equal-budget causal interpretation.',
       'token_cap_counts':dict(collections.Counter(str(r['request'].get('max_tokens',r['request'].get('max_completion_tokens'))) for r in outputs)),
       'policies_note':'Exclusive relation is the number-provenance proxy; it can include arithmetic/other mistakes and is not independently verified unsupported-relation prevalence. Independent labels may overlap.',
       'conditionals_and_abandoned':'Legal declared conditionals are separate; explicitly abandoned speculative errors are separate and excluded from main rates.'}
    cross=collections.Counter()
    for row in outputs:
        exclusive=flags(row,items[row['id']],POLICIES[0]);independent=flags(row,items[row['id']],POLICIES[1])
        if exclusive['relation'] and independent['relation']:cross['both_relation']+=1
        elif exclusive['relation']:cross['exclusive_only_relation']+=1
        elif independent['relation']:cross['independent_only_relation']+=1
        if exclusive['numeric']!=independent['numeric']:cross['numeric_policy_disagreement']+=1
    result['policy_cross_tab']=dict(cross)
    result.update(source_only_answerability_counts=dict(collections.Counter(r['annotation']['answerability'] if r['annotation'] else 'unknown' for r in source_audit['items'])),
        source_only_insufficient_subset={'source_count':len(insufficient),'output_count':len(diagnostic_subset),'metrics':subset_rates,
            'interpretation':'Diagnostic sensitivity based on a separate source-only GPT review. Not human-certified and not a replacement for the fixed full matrix.'},
        answerability_not_insufficient_cases=[r['case_number'] for r in source_audit['items'] if not r['annotation'] or r['annotation']['answerability']!='insufficient'])
    save(ROOT/'analysis_results.json',result)
    dest=HERE.parents[1]/'output/experiments/english150-20261116-expanded';dest.mkdir(parents=True,exist_ok=True)
    save(dest/'结果统计.json',result)
    with (dest/'150题可答性诊断.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['case_number','source_id','answerability','exact_value_identifiable','approximation_supported','supported_target_expression','missing_inputs_or_ambiguities','confidence','rationale','validation_issues']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for item in sorted(source_audit['items'],key=lambda r:r['case_number']):
            a=item['annotation'] or {};row={k:item.get(k) for k in fields};row.update({k:a.get(k) for k in fields if k not in ('case_number','source_id','validation_issues')});row['missing_inputs_or_ambiguities']=json.dumps(a.get('missing_inputs_or_ambiguities'),ensure_ascii=False);row['validation_issues']=json.dumps(item.get('validation_issues',[]));writer.writerow(row)
    with (dest/'分条件幻觉比例.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['policy','group','n','wrong_answer','numeric','relation','both','numeric_rate','relation_rate','h1_relation_share_among_wrong','correct_refusal','valid_conditional','other_error','abandoned_any','uncertain']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for policy,summary in summaries.items():
            for key,m in summary.items():writer.writerow({name:policy if name=='policy' else key if name=='group' else m['n_all_nominal_unanswerable'] if name=='n' else m[name] for name in fields})
    with (dest/'2700条逐项评审.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['case_number','source_id','provider','mode','method','question_english','generation_status','response_type','response_category','evaluation_state','wrong_answer','numeric_hallucination','relational_hallucination','outside_document_input_number','other_error','correct_refusal','correct_refusal_primary','valid_declared_conditional','abandoned_numeric_issue','abandoned_relational_issue','confidence','rationale','validation_issues','review_unresolved','internal_recheck_issues','response','visible_trace','execution']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in sorted(outputs,key=lambda r:(r['case_number'],r['provider'],r['mode'],r['method'])):
            item=items[row['id']];a=item.get('annotation') or {};lab=a.get('labels',{});out={k:row.get(k) for k in fields}
            if not a or item.get('validation_issues'):category='unknown'
            elif a['valid_declared_conditional']:category='valid_conditional'
            elif lab.get('correct_refusal') and a['response_type']=='refusal':category='correct_refusal'
            elif lab.get('wrong_answer'):category='wrong_answer'
            elif lab.get('other_error'):category='other_error'
            elif a['response_type']=='answer':category='answer_not_marked_wrong'
            else:category='other'
            state='unrated' if not a or item.get('validation_issues') or a.get('response_type')=='unfinished' else 'provisional_review_unresolved' if item.get('review_unresolved') else 'low_confidence_or_ambiguous' if a.get('confidence')=='low' or a.get('definition_ambiguous') else 'machine_judged'
            out.update(question_english=source_map[row['source_id']]['modified']['question'],generation_status=row['status'],response_type=a.get('response_type'),
                       response_category=category,evaluation_state=state,correct_refusal_primary=category=='correct_refusal',
                       **{k:lab.get(k) for k in ('wrong_answer','numeric_hallucination','relational_hallucination','outside_document_input_number','other_error','correct_refusal')},
                       **{k:a.get(k) for k in ('valid_declared_conditional','abandoned_numeric_issue','abandoned_relational_issue','confidence','rationale')},
                       validation_issues=json.dumps(item['validation_issues']),review_unresolved=item.get('review_unresolved',False),internal_recheck_issues=json.dumps(item.get('internal_recheck',{}).get('validation_issues',[])),response=row.get('content'),visible_trace=row.get('reasoning_content'),execution=json.dumps(row.get('execution'),ensure_ascii=False))
            writer.writerow(out)
    print(json.dumps({'overall':{p:summaries[p]['overall'] for p in POLICIES},'destination':str(dest)},ensure_ascii=False),flush=True)
    return result

if __name__=='__main__':main()
