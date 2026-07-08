"""
gtrends.py — Google Trends через pytrends (раздел 3.4, Фаза 4).

Для каждого active-тренда берётся первый ключ из wb_keywords и запрашивается
RU-динамика за 12 мес. (interest_over_time). Месячные значения (среднее
индекса 0–100 по месяцу) → signals: level='social_search', source='pytrends'.
trends.collect_metrics берёт отношение двух последних значений как S-рост.

Кэш (rate limit Google суров): сырой ответ → wb_metrics (kind='pytrends');
повторный запрос того же ключа в течение PYTRENDS_CACHE_DAYS суток читается
из кэша и в сеть не ходит. MOCK=1 → только кэш.

CLI:
    python gtrends.py collect                    # active-тренды
    python gtrends.py collect --all              # + candidate
    python gtrends.py collect --trend <trend_id>
    python gtrends.py related --trend <trend_id> # related queries (обзор)
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

import config
import db


def _mock() -> bool:
    return os.environ.get("MOCK", "0") == "1"


# ─── Кэш в wb_metrics ────────────────────────────────────────────────────────

def _cache_get(conn, key: str, kind: str, max_age_days: int):
    row = conn.execute(
        """SELECT payload, date FROM wb_metrics WHERE key=? AND kind=?
           ORDER BY date DESC LIMIT 1""", (key, kind)).fetchone()
    if not row:
        return None
    if _mock():
        return json.loads(row["payload"])  # MOCK: любой возраст
    age = (date.today() - date.fromisoformat(row["date"])).days
    return json.loads(row["payload"]) if age < max_age_days else None


def _cache_put(conn, key: str, kind: str, payload):
    conn.execute(
        """INSERT INTO wb_metrics (key, kind, date, payload) VALUES (?,?,?,?)
           ON CONFLICT(key, kind, date) DO UPDATE SET payload=excluded.payload""",
        (key, kind, date.today().isoformat(),
         json.dumps(payload, ensure_ascii=False)))
    conn.commit()


# ─── pytrends ────────────────────────────────────────────────────────────────

_pytrends = None


def _client():
    global _pytrends
    if _pytrends is None:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            sys.exit("❌ pip install pytrends")
        _pytrends = TrendReq(hl="ru-RU", tz=180, timeout=(10, 30), retries=2,
                             backoff_factor=2)
    return _pytrends


def fetch_interest(conn, keyword: str) -> list[dict] | None:
    """[{'date': 'YYYY-MM-DD', 'value': int}, …] по неделям, 12 мес., geo=RU."""
    cached = _cache_get(conn, keyword, "pytrends", config.PYTRENDS_CACHE_DAYS)
    if cached is not None:
        return cached
    if _mock():
        return None  # в MOCK сети нет

    py = _client()
    try:
        py.build_payload([keyword], geo=config.PYTRENDS_GEO,
                         timeframe=config.PYTRENDS_TIMEFRAME)
        df = py.interest_over_time()
    except Exception as e:
        print(f"    ! pytrends '{keyword}': {e}")
        return None
    time.sleep(config.PYTRENDS_DELAY_SEC)
    if df is None or df.empty or keyword not in df.columns:
        _cache_put(conn, keyword, "pytrends", [])
        return []
    data = [{"date": idx.date().isoformat(), "value": int(v)}
            for idx, v in df[keyword].items()]
    _cache_put(conn, keyword, "pytrends", data)
    return data


def fetch_related(conn, keyword: str) -> dict | None:
    cached = _cache_get(conn, keyword, "pytrends_related", config.PYTRENDS_CACHE_DAYS)
    if cached is not None:
        return cached
    if _mock():
        return None
    py = _client()
    try:
        py.build_payload([keyword], geo=config.PYTRENDS_GEO,
                         timeframe=config.PYTRENDS_TIMEFRAME)
        rq = py.related_queries().get(keyword) or {}
    except Exception as e:
        print(f"    ! related '{keyword}': {e}")
        return None
    time.sleep(config.PYTRENDS_DELAY_SEC)
    out = {}
    for kind_, df in rq.items():
        out[kind_] = df.to_dict("records") if df is not None else []
    _cache_put(conn, keyword, "pytrends_related", out)
    return out


# ─── Сигналы ─────────────────────────────────────────────────────────────────

def monthly_series(points: list[dict]) -> list[tuple[str, float]]:
    """Недельные точки → [(последний день месяца в данных, среднее)], по возрастанию."""
    by_month: dict[str, list] = {}
    last_day: dict[str, str] = {}
    for p in points:
        m = p["date"][:7]
        by_month.setdefault(m, []).append(p["value"])
        last_day[m] = max(last_day.get(m, ""), p["date"])
    return [(last_day[m], sum(v) / len(v)) for m, v in sorted(by_month.items())]


def collect(conn, statuses: tuple, only_trend: str | None) -> int:
    q = "SELECT trend_id, name_ru, wb_keywords FROM trends WHERE status IN (%s)" % \
        ",".join("?" * len(statuses))
    params: list = list(statuses)
    if only_trend:
        q += " AND trend_id=?"
        params.append(only_trend)
    trends = conn.execute(q, params).fetchall()
    print(f"Трендов: {len(trends)}, geo={config.PYTRENDS_GEO}, "
          f"{config.PYTRENDS_TIMEFRAME}" + (" [MOCK]" if _mock() else ""))

    n_signals = 0
    for i, t in enumerate(trends, 1):
        keywords = json.loads(t["wb_keywords"] or "[]")
        if not keywords:
            print(f"  [{i}/{len(trends)}] {t['trend_id']}: нет wb_keywords — пропуск")
            continue
        kw = keywords[0]
        points = fetch_interest(conn, kw)
        if points is None:
            print(f"  [{i}/{len(trends)}] {t['trend_id']} '{kw}': нет данных "
                  "(ошибка/MOCK без кэша)")
            continue
        months = monthly_series(points)
        conn.execute(
            """DELETE FROM signals WHERE trend_id=? AND level='social_search'
               AND source='pytrends'""", (t["trend_id"],))
        for d, val in months:
            conn.execute(
                """INSERT INTO signals (trend_id, level, source, date, value, url)
                   VALUES (?,'social_search','pytrends',?,?,?)""",
                (t["trend_id"], d, val, f"gtrends:{kw}"))
        conn.commit()
        n_signals += len(months)
        trend_txt = ""
        if len(months) >= 2 and months[-2][1]:
            trend_txt = f", посл. м/м ×{months[-1][1] / months[-2][1]:.2f}"
        print(f"  [{i}/{len(trends)}] {t['trend_id']:40s} '{kw}': "
              f"{len(months)} мес.{trend_txt}")
    return n_signals


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["collect", "related"])
    ap.add_argument("--all", action="store_true", help="+ candidate-тренды")
    ap.add_argument("--trend", default=None)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    conn = db.init_db(args.db or config.DB_PATH)

    statuses = ("active", "candidate") if args.all else ("active",)
    if args.command == "collect":
        n = collect(conn, statuses, args.trend)
        print(f"\n✅ Сигналов social_search: {n}")
    elif args.command == "related":
        if not args.trend:
            sys.exit("--trend обязателен для related")
        t = conn.execute("SELECT wb_keywords FROM trends WHERE trend_id=?",
                         (args.trend,)).fetchone()
        if not t:
            sys.exit(f"нет тренда {args.trend}")
        kw = (json.loads(t["wb_keywords"] or "[]") or [""])[0]
        rel = fetch_related(conn, kw)
        print(json.dumps(rel, ensure_ascii=False, indent=2))
