import importlib.util
from pathlib import Path
import pytest


def script():
    spec=importlib.util.spec_from_file_location('phase1_database',Path(__file__).resolve().parents[2]/'scripts/database.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


async def test_reset_and_backup_refuse_other_databases_without_connecting():
    module=script()
    module.env={'APP_ENV':'demo','DATABASE_URL':'postgresql+asyncpg://erp_app:unused@localhost/customer','MOCK_DATABASE_URL':'postgresql+asyncpg://erp_mock:unused@localhost/customer'}
    with pytest.raises(ValueError,match='Only paired'): module.check_source()
    module.env['DATABASE_URL']='postgresql+asyncpg://erp_app:unused@localhost/erp_demo'
    module.env['MOCK_DATABASE_URL']='postgresql+asyncpg://erp_mock:unused@localhost/erp_demo'
    with pytest.raises(ValueError,match='confirm-database'): await module.reset_demo('erp_dev')
    module.env['MOCK_DATABASE_URL']='postgresql+asyncpg://erp_app:unused@localhost/erp_demo'
    with pytest.raises(ValueError,match='separate'): module.check_source()


async def test_reset_refuses_unresolved_payments(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    module = script()
    module.env = {'APP_ENV': 'demo'}
    monkeypatch.setattr(module, 'check_source', lambda: ({}, {}))
    connection = SimpleNamespace(fetchval=AsyncMock(side_effect=[1, 0, 'app.payments', 1]))
    monkeypatch.setattr(module.asyncpg, 'connect', AsyncMock(return_value=connection))
    with pytest.raises(ValueError, match='Reconcile unresolved payments'):
        await module.reset_demo('erp_demo')


@pytest.mark.parametrize('pending',[['app.after_sales',1],['app.after_sales',0,'app.telecom_reversals',1]])
async def test_reset_preserves_unresolved_refund_and_reversal_ids(monkeypatch,pending):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    module=script();module.env={'APP_ENV':'demo'}
    monkeypatch.setattr(module,'check_source',lambda: ({},{}))
    connection=SimpleNamespace(fetchval=AsyncMock(side_effect=[1,0,'app.payments',0,*pending]))
    monkeypatch.setattr(module.asyncpg,'connect',AsyncMock(return_value=connection))
    with pytest.raises(ValueError,match='original request IDs'):
        await module.reset_demo('erp_demo')
