"""
migrate_csv_to_db.py — миграция enriched_looks_v3.csv → trend_signals.db.

Идемпотентно: лук с существующим image_url перезаписывается (теги обновляются).

Запуск:
    python migrate_csv_to_db.py [--csv output/enriched_looks_v3.csv] [--db trend_signals.db]
"""

import argparse
import csv
import json
import sys

import db


def migrate(csv_path: str, db_path: str) -> None:
    conn = db.init_db(db_path)
    inserted = updated = skipped = items_total = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            show = row.get("show", "").strip()
            image_url = row.get("image_url", "").strip()
            if not show or not image_url:
                skipped += 1
                continue

            try:
                items = json.loads(row.get("items_json") or "[]")
            except json.JSONDecodeError:
                skipped += 1
                continue

            family, year, label = db.parse_season(show)
            style_tags = [s.strip() for s in (row.get("style_tags") or "").split(",") if s.strip()]

            old = conn.execute(
                "SELECT look_id FROM looks WHERE image_url = ?", (image_url,)
            ).fetchone()
            if old:
                conn.execute("DELETE FROM items WHERE look_id = ?", (old["look_id"],))
                conn.execute(
                    """UPDATE looks SET designer=?, show_name=?, season_family=?,
                       season_year=?, season_label=?, look_number=?, style_tags=?, confidence=?
                       WHERE look_id=?""",
                    (row["designer"], show, family, year, label,
                     int(row["look_number"] or 0), json.dumps(style_tags, ensure_ascii=False),
                     float(row["confidence"] or 0), old["look_id"]),
                )
                look_id = old["look_id"]
                updated += 1
            else:
                cur = conn.execute(
                    """INSERT INTO looks (designer, show_name, season_family, season_year,
                       season_label, look_number, image_url, style_tags, confidence)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (row["designer"], show, family, year, label,
                     int(row["look_number"] or 0), image_url,
                     json.dumps(style_tags, ensure_ascii=False),
                     float(row["confidence"] or 0)),
                )
                look_id = cur.lastrowid
                inserted += 1

            for it in items:
                conn.execute(
                    """INSERT INTO items (look_id, category, pattern, materials,
                       silhouette, construction, decoration, colors, confidence)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (look_id, it.get("category"), it.get("pattern"),
                     db.json_or_empty(it.get("materials")),
                     db.json_or_empty(it.get("silhouette")),
                     db.json_or_empty(it.get("construction")),
                     db.json_or_empty(it.get("decoration")),
                     db.json_or_empty(it.get("colors")),
                     float(it.get("confidence") or 0)),
                )
                items_total += 1

    conn.commit()
    n_looks = conn.execute("SELECT COUNT(*) FROM looks").fetchone()[0]
    n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"Луков: +{inserted} новых, {updated} обновлено, {skipped} пропущено")
    print(f"Предметов записано за прогон: {items_total}")
    print(f"Итого в БД: {n_looks} луков, {n_items} предметов")

    print("\nЛуки по сезонам:")
    for r in conn.execute(
        """SELECT season_family, season_year, COUNT(*) n FROM looks
           GROUP BY 1,2 ORDER BY season_family, season_year"""):
        print(f"  {r['season_family']:26s} {r['season_year']}  {r['n']:5d}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="output/enriched_looks_v3.csv")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    import config
    migrate(args.csv, args.db or config.DB_PATH)
