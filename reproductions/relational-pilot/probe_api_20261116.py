"""Credential-free source: accept keys over non-echoed terminal stdin only."""
import concurrent.futures
import json
import pathlib
import sys
import termios
import time
import urllib.error
import urllib.request

OUT = pathlib.Path(__file__).parent / 'local' / 'api_probe_20261116'
PROVIDERS = {
    'openai': ('https://api.openai.com/v1', 'gpt-5.6-sol'),
    'deepseek': ('https://api.deepseek.com', 'deepseek-v4-pro'),
    'qwen': ('https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen3.8-27b'),
}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def main():
    old = termios.tcgetattr(sys.stdin)
    hidden = list(old)
    hidden[3] &= ~termios.ECHO
    termios.tcsetattr(sys.stdin, termios.TCSANOW, hidden)
    print('READY_FOR_PRIVATE_STDIN', flush=True)
    try:
        keys = json.loads(sys.stdin.readline())
        OUT.mkdir(parents=True, exist_ok=True)
        def clean(value):
            s = str(value)
            for key in keys.values():
                s = s.replace(key, '[REDACTED]')
            return s
        def probe(family):
            base, model = PROVIDERS[family]
            opener = urllib.request.build_opener(NoRedirect)
            report = {'provider': family, 'model_requested': model, 'base_url': base,
                      'test_only_not_benchmark': True, 'checks': []}
            def send(label, path, payload=None):
                start = time.monotonic()
                req = urllib.request.Request(base + path,
                    data=None if payload is None else json.dumps(payload).encode(),
                    headers={'Authorization': 'Bearer ' + keys[family], 'Content-Type': 'application/json'})
                result = {'label': label}
                try:
                    with opener.open(req, timeout=120) as response:
                        result['http_status'] = response.status
                        if payload is None:
                            raw = json.load(response)
                            ids = [x.get('id') for x in raw.get('data', [])]
                            result.update(model_list_count=len(ids), requested_model_listed=model in ids)
                        else:
                            content, reasoning, returned, finish, usage = '', '', None, None, None
                            for line in response:
                                line = line.decode('utf-8').strip()
                                if not line.startswith('data:'): continue
                                value = line[5:].strip()
                                if value == '[DONE]': break
                                raw = json.loads(value)
                                if raw.get('error'): raise ValueError(clean(raw['error']))
                                returned = raw.get('model', returned)
                                usage = raw.get('usage') or usage
                                for choice in raw.get('choices', []):
                                    delta = choice.get('delta', {})
                                    content += delta.get('content') or ''
                                    reasoning += delta.get('reasoning_content') or ''
                                    finish = choice.get('finish_reason') or finish
                            result.update(returned_model=returned, finish_reason=finish, content=content,
                                          reasoning_characters=len(reasoning), usage=usage)
                except urllib.error.HTTPError as exc:
                    result.update(http_status=exc.code, error=clean(exc.read().decode('utf-8', 'replace'))[:1600])
                except Exception as exc:
                    result.update(error_type=type(exc).__name__, error=clean(exc)[:1000])
                result['seconds'] = round(time.monotonic()-start, 2)
                report['checks'].append(result)
                print(json.dumps({'provider':family, **result}), flush=True)
                return result
            listing = send('model_access', '/models')
            if listing.get('http_status') in (401, 403):
                return report
            for mode in ('low', 'high'):
                payload = {'model':model, 'messages':[{'role':'user','content':'What is 1 + 1? Reply with the number only.'}],
                           'stream':True, 'stream_options':{'include_usage':True}}
                if family == 'openai': payload.update(max_completion_tokens=512, reasoning_effort='none' if mode=='low' else 'high', store=False)
                elif family == 'deepseek':
                    payload.update(max_tokens=512, thinking={'type':'disabled' if mode=='low' else 'enabled'})
                    if mode=='high': payload['reasoning_effort']='high'
                else: payload.update(max_tokens=512, enable_thinking=mode=='high')
                result=send(mode, '/chat/completions', payload)
                if result.get('http_status') in (401,403,402,404,429): break
            return report
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            reports=list(pool.map(probe,PROVIDERS))
        (OUT/'probe_results.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2))
        print('PROBE_COMPLETE',flush=True)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSANOW, old)

if __name__ == '__main__': main()
