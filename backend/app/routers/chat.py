from fastapi import APIRouter

from ..schemas import ChatRequest, ChatResponse
from ..services.chat_service import chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse,
             summary="AI 채팅 (데이터 요약 주입 + 도구 호출 + 대화 자동 저장)")
def post_chat(body: ChatRequest):
    return chat(body.message, body.conversation_id)
