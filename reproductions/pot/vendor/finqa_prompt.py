"""FinQA prompt/builder excerpt from Program-of-Thoughts (MIT); see LICENSE."""
from typing import Dict,Any

def create_reader_request_processed(example: Dict[str, Any]):
    prompt = 'Read the following text and table, and then write code to answer a question:\n'
    if example['text']:
        prompt += example['text'] + '\n'
    prompt += example['table'].strip() + '\n'
    prompt += 'Question: {}\n'.format(example['question'])
    prompt += '#Python\n'
    return prompt

prompt_4shot = """Read the following text and table, and then write code to answer a question:
( in millions ) | dec 282013 | dec 292012
available-for-sale investments | $ 18086 | $ 14001
cash | 854 | 593
equity method investments | 1038 | 992
loans receivable | 1072 | 979
non-marketable cost method investments | 1270 | 1202
reverse repurchase agreements | 800 | 2850
trading assets | 8441 | 5685
total cash and investments | $ 31561 | $ 26302
Question: what percentage of total cash and investments as of dec . 29 2012 was comprised of available-for-sale investments?
#Python
available_for_sale_investments_dec_29_2012 = 14001
total_cash_and_investments_dec_29_2012 = 26302
percent_available_for_sale_investments_dec_29_2012 = available_for_sale_investments_dec_29_2012 / total_cash_and_investments_dec_29_2012
ans = percent_available_for_sale_investments_dec_29_2012


Read the following text and table, and then write code to answer a question:
the chart shows that the firm posted market risk 2013related gains on 248 out of 261 days in this period , with 12 days exceeding $ 210 million .
december 31 ( in millions ) | 1 basis point increase in jpmorgan chase 2019s credit spread
2010 | $ 35
2009 | $ 39
Question: on what percent of trading days were there market gains above $ 210 million?
#Python
days_with_market_gains_above_210_million = 12
total_trading_days = 261
percent_days_with_market_gains_above_210_million = days_with_market_gains_above_210_million / total_trading_days
ans = percent_days_with_market_gains_above_210_million


Read the following text and table, and then write code to answer a question:
american tower corporation and subsidiaries notes to consolidated financial statements ( 3 ) consists of customer-related intangibles of approximately $ 75.0 million and network location intangibles of approximately $ 72.7 million . the customer-related intangibles and network location intangibles are being amortized on a straight-line basis over periods of up to 20 years .
- | preliminary purchase price allocation
current assets | $ 8763
non-current assets | 2332
property and equipment | 26711
intangible assets ( 1 ) | 21079
other non-current liabilities | -1349 ( 1349 )
fair value of net assets acquired | $ 57536
goodwill ( 2 ) | 5998
Question: for acquired customer-related and network location intangibles , what is the expected annual amortization expenses , in millions?
#Python
customer_related_intangibles = 75
network_location_intangibles = 72.7
straight_line_basis = 20
amortization_expenses = ( customer_related_intangibles + network_location_intangibles ) / straight_line_basis
ans = amortization_expenses


Read the following text and table, and then write code to answer a question:
the aggregate commitment under the liquidity asset purchase agreements was approximately $ 23.59 billion and $ 28.37 billion at december 31 , 2008 and 2007 , respectively .
( dollars in billions ) | 2008 amount | 2008 percent of total conduit assets | 2008 amount | percent of total conduit assets
united states | $ 11.09 | 46% ( 46 % ) | $ 12.14 | 42% ( 42 % )
australia | 4.30 | 17 | 6.10 | 21
great britain | 1.97 | 8 | 2.93 | 10
spain | 1.71 | 7 | 1.90 | 7
italy | 1.66 | 7 | 1.86 | 7
portugal | 0.62 | 3 | 0.70 | 2
germany | 0.57 | 3 | 0.70 | 2
netherlands | 0.40 | 2 | 0.55 | 2
belgium | 0.29 | 1 | 0.31 | 1
greece | 0.27 | 1 | 0.31 | 1
other | 1.01 | 5 | 1.26 | 5
total conduit assets | $ 23.89 | 100% ( 100 % ) | $ 28.76 | 100% ( 100 % )
Question: what is percentage change in total conduit asset from 2007 to 2008?
#Python
total_conduit_assets_2007 = 28.76
total_conduit_assets_2008 = 23.89
net_change_in_total_conduit_assets = total_conduit_assets_2008 - total_conduit_assets_2007
percent_change_in_total_conduit_assets = net_change_in_total_conduit_assets / total_conduit_assets_2007
ans = percent_change_in_total_conduit_assets
"""
