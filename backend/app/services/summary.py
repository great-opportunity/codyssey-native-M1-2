"""시계열 분석: 저장된 데이터 → 요약 정보(summary)·통계(statistics).

요약은 두 곳에서 쓰인다.
1) GET /api/data/summary  → 화면 상단 요약 카드
2) POST /api/chat         → 시스템 프롬프트에 그대로 주입 (AI가 '내 데이터'를 알게 되는 지점)
"""
import statistics as st

from ..config import settings

# 최근 7일 평균이 그 전 7일 평균보다 ±2% 넘게 달라지면 증가/감소, 아니면 유지
TREND_WINDOW = 7
TREND_THRESHOLD_PCT = 2.0


def _sorted(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: x["date"])


def _daily_returns(values: list[float]) -> list[float]:
    return [(b / a - 1) * 100 for a, b in zip(values, values[1:]) if a]


def build_summary(items: list[dict]) -> dict:
    rows = _sorted(items)
    values = [r["value"] for r in rows]
    base = {"dataset": settings.DATASET_NAME, "unit": settings.DATASET_UNIT, "count": len(rows)}

    if not rows:
        return {**base, "start_date": None, "end_date": None, "latest_value": None, "mean": None,
                "max": None, "max_date": None, "min": None, "min_date": None, "change_pct": None,
                "trend": "데이터 부족", "trend_detail": "저장된 데이터가 없습니다.", "volatility_30d": None}

    max_row = max(rows, key=lambda r: r["value"])
    min_row = min(rows, key=lambda r: r["value"])

    # 최근 추세: 최근 7일 평균 vs 직전 7일 평균
    if len(values) >= TREND_WINDOW * 2:
        recent = st.mean(values[-TREND_WINDOW:])
        prev = st.mean(values[-TREND_WINDOW * 2:-TREND_WINDOW])
        diff = (recent / prev - 1) * 100
        trend = "증가" if diff > TREND_THRESHOLD_PCT else "감소" if diff < -TREND_THRESHOLD_PCT else "유지"
        trend_detail = (f"최근 {TREND_WINDOW}일 평균 {recent:,.2f}가 직전 {TREND_WINDOW}일 평균 "
                        f"{prev:,.2f}보다 {diff:+.2f}% → {trend}")
    else:
        trend, trend_detail = "데이터 부족", f"추세 판단에는 최소 {TREND_WINDOW * 2}개가 필요합니다."

    returns_30 = _daily_returns(values[-31:])
    return {
        **base,
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "latest_value": round(values[-1], 2),
        "mean": round(st.mean(values), 2),
        "max": round(max_row["value"], 2),
        "max_date": max_row["date"],
        "min": round(min_row["value"], 2),
        "min_date": min_row["date"],
        "change_pct": round((values[-1] / values[0] - 1) * 100, 2) if values[0] else None,
        "trend": trend,
        "trend_detail": trend_detail,
        "volatility_30d": round(st.stdev(returns_30), 2) if len(returns_30) >= 2 else None,
    }


def summary_to_prompt(s: dict) -> str:
    """요약 dict를 AI가 읽기 좋은 문장 묶음으로 바꾼다 (시스템 프롬프트에 들어갈 부분)."""
    if not s["count"]:
        return "- 저장된 데이터가 아직 없음"
    u = s["unit"]
    return "\n".join([
        f"- 데이터: {s['dataset']}",
        f"- 기간: {s['start_date']} ~ {s['end_date']} (총 {s['count']}개)",
        f"- 최신 값({s['end_date']}): {s['latest_value']:,} {u}",
        f"- 평균: {s['mean']:,} {u}",
        f"- 최고: {s['max']:,} {u} ({s['max_date']}) / 최저: {s['min']:,} {u} ({s['min_date']})",
        f"- 기간 전체 변화율: {s['change_pct']:+}%",
        f"- 최근 추세: {s['trend']} — {s['trend_detail']}",
        f"- 최근 30일 일간 변동성(표준편차): {s['volatility_30d']}%",
    ])


def _in_period(date: str, start: str | None, end: str | None) -> bool:
    return (not start or date >= start) and (not end or date <= end)


def with_returns(items: list[dict], start: str | None = None, end: str | None = None) -> list[dict]:
    """기간 안의 일별 데이터에 전일 대비 변동률(return_pct)을 붙인다.

    전일 값은 기간 밖에 있어도 쓴다 (기간 첫날의 변동률도 구하려고).
    """
    rows = _sorted(items)
    out = []
    for i, r in enumerate(rows):
        if not _in_period(r["date"], start, end):
            continue
        prev = rows[i - 1]["value"] if i else None
        out.append({**r, "return_pct": round((r["value"] / prev - 1) * 100, 2) if prev else None})
    return out


def build_period_stats(items: list[dict], start: str | None = None, end: str | None = None) -> dict:
    """AI 도구용 기간 통계. 기간을 비우면 전체. 일별 목록은 넣지 않는다 (그건 get_data_range 몫)."""
    rows = with_returns(items, start, end)
    if not rows:
        return {"period": {"start": start, "end": end}, "count": 0}

    values = [r["value"] for r in rows]
    rets = [r for r in rows if r["return_pct"] is not None]
    max_row = max(rows, key=lambda r: r["value"])
    min_row = min(rows, key=lambda r: r["value"])
    best = max(rets, key=lambda r: r["return_pct"]) if rets else None
    worst = min(rets, key=lambda r: r["return_pct"]) if rets else None

    months: dict[str, list[float]] = {}
    for r in rows:
        months.setdefault(r["date"][:7], []).append(r["value"])

    return {
        "period": {"start": rows[0]["date"], "end": rows[-1]["date"]},
        "count": len(rows),
        "first_value": values[0],
        "last_value": values[-1],
        "change_pct": round((values[-1] / values[0] - 1) * 100, 2) if values[0] else None,
        "mean": round(st.mean(values), 2),
        "max": {"date": max_row["date"], "value": max_row["value"]},
        "min": {"date": min_row["date"], "value": min_row["value"]},
        "best_day": {"date": best["date"], "return_pct": best["return_pct"]} if best else None,
        "worst_day": {"date": worst["date"], "return_pct": worst["return_pct"]} if worst else None,
        "up_days": sum(1 for r in rets if r["return_pct"] > 0),
        "down_days": sum(1 for r in rets if r["return_pct"] < 0),
        "volatility_pct": round(st.stdev(r["return_pct"] for r in rets), 2) if len(rets) >= 2 else None,
        "monthly": [{"month": m, "mean": round(st.mean(v), 2), "count": len(v)} for m, v in months.items()],
    }


def build_statistics(items: list[dict]) -> dict:
    """[보너스] 요약보다 자세한 지표: 7일 이동평균, 일간 변동률, 최대 상승/하락일, 월별 평균."""
    rows = _sorted(items)
    values = [r["value"] for r in rows]
    if len(rows) < 2:
        return {"count": len(rows), "series": [], "monthly": [], "best_day": None, "worst_day": None,
                "up_days": 0, "down_days": 0}

    series = []
    for i, r in enumerate(rows):
        window = values[max(0, i - 6): i + 1]
        series.append({
            "date": r["date"],
            "value": r["value"],
            "ma7": round(st.mean(window), 2) if len(window) == 7 else None,
            "return_pct": round((values[i] / values[i - 1] - 1) * 100, 2) if i and values[i - 1] else None,
        })

    with_ret = [s for s in series if s["return_pct"] is not None]
    best = max(with_ret, key=lambda s: s["return_pct"])
    worst = min(with_ret, key=lambda s: s["return_pct"])

    months: dict[str, list[float]] = {}
    for r in rows:
        months.setdefault(r["date"][:7], []).append(r["value"])

    return {
        "count": len(rows),
        "series": series,
        "monthly": [{"month": m, "mean": round(st.mean(v), 2), "count": len(v)} for m, v in months.items()],
        "best_day": {"date": best["date"], "return_pct": best["return_pct"]},
        "worst_day": {"date": worst["date"], "return_pct": worst["return_pct"]},
        "up_days": sum(1 for s in with_ret if s["return_pct"] > 0),
        "down_days": sum(1 for s in with_ret if s["return_pct"] < 0),
    }
