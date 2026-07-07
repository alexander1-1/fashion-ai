"""
mpstats_client.py — Слой 4: валидация трендов через MPStats API (раздел 5, Фаза 3).

Эндпоинты (сверены с https://mpstats.io/integrations/analytics-wb/ и проверены
живыми вызовами 2026-07-07; база — config.MPSTATS_BASE = api/analytics/v1/wb/):

  GET  keywords/frequency?keyword=X
       → [{"date": "2026-07-06", "frequency": 524}, …] — недельная история с 2022 г.
  POST search/items?path=<фраза>&d1&d2  body={startRow,endRow,filterModel,sortModel}
       → {"total": N, "data": [{id, name, revenue, sales, final_price, …}]}

Токен: .env → MPSTATS_TOKEN, заголовок X-Mpstats-TOKEN.

Кэш (п. 5 инструкции, лимиты API конечны): каждый ответ → wb_metrics
(key, kind, date, payload). Повторный вызов того же ключа в тот же день
читается из кэша и НЕ тратит лимит. MOCK=1 → только кэш (последняя запись
за любую дату), сеть запрещена — для тестов и разработки.

Сигналы для тренд-движка (trends.py их уже читает, менять его не нужно):
  wb_query  source='mpstats'             value = частотность за 30-дн. окно,
                                         13 окон от самой свежей точки данных
  wb_sales  source='mpstats:cards'       value = карточек в выдаче по фразе
  wb_sales  source='mpstats:top_revenue' value = выручка топ-20 выдачи, руб/30дн

CLI:
    python mpstats_client.py limits                     # остаток лимита API
    python mpstats_client.py collect                    # Q+C для active-трендов
    python mpstats_client.py collect --all              # для всех трендов
    python mpstats_client.py collect --trend <trend_id> # точечно
"""

import argparse
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

import config
import db


# ─── Токен и окружение ───────────────────────────────────────────────────────

def load_env(path: str | Path = ".env") -> None:
    """Мини-загрузчик .env: не тянем python-dotenv ради одного файла."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _token() -> str:
    load_env()
    tok = os.environ.get("MPSTATS_TOKEN", "")
    if not tok:
        raise MpstatsError("MPSTATS_TOKEN не найден: добавь его в .env")
    return tok


def _mock() -> bool:
    return os.environ.get("MOCK", "0") == "1"


class MpstatsError(RuntimeError):
    pass


# ─── HTTP с кэшем wb_metrics ─────────────────────────────────────────────────

def _http(method: str, path: str, params: dict, body: dict | None = None):
    headers = {"X-Mpstats-TOKEN": _token(), "Content-Type": "application/json"}
    url = config.MPSTATS_BASE + path
    for attempt in range(4):
        try:
            r = requests.request(method, url, params=params, headers=headers,
                                 json=body, timeout=90)
        except requests.RequestException as e:      # таймаут/обрыв — ретрай
            if attempt == 3:
                raise MpstatsError(f"{method} {path}: сеть — {e}") from e
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 202:            # принят, но не готов — подождать
            time.sleep(2 + attempt * 3)
            continue
        if r.status_code == 429:            # лимит — уважаем Retry-After
            wait = int(r.headers.get("Retry-After", 5))
            time.sleep(min(wait, 60))
            continue
        raise MpstatsError(f"{method} {path}: HTTP {r.status_code} {r.text[:200]}")
    raise MpstatsError(f"{method} {path}: не дождались ответа (202/429)")


def cached_call(conn, key: str, kind: str, fetch):
    """Ответ из wb_metrics за сегодня, иначе fetch() → в кэш.

    MOCK=1: только кэш (последняя запись за любую дату), сети нет.
    """
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT payload FROM wb_metrics WHERE key=? AND kind=? AND date=?",
        (key, kind, today)).fetchone()
    if row:
        return json.loads(row["payload"])

    if _mock():
        row = conn.execute(
            """SELECT payload FROM wb_metrics WHERE key=? AND kind=?
               ORDER BY date DESC LIMIT 1""", (key, kind)).fetchone()
        if row:
            return json.loads(row["payload"])
        raise MpstatsError(f"MOCK=1: нет фикстуры в wb_metrics для ({key!r}, {kind!r})")

    data = fetch()
    conn.execute(
        """INSERT INTO wb_metrics (key, kind, date, payload) VALUES (?,?,?,?)
           ON CONFLICT(key, kind, date) DO UPDATE SET payload=excluded.payload""",
        (key, kind, today, json.dumps(data, ensure_ascii=False)))
    conn.commit()
    time.sleep(config.MPSTATS_DELAY_SEC)
    return data


# ─── Методы API ──────────────────────────────────────────────────────────────

def keyword_frequency(conn, keyword: str) -> list[dict]:
    """Недельная частотность запроса WB: [{'date','frequency'}, …] (новые → старые)."""
    return cached_call(
        conn, keyword.lower().strip(), "keyword",
        lambda: _http("GET", "keywords/frequency", {"keyword": keyword}))


def search_top(conn, phrase: str, d1: str, d2: str) -> dict:
    """Выдача по поисковой фразе, топ по выручке: {'total': N, 'data': […]}."""
    body = {"startRow": 0, "endRow": config.MPSTATS_SERP_ROWS,
            "filterModel": {}, "sortModel": [{"colId": "revenue", "sort": "desc"}]}
    key = f"{phrase.lower().strip()}|{d1}|{d2}"
    return cached_call(
        conn, key, "serp",
        lambda: _http("POST", "search/items",
                      {"path": phrase, "d1": d1, "d2": d2}, body))


def api_limits() -> dict:
    """Остаток лимита API (без кэша — вызов бесплатный)."""
    r = requests.get("https://mpstats.io/api/user/report_api_limit",
                     headers={"X-Mpstats-TOKEN": _token()}, timeout=30)
    r.raise_for_status()
    return r.json()


# ─── Агрегация Q: недельная история → 30-дневные окна ────────────────────────

def q_windows(weekly: list[dict],
              n: int = None, window_days: int = None) -> list[tuple[str, float]]:
    """[{'date','frequency'}…] → [(дата_конца_окна, частотность_за_окно)…].

    Окна отсчитываются от самой свежей точки данных (не от сегодня — хвост
    текущей недели ещё не набрал частотность). Новые → старые.
    """
    n = n or config.MPSTATS_Q_WINDOWS
    window_days = window_days or config.MPSTATS_WINDOW_DAYS
    if not weekly:
        return []
    pts = sorted(
        ((datetime.strptime(p["date"], "%Y-%m-%d").date(), float(p["frequency"]))
         for p in weekly), reverse=True)
    anchor = pts[0][0]
    out = []
    for k in range(n):
        end = anchor - timedelta(days=window_days * k)
        start = end - timedelta(days=window_days)
        total = sum(f for d, f in pts if start < d <= end)
        out.append((end.isoformat(), total))
    return out


# ─── Сбор сигналов по трендам ────────────────────────────────────────────────

def _replace_signals(conn, trend_id: str, level: str, source: str,
                     rows: list[tuple[str, float]]):
    """Идемпотентная запись: старые сигналы этого источника заменяются."""
    conn.execute("DELETE FROM signals WHERE trend_id=? AND level=? AND source=?",
                 (trend_id, level, source))
    conn.executemany(
        "INSERT INTO signals (trend_id, level, source, date, value) VALUES (?,?,?,?,?)",
        [(trend_id, level, source, d, v) for d, v in rows])
    conn.commit()


def trend_keywords(t) -> list[str]:
    kws = [k.strip() for k in json.loads(t["wb_keywords"] or "[]") if k.strip()]
    return kws or [t["name_ru"].lower()]


def collect_trend(conn, t) -> dict:
    """Q и C для одного тренда → сигналы wb_query / wb_sales."""
    kws = trend_keywords(t)

    # Q: суммарная недельная частотность всех ключей тренда → 30-дн. окна
    merged: dict[str, float] = {}
    for kw in kws:
        for p in keyword_frequency(conn, kw):
            merged[p["date"]] = merged.get(p["date"], 0.0) + float(p["frequency"])
    weekly = [{"date": d, "frequency": f} for d, f in merged.items()]
    windows = q_windows(weekly)
    _replace_signals(conn, t["trend_id"], "wb_query", "mpstats", windows)

    # C: выдача по главному ключу за последние 30 дней.
    # API требует d2 строго раньше сегодняшней даты (422 иначе) → вчера.
    d2_date = date.today() - timedelta(days=1)
    d2 = d2_date.isoformat()
    d1 = (d2_date - timedelta(days=config.MPSTATS_WINDOW_DAYS)).isoformat()
    serp = search_top(conn, kws[0], d1, d2)
    cards = int(serp.get("total") or 0)
    top_rev = sum(float(i.get("revenue") or 0)
                  for i in (serp.get("data") or [])[:config.MPSTATS_TOP_N])
    _replace_signals(conn, t["trend_id"], "wb_sales", "mpstats:cards", [(d2, cards)])
    _replace_signals(conn, t["trend_id"], "wb_sales", "mpstats:top_revenue", [(d2, top_rev)])

    return {"trend_id": t["trend_id"], "keywords": kws,
            "q_freq": windows[0][1] if windows else 0.0,
            "c_cards": cards, "c_top_revenue": top_rev}


def collect(trend_id: str = None, include_all: bool = False) -> list[dict]:
    conn = db.connect()
    if trend_id:
        rows = conn.execute("SELECT * FROM trends WHERE trend_id=?", (trend_id,)).fetchall()
        if not rows:
            raise MpstatsError(f"нет тренда {trend_id}")
    elif include_all:
        rows = conn.execute("SELECT * FROM trends WHERE status != 'archived'").fetchall()
    else:
        rows = conn.execute("SELECT * FROM trends WHERE status = 'active'").fetchall()

    results = []
    for t in rows:
        try:
            r = collect_trend(conn, t)
            print(f"  {r['trend_id']}: Q={r['q_freq']:.0f}/30дн, "
                  f"C={r['c_cards']} карточек, топ-{config.MPSTATS_TOP_N} "
                  f"выручка {r['c_top_revenue']:,.0f} ₽")
            results.append(r)
        except (MpstatsError, requests.RequestException) as e:
            print(f"  {t['trend_id']}: ОШИБКА {e} — пропускаю, продолжай позже")
    return results


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("limits", help="остаток лимита API")
    c = sub.add_parser("collect", help="собрать Q и C метрики в signals")
    c.add_argument("--trend", help="один trend_id")
    c.add_argument("--all", action="store_true",
                   help="все тренды кроме archived (по умолчанию только active)")
    args = ap.parse_args()

    if args.cmd == "limits":
        lim = api_limits()
        print(f"Лимит: {lim.get('available')}, израсходовано: {lim.get('use')}")
    elif args.cmd == "collect":
        n = len(collect(trend_id=args.trend, include_all=args.all))
        print(f"Готово: {n} трендов. Дальше: python trends.py score")


if __name__ == "__main__":
    main()
