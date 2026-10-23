from fastapi import APIRouter, Response

from ..schemas import Conversation, ConversationCreate, ConversationListItem
from ..services import conversation_service as svc

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=Conversation, status_code=201, summary="대화 저장")
def create_conversation(body: ConversationCreate):
    return svc.create_conversation(body.title, [m.model_dump() for m in body.messages])


@router.get("", response_model=list[ConversationListItem],
            summary="대화 목록 조회 (messages 제외, 최근 수정순)")
def list_conversations():
    return svc.list_conversations()


@router.get("/{conv_id}", response_model=Conversation, summary="특정 대화 불러오기 (전체 messages 포함)")
def get_conversation(conv_id: str):
    return svc.get_conversation(conv_id)


@router.delete("/{conv_id}", status_code=204, summary="대화 삭제")
def delete_conversation(conv_id: str):
    svc.delete_conversation(conv_id)
    return Response(status_code=204)
