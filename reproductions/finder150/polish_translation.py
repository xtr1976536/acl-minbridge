# -*- coding: utf-8 -*-
"""Improve common finance translations without changing source numeric spans."""
import json,re
from pathlib import Path
P=Path(__file__).resolve().parents[2]/'data/finder150/local'

PHRASES={
 'STATEMENT OF EARNINGS (LOSS)':'合并损益表',
 'Consolidated Statements of Earnings':'合并损益表',
 'Consolidated Statements of Income':'合并利润表',
 'Consolidated Statements of Operations':'合并经营报表',
 'CONSOLIDATED STATEMENTS OF EARNINGS':'合并损益表',
 'CONSOLIDATED STATEMENTS OF INCOME':'合并利润表',
 'CONSOLIDATED STATEMENTS OF OPERATIONS':'合并经营报表',
 'Property revenues':'物业收入','Property operating and maintenance':'物业运营及维护费用',
 'Real estate taxes':'房地产税','Total property expenses':'物业费用合计',
 'Fee and asset management':'收费及资产管理收入','Interest and other income':'利息及其他收入',
 'Depreciation and amortization':'折旧及摊销','General and administrative':'一般及管理费用',
 'Interest':'利息','Property management':'物业管理费用','Total other expenses':'其他费用合计',
 'Equity in income of joint ventures':'合营企业投资收益',
 'Net income attributable to common shareholders':'归属普通股股东的净利润',
 'Income from continuing operations before income taxes':'持续经营税前利润',
 'Sales of equipment':'设备销售收入','Sales of services':'服务销售收入',
 'Insurance revenues':'保险收入','Total revenues':'收入合计','Cost of equipment sold':'设备销售成本',
 'Cost of services sold':'服务销售成本','Selling, general and administrative expenses':'销售、一般及管理费用',
 'Separation costs':'分拆费用','Research and development':'研发费用',
 'Interest and other financial charges':'利息及其他财务费用','Debt extinguishment costs':'债务清偿费用',
 'Insurance losses, annuity benefits and other costs':'保险损失、年金给付及其他成本',
 'Non-operating benefit cost (income)':'非经营性福利成本（收益）',
 'Total costs and expenses':'成本及费用合计','Other income (loss)':'其他收益（损失）',
 'Earnings (loss) from continuing operations before income taxes':'持续经营税前收益（亏损）',
 'Benefit (provision) for income taxes':'所得税收益（拨备）',
 'Earnings (loss) from continuing operations':'持续经营收益（亏损）',
 'Earnings (loss) from discontinued operations, net of taxes':'终止经营收益（亏损），税后',
 'Net earnings (loss)':'净收益（亏损）',
 'Less net earnings (loss) attributable to noncontrolling interests':'减：归属非控股权益的净收益（亏损）',
 'Net earnings (loss) attributable to the Company':'归属本公司的净收益（亏损）',
 'Preferred stock dividends and other':'优先股股利及其他',
 'Net earnings (loss) attributable to GE common shareholders':'归属通用电气普通股股东的净收益（亏损）',
 'Amounts attributable to GE common shareholders':'归属通用电气普通股股东的金额',
 'Diluted earnings (loss) per share':'稀释每股收益（亏损）',
 'Basic earnings (loss) per share':'基本每股收益（亏损）',
 'to GE common shareholders':'归属通用电气普通股股东',
 'Income tax expense':'所得税费用','Net income':'净利润',
 'Income before income taxes':'税前利润','Net sales':'净销售额','Gross profit':'毛利润',
 'Cost of sales':'销售成本','Interest expense':'利息费用','Interest income':'利息收入',
 'Operating income':'营业利润','Operating profit':'营业利润',
 'Basic':'基本','Diluted':'稀释','Common shares':'普通股股数',
 'Weighted average diluted shares outstanding':'稀释加权平均流通股数',
 'Weighted average basic shares outstanding':'基本加权平均流通股数',
 'For the years ended December':'截至各年度末（12月）',
 'Year Ended December':'截至年度末（12月）',
 'in millions; per-share amounts in dollars':'单位：百万美元；每股数据为美元',
 'in millions, except per share amounts':'单位：百万美元，每股数据除外',
 'in thousands, except per share amounts':'单位：千美元，每股数据除外',
 'Net income attributable to UHS':'归属UHS的净利润',
 'Total Noninterest Expense':'非利息费用合计',
 'Net Interest Income after Provision for Credit Losses':'计提信贷损失准备后的净利息收入',
 'Total Noninterest Income':'非利息收入合计',
}

def clean(s):
    s=s.strip()
    if re.fullmatch(r'[调\s]+',s):return ''
    for a,b in [('无控制利息','非控股权益'),('非控制利益','非控股权益'),('共同股东','普通股股东'),('共同份额','普通股'),('每分享额','每股金额'),('每分享数据','每股数据'),('研究(损失)说明(损失)','合并损益表'),('折旧和摊分','折旧及摊销'),('离职费用','分拆费用'),('停止行动','终止经营'),('持续 EPS','持续经营EPS'),('被稀释的净 EPS','稀释净EPS'),('市场制造','做市业务')]:s=s.replace(a,b)
    s=re.sub(r'([^\d]{2,12})\1{1,}',r'\1',s)
    return s

def main():
    p=P/'translations_zh.json';d=json.loads(p.read_text());edits=0
    for rec in d['records'].values():
      collections=[rec['question_parts']]
      collections += [chunk['parts'] for ref in rec['reference_chunks'] for chunk in ref]
      collections += list(rec['deleted_labels'].values())
      for parts in collections:
       for part in parts:
        if part['kind']=='text':
          t=clean(part.get('text',''))
          if t!=part.get('text',''):edits+=1;part['text']=t
    d['financial_terminology_polish_edits']=edits
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print('terminology/duplicate edits',edits)

if __name__=='__main__':main()
