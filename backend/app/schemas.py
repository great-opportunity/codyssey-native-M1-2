"""Pydantic 스키마: 요청이 들어오면 FastAPI가 여기 정의대로 자동 검증한다.

형식이 틀리면(날짜가 아니거나, 값이 음수거나, 메모가 너무 길면) 라우터 코드까지 가지도 않고
422 에러와 함께 '어느 필드가 왜 틀렸는지'를 돌려준다.
"""
import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------- 데이터 ----------
class DataCreate(BaseModel):
    date: dt.date = Field(..., description="날짜 (YYYY-MM-DD)", examples=["2026-10-21"])
    value: float = Field(..., gt=0, le=10_000_000, allow_inf_nan=False,
                         description="값 (BTC 종가, USD)", examples=[84000.5])
    memo: str = Field("", max_length=200, description="메모 (선택, 200자 이하)")

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, v: str) -> str:
        return v.strip()


class DataUpdate(BaseModel):
    """수정은 바꾸고 싶은 필드만 보내면 된다. 단, 최소 1개는 있어야 한다."""
    date: dt.date | None = None
    value: float | None = Field(None, gt=0, le=10_000_000, allow_inf_nan=False)
    memo: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def at_least_one(self):
        if self.date is None and self.value is None and self.memo is None:
            raise ValueError("date, value, memo 중 최소 1개는 보내야 합니다.")
        return self


class DataItem(BaseModel):
    id: str
    date: str
    value: float
    memo: str = ""


class Summary(BaseModel):
    dataset: str
    unit: str
    count: int
    start_date: str | None
    end_date: str | None
    latest_value: float | None
    mean: float | None
    max: float | None
    max_date: str | None
    min: float | None
    min_date: str | None
    change_pct: float | None = Field(None, description="기간 전체 변화율(%)")
    trend: Literal["증가", "감소", "유지", "데이터 부족"]
    trend_detail: str
    volatility_30d: float | None = Field(None, description="최근 30일 일간 변동률 표준편차(%)")


# ---------- 대화 ----------
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)
    created_at: str | None = None


class ConversationCreate(BaseModel):
    title: str = Field("", max_length=100, description="비우면 첫 질문으로 자동 생성")
    messages: list[Message] = Field(..., min_length=1, max_length=200)


class ConversationListItem(BaseModel):
    """목록 응답에는 messages 전체를 넣지 않는다 (가볍게). 전체는 GET /api/conversations/{id}."""
    id: str
    title: str
    message_count: int
    preview: str
    created_at: str
    updated_at: str


class Conversation(BaseModel):
    id: str
    title: str
    messages: list[Message]
    created_at: str
    updated_at: str


# ---------- 채팅 ----------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, examples=["최근 일주일 추세 어때?"])
    conversation_id: str | None = Field(None, description="이어서 대화할 때만 보냄. 없으면 새 대화 생성")

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("빈 메시지는 보낼 수 없습니다.")
        return v


class ToolCallLog(BaseModel):
    name: str
    arguments: dict


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    summary: Summary
    tool_calls: list[ToolCallLog] = []
