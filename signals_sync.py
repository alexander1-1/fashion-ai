"""
signals_sync.py — перенос сигналов MPStats/WB между локальной БД и продом.
===========================================================================
Проблема: trend_signals.db в .gitignore и пересоздаётся на Railway из CSV,
поэтому собранные локально сигналы (Q, карточки, выручка) и wb_keywords
не доезжали до прода — все тренды показывались «ИННОВАТОРАМИ».

Решение: лёгкий экспорт в git-файл + импорт при сборке на Railway.

Локально (после каждого mpstats_client.py collect):
    python3 signals_sync.py export     # → output/wb_signals_export.json.gz
    git add output/wb_signals_export.json.gz && git commit && git push

На Railway (в Dockerfile, автоматически):
    python signals_sync.py import      # после autoregister, перед score
"""

import gzip
import json
import sys

import config
import db

EXPORT_PATH = "output/wb_signals_export.json.gz"


def export(db_path=None):
    conn = db.init_db(db_path or config.DB_PATH)
    data = {
        "signals": [dict(r) for r in conn.execute(
            """SELECT trend_id, level, source, date, value FROM signals
               WHERE source LIKE 'mpstats%'""")],
        "wb_metrics": [dict(r) for r in conn.execute(
            "SELECT key, kind, date, payload FROM wb_metrics")],
        "wb_keywords": {r["trend_id"]: r["wb_keywords"] for r in conn.execute(
            "SELECT trend_id, wb_keywords FROM trends WHERE wb_keywords IS NOT NULL "
            "AND wb_keywords != '' AND wb_keywords != '[]'")},
    }
    with gzip.open(EXPORT_PATH, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"Экспорт: {len(data['signals'])} сигналов, "
          f"{len(data['wb_metrics'])} кэшей WB, "
          f"{len(data['wb_keywords'])} наборов ключей → {EXPORT_PATH}")


def import_(db_path=None):
    import os
    if not os.path.exists(EXPORT_PATH):
        print(f"{EXPORT_PATH} не найден — пропускаю импорт сигналов")
        return
    conn = db.init_db(db_path or config.DB_PATH)
    with gzip.open(EXPORT_PATH, "rt", encoding="utf-8") as f:
        data = json.load(f)

    # Сигналы только для трендов, существующих в этой БД (autoregister мог
    # завести другой набор — например, тренд выпал из порогов).
    known = {r[0] for r in conn.execute("SELECT trend_id FROM trends")}
    rows = [(s["trend_id"], s["level"], s["source"], s["date"], s["value"])
            for s in data["signals"] if s["trend_id"] in known]
    skipped = len(data["signals"]) - len(rows)

    conn.execute("DELETE FROM signals WHERE source LIKE 'mpstats%'")
    conn.executemany(
        "INSERT INTO signals (trend_id, level, source, date, value) VALUES (?,?,?,?,?)",
        rows)

    conn.execute("DELETE FROM wb_metrics")
    conn.executemany(
        "INSERT INTO wb_metrics (key, kind, date, payload) VALUES (?,?,?,?)",
        [(m["key"], m["kind"], m["date"], m["payload"]) for m in data["wb_metrics"]])

    for trend_id, kws in data["wb_keywords"].items():
        if trend_id in known:
            conn.execute("UPDATE trends SET wb_keywords=? WHERE trend_id=?", (kws, trend_id))

    conn.commit()
    print(f"Импорт: {len(rows)} сигналов ({skipped} пропущено — тренд не заведён), "
          f"{len(data['wb_metrics'])} кэшей WB, ключи обновлены")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db_arg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--db" else None
    if cmd == "export":
        export(db_arg)
    elif cmd == "import":
        import_(db_arg)
    else:
        sys.exit("Использование: python signals_sync.py export|import [--db path]")
