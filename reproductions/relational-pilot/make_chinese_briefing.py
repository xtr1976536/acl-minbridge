"""Chinese academic briefing from frozen experiment records; no model API calls."""
import csv,hashlib,json,math
from pathlib import Path
from xml.sax.saxutils import escape
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,
    Image,PageBreak,KeepTogether,Flowable)
from reportlab.lib.enums import TA_CENTER,TA_JUSTIFY
from pypdf import PdfReader

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
DATA=WORK/'output/experiments/english150-20261116-expanded'
RUN=HERE/'local/runs/english150-20261116-expanded'
TMP=WORK/'tmp/pdfs/minbridge_briefing'
OUT=WORK/'output/pdf/MinBridge_关系幻觉预研_中文汇报.pdf'
TMP.mkdir(parents=True,exist_ok=True)
D=json.loads((DATA/'结果统计.json').read_text())
FEE=json.loads((DATA/'调用费用估计.json').read_text())
QA=json.loads((DATA/'最终完整性校验.json').read_text())
AUDIT=json.loads((RUN/'internal_recheck_summary.json').read_text())
SOURCE=json.loads((RUN/'source_answerability.json').read_text())
RECORDS=json.loads((HERE/'v2/final_150_review.json').read_text())
MAIN=D['label_policies']['independent_overlapping']
PROVIDERS={'openai':'GPT-5.6 Sol','deepseek':'DeepSeek-V4-Pro','qwen':'Qwen3.8-27B'}
METHODS={'cot_paired_4shot':'配对CoT','pot':'PoT','cot_existing_abstention':'原有拒答CoT'}
POLICIES={'numeric_provenance_exclusive':'数字溯源互斥','independent_overlapping':'独立标签'}
PAGE_W,PAGE_H=612,792
MARGIN=54
WIDTH=PAGE_W-2*MARGIN
BLACK=colors.HexColor('#171717')
GRAY=colors.HexColor('#555555')
BLUE='#176986';ORANGE='#BA542F'

pdfmetrics.registerFont(TTFont('Song','/System/Library/Fonts/Supplemental/Songti.ttc',subfontIndex=6))
pdfmetrics.registerFont(TTFont('SongBold','/System/Library/Fonts/Supplemental/Songti.ttc',subfontIndex=1))
pdfmetrics.registerFont(TTFont('Hei','/System/Library/Fonts/STHeiti Medium.ttc',subfontIndex=1))
pdfmetrics.registerFont(TTFont('Times','/System/Library/Fonts/Supplemental/Times New Roman.ttf'))
pdfmetrics.registerFont(TTFont('TimesBold','/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf'))
pdfmetrics.registerFontFamily('Song',normal='Song',bold='SongBold',italic='Song',boldItalic='SongBold')
pdfmetrics.registerFontFamily('Hei',normal='Hei',bold='Hei',italic='Hei',boldItalic='Hei')
ST={
 'body':ParagraphStyle('body',fontName='Song',fontSize=11,leading=15.7,textColor=BLACK,
     wordWrap='CJK',alignment=TA_JUSTIFY,firstLineIndent=22,spaceAfter=6),
 'plain':ParagraphStyle('plain',fontName='Song',fontSize=11,leading=15.7,textColor=BLACK,wordWrap='CJK',spaceAfter=6),
 'h1':ParagraphStyle('h1',fontName='Hei',fontSize=14,leading=19,spaceBefore=10,spaceAfter=7,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='Hei',fontSize=11.6,leading=16,spaceBefore=8,spaceAfter=5,keepWithNext=True),
 'title':ParagraphStyle('title',fontName='Hei',fontSize=20,leading=27,alignment=TA_CENTER,spaceAfter=7),
 'subtitle':ParagraphStyle('subtitle',fontName='Song',fontSize=11,leading=16,alignment=TA_CENTER,spaceAfter=6),
 'caption':ParagraphStyle('caption',fontName='Song',fontSize=9.3,leading=12.5,alignment=TA_CENTER,wordWrap='CJK',spaceBefore=4,spaceAfter=8),
 'note':ParagraphStyle('note',fontName='Song',fontSize=9.2,leading=12.6,textColor=GRAY,wordWrap='CJK',spaceAfter=6),
 'cell':ParagraphStyle('cell',fontName='Song',fontSize=9.3,leading=12.4,wordWrap='CJK'),
 'cellsmall':ParagraphStyle('cellsmall',fontName='Song',fontSize=8.6,leading=11.2,wordWrap='CJK'),
 'headcell':ParagraphStyle('headcell',fontName='Hei',fontSize=9.4,leading=12.2,wordWrap='CJK'),
 'equation':ParagraphStyle('equation',fontName='Song',fontSize=11,leading=18,alignment=TA_CENTER,spaceBefore=4,spaceAfter=8),
}
def fmt(x,d=2):return '—' if x is None else f'{100*x:.{d}f}%'
def pp(x,d=2):return '—' if x is None else f'{100*x:+.{d}f}'
def interval(info,unit='percent'):
    c=info.get('ci95') if info else None
    if c is None:return '未定义'
    if unit=='ratio':return f'[{c[0]:.2f}, {c[1]:.2f}]'
    tail='%' if unit=='percent' else ''
    return f'[{c[0]*100:.2f}{tail}, {c[1]*100:.2f}{tail}]'
def text(value,kind='body'):
    value=str(value).replace('H1','RQ1').replace('H2','RQ2').replace('H3','RQ3')
    return Paragraph(value,ST[kind])
def esc(value):return escape(str(value))
def cell(value,head=False,small=False):
    return Paragraph(esc(value).replace('\n','<br/>'),ST['headcell' if head else 'cellsmall' if small else 'cell'])

class AcademicDoc(SimpleDocTemplate):
    def afterFlowable(self,flowable):
        if isinstance(flowable,Paragraph) and flowable.getPlainText().startswith('PoT1。'):
            self.pot_footnote_pages.add(self.page)
        if isinstance(flowable,Paragraph) and flowable.style.name in ('h1','h2'):
            title=flowable.getPlainText();key='section'+str(len(self.bookmarks));self.bookmarks.append((title,self.page))
            self.canv.bookmarkPage(key);self.canv.addOutlineEntry(title,key,level=0 if flowable.style.name=='h1' else 1,closed=False)
    def afterPage(self):
        if self.page in self.pot_footnote_pages:
            self.canv.setFont('Song',8.5);self.canv.setFillColor(GRAY)
            self.canv.drawString(MARGIN,43,'1　382条PoT程序未返回有效数值，后续将单独检查其原因。')

def page_canvas(canv,doc):
    canv.setFont('Times',10);canv.setFillColor(BLACK);canv.drawCentredString(PAGE_W/2,27,str(doc.page))
    if doc.page>1:
        canv.setFont('Song',8.3);canv.setFillColor(GRAY)
        canv.drawString(MARGIN,PAGE_H-28,'MinBridge 关系幻觉预研 | 中文阶段汇报')
        canv.drawRightString(PAGE_W-MARGIN,PAGE_H-28,'2026年11月16日 · 部分复核未完')

story=[];table_no=0;figure_no=0
def add(value,kind='body'):story.append(text(value,kind))
def h1(value):add(value,'h1')
def h2(value):add(value,'h2')
def newpage():story.append(PageBreak())
def table(title,headers,rows,widths=None,small=False,groups=()):
    global table_no
    table_no+=1
    cap=text(f'<b>表{table_no}</b>　{esc(title)}','caption')
    data=[[cell(h,True) for h in headers]]+[[cell(v,small=small) for v in row] for row in rows]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='CENTER')
    rules=[('LINEABOVE',(0,0),(-1,0),.9,BLACK),('LINEBELOW',(0,0),(-1,0),.45,BLACK),
      ('LINEBELOW',(0,-1),(-1,-1),.9,BLACK),('VALIGN',(0,0),(-1,-1),'TOP'),
      ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
      ('TOPPADDING',(0,0),(-1,0),5),('BOTTOMPADDING',(0,0),(-1,0),5),
      ('TOPPADDING',(0,1),(-1,-1),3.7),('BOTTOMPADDING',(0,1),(-1,-1),3.7)]
    for row in groups:rules.append(('LINEABOVE',(0,row),(-1,row),.35,colors.HexColor('#999999')))
    t.setStyle(TableStyle(rules));story.extend([cap,t,Spacer(1,7)])
def figure(path,title,note='',height=None):
    global figure_no
    from PIL import Image as PIL
    figure_no+=1
    w,h=PIL.open(path).size
    if height is None:height=WIDTH*h/w
    img=Image(str(path),width=WIDTH,height=height)
    caption=text(f'<b>图{figure_no}</b>　{esc(title)}'+('。'+esc(note) if note else ''),'caption')
    story.append(KeepTogether([img,caption]))
def note(value):add(esc(value),'note')

def plot_setup():
    font='/System/Library/Fonts/STHeiti Medium.ttc';fm.fontManager.addfont(font)
    plt.rcParams.update({'font.family':fm.FontProperties(fname=font).get_name(),'font.size':9.6,
       'axes.titlesize':10.2,'axes.labelsize':9.5,'xtick.labelsize':9,'ytick.labelsize':9.3,
       'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
def grid(ax):
    ax.set_axisbelow(True);ax.grid(axis='x',color='#d9dfe2',linewidth=.5)
def savefig(fig,name):
    path=TMP/name;fig.savefig(path,dpi=300,facecolor='white');plt.close(fig);return path

def plots():
    plot_setup();result={}
    fig,axes=plt.subplots(1,2,figsize=(7,2.55),constrained_layout=True,sharey=True)
    for ax,(policy,title) in zip(axes,POLICIES.items()):
        for rate,offset,color,label,hatch in [('numeric_rate',-.18,BLUE,'数值幻觉',''),('relation_rate',.18,ORANGE,'关系幻觉/代理','///')]:
            vals=[D['label_policies'][policy]['model/'+p][rate]*100 for p in PROVIDERS]
            ax.bar(np.arange(3)+offset,vals,width=.33,color=color,hatch=hatch,edgecolor='white',label=label)
            for x,v in zip(np.arange(3)+offset,vals):ax.text(x,v+.6,f'{v:.1f}',ha='center',fontsize=8.5)
        ax.set(xticks=np.arange(3),xticklabels=['GPT-5.6','DeepSeek','Qwen'],ylim=(0,26),title=title)
        ax.yaxis.grid(True,color='#dde2e5',linewidth=.5);ax.set_axisbelow(True)
    axes[0].set_ylabel('占各模型900条输出的比例（%）')
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,ncol=2,loc='outside lower center',frameon=False,fontsize=9)
    result['models']=savefig(fig,'01_models.png')
    fig,axes=plt.subplots(3,2,figsize=(7,7.75),constrained_layout=True,sharex=True)
    for i,(provider,name) in enumerate(PROVIDERS.items()):
        for col,mode in enumerate(('low','high')):
            ax=axes[i,col];y=np.arange(3)
            for rate,offset,color,label in [('numeric_rate',-.18,BLUE,'数值幻觉'),('relation_rate',.18,ORANGE,'关系幻觉')]:
                for j,method in enumerate(METHODS):
                    m=MAIN[f'cell/{provider}/{mode}/{method}'];v=m[rate]*100;c=m['confidence'][rate]['ci95']
                    ax.barh(j+offset,v,height=.30,color=color,edgecolor='white',hatch='///' if rate=='relation_rate' else '',label=label if j==0 else None)
                    if c:ax.errorbar(v,j+offset,xerr=[[max(0,v-c[0]*100)],[max(0,c[1]*100-v)]],fmt='none',ecolor='#333333',capsize=2,linewidth=.7)
                    right=c[1]*100 if c else v;ax.text(min(right+1,66),j+offset,f'{v:.1f}',va='center',fontsize=8)
            setting=('low' if mode=='low' else 'high') if provider=='openai' else ('关闭思考' if mode=='low' else '开启思考')
            ax.set(yticks=y,yticklabels=['配对CoT','PoT','原有CoT'],xlim=(0,70),xticks=[0,20,40,60],title=name+' / '+setting)
            ax.invert_yaxis();grid(ax)
            if i==2:ax.set_xlabel('占该条件150条输出的比例（%）')
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=2,frameon=False,fontsize=9)
    result['cells']=savefig(fig,'02_cells.png')
    fig,ax=plt.subplots(figsize=(7,3.1),constrained_layout=True)
    names=[]
    for i,p in enumerate(PROVIDERS):
        for mi,mode in enumerate(('low','high')):
            y=i*2+mi;m=D['h1_h2_h3_comparisons']['independent_overlapping']['h2'][p+'/'+mode+'/pot_vs_cot_paired_4shot']
            names.append(('GPT-5.6' if p=='openai' else 'DeepSeek' if p=='deepseek' else 'Qwen')+'/'+ ('low' if p=='openai' and mode=='low' else 'high' if p=='openai' else '关' if mode=='low' else '开'))
            for metric,offset,color,label in [('numeric_rate_difference_pot_minus_cot',-.13,BLUE,'数值率差'),('relation_rate_difference_pot_minus_cot',.13,ORANGE,'关系率差')]:
                value=m[metric]['estimate']*100;c=m[metric]['ci95']
                ax.errorbar(value,y+offset,xerr=[[max(0,value-c[0]*100)],[max(0,c[1]*100-value)]],fmt='o',color=color,capsize=2,markersize=4,label=label if y==0 else None)
    ax.axvline(0,color='#555555',linewidth=.8,linestyle='--');ax.set(yticks=np.arange(6),yticklabels=names,xlabel='PoT减配对CoT：幻觉率差（百分点）');ax.invert_yaxis();grid(ax)
    ax.legend(loc='lower right',frameon=False,fontsize=9)
    result['h2']=savefig(fig,'03_h2.png')
    fig,ax=plt.subplots(figsize=(7,3.6),constrained_layout=True)
    names=[]
    for i,(key,m) in enumerate(D['h1_h2_h3_comparisons']['independent_overlapping']['h3'].items()):
        p,method=key.split('/');label=('GPT-5.6' if p=='openai' else 'DeepSeek' if p=='deepseek' else 'Qwen')+'/'+METHODS[method]
        names.append(label);v=m['relation_rate_difference_high_minus_low']*100;c=m['ci95']
        ax.errorbar(v,i,xerr=[[max(0,v-c[0]*100)],[max(0,c[1]*100-v)]],fmt='o',color=BLUE,capsize=2,markersize=4)
    ax.axvline(0,color='#555555',linewidth=.8,linestyle='--');ax.set(yticks=np.arange(9),yticklabels=names,xlabel='关系幻觉率差：高减低 / 开启减关闭（百分点）');ax.invert_yaxis();grid(ax)
    result['h3']=savefig(fig,'04_h3.png')
    fig,axes=plt.subplots(1,2,figsize=(7,2.8),constrained_layout=True,sharey=True)
    for ax,rate,title,color in [(axes[0],'numeric_rate','数值幻觉',BLUE),(axes[1],'relation_rate','关系幻觉',ORANGE)]:
        for i,severity in enumerate(('low','medium','high')):
            m=MAIN['severity/'+severity];v=m[rate]*100;c=m['confidence'][rate]['ci95']
            ax.bar(i,v,color=color,width=.52,edgecolor='white')
            ax.errorbar(i,v,yerr=[[max(0,v-c[0]*100)],[max(0,c[1]*100-v)]],fmt='none',ecolor='#333',capsize=3,linewidth=.8)
            ax.text(i,c[1]*100+.6,f'{v:.2f}',ha='center',fontsize=8.5)
        ax.set(xticks=[0,1,2],xticklabels=['低删\n90题','中删\n30题','高删\n30题'],title=title,ylim=(0,23));ax.yaxis.grid(True,color='#dde2e5',linewidth=.5);ax.set_axisbelow(True)
    axes[0].set_ylabel('占该组全部输出的比例（%）')
    result['severity']=savefig(fig,'05_severity.png');return result

def build():
    figs=plots()
    add('MinBridge关系幻觉预研','title')
    add('150道FinQA候选题的2,700条推理输出与GPT自动判读','subtitle')
    add('中文阶段汇报　|　2026年11月16日　|　部分复核待完成','subtitle')
    story.append(Spacer(1,6))
    add('<b>摘要。</b> 本轮比较三个模型、三套提示与两档推理设置，完成全部2,700条英文输出。独立标签机审识别数值幻觉227条（8.41%）、关系幻觉379条（14.04%）；611条错误作答中含关系幻觉的占62.03%。PoT的关系幻觉率高于配对CoT，但数值幻觉率未整体下降；开启思考也没有呈现统一的关系幻觉上升趋势。以上是保留未决项的暂定机审统计，尚未形成独立人工金标。','plain')
    note('状态说明：生成部分已全部补齐。主评审2条受服务商内容校验拒绝；内部复核最后26条因OpenAI账户余额耗尽未完成，另有少量标注校验问题待解决。本报告只整理现有记录，不发起新API调用。')
    from briefing_revision_content import background,experiment_setup
    background(globals())
    experiment_setup(globals())

    newpage();h1('3　测量定义与统计口径')
    h2('3.1　数字来源与关系依据')
    add('变量按指标、实体、期间和单位区分。数值幻觉关注被当作事实采用、却无可见证据来源的定量输入；合法中间结果、单位换算和有依据的常数不因未逐字出现就被判为编造。关系幻觉关注使目标变得可计算的无依据方程、补值、相等假设或定义替换；纯算术和执行错误另记。')
    table('依据层级（据研究计划书定义）',['层级','依据与处理'],[
       ['T0 / T1','问题 / 文档明确给出的关系。'],['T2','在当前实体、期间、单位和口径下适用的公认恒等式或明确准则定义。'],
       ['T3','常见但不唯一的定义；使用时应明确声明口径。'],['T4','额外主观假设或外部数据；未经声明和限定时，不能据此声称实际目标已知。']], [76,428])
    table('两种测量政策并列计算',['口径','数字标签','关系标签'],[
       ['数字溯源互斥','错误目标作答中，采用文档外输入数字。','错误目标作答中未采用文档外输入数字；是操作性关系代理。'],
       ['独立标签','逐项判读最终采用的数字是否具有来源。','逐项判读最终采用的关系是否具有依据；允许与数字标签并存。']], [98,203,203])
    add('互斥代理可能把纯算术或其他错误也归入“关系”；独立判读也可能将带编造数字的回答同时判为关系问题。因此，两者必须分别报告，不能以净比例接近替代逐项一致性。', 'plain')
    h2('3.2　分母与合法回答')
    add('数值幻觉率 = 数值标签计数 / 全部输出数；关系幻觉率 = 关系标签计数 / 全部输出数。关系占错误作答的比例则使用错误作答数作分母。总体、模型汇总、单条件的分母分别为2,700、900、150；未知记录保留在全部分母中，不当作已确认无幻觉。')
    add('本轮：数值率 = 227 / 2,700；关系率 = 379 / 2,700。　(1)','equation')
    add('错误作答中的关系占比 = 379 / 611 = 62.03%。　(2)','equation')
    add('明确声明“若假设成立则得到某值，实际值仍不可确定”的合法条件回答单列。思考中提出、随后明确放弃的错误也单列，不加入最终采纳推导的主幻觉率。原始“拒绝给出现实确定值”标记可与条件回答同现，汇总时将合法条件回答与纯正确拒答分开计数。')
    h2('3.3　GPT判读及区间')
    add('主评审采用GPT-5.6 Sol的medium设置，隐藏生成模型、提示、档位和删除组元数据，以固定种子打乱顺序。判断包含标签、简短理由及证据片段，并对低置信度、引用不符、可答性冲突和百分比口径疑点进行内部复核。代码形态仍可能暴露流程类型，且评审者与一个被评模型同属GPT，不能宣称完全盲化或独立人类标注。')
    note('区间使用2,000次源题配对bootstrap，固定90 / 30 / 30分层，同一源题的18条输出共同重采样。题族尚未人工确认；区间不包含GPT判读误差，按探索性源题区间理解。')

    newpage();h1('4　实验结果')
    h2('4.1　总体与模型汇总')
    table('全矩阵的总体机审结果',['口径','数值幻觉','关系幻觉 / 代理','混合','关系占错误作答'],[
       ['数字溯源互斥','227 / 2,700\n8.41%','384 / 2,700\n14.22%','0','62.85%'],
       ['独立标签','227 / 2,700\n8.41%','379 / 2,700\n14.04%','22','62.03%']], [105,106,114,45,134])
    add('611条输出被判为错误目标作答，占22.63%。独立标签下，数值与关系两类同时出现22条；两类比例不可直接相加作为总错误率。两政策有27条仅被互斥代理归为关系、22条仅被独立标签判为关系，净差虽只有5条，逐项含义并不相同。')
    table('模型汇总（独立标签，每模型900条）',['模型','数值幻觉','关系幻觉','混合','正确拒答','合法条件'],[
       [PROVIDERS[p],f"{MAIN['model/'+p]['numeric']} ({fmt(MAIN['model/'+p]['numeric_rate'])})",f"{MAIN['model/'+p]['relation']} ({fmt(MAIN['model/'+p]['relation_rate'])})",MAIN['model/'+p]['both'],MAIN['model/'+p]['correct_refusal'],MAIN['model/'+p]['valid_conditional']] for p in PROVIDERS], [128,96,96,44,70,70])
    figure(figs['models'],'两种口径的模型汇总','每个柱子的分母为该模型的900条候选题输出；数值为百分比，保留未知记录。')
    add('本批记录中，GPT的数值标签比例较高，Qwen的关系标签比例较高。该汇总同时混合三套提示与两档设置，不能当作模型固有能力排名；提示差异、源题歧义、适应性预算和机器判读误差均影响解释。')
    table('核心比较与补充提示分别汇总（独立标签）',['范围','输出数','数值幻觉率','关系幻觉率'],[
       ['配对CoT + PoT','1,800',fmt(MAIN['core/paired_cot_and_pot']['numeric_rate']),fmt(MAIN['core/paired_cot_and_pot']['relation_rate'])],
       ['原有拒答CoT','900',fmt(MAIN['supplementary/existing_cot']['numeric_rate']),fmt(MAIN['supplementary/existing_cot']['relation_rate'])]], [208,72,112,112])

    newpage();h2('4.2　CoT与PoT比较：关系上升，数值未整体下降')
    table('三种提示的汇总（独立标签，每种900条）',['提示','数值幻觉','关系幻觉','错误作答','正确拒答','合法条件'],[
       [METHODS[m],f"{MAIN['method/'+m]['numeric']} ({fmt(MAIN['method/'+m]['numeric_rate'])})",f"{MAIN['method/'+m]['relation']} ({fmt(MAIN['method/'+m]['relation_rate'])})",MAIN['method/'+m]['wrong_answer'],MAIN['method/'+m]['correct_refusal'],MAIN['method/'+m]['valid_conditional']] for m in METHODS], [111,104,104,66,62,57])
    add('PoT关系幻觉率为30.44%，配对CoT为9.78%，总体比值约3.11；但PoT数值幻觉率为18.44%，高于配对CoT的6.78%。因此，当前自动标签并不支持“PoT数值错误整体下降”的完整迁移预期。原有拒答CoT数值标签为零，同时具有不同的拒答提示，不能与配对CoT混为同一个成绩。')
    figure(figs['h2'],'同模型同档位的PoT减配对CoT差值','误差线为源题配对95%区间；横轴单位为百分点，右侧表示PoT更高。')
    rows=[]
    for p,name in PROVIDERS.items():
        for mode in ('low','high'):
            m=D['h1_h2_h3_comparisons']['independent_overlapping']['h2'][p+'/'+mode+'/pot_vs_cot_paired_4shot']
            rows.append([name,mode if p=='openai' else '关' if mode=='low' else '开',pp(m['numeric_rate_difference_pot_minus_cot']['estimate']),pp(m['relation_rate_difference_pot_minus_cot']['estimate']),f"{m['relation_rate_ratio_pot_over_cot']['estimate']:.3f}"])
    table('H2核心六组比较',['模型','设置','数值率差','关系率差','关系率比'],rows,[150,54,96,96,108],groups=(3,5))
    note('差值单位为百分点；关系率比为PoT / 配对CoT。六组关系比值均达到1.5，只有Qwen关闭思考组同时满足数值率下降；两项条件同时满足1 / 6组。原有拒答CoT的完整对照见附录B。')

    newpage();h2('4.3　18个条件的完整对照')
    add('图3逐一展示每模型、每档位、每提示的数值与关系标签比例，单条件分母均为150。提示产生的差异不能被总体平均数掩盖。独立标签的逐项计数见附录A；互斥代理同样保留，不按结果优劣删除任何条件。')
    figure(figs['cells'],'全部18个条件的独立标签比例','横轴为百分比；误差线为源题配对bootstrap 95%区间，不含机审误差。')
    note('GPT的low / high均为推理强度参数；另外两家为关闭 / 开启思考，档位含义并不完全相同。放宽上限仅作用于原未完成记录，因此本图属于适应性预算后的描述性比较。')

    newpage();h2('4.4　H1与H3：错误构成与推理强度')
    table('H1：关系占错误作答的比例',['口径','分子 / 分母','比例','源题95%区间'],[
       [POLICIES[p],f"{D['label_policies'][p]['overall']['relation']} / 611",fmt(D['label_policies'][p]['overall']['h1_relation_share_among_wrong']),interval(D['label_policies'][p]['overall']['confidence']['h1_relation_share_among_wrong'])] for p in POLICIES],[123,105,87,189])
    add('独立标签下，关系幻觉占全部输出的14.04%，占错误作答的62.03%；两种分母回答不同的问题。源题可答性和标注尚未完成人工确认，这些是当前机审的描述性读数。')
    figure(figs['h3'],'H3：同模型同提示的关系率差','高减低，或开启减关闭；单位为百分点。负值表示高强度 / 开启思考的机审关系率更低。')
    add('九组比较中，关系率上升2组、下降7组。DeepSeek与Qwen的PoT高档关系率分别低17.33和15.33个百分点；GPT配对CoT与DeepSeek原有CoT的点估计为上升。整体没有统一的“开启思考使关系幻觉增加”趋势。')
    note('H3全部差值与区间见附录C。区间仅反映当前自动标签下的源题重采样；部分记录拥有更大生成预算，不能解释为严格同预算的强度因果效应。')

    newpage();h1('5　稳健性、可答性与边界')
    h2('5.1　统一原上限与更新预算')
    table('预算版本敏感性（全部2,700条为分母）',['版本','口径','生成未完','数值率','关系率 / 代理率'],[
      ['原版8,192','互斥',190,fmt(D['original_uniform_8192_sensitivity']['numeric_provenance_exclusive']['numeric_rate']),fmt(D['original_uniform_8192_sensitivity']['numeric_provenance_exclusive']['relation_rate'])],
      ['更新适应性','互斥',0,fmt(D['label_policies']['numeric_provenance_exclusive']['overall']['numeric_rate']),fmt(D['label_policies']['numeric_provenance_exclusive']['overall']['relation_rate'])],
      ['原版8,192','独立',190,fmt(D['original_uniform_8192_sensitivity']['independent_overlapping']['numeric_rate']),fmt(D['original_uniform_8192_sensitivity']['independent_overlapping']['relation_rate'])],
      ['更新适应性','独立',0,fmt(MAIN['overall']['numeric_rate']),fmt(MAIN['overall']['relation_rate'])]], [112,65,83,105,139])
    add('原版190条未完成记录作为未知保留在分母。更新版增加的是此前缺失的完整回答，同时也包含新的随机生成，不能把前后差值当成对同一次回答的纯质量改善，更不能用它证明工具或思考强度的因果效应。')
    h2('5.2　删除程度的描述性分组')
    figure(figs['severity'],'低、中、高删组的独立标签比例','各组分母为1,620、540、540条输出。组内源题数为90、30、30，误差线为相应源题重采样区间。')
    table('删除组汇总',['组别','源题 / 输出','数值率','关系率','正确拒答'],[
       [label,f"{n} / {MAIN['severity/'+key]['n_all_nominal_unanswerable']}",fmt(MAIN['severity/'+key]['numeric_rate']),fmt(MAIN['severity/'+key]['relation_rate']),MAIN['severity/'+key]['correct_refusal']] for key,label,n in [('low','低删',90),('medium','中删',30),('high','高删',30)]],[80,130,95,95,104])
    note('三组由不同源题组成，不是同一题的三个删除水平；组间差异不能作因果解释。第2题两个不同指标的7%应分别计数，校勘已留档，未依据本轮模型表现重新分组。')

    newpage();h2('5.3　源题可答性的独立机器诊断')
    add('额外调用GPT只查看问题和删后材料，不看候选回答、原题金标或模型身份。150题均完成诊断，并对22个疑点或随机项作内部复核。最终机审将134题标为证据不足、13题标为可答、3题标为不确定。这是机器意见，不是人工确认；评审者也可能误读期间、分部或问题范围。')
    add('需要优先核查的题号为：<b>6、12、29、31、50、51、64、73、76、78、82、85、87、94、96、97</b>。其中既有正文保留舍入数字、可以支持近似答案的情况，也有问题表述与原始程序所指范围不完全明确的情况。本轮没有替换或删除这些题。')
    table('可答性诊断中的三类具体疑点',['题号','机审提示的争议','后续核查重点'],[
       ['29','表格可计算整体分部利润变化，但原构造理由指向地区利润。','核对问题是否明确要求地区，不能用不可见金标强行限定目标。'],
       ['31','增加与扣减各自缺失，但两者之差可由期初期末余额确定。','核对“how bigger”究竟要求差额还是比率；不能仅因标准程序需输入就认定不可答。'],
       ['85','期初约3,500万与期末约3,050万仍在正文，可算近似降幅。','核对题目精度要求；支持近似不等于可识别更高精度真值。']], [45,226,233])
    table('源题诊断子集的敏感性（不替代全矩阵）',['口径','源题 / 输出','数值率','关系率 / 代理率'],[
       [POLICIES[p],f"{D['source_only_insufficient_subset']['source_count']} / {D['source_only_insufficient_subset']['output_count']}",fmt(D['source_only_insufficient_subset']['metrics'][p]['numeric_rate']),fmt(D['source_only_insufficient_subset']['metrics'][p]['relation_rate'])] for p in POLICIES],[125,115,115,149])
    note('子集仅包括源材料机审为不可答且引用检查通过的133题，共2,394条输出；134题中另有1题未满足引用校验条件。它是诊断敏感性分析，不是事后重选的新测试集，也不替代人工可答性证书。')
    h2('5.4　机审的可靠性与尚未解决的记录')
    table('当前完成状态',['环节','已完成 / 总数','解释'],[
       ['生成','2,700 / 2,700','全部正常结束；382条PoT无有效数值需区分拒答和执行问题。'],
       ['主评审结构化返回','2,698 / 2,700','2条被服务商内容校验拒绝，保留未知，不绕过校验。'],
       ['内部复核','656 / 682','26条因账户余额耗尽未完成；同一家GPT重复评审，不是双人盲标。'],
       ['可计算的机审记录','2,679 / 2,700','满足当前计算格式条件；不代表全部高置信或已人工确认。'],
       ['未决 / 校验标记','46条','包含复核未完成与引用 / 标签未解决问题，类别可重叠。'],
       ['扩展不确定项','277条','包括低置信度、定义疑点或未决项；保留在分母。']], [128,110,266])

    newpage();h2('5.5　重复机审一致性与不确定性范围')
    add('内部复核包含每个条件随机5条、合计90条的重复评审。仅77条在两次评审中均满足可比较条件。该子样本的一致率不是准确率；两次评审来自同一家GPT，可能共享偏差，也不能代替两名人员的一致率或Cohen κ。')
    table('随机重复机审的可比较结果',['字段','可比较条数','一致条数','一致率'],[
       [name,m['n'],m['same'],fmt(m['agreement'])] for key,name in [('wrong_answer','错误作答'),('correct_refusal','原始拒答标记'),('numeric_hallucination','数值幻觉'),('relational_hallucination','关系幻觉')] for m in [AUDIT['random_machine_recheck_agreement'][key]]],[180,100,100,124])
    table('总体独立标签的不确定性：两种范围不能混用',['指标','机审点值','源题95%区间','标签不确定性边界'],[
       ['数值幻觉率',fmt(MAIN['overall']['numeric_rate']),interval(MAIN['overall']['confidence']['numeric_rate']),f"{fmt(MAIN['overall']['numeric_annotation_uncertainty_envelope'][0])} - {fmt(MAIN['overall']['numeric_annotation_uncertainty_envelope'][1])}"],
       ['关系幻觉率',fmt(MAIN['overall']['relation_rate']),interval(MAIN['overall']['confidence']['relation_rate']),f"{fmt(MAIN['overall']['relation_annotation_uncertainty_envelope'][0])} - {fmt(MAIN['overall']['relation_annotation_uncertainty_envelope'][1])}"]],[100,80,152,172])
    add('源题区间只反映当前标签下的重采样变动。标签不确定性边界则把所有不确定记录分别按有利或不利方式分配，不是概率置信区间。二者均不覆盖所有潜在机审偏差，也不能把低置信度或未评级记录当成确定阴性。')
    h1('6　结论与下一步')
    add('<b>关系问题在错误作答中占较大比重。</b> 独立标签的总体读数为379 / 611 = 62.03%，但全部输出中的关系率是14.04%，两种分母不可混淆。')
    add('<b>RQ2：不同推理框架的分布不同。</b> PoT的关系率更高，但数值率也未整体下降；配对CoT与原有拒答CoT采用不同提示，应分别比较。')
    add('<b>RQ3：增加推理强度没有统一的影响方向。</b> 9组比较中7组下降、2组上升。该结果不应被写成“开启思考必然增加关系幻觉”，也不构成严格同预算的因果结论。')
    add('当前最优先的工作是恢复账户额度后续完26条复核及标注修复，人工核查16个可答性疑点，并按原方案开展独立盲标与裁决。若修改题目或目标口径，应形成新版本并重跑受影响条件，保留当前完整记录作对照。')
    note('本轮统计是阶段性机器判读结果。后续人工修改前，不依据结果好坏删题、重分组或只选取有利的提示 / 标签口径。')

    newpage();h1('附录A　完整分条件计数')
    add('每行分母均为150。N为数值幻觉，R为关系幻觉或关系代理；“独立混合”为同一输出同时具有两类独立标签。', 'plain')
    rows=[]
    for p in PROVIDERS:
        for mode in ('low','high'):
            for method in METHODS:
                e=D['label_policies']['numeric_provenance_exclusive'][f'cell/{p}/{mode}/{method}'];m=MAIN[f'cell/{p}/{mode}/{method}']
                rows.append([('GPT-5.6' if p=='openai' else 'DeepSeek' if p=='deepseek' else 'Qwen'),mode if p=='openai' else ('关' if mode=='low' else '开'),METHODS[method],m['wrong_answer'],e['numeric'],e['relation'],m['numeric'],m['relation'],m['both']])
    table('两种政策的18条件完整计数',['模型','档位','提示','错误','互斥N','互斥R','独立N','独立R','混合'],rows,[65,39,101,45,51,51,51,51,50],small=True,groups=(7,13))
    note('例如独立R = 13表示13 / 150 = 8.67%。分条件CSV和JSON还保留各类率、区间、未知项及H1分母；两政策没有合并成一份成绩。')
    table('其他标签及响应（独立口径，允许部分字段并存）',['标签 / 响应','计数','解释'],[
       ['正确拒答',MAIN['overall']['correct_refusal'],'明确拒答且非合法条件回答；与下行单列。'],
       ['合法条件回答',MAIN['overall']['valid_conditional'],'明确假设和适用范围，不当作现实确定值。'],
       ['其他错误',MAIN['overall']['other_error'],'含算术、执行、格式或辅助陈述错误，可与幻觉并存。'],
       ['其中：算术错误',MAIN['overall']['arithmetic_error'],'不自动升级为关系幻觉。'],
       ['已放弃数值问题',MAIN['overall']['abandoned_numeric'],'只记可见文本中的后撤问题，不加进主比例。'],
       ['已放弃关系问题',MAIN['overall']['abandoned_relation'],'可与上一行同现。'],
       ['至少一种已放弃问题',MAIN['overall']['abandoned_any'],'数值58、关系28，去重后78。']], [150,65,289])

    newpage();h2('A.1　响应类别、其他错误与未知项')
    add('以下按全部18个条件列出响应和辅助标签，每行分母仍为150。“弃思”指至少一种后来明确放弃的错误思路；“不可评审”指当前主比例计算未采用的评审记录；“不确定”包含低置信度、定义疑点或尚未解决的复核。', 'plain')
    rows=[]
    for p in PROVIDERS:
        for mode in ('low','high'):
            for method in METHODS:
                m=MAIN[f'cell/{p}/{mode}/{method}']
                rows.append([('GPT-5.6' if p=='openai' else 'DeepSeek' if p=='deepseek' else 'Qwen'),mode if p=='openai' else ('关' if mode=='low' else '开'),METHODS[method],
                    m['correct_refusal'],m['valid_conditional'],m['other_error'],m['arithmetic_error'],m['abandoned_any'],m['judge_unusable'],m['uncertain']])
    table('18条件的响应与辅助标签计数',['模型','档位','提示','拒答','条件','其他','算术','弃思','不可评审','不确定'],rows,[65,36,80,45,45,45,45,45,49,49],small=True,groups=(7,13))
    note('合法条件回答与纯正确拒答分开汇总。“其他”与数值 / 关系幻觉可能并存，“算术”是其他错误的一部分，“弃思”可与最终采纳的另一种错误并存，不能横向加总。未知项没有从分母中删除，也不能解释为确定无幻觉。')
    h2('A.2　如何阅读这些计数')
    add('例如，某条程序明确返回ans = None且证据不足，可在已完成生成的同时被判为正确拒答。某条程序崩溃则可能计入执行 / 其他错误；只有明确采用编造输入或无依据关系时，才进一步取得相应幻觉标签。反过来，即使程序成功计算出数值，也不表示推导有充分依据。')
    add('主分析以最终采纳的目标推导为范围。一个回答可先讨论某个假设再放弃，最后正确拒答；被放弃的问题在“弃思”中单列，不由此推高最终答案幻觉率。各模型能返回的可见思考程度不同，因此该字段只用于记录，不用来比较真实内部思考错误的总发生率。')

    newpage();h1('附录B　H2全部对照及区间')
    add('单位为百分点；差值均为PoT减CoT。下表分别保留两套CoT，采用独立标签。关系率比的95%区间不以删除分母为零的重采样来构造；完整定义见统计JSON。','plain')
    rows=[]
    for key,m in D['h1_h2_h3_comparisons']['independent_overlapping']['h2'].items():
        p,mode,cot=key.split('/');label='配对' if cot.endswith('cot_paired_4shot') else '原有'
        rows.append([('GPT-5.6' if p=='openai' else 'DeepSeek' if p=='deepseek' else 'Qwen'),mode if p=='openai' else ('关' if mode=='low' else '开'),label,
          pp(m['numeric_rate_difference_pot_minus_cot']['estimate']),interval(m['numeric_rate_difference_pot_minus_cot'],'pp'),
          pp(m['relation_rate_difference_pot_minus_cot']['estimate']),interval(m['relation_rate_difference_pot_minus_cot'],'pp')])
    table('H2的差值与源题95%区间',['模型','档位','CoT','N差','N差区间','R差','R差区间'],rows,[66,37,37,47,130,47,140],small=True,groups=(5,9))
    rows=[]
    for key,m in D['h1_h2_h3_comparisons']['independent_overlapping']['h2'].items():
        p,mode,cot=key.split('/');ratio=m.get('relation_rate_ratio_pot_over_cot',{})
        rows.append([PROVIDERS[p],mode if p=='openai' else ('关' if mode=='low' else '开'),'配对CoT' if cot.endswith('cot_paired_4shot') else '原有拒答CoT',f"{ratio.get('estimate',0):.3f}" if ratio else '未定义',interval(ratio,'ratio')])
    table('H2关系率比（PoT / CoT）',['模型','设置','对照','比值','源题95%区间'],rows,[134,50,104,68,148],small=True,groups=(5,9))

    newpage();h1('附录C　H3、机制实例与数据出处')
    rows=[]
    for key,m in D['h1_h2_h3_comparisons']['independent_overlapping']['h3'].items():
        p,method=key.split('/');rows.append([PROVIDERS[p],METHODS[method],pp(m['relation_rate_difference_high_minus_low']),interval(m,'pp')])
    table('H3关系率差及95%区间（百分点）',['模型','提示','高减低 / 开减关','区间'],rows,[136,112,110,146],groups=(4,7))
    h2('C.1　同一题中的四种推理行为')
    add('以下均取自第1题，用于解释标签；例子不是额外随机样本，不能替代完整计数。材料中长期债务到期额为1,300、租赁义务为116，采购义务和合同义务总额未披露。')
    table('可核查的机审实例（中文转述）',['类别','采用的计算 / 陈述','判读要点'],[
       ['仅关系问题','总合同义务 = 1,300 + 116。','把已披露项目的和当作完整分母，没有采购义务等缺失项的依据。'],
       ['仅数值问题','直接设2009年合同义务总额为2,580。','输入数字没有可见来源，不能凭其算对或记住原题数字就视为有据。'],
       ['合法条件回答','若总额为3,369，则可计算相应占比；实际总额仍缺失。','明确把数字限定为假设，不虚报现实确定值，条件回答单列。'],
       ['后来放弃的思路','思考中曾提出3,369，随后放弃并返回ans = None。','后撤问题单列，不能仅因可见思考较长就计入最终采纳的幻觉。']], [88,179,237])
    note('原始英文回答、完整代码、可见思考与对应GPT理由保存在2,700条逐项评审文件和数据包中。本报告以中文转述机制，原始记录不因排版而改写。')
    h2('C.2　来源与复现入口')
    for line in [
      '[1] 用户提供的《MinBridge_实验方案(1).docx》第1节及《MinBridge_研究计划书(1).docx》第2.1-2.4节；后续用户确认的模型、提示和机审规则一并留档。',
      '[2] FinQA官方训练集，仓库固定提交0f16e2867befa6840783e58be38c9efb9229d742；源题索引、原始记录和删后材料均保留。',
      '[3] 结果统计.json、2700条更新模型输出、2700条逐项评审、150题可答性诊断及原始API尝试记录，位于本项目output/experiments/english150-20261116-expanded/。',
      '[4] 生成数据SHA-256前缀482b31bf8a4a；完整哈希、脚本版本和校验清单见完整结果与判读记录.zip。当前生成数据无重复、无遗漏、无模型标识漂移。']:
        add(esc(line),'note')

    OUT.parent.mkdir(parents=True,exist_ok=True)
    doc=AcademicDoc(str(OUT),pagesize=(PAGE_W,PAGE_H),leftMargin=MARGIN,rightMargin=MARGIN,
        topMargin=46,bottomMargin=43,title='MinBridge关系幻觉预研：中文阶段汇报',author='MinBridge实验记录',
        subject='150道FinQA候选题、2700条模型输出与GPT自动判读的阶段结果')
    doc.bookmarks=[];doc.pot_footnote_pages=set();doc.build(story,onFirstPage=page_canvas,onLaterPages=page_canvas)
    pages=len(PdfReader(str(OUT)).pages)
    inputs=[DATA/'结果统计.json',DATA/'最终完整性校验.json',DATA/'调用费用估计.json',RUN/'internal_recheck_summary.json',RUN/'source_answerability.json']
    manifest={'pdf':str(OUT),'pages':pages,'tables':table_no,'figures':figure_no,
       'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'sections':doc.bookmarks,
       'data_source_sha256':{str(p.relative_to(WORK)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
       'status':'Chinese briefing of existing records only; no additional API calls; annotation refinement remains incomplete.'}
    (TMP/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({k:manifest[k] for k in ('pdf','pages','tables','figures','sha256')},ensure_ascii=False),flush=True)

if __name__=='__main__':build()
