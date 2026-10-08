from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    token: str = Field(min_length=32, max_length=100)
    score: int = Field(ge=1, le=5, strict=True)
    tags: list[Literal['等待时间','解释清晰度','问题解决','办理体验']] = Field(default_factory=list, max_length=4)
    comment: str = Field(default='', max_length=2000)
