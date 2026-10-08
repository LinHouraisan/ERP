import hmac

from fastapi import Request
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import session_scope, utcnow
from app.core.errors import DomainError
from app.modules.auth.models import AuthSession, User
from app.modules.auth.schemas import CurrentUser
from app.modules.auth.service import csrf, digest


def require_origin(request: Request):
    if request.headers.get('origin') != Settings().web_origin:
        raise DomainError('BAD_ORIGIN', '请求来源不被允许', 403)


async def current_user(request: Request):
    token = request.cookies.get('erp_session', '')
    async with session_scope() as db:
        user = await db.scalar(select(User).join(AuthSession).where(
            AuthSession.token_hash == digest(token), AuthSession.expires_at > utcnow(), User.active.is_(True)))
        if user is None:
            raise DomainError('UNAUTHENTICATED', '请先登录', 401)
        if user.role in ('WAREHOUSE', 'INSTALLER', 'FINANCE'):
            allowed = {
                'WAREHOUSE': {'auth', 'products', 'policy-versions', 'inventory', 'installations', 'sales', 'aftersales', 'transfers', 'todos'},
                'INSTALLER': {'auth', 'installations', 'todos'},
                'FINANCE': {'auth', 'finance', 'sales', 'operations', 'aftersales', 'todos'},
            }
            module = request.url.path.removeprefix('/api/v1/').split('/')[0]
            if module not in allowed[user.role]:
                raise DomainError('FORBIDDEN', '当前身份无权访问此业务', 403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            require_origin(request)
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), csrf(token)):
                raise DomainError('CSRF_FAILED', '会话验证失败，请刷新后重试', 403)
        return CurrentUser(user_id=user.id, store_id=user.store_id, username=user.username, role=user.role, csrf_token=csrf(token))


def require_role(user: CurrentUser, *roles: str):
    if user.role not in roles:
        raise DomainError('FORBIDDEN', '当前身份无权执行此操作', 403)


async def owned(db, model, resource_id, user, *, lock=False):
    statement = select(model).where(model.id == resource_id, model.store_id == user.store_id)
    item = await db.scalar(statement.with_for_update().execution_options(populate_existing=True) if lock else statement)
    if item is None:
        raise DomainError('NOT_FOUND', '记录不存在或无权访问', 404)
    return item
