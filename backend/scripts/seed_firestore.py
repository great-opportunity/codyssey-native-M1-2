"""data/btc_daily.csv(200일)를 Firestore data 컬렉션에 한 번 올리는 스크립트.

실행 (backend 폴더에서): .venv/bin/python -m scripts.seed_firestore
이미 같은 날짜가 있으면 건너뛴다 (여러 번 실행해도 중복 없음).
"""
import csv
from pathlib import Path

from app.db import DATA, FirestoreStore, now_iso


def main() -> None:
    store = FirestoreStore()
    existing = {d["date"] for d in store.list(DATA)}
    path = Path(__file__).resolve().parent.parent / "data" / "btc_daily.csv"
    added = 0
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["date"] in existing:
                continue
            store.add(DATA, {"date": row["date"], "value": float(row["value"]), "memo": row["memo"],
                             "created_at": now_iso(), "updated_at": now_iso()})
            added += 1
    print(f"추가 {added}개 / 기존 {len(existing)}개")


if __name__ == "__main__":
    main()
