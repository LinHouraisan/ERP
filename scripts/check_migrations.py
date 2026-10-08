"""Exercise empty initialization and previous-version data upgrade in a new isolated database."""
import asyncio
from datetime import UTC,datetime
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import asyncpg
from sqlalchemy import URL
from alembic.config import Config
from alembic.script import ScriptDirectory
from database import root,env,check_source,admin_config,flags


async def main():
    source,mock=check_source()
    name='erp_upgrade_'+datetime.now(UTC).strftime('%Y%m%d%H%M%S')+'_test'
    admin=await asyncpg.connect(**admin_config(source))
    if await admin.fetchval('SELECT 1 FROM pg_database WHERE datname=$1',name): raise ValueError('Check database already exists; nothing overwritten')
    await admin.execute(f'CREATE DATABASE {name}')
    c=await asyncpg.connect(**{**admin_config(source),'database':name})
    await c.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC; CREATE SCHEMA app AUTHORIZATION erp_app; CREATE SCHEMA boss AUTHORIZATION erp_mock;')
    await c.close();await admin.close()
    runtime={**env,'APP_ENV':'test','AI_MODE':'offline'}
    for key,cfg in [('DATABASE_URL',source),('MOCK_DATABASE_URL',mock)]:
        runtime[key]=URL.create('postgresql+asyncpg',username=cfg['user'],password=cfg['password'],host=cfg['host'],port=cfg['port'],database=name).render_as_string(hide_password=False)
    heads = {folder: ScriptDirectory.from_config(Config(str(root/folder/'alembic.ini'))).get_current_head() for folder in ('backend','mock_boss')}
    for folder,version in [('backend','016'),('mock_boss','003')]:
        subprocess.run([sys.executable,'-m','alembic','upgrade',version],cwd=root/folder,env=runtime,check=True,creationflags=flags)
    store,user,service,account=uuid4(),uuid4(),uuid4(),uuid4()
    c=await asyncpg.connect(**{**source,'database':name})
    await c.execute('INSERT INTO app.stores(id,name,created_at,updated_at) VALUES($1,$2,now(),now())',store,'上一版本升级检查')
    await c.execute("INSERT INTO app.users(id,store_id,username,password_hash,role,active,created_at,updated_at) VALUES($1,$2,$3,'disabled-test-hash','STAFF',false,now(),now())",user,store,str(user))
    await c.execute("INSERT INTO app.service_sessions(id,store_id,staff_id,category,status,preset,created_at,updated_at,ended_at) VALUES($1,$2,$3,'OTHER','ENDED',true,now(),now(),now())",service,store,user)
    before=dict(await c.fetchrow('SELECT * FROM app.service_sessions WHERE id=$1',service));await c.close()
    batch,bill=uuid4(),uuid4()
    c=await asyncpg.connect(**{**source,'database':name})
    await c.execute("INSERT INTO app.bill_batches(id,store_id,actor_id,request_key,input_hash,period,source,created_at,updated_at) VALUES($1,$2,$3,$4,'test','2026-09','旧版模拟账单',now(),now())",batch,store,user,str(batch))
    await c.execute("INSERT INTO app.bill_lines(id,store_id,batch_id,business_no,period,amount,received_amount,original,created_at,updated_at) VALUES($1,$2,$3,'LEGACY-BILL','2026-09',25.00,NULL,'{}',now(),now())",bill,store,batch)
    prior_bill=dict(await c.fetchrow('SELECT * FROM app.bill_lines WHERE id=$1',bill));await c.close()
    c=await asyncpg.connect(**{**mock,'database':name})
    await c.execute("INSERT INTO boss.accounts(id,customer_id,number,account_type,monthly_fee,facts,scenario,source_time) VALUES($1,$2,'19999998888','MOBILE',129.00,'{}','NORMAL',now())",account,uuid4())
    await c.close()
    for folder in ('backend','mock_boss'):
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=root/folder,env=runtime,check=True,creationflags=flags)
    c=await asyncpg.connect(**{**source,'database':name})
    assert dict(await c.fetchrow('SELECT * FROM app.service_sessions WHERE id=$1',service))==before
    upgraded=dict(await c.fetchrow('SELECT * FROM app.bill_lines WHERE id=$1',bill))
    assert {key:upgraded[key] for key in prior_bill}==prior_bill
    assert upgraded['earning_period']=='2026-09' and upgraded['line_key']=='PRIMARY' and upgraded['is_final'] is True
    assert await c.fetchval('SELECT version_num FROM app.alembic_version')==heads['backend']
    try: await c.fetchval('SELECT count(*) FROM boss.accounts')
    except asyncpg.InsufficientPrivilegeError: pass
    else: raise AssertionError('Main role must not read Mock tables')
    await c.close()
    c=await asyncpg.connect(**{**mock,'database':name})
    assert str(await c.fetchval('SELECT monthly_fee FROM boss.accounts WHERE id=$1',account))=='129.00'
    assert await c.fetchval('SELECT version_num FROM boss.alembic_version')==heads['mock_boss']
    await c.close()
    print(f"PASS: empty initialization, 016->{heads['backend']} / 003->{heads['mock_boss']} data preserved, legacy unknown bill receipt preserved, roles isolated; retained check DB {name}")


asyncio.run(main())
