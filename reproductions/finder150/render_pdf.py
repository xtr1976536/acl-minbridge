# -*- coding: utf-8 -*-
"""Create a Chinese FinQA-template PDF with source-faithful red deletions."""
import hashlib,html,json,re,sys,os
from pathlib import Path

P=Path(__file__).resolve().parent
ROOT=P.parents[1]
DATA=ROOT/'data/finder150'
REVIEW=DATA/'local/final_150_review.json'
TRANSLATIONS=DATA/'local/translations_zh.json'
OUT=ROOT/'reports/FinDER_150题_中文删除标注版.pdf'
MODEL='Helsinki-NLP/opus-mt-en-zh'
NUM=re.compile(r'(?<![A-Za-z])(?:\$\s*|€\s*|£\s*)?[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*%|\s*[KMB](?![A-Za-z]))?',re.I)

def normalize_num(s):
    x=s.replace(',','').strip().replace('−','-').replace('$','').replace('€','').replace('£','').strip()
    x=re.sub(r'\s*(?:%|[KMB])$','',x,flags=re.I).strip()
    try:return format(float(x),'.10g')
    except ValueError:return x

def split_chunks(text,limit=380):
    out=[]
    for line in text.splitlines(keepends=True) or [text]:
        if len(line)<=limit:out.append(line);continue
        start=0
        for m in re.finditer(r'(?<=[.!?;:])\s+',line):
            if m.end()-start>=limit:out.append(line[start:m.end()]);start=m.end()
        while len(line)-start>limit:
            poss=[line.rfind(x,start,start+limit) for x in [' ','\t',',']];cut=max(poss)
            cut=(cut+1) if cut>start else start+limit
            out.append(line[start:cut]);start=cut
        if start<len(line):out.append(line[start:])
    return out or ['']

def make_jobs():
    b=json.loads(REVIEW.read_text());jobs={};refs={}
    def add(kind,key,text):
        ids=[]
        for ch in split_chunks(text):
            nums=list(NUM.finditer(ch));parts=[];cursor=0
            for m in nums:
                parts.append({'kind':'text','source':ch[cursor:m.start()]})
                parts.append({'kind':'number','source':m[0],'normalized':normalize_num(m[0])})
                cursor=m.end()
            parts.append({'kind':'text','source':ch[cursor:]})
            digest=hashlib.sha256((kind+'\0'+ch).encode()).hexdigest()
            jobs.setdefault(digest,{'kind':kind,'source':ch,'parts':parts,'numbers':[m[0] for m in nums]})
            ids.append(digest)
        refs[(kind,key)]=ids
    for r in b['records']:
        n=r['number'];add('question',n,r['original']['question'])
        for ri,s in enumerate(r['original']['references']):add('reference',(n,ri),s)
        for f in r['facts']:
            if f['fact_id'] in r['deleted_fact_ids']:add('label',(n,f['fact_id']),f.get('metric_or_context',''))
    return b,jobs,refs

def run_translation(jobs,batch_size=24):
    import torch
    from transformers import MarianMTModel,MarianTokenizer
    tok=MarianTokenizer.from_pretrained(MODEL,local_files_only=True)
    model=MarianMTModel.from_pretrained(MODEL,local_files_only=True)
    device='mps' if torch.backends.mps.is_available() else 'cpu';model.to(device);model.eval()
    items=list(jobs.items());texts=[x['source'] for _,x in items];first=[]
    for start in range(0,len(texts),batch_size):
        enc=tok(texts[start:start+batch_size],return_tensors='pt',padding=True,truncation=True,max_length=420).to(device)
        with torch.no_grad():gen=model.generate(**enc,max_new_tokens=480,num_beams=2,length_penalty=1.0)
        first.extend(tok.batch_decode(gen,skip_special_tokens=True,clean_up_tokenization_spaces=False))
    translated={};fallback_jobs=[]
    for (key,item),zh in zip(items,first):
        znums=[m[0] for m in NUM.finditer(zh)];srcnums=item['numbers']
        # Tabular rows translate poorly as prose; translate their labels and
        # headings separately while copying each source numeric cell verbatim.
        has_tabular_cells='\t' in item['source'] and len(srcnums)>=2
        ok=(not has_tabular_cells and len(znums)==len(srcnums) and [normalize_num(x) for x in znums]==[normalize_num(x) for x in srcnums])
        if ok:
            chunks=[];cursor=0;matches=list(NUM.finditer(zh))
            for m,raw in zip(matches,srcnums):chunks.extend([{'kind':'text','text':zh[cursor:m.start()]},{'kind':'number','text':raw}]);cursor=m.end()
            chunks.append({'kind':'text','text':zh[cursor:]})
            translated[key]={'parts':chunks,'fallback':False};continue
        fallback_jobs.append((key,item))
    # The fallback translates the prose between numeric spans separately and
    # copies every source numeral literally. This is used only on alignment failure.
    phrases=[];phrase_map=[]
    for key,item in fallback_jobs:
        for i,part in enumerate(item['parts']):
            if part['kind']=='text' and part['source']:
                if not re.search(r'[A-Za-z]',part['source']):
                    item['parts'][i]['translated']=part['source'].replace('\t','    ')
                    continue
                phrase_map.append((key,i));phrases.append(part['source'])
            else:item['parts'][i]['translated']=''
    outs=[]
    for start in range(0,len(phrases),batch_size):
        enc=tok(phrases[start:start+batch_size],return_tensors='pt',padding=True,truncation=True,max_length=280).to(device)
        with torch.no_grad():gen=model.generate(**enc,max_new_tokens=220,num_beams=1)
        outs.extend(tok.batch_decode(gen,skip_special_tokens=True,clean_up_tokenization_spaces=False))
    pmap=dict(zip(phrase_map,outs))
    for key,item in fallback_jobs:
        parts=[]
        for i,part in enumerate(item['parts']):
            if part['kind']=='number':parts.append({'kind':'number','text':part['source']})
            else:parts.append({'kind':'text','text':pmap.get((key,i),'')})
        translated[key]={'parts':parts,'fallback':True}
    return translated,device

def save_translations():
    b,jobs,refs=make_jobs();translated,device=run_translation(jobs);records={}
    for r in b['records']:
        n=r['number'];refsout=[]
        for ri,source in enumerate(r['original']['references']):
            offset=0;chunks=[];edits=[e for e in r['edits'] if e['reference_index']==ri]
            for key in refs[('reference',(n,ri))]:
                item=jobs[key];trans=translated[key];nums=list(NUM.finditer(item['source']));parts=[]
                ni=0
                for p in trans['parts']:
                    if p['kind']=='number':
                        m=nums[ni];start=offset+m.start();end=offset+m.end();ni+=1
                        deleted=any(e['start']<=start<e['end'] or start<=e['start']<end for e in edits)
                        parts.append({'kind':'number','text':p['text'],'deleted':deleted})
                    else:parts.append({'kind':'text','text':p.get('text','')})
                chunks.append({'parts':parts,'source_offset':offset,'fallback':trans['fallback']});offset+=len(item['source'])
            assert offset==len(source),(n,ri,offset,len(source))
            refsout.append(chunks)
        qparts=[p for key in refs[('question',n)] for p in translated[key]['parts']]
        labels={}
        for f in r['facts']:
            if f['fact_id'] in r['deleted_fact_ids']:labels[f['fact_id']]=[p for key in refs[('label',(n,f['fact_id']))] for p in translated[key]['parts']]
        records[str(n)]={'question_parts':qparts,'reference_chunks':refsout,'deleted_labels':labels}
    data={'source_sha256':hashlib.sha256(REVIEW.read_bytes()).hexdigest(),'translation_model':'Helsinki-NLP/opus-mt-en-zh local cached snapshot','device':device,'numeric_alignment_fallbacks':sum(v['fallback'] for v in translated.values()),'translated_chunk_count':len(translated),'records':records}
    TRANSLATIONS.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print({'records':len(records),'chunks':len(translated),'fallback_chunks':data['numeric_alignment_fallbacks'],'device':device})

def html_text(s):return html.escape(s).replace('\n','<br/>').replace('\t','&nbsp;&nbsp;&nbsp;&nbsp;')

GLOSSARY={
 'statement of earnings (loss)':'合并损益表','statement of earnings':'损益表','statement of operations':'经营报表',
 'consolidated statements of operations':'合并经营报表','consolidated statements of income':'合并利润表',
 'consolidated income statements':'合并利润表','consolidated statements of earnings':'合并损益表',
 'years ended':'截至年度','year ended':'截至年度','for the years ended':'截至年度',
 'in millions, except per share amounts':'单位：百万美元，每股数据除外','in millions, except per share data':'单位：百万美元，每股数据除外',
 'in thousands, except per share amounts':'单位：千美元，每股数据除外','in thousands, except per share data':'单位：千美元，每股数据除外',
 'in millions':'单位：百万美元','in thousands':'单位：千美元',
 'sales of equipment':'设备销售收入','sales of services':'服务收入','insurance revenues':'保险业务收入',
 'total revenues':'营业收入总额','total revenue':'总收入','net revenues':'净营业收入','net revenue':'净营业收入','net sales':'净销售额',
 'cost of equipment sold':'设备销售成本','cost of services sold':'服务销售成本','cost of products sold':'产品销售成本','cost of sales':'销售成本',
 'selling, general and administrative expenses':'销售、一般及管理费用','selling, general and administrative':'销售、一般及管理费用','research and development expenses':'研发费用','research and development':'研发费用',
 'income from continuing operations':'持续经营收入','earnings from continuing operations':'持续经营收益','income before income taxes':'税前收入','earnings before income taxes':'税前收益',
 'net earnings':'净收益','net income':'净利润','net loss':'净亏损','income tax expense':'所得税费用','provision for income taxes':'所得税拨备',
 'interest expense':'利息费用','interest income':'利息收入','operating income':'营业利润','operating profit':'营业利润','gross profit':'毛利润','gross margin':'毛利',
 'weighted average diluted shares outstanding':'稀释加权平均流通股数','weighted average basic shares outstanding':'基本加权平均流通股数',
 'weighted average shares outstanding':'加权平均流通股数','diluted earnings per share':'稀释每股收益','basic earnings per share':'基本每股收益',
 'diluted':'稀释','basic':'基本','total operating expenses':'营业费用总额','total costs and expenses':'成本及费用总额',
 'income from operations':'营业利润','revenue':'收入','revenues':'收入','expenses':'费用','expense':'费用',
 'net sales':'净销售额','product revenues, net':'产品净收入','total net sales':'净销售额总额','total net revenues':'净营业收入总额',
}
def translate_label(source,machine=''):
    from polish_translation import PHRASES
    raw=re.sub(r'\s+',' ',source).strip(' \t')
    note=bool(re.search(r'\s*\(?Note\s*$',raw,re.I))
    if note:raw=re.sub(r'\s*\(?Note\s*$','',raw,flags=re.I).rstrip()
    if not re.search('[A-Za-z]',raw):return raw
    key=raw.lower().strip(' :;,.')
    oldterms=json.loads((DATA/'local/table_terms_zh.json').read_text()) if (DATA/'local/table_terms_zh.json').exists() else {}
    oldterms_lower={k.lower().strip(' :;,.'):v for k,v in oldterms.items()}
    for phrase,translated in PHRASES.items():
        if key==phrase.lower():return translated+('（注' if note else '')
    if key in GLOSSARY:return GLOSSARY[key]+('（注' if note else '')
    if key in oldterms_lower:
        from polish_translation import clean
        return clean(oldterms_lower[key])+('（注' if note else '')
    if key.endswith('（注'):
        base=key[:-3].strip()
        if base in oldterms:return oldterms[base]+'（注'
        if base in GLOSSARY:return GLOSSARY[base]+'（注'
        for eng,zh in sorted({**oldterms,**GLOSSARY}.items(),key=lambda z:-len(z[0])):
            if base==eng.lower():return zh+'（注'
    for eng,zh in sorted(GLOSSARY.items(),key=lambda z:-len(z[0])):
        if key==eng:return zh
    # Keep a table's numbers in its value cells, and render a clean Chinese
    # descriptor for common compound row names.
    if key.startswith('total '):
        for eng,zh in GLOSSARY.items():
            if key.startswith(eng):return zh+raw[len(eng):]
    if re.search(r'\d',raw):
        parts=[];cursor=0
        for m in NUM.finditer(raw):
            if m.start()>cursor:parts.append(translate_label(raw[cursor:m.start()]))
            parts.append(m[0]);cursor=m.end()
        if cursor and cursor<len(raw):parts.append(translate_label(raw[cursor:]))
        if cursor:return ''.join(parts)
    return raw

def make_table_cell(source,abs_start,edits,translated_hint=''):
    parts=[];cursor=0;nums=list(NUM.finditer(source))
    if not re.search('[A-Za-z]',source) and not nums:return html_text(source.strip())
    if not nums:
        return translate_label(source,translated_hint)
    # Labels such as "Note 12" still need translation, with their index retained.
    for m in nums:
        if m.start()>cursor:
            phrase=source[cursor:m.start()]
            if re.search(r'[A-Za-z]',phrase):parts.append(translate_label(phrase,translated_hint))
            else:parts.append(phrase)
        start=abs_start+m.start();end=abs_start+m.end();deleted=any(e['start']<=start<e['end'] or start<=e['start']<end for e in edits)
        token=html.escape(m[0])
        parts.append(f'<font color="#c00018"><u>{token}</u></font>' if deleted else token)
        cursor=m.end()
    if cursor<len(source):
        tail=source[cursor:]
        if re.search(r'[A-Za-z]',tail):parts.append(translate_label(tail,translated_hint))
        else:parts.append(tail)
    return ''.join(html_text(x) if '<font ' not in x else x for x in parts).replace('\t','&nbsp;&nbsp;')

def build_pdf():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import BaseDocTemplate,Frame,PageTemplate,Paragraph,Spacer,Table,TableStyle
    b=json.loads(REVIEW.read_text());tr=json.loads(TRANSLATIONS.read_text())
    assert tr['source_sha256']==hashlib.sha256(REVIEW.read_bytes()).hexdigest()
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont('STHeiti',os.environ.get('FINDER_PDF_FONT','/System/Library/Fonts/STHeiti Medium.ttc'),subfontIndex=0))
    styles={'body':ParagraphStyle('body',fontName='STHeiti',fontSize=9.6,leading=13.7,spaceAfter=2,alignment=TA_LEFT,wordWrap='CJK'),
      'label':ParagraphStyle('label',fontName='STHeiti',fontSize=10.0,leading=13.8,spaceBefore=3.8,spaceAfter=1,wordWrap='CJK'),
      'title':ParagraphStyle('title',fontName='STHeiti',fontSize=13.8,leading=17,spaceBefore=0,spaceAfter=2.5,wordWrap='CJK'),
      'cell':ParagraphStyle('cell',fontName='STHeiti',fontSize=8.6,leading=10.7,wordWrap='CJK')}
    class Doc(BaseDocTemplate):
      def __init__(self,path):
        super().__init__(path,pagesize=A4,leftMargin=16*mm,rightMargin=16*mm,topMargin=14*mm,bottomMargin=14*mm,title='FinDER 150题中文删除标注审核本',author='MinBridge research review')
        self.addPageTemplates(PageTemplate(id='main',frames=[Frame(self.leftMargin,self.bottomMargin,self.width,self.height,id='normal',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.footer))
      def footer(self,canvas,doc):
        canvas.saveState();canvas.setFont('STHeiti',8.5);canvas.setFillColor(colors.HexColor('#666666'));canvas.drawString(16*mm,8*mm,'红色下划线表示删除内容');canvas.drawRightString(A4[0]-16*mm,8*mm,f'第{doc.page}页');canvas.restoreState()
    story=[];doc=Doc(str(OUT));zrecords=tr['records'];special={1274:'2023年研发费用占产品收入比例＝研发费用÷产品收入×100%。',882:'总非利息费用＝净利息收入（拨备后）＋总非利息收入－税前收入。',2697:'稀释每股收益＝归属UHS净利润÷稀释加权平均股数。',742:'净利润率＝净利润÷营业收入×100%。',3514:'收入增长倍数＝2023年总营业收入÷2021年总营业收入。',5010:'终止经营对每股收益的影响＝2023年稀释净每股收益－持续经营稀释每股收益。',4878:'税前收益占物业收入倍数＝持续经营税前收益÷物业收入。'}
    for r in b['records']:
      z=zrecords[str(r['number'])];sev={'low':'低删组','medium':'中删组','high':'高删组'}[r['severity']]
      story.append(Paragraph(f"第{r['number']}题（{sev}）",styles['title']));story.append(Paragraph('材料',styles['label']))
      from source_layout import blocks,label_html,cell_html
      manual_narratives=json.loads((DATA/'local/narratives_zh.json').read_text())
      if str(r['source_index']) in manual_narratives:
        from decimal import Decimal
        narrative=manual_narratives[str(r['source_index'])];deleted_vals={Decimal(f['value']) for f in r['facts'] if f['fact_id'] in r['deleted_fact_ids']}
        fragments=[];cursor=0
        for match in NUM.finditer(narrative):
          fragments.append(html_text(narrative[cursor:match.start()]))
          value=Decimal(re.sub(r'[^\d.\-]','',match[0]))
          token=html_text(match[0])
          fragments.append(f'<font color="#c00018"><u>{token}</u></font>' if value in deleted_vals else token);cursor=match.end()
        fragments.append(html_text(narrative[cursor:]));story.append(Paragraph(''.join(fragments),styles['body']))
      for ri,refchunks in ([] if str(r['source_index']) in manual_narratives else enumerate(z['reference_chunks'])):
        source_ref=r['original']['references'][ri]
        table_rows=[]
        def flush_table():
          nonlocal table_rows
          if not table_rows:return
          width=max(len(row) for row in table_rows)
          data=[row+[Paragraph('',styles['cell'])]*(width-len(row)) for row in table_rows]
          first=doc.width*.44
          widths=[first]+[(doc.width-first)/(width-1)]*(width-1) if width>1 else [doc.width]
          table=Table(data,colWidths=widths,hAlign='LEFT',splitByRow=1)
          commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),1.5),('BOTTOMPADDING',(0,0),(-1,-1),1.5),('LINEBELOW',(0,0),(-1,-1),.20,colors.HexColor('#dddddd'))]
          if any(re.fullmatch(r'(19|20)\d{2}',c.getPlainText().strip()) for c in data[0]):commands.append(('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eef0f2')))
          table.setStyle(TableStyle(commands));story.append(table);table_rows=[]
        local_edits=[e for e in r['edits'] if e['reference_index']==ri]
        for block in blocks(source_ref,refchunks):
          if block['kind']=='row':
            label=label_html(block['label'],source_ref,refchunks)
            cells=[Paragraph(label,styles['cell'])]+[Paragraph(cell_html(c,local_edits),styles['cell']) for c in block['cells']]
            table_rows.append(cells)
          else:
            flush_table();raw=block['source']
            known=translate_label(raw)
            text=html_text(known) if known!=raw and len(raw)<180 else (block['zh'] or html_text(raw))
            if text.strip():story.append(Paragraph(text,styles['body']))
        flush_table()
      from reportlab.platypus import KeepTogether
      qoverride={5010:'2023年终止经营对每股收益的影响是多少？',4878:'2023年持续经营税前收益占物业收入的倍数是多少？',2304:'高盛的基本每股收益从2021年到2023年下降了多少？',2832:'2023年净销售额是2021年的多少倍？',3514:'PG&amp;E公司2023年总营业收入是2021年的多少倍？',742:'J.B. Hunt运输服务公司2023年的净利润率是多少？',1274:'Vertex公司2023年研发费用占产品收入的比例是多少？',5142:'Dayforce公司2023年经常性收入占总收入的比例是多少？',1456:'MarketAxess公司2023年的有效税率是多少？'}
      manual_q={int(line.split('|',1)[0]):line.strip().split('|',1)[1] for line in (DATA/'local/questions_zh.txt').read_text().splitlines() if '|' in line}
      qhtml=html_text(manual_q[r['number']])
      story.append(KeepTogether([Paragraph('问题',styles['label']),Paragraph(qhtml,styles['body']),Paragraph('关系',styles['label']),Paragraph(special.get(r['source_index'],html_text(r.get('complete_numeric_relation_private',''))),styles['body'])]))
      facts={f['fact_id']:f for f in r['facts']};bits=[]
      for fid in r['deleted_fact_ids']:
        f=facts[fid];lab=html_text(translate_label(f.get('metric_or_context','')));period=f.get('period_hint') or ''
        if period and period!='question':lab+=f'（{html.escape(period)}）'
        bits.append(f'{lab}：{html.escape(format(__import__("decimal").Decimal(f["value"]),"f"))}')
      story.append(KeepTogether([Paragraph('删除事实总结',styles['label']),Paragraph('；'.join(bits) if bits else '已删除必要事实及其等价披露。',styles['body'])]));story.append(Spacer(1,3.5))
    OUT.parent.mkdir(parents=True,exist_ok=True);doc.build(story);print('PDF built',OUT)

def main():
    if '--build-only' in sys.argv:build_pdf()
    else:save_translations();build_pdf()

if __name__=='__main__':main()
