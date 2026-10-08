from uuid import uuid5
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.core.security import owned
from app.integrations import boss
from app.modules.accounts.models import Customer, BusinessAccount, AccountSnapshot, AccountBinding
from app.modules.services.models import ServiceSession
from app.modules.services.service import event, require_active


async def query(db, user, sid, data):
    service = await owned(db, ServiceSession, sid, user)
    require_active(service)
    await db.commit()
    result = await boss.query_account(data.number, data.account_type)
    service = await owned(db, ServiceSession, sid, user, lock=True)
    require_active(service)
    if result.status == 'NOT_FOUND':
        event(db, user, sid, 'ACCOUNT_NOT_FOUND')
        await db.commit()
        return None
    facts = result.payload
    customer_id = uuid5(user.store_id, str(facts.customer_external_id))
    account_id = uuid5(user.store_id, str(facts.external_id))
    await db.execute(insert(Customer).values(id=customer_id, store_id=user.store_id, external_id=facts.customer_external_id).on_conflict_do_nothing())
    await db.execute(insert(BusinessAccount).values(id=account_id, store_id=user.store_id, customer_id=customer_id,
        external_id=facts.external_id, source=result.source, number=facts.number, account_type=facts.account_type).on_conflict_do_nothing())
    account = await owned(db, BusinessAccount, account_id, user, lock=True)
    binding = await db.scalar(select(AccountBinding).where(AccountBinding.account_id == account_id).order_by(AccountBinding.created_at.desc(), AccountBinding.id.desc()).limit(1))
    if binding is None or binding.customer_id != customer_id:
        db.add(AccountBinding(store_id=user.store_id, account_id=account_id, customer_id=customer_id, source=result.source, source_time=result.source_time))
        account.customer_id = customer_id
    service.customer_id, service.account_id = customer_id, account_id
    required = ('monthly_fee', 'broadband', 'verified', 'tenure_months', 'is_new_customer', 'restrictions', 'discounts')
    snapshot = AccountSnapshot(store_id=user.store_id, service_id=sid, account_id=account_id, source=result.source,
        source_time=result.source_time, completeness='PARTIAL' if any(getattr(facts, field) is None for field in required) or 'contract_end' not in facts.model_fields_set else 'COMPLETE', payload=facts.model_dump(mode='json', exclude_unset=True))
    db.add(snapshot); await db.flush()
    event(db, user, sid, 'ACCOUNT_QUERIED', {'snapshot_id': str(snapshot.id)})
    await db.commit()
    return snapshot
