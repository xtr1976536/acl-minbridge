"""Tests only the actual first-stage FinQA workflow; no hypothetical pipelines."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare,prompts,run,analyze_expanded,judge_expanded,judging_validation

class PhaseOneTests(unittest.TestCase):
    def view(self):return {'question':'What is A?','pre_text':['A is 50.'],'post_text':[],'table':[['item','value'],['A','50']]}
    def annotation(self):return {'response_type':'refusal','labels':{k:False for k in judge_expanded.LABELS},'valid_declared_conditional':False,'abandoned_numeric_issue':False,'abandoned_relational_issue':False,'arithmetic_error':False,'confidence':'high','definition_ambiguous':False,'answerability':'insufficient'}
    def output(self):return {'finish_reason':'stop','content':'ans = None','status':'execution_failed'}
    def item(self,a):return {'annotation':a,'validation_issues':[]}
    def test_exact_deletion(self):
        v=self.view();e={'location':'pre_text/0','start':0,'end':8,'original':'A is 50.','replacement':'','fact_description':'Delete A'}
        result=prepare.apply_edits(v,[e]);self.assertEqual(result['pre_text'],['']);self.assertEqual(result['question'],v['question']);self.assertEqual(v['pre_text'],['A is 50.'])
    def test_question_edit_rejected(self):
        with self.assertRaises(ValueError):prepare.apply_edits(self.view(),[{'location':'question','start':0,'end':1,'original':'W','replacement':'','fact_description':'bad'}])
    def test_drift_rejected(self):
        with self.assertRaises(ValueError):prepare.apply_edits(self.view(),[{'location':'pre_text/0','start':0,'end':8,'original':'A is 51.','replacement':'','fact_description':'bad'}])
    def test_three_prompts(self):
        v=self.view();p=prompts.messages('pot',v);c=prompts.messages('cot_paired_4shot',v);a=prompts.messages('cot_existing_abstention',v)
        self.assertIn('#Python',p[-1]['content']);self.assertIn('Reasoning:',c[-1]['content']);self.assertIn('If the evidence is insufficient',a[-1]['content']);self.assertNotIn('If the evidence is insufficient',c[-1]['content'])
    def test_only_four_finqa_examples(self):self.assertEqual(len(prompts.demo_questions()),4)
    def test_worker_success(self):
        result=run.execute_pot('ans = 12 / 261',20);self.assertEqual(result['status'],'executed');self.assertAlmostEqual(result['value'],12/261)
    def test_worker_explicit_none(self):self.assertEqual(run.execute_pot('ans = None',20)['status'],'execution_failed')
    def test_worker_unsafe_import_rejected(self):self.assertEqual(run.execute_pot('import os\nans = 1',20)['status'],'rejected_or_failed')
    def test_completed_none_can_be_refusal(self):
        a=self.annotation();a['labels']['correct_refusal']=True;r=analyze_expanded.flags(self.output(),self.item(a),'independent_overlapping');self.assertEqual(r['correct_refusal'],1);self.assertEqual(r['relation'],0)
    def test_conditional_is_separate(self):
        a=self.annotation();a.update(response_type='conditional_answer',valid_declared_conditional=True);a['labels'].update(correct_refusal=True,outside_document_input_number=True)
        r=analyze_expanded.flags(self.output(),self.item(a),'numeric_provenance_exclusive');self.assertEqual(r['valid_conditional'],1);self.assertEqual(r['correct_refusal'],0);self.assertEqual(r['numeric'],0)
    def test_independent_mixed(self):
        a=self.annotation();a['response_type']='answer';a['labels'].update(wrong_answer=True,numeric_hallucination=True,relational_hallucination=True,outside_document_input_number=True)
        self.assertEqual(analyze_expanded.flags(self.output(),self.item(a),'independent_overlapping')['both'],1);self.assertEqual(analyze_expanded.flags(self.output(),self.item(a),'numeric_provenance_exclusive')['relation'],0)
    def test_arithmetic_not_automatic_relation(self):
        a=self.annotation();a['response_type']='answer';a['arithmetic_error']=True;a['labels'].update(wrong_answer=True,other_error=True)
        self.assertEqual(analyze_expanded.flags(self.output(),self.item(a),'independent_overlapping')['relation'],0);self.assertEqual(analyze_expanded.flags(self.output(),self.item(a),'numeric_provenance_exclusive')['relation'],1)
    def test_cutoff_kept_unknown(self):
        o=self.output();o['finish_reason']='length';a=self.annotation();a['labels']['correct_refusal']=True;r=analyze_expanded.flags(o,self.item(a),'independent_overlapping');self.assertEqual(r['unfinished_generation'],1);self.assertEqual(r['correct_refusal'],0)
    def test_missing_annotation_not_negative(self):self.assertEqual(analyze_expanded.flags(self.output(),None,'independent_overlapping')['judge_unusable'],1)
    def test_undefined_ratio_not_silently_dropped(self):self.assertIsNone(analyze_expanded.ci([1,float('nan')])['ci95'])
    def test_paired_ratio_values(self):self.assertEqual(analyze_expanded.division([1,2],[1,2]).tolist(),[1,1])

if __name__=='__main__':unittest.main()
