import json,sys,termios,urllib.request,urllib.error
from pathlib import Path
from probe_api_20261116 import NoRedirect
old=termios.tcgetattr(sys.stdin);hidden=list(old);hidden[3]&=~termios.ECHO
termios.tcsetattr(sys.stdin,termios.TCSANOW,hidden)
print('READY_FOR_PRIVATE_STDIN',flush=True)
try:
    key=json.loads(sys.stdin.readline())['qwen']
    payload={'model':'qwen3.8-27b','messages':[{'role':'user','content':'Give a detailed derivation of 1 + 1 under Peano arithmetic. Explain every axiom and each step.'}],
             'enable_thinking':True,'max_completion_tokens':64,'stream':True,'stream_options':{'include_usage':True}}
    req=urllib.request.Request('https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
             data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    result={'test_only_not_benchmark':True,'request':payload,'content':'','reasoning_content':''}
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=60) as response:
            result['http_status']=response.status
            for line in response:
                line=line.decode().strip()
                if not line.startswith('data:'):continue
                line=line[5:].strip()
                if line=='[DONE]':break
                raw=json.loads(line)
                result['usage']=raw.get('usage') or result.get('usage')
                for c in raw.get('choices',[]):
                    result['content']+=c.get('delta',{}).get('content') or ''
                    result['reasoning_content']+=c.get('delta',{}).get('reasoning_content') or ''
                    result['finish_reason']=c.get('finish_reason') or result.get('finish_reason')
    except urllib.error.HTTPError as exc:
        result.update(http_status=exc.code,error=exc.read().decode().replace(key,'[REDACTED]'))
    path=Path(__file__).parent/'local/api_probe_20261116/qwen_total_budget_probe.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('content','reasoning_content','request')}),flush=True)
finally:termios.tcsetattr(sys.stdin,termios.TCSANOW,old)
