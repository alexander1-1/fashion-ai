"""
wildbox_import.py — импорт CSV-экспортов Wildbox из inbox/wildbox/ (п. 5 инструкции).

Wildbox остаётся ручной перепроверкой MPStats: раз в неделю экспорт
«трендовых запросов» кладётся в inbox/wildbox/*.csv, скрипт импортирует
его в signals (level='wb_query', source='wildbox').

Формат CSV гибкий: колонки распознаются по заголовку —
  ключ:    запрос | ключ | фраза | keyword | query
  частота: частот* | frequency | freq | запросов
  дата:    дата | date (необязательна; иначе — дата изменения файла)

Сопоставление ключ → тренд: точное совпадение (без регистра) с одним из
wb_keywords тренда. Несопоставленные ключи выводятся списком — это сигнал
пополнить wb_keywords.

CLI:
    python wildbox_import.py             # импорт + перенос в processed/
    python wildbox_import.py --dry-run   # показать, что будет импортировано
"""

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path

import db

INBOX = Path("inbox/wildbox")

KEY_COLS = ("запрос", "ключ", "фраза", "keyword", "query")
FREQ_COLS = ("частот", "frequency", "freq", "запросов")
DATE_COLS = ("дата", "date")


def _find_col(header: list[str], candidates: tuple) -> str | None:
    for col in header:
        low = col.strip().lower()
        if any(low.startswith(c) or c in low for c in candidates):
            return col
    return None


def _keyword_index(conn) -> dict[str, str]:
    """ключ (lowercase) → trend_id по wb_keywords всех трендов."""
    idx = {}
    for t in conn.execute("SELECT trend_id, wb_keywords FROM trends"):
        for kw in json.loads(t["wb_keywords"] or "[]"):
            idx[kw.strip().lower()] = t["trend_id"]
    return idx


def _parse_freq(raw: str) -> float | None:
    s = str(raw).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def import_file(conn, path: Path, idx: dict, dry: bool) -> tuple[int, list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        reader = csv.DictReader(fh, dialect=dialect)
        header = reader.fieldnames or []
        kcol = _find_col(header, KEY_COLS)
        fcol = _find_col(header, FREQ_COLS)
        dcol = _find_col(header, DATE_COLS)
        if not kcol or not fcol:
            print(f"  {path.name}: не нашёл колонки ключа/частоты в {header}")
            return 0, []

        default_date = date.fromtimestamp(path.stat().st_mtime).isoformat()
        imported, unmatched = 0, []
        # Частотности ключей одного тренда на одну дату суммируются
        # (wb_query = частотность тренда, как в mpstats_client).
        totals: dict[tuple[str, str], float] = {}
        for row in reader:
            kw = (row.get(kcol) or "").strip().lower()
            freq = _parse_freq(row.get(fcol) or "")
            if not kw or freq is None:
                continue
            trend_id = idx.get(kw)
            if not trend_id:
                unmatched.append(kw)
                continue
            d = default_date
            if dcol and row.get(dcol):
                for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        d = datetime.strptime(row[dcol].strip(), fmt).date().isoformat()
                        break
                    except ValueError:
                        pass
            totals[(trend_id, d)] = totals.get((trend_id, d), 0.0) + freq
            imported += 1
        if not dry:
            for (trend_id, d), freq in totals.items():
                conn.execute(
                    """DELETE FROM signals WHERE trend_id=? AND level='wb_query'
                       AND source='wildbox' AND date=?""", (trend_id, d))
                conn.execute(
                    """INSERT INTO signals (trend_id, level, source, date, value, url)
                       VALUES (?,'wb_query','wildbox',?,?,?)""",
                    (trend_id, d, freq, path.name))
            conn.commit()
        return imported, unmatched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    INBOX.mkdir(parents=True, exist_ok=True)
    files = sorted(INBOX.glob("*.csv"))
    if not files:
        print(f"Нет CSV в {INBOX}/ — положи туда экспорт Wildbox.")
        return

    conn = db.connect()
    idx = _keyword_index(conn)
    processed = INBOX / "processed"
    total = 0
    all_unmatched: set[str] = set()

    for f in files:
        n, unmatched = import_file(conn, f, idx, args.dry_run)
        total += n
        all_unmatched.update(unmatched)
        print(f"  {f.name}: импортировано {n} строк"
              + (f", не сопоставлено {len(unmatched)}" if unmatched else ""))
        if not args.dry_run and n:
            processed.mkdir(exist_ok=True)
            f.rename(processed / f.name)

    if all_unmatched:
        print("\nНе сопоставлены с трендами (добавь в wb_keywords при необходимости):")
        for kw in sorted(all_unmatched)[:30]:
            print(f"  - {kw}")
    print(f"\nИтого: {total} сигналов wb_query (source='wildbox')"
          + (" [dry-run, ничего не записано]" if args.dry_run else ""))


if __name__ == "__main__":
    main()
