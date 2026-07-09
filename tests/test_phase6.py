"""Тесты Фазы 6: Студия (studio_gen, MOCK) и отчёты (reports/trend_report).
Без сети и без платных вызовов. Запуск: pytest tests/test_phase6.py"""

import json
import os
import sys
from pathlib import Path

os.environ["MOCK"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import config
import db


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    """Мини-база: 2 сезона луков, предметы со stand collar, тренд со скорингом."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "STUDIO_DIR", str(tmp_path / "studio"))
    monkeypatch.setattr(config, "REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(config, "REPORTS_IMG_CACHE", str(tmp_path / "img_cache"))
    c = db.init_db(config.DB_PATH)
    for i, (year, n) in enumerate([(2025, 2), (2026, 2)]):
        for j in range(n):
            lid = year * 10 + j
            c.execute(
                """INSERT INTO looks (look_id, designer, show_name, season_family,
                   season_year, season_label, image_url, style_tags, confidence)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (lid, "TestBrand", f"Fall {year}", "fall-rtw", year,
                 f"FW{year % 100}", f"http://x/{lid}.jpg", '["Minimalism"]', 0.9))
            c.execute(
                """INSERT INTO items (look_id, category, pattern, materials,
                   silhouette, construction, decoration, colors, confidence)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (lid, "Knitwear/Cardigan", "Solid", '["Chunky Knit"]',
                 '["Relaxed"]', '["Stand Collar"]', "[]", '["Black"]', 0.9))
    c.execute(
        """INSERT INTO trends (trend_id, name_ru, name_en, type_dimension, field,
           element, wb_keywords, status, origin)
           VALUES ('construction--stand-collar','Воротник-стойка','Stand Collar',
                   'крой','construction','Stand Collar',
                   '["джемпер воротник стойка"]','active','manual')""")
    c.execute(
        """INSERT INTO trend_scores (trend_id, date, p_share, q_freq, stage,
           trend_type, rationale)
           VALUES ('construction--stand-collar','2026-07-01',0.036,1200,
                   'РАННИЕ ПОСЛЕДОВАТЕЛИ',1,'тест')""")
    c.commit()
    yield c
    c.close()


# ─── Студия ──────────────────────────────────────────────────────────────────

def test_designs_table_created(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(designs)")}
    assert {"design_id", "trend_id", "image_prompt", "tech_spec",
            "image_path", "status"} <= cols


def test_mock_generation_creates_designs_and_pngs(conn):
    import studio_gen
    created = studio_gen.generate_for_trend(conn, "construction--stand-collar")
    assert len(created) == config.STUDIO_N_VARIANTS
    for d in created:
        assert d["status"] == "ok"
        assert d["model"] == "mock"
        assert d["stage"] == "РАННИЕ ПОСЛЕДОВАТЕЛИ"
        assert Path(d["image_path"]).exists()
        assert "Stand Collar" in d["image_prompt"]
    n = conn.execute("SELECT COUNT(*) FROM designs").fetchone()[0]
    assert n == config.STUDIO_N_VARIANTS


def test_mock_brief_has_prompts_and_techspec(conn):
    import studio_gen
    t = conn.execute("SELECT * FROM trends").fetchone()
    s = conn.execute("SELECT * FROM trend_scores").fetchone()
    brief = studio_gen.build_brief(t, s, n=4)
    assert len(brief["image_prompts"]) == 4
    assert len(set(brief["image_prompts"])) == 4          # варианты различаются
    assert brief["tech_spec"]["category"]


def test_techspec_text_contains_fields(conn):
    import studio_gen
    studio_gen.generate_for_trend(conn, "construction--stand-collar", n=1)
    d = conn.execute("SELECT * FROM designs LIMIT 1").fetchone()
    text = studio_gen.techspec_text(d)
    for token in ("ТЗ КОНСТРУКТОРУ", "Категория", "Крой", "Промпт изображения"):
        assert token in text


def test_unknown_trend_raises(conn):
    import studio_gen
    with pytest.raises(ValueError):
        studio_gen.generate_for_trend(conn, "no--such-trend")


# ─── Отчёты ──────────────────────────────────────────────────────────────────

def test_category_trends_cooccurrence(conn):
    from reports.trend_report import category_trends
    trends = category_trends(conn, "Knitwear/Cardigan")
    tids = [t["trend_id"] for t in trends]
    assert "construction--stand-collar" in tids
    t = next(t for t in trends if t["trend_id"] == "construction--stand-collar")
    assert t["cat_count"] == 4        # все 4 предмета категории с элементом
    assert t["stage"] == "РАННИЕ ПОСЛЕДОВАТЕЛИ"


def test_build_report_creates_pdf(conn):
    from reports.trend_report import build_report
    out = build_report("Knitwear/Cardigan", db_path=config.DB_PATH,
                       allow_net=False)
    assert out.exists()
    assert out.stat().st_size > 5_000
    assert out.read_bytes()[:5] == b"%PDF-"


def test_report_shows_studio_designs(conn):
    import studio_gen
    from reports.trend_report import studio_designs
    studio_gen.generate_for_trend(conn, "construction--stand-collar", n=2)
    by_trend = studio_designs(conn, ["construction--stand-collar"])
    assert by_trend == {"construction--stand-collar": 2}
