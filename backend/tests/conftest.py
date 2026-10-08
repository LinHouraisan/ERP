import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')
os.environ['APP_ENV'] = 'test'
os.environ['AI_MODE'] = 'offline'
os.environ['DATABASE_URL'] = os.environ['TEST_DATABASE_URL']
os.environ['BOSS_URL'] = 'http://127.0.0.1:8002'

from app.core.db import require_test_database

require_test_database(os.environ['DATABASE_URL'])

import httpx
import pytest


@pytest.fixture
async def client():
    from app.main import app
    from app.seed import seed_demo
    await seed_demo()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:5173') as c:
        c.headers['Origin'] = 'http://127.0.0.1:5173'
        response = await c.post('/api/v1/auth/login', json={'username': 'admin', 'password': os.environ['DEMO_PASSWORD']})
        assert response.status_code == 200, response.text
        c.headers['X-CSRF-Token'] = response.json()['csrf_token']
        yield c


@pytest.fixture
async def mock_account():
    import asyncpg
    import json
    from uuid import uuid4
    from datetime import UTC, datetime
    url = os.environ['MOCK_TEST_DATABASE_URL']
    require_test_database(url)
    c = await asyncpg.connect(url.replace('postgresql+asyncpg://','postgresql://'))
    uid, number = uuid4(), '199'+str(uuid4().int)[-8:]
    facts = {'schema_version':1,'simulated':True,'package_name':'融合129','product_id':str(uuid4()),'broadband':True,
        'contract_end':None,'verified':True,'tenure_months':24,'is_new_customer':False,'discounts':[],'restrictions':[]}
    await c.execute('INSERT INTO boss.accounts(id,customer_id,number,account_type,monthly_fee,facts,scenario,source_time) VALUES($1,$2,$3,$4,129.00,$5,$6,$7)',
        uid,uuid4(),number,'MOBILE',json.dumps(facts),'NORMAL',datetime.now(UTC))
    yield c, uid, number
    await c.close()
