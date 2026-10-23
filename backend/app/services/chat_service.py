"""AI 채팅: 컨텍스트 주입 + 도구 호출(Function Calling).

흐름
1) 데이터 요약 조회 (GET /api/data/summary 와 같은 함수)
2) 요약을 시스템 프롬프트에 끼워 넣기  ← 컨텍스트 주입
3) GPT 호출. 요약만으로 부족하면 GPT가 도구(특정 기간 데이터, 상세 통계 등)를 직접 요청
4) 질문·답변을 conversations에 자동 저장
"""
import json
from datetime import date

from fastapi import HTTPException
from openai import OpenAI, OpenAIError

from ..config import settings
from ..db import now_iso
from . import conversation_service as conv
from .data_service import list_data
from .summary import build_statistics, build_summary, summary_to_prompt

MAX_HISTORY = 10      # 이전 대화는 최근 10개 메시지만 함께 보냄 (토큰 절약)
MAX_TOOL_ROUNDS = 3   # 도구 호출 반복 상한 (무한루프·과금 방지)

SYSTEM_TEMPLATE = """너는 사용자의 시계열 데이터를 잘 아는 데이터 분석 비서야.
오늘 날짜: {today}

[사용자 데이터 요약]
{summary}

규칙
- 위 요약과 도구 결과에 있는 숫자만 근거로 답해. 모르는 수치를 지어내지 마.
- 특정 날짜·기간의 값이 필요하면 get_data_range, 이동평균·월별·최대 상승일 같은 상세 지표가 필요하면 get_statistics 도구를 호출해.
- 이전 대화 목록이 필요하면 list_conversations 도구를 호출해.
- 투자 권유는 하지 말고, 데이터 해석 위주로 한국어로 간결하게 답해. 숫자에는 단위({unit})를 붙여."""

TOOLS = [
    {"type": "function", "function": {
        "name": "get_data_summary",
        "description": "저장된 데이터 전체의 최신 요약(기간, 개수, 평균/최대/최소, 추세)을 다시 조회한다.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_data_range",
        "description": "특정 기간의 일별 데이터(date, value, memo)를 조회한다. 특정 날짜 값, 기간 비교 질문에 사용.",
        "parameters": {"type": "object", "properties": {
            "start_date": {"type": "string", "description": "시작일 YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "종료일 YYYY-MM-DD"},
        }, "required": ["start_date", "end_date"]},
    }},
    {"type": "function", "function": {
        "name": "get_statistics",
        "description": "상세 통계: 월별 평균, 최대 상승일/하락일, 상승·하락 일수, 최근 7일 이동평균.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "list_conversations",
        "description": "저장된 이전 대화 목록(제목, 미리보기)을 조회한다.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


def run_tool(name: str, args: dict) -> dict:
    """GPT가 요청한 도구를 실제로 실행. MCP 서버에서도 이 함수를 그대로 재사용한다."""
    if name == "get_data_summary":
        return build_summary(list_data())
    if name == "get_data_range":
        rows = list_data(args.get("start_date"), args.get("end_date"))
        return {"count": len(rows), "rows": rows[:120]}  # 너무 길면 잘라서 토큰 보호
    if name == "get_statistics":
        stats = build_statistics(list_data())
        stats["recent_series"] = stats.pop("series")[-14:]
        return stats
    if name == "list_conversations":
        return {"conversations": conv.list_conversations()[:20]}
    return {"error": f"알 수 없는 도구: {name}"}


def chat(message: str, conversation_id: str | None) -> dict:
    if not settings.OPENAI_API_KEY:
        raise HTTPException(503, "서버에 OPENAI_API_KEY가 설정되지 않았습니다.")

    # 1) 요약 조회 → 2) 시스템 프롬프트에 주입
    summary = build_summary(list_data())
    system_prompt = SYSTEM_TEMPLATE.format(
        today=date.today().isoformat(), summary=summary_to_prompt(summary), unit=summary["unit"])

    history = []
    if conversation_id:
        history = conv.get_conversation(conversation_id).get("messages", [])[-MAX_HISTORY:]

    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": message})

    # 3) GPT 호출 (+ 필요하면 도구 호출 반복)
    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=40)
    tool_log = []
    try:
        for _ in range(MAX_TOOL_ROUNDS + 1):
            res = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                tools=TOOLS,
                max_completion_tokens=settings.OPENAI_MAX_TOKENS,
            )
            msg = res.choices[0].message
            if not msg.tool_calls:
                break
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [c.model_dump() for c in msg.tool_calls]})
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                tool_log.append({"name": call.function.name, "arguments": args})
                result = run_tool(call.function.name, args)
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, ensure_ascii=False)})
    except OpenAIError as e:
        raise HTTPException(502, f"AI 응답 생성 중 오류: {e.__class__.__name__}") from e

    reply = (msg.content or "").strip() or "답변을 만들지 못했어요. 질문을 조금 바꿔서 다시 시도해 주세요."

    # 4) 대화 자동 저장
    ts = now_iso()
    new_msgs = [{"role": "user", "content": message, "created_at": ts},
                {"role": "assistant", "content": reply, "created_at": ts}]
    if conversation_id:
        conv.append_messages(conversation_id, new_msgs)
    else:
        conversation_id = conv.create_conversation("", new_msgs)["id"]

    return {"reply": reply, "conversation_id": conversation_id, "summary": summary, "tool_calls": tool_log}
