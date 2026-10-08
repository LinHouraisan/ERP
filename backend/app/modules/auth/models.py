from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Identity


class Organization(Identity, Base):
    __tablename__ = 'organizations'
    name: Mapped[str] = mapped_column(String(100))


class Store(Identity, Base):
    __tablename__ = 'stores'
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(80), default='演示市', server_default='演示市')
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey('app.organizations.id'))


class User(Identity, Base):
    __tablename__ = 'users'
    __table_args__ = (UniqueConstraint('id', 'store_id'), CheckConstraint("role IN ('STAFF','MANAGER','ADMIN','WAREHOUSE','INSTALLER','FINANCE')", name='ck_users_role'))
    store_id: Mapped[UUID] = mapped_column(ForeignKey('app.stores.id'))
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuthSession(Identity, Base):
    __tablename__ = 'auth_sessions'
    user_id: Mapped[UUID] = mapped_column(ForeignKey('app.users.id'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
