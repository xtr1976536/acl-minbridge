"""Two-round AI review set; source and complete mutation audit are retained.

This is a human-review deliverable, not an assertion of two human sign-offs.
"""
from __future__ import annotations
import ast,copy,hashlib,html,json,math,re,sys,difflib
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

HERE=Path(__file__).resolve().parent
PILOT=HERE.parent
sys.path.insert(0,str(PILOT))
from prepare import digest

NUM=re.compile(r'(?<![A-Za-z\d])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?![A-Za-z\d])')
YEAR=re.compile(r'\b(?:19|20)\d{2}\b')
MARK='[not disclosed]'
STOP=set('the a an of and in for to on at as by with net total year ended balance company million millions thousand thousands dollars dollar value amount'.split())


def clean(s):
    s=html.unescape(re.sub(r'<[^>]+>','',str(s)))
    s=re.sub(r"\b(\w+) 2019s\b",r"\1's",s)
    s=s.replace('201c','"').replace('201d','"').replace('a0 ',' ')
    s=re.sub(r'20ac(?=\d)','€',s)
    # Hex-2013 is an en dash in FinQA's normalized day ranges, not year 2013.
    month=r'(?:january|february|march|april|may|june|july|august|september|october|november|december)'
    s=re.sub(r'\b('+month+r'\s+\d{1,2})\s+2013\s+(\d{1,2})(?!\d)',r'\1-\2',s,flags=re.I)
    return s


def view(row):
    return {'question':clean(row['qa']['question']),
            'pre_text':[clean(t) for t in row['pre_text']],
            'table':[[clean(c) for c in r] for r in row['table_ori']],
            'post_text':[clean(t) for t in row['post_text']]}


def units(v):
    for k in ['pre_text','post_text']:
        for i,s in enumerate(v[k]):yield f'{k}/{i}',s
    for i,r in enumerate(v['table']):
        for j,s in enumerate(r):yield f'table/{i}/{j}',s


def tokens(s):return set(re.findall(r'[a-z]{3,}',s.lower()))-STOP


def row_map(row):
    old=row['table'];new=row['table_ori'];mapping={}
    def canonical(s):return re.sub('[^a-z0-9]','',clean(s).lower())
    for i,r in enumerate(old):
        scores=[]
        ov=set(re.findall(r'\d+(?:\.\d+)?',' '.join(r[1:]).replace(',','')))
        for j,n in enumerate(new):
            nv=set(re.findall(r'\d+(?:\.\d+)?',' '.join(n[1:]).replace(',','')))
            label=difflib.SequenceMatcher(None,canonical(r[0]),canonical(n[0])).ratio()
            value=len(ov&nv)/max(1,len(ov|nv))
            scores.append((label*5+value*3,j))
        mapping[i]=max(scores)[1]
    return mapping


def financial_numbers(s,table=False):
    result=[]
    for m in NUM.finditer(s):
        raw=m[0];val=Decimal(raw.replace(',',''))
        left=s[max(0,m.start()-45):m.start()].lower();right=s[m.end():m.end()+35].lower()
        if not table:
            # PDF artifacts, filing identifiers, note/page numbers and dates are
            # not quantitative financial facts under the declared inventory.
            if val==val.to_integral_value() and (1800<=abs(val)<=2200 or abs(val) in [20132014,2016201520142013]):
                amount_context=(bool(re.search(r'[$€£]\s*$',left)) or
                    bool(re.match(r'\s*(?:million|billion|thousand|rigs|employees|vehicles|shares|acres|barrels)\b',right)) or
                    bool(re.search(r'(?:rig count|number of (?:rigs|employees|vehicles|shares))\s*(?:was|of|is|were|totaled)?\s*$',left)))
                if not amount_context:continue
            if m.start()<=2 and re.match(r'^\s*\(?\d{1,3}\)?\s*[.)|:]?\s*[A-Za-z]',s):
                if not re.match(r'\s*(?:million|billion|thousand|percent|years|months|days|employees|vehicles|shares|acres|barrels|units|properties|rigs|stations|facilities|ships|trucks|people)\b',right):continue
            if re.search(r'(?:note|item|page|section|statement|sfas|fas|level|part|exhibit|form)\s*$',left):continue
            if re.search(r'(?:s\s*&\s*p|russell|mid\s*cap|ftse|fasb|codification)\s*$',left):continue
            if re.search(r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s*$',left):continue
            if re.search(r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\s*[-–]\s*$',left):continue
            if right.lstrip().startswith(('-k','-q','( k','(k')):continue
            # Footnote indices and isolated page/section numbers.
            if re.fullmatch(r'\s*\(?\d+\)?\s*[.:]?\s*',s):continue
            if left.rstrip().endswith('(') and right.lstrip().startswith(')') and not re.search(r'[$%]|million|thousand|billion',s):continue
        if result:
            prev=result[-1]
            gap=s[prev['end']:m.start()]
            if abs(prev['value'])==abs(val) and len(gap)<9 and not re.search('[A-Za-z]',gap):
                # FinQA duplicated percent/negative surface form, not two facts.
                prev['end']=m.end();continue
        percent=('%' in right[:4] or 'percent' in right[:12])
        scale=Decimal(1)
        if not percent:
            for w,v in [('billion',1_000_000_000),('million',1_000_000),('thousand',1000)]:
                if re.match(r'\s*'+w,right):scale=Decimal(v);break
        if left.rstrip().endswith('(') and right.lstrip().startswith(')'):val=-abs(val)
        result.append({'start':m.start(),'end':m.end(),'raw':raw,'value':val,'scale':scale,'percent':percent})
    return result


def inventory(v,header_rows=1):
    facts=[];table_facts=[];locs={};table=v['table']
    captions=' '.join(table[0]) if table else ''
    table_scale=Decimal(1)
    all_text=' '.join(v['pre_text'][-5:]+v['post_text'][:1])
    # Prefer explicit table units, then a nearby source statement.
    explicit=[(word,scale) for word,scale in [('billion',10**9),('million',10**6),('thousand',1000)] if word in captions.lower()]
    if explicit:table_scale=Decimal(explicit[0][1])
    else:
        for word,scale in [('billion',10**9),('million',10**6),('thousand',1000)]:
            if 'in '+word in all_text.lower():table_scale=Decimal(scale);break
    for r,row in enumerate(table):
        if r<header_rows:
            # Normalized FinQA sometimes folds an opening-balance data row
            # into its header. Original monetary cells remain genuine facts.
            def is_amount_cell(s):
                if not re.fullmatch(r'\s*[$€£%()\-+\d,.\s]+\s*',s):return False
                if re.fullmatch(r'\s*(?:19|20)\d{2}\s*',s):return False
                return bool(re.search(r'\d',s))
            if not any(is_amount_cell(s) for s in row[1:]):continue
        for c,s in enumerate(row):
            if c==0:continue
            if r==0:
                # Usually header, except vertical two-column value tables.
                if any(YEAR.search(x) for x in row[1:]) or not re.fullmatch(r'\s*[$€£(\-\d,. )]+\s*',s):continue
            header=table[0][c] if c<len(table[0]) else ''
            if re.search('expires|expiration|period ends|year in which',header,re.I):continue
            if re.search(r'\bdate\b',header,re.I) and not re.search('fair.value|price|grant',header,re.I):continue
            if re.fullmatch(r'\s*(?:19|20)\d{2}(?:\s*[-–]\s*(?:19|20)\d{2})?\s*',s) and re.search('year|state|country',row[0],re.I):continue
            ns=financial_numbers(s,True)
            for k,n in enumerate(ns):
                if r==0 and 1900<=abs(n['value'])<=2100:continue
                percent=n['percent'] or '%' in header or ('ratio' in header.lower() and 'exposure' in header.lower())
                scale=Decimal(1) if percent or re.search('per.share|risk.free|volatility|yield|life|interest rate',row[0],re.I) else table_scale
                # Scope/location is retained even when another cell has the same number.
                f={'fact_id':f'F{len(facts)+1:03}','kind':'table','metric':row[0],
                   'period_or_scope':header or f'row {r}', 'value':str(n['value']),
                   'scale':str(scale),'percent':percent,
                   'locations':[{'location':f'table/{r}/{c}','start':n['start'],'end':n['end'],'original':s[n['start']:n['end']]}]}
                facts.append(f);table_facts.append(f);locs[(f'table/{r}/{c}',n['start'])]=f
    repeated={}
    for path,s in units(v):
        if path.startswith('table/'):continue
        quantities=financial_numbers(s)
        table_echo=bool(quantities) and len(tokens(s))<=5 and all(
            any(abs(Decimal(f['value']))==abs(n['value']) for f in table_facts) for n in quantities)
        years=list(dict.fromkeys(YEAR.findall(s)))
        for k,n in enumerate(quantities):
            canonical=re.sub(r'\s+',' ',s).strip().lower()
            key=(canonical,n['start'],str(n['value']))
            location={'location':path,'start':n['start'],'end':n['end'],'original':s[n['start']:n['end']]}
            if key in repeated:
                repeated[key]['locations'].append(location);continue
            context=s[max(0,n['start']-110):n['end']+100]
            near_years=YEAR.findall(context)
            year=years[k] if len(years)==len(quantities) else (near_years[-1] if len(set(near_years))==1 else '')
            candidates=[]
            for f in table_facts:
                fv=abs(Decimal(f['value']));nv=abs(n['value'])
                if bool(f['percent'])!=bool(n['percent']):continue
                exact=(fv==nv)
                fs=Decimal(f['scale']);ns=n['scale']
                if ns==1 and not n['percent']:ns=fs
                # Rounded million/thousand restatements may describe the same fact.
                places=max(0,-n['value'].as_tuple().exponent)
                tolerance=ns*Decimal(10)**(-places)/2
                rounded=(abs(fv*fs-nv*ns)<=tolerance)
                if not (exact or rounded):continue
                overlap=len(tokens(context)&tokens(f['metric']+' '+f['period_or_scope']+' '+captions))
                metric_words=tokens(f['metric'])
                if metric_words and not (tokens(context)&metric_words) and not table_echo:continue
                if table_echo and exact:overlap=max(overlap,2)
                if overlap<1:continue
                scope=f['period_or_scope']+' '+f['metric']
                score=overlap*3 + (4 if year and year in scope else 0)
                if year and YEAR.search(scope) and year not in scope:score-=8
                candidates.append((score,f))
            candidates.sort(key=lambda x:-x[0])
            # Do not merge different metrics/periods just because numeric values agree.
            if candidates and candidates[0][0]>=3 and (len(candidates)==1 or candidates[0][0]>candidates[1][0]):
                f=candidates[0][1];f['locations'].append(location)
                f.setdefault('equivalence_basis',[]).append('matching quantity/unit and metric/period context; AI review')
            else:
                f={'fact_id':f'F{len(facts)+1:03}','kind':'text','metric':s[max(0,n['start']-85):n['end']+85],
                   'period_or_scope':year or path,'value':str(n['value']), 'scale':str(n['scale']),
                   'percent':n['percent'],'locations':[location]}
                facts.append(f)
            repeated[key]=f
    # Quantified assumptions stated in the question are part of the known
    # information, but may never be deleted. Do not count date numerals.
    q=v['question']
    for n in financial_numbers(q):
        near=q[max(0,n['start']-3):n['end']+18]
        if not (n['percent'] or '$' in near or re.search('million|billion|dollar',near,re.I)):continue
        loc={'location':'question','start':n['start'],'end':n['end'],'original':q[n['start']:n['end']]}
        candidates=[f for f in facts if Decimal(f['value'])==n['value'] and bool(f['percent'])==n['percent']
                    and len(tokens(q)&tokens(f['metric']))>=2]
        if len(candidates)==1:candidates[0]['locations'].append(loc)
        else:
            facts.append({'fact_id':f'F{len(facts)+1:03}','kind':'question','metric':'Question-specified assumption: '+q,
                          'period_or_scope':'question','value':str(n['value']),'scale':str(n['scale']),
                          'percent':n['percent'],'locations':[loc]})
    return facts


def select_facts(facts,targets,locations,patterns,v):
    wanted=set();paths=dict(units(v))
    for f in facts:
        if any(l['location']=='question' for l in f['locations']):continue
        for loc in f['locations']:
            path=loc['location']
            vals=financial_numbers(paths[path],path.startswith('table/'))
            rawval=next((n['value'] for n in vals if n['start']<=loc['start']<n['end']),Decimal(f['value']))
            if path in locations or any(abs(rawval)==abs(Decimal(str(t))) for t in targets):wanted.add(f['fact_id'])
            if not path.startswith('table/') and any(re.search(p,paths[path],re.I) for p in patterns):wanted.add(f['fact_id'])
    return wanted


def mutate(v,facts,wanted):
    out=copy.deepcopy(v);edits=[];changes=defaultdict(list)
    for f in facts:
        if f['fact_id'] in wanted:
            for loc in f['locations']:changes[loc['location']].append({**loc,'fact_id':f['fact_id']})
    for path,spans in changes.items():
        parts=path.split('/');parent=out[parts[0]]
        for p in parts[1:-1]:parent=parent[int(p)]
        idx=int(parts[-1]);old=parent[idx]
        # One-quantity table cell: replace the whole surface form, including $/().
        cell_facts={f['fact_id'] for f in facts for l in f['locations'] if l['location']==path}
        if path.startswith('table/') and cell_facts<=wanted:
            parent[idx]=MARK
            edits.append({'location':path,'original':old,'replacement':MARK,'fact_ids':sorted(cell_facts)})
        else:
            text=old
            for span in sorted(spans,key=lambda x:x['start'],reverse=True):
                text=text[:span['start']]+MARK+text[span['end']:]
            # FinQA repeats a percentage as "x% ( x % )"; the joined numeric
            # span consumes its opening parenthesis, so close that surface form.
            text=re.sub(re.escape(MARK)+r'\s*%\s*\)',MARK+'%',text)
            parent[idx]=text
            edits.append({'location':path,'original':old,'replacement':text,'fact_ids':sorted({s['fact_id'] for s in spans})})
    return out,edits


def expression(program):
    vals=[]
    for op,argstring in re.findall(r'([a-z_]+)\(([^()]*)\)',program):
        args=[]
        for a in argstring.split(','):
            a=a.strip()
            if a.startswith('#'):a=vals[int(a[1:])]
            elif a.startswith('const_'):a=a[6:].replace('_','.')
            elif a.endswith('%'):a=f'({a[:-1]}/100)'
            args.append(a)
        if len(args)==2 and op in ['add','subtract','multiply','divide','greater','exp']:
            sym={'add':'+','subtract':'-','multiply':'*','divide':'/','greater':'>','exp':'**'}[op]
            vals.append(f'({args[0]} {sym} {args[1]})')
    return vals[-1] if vals else program


def build():
    old=json.loads((PILOT/'local/test_disjoint_review_batch_150_scanned.json').read_text())
    raw={r['id']:r for r in json.loads((PILOT/'local/raw/train.json').read_text())}
    manual=json.loads((HERE/'manual_review.json').read_text())
    test=json.loads((PILOT.parent/'gbfr/data/raw/official/FinQA.json').read_text())
    protected={'/'.join(r['filename'].split('/')[:2]) for r in test}
    special_overrides={'35':508,'111':265.06,'129':42,'132':23,'133':551539,'141':1415,'150':24.0}
    entries=[]
    for i,d in enumerate(old['drafts'],1):
        key=str(i);rep=manual['replacements'].get(key)
        source_id=rep[0] if rep else d['source_id'];row=raw[source_id]
        v=view(row);mapping=row_map(row)
        first=row['table'][0]
        is_vertical=(len(first)==2 and re.fullmatch(r'\s*[$€£(\-\d,. )]+\s*',first[1]) and not YEAR.search(first[1]))
        headers=0 if is_vertical else mapping.get(1,1)
        facts=inventory(v,headers)
        target=special_overrides.get(key,manual['target_overrides'].get(key,Decimal(d['removed_operand_hint'])))
        targets=[target]+manual['extra_values'].get(key,[])
        # Target changes noted during direct review.
        if i==105:targets=[63]
        if i==112:targets.append(1.9)
        if i==132:targets=[]  # exact product/period cells, not every occurrence of 23%.
        locations=[]
        for loc in manual['extra_locations'].get(key,[]):
            _,r,c=loc.split('/');locations.append(f'table/{mapping[int(r)]}/{c}')
        if i==76:targets.append(138.6)
        if i in [14,150]:
            targets=[]
            locations+=['table/5/2'] if i==14 else ['table/1/2']
        if i==87:
            targets=[target]
            patterns=manual['text_patterns'].get(key,[])+['coatings sales increased']
        elif i==124:
            targets=[target,171]
            patterns=manual['text_patterns'].get(key,[])+['total other income and expense decreased']
        else:patterns=manual['text_patterns'].get(key,[])
        wanted=select_facts(facts,targets,locations,patterns,v)
        # A conservative second-round guard: if a deleted table quantity has
        # an unmerged textual restatement, remove that disclosure too rather
        # than rely on a fragile local-context match across PDF fragments.
        selected_table=[f for f in facts if f['fact_id'] in wanted and f['kind']=='table']
        for f in facts:
            if f['kind']!='text' or f['fact_id'] in wanted:continue
            if any(l['location']=='question' for l in f['locations']):continue
            for tf in selected_table:
                same_raw=abs(Decimal(f['value']))==abs(Decimal(tf['value']))
                same_units=(bool(f['percent'])==bool(tf['percent']))
                if same_raw and same_units:
                    wanted.add(f['fact_id']);break
        # The explicitly equated EUR/USD amounts are two disclosures of the
        # same transaction-price fact, not two independently deleted prices.
        if i==47:
            ps=[f for f in facts if f['fact_id'] in wanted and abs(Decimal(f['value'])) in [253,343]]
            if len(ps)==2:
                keep,drop=ps
                keep['locations']+=drop['locations'];keep['equivalence_basis']=['same cash consideration explicitly restated in EUR and USD in one sentence']
                wanted.discard(drop['fact_id']);facts.remove(drop)
        if not wanted:raise ValueError(('No deleted fact',i,source_id))
        n=len(facts);m=len(wanted)
        correction=manual['corrections'].get(key)
        formula=correction[0] if correction else expression(row['qa']['program'])
        if i==3:formula='((20.9-20.2)/20.2, (21.3-20.9)/20.9)'
        note=manual['special_notes'].get(key,'缺失的目标输入在其他指标、其他期间或估值参数中没有合法的唯一替代；不能用近邻值或外部数据补设。')
        entries.append({'number':i,'source_id':source_id,'previous_source_id':d['source_id'],
                        'report_id':'/'.join(row['filename'].split('/')[:2]),'source_sha256':digest(row),
                        'source_question_raw':row['qa']['question'],
                        'original':v,'facts':facts,'source_table_header_rows':headers,'base_deleted_fact_ids':sorted(wanted),
                        'base_ratio':m/n,'original_fact_count':n,'formula':formula,
                        'original_gold_program_private':row['qa']['program'],
                        'reference_correction':correction[1] if correction else None,
                        'replacement_reason':rep[1] if rep else None,
                        'ai_direct_reason_zh':note,
                        'round1':{'type':'program audit plus AI direct source assessment',
                                  'original_draft_accepted_without_change':False,
                                  'finding':note,'source_replacement':bool(rep)},
                        'human_reviews':[]})
    assert len({e['source_id'] for e in entries})==150
    assert len({e['report_id'] for e in entries})==150
    assert not ({e['report_id'] for e in entries}&protected)
    # Assign by base deletion ratio before any model outputs, then enlarge the
    # medium/high deletions to produce disjoint observed ratio ranges.
    order=sorted(entries,key=lambda e:(e['base_ratio'],e['number']))
    low,medium,high=order[:90],order[90:120],order[120:]
    low_max=max(e['base_ratio'] for e in low)
    mid_floor=min(.65,low_max+.06)
    for e in medium:
        e['target_fraction']=max(e['base_ratio'],mid_floor)
    mid_max=max(math.ceil(e['target_fraction']*e['original_fact_count'])/e['original_fact_count'] for e in medium)
    high_floor=min(.90,mid_max+.08)
    for e in high:e['target_fraction']=max(e['base_ratio'],high_floor)
    for group,items in [('low',low),('medium',medium),('high',high)]:
        for e in items:
            e['severity']=group;wanted=set(e['base_deleted_fact_ids'])
            target_n=math.ceil(e.get('target_fraction',e['base_ratio'])*len(e['facts']))
            # Additional removals cannot restore a uniquely identified target.
            # Prefer table facts in the same target metric, then nearby table facts,
            # then text facts. All are counted and listed, never hidden padding.
            deleted_metrics={f['metric'] for f in e['facts'] if f['fact_id'] in wanted}
            rest=sorted((f for f in e['facts'] if f['fact_id'] not in wanted),
                        key=lambda f:(0 if f['metric'] in deleted_metrics else 1,
                                      0 if f['kind']=='table' else 1,f['fact_id']))
            for f in rest:
                if any(l['location']=='question' for l in f['locations']):continue
                if len(wanted)>=target_n:break
                wanted.add(f['fact_id'])
            e['deleted_fact_ids']=sorted(wanted);e['deleted_fact_count']=len(wanted)
            e['deletion_ratio']=len(wanted)/len(e['facts'])
            e['modified'],e['edits']=mutate(e['original'],e['facts'],wanted)
            e['modified_sha256']=digest(e['modified'])
            e['round2']={'type':'second pass by the same AI assistant, not a second human',
                         'question_unchanged':e['modified']['question']==e['original']['question'],
                         'report_disjoint_from_official_test':e['report_id'] not in protected,
                         'deleted_positions_reproducible':True,
                         'deleted_equivalent_mentions':sum(len(f['locations']) for f in e['facts'] if f['fact_id'] in wanted),
                         'reason':e['ai_direct_reason_zh'],
                         'status':'AI-reviewed exact-answer non-identifiability; human confirmation pending'}
    ranges={g:[min(e['deletion_ratio'] for e in entries if e['severity']==g),max(e['deletion_ratio'] for e in entries if e['severity']==g)] for g in ['low','medium','high']}
    assert ranges['low'][1]<ranges['medium'][0] and ranges['medium'][1]<ranges['high'][0],ranges
    bundle={'status':'final_150_for_human_review_after_two_AI_rounds_not_human_gold',
            'count':150,'groups':{'low':90,'medium':30,'high':30},'ratio_ranges':ranges,
            'ratio_denominator':'all distinct explicitly quantified financial/operating facts in original visible evidence and question-specified assumptions; dates, note/page indices and conversion constants excluded',
            'fact_equivalence':'same metric/entity/period/unit; repeated paragraphs and context-matched table/text restatements merged; ledger retained for reviewer correction',
            'strata_rule':'rank initial support-cut ratios, take 90/30/30; enlarge middle/high deletions before outcomes so actual ranges do not overlap; no claim of globally minimal cuts or causal severity effect',
            'source_normalization':'original table_ori displayed; normalized table artifacts 2013/2014 that encode dash characters are not treated as financial values. Text and question otherwise retained with typographic cleanup only.',
            'records':entries}
    (HERE/'final_150_review.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2))
    summary={'count':150,'groups':bundle['groups'],'ratio_ranges':ranges,
             'replaced_sources':{e['number']:[e['previous_source_id'],e['source_id'],e['replacement_reason']] for e in entries if e['replacement_reason']},
             'corrected_references':{e['number']:e['reference_correction'] for e in entries if e['reference_correction']},
             'total_original_english_characters':sum(sum(len(s) for _,s in units(e['original'])) for e in entries),
             'human_reviews_completed':0,'model_calls':0}
    (HERE/'audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':build()
