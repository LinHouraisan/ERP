"""Dedicated test data for the real-HTTP browser scenarios; never targets the demo DB."""
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import asyncpg
from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv(Path(__file__).resolve().parents[2]/'.env')
os.environ.update(APP_ENV='test',AI_MODE='offline',DATABASE_URL=os.environ['TEST_DATABASE_URL'])
from app import models
from app.core.db import session_scope, require_test_database
from app.modules.auth.schemas import CurrentUser
from app.modules.queue.models import QueueTicket
from app.modules.queue.schemas import TicketAction
from app.modules.queue.service import transition
from app.seed import seed_demo,DEMO_STORE,seed_id


async def main():
    require_test_database(os.environ['DATABASE_URL']); require_test_database(os.environ['MOCK_TEST_DATABASE_URL'])
    await seed_demo()
    actor=CurrentUser(user_id=seed_id('ADMIN'),store_id=DEMO_STORE,username='admin',role='ADMIN',csrf_token='fixture')
    async with session_scope() as db:
        tickets=(await db.scalars(select(QueueTicket).where(QueueTicket.store_id==DEMO_STORE,QueueTicket.status.in_(['WAITING','CALLED','SERVING'])))).all()
        for t in tickets:
            await transition(db,actor,t.id,'finish' if t.status=='SERVING' else 'cancel',TicketAction(reason='专用浏览器测试前整理测试队列'))
    db=await asyncpg.connect(os.environ['MOCK_TEST_DATABASE_URL'].replace('postgresql+asyncpg','postgresql'))
    uid,number=uuid4(),'199'+str(uuid4().int)[-8:]
    facts={'schema_version':1,'simulated':True,'package_name':'融合129','product_id':str(seed_id('product-0')),'broadband':True,'contract_end':None,'verified':True,'tenure_months':24,'is_new_customer':False,'discounts':[],'restrictions':[]}
    await db.execute('INSERT INTO boss.accounts(id,customer_id,number,account_type,monthly_fee,facts,scenario,source_time) VALUES($1,$2,$3,$4,129.00,$5,$6,$7)',uid,uuid4(),number,'MOBILE',json.dumps(facts),sys.argv[1],datetime.now(UTC))
    await db.close()
    print(json.dumps({'number':number,'account_id':str(uid)}))


asyncio.run(main())
