"""conversations 컬렉션 로직."""
from fastapi import HTTPException

from ..db import CONVERSATIONS, get_store, now_iso


def _title_from(text: str) -> str:
    text = " ".join(text.split())
    return text[:30] + ("…" if len(text) > 30 else "")


def list_conversations() -> list[dict]:
    items = []
    for d in get_store().list(CONVERSATIONS):
        msgs = d.get("messages", [])
        items.append({
            "id": d["id"],
            "title": d.get("title", ""),
            "message_count": len(msgs),
            "preview": msgs[-1]["content"][:60] if msgs else "",
            "created_at": d["created_at"],
            "updated_at": d["updated_at"],
        })
    return sorted(items, key=lambda i: i["updated_at"], reverse=True)


def get_conversation(conv_id: str) -> dict:
    doc = get_store().get(CONVERSATIONS, conv_id)
    if not doc:
        raise HTTPException(404, "해당 id의 대화가 없습니다.")
    return doc


def create_conversation(title: str, messages: list[dict]) -> dict:
    ts = now_iso()
    msgs = [{**m, "created_at": m.get("created_at") or ts} for m in messages]
    first_user = next((m["content"] for m in msgs if m["role"] == "user"), msgs[0]["content"])
    doc = {"title": title.strip() or _title_from(first_user), "messages": msgs,
           "created_at": ts, "updated_at": ts}
    conv_id = get_store().add(CONVERSATIONS, doc)
    return {"id": conv_id, **doc}


def append_messages(conv_id: str, new_messages: list[dict]) -> None:
    doc = get_conversation(conv_id)
    get_store().update(CONVERSATIONS, conv_id, {
        "messages": doc.get("messages", []) + new_messages,
        "updated_at": now_iso(),
    })


def delete_conversation(conv_id: str) -> None:
    if not get_store().delete(CONVERSATIONS, conv_id):
        raise HTTPException(404, "해당 id의 대화가 없습니다.")
