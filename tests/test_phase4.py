"""Тесты Фазы 4: ext_photos → signals, pytrends-агрегация, Pinterest CSV,
channels.txt. Без сети и без платных вызовов (MOCK). Запуск: pytest tests/test_phase4.py"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
os.environ["MOCK"] = "1"

import db
import photo_tagger as pt
from gtrends import monthly_series
from inbox_process import import_pinterest_csv, _keyword_index
from tg_collect import read_channels


def _conn():
    conn = db.init_db(":memory:")
    conn.execute(
        """INSERT INTO trends (trend_id, name_ru, name_en, type_dimension, field,
           element, wb_keywords, status, origin)
           VALUES ('construction--stand-collar','воротник-стойка','Stand Collar',
                   'крой','construction','Stand Collar',
                   '["воротник стойка"]','active','manual')""")
    conn.execute(
        """INSERT INTO trends (trend_id, name_ru, name_en, type_dimension, field,
           element, wb_keywords, status, origin)
           VALUES ('category--cardigan','кардиган','Cardigan',
                   'изделие','category','Cardigan',
                   '["кардиган"]','active','manual')""")
    conn.commit()
    return conn


def _tmp_photo(content: bytes = b"x" * 10) -> pathlib.Path:
    f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    f.write(content)
    f.close()
    return pathlib.Path(f.name)


# ─── ext_photos: регистрация и дедуп ─────────────────────────────────────────

def test_register_and_sha1_dedup():
    conn = _conn()
    p1, p2 = _tmp_photo(b"same-bytes"), _tmp_photo(b"same-bytes")
    assert pt.register_photo(conn, p1, "influencer", "tg:test", "2026-07-01")
    # другой путь, те же байты → дубликат
    assert pt.register_photo(conn, p2, "influencer", "tg:test", "2026-07-02") is None
    # повторно тот же путь → дубликат
    assert pt.register_photo(conn, p1, "influencer", "tg:test", "2026-07-01") is None
    assert conn.execute("SELECT COUNT(*) FROM ext_photos").fetchone()[0] == 1


# ─── Теги → сигналы ──────────────────────────────────────────────────────────

TAGS = {
    "styles": ["Minimalism"],
    "items": [
        {"category": "Cardigan", "pattern": "Solid",
         "materials": ["Chunky Knit"], "silhouette": [],
         "construction": ["Stand Collar"], "decoration": [],
         "colors": ["Black"], "confidence": 0.9},
        {"category": "Dress", "pattern": "Solid", "materials": [],
         "silhouette": [], "construction": ["Stand Collar"], "decoration": [],
         "colors": [], "confidence": 0.3},  # ниже порога — не считается
    ],
    "confidence": 0.3,
}


def test_photo_elements_confidence_filter():
    els = pt._photo_elements(TAGS)
    assert ("category", "Cardigan") in els
    assert ("construction", "Stand Collar") in els
    assert ("styles", "Minimalism") in els
    assert ("category", "Dress") not in els  # confidence 0.3 < 0.6


def test_signals_written_and_deduped():
    conn = _conn()
    p = _tmp_photo(b"photo-1")
    pt.register_photo(conn, p, "influencer", "tg:rogov24", "2026-07-01",
                      url="https://t.me/rogov24/1")
    conn.execute("UPDATE ext_photos SET tags=?, confidence=0.9, status='tagged'",
                 (json.dumps(TAGS),))
    conn.commit()

    n_ph, n_sig = pt.rebuild_signals(conn)
    assert n_ph == 1
    assert n_sig == 2  # cardigan + stand collar (Minimalism-тренда нет в БД)
    rows = conn.execute(
        "SELECT trend_id, level, source, value FROM signals").fetchall()
    assert {r["trend_id"] for r in rows} == \
        {"category--cardigan", "construction--stand-collar"}
    assert all(r["level"] == "influencer" and r["value"] == 1 for r in rows)

    # повторный прогон не дублирует
    pt.rebuild_signals(conn)
    assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 2


def test_metrics_pick_up_influencer_signals():
    from trends import collect_metrics
    conn = _conn()
    p = _tmp_photo(b"photo-2")
    pt.register_photo(conn, p, "influencer", "tg:test", "2026-07-01")
    conn.execute("UPDATE ext_photos SET tags=?, confidence=0.9, status='tagged'",
                 (json.dumps(TAGS),))
    conn.commit()
    pt.rebuild_signals(conn)
    # дата фото свежая относительно сегодня? возьмём сигнал на сегодня
    from datetime import date
    conn.execute("UPDATE signals SET date=?", (date.today().isoformat(),))
    conn.commit()
    m = collect_metrics(conn, "category--cardigan")
    assert m["i"] == 1 and m["m"] == 0


# ─── gtrends: месячная агрегация ─────────────────────────────────────────────

def test_monthly_series():
    pts = [{"date": "2026-05-03", "value": 10}, {"date": "2026-05-10", "value": 20},
           {"date": "2026-06-07", "value": 40}]
    months = monthly_series(pts)
    assert months == [("2026-05-10", 15.0), ("2026-06-07", 40.0)]


# ─── Pinterest CSV (long и wide) ─────────────────────────────────────────────

def _csv(tmp_text: str) -> pathlib.Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                                    encoding="utf-8")
    f.write(tmp_text)
    f.close()
    return pathlib.Path(f.name)


def test_pinterest_long_format():
    conn = _conn()
    path = _csv("keyword,date,volume\n"
                "воротник стойка,2026-06-01,55\n"
                "кардиган,2026-06-01,80\n"
                "неизвестный ключ,2026-06-01,10\n")
    n, unmatched = import_pinterest_csv(conn, path, _keyword_index(conn), dry=False)
    assert n == 2 and unmatched == {"неизвестный ключ"}
    rows = conn.execute(
        "SELECT trend_id, value FROM signals WHERE source='pinterest'").fetchall()
    assert {(r["trend_id"], r["value"]) for r in rows} == \
        {("construction--stand-collar", 55.0), ("category--cardigan", 80.0)}


def test_pinterest_wide_format():
    conn = _conn()
    path = _csv("Trend,2026-05-01,2026-06-01\n"
                "кардиган,30,60\n")
    n, _ = import_pinterest_csv(conn, path, _keyword_index(conn), dry=False)
    assert n == 2
    rows = conn.execute(
        """SELECT date, value FROM signals WHERE source='pinterest'
           ORDER BY date""").fetchall()
    assert [(r["date"], r["value"]) for r in rows] == \
        [("2026-05-01", 30.0), ("2026-06-01", 60.0)]


def test_pinterest_name_ru_matches():
    conn = _conn()
    idx = _keyword_index(conn)
    assert idx["воротник-стойка"] == "construction--stand-collar"  # name_ru
    assert idx["воротник стойка"] == "construction--stand-collar"  # wb_keyword


# ─── channels.txt ────────────────────────────────────────────────────────────

def test_read_channels():
    channels = read_channels(str(pathlib.Path(__file__).parent.parent / "channels.txt"))
    assert len(channels) == 18
    assert "rogov24" in channels and "theblueprintnews" in channels
    assert all(" " not in c and not c.startswith("@") for c in channels)
