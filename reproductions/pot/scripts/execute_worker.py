import json,sys
sys.dont_write_bytecode=True
from protocol import VENDOR,guard
sys.path.insert(0,str(VENDOR))
from tool import safe_execute,floatify_ans
r=json.load(sys.stdin);code=r['code']
try:
 raw_code=code
 code=code.lstrip()  # Chat boundary whitespace only; preserve internal indentation.
 if r['task']!='finqa':raise ValueError('Only FinQA is part of this experiment')
 code=code.replace('&','_')
 guard(code)
 ans=floatify_ans(safe_execute(code))
 print(json.dumps({'value':ans,'status':'executed' if ans is not None else 'execution_failed','executed_code':code,'leading_whitespace_removed':raw_code!=raw_code.lstrip()},default=str))
except Exception as e:print(json.dumps({'value':None,'status':'rejected_or_failed','error':type(e).__name__+': '+str(e)}))
