"""Requested background/setup revision; exact prompts and observed labeled cases."""
import hashlib,json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph,Spacer,KeepTogether
import prompts

CASES=[
 {'type':'缺失项被擅自设为零','case':72,'id':'974202071772dc1fd0a82e4044853b6263629ad7d6e80ae86f4031ff609f546c',
  'question':'2008年第四季度回购股数中，12月回购占多少？',
  'evidence':'10月和11月分别为25,394股、7,526股；12月股数和季度总数均未披露。',
  'adopted':'模型直接令12月回购量=0，再计算季度总数和12月占比，输出0。',
  'why':'“未披露”不蕴含“等于零”。新增约束“12月回购量=0”决定分子和分母，是无依据的关键补值关系。'},
 {'type':'把已披露子集当成完整总额','case':1,'id':'21c90b1d9a14d8cf0b0445005661ca1bbb566d049b6de6638a639fd677c005ce',
  'question':'2009年长期债务到期额占未来合同义务总额的比例是多少？',
  'evidence':'金额单位为百万美元：到期额1,300、租赁义务116；采购义务和合同义务总额缺失。',
  'adopted':'模型采用“总合同义务=1,300+116”，再计算1,300/(1,300+116)。',
  'why':'把部分项目之和等同于完整总额，隐含排除了未披露的采购义务；材料没有支持这一完整性假设。'},
 {'type':'跨期间或现金流口径替代','case':55,'id':'5d82017797b3f5c4cd255780c1022bad78d22cc9853e4e6658fe8401bb57f59f',
  'question':'2007年经营租赁费用的增长率是多少？',
  'evidence':'2006年租赁费用为45,000千美元，2007年费用缺失；从未来最低付款表可倒算2008年付款30,774千美元。',
  'adopted':'模型将30,774当作2007年租赁费用，计算(30,774-45,000)/45,000，给出约-31.61%。',
  'why':'2008年的未来最低付款不等于2007年的实际租赁费用；这个跨期、跨口径相等关系没有依据。'},
 {'type':'把另一指标绑定为缺失指标','case':15,'id':'3b971ca238b8d30aeed9a35415fe2cfce1f579dec553655faeeb2d73e87d8f64',
  'question':'2007-2009年其他无形资产的平均摊销费用是多少？',
  'evidence':'金额单位为百万美元：2007年8.5、2009年19.3，2008年摊销缺失；13.9来自表中CMG外币折算项。',
  'adopted':'模型令2008年摊销费用=13.9，再计算(8.5+13.9+19.3)/3。',
  'why':'13.9这一数字虽出现于材料，却属于另一指标。问题出在把两个不同类型的金融量设为相等，而非凭空创造13.9。'},
 {'type':'期间平均量替代时点基准','case':94,'id':'351d3dce20bd654369124ca0854998e24cbc010baa4a14748cbfd2bd1d932e31',
  'question':'2012-2016年欧洲邮轮市场预期新增床位容量的百分比是多少？',
  'evidence':'预计新增28,000；2011年加权平均营销床位149,000；2011年末容量未披露。',
  'adopted':'模型把149,000作为期初容量基数，计算28,000/149,000×100，给出约18.79%。',
  'why':'期间加权平均供应量与年末容量不是同一变量；将二者等同是决定分母的额外关系。该题目标口径也已列入人工核查清单。'},
 {'type':'改变统计范围或平均定义','case':150,'id':'ed88604415a66d10350f3a7b593552ded4d163657734fef76b6dc248df01b1e6',
  'question':'2011-2013年的平均预期波动率是多少？',
  'evidence':'2011年28.8%、2013年22.1%，2012年缺失。',
  'adopted':'模型用(28.8+22.1)/2作为区间平均值。',
  'why':'它将三年范围的平均替换为两个已披露端点的平均，未经题目或材料授权；正确计算25.45%并不能使这一范围替换成立。'},
 {'type':'添加无依据的大小或方向约束','case':42,'id':'9bffe708bf47475ca6bd0c9399e83825cc9054ba2e263a9224215b8baca38c9e',
  'question':'K系列五年总回报是否跑赢标普500？',
  'evidence':'K系列从100降至55.04；标普500的2018年终值缺失，因而其完整五年回报未确定。',
  'adopted':'模型断言标普500“五年回报为正”，据此回答K系列未跑赢。',
  'why':'材料没有支持“标普500五年回报>0”这一不等式。关系幻觉也可表现为决定比较结论的约束，不限于计算公式。'},
]

def quote(g,title,raw):
    style=ParagraphStyle('prompt_quote',fontName='Times',fontSize=9.6,leading=12.6,spaceAfter=7,
                         borderColor=g['colors'].HexColor('#c6c6c6'),borderWidth=.4,borderPadding=8,
                         backColor=g['colors'].HexColor('#f7f7f7'),splitLongWords=True)
    g['h2'](title)
    # Actual prompt spelling and line structure are retained; line wrapping is visual.
    g['story'].append(Paragraph(escape(raw).replace('\n','<br/>'),style))

def background(g):
    add,h1,h2,note=g['add'],g['h1'],g['h2'],g['note']
    h1('1　背景与研究问题')
    h2('1.1　判定对象与严格定义')
    add('设F为当前问题和材料中可见的事实集合；每个金融量由“指标、实体、期间、单位”四元组标识。以下定义只评价回答最终采纳的事实、关系和结论；明确声明的合法条件回答，以及提出后又明确否定的试探思路，不作为主答案的幻觉。')
    add('<b>数值幻觉。</b> 当且仅当存在一个被最终采纳的定量输入v，同时满足：①v被当作真实事实使用，而非明确限定的假设值；②v既不能由F直接溯源，也不能通过有依据的推导、合法单位换算或适用的数学常数从F得到；③它属于编造或篡改的输入量，而非单纯算错的中间结果。三个条件须同时成立。')
    add('数字未逐字出现，不足以判定数值幻觉：合法推导的新数值不属于编造；错误计算的中间数值另记算术错误。仅把材料中的数值或数学常数绑定到错误金融量，主要作为关系问题审查；例如“缺失量=0”主要检查这条补值约束，不仅因为字面0额外判数值幻觉。')
    add('<b>关系幻觉。</b> 当且仅当存在一个被最终采纳的方程、映射或约束r，同时满足：①r不由问题、材料或当前口径下适用的公认恒等式 / 明确定义支持，即为额外假设T4或未声明的非唯一口径T3；②r是当前推导得到目标结果的关键桥接关系，去掉r后该推导不再足以得到所声称的结果；或者r无依据地替换了问题 / 材料的明确目标定义，构成定义漂移。')
    add('关系可以是“缺失项=0”“部分之和=整体”“另一期间值=当前值”，也可以是决定比较答案的大小约束。纯算术错误、单纯执行失败，以及没有被最终采用的错误关系，不因其出错而自动归为关系幻觉。')
    add('<b>错误目标作答。</b> 指证据不足时仍给出现实目标的确定答案、证据充足时结论错误，或条件回答的推导本身错误；合法条件回答不因含有数值而自动计错。')
    add('<b>统计实现。</b> 主比例使用“正常结束生成且评审可用 ∩ 错误目标作答 ∩ 相应幻觉标签”作为分子，全体输出作为分母。标签允许并存。关系判定由GPT依据关键原文片段及上述标准完成，并非已取得符号求解器的完备反事实证明。数字溯源互斥代理另在第3节定义，不用它替代上述独立关系判定。')
    h2('1.2　数值幻觉实例')
    add('<b>第1题，Qwen3.8-27B，开启思考，PoT。</b> 题目要求2009年长期债务到期额占合同义务总额的比例。材料披露到期额1,300，但总额及采购义务未披露。模型直接设置“总合同义务=2,580”，再以1,300/2,580计算。2,580既无可见来源，也未由已知量合法推导，却被当作实际输入使用，因此当前机审将其判为数值幻觉。')
    h2('1.3　关系幻觉的具体机制与实例')
    note('以下七类是对当前关系标签实例的机制归纳，可相互重叠，不是新增的互斥统计标签。每个例子均来自这150题的真实输出，且已被当前机审判为关系幻觉；仍需后续人工核查。')
    outputs={r['id']:r for r in map(json.loads,(g['RUN']/'effective_outputs_2700.jsonl').read_text().splitlines())}
    annotations={a['id']:a for a in map(json.loads,(g['RUN']/'machine_annotations_final.jsonl').read_text().splitlines())}
    provenance=[]
    for i,example in enumerate(CASES,1):
        block_start=len(g['story'])
        out=outputs[example['id']];a=annotations[example['id']]
        assert out['case_number']==example['case'] and a['annotation']['labels']['relational_hallucination']
        assert a['annotation']['labels']['wrong_answer'] and not a['validation_issues']
        mode=out['mode'] if out['provider']=='openai' else '关闭思考' if out['mode']=='low' else '开启思考'
        h2(f'（{i}）{example["type"]}')
        note(f'第{example["case"]}题 | {g["PROVIDERS"][out["provider"]]} | {mode} | {g["METHODS"][out["method"]]}')
        add('<b>问题：</b>'+escape(example['question'])+'<br/><b>可见事实：</b>'+escape(example['evidence'])+'<br/><b>模型采用的推导：</b>'+escape(example['adopted'])+'<br/><b>判定依据：</b>'+escape(example['why']),'plain')
        block=g['story'][block_start:];g['story'][block_start:]=[KeepTogether(block)]
        provenance.append({'mechanism':example['type'],'case':example['case'],'id':example['id'],
                           'model_annotation':a['annotation'],'response_sha256':hashlib.sha256(out['content'].encode()).hexdigest()})
    (g['TMP']/'revised_example_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2))
    h2('1.4　研究问题')
    add('<b>RQ1：关系幻觉是否存在？占比如何？</b> 报告其占全部输出的比例，以及占错误作答的比例。','plain')
    add('<b>RQ2：不同推理框架下，关系幻觉的分布如何？</b> 比较PoT、配对CoT和原有拒答CoT。','plain')
    add('<b>RQ3：推理强度如何影响关系幻觉？</b> 比较同模型同提示的高低设置，观察能否降低关系幻觉。','plain')
    note('CoT、PoT本身是推理方法；其具体提示及执行器配置可视为harness配置。本文统一称为“推理框架”。')

def experiment_setup(g):
    add,h1,h2,note,table=g['add'],g['h1'],g['h2'],g['note'],g['table']
    g['newpage']();h1('2　实验设置')
    h2('2.1　数据、删除比例与实验数量')
    add('我们基于FinQA官方训练集构造了150道不可答题，之后将进行人工检查，确保这150道题确实不可答。')
    add('对每道题，N为删除前材料及题干中去重后的定量金融 / 经营事实总数，D为实际删除的此类事实数，删除比例ρ=D/N。同一指标、实体、期间、单位的重复披露只计一次；不同事实即使数值相同也分别计数。年份、页码、注释编号和单位换算常数不单独计入N。')
    add('低删、中删、高删按ρ构造，数量为90、30、30，比例6:2:2；不是简单地规定每题分别删1、2、3个数字。本批次各组的实际删除比例范围如下，并非通用的预设阈值。')
    table('删除比例分组',['组别','题数','实际删除比例ρ'],[
       ['低删','90','0.85% - 9.09%'],['中删','30','15.38% - 22.73%'],['高删','30','30.77% - 66.67%']],[120,100,284])
    note('中删组上限按第2题已记录的事实计数校勘计算：D=5、N=22，ρ=22.73%；原分组与已有统计结果不变。分组在查看模型输出前构造。')
    add('<b>实验数量：</b>150题 × 3个模型 × 3种推理框架 × 2档推理设置 = <b>2,700条输出</b>。','plain')
    h2('2.2　模型与推理强度')
    table('模型与两档设置',['模型','两档设置'],[
       ['GPT-5.6 Sol','low / high'],['DeepSeek-V4-Pro','关闭 / 开启思考'],['Qwen3.8-27B','关闭 / 开启思考']],[252,252])
    h2('2.3　CoT与PoT的来源及实际提示差异')
    add('<b>配对CoT。</b> CoT的基本方法见Wei等的论文<i>Chain-of-Thought Prompting Elicits Reasoning in Large Language Models</i>（2022；<link href="https://arxiv.org/abs/2201.11903">arXiv:2201.11903</link>）。本次“配对CoT”不是该论文的一份原版金融提示：我们取下述PoT论文配套代码的FinQA四示例，将Python解答改写成文字推导，其余示例证据和问题保持配对。因此它是本项目构造的CoT适配版。')
    add('<b>原有拒答CoT。</b> 来源是Hall、Shome与Eiers的<i>VeriFin: A Neurosymbolic Framework for Verifying LLM-Generated Financial Claims</i>（2026；<link href="https://arxiv.org/abs/2608.10213">arXiv:2608.10213</link>）及其<link href="https://github.com/verifiedfinance/anon/blob/main/src/verifiqa/answerers/cot.py">配套代码cot.py</link>中的CotAnswerer。本次保留该代码的任务指令和拒答句，只将问题与证据适配为FinQA。它没有加入四道演示例。')
    add('<b>PoT<super>1</super>。</b> 来源是Chen等的<i>Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks</i>（TMLR 2023；<link href="https://arxiv.org/abs/2211.12588">arXiv:2211.12588</link>）；它要求生成Python，再交给执行器计算。配对CoT与PoT的主要差别是示例解答和输出形式；原有CoT还同时改变了示例数量，并明确要求证据不足时拒答。')
    quote(g,'配对CoT：实际任务指令与目标题模板',
'''Read the following text and table, and then explain the facts, formula and calculation to answer a question:
{text}
{table}
Question: {question}
Reasoning:''')
    note('上面的指令用于四道演示例，也用于末尾待答题；{text}、{table}、{question}为填入材料的变量位。实际请求依次放入四道完整示例，再放入待答题；没有额外添加“证据不足就拒答”的句子。')
    add('四道配对示例依次演示：可供出售投资占总现金及投资的比例；特定收益交易日占比；两项无形资产在采用20年期限时的年摊销；2007至2008年资产的百分比变化。', 'plain')
    quote(g,'同一示例的配对CoT推导原文（示例1）',prompts.SOLUTIONS[0])
    note('对应示例问题：2012年12月29日可供出售投资占总现金及投资的比例是多少？同一材料的两个相关输入为14,001和26,302。四示例和文字推导由本项目适配，不称作PoT作者发布的原版CoT。')
    first_pot=prompts.parts()[3][0].split('\n#Python\n',1)[1]
    quote(g,'同一示例的PoT解答原文',first_pot)
    note('PoT的任务指令使用“and then write code to answer a question:”，目标题末尾为“#Python”；配对CoT将它们分别换成上面的文字推导指令和“Reasoning:”。')
    quote(g,'原有拒答CoT：实际完整任务模板',prompts.existing_template().strip())
    add('该模板要求“仅使用提供的证据”“展示计算步骤并给出数值答案”，并明确写出：<b>If the evidence is insufficient, say so rather than guessing.</b>（若证据不足，应说明不足，而不是猜测。）配对CoT依靠四示例引导推导，没有这句拒答要求。两种CoT的表现差异因此不能只解释为“是否使用拒答句”这一个因素。')
