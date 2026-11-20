"""Reconstruct table layout from immutable source spans for the Chinese PDF."""
import re
from render_pdf import NUM,translate_label,html_text,make_table_cell

NUMERIC=re.compile(r'^[\s\d,.$€£()%+\-−—–/]+$')

def blocks(source,translated_chunks):
    lines=[]
    for m in re.finditer(r'[^\n]+',source):
        s=m[0].strip()
        if s:lines.append({'text':s,'start':m.start()+len(m[0])-len(m[0].lstrip()),'end':m.end()})
    def zh(start,end):
        items=[]
        for ci,c in enumerate(translated_chunks):
            cend=translated_chunks[ci+1]['source_offset'] if ci+1<len(translated_chunks) else len(source)
            if c['source_offset']<end and cend>start:
                for p in c['parts']:
                    text=html_text(p['text'])
                    if p.get('deleted'):text=f'<font color="#c00018"><u>{text}</u></font>'
                    items.append(text)
        return ''.join(items)
    out=[];i=0;pending=None
    def flush_pending():
        nonlocal pending
        if pending:
            out.append({'kind':'text','source':pending['text'],'start':pending['start'],'end':pending['end'],'zh':zh(pending['start'],pending['end'])})
            pending=None
    while i<len(lines):
        line=lines[i];s=line['text']
        # Pure numeric lines from vertical PDF text extraction are grouped into
        # one row until the next text label, retaining every original token.
        if NUMERIC.fullmatch(s):
            run=[]
            while i<len(lines) and NUMERIC.fullmatch(lines[i]['text']):
                x=lines[i]
                if x['text'] in ['$','€','£'] and i+1<len(lines) and NUMERIC.fullmatch(lines[i+1]['text']):
                    run.append({'text':x['text']+lines[i+1]['text'],'start':x['start'],'end':lines[i+1]['end']});i+=2
                elif x['text'] in [')','%'] and run:
                    run[-1]['text']+=x['text'];run[-1]['end']=x['end'];i+=1
                else:run.append(x);i+=1
            if run:
                label=pending;pending=None
                out.append({'kind':'row','label':label,'cells':run})
            continue
        # Horizontal tables have two or more numeric cells; keep column order,
        # currency marks and accounting parentheses from the source.
        if '\t' in s and len(list(NUM.finditer(s)))>=2:
            flush_pending();matches=list(re.finditer(r'[^\t]+',source[line['start']:line['end']]))
            raw=[];j=0
            while j<len(matches):
                m=matches[j];val=m[0].strip();start=line['start']+m.start()+len(m[0])-len(m[0].lstrip())
                if not val:j+=1;continue
                end=line['start']+m.end()
                if val=='%' and raw:
                    raw[-1]['text']+='%' ;raw[-1]['end']=end;j+=1;continue
                if val in ['$','€','£'] and j+1<len(matches):
                    j+=1;v=matches[j];val+=v[0].strip();end=line['start']+v.end()
                raw.append({'text':val,'start':start,'end':end});j+=1
            if raw:
                label=raw[0] if re.search('[A-Za-z]',raw[0]['text']) else None
                cells=raw[1:] if label else raw
                out.append({'kind':'row','label':label,'cells':cells});i+=1;continue
        flush_pending()
        # A short text line immediately preceding numbers is a row label.
        if len(s)<210 and i+1<len(lines) and NUMERIC.fullmatch(lines[i+1]['text']):pending=line;i+=1;continue
        out.append({'kind':'text','source':s,'start':line['start'],'end':line['end'],'zh':zh(line['start'],line['end'])});i+=1
    flush_pending();return out

def label_html(label,source,translated_chunks):
    if not label:return ''
    s=label['text']
    # Dates and units remain in their source text order; known finance labels
    # use the curated terminology table.
    if re.search(r'for the years ended|year ended',s,re.I) and re.search(r'December\s+31',s,re.I):
        unit='（单位：百万美元；每股金额为美元）' if 'million' in s.lower() else ''
        return '截至12月31日的年度'+unit
    if re.search(r'in thousands, except share amounts',s,re.I):return '单位：千美元，股数数据除外'
    return make_table_cell(s,label['start'],[])

def cell_html(cell,edits):
    # For merged currencies/parentheses, locate numeric spans in the untouched
    # source range; the enclosing range intersects the exact deletion span.
    s=cell['text'];out=[];last=0
    for m in NUM.finditer(s):
        out.append(html_text(s[last:m.start()]))
        red=any(cell['start']<e['end'] and e['start']<cell['end'] for e in edits)
        raw=html_text(m[0]);out.append(f'<font color="#c00018"><u>{raw}</u></font>' if red else raw);last=m.end()
    out.append(html_text(s[last:]));return ''.join(out)
