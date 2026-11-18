"""FinQA PoT execution helper used by the actual first-stage run."""
import json,os,subprocess,sys
from prepare import ROOT

def execute_pot(code, timeout):
    worker=ROOT/'reproductions/pot/scripts/execute_worker.py'
    try:
        child=subprocess.run([sys.executable,str(worker)],input=json.dumps({'task':'finqa','code':code}),text=True,capture_output=True,cwd='/tmp',timeout=timeout,
            env={'PATH':os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1'})
        if child.returncode:return {'status':'worker_error','returncode':child.returncode}
        return json.loads(child.stdout.strip())
    except subprocess.TimeoutExpired:return {'status':'worker_timeout'}
    except (ValueError,OSError):return {'status':'worker_error'}
