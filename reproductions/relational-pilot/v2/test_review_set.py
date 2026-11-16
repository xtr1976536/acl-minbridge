import json,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from build_set import financial_numbers,inventory


class ReviewSetTests(unittest.TestCase):
    def test_year_like_rig_count_is_not_a_date(self):
        n=financial_numbers('2017 compared to 2016 overall the rig count was 2030 in 2017, an increase of 27%.')
        self.assertEqual([int(v['value']) for v in n],[2030,27])

    def test_footnote_and_expiration_year_are_not_facts(self):
        self.assertEqual(financial_numbers('1 leases expire on varying dates through 2109.'),[])
        self.assertEqual(financial_numbers('32 | bhge 2018 form 10-k.'),[])

    def test_opening_balance_folded_into_header_is_counted(self):
        v={'question':'What changed?','pre_text':[],'post_text':[],
           'table':[['Shares','Units'],['December 31, 2012','1,119'],['Granted','926'],['December 31, 2013','1,647']]}
        f=inventory(v,header_rows=2)
        self.assertEqual(len(f),3)
        self.assertIn('1119',[x['value'] for x in f])

    def test_flattened_table_echo_is_deduplicated(self):
        v={'question':'What share is owned?','pre_text':['31.5 19.2 50.7 leased facilities2.'],'post_text':[],
           'table':[['Area','US','Other','Total'],['Owned facilities','31.5','19.2','50.7']]}
        f=inventory(v)
        self.assertEqual(len(f),3)
        self.assertTrue(all(len(x['locations'])==2 for x in f))

    def test_final_intel_duplicates_are_removed(self):
        d=json.loads((HERE/'final_150_review.json').read_text())['records'][9]
        self.assertEqual(d['original_fact_count'],9)
        self.assertIn('[not disclosed]',d['modified']['pre_text'][128])
        self.assertNotIn('2.5',d['modified']['pre_text'][128])
        self.assertNotIn('9.6',d['modified']['pre_text'][128])

    def test_final_rig_count_text_cannot_restore_table(self):
        d=json.loads((HERE/'final_150_review.json').read_text())['records'][59]
        self.assertNotIn('2030',d['modified']['post_text'][6])
        self.assertNotIn('69%',d['modified']['post_text'][7])

    def test_final_all_150_have_two_ai_not_human_signoffs(self):
        d=json.loads((HERE/'final_150_review.json').read_text())
        self.assertEqual(len(d['records']),150)
        self.assertEqual(d['groups'],{'low':90,'medium':30,'high':30})
        self.assertTrue(all(x['round1'] and x['round2'] and not x['human_reviews'] for x in d['records']))


if __name__=='__main__':unittest.main()
