"""Тесты mpstats_client (Фаза 3): агрегация окон Q, кэш, MOCK-режим.

Запуск: pytest tests/test_mpstats.py (или python tests/test_mpstats.py)
"""
import json
import os
import sys
import pathlib
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import db
import mpstats_client as mc


def _weekly(vals, d0=None):
    d0 = d0 or date(2026, 7, 6)
    return [{"date": (d0 - timedelta(days=7 * i)).isoformat(), "frequency": v}
            for i, v in enumerate(vals)]


def test_q_windows_sums_weeks_into_30d_windows():
    # Окно k покрывает (anchor-30(k+1), anchor-30k]: точки не теряются
    # и не считаются дважды. В окно 0 попадают дни 0..28 → 5 недельных точек,
    # в окно 1 — дни 35..56 → 4 точки (неизбежно для 30 дней при шаге 7).
    w = mc.q_windows(_weekly([100] * 9), n=2, window_days=30)
    assert len(w) == 2
    assert w[0][0] == "2026-07-06"        # конец окна = свежая точка данных
    assert w[0][1] == 500                 # недели -0,-7,-14,-21,-28
    assert w[1][1] == 400                 # недели -35,-42,-49,-56


def test_q_windows_empty():
    assert mc.q_windows([]) == []


def test_q_windows_anchor_is_latest_data_not_today():
    w = mc.q_windows(_weekly([50, 50], d0=date(2026, 1, 5)), n=1)
    assert w[0][0] == "2026-01-05"


def test_cached_call_hits_cache_without_network(tmp_path=None):
    conn = db.init_db(":memory:")
    today = date.today().isoformat()
    conn.execute("INSERT INTO wb_metrics (key,kind,date,payload) VALUES (?,?,?,?)",
                 ("k1", "keyword", today, json.dumps({"ok": 1})))
    calls = []
    out = mc.cached_call(conn, "k1", "keyword", lambda: calls.append(1) or {})
    assert out == {"ok": 1} and not calls   # fetch не вызывался


def test_mock_mode_uses_stale_cache_and_never_fetches():
    conn = db.init_db(":memory:")
    conn.execute("INSERT INTO wb_metrics (key,kind,date,payload) VALUES (?,?,?,?)",
                 ("k2", "keyword", "2020-01-01", json.dumps([1, 2])))
    os.environ["MOCK"] = "1"
    try:
        assert mc.cached_call(conn, "k2", "keyword", lambda: 1 / 0) == [1, 2]
        try:
            mc.cached_call(conn, "нет-такого", "keyword", lambda: 1 / 0)
            assert False, "должен был упасть без фикстуры"
        except mc.MpstatsError:
            pass
    finally:
        os.environ.pop("MOCK")


def test_trend_keywords_fallback_to_name_ru():
    t = {"wb_keywords": "[]", "name_ru": "Клетка"}
    assert mc.trend_keywords(t) == ["клетка"]
    t = {"wb_keywords": '["рубашка в клетку", " "]', "name_ru": "Клетка"}
    assert mc.trend_keywords(t) == ["рубашка в клетку"]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  OK   {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
