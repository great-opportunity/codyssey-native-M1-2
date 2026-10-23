"""저장소 계층.

라우터·서비스는 Firestore를 직접 만지지 않고 이 파일의 Store만 사용한다.
- FirestoreStore: 실제 서비스용 (Firebase Firestore)
- MemoryStore: 키 없이 로컬에서 기능을 확인할 때 쓰는 임시 저장소 (서버 끄면 사라짐)

컬렉션 구조
- data:           {date: "YYYY-MM-DD", value: float, memo: str, created_at, updated_at}
- conversations:  {title, messages: [{role, content, created_at}], created_at, updated_at}
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import settings

DATA = "data"
CONVERSATIONS = "conversations"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self) -> None:
        self._cols: dict[str, dict[str, dict]] = {DATA: {}, CONVERSATIONS: {}}

    def list(self, col: str) -> list[dict]:
        return [{"id": k, **v} for k, v in self._cols[col].items()]

    def get(self, col: str, doc_id: str) -> dict | None:
        doc = self._cols[col].get(doc_id)
        return {"id": doc_id, **doc} if doc else None

    def add(self, col: str, data: dict) -> str:
        doc_id = uuid.uuid4().hex[:20]
        self._cols[col][doc_id] = dict(data)
        return doc_id

    def update(self, col: str, doc_id: str, data: dict) -> bool:
        if doc_id not in self._cols[col]:
            return False
        self._cols[col][doc_id].update(data)
        return True

    def delete(self, col: str, doc_id: str) -> bool:
        return self._cols[col].pop(doc_id, None) is not None


class FirestoreStore:
    def __init__(self) -> None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
            cred = credentials.Certificate(json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON))
        elif settings.FIREBASE_SERVICE_ACCOUNT_PATH:
            cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
        else:
            raise RuntimeError(
                "Firestore 키가 없습니다. FIREBASE_SERVICE_ACCOUNT_JSON 또는 "
                "FIREBASE_SERVICE_ACCOUNT_PATH를 설정하거나, 로컬 테스트라면 STORAGE=memory로 실행하세요."
            )
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        self._db = firestore.client()

    def list(self, col: str) -> list[dict]:
        return [{"id": d.id, **d.to_dict()} for d in self._db.collection(col).stream()]

    def get(self, col: str, doc_id: str) -> dict | None:
        snap = self._db.collection(col).document(doc_id).get()
        return {"id": snap.id, **snap.to_dict()} if snap.exists else None

    def add(self, col: str, data: dict) -> str:
        _, ref = self._db.collection(col).add(data)
        return ref.id

    def update(self, col: str, doc_id: str, data: dict) -> bool:
        ref = self._db.collection(col).document(doc_id)
        if not ref.get().exists:
            return False
        ref.update(data)
        return True

    def delete(self, col: str, doc_id: str) -> bool:
        ref = self._db.collection(col).document(doc_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True


_store: Any = None


def get_store() -> MemoryStore | FirestoreStore:
    """앱 전체에서 하나의 저장소 객체를 같이 쓴다."""
    global _store
    if _store is None:
        if settings.STORAGE == "memory":
            _store = MemoryStore()
            _seed_memory(_store)
        else:
            _store = FirestoreStore()
    return _store


def _seed_memory(store: MemoryStore) -> None:
    """메모리 모드에선 서버가 켜질 때 CSV 데이터를 미리 채워 둔다."""
    import csv
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "btc_daily.csv"
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            store.add(DATA, {"date": row["date"], "value": float(row["value"]),
                             "memo": row["memo"], "created_at": now_iso(), "updated_at": now_iso()})
