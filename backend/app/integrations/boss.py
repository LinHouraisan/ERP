from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings
from app.core.errors import DomainError


class AccountFacts(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1]
    simulated: Literal[True]
    external_id: UUID
    customer_external_id: UUID
    number: str
    account_type: Literal['MOBILE']
    product_id: UUID | None = None
    package_name: str | None = None
    monthly_fee: Decimal | None = None
    broadband: bool | None = None
    contract_end: date | None = None
    verified: bool | None = None
    tenure_months: int | None = None
    is_new_customer: bool | None = None
    discounts: list[str] | None = None
    restrictions: list[str] | None = None


class AccountResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['FOUND', 'NOT_FOUND']
    source: Literal['BOSS_MOCK'] | None = None
    source_time: datetime | None = None
    payload: AccountFacts | None = None


class AcceptanceResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['NOT_FOUND','PROCESSING','SUCCESS','FAILED']
    external_request_id: UUID | None = None
    external_order_id: UUID | None = None
    reason: str | None = None


async def request(method, path, payload=None):
    cfg = Settings()
    try:
        async with httpx.AsyncClient(base_url=cfg.boss_url, timeout=2, trust_env=False) as c:
            response = await c.request(method, path, json=payload, headers={'Authorization': 'Bearer '+cfg.boss_token.get_secret_value()})
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise DomainError('BOSS_TIMEOUT', '模拟外部系统响应超时，请核查后重试', 504) from None
    except (httpx.HTTPError, ValueError):
        raise DomainError('BOSS_UNAVAILABLE', '模拟外部系统暂不可用', 502) from None


async def query_account(number, account_type='MOBILE'):
    try:
        result = AccountResult.model_validate(await request('POST', '/mock/v1/account-query', {'number': number, 'account_type': account_type}))
        if result.status == 'FOUND' and (result.payload is None or result.source_time is None or result.source is None):
            raise ValueError('Missing source facts')
        return result
    except (ValidationError, ValueError):
        raise DomainError('BOSS_INVALID_RESPONSE', '外部资料结构不完整，需人工核查', 502) from None


async def acceptance_request(method, path, payload=None):
    try:
        result = AcceptanceResult.model_validate(await request(method, path, payload))
        if result.status != 'NOT_FOUND' and (result.external_request_id is None or result.external_order_id is None): raise ValueError('Missing external identity')
        return result.model_dump(mode='json')
    except ValueError:
        raise DomainError('BOSS_INVALID_RESPONSE', '受理返回不完整，需核对原请求号', 502) from None


async def submit(payload):
    return await acceptance_request('POST', '/mock/v1/acceptances', payload)


async def lookup(request_id):
    return await acceptance_request('GET', f'/mock/v1/acceptances/by-request/{request_id}')


class PaymentResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['NOT_FOUND', 'SUCCESS', 'FAILED']
    simulated: Literal[True]
    external_request_id: UUID | None = None
    external_payment_id: UUID | None = None
    order_id: UUID | None = None
    amount: Decimal | None = None
    method: Literal['CASH', 'CARD', 'WECHAT', 'ALIPAY'] | None = None


async def payment_request(method, path, payload=None):
    try:
        return PaymentResult.model_validate(await request(method, path, payload)).model_dump(mode='json')
    except ValueError:
        raise DomainError('BOSS_INVALID_RESPONSE', '支付返回不完整，需按原请求号核对', 502) from None


class RefundResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['NOT_FOUND', 'SUCCESS', 'FAILED']
    simulated: Literal[True]
    external_request_id: UUID | None = None
    external_refund_id: UUID | None = None
    external_payment_id: UUID | None = None
    amount: Decimal | None = None


async def refund_request(method, path, payload=None):
    try:
        return RefundResult.model_validate(await request(method, path, payload)).model_dump(mode='json')
    except ValueError:
        raise DomainError('BOSS_INVALID_RESPONSE', '退款返回不完整，需按原请求号核对', 502) from None


class ReversalResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['NOT_FOUND','SUCCESS','FAILED']
    simulated: Literal[True]
    external_request_id: UUID | None = None
    external_reversal_id: UUID | None = None
    original_request_id: UUID | None = None
    reason: str | None = None


async def reversal_request(method, path, payload=None):
    try:
        return ReversalResult.model_validate(await request(method, path, payload)).model_dump(mode='json')
    except ValueError:
        raise DomainError('BOSS_INVALID_RESPONSE', '冲正返回不完整，须按原请求号核查', 502) from None
