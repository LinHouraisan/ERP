"""Project demo backup, isolated restore check, and explicitly confirmed demo reset."""
import argparse
import asyncio
from datetime import datetime, UTC
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse, unquote
import asyncpg
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
env={**os.environ,**dotenv_values(root/'.env')}
flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0


def connection(key):
    url=urlparse(env[key].replace('postgresql+asyncpg','postgresql'))
    return dict(host=url.hostname,port=url.port or 5432,user=unquote(url.username),password=unquote(url.password),database=url.path.lstrip('/'))


def check_source(test=False):
    a,b=connection('TEST_DATABASE_URL' if test else 'DATABASE_URL'),connection('MOCK_TEST_DATABASE_URL' if test else 'MOCK_DATABASE_URL')
    expected='erp_phase1_test' if test else 'erp_demo'
    if env.get('APP_ENV') not in ('demo','test','development') or any(c['database']!=expected for c in (a,b)) or any(a[k]!=b[k] for k in ('host','port','database')):
        raise ValueError('Only paired project demo/test databases are supported')
    if a['user']!='erp_app' or b['user']!='erp_mock': raise ValueError('Expected separate erp_app and erp_mock roles')
    return a,b


def pgtool(name,args,cfg):
    binary=root/'.local/pgsql/bin'/(name+('.exe' if os.name=='nt' else ''))
    command=str(binary) if binary.exists() else shutil.which(name)
    if not command: raise ValueError('PostgreSQL client tools are required')
    subprocess.run([command,'--host',cfg['host'],'--port',str(cfg['port']),'--username',cfg['user'],'--dbname',cfg['database'],*args],
        env={**os.environ,'PGPASSWORD':cfg['password']},check=True,creationflags=flags)


async def fingerprint(c):
    data={}
    queries = {
        'services':'SELECT id,status,preset,ended_at FROM app.service_sessions ORDER BY id',
        'snapshots':'SELECT id,payload,source_time FROM app.account_snapshots ORDER BY id',
        'requests':'SELECT id,external_request_id,external_order_id,status,external_payload FROM app.acceptances ORDER BY id',
        'feedback':'SELECT id,service_id,score,content_hash FROM app.feedback ORDER BY id',
    }
    for table in ('sales_orders','payments','stock','stock_movements','installations','earnings','bill_lines','customer_business',
        'transactions','transaction_links','after_sales','after_sale_events','telecom_reversals','reversal_events','earning_adjustments',
        'reconciliation_cases','settlements','settlement_lines','transfers','transfer_events','stock_counts','stock_serials'):
        if await c.fetchval('SELECT to_regclass($1)', 'app.'+table): queries[table] = f'SELECT * FROM app.{table} ORDER BY id'
    for name,query in queries.items():
        rows=[dict(r) for r in await c.fetch(query)]
        data[name]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
    return data


async def mock_fingerprint(c):
    result={}
    for table,key in [('accounts','id'),('acceptances','external_request_id'),('payments','external_request_id'),('refunds','external_request_id'),('reversals','external_request_id')]:
        if not await c.fetchval('SELECT to_regclass($1)','boss.'+table): continue
        rows=[dict(r) for r in await c.fetch(f'SELECT * FROM boss.{table} ORDER BY {key}')]
        result[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
    return result


async def backup(test=False):
    a,b=check_source(test)
    folder=root/'.local/backups'/datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True)
    c=await asyncpg.connect(**a)
    async with c.transaction(isolation='repeatable_read',readonly=True):
        snapshot=await c.fetchval('SELECT pg_export_snapshot()')
        manifest={'database':a['database'],'created_at':datetime.now(UTC).isoformat(),'fingerprint':await fingerprint(c)}
        if not re.fullmatch(r'[0-9A-Fa-f-]+',snapshot): raise ValueError('Unexpected PostgreSQL snapshot format')
        external=await asyncpg.connect(**b)
        async with external.transaction(isolation='repeatable_read',readonly=True):
            await external.execute(f"SET TRANSACTION SNAPSHOT '{snapshot}'")
            manifest['mock_fingerprint']=await mock_fingerprint(external)
        await external.close()
        for schema,cfg in [('app',a),('boss',b)]:
            pgtool('pg_dump',['--format=custom','--no-owner','--no-acl','--schema',schema,'--snapshot',snapshot,'--file',str(folder/f'{schema}.dump')],cfg)
    await c.close()
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Backup created: '+str(folder))
    return folder


def admin_config(source):
    local=root/'.local/pg-password'
    password=local.read_text().strip() if source['host']=='127.0.0.1' and source['port']==55432 and local.exists() else env.get('PG_ADMIN_PASSWORD')
    return {**source,'user':'postgres','password':password,'database':'postgres'}


async def restore_check(folder,test=False):
    a,b=check_source(test)
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['database']!=a['database']: raise ValueError('Backup database does not match selected source')
    name='erp_restore_'+datetime.now(UTC).strftime('%Y%m%d%H%M%S')+'_test'
    if not re.fullmatch(r'erp_restore_\d{14}_test',name): raise ValueError('Unsafe restore name')
    admin=await asyncpg.connect(**admin_config(a))
    if await admin.fetchval('SELECT 1 FROM pg_database WHERE datname=$1',name): raise ValueError('Restore target already exists; nothing overwritten')
    await admin.execute(f'CREATE DATABASE {name}')
    await admin.execute(f'GRANT CREATE ON DATABASE {name} TO erp_app,erp_mock')
    for schema,cfg in [('app',a),('boss',b)]:
        pgtool('pg_restore',['--no-owner','--no-acl','--exit-on-error',str(folder/f'{schema}.dump')],{**cfg,'database':name})
    await admin.execute(f'REVOKE CREATE ON DATABASE {name} FROM erp_app,erp_mock')
    await admin.close()
    c=await asyncpg.connect(**{**a,'database':name})
    actual=await fingerprint(c)
    unknown=await c.fetchval("SELECT count(*) FROM app.acceptances WHERE status IN ('UNKNOWN','SUBMITTING','SUBMITTED')")
    unresolved_payments=await c.fetchval("SELECT count(*) FROM app.payments WHERE status IN ('UNKNOWN','PENDING')") if await c.fetchval("SELECT to_regclass('app.payments')") else None
    await c.close()
    if actual!=manifest['fingerprint']: raise ValueError('Restore fingerprint differs from backup')
    if 'mock_fingerprint' in manifest:
        external=await asyncpg.connect(**{**b,'database':name})
        restored_mock=await mock_fingerprint(external);await external.close()
        if restored_mock!=manifest['mock_fingerprint']: raise ValueError('Restored Mock receipts differ from backup')
    result={'restored_database':name,'fingerprint':actual,'unresolved_requests_preserved':unknown,'unresolved_payments_preserved':unresolved_payments,'note':'Unresolved results require the original external_request_id lookup; restored snapshots do not prove external success.'}
    if 'mock_fingerprint' in manifest: result['mock_fingerprint']=restored_mock
    (folder/'restore-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


async def reset_demo(confirm):
    a,b=check_source()
    if confirm!='erp_demo' or env.get('APP_ENV')!='demo': raise ValueError('Reset requires APP_ENV=demo and --confirm-database erp_demo')
    c=await asyncpg.connect(**a)
    from uuid import uuid5,NAMESPACE_URL
    if not await c.fetchval('SELECT 1 FROM app.stores WHERE id=$1',uuid5(NAMESPACE_URL,'erp-phase1-demo/store')): raise ValueError('Project demo marker missing')
    if await c.fetchval("SELECT count(*) FROM app.acceptances WHERE status IN ('UNKNOWN','SUBMITTING','SUBMITTED')"):
        raise ValueError('Reconcile unresolved acceptances before reset; reset is not cancellation')
    if await c.fetchval("SELECT to_regclass('app.payments')") and await c.fetchval("SELECT count(*) FROM app.payments WHERE status IN ('PENDING','UNKNOWN')"):
        raise ValueError('Reconcile unresolved payments before reset; reset is not a refund')
    for table,column in [('after_sales','refund_status'),('telecom_reversals','status')]:
        if await c.fetchval('SELECT to_regclass($1)','app.'+table) and await c.fetchval(f"SELECT count(*) FROM app.{table} WHERE {column} IN ('PENDING','UNKNOWN')"):
            raise ValueError('Reconcile unresolved refunds and reversals before reset; their original request IDs must be retained')
    await c.close()
    await backup()
    c=await asyncpg.connect(**{**admin_config(a),'database':a['database']})
    tables=await c.fetch("SELECT format('%I.%I',schemaname,tablename) AS name FROM pg_tables WHERE schemaname IN ('app','boss') AND tablename <> 'alembic_version'")
    async with c.transaction():
        await c.execute('TRUNCATE '+','.join(r['name'] for r in tables)+' CASCADE')
    await c.close()
    for folder in ('backend','mock_boss'):
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=root/folder,env=env,check=True,creationflags=flags)
        subprocess.run([sys.executable,'-m','app.seed','--demo'],cwd=root/folder,env=env,check=True,creationflags=flags)
    print('Explicitly confirmed demo reset complete; backup retained.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['backup','restore-check','reset'])
    parser.add_argument('--test',action='store_true');parser.add_argument('--backup',type=Path)
    parser.add_argument('--reset-demo',action='store_true');parser.add_argument('--confirm-database')
    args=parser.parse_args()
    if args.action=='backup': asyncio.run(backup(args.test))
    elif args.action=='restore-check':
        if not args.backup: parser.error('--backup is required')
        asyncio.run(restore_check(args.backup,args.test))
    else:
        if not args.reset_demo or args.test: parser.error('reset requires --reset-demo and cannot target test data')
        asyncio.run(reset_demo(args.confirm_database))


if __name__=='__main__': main()
