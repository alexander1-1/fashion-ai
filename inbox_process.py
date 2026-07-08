"""
inbox_process.py — обработчик папок inbox/ (разделы 3.2–3.4, Фаза 4).

Полуручной режим для источников без надёжного API: всё, что попало в папку,
платформа подхватывает.

  inbox/instagram/          фото/скриншоты из ленты → influencer, source='instagram'
  inbox/tiktok/             скриншоты выдачи        → influencer, source='tiktok'
  inbox/brands/{slug}/      фото новинок бренда     → level из brand_arrivals.BRANDS
  inbox/telegram/{channel}/ ручные дозаливки        → influencer, source='tg:{channel}'
  inbox/pinterest/*.csv     экспорт trends.pinterest.com → social_search,
                            source='pinterest' (ключи матчатся с wb_keywords)

Дата фото = mtime файла (для ручных заливок); имя файла вида
YYYY-MM-DD_*.jpg переопределяет дату. Дубликаты отсекаются по sha1.

CLI:
    python inbox_process.py            # зарегистрировать всё новое
    python inbox_process.py --tag      # + сразу тегировать pending
    python inbox_process.py --tag --sample 20
"""

import argparse
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path

import config
import db
from brand_arrivals import BRAND_BY_SLUG
from photo_tagger import register_photo, tag_pending

INBOX = Path(config.INBOX_DIR)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DATE_IN_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _file_date(p: Path) -> str:
    m = DATE_IN_NAME.match(p.name)
    if m:
        return m.group(1)
    return date.fromtimestamp(p.stat().st_mtime).isoformat()


def _register_dir(conn, folder: Path, level: str, source: str) -> int:
    if not folder.is_dir():
        return 0
    n = 0
    for p in sorted(folder.rglob("*")):
        if p.suffix.lower() not in IMG_EXT or not p.is_file():
            continue
        pid = register_photo(conn, p, level=level, source=source,
                             photo_date=_file_date(p))
        if pid:
            n += 1
    return n


def register_images(conn) -> dict[str, int]:
    stats: dict[str, int] = {}

    stats["instagram"] = _register_dir(
        conn, INBOX / "instagram", "influencer", "instagram")
    stats["tiktok"] = _register_dir(
        conn, INBOX / "tiktok", "influencer", "tiktok")

    brands_dir = INBOX / "brands"
    if brands_dir.is_dir():
        for sub in sorted(brands_dir.iterdir()):
            if not sub.is_dir():
                continue
            brand = BRAND_BY_SLUG.get(sub.name)
            if not brand:
                print(f"  ! inbox/brands/{sub.name}: нет в реестре брендов "
                      "(brand_arrivals.BRANDS) — пропуск")
                continue
            n = _register_dir(conn, sub, brand["level"], sub.name)
            if n:
                stats[f"brands/{sub.name}"] = n

    tg_dir = INBOX / "telegram"
    if tg_dir.is_dir():
        for sub in sorted(tg_dir.iterdir()):
            if sub.is_dir():
                n = _register_dir(conn, sub, "influencer", f"tg:{sub.name}")
                if n:
                    stats[f"telegram/{sub.name}"] = n
    return stats


# ─── Pinterest Trends CSV ────────────────────────────────────────────────────
# Экспорт trends.pinterest.com бывает двух форм:
#   long:  keyword, date, value (колонки распознаются по заголовку)
#   wide:  первая колонка — ключ/дата, остальные — даты/ключи (матрица)

KEY_COLS = ("trend", "keyword", "query", "запрос", "ключ", "фраза")
VAL_COLS = ("volume", "value", "interest", "счёт", "объ")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _keyword_index(conn) -> dict[str, str]:
    idx = {}
    for t in conn.execute("SELECT trend_id, name_ru, wb_keywords FROM trends"):
        idx[t["name_ru"].strip().lower()] = t["trend_id"]
        for kw in json.loads(t["wb_keywords"] or "[]"):
            idx[kw.strip().lower()] = t["trend_id"]
    return idx


def _parse_num(raw) -> float | None:
    s = str(raw or "").replace("\xa0", "").replace(" ", "").replace(",", ".").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def _norm_date(s: str) -> str | None:
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def import_pinterest_csv(conn, path: Path, idx: dict, dry: bool) -> tuple[int, set]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(fh, dialect))
    if not rows:
        return 0, set()

    header = [c.strip() for c in rows[0]]
    low = [c.lower() for c in header]
    default_date = date.fromtimestamp(path.stat().st_mtime).isoformat()

    triples: list[tuple[str, str, float]] = []  # (keyword, date, value)

    kcol = next((i for i, c in enumerate(low)
                 if any(k in c for k in KEY_COLS)), None)
    date_cols = [i for i, c in enumerate(header) if _norm_date(c)]

    if kcol is not None and date_cols:            # wide: ключ + колонки-даты
        for row in rows[1:]:
            if len(row) <= kcol:
                continue
            kw = row[kcol].strip().lower()
            for i in date_cols:
                v = _parse_num(row[i]) if i < len(row) else None
                if kw and v is not None:
                    triples.append((kw, _norm_date(header[i]), v))
    elif kcol is not None:                        # long: ключ, [дата], значение
        vcol = next((i for i, c in enumerate(low)
                     if any(k in c for k in VAL_COLS)), None)
        dcol = next((i for i, c in enumerate(low) if "date" in c or "дата" in c), None)
        if vcol is None:
            print(f"  {path.name}: не нашёл колонку значения в {header}")
            return 0, set()
        for row in rows[1:]:
            if len(row) <= max(kcol, vcol):
                continue
            kw = row[kcol].strip().lower()
            v = _parse_num(row[vcol])
            d = _norm_date(row[dcol]) if dcol is not None and len(row) > dcol \
                and row[dcol] else None
            if kw and v is not None:
                triples.append((kw, d or default_date, v))
    else:
        print(f"  {path.name}: не распознал формат (заголовок: {header[:5]}…)")
        return 0, set()

    matched, unmatched = 0, set()
    per_trend_date: dict[tuple[str, str], float] = {}
    for kw, d, v in triples:
        tid = idx.get(kw)
        if not tid:
            unmatched.add(kw)
            continue
        per_trend_date[(tid, d)] = max(per_trend_date.get((tid, d), 0.0), v)
        matched += 1

    if not dry:
        for (tid, d), v in per_trend_date.items():
            conn.execute(
                """DELETE FROM signals WHERE trend_id=? AND level='social_search'
                   AND source='pinterest' AND date=?""", (tid, d))
            conn.execute(
                """INSERT INTO signals (trend_id, level, source, date, value, url)
                   VALUES (?,'social_search','pinterest',?,?,?)""",
                (tid, d, v, path.name))
        conn.commit()
    return matched, unmatched


def process_pinterest(conn, dry: bool) -> int:
    folder = INBOX / "pinterest"
    folder.mkdir(parents=True, exist_ok=True)
    files = sorted(folder.glob("*.csv"))
    if not files:
        return 0
    idx = _keyword_index(conn)
    processed = folder / "processed"
    total = 0
    all_unmatched: set[str] = set()
    for f in files:
        n, unmatched = import_pinterest_csv(conn, f, idx, dry)
        total += n
        all_unmatched |= unmatched
        print(f"  pinterest/{f.name}: строк сопоставлено {n}"
              + (f", не сопоставлено {len(unmatched)}" if unmatched else ""))
        if not dry and n:
            processed.mkdir(exist_ok=True)
            f.rename(processed / f.name)
    if all_unmatched:
        print("  Не сопоставлены (пополни wb_keywords при необходимости): "
              + ", ".join(sorted(all_unmatched)[:15]))
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", action="store_true",
                    help="сразу тегировать pending-фото")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = db.init_db()
    for sub in ("instagram", "tiktok", "brands", "telegram", "pinterest", "wildbox"):
        (INBOX / sub).mkdir(parents=True, exist_ok=True)

    print("Регистрация фото из inbox/:")
    stats = register_images(conn)
    for k, v in stats.items():
        print(f"  {k}: +{v}")
    if not any(stats.values()):
        print("  новых фото нет")

    print("\nPinterest CSV:")
    n_pin = process_pinterest(conn, args.dry_run)
    if not n_pin:
        print("  нет CSV в inbox/pinterest/")

    n_pending = conn.execute(
        "SELECT COUNT(*) FROM ext_photos WHERE status='pending'").fetchone()[0]
    print(f"\nВ очереди на тегирование: {n_pending}")
    if args.tag and n_pending:
        print("\nТегирование:")
        s = tag_pending(conn, args.sample)
        print(f"Итого: tagged={s['tagged']} errors={s['errors']} "
              f"signals={s['signals']}")
    elif n_pending:
        print("Запусти: python photo_tagger.py tag" +
              (f" --sample {args.sample}" if args.sample else ""))


if __name__ == "__main__":
    main()
