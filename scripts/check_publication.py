"""Read-only secret/privacy/full-proposal scan, including compressed records/PDFs."""
import argparse,gzip,hashlib,json,re,subprocess
from pathlib import Path

PATTERNS={
 'model_api_key':re.compile(r'(?<![A-Za-z0-9])sk-(?:proj-|ws[.-])?[A-Za-z0-9_.-]{20,}'),
 'github_token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})'),
 'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
 'aws_access_key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
 'local_personal_path':re.compile(r'/Users/|/home/(?!runner\b)[A-Za-z0-9_-]+/|wxid_[A-Za-z0-9_]+|xwechat_files'),
}
DENIED_NAMES=('definition_sources','user_confirmed_analysis_policy','protocol.pending','实验方案','研究计划书','完整实验计划')
ALLOWED_PDFS={'reports/MinBridge_关系幻觉预研_中文汇报.pdf','reports/figures/两种口径_模型汇总.pdf','reports/figures/独立标签_18条件对照.pdf'}
def scan(root,tracked=False):
    if tracked:
        names=subprocess.check_output(['git','-C',str(root),'ls-files','-z']).decode().split('\0');files=[root/n for n in names if n]
    else:files=[p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts]
    findings=[];decoded_files=0;pdfs=0
    for p in files:
        name=p.relative_to(root).as_posix()
        if p.is_symlink():findings.append({'file':name,'rule':'symlink'});continue
        if p.suffix in ('.docx','.doc','.rtf','.pem','.key','.p12','.pfx','.zip') or p.name=='.env' or p.name.startswith('.env.'):
            findings.append({'file':name,'rule':'forbidden_file_type'})
        if any(term in p.name for term in DENIED_NAMES):findings.append({'file':name,'rule':'private_plan_or_internal_file'})
        data=p.read_bytes()
        if p.suffix=='.gz':data=gzip.decompress(data);decoded_files+=1
        if p.suffix=='.pdf':
            if name not in ALLOWED_PDFS:findings.append({'file':name,'rule':'unapproved_pdf'})
            from pypdf import PdfReader
            r=PdfReader(p);content='\n'.join(page.extract_text() or '' for page in r.pages)+'\n'+str(r.metadata);pdfs+=1
        elif p.suffix in ('.png','.jpg','.jpeg'):continue
        else:
            try:content=data.decode('utf-8-sig')
            except UnicodeDecodeError:findings.append({'file':name,'rule':'unreviewed_binary'});continue
        # This scanner necessarily contains the pattern spelling, not secrets.
        if name=='scripts/check_publication.py':continue
        for rule,pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                findings.append({'file':name,'rule':rule,'line':content.count('\n',0,match.start())+1})
                if len(findings)>1000:break
        if p.stat().st_size>=100*1024*1024:findings.append({'file':name,'rule':'github_file_size_limit'})
    return {'passed':not findings,'files_scanned':len(files),'compressed_files_decoded':decoded_files,'pdfs_text_checked':pdfs,
            'findings':findings,'sensitive_values_printed':False,'network_requests':0}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--tracked',action='store_true');parser.add_argument('--report',type=Path);args=parser.parse_args()
    report=scan(args.root.resolve(),args.tracked)
    if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(0 if report['passed'] else 1)
