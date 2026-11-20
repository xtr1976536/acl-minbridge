"""FinDER fact-deletion candidates, matching the FinQA pilot protocol.

No API calls. Upstream answers are audit-only and never enter model inputs.
The arithmetic screens are conservative finite checks, not human gold labels.
"""
from __future__ import annotations
import argparse, copy, csv, hashlib, json, math, re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'data/finder150/local/upstream.parquet'
REVISION = 'c4c1b6454aef7f0bb1c37235c7f52ce644642da0'
MARK = '[not disclosed]'
NUM = re.compile(r'(?<![\w.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?=$|[^\w.]|[KMBkmb](?![A-Za-z]))')
EXPR_NUM = r'[-+]?\d[\d,]*(?:\.\d+)?'
EXPR = re.compile(r'('+EXPR_NUM+r')\s*(?:million|billion|thousand)?\s*([+×÷*/−–-])\s*\$?\s*('+EXPR_NUM+r')', re.I)
YEAR = re.compile(r'\b(?:19|20)\d{2}\b')
MONTH = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember|t)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?'
STOP = set('the a an and of for to in at on net total as year years ended income expense expenses revenue revenues cost costs million millions thousand thousands dollars dollar amount financial'.split())

def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def dec(s):
    return Decimal(str(s).replace(',','').replace('−','-'))

def norm(v):
    return str(v.normalize()) if v else '0'

def words(s):
    return set(re.findall(r'[a-z]{3,}',s.lower())) - STOP

def numeric_spans(s):
    """Financial/operating quantities; exclude dates, labels and unit constants."""
    for m in NUM.finditer(s):
        v=dec(m[0]);left=s[max(0,m.start()-65):m.start()];right=s[m.end():m.end()+50]
        line_start=s.rfind('\n',0,m.start())+1
        line_end=s.find('\n',m.end());line_end=len(s) if line_end<0 else line_end
        line=s[line_start:line_end]
        currency=bool(re.search(r'[$€£]\s*$',left))
        quantity_unit=bool(re.match(r'\s*(?:million|billion|thousand|employees|associates|teammates|shares|workers|people|countries|locations|stores|drivers|engineers|percent|%)\b',right,re.I))
        if 1900<=abs(v)<=2100 and v==int(v) and ',' not in m[0] and not currency and not quantity_unit:
            continue
        if re.search(MONTH+r'\s*$',left,re.I) or re.match(r'\s*'+MONTH+r'\b',right,re.I) or re.search(r'\b(?:Note|Item|Page|Section|Form|Class|Level|Part)\s*$',left,re.I):
            continue
        if re.match(r'\s*[-/]\s*(?:\d{1,2}|20\d{2})(?:\b|/)',right) and re.search(r'(?:\b\d{1,2}[-/])?$',left[-4:]) and '/' in (left[-4:]+right[:8]):
            continue
        if re.search(r'(?:per|each)\s*$',left,re.I) and re.match(r'\s*(?:man.hours|hours|shares)\b',right,re.I):
            continue
        # Attached numbered footnotes, filing labels and list counters.
        if abs(v)<10 and v==int(v) and re.search(r'[A-Za-z]\($',left) and re.match(r'\s*\)',right):
            continue
        if re.search(r'\b(?:S&P|Fortune|Russell|Section|ASC)\s*$',left,re.I):
            continue
        if re.search(r'\b(?:EEO|ISO|IFRS|SFAS|FAS|IAS)[-\s]*$',left,re.I):
            continue
        if not currency and re.match(r'\s*[-–]?\s*(?:K|Q)\b',right) and abs(v)==10:
            continue
        if re.fullmatch(r'\s*\(?\d{1,3}\)?\s*[.)]\s+.*',line) and m.start()-line_start<4:
            continue
        # Accounting parentheses are part of the deleted numeric surface.
        start,end=m.span()
        if re.search(r'\(\s*$',left) and re.match(r'\s*\)',right):
            v=-abs(v);start=s.rfind('(',line_start,start);end=m.end()+re.match(r'\s*\)',right).end()
        yield {'start':start,'end':end,'raw':s[start:end],'value':norm(v),
               'percent':bool(re.match(r'\s*%',right) or re.match(r'\s*percent\b',right,re.I)),
               'line':line.strip(),'left':left,'right':right}

def inventory(view):
    facts=[];seen={}
    for ri,s in enumerate(view['references']):
        spans=list(numeric_spans(s));lines=s.splitlines(keepends=True);line_starts=[];offset=0
        for line in lines:line_starts.append((offset,line));offset+=len(line)
        last_label='';row_counter=0;within_row=0
        periods=list(dict.fromkeys(YEAR.findall(s[:min(len(s),1000)])))[:4]
        period_count=len(periods) if 1<=len(periods)<=4 else 0
        for n in spans:
            before=s[:n['start']];li=before.count('\n');line=lines[li] if li<len(lines) else ''
            line_prefix=s[line_starts[li][0]:n['start']]
            label_part=NUM.sub('',line_prefix).strip(' \t$€£()—–-,.%')
            if label_part and re.search('[A-Za-z]',label_part):
                label=label_part[-160:]
                if label!=last_label:row_counter+=1;within_row=0;last_label=label
            else:
                # Vertical extraction: the nearest preceding meaningful text is
                # the row label, even when separated by many empty lines.
                label=last_label
                for _,prev in reversed(line_starts[:li]):
                    p=prev.strip()
                    if not p or re.fullmatch(r'[\d\s,$€£().%+—–-]+',p):continue
                    if YEAR.fullmatch(p) or re.fullmatch(r'(?:In |in )?(?:millions|thousands).*',p):continue
                    label=p[-160:];break
                if label!=last_label:row_counter+=1;within_row=0;last_label=label
            period=periods[within_row%period_count] if period_count>1 else (periods[0] if periods else '')
            # Narrative scope is not fabricated from a table header.
            narrative=(len(n['line'])>180 or len(list(NUM.finditer(n['line'])))>6)
            if narrative:
                context=s[max(0,n['start']-100):n['end']+100]
                ys=list(dict.fromkeys(YEAR.findall(context)))
                period=ys[0] if len(ys)==1 else ''
                label=n['line'][:200]
            within_row+=1
            canonical_line=re.sub(r'\s+',' ',n['line']).strip()
            # Only exact repeated disclosures with the same local semantics
            # are merged; numeric equality alone NEVER merges distinct facts.
            # Within a narrative, separate mentions are not merged solely
            # because their surface value and sentence happen to match.
            occurrence=sum(1 for x in spans if x['start']<n['start'] and s.count('\n',0,x['start'])==li) if narrative else None
            key=(canonical_line,label,period,n['value'],n['percent'],occurrence)
            loc={'reference_index':ri,'start':n['start'],'end':n['end'],'original':n['raw']}
            if key in seen:
                seen[key]['locations'].append(loc);continue
            f={'fact_id':f'F{len(facts)+1:03d}','metric_or_context':label,
               'period_hint':period,'period_hint_is_heuristic':True,
               'value':n['value'],'percent':n['percent'],'locations':[loc]}
            seen[key]=f;facts.append(f)
    # Quantified assumptions explicitly supplied by the question are counted
    # and protected. Date numerals were excluded by numeric_spans.
    evidence_values={dec(f['value']) for f in facts}
    for n in numeric_spans(view['question']):
        qv=dec(n['value'])
        suffix=re.match(r'\s*([KMBkmb])\b',n['right'])
        if suffix:qv*=Decimal({'K':1000,'M':1000000,'B':1000000000}[suffix[1].upper()])
        if not (n['percent'] or qv in evidence_values or re.search(r'[$€£]|million|billion|thousand',n['left'][-4:]+n['raw']+n['right'][:15],re.I)):continue
        facts.append({'fact_id':f'F{len(facts)+1:03d}','metric_or_context':'Question-specified assumption',
                      'period_hint':'question','value':norm(qv),'percent':n['percent'],
                      'protected':True,'locations':[{'question':True,'start':n['start'],'end':n['end'],'original':n['raw']}]})
    return facts

def calc(a,op,b):
    return {'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b}[op]()

def choose_formula(row,facts):
    known={dec(f['value']) for f in facts if not f.get('protected')}
    options=[]
    for m in EXPR.finditer(row['answer']):
        a,b=dec(m[1]),dec(m[3]);op={'×':'*','÷':'/','−':'-','–':'-'}.get(m[2],m[2])
        if 1900<=abs(a)<=2100 and 1900<=abs(b)<=2100:continue
        if a not in known or b not in known or a==b or a==0 or b==0:continue
        if abs(a)==1 or abs(b)==1 or (abs(a)==100 and row['type']=='Division'):continue
        try:z=calc(a,op,b)
        except (ZeroDivisionError,InvalidOperation):continue
        expected={'Subtract':'-','Subtraction':'-','Addition':'+','Division':'/','Multiplication':'*'}.get(row['type'])
        # Upstream operator labels are not authoritative (some "Multiplication"
        # examples explicitly calculate a ratio).
        score=(op==expected)*3+(min(abs(a),abs(b))>10)*2-(m.start()/max(1,len(row['answer'])))
        options.append((score,m.start(),a,op,b,z))
    if not options:return None
    _,_,a,op,b,z=max(options,key=lambda x:(x[0],-x[1]))
    return {'a':norm(a),'op':op,'b':norm(b),'value':norm(z),'expression':f'({a}) {op} ({b})',
            'origin':'explicit arithmetic expression in upstream answer, independently assessed before acceptance',
            'scope':'numeric component of the unchanged source question; accompanying qualitative claims are not assigned numeric gold'}

def identity_graph(values):
    """Finite, conservative value-level inverse recovery screen.

    Equality of unrelated values adds constraints; it never licenses merging
    facts in the deletion denominator. Such extra constraints may over-delete.
    """
    edges=set();vs=sorted(values)
    for i,a in enumerate(vs):
        for b in vs[i:]:
            for c in (a+b,a-b,b-a):
                if c in values and len({a,b,c})>=2:edges.add(tuple(sorted({a,b,c})))
            # x*y=z is checked in both directions during closure.
            if a and b and abs(a)!=1 and abs(b)!=1:
                c=a*b
                if c in values and len({a,b,c})>=2:edges.add(tuple(sorted({a,b,c})))
    return sorted(edges)

def sum_edges(facts):
    """Screen contiguous table-line component sums up to eight operands."""
    groups=defaultdict(list)
    for f in facts:
        if not f.get('protected') and f.get('period_hint'):
            groups[f['period_hint']].append(dec(f['value']))
    values={dec(f['value']) for f in facts};edges=set()
    for vs in groups.values():
        for start in range(len(vs)):
            for size in range(3,min(8,len(vs)-start)+1):
                parts=vs[start:start+size];total=sum(parts)
                if total in values and total not in parts:
                    # Keep only sets of distinct operands: repeated values need
                    # coefficient-aware handling and are flagged for review.
                    if len(set(parts))==len(parts):edges.add(tuple(sorted(set(parts+[total]))))
    return sorted(edges)

def rounded_eps_edges(facts):
    """Also block EPS/income/share inversions within displayed rounding bounds.

    Currency/share scale factors are explicit screening constants, not facts.
    Broad matching is conservative; no claim of exact equality is made.
    """
    fs=[f for f in facts if not f.get('protected')]
    eps=[f for f in fs if 0<abs(dec(f['value']))<100 and re.search(r'per.share|basic|diluted',f['metric_or_context'],re.I)]
    ni=[f for f in fs if abs(dec(f['value']))>100 and re.search(r'net.*(?:income|earnings|profit)|earnings.*attributable|income.*(?:common|shareholder)|continuing.operations',f['metric_or_context'],re.I)]
    shares=[f for f in fs if abs(dec(f['value']))>100 and re.search(r'weighted|shares|basic|diluted',f['metric_or_context'],re.I)]
    edges=set()
    for e in eps:
        ev=dec(e['value']);et=Decimal('0.005')
        for n in ni:
            nv=dec(n['value'])
            for s in shares:
                sv=dec(s['value'])
                if sv<=0:continue
                for scale in (Decimal(1),Decimal(1000),Decimal(1000000)):
                    value=ev*sv/scale
                    tolerance=(abs(sv)*et+abs(ev)*Decimal('0.5'))/scale+Decimal('0.5')
                    if abs(value-nv)<=tolerance and len({ev,nv,sv})>=2:
                        edges.add(tuple(sorted({ev,nv,sv})))
    return sorted(edges)

def recover(known,edges):
    support={v:{v} for v in known};changed=True
    while changed:
        changed=False
        for e in edges:
            missing=[v for v in e if v not in support]
            if len(missing)==1:
                support[missing[0]]=set().union(*(support[v] for v in e if v in support));changed=True
    return support

def base_cut(row,facts,formula):
    byvalue=defaultdict(list)
    protected={dec(f['value']) for f in facts if f.get('protected')}
    for f in facts:
        if not f.get('protected'):byvalue[dec(f['value'])].append(f)
    a,b=dec(formula['a']),dec(formula['b']);z=dec(formula['value'])
    choices=[v for v in [a,b] if v not in protected]
    if not choices:return None
    target=min(choices,key=lambda v:(len(byvalue[v]),-abs(v)))
    deleted_values={target}
    # Remove direct numeric-answer disclosures too, if present.
    if z in byvalue and z not in protected:deleted_values.add(z)
    # Close answer restatements beyond the first binary subexpression: complete
    # sums, percentages and rounded results may already be disclosed in evidence.
    for n in numeric_spans(row['answer']):
        v=dec(n['value'])
        if v in byvalue and v not in [a,b] and v not in protected:deleted_values.add(v)
    values=set(byvalue)|protected
    edges=identity_graph(values)+sum_edges(facts)+rounded_eps_edges(facts)
    repairs=[]
    for _ in range(len(values)):
        known=values-deleted_values;support=recover(known,edges)
        exposed=[v for v in deleted_values if v in support]
        if not exposed:break
        candidates=Counter(v for x in exposed for v in support[x] if v not in protected)
        if not candidates:return None
        pick=min(candidates,key=lambda v:(len(byvalue[v])/candidates[v],-abs(v)))
        repairs.append({'recoverable_value':norm(exposed[0]),'additional_removed_value':norm(pick),
                        'reason':'close an arithmetic inverse/recovery route; may conservatively include numerical coincidences'})
        deleted_values.add(pick)
    else:return None
    deleted={f['fact_id'] for v in deleted_values for f in byvalue[v]}
    return {'target':norm(target),'deleted_ids':sorted(deleted),'deleted_values':sorted(map(norm,deleted_values)),
            'repairs':repairs,'edges':edges,'protected':protected}

def mutate(view,facts,deleted):
    result=copy.deepcopy(view);edits=[]
    for ri,s in enumerate(view['references']):
        spans={}
        for f in facts:
            if f['fact_id'] in deleted:
                for loc in f['locations']:
                    if not loc.get('question') and loc['reference_index']==ri:spans[(loc['start'],loc['end'])]=loc
        last=len(s)+1
        for (a,b),loc in sorted(spans.items(),reverse=True):
            assert b<=last and s[a:b]==loc['original'];last=a
            edits.append({**loc,'replacement':MARK});s=s[:a]+MARK+s[b:]
        result['references'][ri]=s
    return result,sorted(edits,key=lambda e:(e['reference_index'],e['start']))

def prepare():
    rows=pq.read_table(SOURCE).to_pylist();candidates=[];excluded=[]
    for i,row in enumerate(rows):
        if row['type'] not in ['Subtract','Subtraction','Addition','Division','Multiplication'] or not row['answer']:continue
        answer=row['answer'];q=row['text']
        if re.search(r'cannot be (?:answered|determined|calculated)|not (?:possible|enough)|insufficient|not provided|not provide|assuming|hypothetical|projected|forecast|\$[XYR]\b|\b[XYR] dollars',answer+' '+q,re.I) or re.search(r'\b(?:proj\.?|expected|estimate|forecast)\b|\+\s*\d+\s*pp',q,re.I):
            excluded.append({'index':i,'id':row['_id'],'reason':'upstream already insufficient, conditional, hypothetical, or forecasting target'});continue
        view={'question':q,'references':row['references']}
        facts=inventory(view)
        # Assistant-verified equivalences in the DexCom workforce disclosure:
        # narrative and table both give worldwide headcount; the ethnic-diversity
        # column explicitly covers US only, so its US and total cells restate
        # one fact. Gender subgroups remain distinct even when amounts coincide.
        if row['_id']=='1023e5b0':
            for value,basis in [('9600','same worldwide year-end headcount in narrative and grand-total table cell'),
                                ('3700','ethnic diversity is explicitly US-only; US and total cells repeat the same count')]:
                matches=[f for f in facts if dec(f['value'])==Decimal(value)]
                if len(matches)>1:
                    keep=matches[0];keep['equivalence_basis']=basis
                    for drop in matches[1:]:
                        keep['locations'].extend(drop['locations']);facts.remove(drop)
            for fi,f in enumerate(facts,1):f['fact_id']=f'F{fi:03d}'
        if row['_id']=='dc4687be':
            labels={'28000':'Cloud services and license support operations','37000':'Services',
                    '32000':'Sales and marketing','47000':'Research and development',
                    '3000':'Hardware','12000':'General and administrative'}
            for f in facts:
                key=str(int(dec(f['value']))) if dec(f['value'])==int(dec(f['value'])) else ''
                if key in labels:
                    f['metric_or_context']=labels[key]
                    f['period_hint']='2024'
                    f['assistant_label_correction']='source extraction lists employee count before its label'
        formula=choose_formula(row,facts)
        if not formula:continue
        cut=base_cut(row,facts,formula)
        if not cut:continue
        n=len(facts);k=len(cut['deleted_ids'])
        if n<3 or k>=n-1:continue
        candidate={'source_index':i,'source_id':row['_id'],'source_sha256':digest(row),
            'report_fingerprint':digest(row['references']),'original':view,'facts':facts,
            'source_answer_private':answer,'source_type':row['type'],'category':row['category'],
            'source_reasoning_flag':row['reasoning'],'formula':formula,'cut':{k:v for k,v in cut.items() if k not in ['edges','protected']},
            'original_fact_count':n,'base_ratio':k/n,'source_answerability_status':'candidate; requires assistant source assessment and later human confirmation'}
        candidates.append(candidate)
    (HERE/'draft_candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2)+'\n')
    (HERE/'excluded_source_records.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2)+'\n')
    with (HERE/'candidate_catalog.txt').open('w') as f:
        for c in candidates:
            f.write(f"{c['source_index']}|{c['source_id']}|N={c['original_fact_count']}, D={len(c['cut']['deleted_ids'])}, r={c['base_ratio']:.3f}|{c['original']['question']}|{c['formula']['expression']}|remove={c['cut']['deleted_values']}\n")
    print(json.dumps({'candidates':len(candidates),'distinct_evidence_sets':len({c['report_fingerprint'] for c in candidates}),
                      'excluded_upstream_problematic':len(excluded),'ratio_histogram':dict(Counter(round(c['base_ratio'],1) for c in candidates))},indent=2))

if __name__=='__main__':
    prepare()
