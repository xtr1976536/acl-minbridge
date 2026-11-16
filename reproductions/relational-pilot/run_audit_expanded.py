"""Execute internal rechecks after the main blinded assessment is complete."""
import argparse,hashlib,json,threading
from expanded_engine_evaluation import ROOT,HERE,Engine,credentials,freeze
from audit_expanded import build,finalize

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--build-only',action='store_true');parser.add_argument('--finalize-only',action='store_true');args=parser.parse_args()
    if args.finalize_only:finalize()
    else:
        jobs=build()
        if args.build_only:print('AUDIT_JOBS_READY',len(jobs))
        else:
            freeze(ROOT/'audit_runtime.json',{'engine_sha256':hashlib.sha256((HERE/'expanded_engine_evaluation.py').read_bytes()).hexdigest(),
                  'audit_script_sha256':hashlib.sha256((HERE/'audit_expanded.py').read_bytes()).hexdigest(),
                  'note':'API policy/content rejections are retained as unknown, not retried to bypass controls.'})
            engine=Engine('audit',credentials());engine.semaphores['openai']=threading.Semaphore(12)
            engine.run(jobs,workers=12,max_attempts=3);finalize()
