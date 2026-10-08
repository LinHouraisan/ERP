"""Start this checkout locally; no system service installation and no unrelated process stops."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--background',action='store_true');args=parser.parse_args()
env={**os.environ,**dotenv_values(root/'.env')}
web=urlparse(env.get('WEB_ORIGIN','http://127.0.0.1:5173'))
if web.hostname!='127.0.0.1': raise SystemExit('Local launcher requires WEB_ORIGIN on 127.0.0.1')
ports=[8000,8001,web.port or 5173]
for port in ports:
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',port))==0: raise SystemExit(f'Port {port} is already in use; existing process left untouched.')
flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
local=root/'.local';local.mkdir(exist_ok=True)
pg=local/'pgsql/bin/pg_ctl.exe'
if pg.exists() and (local/'pgdata').exists():
    if subprocess.run([str(pg),'-D',str(local/'pgdata'),'status'],capture_output=True,creationflags=flags).returncode:
        subprocess.run([str(pg),'-D',str(local/'pgdata'),'-l',str(local/'postgres.log'),'start'],check=True,creationflags=flags)
for folder in ('backend','mock_boss'):
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=root/folder,env=env,check=True,creationflags=flags)
    subprocess.run([sys.executable,'-m','app.seed','--demo'],cwd=root/folder,env=env,check=True,creationflags=flags)
children=[]
try:
    commands=[('mock_boss',[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001','--no-access-log']),
        ('backend',[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--no-access-log']),
        ('frontend',[shutil.which('node'),str(root/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(ports[2]),'--strictPort'])]
    for folder,command in commands:
        with (local/f'{folder}.log').open('ab') as log:
            children.append(subprocess.Popen(command,cwd=root/folder,env=env,stdout=log,stderr=log,creationflags=flags))
    print(f'Local simulated workspace: {web.geturl()} (login password in private .env). Logs: .local/')
    if args.background:
        print('Started component process IDs: '+', '.join(str(p.pid) for p in children))
    else:
        print('Press Ctrl+C to stop only these application processes; database remains available.')
        while all(p.poll() is None for p in children): time.sleep(1)
except KeyboardInterrupt: pass
finally:
    if not args.background:
        for child in children:
            if child.poll() is None:
                if os.name=='nt': subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=subprocess.DEVNULL,creationflags=flags)
                else: child.terminate()
