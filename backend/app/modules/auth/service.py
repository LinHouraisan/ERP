import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import select

from app.core.db import utcnow
from app.core.errors import DomainError
from app.modules.auth.models import AuthSession, User

hasher = PasswordHasher()


def hash_password(password: str):
    return hasher.hash(password)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf(token: str):
    return hmac.new(token.encode(), b'erp-csrf', hashlib.sha256).hexdigest()


async def login(db, username, password):
    user = await db.scalar(select(User).where(User.username == username, User.active.is_(True)))
    try:
        if user is None or not hasher.verify(user.password_hash, password):
            raise DomainError('BAD_CREDENTIALS', '账号或口令错误', 401)
    except VerificationError:
        raise DomainError('BAD_CREDENTIALS', '账号或口令错误', 401) from None
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=digest(token), expires_at=utcnow() + timedelta(hours=8)))
    await db.commit()
    return user, token
