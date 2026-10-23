"""data 컬렉션 CRUD 로직. 라우터는 HTTP만, 실제 일은 여기서."""
from fastapi import HTTPException

from ..db import DATA, get_store, now_iso
from ..schemas import DataCreate, DataUpdate


def _public(doc: dict) -> dict:
    return {"id": doc["id"], "date": doc["date"], "value": doc["value"], "memo": doc.get("memo", "")}


def list_data(start: str | None = None, end: str | None = None) -> list[dict]:
    items = [_public(d) for d in get_store().list(DATA)]
    if start:
        items = [i for i in items if i["date"] >= start]
    if end:
        items = [i for i in items if i["date"] <= end]
    return sorted(items, key=lambda i: i["date"])


def _ensure_unique_date(date: str, exclude_id: str | None = None) -> None:
    # 시계열이라 하루에 값 하나만 허용 (같은 날짜 중복 저장 방지)
    for d in get_store().list(DATA):
        if d["date"] == date and d["id"] != exclude_id:
            raise HTTPException(409, f"{date} 데이터가 이미 있습니다. 수정(PUT)을 사용하세요.")


def create_data(body: DataCreate) -> dict:
    date = body.date.isoformat()
    _ensure_unique_date(date)
    doc = {"date": date, "value": body.value, "memo": body.memo,
           "created_at": now_iso(), "updated_at": now_iso()}
    doc_id = get_store().add(DATA, doc)
    return _public({"id": doc_id, **doc})


def update_data(doc_id: str, body: DataUpdate) -> dict:
    changes = body.model_dump(exclude_none=True)
    if "date" in changes:
        changes["date"] = changes["date"].isoformat()
        _ensure_unique_date(changes["date"], exclude_id=doc_id)
    if "memo" in changes:
        changes["memo"] = changes["memo"].strip()
    changes["updated_at"] = now_iso()
    if not get_store().update(DATA, doc_id, changes):
        raise HTTPException(404, "해당 id의 데이터가 없습니다.")
    return _public(get_store().get(DATA, doc_id))


def delete_data(doc_id: str) -> None:
    if not get_store().delete(DATA, doc_id):
        raise HTTPException(404, "해당 id의 데이터가 없습니다.")
