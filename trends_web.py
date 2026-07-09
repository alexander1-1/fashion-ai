"""
trends_web.py — Фаза 5: UI «Тренды» (дашборд + карточка тренда).

Blueprint для Flask-приложения (app.py / app_hf.py):
  /trends              — таблица трендов: стадия, тип, спарклайны сигналов по уровням
  /trends/<trend_id>   — карточка: воронка подиум→WB, фото-референсы,
                         метрики MPStats, рекомендации
  /inbox/<path>        — отдача фото из inbox/ (TG/бренды) для референсов

Читает только trend_signals.db (Фазы 2–4). Если базы нет (например, на HF
Spaces) — страница показывает пустое состояние, ничего не падает.
"""

import json
import os
import sqlite3
from collections import defaultdict

from flask import Blueprint, abort, render_template, request, send_from_directory

import config

bp = Blueprint("trends", __name__)

STAGE_ORDER = {s: n for n, s in enumerate(config.STAGES)}

STAGE_COLORS = {
    "ИННОВАТОРЫ": "#9b8cde",
    "РАННИЕ ПОСЛЕДОВАТЕЛИ": "#6ca0dc",
    "РАННЕЕ БОЛЬШИНСТВО": "#6aaa6a",
    "ПОЗДНЕЕ БОЛЬШИНСТВО": "#c9a84c",
    "СПАД": "#c96a5a",
}

TYPE_LABELS = {
    1: "Тип 1 — новый, на WB нет",
    2: "Тип 2 — визуальный, метрики WB слабые",
    3: "Тип 3 — подтверждённый с ростом",
    4: "Тип 4 — базово-трендовый, сильная аналитика",
}

# Рекомендации по стадии — из методики (п. 4.2 инструкции)
STAGE_ADVICE = {
    "ИННОВАТОРЫ": "Тренд только на подиуме. Наблюдать; в производство не входить, "
                  "готовить гипотезы адаптации.",
    "РАННИЕ ПОСЛЕДОВАТЕЛИ": "Момент пилотной тестовой партии: первые дропы у "
                            "middle/fast-fashion, первый рост запросов WB с низкой базы.",
    "РАННЕЕ БОЛЬШИНСТВО": "Массовый рост запросов, ниша насыщается. Масштабирование "
                          "только с модификациями: цвет, материал, деталь, фурнитура.",
    "ПОЗДНЕЕ БОЛЬШИНСТВО": "Тренд — коммерческая база. Модификации в цвета/материалы, "
                           "конкуренция ценой; следить за чувствительностью к цене.",
    "СПАД": "Не входить. Распродажа остатков, выход из ниши.",
}

FIELDS_ARRAY = ("materials", "silhouette", "construction", "decoration", "colors")
FIELDS_SCALAR = ("pattern", "category")


def _conn():
    path = os.environ.get("TRENDS_DB", config.DB_PATH)
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Общие выборки ────────────────────────────────────────────────────────────

LATEST_SCORE_SQL = """
SELECT t.trend_id, t.name_ru, t.name_en, t.type_dimension, t.field, t.element,
       t.wb_keywords, t.status, t.origin, t.notes, t.created_at,
       s.stage, s.trend_type, s.rationale, s.date AS score_date,
       s.p_share, s.p_growth, s.m_count, s.f_count, s.i_count, s.s_growth,
       s.q_freq, s.q_growth, s.q_decline_months, s.c_cards, s.c_top_revenue
FROM trends t
LEFT JOIN trend_scores s ON s.trend_id = t.trend_id
  AND s.date = (SELECT MAX(date) FROM trend_scores WHERE trend_id = t.trend_id)
"""


def _podium_series(conn, trend_id=None):
    """{trend_id: [{"label": "fall-rtw 2026", "value": share}, …]} по сезонам.

    Для спарклайна берём одну линейку сезонов (family с максимальной долей
    в самом свежем году), отсортированную по году.
    """
    where, args = "", ()
    if trend_id:
        where, args = "AND trend_id = ?", (trend_id,)
    rows = conn.execute(
        f"""SELECT trend_id, url, value FROM signals
            WHERE level='podium' AND url LIKE 'season:%' {where}""", args)

    per_trend = defaultdict(lambda: defaultdict(dict))  # tid → family → {year: share}
    for r in rows:
        try:
            _, family, year = r["url"].split(":")
            per_trend[r["trend_id"]][family][int(year)] = r["value"]
        except ValueError:
            continue

    out = {}
    for tid, families in per_trend.items():
        best_family = max(
            families.items(),
            key=lambda kv: (max(kv[1]), kv[1][max(kv[1])]))[0]
        series = sorted(families[best_family].items())
        out[tid] = [{"label": f"{best_family} {y}", "value": v} for y, v in series]
    return out


def _q_series(conn, trend_id=None, limit=13):
    """{trend_id: [{"label": "2026-07", "value": freq}, …]} — частотность WB по месяцам."""
    where, args = "", ()
    if trend_id:
        where, args = "AND trend_id = ?", (trend_id,)
    rows = conn.execute(
        f"""SELECT trend_id, date, value FROM signals
            WHERE level='wb_query' {where} ORDER BY trend_id, date""", args)
    out = defaultdict(list)
    for r in rows:
        out[r["trend_id"]].append({"label": r["date"][:7], "value": r["value"]})
    return {tid: pts[-limit:] for tid, pts in out.items()}


def _weekly_series(conn, level, trend_id=None, weeks=12):
    """{trend_id: [{"label": "нед. 27", "value": n}, …]} — сумма сигналов по неделям."""
    where, args = "", ()
    if trend_id:
        where, args = "AND trend_id = ?", (trend_id,)
    rows = conn.execute(
        f"""SELECT trend_id, strftime('%Y-%W', date) wk, SUM(value) n
            FROM signals WHERE level = '{level}' {where}
            GROUP BY trend_id, wk ORDER BY trend_id, wk""", args)
    out = defaultdict(list)
    for r in rows:
        out[r["trend_id"]].append({"label": r["wk"], "value": r["n"]})
    return {tid: pts[-weeks:] for tid, pts in out.items()}


def _row_to_dict(r):
    d = dict(r)
    try:
        d["wb_keywords"] = json.loads(d.get("wb_keywords") or "[]")
    except json.JSONDecodeError:
        d["wb_keywords"] = []
    d["stage_color"] = STAGE_COLORS.get(d.get("stage"), "#555")
    d["type_label"] = TYPE_LABELS.get(d.get("trend_type"), "")
    return d


# ─── Маршруты ─────────────────────────────────────────────────────────────────

@bp.route("/trends")
def trends_dashboard():
    conn = _conn()
    if conn is None:
        return render_template("trends.html", rows=[], stages=config.STAGES,
                               dimensions=[], statuses=[], db_missing=True,
                               f_stage="", f_dim="", f_status="", f_q="",
                               stage_counts={}, stage_colors=STAGE_COLORS)

    f_stage = request.args.get("stage", "")
    f_dim = request.args.get("dimension", "")
    f_status = request.args.get("status", "")
    f_q = request.args.get("q", "").strip()

    rows = [_row_to_dict(r) for r in conn.execute(LATEST_SCORE_SQL +
            " WHERE t.status != 'archived'")]

    stage_counts = defaultdict(int)
    for d in rows:
        if d["stage"]:
            stage_counts[d["stage"]] += 1
    dimensions = sorted({d["type_dimension"] for d in rows})
    statuses = sorted({d["status"] for d in rows})

    if f_stage:
        rows = [d for d in rows if d["stage"] == f_stage]
    if f_dim:
        rows = [d for d in rows if d["type_dimension"] == f_dim]
    if f_status:
        rows = [d for d in rows if d["status"] == f_status]
    if f_q:
        q = f_q.lower()
        rows = [d for d in rows if q in d["name_ru"].lower()
                or q in d["name_en"].lower() or q in d["trend_id"]]

    # стадия (дальше по диффузии — выше) → частотность Q → доля подиума
    rows.sort(key=lambda d: (-STAGE_ORDER.get(d["stage"], -1),
                             -(d["q_freq"] or 0), -(d["p_share"] or 0)))

    podium = _podium_series(conn)
    q_ser = _q_series(conn)
    infl = _weekly_series(conn, "influencer")
    for d in rows:
        d["spark"] = {
            "podium": podium.get(d["trend_id"], []),
            "influencer": infl.get(d["trend_id"], []),
            "q": q_ser.get(d["trend_id"], []),
        }

    conn.close()
    return render_template("trends.html", rows=rows, stages=config.STAGES,
                           dimensions=dimensions, statuses=statuses,
                           db_missing=False, f_stage=f_stage, f_dim=f_dim,
                           f_status=f_status, f_q=f_q,
                           stage_counts=stage_counts, stage_colors=STAGE_COLORS)


def _podium_refs(conn, field, element, limit=8):
    """Фото-референсы с подиума: луки, где предмет содержит элемент тренда."""
    if field == "styles":
        rows = conn.execute(
            """SELECT image_url, designer, season_label, confidence AS conf
               FROM looks WHERE style_tags LIKE ?
               ORDER BY season_year DESC, confidence DESC LIMIT ?""",
            (f'%"{element}"%', limit))
    elif field in FIELDS_SCALAR:
        rows = conn.execute(
            f"""SELECT l.image_url, l.designer, l.season_label, i.confidence AS conf
                FROM items i JOIN looks l USING (look_id)
                WHERE i.{field} = ? AND i.confidence >= ?
                ORDER BY l.season_year DESC, i.confidence DESC LIMIT ?""",
            (element, config.MIN_ITEM_CONFIDENCE, limit))
    else:
        rows = conn.execute(
            f"""SELECT l.image_url, l.designer, l.season_label, i.confidence AS conf
                FROM items i JOIN looks l USING (look_id)
                WHERE i.{field} LIKE ? AND i.confidence >= ?
                ORDER BY l.season_year DESC, i.confidence DESC LIMIT ?""",
            (f'%"{element}"%', config.MIN_ITEM_CONFIDENCE, limit))
    seen, out = set(), []
    for r in rows:
        if r["image_url"] in seen:
            continue
        seen.add(r["image_url"])
        out.append(dict(r))
    return out


def _ext_refs(conn, element, limit=8):
    """Фото-референсы из TG/брендов: ext_photos, чьи vision-теги содержат элемент."""
    rows = conn.execute(
        """SELECT path, url, source, level, date FROM ext_photos
           WHERE status='tagged' AND tags LIKE ?
           ORDER BY date DESC LIMIT ?""",
        (f'%"{element}"%', limit))
    return [dict(r) for r in rows if os.path.exists(r["path"])]


def _keyword_freqs(conn, keywords):
    """Последняя частотность и динамика по каждому WB-ключу из кэша MPStats."""
    out = []
    for kw in keywords:
        row = conn.execute(
            """SELECT payload FROM wb_metrics WHERE key=? AND kind='keyword'
               ORDER BY date DESC LIMIT 1""", (kw,)).fetchone()
        if not row:
            out.append({"keyword": kw, "freq": None, "wow": None})
            continue
        try:
            pts = json.loads(row["payload"])  # свежие первыми
        except json.JSONDecodeError:
            pts = []
        freq = pts[0]["frequency"] if pts else None
        wow = None
        if len(pts) >= 2 and pts[1].get("frequency"):
            wow = (pts[0]["frequency"] - pts[1]["frequency"]) / pts[1]["frequency"]
        out.append({"keyword": kw, "freq": freq, "wow": wow})
    return out


@bp.route("/trends/<trend_id>")
def trend_detail(trend_id):
    conn = _conn()
    if conn is None:
        abort(404, "trend_signals.db не найден")
    row = conn.execute(LATEST_SCORE_SQL + " WHERE t.trend_id = ?", (trend_id,)).fetchone()
    if not row:
        conn.close()
        abort(404, f"тренд {trend_id} не найден")
    t = _row_to_dict(row)

    series = {
        "podium": _podium_series(conn, trend_id).get(trend_id, []),
        "influencer": _weekly_series(conn, "influencer", trend_id, weeks=16).get(trend_id, []),
        "q": _q_series(conn, trend_id).get(trend_id, []),
    }

    # Воронка подиум → WB (значения последнего скоринга)
    funnel = [
        {"level": "Подиум", "key": "P",
         "value": f"{t['p_share']:.1%}" if t["p_share"] else "—",
         "hint": ("рост ×%.2f к прошлому сезону" % t["p_growth"]) if t["p_growth"] else ""},
        {"level": "Middle-бренды", "key": "M",
         "value": t["m_count"] if t["m_count"] is not None else "—",
         "hint": f"появлений за {config.STAGE_WINDOW_MF_DAYS} дн."},
        {"level": "Fast-fashion", "key": "F",
         "value": t["f_count"] if t["f_count"] is not None else "—",
         "hint": f"появлений за {config.STAGE_WINDOW_MF_DAYS} дн."},
        {"level": "Инфлюенсеры", "key": "I",
         "value": t["i_count"] if t["i_count"] is not None else "—",
         "hint": f"появлений за {config.STAGE_WINDOW_I_DAYS} дн."},
        {"level": "Соц. поиск", "key": "S",
         "value": f"×{t['s_growth']:.2f}" if t["s_growth"] else "—",
         "hint": "динамика Pinterest/Google"},
        {"level": "Запросы WB", "key": "Q",
         "value": f"{t['q_freq']:,.0f}".replace(",", " ") if t["q_freq"] else "—",
         "hint": (f"{t['q_growth']:+.0%} м/м" if t["q_growth"] is not None else "")
                 + (f" · спад {t['q_decline_months']} мес." if (t["q_decline_months"] or 0) >= 1 else "")},
        {"level": "Ниша WB", "key": "C",
         "value": t["c_cards"] if t["c_cards"] is not None else "—",
         "hint": (f"карточек; выручка топ-20: {t['c_top_revenue']:,.0f} ₽/мес".replace(",", " ")
                  if t["c_top_revenue"] else "карточек")},
    ]

    podium_refs = _podium_refs(conn, t["field"], t["element"])
    ext_refs = _ext_refs(conn, t["element"])
    keyword_freqs = _keyword_freqs(conn, t["wb_keywords"])
    conn.close()

    return render_template("trend_detail.html", t=t, series=series, funnel=funnel,
                           podium_refs=podium_refs, ext_refs=ext_refs,
                           keyword_freqs=keyword_freqs, stages=config.STAGES,
                           stage_colors=STAGE_COLORS,
                           stage_advice=STAGE_ADVICE.get(t["stage"] or "", ""))


@bp.route("/inbox/<path:relpath>")
def inbox_photo(relpath):
    """Отдача фото-референсов из inbox/ (только чтение, только внутри папки)."""
    return send_from_directory(os.path.abspath(config.INBOX_DIR), relpath)
