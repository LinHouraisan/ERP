from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import Settings
from app.core.db import session_scope
from app.core.errors import DomainError, install_errors

app = FastAPI(title="营业厅服务工作台")
install_errors(app)

from app.modules.auth.router import router as auth_router
app.include_router(auth_router)
from app.modules.catalog.router import router as catalog_router
app.include_router(catalog_router)
from app.modules.services.router import router as services_router
app.include_router(services_router)
from app.modules.recommendations.router import router as recommendations_router
app.include_router(recommendations_router)
from app.modules.recommendations.ai_router import router as ai_router
app.include_router(ai_router)
from app.modules.quality.router import router as quality_router
app.include_router(quality_router)
from app.modules.queue.router import router as queue_router
app.include_router(queue_router)
from app.modules.acceptances.router import router as acceptances_router
app.include_router(acceptances_router)
from app.modules.feedback.router import router as feedback_router
app.include_router(feedback_router)
from app.modules.improvements.router import router as improvements_router
app.include_router(improvements_router)
from app.modules.evaluations.router import router as evaluations_router
app.include_router(evaluations_router)
from app.modules.inventory.router import router as inventory_router
app.include_router(inventory_router)
from app.modules.accounts.router import router as customers_router
app.include_router(customers_router)
from app.modules.sales.router import router as sales_router
app.include_router(sales_router)
from app.modules.installations.router import router as installations_router
app.include_router(installations_router)
from app.modules.finance.router import router as finance_router
app.include_router(finance_router)
from app.modules.operations.router import router as operations_router
app.include_router(operations_router)
from app.modules.aftersales.router import router as aftersales_router
app.include_router(aftersales_router)
from app.modules.transactions.router import router as transactions_router
app.include_router(transactions_router)
from app.modules.aftersales.reversals import router as reversals_router
app.include_router(reversals_router)
from app.modules.finance.settlements import router as settlements_router
app.include_router(settlements_router)
from app.modules.inventory.transfers import router as transfers_router
app.include_router(transfers_router)
from app.modules.inventory.counts import router as counts_router
app.include_router(counts_router)
from app.modules.operations.todos import router as todos_router
app.include_router(todos_router)


@app.get('/health/live')
async def live():
    return {'status': 'alive'}


@app.get('/health/ready')
async def ready():
    try:
        async with session_scope() as db:
            version = await db.scalar(text('select version_num from app.alembic_version'))
        cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
        if version != ScriptDirectory.from_config(cfg).get_current_head():
            raise ValueError('Migration required')
    except Exception:
        raise DomainError('NOT_READY', '数据库或迁移尚未就绪', 503) from None
    return {'status': 'ready', 'ai_mode': Settings().ai_mode, 'simulated': True}
