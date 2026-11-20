"""Regression checks for failures that could invalidate deletion cases."""
import json,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P))
from build_finder import numeric_spans,inventory,dec,rounded_eps_edges,recover
from replay import load

class ConstructionChecks(unittest.TestCase):
    def test_year_like_headcount_not_lost(self):
        ns=list(numeric_spans('International\n2,100\t1,700\t3,800'))
        self.assertEqual([int(dec(n['value'])) for n in ns],[2100,1700,3800])
    def test_calendar_dates_excluded_in_both_orders(self):
        self.assertEqual(list(numeric_spans('Fiscal Year Ended 30 September 2024')),[])
        self.assertEqual(list(numeric_spans('Jan 28, 2024')),[])
    def test_parenthesized_expense_not_footnote(self):
        ns=list(numeric_spans('Interest expense\t(30.7)\t(64.4)'))
        self.assertEqual([dec(n['value']) for n in ns],[dec('-30.7'),dec('-64.4')])
    def test_attached_footnote_and_filing_index_excluded(self):
        self.assertEqual(list(numeric_spans('Revenue(1) EEO-1 report')),[])
    def test_eps_rounding_recovery_is_screened(self):
        fs=[{'value':'4.23','metric_or_context':'Basic EPS per share'},
            {'value':'906','metric_or_context':'Net income'},
            {'value':'214.2','metric_or_context':'Weighted average basic shares'}]
        edges=rounded_eps_edges(fs)
        self.assertIn(dec('4.23'),recover({dec('906'),dec('214.2')},edges))
    def test_equal_values_in_different_metrics_not_merged(self):
        v={'question':'Ratio?','references':['2024\t2023\nRevenue\t10\t12\nExpense\t10\t8']}
        fs=inventory(v)
        self.assertEqual(sum(dec(f['value'])==10 for f in fs),2)
    def test_final_visible_export_has_no_private_fields(self):
        d=load('model_inputs_150.json')
        self.assertEqual(len(d['drafts']),150)
        for r in d['drafts']:self.assertEqual(set(r['visible']),{'question','pre_text','table','post_text'})
    def test_no_known_bad_source_in_final(self):
        d=load('final_150_review.json.gz')
        self.assertTrue({42,560,1064,1316,2458,5450}.isdisjoint({r['source_index'] for r in d['records']}))
    def test_all_signoffs_are_machine_not_human(self):
        d=load('final_150_review.json.gz')
        self.assertEqual(d['human_reviews_completed'],0)
        self.assertTrue(all(not r['human_reviews'] and r['round1'] and r['round2'] for r in d['records']))

if __name__=='__main__':unittest.main()
