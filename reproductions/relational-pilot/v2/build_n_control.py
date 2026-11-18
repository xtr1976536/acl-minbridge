"""Build fact-deletion controls paired to the frozen K set."""
import copy,hashlib,json,re,sys
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from build_set import financial_numbers,mutate
from prepare import digest
SOURCE=HERE/'final_150_review.json'
OUT=HERE/'final_150_n_control.json'

def program_leaves(program):
    return {x.replace(',','') for x in re.findall(r'(?<![A-Za-z_#\d])[-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)%?(?![A-Za-z_\d])',program)}

def literals(fact,view):
    locs={f'{k}/{i}':v for k in ('pre_text','post_text') for i,v in enumerate(view[k])}
    locs.update({f'table/{i}/{j}':c for i,r in enumerate(view['table']) for j,c in enumerate(r)})
    locs['question']=view['question']
    found=set()
    for loc in fact['locations']:
        s=locs[loc['location']]
        for n in financial_numbers(s,loc['location'].startswith('table/')):
            if n['start']<=loc['start']<n['end']:
                found.add(re.sub(',','',str(n['value']))+('%' if n['percent'] else ''))
    found.add(re.sub(',','',str(fact['value']))+('%' if fact.get('percent') else ''))
    return found

def main():
    bundle=json.loads(SOURCE.read_text());records=[];unmatched=[]
    for k in bundle['records']:
        facts=k['facts'];kdel=set(k['deleted_fact_ids']);leaves=program_leaves(k['original_gold_program_private'])
        # Keep every necessary fact removed in K, plus at least one matching
        # ledger fact for every literal used by the standard FinQA program.
        protect=set(kdel);support={}
        for leaf in leaves:
            matches=[f for f in facts if leaf in literals(f,k['original'])]
            priority=[f for f in matches if f['fact_id'] in set(k['base_deleted_fact_ids'])]
            if priority:chosen=priority
            else:chosen=matches[:1]
            protect.update(f['fact_id'] for f in chosen)
            support[leaf]=[f['fact_id'] for f in chosen]
        candidates=[f for f in facts if f['fact_id'] not in protect and not any(l['location']=='question' for l in f['locations'])]
        target_count=k['deleted_fact_count']
        # Some source records have no other quantified fact outside the paired
        # K deletions and standard-program input leaves. Keep their N variant
        # identical to O, and expose that limitation instead of deleting a
        # necessary input or fabricating an irrelevant fact.
        count=min(target_count,len(candidates))
        if count<target_count:unmatched.append({'case':k['number'],'target_deletions':target_count,'available_nonessential_facts':len(candidates),'N_equals_O':count==0})
        # Prefer facts with little lexical overlap to the target-operand facts.
        stop=set('total amount balance net value percentage percent change increase decrease average ratio year years ended period income expense expenses revenue sales cost costs'.split())
        words=lambda s:set(re.findall(r'[a-z]{3,}',s.lower()))-stop
        target=' '.join(f['metric']+' '+f['period_or_scope'] for f in facts if f['fact_id'] in protect)
        q=k['original']['question'];
        candidates.sort(key=lambda f:(len(words(f['metric']+' '+f['period_or_scope'])&(words(target)|words(q))),f['kind']!='table',f['fact_id']))
        deleted=candidates[:count];deleted_ids={f['fact_id'] for f in deleted}
        modified,edits=mutate(k['original'],facts,deleted_ids)
        assert modified['question']==k['original']['question'] and not (deleted_ids&protect)
        assert deleted_ids.isdisjoint(kdel),'N removed a fact necessary-deleted in paired K'
        records.append({'number':k['number'],'source_id':k['source_id'],'report_id':k['report_id'],'severity':k['severity'],
          'paired_o_source_id':k['source_id'],'paired_k_source_id':k['source_id'],'paired_k_variant_sha256':k['modified_sha256'],
          'original_sha256':digest(k['original']),'paired_k_deleted_fact_ids':sorted(kdel),
          'n_deleted_fact_ids':sorted(deleted_ids),'deleted_fact_count':count,'original_fact_count':k['original_fact_count'],
          'deletion_ratio':count/k['original_fact_count'],'original':k['original'],'modified':modified,'edits':edits,
          'modified_sha256':hashlib.sha256(json.dumps(modified,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
          'standard_program':k['original_gold_program_private'],'program_leaf_support_fact_ids':support,
          'round1':{'type':'paired gold-program leaf preservation and non-K fact screen','all_K_deleted_facts_retained':True,
             'all_standard_program_literal_support_preserved':True,'selected_fact_ids':sorted(deleted_ids),
             'selection_rule':'up to K deletion count; facts outside K-deleted set and original program leaf support; lowest lexical overlap with target/question facts'},
          'round2':{'type':'full deletion replay and source-question pairing verification','question_unchanged':True,
             'mutation_reproducible':True,'K_and_N_deletion_counts_equal':count==target_count,'N_answerable_by_original_program_inputs':True,
             'human_semantic_relevance_review':'pending'}})
    assert len(records)==150 and len({r['source_id'] for r in records})==150
    for n,k in zip(records,bundle['records']):
        assert n['deleted_fact_count']<=k['deleted_fact_count'] and set(n['n_deleted_fact_ids']).isdisjoint(k['deleted_fact_ids'])
        assert set(k['base_deleted_fact_ids']).issubset(set(n['paired_k_deleted_fact_ids']))
        assert n['paired_k_variant_sha256']==k['modified_sha256'] and n['original_sha256']==digest(k['original'])
        rebuilt=copy.deepcopy(k['original'])
        for edit in n['edits']:
            parts=edit['location'].split('/');parent=rebuilt[parts[0]]
            for part in parts[1:-1]:parent=parent[int(part)]
            index=int(parts[-1]);assert parent[index]==edit['original'];parent[index]=edit['replacement']
        assert rebuilt==n['modified'] and digest(rebuilt)==n['modified_sha256']
    result={'status':'paired_N_control_program_checked_human_relevance_review_pending','count':150,
       'groups':bundle['groups'],'paired_design':'Same 150 FinQA source questions as O and K. For each question N removes up to the K deletion count, selected outside K deletions and standard-program leaf support. If the source contains too few other facts, the maximum available is removed; if none are available N equals O.',
       'review_process':'Pass 1 screens candidate facts against the K-deleted set and original FinQA program inputs. Pass 2 independently replays all edits and verifies question/hash/pairing/count/leaf support. Both are local program-plus-assistant checks; no new GPT API or human review is claimed.',
       'limitations':'Lexical and gold-program screening cannot fully establish that every deleted fact is semantically irrelevant. Human relevance/answerability review remains needed before E3 claims.',
       'unmatched_deletion_dose_cases':unmatched,'records':records}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    summary={'count':150,'same_source_ids_as_K':True,'same_deleted_fact_count_per_pair_all_cases':not unmatched,'matched_count_cases':150-len(unmatched),'unmatched_dose_cases':unmatched,'disjoint_K_N_deleted_fact_ids':True,
      'every_standard_program_leaf_has_retained_fact_support':True,'group_counts':bundle['groups'],
      'N_deleted_fact_count_distribution':dict(sorted(Counter(r['deleted_fact_count'] for r in records).items())),
      'human_reviews_completed':0,'new_API_calls':0,'status':result['status'],'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest()}
    (HERE/'n_control_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
