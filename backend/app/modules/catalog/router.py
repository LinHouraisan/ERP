from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from app.core.errors import DomainError

from app.core.db import get_db
from app.core.security import current_user, owned, require_role
from app.modules.catalog.models import PolicyVersion, Product
from app.modules.catalog.schemas import PolicyInput, PolicyOut, ProductInput, ProductOut
from app.modules.catalog import service

router = APIRouter(prefix='/api/v1', tags=['资料'])


@router.get('/products')
async def products(q: str = '', page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    where = (Product.store_id == user.store_id, Product.name.contains(q, autoescape=True))
    rows = (await db.scalars(select(Product).where(*where).order_by(Product.created_at, Product.id).offset((page-1)*page_size).limit(page_size))).all()
    return {'items': [ProductOut.model_validate(p) for p in rows], 'total': await db.scalar(select(func.count()).select_from(Product).where(*where)), 'page': page, 'page_size': page_size}


@router.post('/products', response_model=ProductOut, status_code=201)
async def create_product(data: ProductInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'ADMIN')
    pid = await db.scalar(insert(Product).values(store_id=user.store_id, **data.model_dump()).on_conflict_do_nothing().returning(Product.id))
    if pid is None: raise DomainError('SKU_EXISTS', '本店已有相同商品编码，请使用原商品')
    await db.commit()
    return await db.get(Product, pid)


@router.get('/products/{product_id}/policy-versions')
async def policies(product_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    await owned(db, Product, product_id, user)
    rows = (await db.scalars(select(PolicyVersion).where(PolicyVersion.product_id == product_id).order_by(PolicyVersion.version.desc()))).all()
    return {'items': [PolicyOut.model_validate(p) for p in rows], 'total': len(rows), 'page': 1, 'page_size': len(rows)}


@router.get('/policy-versions/{policy_id}', response_model=PolicyOut)
async def policy_detail(policy_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await owned(db, PolicyVersion, policy_id, user)


@router.post('/products/{product_id}/policy-versions', response_model=PolicyOut, status_code=201)
async def create_policy(product_id: UUID, data: PolicyInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.create_policy(db, user, product_id, data)


@router.post('/policy-versions/{policy_id}/publish', response_model=PolicyOut)
async def publish(policy_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.publish(db, user, policy_id)


@router.post('/policy-versions/{policy_id}/edit', response_model=PolicyOut)
async def edit(policy_id: UUID, data: PolicyInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.edit_policy(db, user, policy_id, data)
