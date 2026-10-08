from datetime import timedelta
from sqlalchemy import or_, select
from fastapi import APIRouter, Depends
from app.core.db import get_db, utcnow
from app.core.security import current_user
from app.modules.auth.models import User
from app.modules.aftersales.models import AfterSale, Reversal
from app.modules.sales.models import Payment
from app.modules.acceptances.models import Acceptance
from app.modules.services.models import ServiceSession, ServiceTask
from app.modules.installations.models import Installation
from app.modules.finance.models import ReconciliationCase, Settlement
from app.modules.inventory.transfers_models import Transfer, StockCount
from app.modules.improvements.models import ImprovementTask
from app.modules.transactions.models import Transaction
from app.modules.transactions.router import view as transaction_view

router=APIRouter(prefix='/api/v1/todos',tags=['统一待办'])


@router.get('')
async def todos(user=Depends(current_user),db=Depends(get_db)):
    staff=(await db.scalars(select(User).where(User.store_id==user.store_id,User.active.is_(True)).order_by(User.created_at,User.id))).all()
    names={s.id:s.username for s in staff}
    manager=next((s.id for s in staff if s.role=='MANAGER'),next((s.id for s in staff if s.role=='ADMIN'),user.user_id))
    role_owner=lambda role: next((s.id for s in staff if s.role==role),manager)
    items=[]
    now=utcnow()
    def add(kind,row,title,url,owner=None,due=None,status=None):
        deadline=due or row.created_at+timedelta(days=2)
        assigned=owner or manager
        items.append({'key':kind+':'+str(row.id),'source_id':row.id,'kind':kind,'title':title,'url':url,'owner_id':assigned,
            'owner_name':names.get(assigned,'本店负责人'),'due_at':deadline,'overdue':deadline<now,'status':status or row.status})

    if user.role!='FINANCE':
        q=select(Installation).where(Installation.store_id==user.store_id,Installation.status.not_in(['COMPLETED','CANCELLED']))
        if user.role=='INSTALLER': q=q.where(Installation.installer_id==user.user_id)
        for row in (await db.scalars(q)).all(): add('INSTALLATION',row,'安装交付待处理',f'/installations?id={row.id}',row.installer_id,row.appointment_at)
    if user.role=='INSTALLER': return {'items':sorted(items,key=lambda x:x['due_at']),'as_of':now}
    for row in (await db.scalars(select(AfterSale).where(AfterSale.store_id==user.store_id,AfterSale.status.in_(['REQUESTED','APPROVED'])))).all():
        if user.role=='WAREHOUSE' and (row.kind!='RETURN_REFUND' or row.stock_processed or row.status!='APPROVED'): continue
        owner=role_owner('WAREHOUSE') if row.kind=='RETURN_REFUND' and row.status=='APPROVED' and not row.stock_processed else role_owner('FINANCE') if row.status=='APPROVED' and row.refund_status!='SUCCESS' else manager
        add('AFTERSALE',row,'售后审批、退款或退库',f'/aftersales?id={row.id}',owner,status=row.status+'/'+row.refund_status)
    if user.role in ('STAFF','MANAGER','ADMIN'):
        for row in (await db.scalars(select(Transaction).where(Transaction.store_id==user.store_id))).all():
            summary=await transaction_view(db,row)
            if summary['status'] not in ('COMPLETED','COMPLETED_WITH_ADJUSTMENTS'):
                add('TRANSACTION',row,row.title,f'/transactions?id={row.id}',row.actor_id,status=summary['status'])
        for row in (await db.scalars(select(Reversal).where(Reversal.store_id==user.store_id,Reversal.status.not_in(['SUCCESS','REJECTED'])))).all():
            if row.status=='FAILED' and row.resolution: continue
            add('REVERSAL',row,'通信冲正待核查',f'/reversals?id={row.id}')
        for row in (await db.scalars(select(Acceptance).where(Acceptance.store_id==user.store_id,Acceptance.status.in_(['UNKNOWN','SUBMITTING','SUBMITTED'])))).all():
            source=await db.get(ServiceSession,row.service_id)
            add('ACCEPTANCE',row,'受理结果待核对',f'/services?id={row.service_id}',source.staff_id)
        for row in (await db.scalars(select(ServiceTask).where(ServiceTask.store_id==user.store_id,ServiceTask.status.in_(['OPEN','IN_PROGRESS'])))).all():
            source=await db.get(ServiceSession,row.service_id)
            add('SERVICE_TASK',row,row.title,f'/services?id={row.service_id}',source.staff_id if row.owner_role=='STAFF' else role_owner(row.owner_role))
    if user.role in ('STAFF','FINANCE','MANAGER','ADMIN'):
        for row in (await db.scalars(select(Payment).where(Payment.store_id==user.store_id,Payment.status.in_(['PENDING','UNKNOWN'])))).all():
            add('PAYMENT',row,'原收款请求待核对',f'/sales?id={row.order_id}',row.cashier_id)
    if user.role in ('FINANCE','MANAGER','ADMIN'):
        for row in (await db.scalars(select(ReconciliationCase).where(ReconciliationCase.store_id==user.store_id,ReconciliationCase.status=='OPEN'))).all():
            add('RECONCILIATION',row,'账单差异：'+row.reason,f'/settlements?case_id={row.id}',row.owner_id,row.due_at)
        for row in (await db.scalars(select(Settlement).where(Settlement.store_id==user.store_id,Settlement.status=='DRAFT'))).all():
            add('SETTLEMENT',row,'提成结算草稿待核对',f'/settlements?id={row.id}',role_owner('FINANCE'))
    if user.role in ('WAREHOUSE','MANAGER','ADMIN'):
        for row in (await db.scalars(select(StockCount).where(StockCount.store_id==user.store_id,StockCount.status=='REQUESTED'))).all():
            add('STOCK_COUNT',row,'盘点差异待审批',f'/transfers?count_id={row.id}')
        for row in (await db.scalars(select(Transfer).where(or_(Transfer.source_store_id==user.store_id,Transfer.destination_store_id==user.store_id),Transfer.status.not_in(['RECEIVED','REJECTED','CLOSED_LOSS'])))).all():
            add('TRANSFER',row,'调拨发货、收货或差异核查',f'/transfers?id={row.id}',role_owner('WAREHOUSE') if row.status in ('APPROVED','IN_TRANSIT') else manager)
    if user.role in ('MANAGER','ADMIN'):
        for row in (await db.scalars(select(ImprovementTask).where(ImprovementTask.store_id==user.store_id,ImprovementTask.status.not_in(['CLOSED','REJECTED'])))).all():
            add('IMPROVEMENT',row,'改进建议待确认或验证','/improvements',row.owner_id)
    return {'items':sorted(items,key=lambda x:x['due_at']),'as_of':now,'definition':'从原单据汇总；装维按预约时间、对账按指定期限，其余默认创建后两天复核。完成状态由原业务决定。'}
