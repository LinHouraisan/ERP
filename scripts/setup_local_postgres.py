"""Windows project-only PostgreSQL, with pinned official archive and dedicated roles/databases."""
import asyncio
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import zipfile
from urllib.parse import urlparse, unquote
import asyncpg
import httpx
from dotenv import dotenv_values

if os.name!='nt': raise SystemExit('Use Compose or an existing PostgreSQL installation on this platform.')
root=Path(__file__).resolve().parents[1]; local=root/'.local'; local.mkdir(exist_ok=True)
subprocess.run([sys.executable,str(root/'scripts/init_env.py')],check=True)
env=dotenv_values(root/'.env')
data=local/'pgdata'; pg=local/'pgsql/bin'; archive=local/'postgresql.zip'
expected='e2246ba91d22345bc3d017586c09ede52d9df180b1eeb480f050445f1cad84e2'
if not (pg/'postgres.exe').exists():
    if not archive.exists():
        print('Downloading pinned PostgreSQL 18.6 Windows binaries into .local/ (about 367 MiB).')
        with httpx.stream('GET','https://get.enterprisedb.com/postgresql/postgresql-18.6-5-windows-x64-binaries.zip',follow_redirects=True,timeout=60) as response:
            response.raise_for_status()
            with archive.open('wb') as out:
                for block in response.iter_bytes(): out.write(block)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected: raise SystemExit('Archive checksum mismatch; no extraction performed.')
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            target=(local/entry.filename).resolve()
            if entry.filename.startswith(('pgsql/bin/','pgsql/lib/','pgsql/share/')) and target.is_relative_to(local.resolve()): z.extract(entry,local)
password_file=local/'pg-password'
if data.exists() and not password_file.exists(): raise SystemExit('Existing local cluster lacks its private password file; refusing reinitialization.')
if not password_file.exists(): password_file.write_text(env['PG_ADMIN_PASSWORD'],encoding='ascii')
password=password_file.read_text().strip()
flags=subprocess.CREATE_NO_WINDOW
if not data.exists():
    subprocess.run([str(pg/'initdb.exe'),'-D',str(data),'-U','postgres','--auth=scram-sha-256','--pwfile='+str(password_file),'--encoding=UTF8','--locale=C'],check=True,creationflags=flags)
    with (data/'postgresql.conf').open('a') as f: f.write("\nlisten_addresses='127.0.0.1'\nport=55432\n")
if subprocess.run([str(pg/'pg_ctl.exe'),'-D',str(data),'status'],capture_output=True,creationflags=flags).returncode:
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',55432))==0: raise SystemExit('Port 55432 already belongs to another process.')
    subprocess.run([str(pg/'pg_ctl.exe'),'-D',str(data),'-l',str(local/'postgres.log'),'start'],check=True,creationflags=flags)


async def provision():
    conn=await asyncpg.connect(host='127.0.0.1',port=55432,user='postgres',password=password)
    for role,key in [('erp_app','DATABASE_URL'),('erp_mock','MOCK_DATABASE_URL')]:
        url=urlparse(env[key].replace('postgresql+asyncpg','postgresql'))
        if url.hostname!='127.0.0.1' or url.port!=55432 or url.username!=role: raise ValueError('Local setup requires the example project URLs')
        if not await conn.fetchval('SELECT 1 FROM pg_roles WHERE rolname=$1',role):
            secret=unquote(url.password).replace("'","''")
            await conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{secret}'")
    for name in ('erp_demo','erp_phase1_test'):
        if not await conn.fetchval('SELECT 1 FROM pg_database WHERE datname=$1',name): await conn.execute(f'CREATE DATABASE {name}')
        c=await asyncpg.connect(host='127.0.0.1',port=55432,user='postgres',password=password,database=name)
        await c.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC; CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION erp_app; CREATE SCHEMA IF NOT EXISTS boss AUTHORIZATION erp_mock;')
        await c.execute(f'ALTER ROLE erp_app IN DATABASE {name} SET search_path TO app; ALTER ROLE erp_mock IN DATABASE {name} SET search_path TO boss;')
        await c.close()
    await conn.close()


asyncio.run(provision())
print('Project-only PostgreSQL ready on 127.0.0.1:55432. Existing roles and records preserved.')
