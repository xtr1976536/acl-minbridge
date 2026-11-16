"""Chinese research-facing descriptive report and figures from machine annotations."""
import collections,hashlib,json,math
from pathlib import Path
from expanded_engine_concurrent import HERE,ROOT,OLD,readlines,save

DEST=HERE.parents[1]/'output/experiments/english150-20261116-expanded'
PROVIDERS={'openai':'GPT-5.6 Sol','deepseek':'DeepSeek-V4-Pro','qwen':'Qwen3.8-27B'}
METHODS={'cot_paired_4shot':'配对CoT','pot':'PoT','cot_existing_abstention':'原有拒答CoT'}
POLICIES={'numeric_provenance_exclusive':'数字溯源互斥口径','independent_overlapping':'独立标签口径'}
def pct(v):return '—' if v is None else f'{v*100:.2f}%'
def pp(v):return '—' if v is None else f'{v*100:+.2f}'
def ci_text(c):
    if not c or c.get('ci95') is None:return '未定义'
    return f"[{c['ci95'][0]*100:.2f}%, {c['ci95'][1]*100:.2f}%]"
def number(value):return f'{value:.3f}' if value is not None else '—'

def fees():
    base=json.loads((OLD/'progress.json').read_text())['cost_upper_estimate_usd'];phases={}
    for path in ROOT.glob('*_attempts.jsonl'):
        rows=readlines(path);phases[path.stem]={'attempts':len(rows),'cost_upper_usd':sum(r['cost_upper_estimate_usd'] for r in rows)}
    result={'previous_generation_cost_upper_usd':base,'phases':phases,
        'cumulative_cost_upper_usd':base+sum(v['cost_upper_usd'] for v in phases.values()),
        'budget_policy':'User removed cumulative budget limit. Estimates are conservative undiscounted usage accounting, not provider invoices.'}
    save(ROOT/'all_phase_costs.json',result);save(DEST/'调用费用估计.json',result);return result

def make_figures(data):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    import numpy as np
    font=Path('/System/Library/Fonts/STHeiti Medium.ttc')
    if font.exists():fm.fontManager.addfont(str(font));family=fm.FontProperties(fname=str(font)).get_name()
    else:family='DejaVu Sans'
    plt.rcParams.update({'font.family':family,'font.size':11,'axes.unicode_minus':False,
        'axes.spines.top':False,'axes.spines.right':False,'axes.labelsize':11,'pdf.fonttype':42})
    palette={'numeric_rate':'#176986','relation_rate':'#BA542F'}
    independent=data['label_policies']['independent_overlapping'];methods=list(METHODS)
    fig,axes=plt.subplots(3,2,figsize=(12,10),constrained_layout=True,sharex=True)
    top=max((independent[f'cell/{p}/{m}/{t}']['confidence'][rate]['ci95'] or [0,independent[f'cell/{p}/{m}/{t}'][rate]])[1] for p in PROVIDERS for m in ('low','high') for t in methods for rate in palette)
    xmax=min(100,max(15,math.ceil((top*100+6)/10)*10))
    for i,(provider,name) in enumerate(PROVIDERS.items()):
        for col,mode in enumerate(('low','high')):
            ax=axes[i,col];y=np.arange(3)
            mode_label=('低强度' if mode=='low' else '高强度') if provider=='openai' else ('关闭思考' if mode=='low' else '开启思考')
            for rate,offset,label,hatch in [('numeric_rate',-.18,'数值幻觉',''),('relation_rate',.18,'关系幻觉','///')]:
                vals=[independent[f'cell/{provider}/{mode}/{method}'][rate]*100 for method in methods]
                intervals=[independent[f'cell/{provider}/{mode}/{method}']['confidence'][rate]['ci95'] for method in methods]
                ax.barh(y+offset,vals,height=.32,color=palette[rate],label=label,hatch=hatch,edgecolor='white',linewidth=.4)
                for j,(v,interval) in enumerate(zip(vals,intervals)):
                    if interval is not None:ax.errorbar(v,y[j]+offset,xerr=[[max(0,v-interval[0]*100)],[max(0,interval[1]*100-v)]],fmt='none',ecolor='#31373D',capsize=2,linewidth=.8)
                    right=interval[1]*100 if interval is not None else v
                    ax.text(min(right+.8,xmax-4.5),y[j]+offset,f'{v:.1f}%',va='center',fontsize=9)
            ax.set(yticks=y,yticklabels=[METHODS[t] for t in methods],xlim=(0,xmax),title=f'{name} · {mode_label}');ax.invert_yaxis()
            ax.xaxis.grid(True,color='#D8DFE3',linewidth=.6);ax.set_axisbelow(True)
            if i==2:ax.set_xlabel('占该条件全部150条输出的比例（%）')
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=2,frameon=False,title='误差线：源题配对bootstrap 95%区间（不含机审误差）',title_fontsize=10)
    fig.suptitle('最终采纳推导的幻觉比例（GPT机审，独立标签）',fontsize=16,fontweight='medium')
    fig.savefig(DEST/'独立标签_18条件对照.png',dpi=240,facecolor='white');fig.savefig(DEST/'独立标签_18条件对照.pdf',facecolor='white');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4.5),constrained_layout=True,sharey=True)
    x=np.arange(3)
    for ax,(policy,title) in zip(axes,POLICIES.items()):
        for rate,offset,label,hatch in [('numeric_rate',-.19,'数值幻觉',''),('relation_rate',.19,'关系幻觉 / 关系代理','///')]:
            values=[data['label_policies'][policy]['model/'+p][rate]*100 for p in PROVIDERS]
            ax.bar(x+offset,values,width=.35,color=palette[rate],label=label,hatch=hatch,edgecolor='white')
            for xx,v in zip(x+offset,values):ax.text(xx,v+.6,f'{v:.1f}%',ha='center',fontsize=10)
        ax.set(xticks=x,xticklabels=['GPT-5.6','DeepSeek','Qwen'],title=title,ylabel='占该模型全部900条输出的比例（%）')
        ax.yaxis.grid(True,color='#D8DFE3',linewidth=.6);ax.set_axisbelow(True)
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=2,frameon=False)
    fig.suptitle('两种测量口径分别报告，不混为一个成绩',fontsize=15,fontweight='medium')
    fig.savefig(DEST/'两种口径_模型汇总.png',dpi=240,facecolor='white');fig.savefig(DEST/'两种口径_模型汇总.pdf',facecolor='white');plt.close(fig)

def main():
    data=json.loads((ROOT/'analysis_results.json').read_text());cost=fees()
    effective=json.loads((ROOT/'effective_outputs_manifest.json').read_text());review=json.loads((ROOT/'internal_recheck_summary.json').read_text())
    labels=readlines(ROOT/'machine_annotations_final.jsonl');outputs={r['id']:r for r in readlines(ROOT/'effective_outputs_2700.jsonl')}
    audit_latest={r['job_id']:r for r in readlines(ROOT/'audit_attempts.jsonl')}
    audit_finished=sum(r['status']=='completed' for r in audit_latest.values())
    audit_credit_blocked=sum('credit_balance_exhausted' in str(r.get('error','')) for r in audit_latest.values())
    sources=json.loads((ROOT/'source_answerability.json').read_text())
    rejected=[r['id'] for r in labels if r.get('provider_content_rejection')]
    unresolved=[r['id'] for r in labels if r.get('validation_issues') or r.get('review_unresolved')]
    lines=['# MinBridge关系幻觉预研：更新输出与GPT自动判读','',
       (f'**当前为待续核快照：** 生成部分2,700条全部完成；最后{audit_credit_blocked}条内部复核因OpenAI账户余额耗尽未完成，另有标注校验问题未解决。下列比例保留全部未决标记。' if audit_credit_blocked else '**当前为机器评审统计：** 生成记录完整，仍须结合未决标记和可答性疑点解读，不能替代人工金标。'),'',
       '本轮保留固定150道源题、3个模型、3套提示和2档设置，共2,700条实验条件。下列比例来自GPT-5.6 Sol主评及内部机器复核，尚未经过两名人员独立盲标和第三人裁决；不能称为已验证的人工金标或正式假设检验。','',
       '## 1. 补跑后的结果完整性','',
       f"最终2,700条均正常结束生成，连接/流中断与长度截断均为0。PoT中有{effective['generation_status'].get('execution_failed',0)}条完整程序未取得有效数值，包含`ans = None`等拒答表达，不能直接视为幻觉或没有跑完。",'',
       '原始8条GPT连接中断和182条其他模型截断均已重跑；仍截断者按授权进一步放宽。最终token上限分布：'+ '；'.join(f'{k} tokens：{v}条' for k,v in effective['token_caps'].items())+'。原有输出和全部新尝试均留档，没有根据答案好坏选择重跑结果。','',
       'GPT采用low/high；DeepSeek和Qwen采用关闭/开启思考。两个CoT提示分别为配对4-shot CoT和保留拒答指令的原有CoT，不合并为一种提示。','',
       '## 2. 全部2,700条中的比例','',
       '首张汇总表以全部2,700条候选题输出为分母，后面的模型表以900条、条件表以150条为分母。按“每条输出是否包含该类错误”计数，不按推理步骤计数。主统计只评价最终采纳的推导与结论，并要求它构成错误目标作答；不完整/不可评审记录仍保留在分母。','',
       '|口径|错误作答|数值幻觉|关系幻觉／关系代理|两类同时出现|关系占错误作答|','|---|---:|---:|---:|---:|---:|']
    for policy,title in POLICIES.items():
        m=data['label_policies'][policy]['overall'];n=m['n_all_nominal_unanswerable']
        lines.append(f"|{title}|{m['wrong_answer']}/{n}（{pct(m['wrong_answer_rate'])}）|{m['numeric']}/{n}（{pct(m['numeric_rate'])}）|{m['relation']}/{n}（{pct(m['relation_rate'])}）|{m['both']}|{pct(m['h1_relation_share_among_wrong'])}|")
    ind=data['label_policies']['independent_overlapping'];paired=ind['method/cot_paired_4shot'];pot=ind['method/pot']
    h2core=[v for k,v in data['h1_h2_h3_comparisons']['independent_overlapping']['h2'].items() if k.endswith('pot_vs_cot_paired_4shot')]
    numeric_lower=sum(v['numeric_rate_difference_pot_minus_cot']['estimate']<0 for v in h2core)
    relation_15=sum(v.get('relation_rate_ratio_pot_over_cot',{}).get('estimate',-1)>=1.5 for v in h2core)
    joint=sum(v['numeric_rate_difference_pot_minus_cot']['estimate']<0 and v.get('relation_rate_ratio_pot_over_cot',{}).get('estimate',-1)>=1.5 for v in h2core)
    h3=[v['relation_rate_difference_high_minus_low'] for v in data['h1_h2_h3_comparisons']['independent_overlapping']['h3'].values()]
    lines+=['', '**当前自动判读的主要读数：**','',
        f"1. H1所关心的关系错误在本批错误作答中占{pct(ind['overall']['h1_relation_share_among_wrong'])}，点估计超过30%；它不是“全部输出中关系错误超过30%”。",
        f"2. PoT的关系幻觉率为{pct(pot['relation_rate'])}，高于配对CoT的{pct(paired['relation_rate'])}；但PoT数值幻觉率为{pct(pot['numeric_rate'])}，配对CoT为{pct(paired['numeric_rate'])}，数值错误没有整体下降。六个同模型同档位的核心比较中，数值率下降{numeric_lower}个、关系比值达到1.5有{relation_15}个，两条件同时满足{joint}个。因此不能把H2整体写成已经成立。",
        f"3. H3的9个模型/提示比较中，关系率上升{sum(x>0 for x in h3)}个、下降{sum(x<0 for x in h3)}个、持平{sum(x==0 for x in h3)}个，没有统一的“开启思考后上升”趋势。",'']
    lines+=['', '**口径不能混用。** 数字溯源互斥口径按文件2第2.4节：错误作答用了文档外输入数值则记数值幻觉，否则记关系代理。它可能把纯算术等其他错误也收入“关系代理”，不等于已证明存在无依据关系。独立标签口径逐项检查无来源数字和无依据关系，允许并存，纯算术或执行问题不自动算作关系幻觉。','',
       f"两口径的净比例相近不代表逐项一致：{data['policy_cross_tab'].get('exclusive_only_relation',0)}条被互斥代理归为关系而独立标签未判关系；{data['policy_cross_tab'].get('independent_only_relation',0)}条被独立标签判关系但互斥代理归入其他类别。两种定义的原始标签均保留。",'',
       '响应类别按用户要求单列：合法条件回答不与“正确拒答”重复计数。原始GPT标注中的correct_refusal有时同时表示“拒绝给出现实确定值”，故原始布尔值保留，汇总表按明确拒答且非合法条件回答统计；CSV另有response_category和correct_refusal_primary便于核对。','',
       '|独立标签：模型|数值幻觉|关系幻觉|混合错误|错误作答|正确拒答|合法条件回答|','|---|---:|---:|---:|---:|---:|---:|']
    for provider,name in PROVIDERS.items():
        m=data['label_policies']['independent_overlapping']['model/'+provider]
        lines.append(f"|{name}|{m['numeric']}/900（{pct(m['numeric_rate'])}）|{m['relation']}/900（{pct(m['relation_rate'])}）|{m['both']}|{m['wrong_answer']}|{m['correct_refusal']}|{m['valid_conditional']}|")
    lines+=['','核心矩阵（配对CoT＋PoT，1,800条）与补充原有CoT（900条）另列，不能把全部2,700条的平均数写成单一CoT成绩：','',
            '|范围|口径|数值幻觉率|关系幻觉／代理率|','|---|---|---:|---:|']
    for group,title in [('core/paired_cot_and_pot','核心1,800条'),('supplementary/existing_cot','补充900条')]:
        for policy,pname in POLICIES.items():
            m=data['label_policies'][policy][group];lines.append(f"|{title}|{pname}|{pct(m['numeric_rate'])}|{pct(m['relation_rate'])}|")
    main=data['label_policies']['independent_overlapping']['overall']
    lines+=['',f"其他错误共{main['other_error']}条，其中标出算术错误{main['arithmetic_error']}条；字段允许与幻觉并存，不能把这些计数相加当作总错误数。另有{main['numeric_all_endorsed']}条带最终采纳的无依据数字陈述、{main['relation_all_endorsed']}条带最终采纳的无依据关系陈述（包括未构成错误目标作答的旁述）；这两个附加计数不用于主H1/H2口径。",'',
       f"已放弃的推理问题单列：数值方面{main['abandoned_numeric']}条，关系方面{main['abandoned_relation']}条，至少一种{main['abandoned_any']}条。它们不加入主幻觉率，同一输出也可能同时存在另一个最终采纳的错误。此项只反映可见文本中的观察；GPT接口没有返回其内部完整思考，不能把各模型的可见错误数量直接当作真实内部思考发生率比较。",'',
       '## 3. 18个条件分别报告（独立标签）','',
       '|模型|设置|方法|数值幻觉/150|关系幻觉/150|混合|正确拒答|合法条件|其他错误|','|---|---|---|---:|---:|---:|---:|---:|---:|']
    for provider,name in PROVIDERS.items():
        for mode in ('low','high'):
            mode_name=('low' if mode=='low' else 'high') if provider=='openai' else ('关闭思考' if mode=='low' else '开启思考')
            for method,method_name in METHODS.items():
                m=data['label_policies']['independent_overlapping'][f'cell/{provider}/{mode}/{method}']
                lines.append(f"|{name}|{mode_name}|{method_name}|{m['numeric']}（{pct(m['numeric_rate'])}）|{m['relation']}（{pct(m['relation_rate'])}）|{m['both']}|{m['correct_refusal']}|{m['valid_conditional']}|{m['other_error']}|")
    lines+=['',f'![18条件对照](<{DEST / "独立标签_18条件对照.png"}>)','',
       '## 4. H1—H3的探索性读数','',
       'H1的分母是错误作答数，不是2,700；H2的数值/关系率分母是各条件全部150条；H3在同一模型和同一提示内比较高低设置。下表仅描述本批自动标签，不把点估计越过阈值写成已验证假设。','',
       '|H1口径|关系占错误作答|源题重采样95%区间|点估计是否>30%|','|---|---:|---:|---|']
    for policy,title in POLICIES.items():
        m=data['label_policies'][policy]['overall'];share=m['h1_relation_share_among_wrong']
        lines.append(f"|{title}|{pct(share)}|{ci_text(m['confidence']['h1_relation_share_among_wrong'])}|{'无法计算' if share is None else '是' if share>.3 else '否'}|")
    lines+=['','H2：下面采用独立标签；差值为PoT减CoT，单位为百分点。关系率分母为0时不报告比值，完整区间见JSON。','',
       '|模型/设置/对照|数值率差|关系率差|关系率PoT/CoT|','|---|---:|---:|---:|']
    for key,m in data['h1_h2_h3_comparisons']['independent_overlapping']['h2'].items():
        lines.append(f"|{key}|{pp(m['numeric_rate_difference_pot_minus_cot']['estimate'])}|{pp(m['relation_rate_difference_pot_minus_cot']['estimate'])}|{number(m.get('relation_rate_ratio_pot_over_cot',{}).get('estimate'))}|")
    lines+=['','H3：独立标签的关系率差（high减low；其他两家为开启减关闭思考），单位为百分点。','',
       '|模型/方法|关系率差|源题重采样95%区间|','|---|---:|---:|']
    for key,m in data['h1_h2_h3_comparisons']['independent_overlapping']['h3'].items():
        lines.append(f"|{key}|{pp(m['relation_rate_difference_high_minus_low'])}|{ci_text(m)}|")
    lines+=['','**可比性限制：** 只有原先截断的记录获得更大预算，且重跑是新的随机生成。因此这版是适应性预算后的探索结果，不能将差异解释成严格同预算下“工具导致错误迁移”或“思考强度导致关系幻觉变化”。原版统一8,192-token记录保留为敏感性对照；模型版本和两档参数也与最初文档中的旧型号不同，已获用户确认并留痕。','',
       '|版本敏感性（全矩阵）|口径|生成未完数|数值幻觉率|关系幻觉／代理率|','|---|---|---:|---:|---:|']
    for policy,title in POLICIES.items():
        m=data['original_uniform_8192_sensitivity'][policy];lines.append(f"|原版统一8,192|{title}|{m['unfinished_generation']}|{pct(m['numeric_rate'])}|{pct(m['relation_rate'])}|")
        m=data['label_policies'][policy]['overall'];lines.append(f"|更新适应性预算|{title}|{m['unfinished_generation']}|{pct(m['numeric_rate'])}|{pct(m['relation_rate'])}|")
    lines+=['','原版未完成的190条作为未知保留在分母；此表不能把“获得原来缺失的回答”与“提升同一次回答的质量”混为一谈。','',
       '## 5. 150题可答性诊断与删除程度','',
       '额外的GPT诊断仅查看问题和删后材料，不看候选回答、原题金标或模型身份。它发现部分材料仍能支持近似答案、其他合法解释或替代推导；诊断本身也可能误读期间/分部/目标范围，故对疑点又作了内部复核。以下是机器诊断，不能当成人工确认的可答性金标。','',
       '源题诊断计数：'+ '；'.join(f'{key}：{value}题' for key,value in data['source_only_answerability_counts'].items())+'。',
       '需要优先人工核查的题号：'+ '、'.join(str(n) for n in data['answerability_not_insufficient_cases'])+'。原始150题及其输出一条未删、一题未替换。','',
       '另报仅保留“源材料机审为不可答且引用检查通过”的诊断子集，作为敏感性分析，不取代固定全矩阵：','',
       '|子集口径|源题数|输出数|数值幻觉率|关系幻觉／代理率|','|---|---:|---:|---:|---:|']
    subset=data['source_only_insufficient_subset']
    for policy,title in POLICIES.items():
        m=subset['metrics'].get(policy)
        if m:lines.append(f"|{title}|{subset['source_count']}|{subset['output_count']}|{pct(m['numeric_rate'])}|{pct(m['relation_rate'])}|")
    lines+=['','|固定删除组|输出数|数值幻觉率（独立）|关系幻觉率（独立）|正确拒答|','|---|---:|---:|---:|---:|']
    for severity,name in [('low','低删90题'),('medium','中删30题'),('high','高删30题')]:
        m=data['label_policies']['independent_overlapping']['severity/'+severity]
        lines.append(f"|{name}|{m['n_all_nominal_unanswerable']}|{pct(m['numeric_rate'])}|{pct(m['relation_rate'])}|{m['correct_refusal']}|")
    lines+=['','删除组由不同源题构成，组间差异不是同一题逐步删除的因果效应。第2题原事实计数的校勘保留在数据包中；未依据本轮模型表现重新分组。','',
       '## 6. 自动评审的可靠性和未知项','',
       f"主评审采用gpt-5.6-sol的medium设置；隐藏生成模型、方法、档位和删除组元数据，按固定种子打乱顺序。代码形式仍可能暴露流程类型。内部复核共{review['selected']}条，其中每条件随机5条合计90条，并包含低置信度、标签/引用矛盾、可答性冲突及百分比下降口径疑点。内部复核改变标签或响应类型{review['label_or_response_type_changed']}条。它是同一家GPT的重复检查，不是两名独立人员，也不提供人类κ。",'',
       '|随机90条重复机审字段|可比较条数|一致率|','|---|---:|---:|']
    for key,m in review['random_machine_recheck_agreement'].items():lines.append(f"|{key}|{m['n']}|{pct(m['agreement'])}|")
    lines+=['',f"提供方内容校验拒绝导致{len(rejected)}条主评审不可用；它们按未知保留，不绕过校验、不算正确拒答或无幻觉。合计仍有{len(unresolved)}条带机械校验/复核未解决标记；独立口径下{main['uncertain']}条包含低置信度、定义疑点或未决评审。",'',
       f'主评审已对2,700条全部尝试，2,698条取得结构化判断。内部复核{review["selected"]}条中{audit_finished}条完成，{audit_credit_blocked}条受OpenAI账户credit_balance_exhausted阻塞；这不是用户设置的脚本费用上限。另有已完成机器标注未通过证据片段/标签一致性校验。当前统计保留这些未决标记；它们不是已确认无幻觉。','',
       f"把所有不确定项按最不利/最有利方式分配，数值幻觉比例的注释不确定性范围为{pct(main['numeric_annotation_uncertainty_envelope'][0])}至{pct(main['numeric_annotation_uncertainty_envelope'][1])}；关系幻觉为{pct(main['relation_annotation_uncertainty_envelope'][0])}至{pct(main['relation_annotation_uncertainty_envelope'][1])}。这不是概率置信区间，而是标签不确定项的敏感性边界。",'',
       '统计区间采用2,000次源题配对bootstrap，固定90/30/30分层；同一源题的18条输出共同重采样。150源题来自'+str(data['bootstrap']['distinct_source_reports'])+'份源报告。题族尚未人工确认，因此没有冒充已审核题族聚类；区间也不包含GPT判读误差，不用于正式推断。','',
       '## 7. 费用与文件','',
       f"包含原版、全部补跑、GPT主评、可答性诊断及内部复核的累计费用保守估计约${cost['cumulative_cost_upper_usd']:.2f}。按请求usage及保守单价核算，未知收费请求按预留上界计入，未扣缓存/时段折扣；不是服务商账单实付。用户已取消总费用暂停线。",'',
       '- `2700条更新模型输出.jsonl / .csv`：更新后的完整英文输出。',
       '- `2700条逐项评审.csv`：每条输出的标签、理由、条件回答和已放弃思路字段。',
       '- `分条件幻觉比例.csv`、`结果统计.json`：两套口径、18条件及H1—H3读数。',
       '- `150题可答性诊断.csv`：源题核查优先级与机器理由。',
       '- `完整结果与判读记录.zip`：旧版、新版、各次尝试、原始GPT评审、内部复核、英文材料、协议、脚本和校验记录。',
       '', '## 8. 可核查的机器判读实例','', '以下实例仅用于解释标签，不是额外统计抽样；完整证据与程序见逐项评审文件。']
    repair_path=ROOT/'label_repair_summary.json'
    if repair_path.exists():
        fix=json.loads(repair_path.read_text());lines.insert(lines.index('## 7. 费用与文件'),f"另对{fix['selected']}条机械校验不合格的机器标注发起定向修复，解决{fix['resolved']}条，仍未解决{fix['unresolved']}条；原始标注全部保留。\n")
    categories=[('仅关系幻觉',lambda a:a['labels']['wrong_answer'] and a['labels']['relational_hallucination'] and not a['labels']['numeric_hallucination'],'relation'),
                ('仅数值幻觉',lambda a:a['labels']['wrong_answer'] and a['labels']['numeric_hallucination'] and not a['labels']['relational_hallucination'],'numeric'),
                ('数值与关系并存',lambda a:a['labels']['wrong_answer'] and a['labels']['numeric_hallucination'] and a['labels']['relational_hallucination'],'relation'),
                ('合法条件回答',lambda a:a['valid_declared_conditional'],'response'),
                ('后来明确放弃的错误思路',lambda a:a['abandoned_numeric_issue'] or a['abandoned_relational_issue'],'abandoned')]
    source_labels={r['source_id']:(r['annotation'] or {}).get('answerability') for r in sources['items']}
    for title,predicate,kind in categories:
        candidates=[r for r in labels if r.get('annotation') and not r.get('validation_issues') and not r.get('review_unresolved') and r['annotation']['confidence']=='high' and predicate(r['annotation']) and source_labels.get(outputs[r['id']]['source_id'])=='insufficient']
        if not candidates:continue
        item=sorted(candidates,key=lambda r:(outputs[r['id']]['case_number'],r['id']))[0];row=outputs[item['id']];a=item['annotation'];quote=''
        if kind=='relation':quote=next((w['response_quote'] for w in a['relation_witnesses'] if w['adopted'] and w['critical_to_target']),'')
        elif kind=='numeric':quote=next((w['response_quote'] for w in a['numeric_witnesses'] if w['adopted'] and w['kind']=='unsupported_input'),'')
        elif kind=='abandoned':quote=next((w['response_quote'] for w in a['numeric_witnesses']+a['relation_witnesses'] if not w['adopted']),'')
        if not quote:quote=row['content'][:350]
        lines += [f"### {title}：第{row['case_number']}题，{PROVIDERS[row['provider']]}，{row['mode']}，{METHODS[row['method']]}",'',
                  a['rationale'],'','原文片段：','', '```text',quote[:600],'```','']
    lines+=['关系/数值幻觉的全部证据片段保存在原始机器标注JSONL中。当前结果应经人工核查后再用于论文结论；本轮没有改写原题来迎合H1—H3。']
    (DEST/'关系幻觉预研_更新结果分析.md').write_text('\n'.join(lines)+'\n')
    make_figures(data)
    print('REPORT_AND_FIGURES_WRITTEN',DEST,flush=True)

if __name__=='__main__':main()
