"""
trends.py — тренд-движок: автозаведение, скоринг стадии диффузии и типа (раздел 4).

Автозаведение (п. 4.1а): элемент таксономии, чья доля луков в новом сезоне
выросла к тому же сезону прошлого года, заводится как тренд.
`output/trusted_elements.json` (элементы, прошедшие eval по golden set) →
статус 'active'; остальные — 'candidate' (ручная проверка: распознавание
элемента ещё не подтверждено, доли могут быть шумом).

Скоринг стадии (п. 4.2): правила по P/M/F/I/S/Q/C, пороги в config.py.
Сейчас заполнен только уровень podium → большинство трендов корректно
попадает в «ИННОВАТОРЫ»; M/F/I/S — Фаза 4, Q/C (MPStats) — Фаза 3.

Тип тренда (п. 4.3): rule-based первый проход. Синтез рекомендаций
Sonnet 5 по числовой сводке — после подключения MPStats (дёшево, ~50 вызовов).

CLI:
    python trends.py autoregister   # завести тренды по росту частот
    python trends.py score          # посчитать стадию+тип для всех трендов
    python trends.py list           # таблица трендов с последним скорингом
"""

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

import config
import db
import taxonomy

ARRAY_FIELDS = ("materials", "silhouette", "construction", "decoration", "colors")
SCALAR_FIELDS = ("pattern", "category")
LOOK_FIELDS = ("styles",)  # style_tags на уровне лука
ALL_FIELDS = ARRAY_FIELDS + SCALAR_FIELDS + LOOK_FIELDS


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def trend_id_for(field: str, element: str) -> str:
    return f"{field}--{_slug(element)}"


# ─── Частоты элементов по сезонам ────────────────────────────────────────────

def season_element_shares(conn) -> dict:
    """{(field, element): {(family, year): (n_looks_с_элементом, n_looks_сезона, share)}}"""
    season_totals = {
        (r["season_family"], r["season_year"]): r["n"]
        for r in conn.execute(
            "SELECT season_family, season_year, COUNT(*) n FROM looks GROUP BY 1,2")
    }

    counts = defaultdict(lambda: defaultdict(set))  # (field, element) → season → {look_id}

    q = """SELECT i.look_id, i.category, i.pattern, i.materials, i.silhouette,
                  i.construction, i.decoration, i.colors,
                  l.season_family, l.season_year
           FROM items i JOIN looks l USING (look_id)
           WHERE i.confidence >= ?"""
    for r in conn.execute(q, (config.MIN_ITEM_CONFIDENCE,)):
        season = (r["season_family"], r["season_year"])
        for f in SCALAR_FIELDS:
            v = r[f]
            if v and v != taxonomy.NOT_VISIBLE:
                counts[(f, v)][season].add(r["look_id"])
        for f in ARRAY_FIELDS:
            for v in json.loads(r[f] or "[]"):
                if v and v != taxonomy.NOT_VISIBLE:
                    counts[(f, v)][season].add(r["look_id"])

    for r in conn.execute(
            "SELECT look_id, style_tags, season_family, season_year FROM looks"):
        season = (r["season_family"], r["season_year"])
        for v in json.loads(r["style_tags"] or "[]"):
            counts[("styles", v)][season].add(r["look_id"])

    out = {}
    for key, per_season in counts.items():
        out[key] = {
            s: (len(ids), season_totals[s], len(ids) / season_totals[s])
            for s, ids in per_season.items()
        }
    return out


def yoy_pairs(shares_by_season: dict, season_totals: dict):
    """Пары (family, year) vs (family, year-1) с достаточным объёмом сезона."""
    pairs = []
    for (family, year) in season_totals:
        prev = (family, year - 1)
        if prev in season_totals \
                and season_totals[(family, year)] >= config.AUTOREG_MIN_SEASON_LOOKS \
                and season_totals[prev] >= config.AUTOREG_MIN_SEASON_LOOKS:
            pairs.append(((family, year), prev))
    return pairs


# ─── Автозаведение трендов ───────────────────────────────────────────────────

def load_trusted(path: str = "output/trusted_elements.json") -> set:
    try:
        data = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        print(f"! {path} не найден — все тренды получат статус 'candidate'")
        return set()
    return {(e["field"], e["element"]) for e in data}


def autoregister(conn, trusted_path: str = "output/trusted_elements.json") -> list:
    trusted = load_trusted(trusted_path)
    season_totals = {
        (r["season_family"], r["season_year"]): r["n"]
        for r in conn.execute(
            "SELECT season_family, season_year, COUNT(*) n FROM looks GROUP BY 1,2")
    }
    all_shares = season_element_shares(conn)
    pairs = yoy_pairs(all_shares, season_totals)
    today = date.today().isoformat()
    created = []

    for (field, element), per_season in all_shares.items():
        best = None  # (growth, share_new, count_new, season_new, season_prev, share_prev)
        for season_new, season_prev in pairs:
            cnt_new, total_new, share_new = per_season.get(season_new, (0, season_totals[season_new], 0.0))
            cnt_prev, _, share_prev = per_season.get(season_prev, (0, season_totals[season_prev], 0.0))
            if cnt_new < config.AUTOREG_MIN_COUNT or share_new < config.AUTOREG_MIN_SHARE:
                continue
            if share_prev > 0:
                growth = share_new / share_prev
                if growth < config.AUTOREG_GROWTH_RATIO:
                    continue
            else:  # элемента не было в прошлом сезоне — «новый» при заметной доле
                if share_new < config.AUTOREG_NEW_MIN_SHARE:
                    continue
                growth = float("inf")
            if best is None or share_new > best[1]:
                best = (growth, share_new, cnt_new, season_new, season_prev, share_prev)

        if best is None:
            continue

        growth, share_new, cnt_new, season_new, season_prev, share_prev = best
        tid = trend_id_for(field, element)
        name_ru = taxonomy.ru(field if field != "colors" else "category", element) \
            if field != "colors" else element
        status = "active" if (field, element) in trusted else "candidate"
        growth_txt = "новый" if growth == float("inf") else f"×{growth:.2f}"
        notes = (f"авто: {season_new[0]} {season_new[1]} {share_new:.1%} "
                 f"({cnt_new} луков) vs {season_prev[1]} {share_prev:.1%} → {growth_txt}"
                 + ("" if status == "active" else "; элемент вне trusted-списка — проверить распознавание"))

        conn.execute(
            """INSERT INTO trends (trend_id, name_ru, name_en, type_dimension, field,
                                   element, wb_keywords, status, origin, notes)
               VALUES (?,?,?,?,?,?,?,?,'auto',?)
               ON CONFLICT(field, element) DO UPDATE SET notes = excluded.notes""",
            (tid, name_ru, element, config.FIELD_TO_DIMENSION[field], field, element,
             json.dumps([name_ru.lower()], ensure_ascii=False), status, notes),
        )
        # подиум-сигналы по каждому сезону — для воронки/спарклайнов
        conn.execute("DELETE FROM signals WHERE trend_id=? AND level='podium' AND source='vogue'", (tid,))
        for (family, year), (cnt, total, share) in per_season.items():
            conn.execute(
                """INSERT INTO signals (trend_id, level, source, date, value, url)
                   VALUES (?, 'podium', 'vogue', ?, ?, ?)""",
                (tid, today, share, f"season:{family}:{year}"),
            )
        created.append((tid, name_ru, status, notes))

    conn.commit()
    return created


def add_manual_trend(conn, field: str, element: str, name_ru: str,
                     wb_keywords: list[str] | None = None, notes: str = "") -> str:
    """Заведение вручную из копилки гипотез (п. 4.1б)."""
    tid = trend_id_for(field, element)
    conn.execute(
        """INSERT OR IGNORE INTO trends (trend_id, name_ru, name_en, type_dimension,
           field, element, wb_keywords, status, origin, notes)
           VALUES (?,?,?,?,?,?,?, 'active', 'manual', ?)""",
        (tid, name_ru, element, config.FIELD_TO_DIMENSION.get(field, field),
         field, element, json.dumps(wb_keywords or [name_ru.lower()], ensure_ascii=False), notes),
    )
    conn.commit()
    return tid


# ─── Сбор метрик по тренду ───────────────────────────────────────────────────

def collect_metrics(conn, trend_id: str, shares_cache: dict | None = None) -> dict:
    t = conn.execute("SELECT * FROM trends WHERE trend_id=?", (trend_id,)).fetchone()
    if not t:
        raise ValueError(f"нет тренда {trend_id}")

    season_totals = {
        (r["season_family"], r["season_year"]): r["n"]
        for r in conn.execute(
            "SELECT season_family, season_year, COUNT(*) n FROM looks GROUP BY 1,2")
    }
    shares = (shares_cache or season_element_shares(conn)).get(
        (t["field"], t["element"]), {})

    # P: лучшая YoY-пара (максимальная доля нового сезона)
    p_share = p_growth = None
    p_season = ""
    for season_new, season_prev in yoy_pairs(shares, season_totals):
        cnt, _, share_new = shares.get(season_new, (0, 0, 0.0))
        _, _, share_prev = shares.get(season_prev, (0, 0, 0.0))
        if p_share is None or share_new > p_share:
            p_share = share_new
            p_growth = (share_new / share_prev) if share_prev > 0 else (
                float("inf") if share_new > 0 else 1.0)
            p_season = f"{season_new[0]} {season_new[1]}"

    today = date.today()
    def _count(levels: tuple, days: int) -> int:
        since = (today - timedelta(days=days)).isoformat()
        ph = ",".join("?" * len(levels))
        return conn.execute(
            f"""SELECT COALESCE(SUM(value),0) FROM signals
                WHERE trend_id=? AND level IN ({ph}) AND date >= ?
                AND source != 'vogue'""",
            (trend_id, *levels, since)).fetchone()[0]

    m = _count(("middle",), config.STAGE_WINDOW_MF_DAYS)
    f = _count(("fast_fashion",), config.STAGE_WINDOW_MF_DAYS)
    i = _count(("influencer",), config.STAGE_WINDOW_I_DAYS)

    # S: рост соц.поиска — отношение последнего значения к предыдущему
    s_rows = conn.execute(
        """SELECT value FROM signals WHERE trend_id=? AND level='social_search'
           ORDER BY date DESC LIMIT 2""", (trend_id,)).fetchall()
    s_growth = (s_rows[0][0] / s_rows[1][0]) if len(s_rows) == 2 and s_rows[1][0] else None

    # Q: частотность WB (последние месячные значения), рост м/м, месяцы спада подряд
    q_rows = [r[0] for r in conn.execute(
        """SELECT value FROM signals WHERE trend_id=? AND level='wb_query'
           ORDER BY date DESC LIMIT 13""", (trend_id,)).fetchall()]
    q_freq = q_rows[0] if q_rows else 0.0
    q_growth = ((q_rows[0] - q_rows[1]) / q_rows[1]) if len(q_rows) >= 2 and q_rows[1] else None
    q_decline = 0
    for a, b in zip(q_rows, q_rows[1:]):  # от свежего к старому
        if a < b:
            q_decline += 1
        else:
            break
    # Сезонная поправка: летние/зимние просадки м/м — не спад тренда.
    # Если есть данные за 13 месяцев и текущее значение не хуже прошлогоднего
    # (с допуском SEASONAL_YOY_TOLERANCE), серию м/м-падения не считаем спадом.
    if (len(q_rows) >= 13 and q_rows[12]
            and q_rows[0] >= getattr(config, "SEASONAL_YOY_TOLERANCE", 0.9) * q_rows[12]):
        q_decline = 0

    # C: насыщенность ниши — из последнего сигнала wb_sales/кэша MPStats (Фаза 3)
    c_row = conn.execute(
        """SELECT value FROM signals WHERE trend_id=? AND level='wb_sales'
           AND source='mpstats:cards' ORDER BY date DESC LIMIT 1""", (trend_id,)).fetchone()
    c_cards = int(c_row[0]) if c_row else None
    r_row = conn.execute(
        """SELECT value FROM signals WHERE trend_id=? AND level='wb_sales'
           AND source='mpstats:top_revenue' ORDER BY date DESC LIMIT 1""", (trend_id,)).fetchone()
    c_top_revenue = r_row[0] if r_row else None

    return {
        "trend_id": trend_id, "name_ru": t["name_ru"],
        "p_share": p_share or 0.0, "p_growth": p_growth, "p_season": p_season,
        "m": m, "f": f, "i": i, "s_growth": s_growth,
        "q_freq": q_freq, "q_growth": q_growth, "q_decline_months": q_decline,
        "c_cards": c_cards, "c_top_revenue": c_top_revenue,
    }


# ─── Правила стадии (п. 4.2) и типа (п. 4.3) ─────────────────────────────────

def score_stage(m: dict) -> tuple[str, str]:
    cfg = config
    p_growing = m["p_growth"] is not None and (
        m["p_growth"] == float("inf") or m["p_growth"] >= cfg.P_GROWTH_RATIO)
    mfi = m["m"] + m["f"] + m["i"]
    q, qg, qd = m["q_freq"], m["q_growth"], m["q_decline_months"]
    q_zero = q < cfg.Q_ZERO_MAX

    if qd >= cfg.Q_DECLINE_MONTHS:
        return "СПАД", f"Q падает {qd} мес. подряд → не входить, распродажа остатков"

    if q >= cfg.Q_MASS_MIN_FREQ and qg is not None and qg <= 0:
        return ("ПОЗДНЕЕ БОЛЬШИНСТВО",
                "Q на плато/начало спада при высокой частотности → коммерческая база, "
                "модификации цвета/материала, конкуренция ценой")

    saturated = m["c_cards"] is not None and m["c_cards"] >= cfg.C_SATURATED_CARDS
    if (q >= cfg.Q_MASS_MIN_FREQ and (qg or 0) >= cfg.Q_MASS_GROWTH_MOM) or saturated:
        return ("РАННЕЕ БОЛЬШИНСТВО",
                "массовый рост Q / ниша насыщается → масштабирование только с модификациями")

    q_first_growth = qg is not None and qg >= cfg.Q_EARLY_GROWTH_MOM and q < cfg.Q_EARLY_MAX_FREQ
    if (m["m"] > 0 or m["f"] > 0) or q_first_growth or (m["i"] > 0 and not q_zero):
        return ("РАННИЕ ПОСЛЕДОВАТЕЛИ",
                "появления у middle/fast-fashion, первый рост Q с низкой базы → "
                "момент пилотной тестовой партии")

    if p_growing and mfi <= cfg.MFI_ZERO_MAX and q_zero:
        return ("ИННОВАТОРЫ",
                f"P растёт ({m['p_season']}: {m['p_share']:.1%}), M+F+I≈0, Q≈0 — "
                "тренд только на подиуме")

    return ("ИННОВАТОРЫ",
            "данных ниже подиума нет (M/F/I/Q не подключены или пусты) — стадия по умолчанию")


def classify_type(m: dict, stage: str) -> tuple[int, str]:
    cfg = config
    q_zero = m["q_freq"] < cfg.Q_ZERO_MAX
    visual = m["p_share"] > 0 or m["i"] > 0
    saturated = m["c_cards"] is not None and m["c_cards"] >= cfg.C_SATURATED_CARDS
    q_falling = m["q_decline_months"] >= 1

    if visual and not q_zero and (q_falling or saturated):
        return 2, ("визуально трендовый, но метрики WB плохие → "
                   "использовать как элемент в другой категории")
    if q_zero and visual:
        return 1, ("новый, на WB нет (Q≈0, есть P/I) → выводить на проверенном изделии, "
                   "опора на вирусность")
    if (m["q_growth"] or 0) >= cfg.TYPE4_MIN_Q_GROWTH \
            and m["c_cards"] is not None and m["c_cards"] < cfg.TYPE4_MAX_CARDS \
            and (m["c_top_revenue"] or 0) >= cfg.TYPE4_MIN_TOP_REVENUE:
        return 4, ("базово-трендовый с сильной аналитикой (растущие Q, высокая выручка, "
                   "низкая конкуренция) → усилить цветом/материалом")
    return 3, ("подтверждённый тренд с ростом → модификации материалов/декора, "
               "соседние подкатегории")


def score_all(conn) -> list:
    shares_cache = season_element_shares(conn)
    results = []
    for t in conn.execute("SELECT trend_id FROM trends WHERE status != 'archived'"):
        m = collect_metrics(conn, t["trend_id"], shares_cache)
        stage, why_stage = score_stage(m)
        ttype, why_type = classify_type(m, stage)
        rationale = f"стадия: {why_stage} | тип {ttype}: {why_type}"
        p_growth = None if m["p_growth"] in (None, float("inf")) else round(m["p_growth"], 3)
        conn.execute(
            """INSERT INTO trend_scores (trend_id, date, p_share, p_growth, m_count,
               f_count, i_count, s_growth, q_freq, q_growth, q_decline_months,
               c_cards, c_top_revenue, stage, trend_type, rationale)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(trend_id, date) DO UPDATE SET
                 p_share=excluded.p_share, p_growth=excluded.p_growth,
                 m_count=excluded.m_count, f_count=excluded.f_count,
                 i_count=excluded.i_count, s_growth=excluded.s_growth,
                 q_freq=excluded.q_freq, q_growth=excluded.q_growth,
                 q_decline_months=excluded.q_decline_months,
                 c_cards=excluded.c_cards, c_top_revenue=excluded.c_top_revenue,
                 stage=excluded.stage, trend_type=excluded.trend_type,
                 rationale=excluded.rationale""",
            (m["trend_id"], date.today().isoformat(), m["p_share"], p_growth,
             m["m"], m["f"], m["i"], m["s_growth"], m["q_freq"], m["q_growth"],
             m["q_decline_months"], m["c_cards"], m["c_top_revenue"],
             stage, ttype, rationale),
        )
        results.append((m["trend_id"], m["name_ru"], stage, ttype, m["p_share"], m["p_season"]))
    conn.commit()
    return results


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _cmd_list(conn):
    rows = conn.execute(
        """SELECT t.trend_id, t.name_ru, t.type_dimension, t.status,
                  s.stage, s.trend_type, s.p_share
           FROM trends t
           LEFT JOIN trend_scores s ON s.trend_id = t.trend_id
             AND s.date = (SELECT MAX(date) FROM trend_scores WHERE trend_id = t.trend_id)
           ORDER BY t.status, s.p_share DESC NULLS LAST""").fetchall()
    print(f"{'trend_id':40s} {'название':28s} {'измерение':11s} {'статус':10s} {'стадия':22s} тип   P")
    for r in rows:
        p = f"{r['p_share']:.1%}" if r["p_share"] is not None else "—"
        print(f"{r['trend_id']:40s} {r['name_ru'][:27]:28s} {r['type_dimension']:11s} "
              f"{r['status']:10s} {(r['stage'] or '—'):22s} {r['trend_type'] or '—'}   {p}")
    print(f"\nвсего: {len(rows)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["autoregister", "score", "list"])
    ap.add_argument("--db", default=None)
    ap.add_argument("--trusted", default="output/trusted_elements.json")
    args = ap.parse_args()
    conn = db.init_db(args.db or config.DB_PATH)

    if args.command == "autoregister":
        created = autoregister(conn, args.trusted)
        for tid, name, status, notes in sorted(created, key=lambda x: x[2]):
            print(f"[{status:9s}] {tid:45s} {name} — {notes}")
        n_active = sum(1 for c in created if c[2] == "active")
        print(f"\nзаведено/обновлено: {len(created)} (active: {n_active}, "
              f"candidate: {len(created) - n_active})")
    elif args.command == "score":
        for tid, name, stage, ttype, p, season in score_all(conn):
            print(f"{tid:45s} {name[:25]:26s} {stage:22s} тип {ttype}  P={p:.1%} ({season})")
    elif args.command == "list":
        _cmd_list(conn)
