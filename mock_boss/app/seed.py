import argparse
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import make_url
from app.config import Settings, session_scope
from app.models import Account


async def seed():
    if make_url(Settings().mock_database_url).database not in ('erp_demo', 'erp_dev', 'erp_phase1_test'):
        raise ValueError('Mock seed requires a named project development/demo/test database')
    async with session_scope() as db:
        for i in range(1, 15):
            uid = uuid5(NAMESPACE_URL, f'erp-mock/account/{i}')
            if await db.get(Account, uid):
                continue
            facts = {'schema_version': 1, 'simulated': True, 'package_name': '融合129',
                     'broadband': True, 'contract_end': None, 'verified': True,
                     'tenure_months': 24, 'is_new_customer': False, 'discounts': [], 'restrictions': [],
                     'product_id': str(uuid5(NAMESPACE_URL, 'erp-phase1-demo/product-0'))}
            if i == 2: facts['contract_end'] = '2027-10-02'
            if i == 3: facts['contract_end'] = '2026-10-02'
            if i == 5: facts['verified'] = None
            if i == 6: facts['broadband'] = False
            if i == 7: facts['discounts'] = ['retention']
            if i == 8: facts['is_new_customer'] = True
            if i == 9: facts['restrictions'] = ['ARREARS']
            if i == 10: facts['tenure_months'] = None
            if i == 13: facts['contract_end'] = '2026-10-15'
            db.add(Account(id=uid, customer_id=uuid5(NAMESPACE_URL, f'erp-mock/customer/{i}'),
                number=f'199000000{i:02}', monthly_fee=None if i == 4 else Decimal('129.00'), facts=facts,
                scenario='QUERY_TIMEOUT' if i == 12 else 'NORMAL', source_time=datetime(2026, 10, 2, tzinfo=UTC)))
        await db.commit()


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--demo', action='store_true', required=True); p.parse_args()
    asyncio.run(seed())
    print('14 simulated accounts initialized without overwriting existing facts.')
