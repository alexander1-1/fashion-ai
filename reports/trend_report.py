"""
reports/trend_report.py — Фаза 6: PDF-отчёт по категории (п. 5.1 инструкции).

Содержимое (перенос логики отчётов из fashion-ai на данные trend_signals.db):
  1. Срез категории: объём подиумного сигнала, метрики WB (частотность ключей,
     карточки, выручка топов из кэша MPStats), динамика Q.
  2. Тренды внутри категории со стадиями диффузии и типами.
  3. Конкурентное позиционирование: инноваторы / ранние последователи /
     большинство — как в отчёте fashion-ai.
  4. Фото-референсы подиума + гипотезы модификаций (стадийные рекомендации
     методики + сгенерированные Студией варианты, если есть).

Фото-референсы скачиваются в output/reports/img_cache (повторно не качаются).
MOCK=1 или --no-images — без сети: используются только уже скачанные.

CLI:
    python -m reports.trend_report --category "Knitwear/Cardigan"
    python -m reports.trend_report --list-categories
    MOCK=1 python -m reports.trend_report --category Dress --no-images
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import db
import taxonomy
from reports import pdf_kit as K

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

MOCK = os.environ.get("MOCK", "0") == "1"

# Рекомендации по стадии (те же, что в trends_web.py — методика п. 4.2)
STAGE_ADVICE = {
    "ИННОВАТОРЫ": "наблюдать, в производство не входить, готовить гипотезы адаптации",
    "РАННИЕ ПОСЛЕДОВАТЕЛИ": "момент пилотной тестовой партии",
    "РАННЕЕ БОЛЬШИНСТВО": "масштабирование только с модификациями (цвет, материал, деталь, фурнитура)",
    "ПОЗДНЕЕ БОЛЬШИНСТВО": "коммерческая база: модификации в цвета/материалы, конкуренция ценой",
    "СПАД": "не входить; распродажа остатков",
}

ARRAY_FIELDS = ("materials", "silhouette", "construction", "decoration", "colors")


# ─── Сбор данных ─────────────────────────────────────────────────────────────

def category_trends(conn, category: str) -> list[dict]:
    """Тренды, встречающиеся в предметах категории, с последним скорингом.

    Для array/scalar-полей — co-occurrence по items той же категории;
    для styles — луки, где есть предмет категории и стиль-тег;
    тренд самой категории (field='category') включается всегда.
    """
    total_items = conn.execute(
        "SELECT COUNT(*) FROM items WHERE category=? AND confidence>=?",
        (category, config.MIN_ITEM_CONFIDENCE)).fetchone()[0]

    rows = conn.execute("""
        SELECT t.*, s.stage, s.trend_type, s.rationale, s.p_share, s.p_growth,
               s.q_freq, s.q_growth, s.q_decline_months, s.c_cards, s.c_top_revenue
        FROM trends t
        LEFT JOIN trend_scores s ON s.trend_id = t.trend_id
          AND s.date = (SELECT MAX(date) FROM trend_scores WHERE trend_id = t.trend_id)
        WHERE t.status != 'archived'""").fetchall()

    out = []
    for r in rows:
        d = dict(r)
        f, el = d["field"], d["element"]
        if f == "category":
            if el != category:
                continue
            n = total_items
        elif f == "styles":
            n = conn.execute(
                """SELECT COUNT(DISTINCT l.look_id) FROM looks l
                   JOIN items i USING (look_id)
                   WHERE i.category=? AND i.confidence>=? AND l.style_tags LIKE ?""",
                (category, config.MIN_ITEM_CONFIDENCE, f'%"{el}"%')).fetchone()[0]
        elif f == "pattern":
            n = conn.execute(
                "SELECT COUNT(*) FROM items WHERE category=? AND confidence>=? AND pattern=?",
                (category, config.MIN_ITEM_CONFIDENCE, el)).fetchone()[0]
        elif f in ARRAY_FIELDS:
            n = conn.execute(
                f"""SELECT COUNT(*) FROM items WHERE category=? AND confidence>=?
                    AND {f} LIKE ?""",
                (category, config.MIN_ITEM_CONFIDENCE, f'%"{el}"%')).fetchone()[0]
        else:
            continue
        if n == 0 and f != "category":
            continue
        d["cat_count"] = n
        d["cat_share"] = n / total_items if total_items else 0.0
        d["is_category_trend"] = (f == "category")
        out.append(d)

    out.sort(key=lambda d: (not d["is_category_trend"], -d["cat_count"]))
    return out


def q_series(conn, trend_id: str, limit: int = 8) -> list[tuple[str, float]]:
    rows = conn.execute(
        """SELECT date, value FROM signals WHERE trend_id=? AND level='wb_query'
           ORDER BY date""", (trend_id,)).fetchall()
    return [(r["date"][:7], r["value"]) for r in rows][-limit:]


def keyword_freqs(conn, kws: list[str]) -> list[dict]:
    out = []
    for kw in kws:
        row = conn.execute(
            """SELECT payload FROM wb_metrics WHERE key=? AND kind='keyword'
               ORDER BY date DESC LIMIT 1""", (kw,)).fetchone()
        pts = json.loads(row["payload"]) if row else []
        freq = pts[0]["frequency"] if pts else None
        out.append({"keyword": kw, "freq": freq})
    return out


def serp_top(conn, kws: list[str]) -> tuple[int | None, list[dict]]:
    """(всего карточек, топ выдачи) из кэша MPStats для первого ключа с данными."""
    for kw in kws:
        row = conn.execute(
            """SELECT payload FROM wb_metrics WHERE kind='serp' AND key LIKE ?
               ORDER BY date DESC LIMIT 1""", (f"{kw.lower()}|%",)).fetchone()
        if row:
            p = json.loads(row["payload"])
            return int(p.get("total") or 0), (p.get("data") or [])[:config.REPORT_TOP_CARDS]
    return None, []


def podium_refs(conn, category: str, limit: int = 12) -> list[dict]:
    rows = conn.execute(
        """SELECT l.image_url, l.designer, l.season_label
           FROM items i JOIN looks l USING (look_id)
           WHERE i.category=? AND i.confidence>=?
           ORDER BY l.season_year DESC, i.confidence DESC LIMIT ?""",
        (category, config.MIN_ITEM_CONFIDENCE, limit * 3)).fetchall()
    seen, out = set(), []
    for r in rows:
        if r["image_url"] in seen:
            continue
        seen.add(r["image_url"])
        out.append(dict(r))
        if len(out) >= limit:
            break
    return out


def fetch_image(url: str, allow_net: bool) -> Path | None:
    """Скачивание референса в кэш; в MOCK/--no-images — только из кэша."""
    cache = Path(config.REPORTS_IMG_CACHE)
    cache.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg"
    path = cache / name
    if path.exists():
        return path
    if not allow_net:
        return None
    try:
        import requests
        r = requests.get(url, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        path.write_bytes(r.content)
        return path
    except Exception:
        return None


def studio_designs(conn, trend_ids: list[str]) -> dict:
    """{trend_id: n_дизайнов} — что уже сгенерировано Студией."""
    try:
        rows = conn.execute(
            f"""SELECT trend_id, COUNT(*) n FROM designs WHERE status='ok'
                AND trend_id IN ({','.join('?' * len(trend_ids))})
                GROUP BY trend_id""", trend_ids).fetchall()
    except Exception:
        return {}
    return {r["trend_id"]: r["n"] for r in rows}


# ─── Построение PDF ──────────────────────────────────────────────────────────

def _fmt(v, kind="int"):
    if v is None:
        return "—"
    if kind == "pct":
        return f"{v:.1%}"
    if kind == "money":
        return f"{v:,.0f} ₽".replace(",", " ")
    return f"{v:,.0f}".replace(",", " ")


def build_report(category: str, db_path: str = None, allow_net: bool = True) -> Path:
    conn = db.connect(db_path or os.environ.get("TRENDS_DB", config.DB_PATH))
    cat_ru = taxonomy.ru("category", category)

    trends = category_trends(conn, category)
    if not trends:
        sys.exit(f"Нет данных по категории {category!r} — проверь --list-categories")
    cat_trend = next((t for t in trends if t["is_category_trend"]), None)
    element_trends = [t for t in trends if not t["is_category_trend"]]

    kws = []
    if cat_trend:
        kws = [k for k in json.loads(cat_trend["wb_keywords"] or "[]") if k.strip()]
    kw_rows = keyword_freqs(conn, kws) if kws else []
    total_cards, top_cards = serp_top(conn, kws) if kws else (None, [])
    qs = q_series(conn, cat_trend["trend_id"]) if cat_trend else []
    refs = podium_refs(conn, category)
    designs_by_trend = studio_designs(conn, [t["trend_id"] for t in trends])

    n_items = conn.execute(
        "SELECT COUNT(*) FROM items WHERE category=? AND confidence>=?",
        (category, config.MIN_ITEM_CONFIDENCE)).fetchone()[0]
    n_looks = conn.execute(
        """SELECT COUNT(DISTINCT look_id) FROM items
           WHERE category=? AND confidence>=?""",
        (category, config.MIN_ITEM_CONFIDENCE)).fetchone()[0]

    out_dir = Path(config.REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")
    out_pdf = out_dir / f"trend_report_{slug}_{date.today().isoformat()}.pdf"

    doc = SimpleDocTemplate(str(out_pdf), pagesize=(K.W, K.H),
                            leftMargin=K.MARGIN, rightMargin=K.MARGIN,
                            topMargin=1.0 * cm, bottomMargin=1.5 * cm)
    story = []

    # ── Обложка ────────────────────────────────────────────────────────────────
    ref_paths = [p for p in (fetch_image(r["image_url"], allow_net) for r in refs[:6]) if p]
    cover_rows = [[Spacer(1, 0.4 * cm)]]
    if ref_paths:
        n = len(ref_paths)
        pw = K.INNER / max(n, 4)
        strip = Table([[K.thumb(p, pw - 2, pw * 1.4) for p in ref_paths]],
                      colWidths=[pw] * n)
        strip.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        cover_rows += [[strip], [Spacer(1, 0.3 * cm)]]
    cover_rows += [
        [Paragraph("ТРЕНД-АНАЛИТИКА · ПОДИУМ → WILDBERRIES",
                   K.sty(size=9, color=K.C_GOLD, align=TA_CENTER, sa=2))],
        [Paragraph(cat_ru.upper(),
                   K.sty(size=34, color=K.C_WHITE, align=TA_CENTER, leading=40, sa=4))],
        [Spacer(1, 0.15 * cm)],
        [Paragraph(f"{n_looks:,} луков · {n_items:,} предметов · "
                   f"{len(element_trends)} трендов в категории".replace(",", " "),
                   K.sty(size=11, color=K.C_GOLD, align=TA_CENTER, sa=2))],
        [Spacer(1, 0.12 * cm)],
        [Paragraph(date.today().strftime("%d.%m.%Y"),
                   K.sty(size=8, color=K.C_SUB, align=TA_CENTER))],
        [Spacer(1, 0.4 * cm)],
    ]
    cover = Table(cover_rows, colWidths=[K.INNER])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), K.C_COVER),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story += [cover, PageBreak()]

    # ── 1. Срез категории ─────────────────────────────────────────────────────
    K.section_header(story, "Раздел 1", f"Срез категории: {cat_ru}")

    stats = [
        ("Луков с категорией (подиум)", _fmt(n_looks)),
        ("Предметов (confidence ≥ %.1f)" % config.MIN_ITEM_CONFIDENCE, _fmt(n_items)),
    ]
    if cat_trend:
        stats += [
            ("Стадия диффузии", cat_trend["stage"] or "—"),
            ("Частотность WB (30 дн.)", _fmt(cat_trend["q_freq"])),
            ("Рост Q м/м", _fmt(cat_trend["q_growth"], "pct")
             if cat_trend["q_growth"] is not None else "—"),
            ("Карточек в выдаче", _fmt(cat_trend["c_cards"])),
            ("Выручка топ-20", _fmt(cat_trend["c_top_revenue"], "money")),
        ]
    tbl = Table([[Paragraph(a, K.ST_BODY), Paragraph(f"<b>{b}</b>", K.ST_BODY)]
                 for a, b in stats], colWidths=[K.INNER * 0.55, K.INNER * 0.45])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), K.C_SURF),
        ("BOX", (0, 0), (-1, -1), 0.5, K.C_LINE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, K.C_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
    story.append(tbl)
    if not cat_trend:
        story.append(Paragraph(
            "Тренд самой категории не заведён (частота не растёт год-к-году) — "
            "метрики WB см. по трендам-элементам ниже.", K.ST_SMALL))

    # Распределение трендов категории по стадиям диффузии
    stage_counts = {}
    for t in element_trends:
        if t["stage"]:
            stage_counts[t["stage"]] = stage_counts.get(t["stage"], 0) + 1
    if stage_counts:
        K.sub_header(story, "Тренды категории по стадиям диффузии")
        total_st = sum(stage_counts.values())
        srows = []
        for stage in config.STAGES:
            n = stage_counts.get(stage, 0)
            if not n:
                continue
            sc = K.STAGE_HEX.get(stage, "#8a8377")
            bar_w = max(4, K.INNER * 0.5 * n / total_st)
            bar = Table([[""]], colWidths=[bar_w], rowHeights=[10])
            bar.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), K.colors.HexColor(sc))]))
            srows.append([
                Paragraph(f'<font color="{sc}"><b>{stage}</b></font>',
                          K.sty(size=8, leading=11)),
                bar,
                Paragraph(f"<b>{n}</b> ({n / total_st:.0%})", K.ST_SMALL)])
        st = Table(srows, colWidths=[K.INNER * 0.3, K.INNER * 0.52, K.INNER * 0.18])
        st.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, -1), "LEFT")]))
        story.append(st)

    # Q-динамика: если у категории нет своего тренда — суммарная по топ-элементам
    if not qs and element_trends:
        merged = {}
        for t in element_trends[:10]:
            for m, v in q_series(conn, t["trend_id"]):
                merged[m] = merged.get(m, 0.0) + v
        qs = sorted(merged.items())[-8:]
        if qs:
            story.append(Paragraph(
                "Q ниже — суммарная частотность WB по топ-10 трендам категории.",
                K.ST_XSML))

    if qs:
        K.sub_header(story, "Динамика запросов WB (частотность за 30-дневные окна)")
        head = [Paragraph(f"<b>{m}</b>", K.ST_XSML) for m, _ in qs]
        vals = [Paragraph(_fmt(v), K.ST_SMALL) for _, v in qs]
        qt = Table([head, vals], colWidths=[K.INNER / len(qs)] * len(qs))
        qt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), K.C_AMBER_L),
            ("BOX", (0, 0), (-1, -1), 0.5, K.C_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        story.append(qt)

    if kw_rows:
        K.sub_header(story, "Ключевые запросы WB (кэш MPStats)")
        rows = [[Paragraph("<b>ключ</b>", K.ST_SMALL),
                 Paragraph("<b>частотность/нед.</b>", K.ST_SMALL)]]
        rows += [[Paragraph(k["keyword"], K.ST_BODY),
                  Paragraph(_fmt(k["freq"]), K.ST_BODY)] for k in kw_rows]
        kt = Table(rows, colWidths=[K.INNER * 0.7, K.INNER * 0.3])
        kt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), K.C_COVER),
            ("TEXTCOLOR", (0, 0), (-1, 0), K.C_WHITE),
            ("BOX", (0, 0), (-1, -1), 0.5, K.C_LINE),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, K.C_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
        story.append(kt)

    if top_cards:
        K.sub_header(story, f"Топ выдачи WB по выручке "
                            f"(всего карточек: {_fmt(total_cards)})")
        rows = [[Paragraph("<b>#</b>", K.ST_SMALL),
                 Paragraph("<b>карточка</b>", K.ST_SMALL),
                 Paragraph("<b>выручка/30дн</b>", K.ST_SMALL)]]
        for i, c in enumerate(top_cards, 1):
            name = str(c.get("name") or c.get("id") or "—")[:60]
            rows.append([Paragraph(str(i), K.ST_BODY),
                         Paragraph(name, K.ST_BODY),
                         Paragraph(_fmt(c.get("revenue"), "money"), K.ST_BODY)])
        ct = Table(rows, colWidths=[K.INNER * 0.06, K.INNER * 0.64, K.INNER * 0.3])
        ct.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), K.C_COVER),
            ("TEXTCOLOR", (0, 0), (-1, 0), K.C_WHITE),
            ("BOX", (0, 0), (-1, -1), 0.5, K.C_LINE),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, K.C_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
        story.append(ct)
    elif cat_trend:
        story.append(Paragraph(
            "Выдача WB не в кэше — запусти python mpstats_client.py collect "
            f"--trend {cat_trend['trend_id']}", K.ST_SMALL))
    story.append(PageBreak())

    # ── 2. Тренды в категории со стадиями ─────────────────────────────────────
    K.section_header(story, "Раздел 2", "Тренды внутри категории: стадии диффузии")
    rows = [[Paragraph(f"<b>{h}</b>", K.sty(size=7, color=K.C_WHITE))
             for h in ("тренд", "измерение", "стадия", "тип",
                       "в категории", "P подиум", "Q WB", "карточек")]]
    for t in element_trends[:28]:
        stage = t["stage"] or "—"
        sc = K.STAGE_HEX.get(stage, "#8a8377")
        rows.append([
            Paragraph(f"<b>{t['name_ru']}</b>", K.sty(size=8, leading=10)),
            Paragraph(t["type_dimension"], K.ST_XSML),
            Paragraph(f'<font color="{sc}"><b>{stage}</b></font>',
                      K.sty(size=7, leading=9)),
            Paragraph(str(t["trend_type"] or "—"), K.ST_XSML),
            Paragraph(f"{t['cat_count']} ({t['cat_share']:.0%})", K.ST_XSML),
            Paragraph(_fmt(t["p_share"], "pct") if t["p_share"] else "—", K.ST_XSML),
            Paragraph(_fmt(t["q_freq"]), K.ST_XSML),
            Paragraph(_fmt(t["c_cards"]), K.ST_XSML),
        ])
    widths = [0.24, 0.11, 0.17, 0.05, 0.12, 0.10, 0.11, 0.10]
    tt = Table(rows, colWidths=[K.INNER * w for w in widths], repeatRows=1)
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), K.C_COVER),
        ("BOX", (0, 0), (-1, -1), 0.5, K.C_LINE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, K.C_LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [K.C_SURF, K.C_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(tt)
    story.append(PageBreak())

    # ── 3. Конкурентное позиционирование ──────────────────────────────────────
    K.section_header(story, "Раздел 3", "Конкурентное позиционирование по стадиям")
    story.append(Paragraph(
        "Куда входить и как — по положению трендов категории на кривой диффузии "
        "инноваций (методика «Адаптация трендов»).", K.ST_SMALL))
    for stage in config.STAGES:
        group = [t for t in element_trends if t["stage"] == stage]
        if not group:
            continue
        sc = K.STAGE_HEX.get(stage, "#8a8377")
        hdr = Table([[Paragraph(
            f"<b>{stage}</b> · {len(group)} трендов · {STAGE_ADVICE.get(stage, '')}",
            K.sty(size=9, color=K.C_WHITE, leading=12))]], colWidths=[K.INNER])
        hdr.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), K.colors.HexColor(sc)),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
        names = "  ·  ".join(
            f"{t['name_ru']} ({t['cat_count']})" for t in group[:10])
        body = Paragraph(names, K.sty(size=8, leading=12, sa=8))
        story.append(KeepTogether([hdr, Spacer(1, 3), body]))
    story.append(PageBreak())

    # ── 4. Референсы + гипотезы модификаций ───────────────────────────────────
    K.section_header(story, "Раздел 4", "Фото-референсы и гипотезы модификаций")
    grid_paths = [(r, fetch_image(r["image_url"], allow_net)) for r in refs]
    grid_paths = [(r, p) for r, p in grid_paths if p]
    if grid_paths:
        n_cols = 4
        pw = (K.INNER - 0.6 * cm) / n_cols
        cells, caps = [], []
        grows = []
        for i in range(0, min(len(grid_paths), 8), n_cols):
            chunk = grid_paths[i:i + n_cols]
            cells = [K.thumb(p, pw - 4, (pw - 4) * 1.4) for _, p in chunk]
            caps = [Paragraph(f"{r['designer']} · {r['season_label']}", K.ST_CAP)
                    for r, _ in chunk]
            while len(cells) < n_cols:
                cells.append(Spacer(pw, 1))
                caps.append(Spacer(pw, 1))
            grows += [cells, caps]
        gt = Table(grows, colWidths=[pw + 0.15 * cm] * n_cols)
        gt.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(gt)
    else:
        story.append(Paragraph(
            "Референсы не скачаны (MOCK/--no-images и пустой кэш) — "
            "см. карточки трендов в UI.", K.ST_SMALL))

    K.sub_header(story, "Гипотезы модификаций (топ трендов категории)")
    for t in element_trends[:8]:
        stage = t["stage"] or "—"
        sc = K.STAGE_HEX.get(stage, "#8a8377")
        n_des = designs_by_trend.get(t["trend_id"], 0)
        parts = [f"<b>{t['name_ru']}</b> "
                 f'<font color="{sc}">[{stage}]</font> — '
                 f"{STAGE_ADVICE.get(stage, 'стадия не определена')}."]
        if t["rationale"]:
            parts.append(f'<font color="#8a8377" size="7">{t["rationale"]}</font>')
        if n_des:
            parts.append(f'<font color="#9c4a3f" size="7">Студия: {n_des} '
                         f"сгенерированных вариантов (см. /trends/{t['trend_id']})</font>")
        blk = Table([[Paragraph("<br/>".join(parts), K.sty(size=8, leading=11))]],
                    colWidths=[K.INNER])
        blk.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), K.C_SURF),
            ("BOX", (0, 0), (-1, -1), 0.5, K.C_LINE),
            ("LINEBEFORE", (0, 0), (0, -1), 2.5, K.colors.HexColor(sc)),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
        story += [blk, Spacer(1, 0.12 * cm)]

    # ── 5. Закупочный бриф (Фаза 7) ───────────────────────────────────────────
    from reports.purchase_brief import (append_brief_section, build_brief_data,
                                        export_excel)
    brief = build_brief_data(conn, category, element_trends)
    out_xlsx = None
    if brief:
        story.append(PageBreak())
        append_brief_section(story, brief, cat_ru)
        out_xlsx = export_excel(brief, category, out_dir)

    footer = (f"ТРЕНД-АНАЛИТИКА · {cat_ru.upper()} · "
              f"{date.today().strftime('%d.%m.%Y')}").upper()
    doc.build(story, canvasmaker=K.make_canvas(footer))
    conn.close()
    print(f"PDF: {out_pdf}")
    if out_xlsx:
        print(f"Excel (закупка): {out_xlsx}")
    return out_pdf


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--category", help="EN-категория из taxonomy (например Dress)")
    ap.add_argument("--list-categories", action="store_true")
    ap.add_argument("--no-images", action="store_true",
                    help="не качать фото-референсы (использовать только кэш)")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    if args.list_categories:
        conn = db.connect(args.db or config.DB_PATH)
        for r in conn.execute(
                """SELECT category, COUNT(*) n FROM items
                   WHERE category IS NOT NULL AND category != ''
                   GROUP BY category ORDER BY n DESC"""):
            print(f"  {r['category']:24s} {r['n']:6d} предметов "
                  f"({taxonomy.ru('category', r['category'])})")
        return
    if not args.category:
        ap.error("нужен --category или --list-categories")
    build_report(args.category, db_path=args.db,
                 allow_net=not (args.no_images or MOCK))


if __name__ == "__main__":
    main()
