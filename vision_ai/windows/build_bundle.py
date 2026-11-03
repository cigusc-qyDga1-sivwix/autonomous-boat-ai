"""Build a portable x64 bundle. Never runs a real replay or writes production."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile

RUNTIME_URL='https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
RUNTIME_SHA='4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def extract(archive,target):
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            path=Path(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('unsafe_archive_path')
        z.extractall(target)

def build(runtime,wheels,output):
    source=Path(__file__).resolve().parents[1]
    if sha(runtime)!=RUNTIME_SHA:
        raise ValueError('official_python_archive_hash_mismatch')
    files=sorted(wheels.glob('*.whl'))
    if len(files)!=6:
        raise ValueError('exactly_six_locked_windows_wheels_required')
    root=output/'BOAT_VISION_WINDOWS'
    if root.exists():
        raise ValueError('bundle_destination_already_exists')
    root.mkdir(parents=True)
    runtime_dir=root/'runtime'
    extract(runtime,runtime_dir)
    packages=runtime_dir/'Lib'/'site-packages'
    for wheel in files:
        extract(wheel,packages)
    (runtime_dir/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n..\nimport site\n',encoding='ascii')
    shutil.copytree(source,root/'vision_ai',ignore=shutil.ignore_patterns('__pycache__','*.pyc','windows','tests','cv_tests'))
    shutil.copyfile(source/'windows/config.json',root/'config.json')
    shutil.copyfile(source/'windows/README_WINDOWS.md',root/'README_WINDOWS.md')
    for name,option in [('CHECK_RUNTIME','--check-runtime'),('START_CAPTURE','--config config.json --output outbox'),('START_WATCH','--config config.json --output outbox --watch')]:
        content='@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\n"%~dp0runtime\\python.exe" -m vision_ai.windows_runner '+option+'\r\nset "runner_exit=%ERRORLEVEL%"\r\necho.\r\necho Runner exit code: %runner_exit%\r\necho Numerical results, if any, are in outbox.\r\npause\r\nexit /b %runner_exit%\r\n'
        (root/(name+'.cmd')).write_bytes(content.encode('ascii'))
    (root/'outbox').mkdir()
    manifest={'schema':'boatlabs.vision_ai.windows_bundle.v1','python':'3.12.10','architecture':'Windows x64',
              'python_source_url':RUNTIME_URL,'python_archive_sha256':sha(runtime),
              'wheels':[{'name':p.name,'sha256':sha(p),'origin':'https://pypi.org/'} for p in files],
              'verification':{'windows_runtime_executed':False,'real_replay_verified':False},
              'application_files':{str(p.relative_to(root)).replace('\\','/'):sha(p) for p in sorted(root.rglob('*')) if p.is_file() and 'runtime' not in p.relative_to(root).parts}}
    (root/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    destination=output/'BOAT_VISION_WINDOWS.zip'
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file():
                z.write(p,p.relative_to(output))
    print(json.dumps({'bundle':str(destination.resolve()),'bytes':destination.stat().st_size,'sha256':sha(destination)}))
    return destination

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path)
    parser.add_argument('--wheels',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--download',action='store_true')
    args=parser.parse_args()
    if args.download:
        cache=args.output/'downloads'
        cache.mkdir(parents=True,exist_ok=True)
        args.runtime=cache/'python-3.12.10-embed-amd64.zip'
        with urllib.request.urlopen(RUNTIME_URL,timeout=60) as response:
            args.runtime.write_bytes(response.read(20_000_001))
        args.wheels=cache/'wheels'
        subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:','--platform','win_amd64','--python-version','312','--implementation','cp','--abi','cp312','-r',str(Path(__file__).with_name('requirements.txt')),'-d',str(args.wheels)],check=True)
    if args.runtime is None or args.wheels is None:
        parser.error('provide --download or both --runtime and --wheels')
    build(args.runtime,args.wheels,args.output)

if __name__=='__main__':
    main()
