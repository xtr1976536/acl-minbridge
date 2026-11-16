"""Extract official prompts/builders without executing argparse, API code or main loops."""
import ast,hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];VENDOR=ROOT/'vendor'
def official(task):
 if task!='finqa':raise ValueError('This release contains only the FinQA first-stage experiment')
 source=(VENDOR/'finqa_prompt.py').read_text();tree=ast.parse(source)
 selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.Assign))]
 namespace={'Dict':dict,'Any':object}
 exec(compile(ast.Module(body=selected,type_ignores=[]),'finqa_prompt.py','exec'),namespace)
 return namespace['prompt_4shot'],namespace['create_reader_request_processed'],[],{'source':'PoT FinQA prompt-only excerpt','script_sha256':hashlib.sha256(source.encode()).hexdigest(),'count':0,'max_tokens':512,'temperature':0.0,'top_p':1,'stop':['\n\n'],'n':1}
def guard(code):
 """Reject obvious filesystem/network/dynamic-code access before official execution.
 This is a compatibility guard, not a hostile-code security boundary.
 """
 tree=ast.parse(code)
 forbidden={'open','exec','eval','compile','__import__','globals','locals','getattr','setattr','delattr','input','breakpoint','exit','quit'}
 for n in ast.walk(tree):
  if isinstance(n,ast.Name) and (n.id in forbidden or n.id.startswith('__')):raise ValueError('Blocked name '+n.id)
  if isinstance(n,ast.Attribute) and (n.attr.startswith('_') or n.attr in ['system','popen','load','save','tofile','fromfile','memmap','read','write']):raise ValueError('Blocked attribute '+n.attr)
  if isinstance(n,(ast.Import,ast.ImportFrom)):
   names=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module or '']
   if any(s.split('.')[0] not in {'math','sympy','statistics','numpy'} for s in names):raise ValueError('Blocked import')
 return code
