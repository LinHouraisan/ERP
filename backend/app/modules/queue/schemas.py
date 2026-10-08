from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Literal['PLAN', 'FAULT', 'OTHER']


class TicketAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(default='', max_length=2000)
    category: Literal['PLAN', 'FAULT', 'OTHER'] | None = None


def ticket_view(row):
    return {k: getattr(row, k) for k in ('id', 'ticket_number', 'category', 'window_id', 'service_id', 'status', 'queued_at', 'called_at', 'cumulative_wait_seconds', 'round_wait_seconds', 'updated_at')}


def public_ticket(row, window=None):
    return {'ticket_number': row.ticket_number, 'category': row.category, 'window': window, 'status': row.status, 'updated_at': row.updated_at}
