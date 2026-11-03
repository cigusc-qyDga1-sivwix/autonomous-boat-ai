"""Small, idempotent updater for the original portable bundle. No network."""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile

OLD_SHA='63f9042931a41cbf3b40cd27d846dd14e70c53f7d000e6bd92ac1bdc006b1590'
FIX_COMMIT='083fa64997a024984f34b2b2b9bc837e56cc63ae'

def make_script(source,old_sha=OLD_SHA):
    encoded=base64.b64encode(source).decode('ascii')
    new_sha=hashlib.sha256(source).hexdigest()
    return f'''import base64,hashlib,json,sys
from pathlib import Path
root=Path.cwd()
target=root/'vision_ai/windows_runner.py'
manifest=root/'BUILD_MANIFEST.json'
source=base64.b64decode({encoded!r})
new_sha={new_sha!r}
if hashlib.sha256(source).hexdigest()!=new_sha:
    raise SystemExit('PATCH_PAYLOAD_HASH_MISMATCH')
if not target.is_file() or not manifest.is_file():
    raise SystemExit('WRONG_FOLDER: put FIX_PLAYER_WAIT.cmd next to START_CAPTURE.cmd.')
previous=target.read_bytes()
previous_sha=hashlib.sha256(previous).hexdigest()
if previous_sha==new_sha:
    print('ALREADY_FIXED: run START_CAPTURE.cmd. Real capture is still unverified.')
    raise SystemExit(0)
if previous_sha!={old_sha!r}:
    raise SystemExit('VERSION_MISMATCH: no files changed. Please report this message.')
metadata=json.loads(manifest.read_text(encoding='utf-8'))
compile(source,str(target),'exec')
metadata.setdefault('application_files',{{}})['vision_ai/windows_runner.py']=new_sha
metadata.setdefault('applied_patches',[]).append({{'patch':'visible-player-wait-v2','source_commit':{FIX_COMMIT!r},'previous_sha256':previous_sha,'new_sha256':new_sha}})
backup=target.with_name('windows_runner.py.before-player-fix')
if not backup.exists():
    backup.write_bytes(previous)
temporary=target.with_suffix('.fix.tmp')
temporary.write_bytes(source)
temporary.replace(target)
mt=manifest.with_suffix('.fix.tmp')
mt.write_text(json.dumps(metadata,indent=2)+'\\n',encoding='utf-8')
mt.replace(manifest)
print('FIX_APPLIED: player initialization now waits; config.json and outbox were preserved.')
print('Next: run START_CAPTURE.cmd. This is not proof of successful video capture.')
'''

def build(output):
    source=Path(__file__).resolve().parents[1].joinpath('windows_runner.py').read_bytes()
    payload=base64.b64encode(make_script(source).encode('utf-8')).decode('ascii')
    lines=['@echo off','setlocal','cd /d "%~dp0"','echo BOAT VISION - player initialization fix',
           'if not exist "runtime\\python.exe" (','echo WRONG FOLDER: place this file next to START_CAPTURE.cmd.',
           'if not defined BOAT_VISION_FIX_NOPAUSE pause','exit /b 2',')',
           '"%~dp0runtime\\python.exe" -c "import base64,pathlib,sys;exec(base64.b64decode(pathlib.Path(sys.argv[1]).read_bytes().split(b\'::PAYLOAD\'+bytes([13,10]),1)[1]))" "%~f0"',
           'set "fix_exit=%ERRORLEVEL%"','echo Fix exit code: %fix_exit%',
           'if not defined BOAT_VISION_FIX_NOPAUSE pause','exit /b %fix_exit%','::PAYLOAD',payload]
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(('\r\n'.join(lines)+'\r\n').encode('ascii'))
    print('Created '+str(output))
    return output

def self_test():
    old=b'# old runner fixture\n'
    new=b'# new runner fixture\n'
    script=make_script(new,hashlib.sha256(old).hexdigest())
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        (root/'vision_ai').mkdir()
        target=root/'vision_ai/windows_runner.py'
        target.write_bytes(old)
        (root/'BUILD_MANIFEST.json').write_text('{}')
        (root/'config.json').write_text('KEEP_CONFIG')
        (root/'outbox').mkdir()
        (root/'outbox/existing.json').write_text('KEEP_RESULTS')
        for _ in range(2):
            result=subprocess.run([sys.executable,'-c',script],cwd=root,capture_output=True,text=True)
            assert result.returncode==0,result.stderr
        assert target.read_bytes()==new
        assert target.with_name('windows_runner.py.before-player-fix').read_bytes()==old
        assert (root/'config.json').read_text()=='KEEP_CONFIG'
        assert (root/'outbox/existing.json').read_text()=='KEEP_RESULTS'
        metadata=json.loads((root/'BUILD_MANIFEST.json').read_text())
        assert len(metadata['applied_patches'])==1
        assert metadata['application_files']['vision_ai/windows_runner.py']==hashlib.sha256(new).hexdigest()
        target.write_text('unknown version')
        result=subprocess.run([sys.executable,'-c',script],cwd=root,capture_output=True,text=True)
        assert result.returncode!=0
        assert target.read_text()=='unknown version'
    print('PASS: patch application, idempotence, backup, preservation and mismatch refusal.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    self_test()
    path=build(args.output)
    with zipfile.ZipFile(path.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        z.write(path,path.name)
