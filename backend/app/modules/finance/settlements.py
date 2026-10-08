from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func
from app.core.config import business_date
from app.core.db import get_db, utcnow
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import current_user, owned, require_role
from app.modules.auth.models import User
from app.modules.finance.models import Earning, EarningAdjustment, BillLine, ReconciliationCase, Settlement, SettlementLine
from app.modules.finance.schemas import Period, SignedMoney
from app.modules.finance.service import earning_view
from app.modules.aftersales.schemas import Note
from app.modules.catalog.schemas import Money
from app.modules.inventory.schemas import RequestKey

router = APIRouter(prefix='/api/v1/finance', tags=['跨期结算与差异处理'])


class SettlementInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    owner_id: UUID
    period: Period
    amount: Money
    earning_ids: list[UUID] = Field(min_length=1, max_length=300)
    note: str = Field(min_length=1, max_length=1000)


class CaseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    earning_id: UUID | None = None
    bill_line_id: UUID | None = None
    owner_id: UUID
    kind: Literal['TIMING','AMOUNT','MISSING_INTERNAL','ADJUSTMENT']
    reason: str = Field(min_length=1, max_length=1000)
    due_at: AwareDatetime
    proposed_delta: SignedMoney | None = None

    @model_validator(mode='after')
    def source(self):
        if not (self.earning_id or self.bill_line_id): raise ValueError('须关联原台账或原账单')
        if (self.kind == 'ADJUSTMENT') != (self.proposed_delta is not None) or self.proposed_delta is not None and not self.earning_id:
            raise ValueError('补发或扣回申请须关联收益并填写差额')
        return self


class Closure(Note):
    manual: bool = Field(default=False, strict=True)


async def settlement_view(db, row):
    lines = (await db.scalars(select(SettlementLine).where(SettlementLine.settlement_id == row.id).order_by(SettlementLine.id))).all()
    return {**{k:getattr(row,k) for k in ('id','owner_id','period','status','note','confirmed_by','confirmed_at','confirmation_note','created_at','earning_ids')},
        'amount':str(row.amount),'simulated':True,'lines':[{'earning_id':l.earning_id,'amount':str(l.amount),'snapshot':l.snapshot} for l in lines]}


@router.get('/settlements')
async def listing(user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'FINANCE','MANAGER','ADMIN')
    rows=(await db.scalars(select(Settlement).where(Settlement.store_id == user.store_id).order_by(Settlement.created_at.desc()).limit(100))).all()
    return {'items':[await settlement_view(db,r) for r in rows]}


@router.post('/settlements')
async def create(data: SettlementInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'FINANCE','MANAGER','ADMIN')
    await owned(db,User,data.owner_id,user,lock=True)
    ih=content_hash(data.model_dump(mode='json'))
    old=await db.scalar(select(Settlement).where(Settlement.store_id == user.store_id,Settlement.request_key == data.request_key))
    if old:
        if old.input_hash!=ih: raise DomainError('KEY_CONFLICT','结算请求号对应不同内容')
        return await settlement_view(db,old)
    for eid in set(data.earning_ids):
        earning=await owned(db,Earning,eid,user)
        if earning.owner_id!=data.owner_id or earning.period>data.period: raise DomainError('EARNING_MISMATCH','来源必须属于所选员工，结算账期不得早于业务账期')
    row=Settlement(store_id=user.store_id,actor_id=user.user_id,input_hash=ih,**{**data.model_dump(),'earning_ids':[str(i) for i in dict.fromkeys(data.earning_ids)]})
    db.add(row); await db.commit(); return await settlement_view(db,row)


@router.post('/settlements/{sid}/confirm')
async def confirm(sid: UUID, data: Note, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'FINANCE','MANAGER','ADMIN')
    row=await owned(db,Settlement,sid,user)
    # Serializes this employee's disbursements across drafts and periods.
    await owned(db,User,row.owner_id,user,lock=True)
    row=await owned(db,Settlement,sid,user,lock=True)
    if row.status=='CONFIRMED': return await settlement_view(db,row)
    last=await db.scalar(select(func.max(Settlement.period)).where(Settlement.store_id==user.store_id,Settlement.owner_id==row.owner_id,Settlement.status=='CONFIRMED'))
    if last and row.period<last: raise DomainError('PERIOD_ORDER','已有后续账期结算，请将补发或扣回列入当前账期')
    earnings=(await db.scalars(select(Earning).where(Earning.store_id==user.store_id,Earning.owner_id==row.owner_id).order_by(Earning.id).with_for_update())).all()
    balances=[]
    for earning in earnings:
        detail=await earning_view(db,earning,row.period)
        amount=Decimal(detail['available_commission'])
        if amount<0 or str(earning.id) in row.earning_ids and amount>0: balances.append((earning,amount,detail))
    net=sum((a for _,a,_ in balances),Decimal('0.00'))
    if row.amount>net or not balances: raise DomainError('SETTLEMENT_LIMIT','可结算余额不足；历史已发提成的扣回必须先抵扣，不能超发')
    debt=sum((a for _,a,_ in balances if a<0),Decimal('0.00'))
    positive_needed=row.amount-debt
    for earning,available,detail in balances:
        amount=available if available<0 else min(available,positive_needed)
        if amount>0: positive_needed-=amount
        if amount:
            db.add(SettlementLine(store_id=user.store_id,settlement_id=row.id,earning_id=earning.id,amount=amount,
                snapshot={'business_no':earning.business_no,'earning_period':earning.period,'rule':earning.snapshot['rule'],
                    'adjusted_commission':detail['adjusted_commission'],'previously_settled':detail['settled_commission'],
                    'available_before':str(available),'match_status':detail['match_status']}))
    row.status,row.confirmed_by,row.confirmed_at,row.confirmation_note='CONFIRMED',user.user_id,utcnow(),data.note
    await db.commit(); return await settlement_view(db,row)


async def case_view(db,row):
    adjustment=await db.scalar(select(EarningAdjustment).where(EarningAdjustment.case_id==row.id))
    return {**{k:getattr(row,k) for k in ('id','earning_id','bill_line_id','actor_id','owner_id','kind','reason','due_at','status','closed_by','closed_at','evidence','created_at')},
        'proposed_delta':str(row.proposed_delta) if row.proposed_delta is not None else None, 'adjustment_id':adjustment.id if adjustment else None}


@router.get('/cases')
async def cases(user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'FINANCE','MANAGER','ADMIN')
    rows=(await db.scalars(select(ReconciliationCase).where(ReconciliationCase.store_id==user.store_id).order_by(ReconciliationCase.created_at.desc()).limit(100))).all()
    return {'items':[await case_view(db,r) for r in rows]}


@router.post('/cases')
async def new_case(data: CaseInput,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'FINANCE','MANAGER','ADMIN')
    owner=await owned(db,User,data.owner_id,user,lock=True)
    if not owner.active or owner.role not in ('FINANCE','MANAGER','ADMIN'): raise DomainError('INVALID_OWNER','请选择本店财务或负责人')
    ih=content_hash(data.model_dump(mode='json'))
    old=await db.scalar(select(ReconciliationCase).where(ReconciliationCase.store_id==user.store_id,ReconciliationCase.request_key==data.request_key))
    if old:
        if old.input_hash!=ih: raise DomainError('KEY_CONFLICT','差异处理请求号对应不同内容')
        return await case_view(db,old)
    earning=await owned(db,Earning,data.earning_id,user) if data.earning_id else None
    bill=await owned(db,BillLine,data.bill_line_id,user) if data.bill_line_id else None
    if earning and bill and (earning.business_no!=bill.business_no or earning.period!=bill.earning_period): raise DomainError('SOURCE_MISMATCH','账单与收益业务号及归属期不一致')
    row=ReconciliationCase(store_id=user.store_id,actor_id=user.user_id,input_hash=ih,**data.model_dump())
    db.add(row); await db.commit(); return await case_view(db,row)


@router.post('/cases/{cid}/approve-adjustment')
async def approve_adjustment(cid: UUID,data: Note,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    row=await owned(db,ReconciliationCase,cid,user)
    if row.kind!='ADJUSTMENT' or row.earning_id is None: raise DomainError('NOT_ADJUSTMENT','此记录不是收益调整申请')
    earning=await owned(db,Earning,row.earning_id,user,lock=True)
    row=await owned(db,ReconciliationCase,cid,user,lock=True)
    if await db.scalar(select(EarningAdjustment.id).where(EarningAdjustment.case_id==cid)): return await case_view(db,row)
    if row.status!='OPEN': raise DomainError('CASE_CLOSED','差异处理单已关闭')
    detail=await earning_view(db,earning)
    expected=Decimal(detail['adjusted_expected'])+row.proposed_delta
    if not Decimal('0.00')<=expected<=Decimal('9999999999.99'): raise DomainError('ADJUSTMENT_LIMIT','调整后的收益不得为负或超过金额上限')
    commission=(expected*Decimal(earning.snapshot['rule']['employee_rate'])).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    db.add(EarningAdjustment(store_id=user.store_id,earning_id=earning.id,case_id=row.id,actor_id=user.user_id,
        period=business_date().strftime('%Y-%m'),expected_delta=row.proposed_delta,
        commission_delta=commission-Decimal(detail['adjusted_commission']),reason=row.reason,
        snapshot={'rule':earning.snapshot['rule'],'approval_evidence':data.note,'previous_expected':detail['adjusted_expected']}))
    await db.commit(); return await case_view(db,row)


@router.post('/cases/{cid}/close')
async def close_case(cid: UUID,data: Closure,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'FINANCE','MANAGER','ADMIN')
    if data.manual: require_role(user,'MANAGER','ADMIN')
    row=await owned(db,ReconciliationCase,cid,user,lock=True)
    if row.status=='CLOSED': return await case_view(db,row)
    earning=await owned(db,Earning,row.earning_id,user) if row.earning_id else None
    if earning is None and row.bill_line_id:
        bill=await owned(db,BillLine,row.bill_line_id,user)
        earning=await db.scalar(select(Earning).where(Earning.store_id==user.store_id,Earning.business_no==bill.business_no,Earning.period==bill.earning_period))
    detail=await earning_view(db,earning) if earning else None
    if not data.manual and (detail is None or detail['match_status']!='MATCHED' or detail['actual_received'] is None or Decimal(detail['actual_received'])!=Decimal(detail['adjusted_expected'])):
        raise DomainError('CASE_UNRESOLVED','账单或到账差异仍未消除；人工结案须由店长提供依据')
    if row.kind=='ADJUSTMENT' and not await db.scalar(select(EarningAdjustment.id).where(EarningAdjustment.case_id==row.id)):
        raise DomainError('ADJUSTMENT_PENDING','调整申请尚未获批，不可直接结案')
    row.status,row.closed_by,row.closed_at='CLOSED',user.user_id,utcnow()
    row.evidence={'note':data.note,'manual':data.manual,'match_status':detail['match_status'] if detail else 'MISSING_INTERNAL'}
    await db.commit(); return await case_view(db,row)


@router.get('/owners')
async def owners(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'FINANCE','MANAGER','ADMIN')
    rows=(await db.scalars(select(User).where(User.store_id==user.store_id,User.active.is_(True)))).all()
    return {'items':[{'id':r.id,'username':r.username,'role':r.role} for r in rows]}
