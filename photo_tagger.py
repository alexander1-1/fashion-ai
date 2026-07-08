"""
photo_tagger.py — vision-тегирование внешних фото и сигналы (раздел 3, Фаза 4).

Общий пайплайн для всех источников ниже подиума (TG-каналы, новинки брендов,
inbox/instagram|tiktok): фото регистрируются в ext_photos (status='pending'),
этот модуль тегирует их тем же двухпроходным vision-пайплайном, что и луки
подиума (enrich_looks: Haiku, tool use со строгими enum, кропы, MOCK=1),
и пишет строки в signals по совпадению элементов с трендами.

Одно фото с элементом тренда → одна строка signals (value=1), дата = дата
поста/новинки. trends.collect_metrics суммирует value в окне — счётчики
M/F/I начинают заполняться без изменений тренд-движка.

Дедупликация: перед записью сигналы этого фото (по image_path) удаляются.

CLI:
    python photo_tagger.py tag                 # тегировать все pending
    python photo_tagger.py tag --sample 20     # только N фото (тест)
    python photo_tagger.py signals             # пересобрать signals из tagged
    python photo_tagger.py status              # счётчики по статусам/источникам
    MOCK=1 python photo_tagger.py tag          # без API (фикстуры/заглушки)
"""

import argparse
import base64
import hashlib
import io
import json
from datetime import date
from pathlib import Path

import config
import db
import enrich_looks as el
import taxonomy


# ─── Подготовка изображений из локального файла ──────────────────────────────

def prepare_images_from_file(path: str | Path) -> dict:
    """Как enrich_looks.prepare_images, но из файла: full + 2 кропа (b64 JPEG)."""
    from PIL import Image
    img = Image.open(path)
    w, h = img.size
    top = img.crop((0, 0, w, int(h * 0.55)))
    bottom = img.crop((0, int(h * 0.45), w, h))
    return {
        "full": base64.standard_b64encode(
            el._resize_jpeg(img, el.FULL_MAX_SIDE)).decode(),
        "top": base64.standard_b64encode(
            el._resize_jpeg(top, el.CROP_MAX_SIDE)).decode(),
        "bottom": base64.standard_b64encode(
            el._resize_jpeg(bottom, el.CROP_MAX_SIDE)).decode(),
    }


def analyze_photo(client, path: str | Path, model: str = el.MODEL_BULK) -> dict:
    """Двухпроходный анализ локального фото → {styles, items, confidence}."""
    key = str(path)
    images = prepare_images_from_file(path) if not el.MOCK else \
        {"full": "", "top": "", "bottom": ""}
    a = el.validate_a(client.call(
        el.request_params_a(images, model), f"A:{key}"))
    if not a["items"]:
        return el.merge_passes(a, {"items": []})
    b = el.validate_b(client.call(
        el.request_params_b(images, model, a["items"]), f"B:{key}"))
    return el.merge_passes(a, b)


# ─── HTTP-клиент (fallback без anthropic SDK) ────────────────────────────────

class HttpClient:
    """Messages API напрямую через requests — когда SDK не установлен.
    Пишет фикстуры туда же, куда LiveClient (тесты переигрывают бесплатно)."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self):
        import os
        from mpstats_client import load_env
        load_env()
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise SystemExit("❌ Set ANTHROPIC_API_KEY (или MOCK=1)")
        self._fixtures = {}
        if Path(el.FIXTURES_PATH).exists():
            self._fixtures = json.loads(Path(el.FIXTURES_PATH).read_text())

    def call(self, params: dict, key: str, retries: int = 3) -> dict:
        import time
        import requests
        for attempt in range(retries):
            try:
                r = requests.post(
                    self.API_URL, json=params, timeout=120,
                    headers={"x-api-key": self.api_key,
                             "anthropic-version": "2023-06-01"})
                r.raise_for_status()
                result = el.extract_tool_input(r.json())
                self._fixtures[key] = result
                Path(el.FIXTURES_PATH).parent.mkdir(parents=True, exist_ok=True)
                Path(el.FIXTURES_PATH).write_text(
                    json.dumps(self._fixtures, ensure_ascii=False, indent=1))
                return result
            except Exception as e:
                print(f"    API error: {e} (attempt {attempt + 1})")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"API failed after {retries} retries: {key}")


def make_client():
    from mpstats_client import load_env
    load_env()  # ANTHROPIC_API_KEY можно держать в .env
    if el.MOCK:
        return el.MockClient()
    try:
        import anthropic  # noqa: F401
        return el.LiveClient()
    except ImportError:
        return HttpClient()


# ─── Регистрация фото в ext_photos ───────────────────────────────────────────

def file_sha1(path: str | Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def register_photo(conn, path: str | Path, level: str, source: str,
                   photo_date: str, url: str = "") -> int | None:
    """Добавить фото в очередь. None — дубликат (path или sha1 уже есть)."""
    p = Path(path)
    if not p.exists():
        return None
    rel = str(p)
    sha = file_sha1(p)
    cur = conn.execute(
        """INSERT OR IGNORE INTO ext_photos (level, source, date, path, url, sha1)
           VALUES (?,?,?,?,?,?)""",
        (level, source, photo_date, rel, url, sha))
    conn.commit()
    return cur.lastrowid if cur.rowcount else None


# ─── Сигналы из тегов ────────────────────────────────────────────────────────

def _photo_elements(tags: dict) -> set[tuple[str, str]]:
    """Множество (field, element) фото; предметы с confidence ниже порога
    не учитываются (как в trends.season_element_shares)."""
    out = set()
    for s in tags.get("styles") or []:
        out.add(("styles", s))
    for it in tags.get("items") or []:
        if (it.get("confidence") or 0) < config.MIN_ITEM_CONFIDENCE:
            continue
        for f in ("category", "pattern"):
            v = it.get(f)
            if v and v != taxonomy.NOT_VISIBLE and v != "Other":
                out.add((f, v))
        for f in ("materials", "silhouette", "construction", "decoration", "colors"):
            for v in it.get(f) or []:
                if v and v != taxonomy.NOT_VISIBLE:
                    out.add((f, v))
    return out


def _trend_index(conn) -> dict[tuple[str, str], str]:
    return {(t["field"], t["element"]): t["trend_id"]
            for t in conn.execute(
                "SELECT trend_id, field, element FROM trends "
                "WHERE status != 'archived'")}


def write_signals_for_photo(conn, photo_row, trend_idx: dict) -> int:
    """Сигналы одного tagged-фото; старые сигналы этого файла затираются."""
    tags = json.loads(photo_row["tags"] or "{}")
    conn.execute("DELETE FROM signals WHERE image_path=?", (photo_row["path"],))
    n = 0
    for field_element in _photo_elements(tags):
        tid = trend_idx.get(field_element)
        if not tid:
            continue
        conn.execute(
            """INSERT INTO signals (trend_id, level, source, date, value, url, image_path)
               VALUES (?,?,?,?,1,?,?)""",
            (tid, photo_row["level"], photo_row["source"], photo_row["date"],
             photo_row["url"], photo_row["path"]))
        n += 1
    return n


def rebuild_signals(conn) -> tuple[int, int]:
    trend_idx = _trend_index(conn)
    photos = conn.execute(
        "SELECT * FROM ext_photos WHERE status='tagged'").fetchall()
    total = 0
    for p in photos:
        total += write_signals_for_photo(conn, p, trend_idx)
    conn.commit()
    return len(photos), total


# ─── Тегирование очереди ─────────────────────────────────────────────────────

def tag_pending(conn, sample: int = 0, model: str = el.MODEL_BULK) -> dict:
    client = make_client()
    trend_idx = _trend_index(conn)
    q = "SELECT * FROM ext_photos WHERE status='pending' ORDER BY photo_id"
    rows = conn.execute(q).fetchall()
    if sample:
        rows = rows[:sample]

    stats = {"tagged": 0, "errors": 0, "signals": 0, "skipped_missing": 0}
    for i, row in enumerate(rows, 1):
        path = row["path"]
        if not el.MOCK and not Path(path).exists():
            conn.execute("UPDATE ext_photos SET status='error' WHERE photo_id=?",
                         (row["photo_id"],))
            stats["skipped_missing"] += 1
            continue
        try:
            tags = analyze_photo(client, path, model)
            conn.execute(
                """UPDATE ext_photos SET tags=?, confidence=?, status='tagged'
                   WHERE photo_id=?""",
                (json.dumps(tags, ensure_ascii=False), tags["confidence"],
                 row["photo_id"]))
            fresh = conn.execute("SELECT * FROM ext_photos WHERE photo_id=?",
                                 (row["photo_id"],)).fetchone()
            n_sig = write_signals_for_photo(conn, fresh, trend_idx)
            stats["tagged"] += 1
            stats["signals"] += n_sig
            print(f"  [{i}/{len(rows)}] {row['source']:20s} {Path(path).name:40s} "
                  f"conf={tags['confidence']:.2f} сигналов={n_sig}")
        except Exception as e:
            conn.execute("UPDATE ext_photos SET status='error' WHERE photo_id=?",
                         (row["photo_id"],))
            stats["errors"] += 1
            print(f"  [{i}/{len(rows)}] ! {path}: {e}")
        conn.commit()
    return stats


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _cmd_status(conn):
    print("По статусам:")
    for r in conn.execute(
            "SELECT status, COUNT(*) n FROM ext_photos GROUP BY 1"):
        print(f"  {r['status']:10s} {r['n']}")
    print("\nПо источникам:")
    for r in conn.execute(
            """SELECT level, source, COUNT(*) n, MIN(date) d1, MAX(date) d2
               FROM ext_photos GROUP BY 1,2 ORDER BY 1,2"""):
        print(f"  {r['level']:14s} {r['source']:22s} {r['n']:5d}  {r['d1']} … {r['d2']}")
    n_sig = conn.execute(
        """SELECT COUNT(*) FROM signals
           WHERE level IN ('middle','fast_fashion','influencer')""").fetchone()[0]
    print(f"\nСигналов M/F/I в signals: {n_sig}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["tag", "signals", "status"])
    ap.add_argument("--sample", type=int, default=0, help="только N фото")
    ap.add_argument("--model", default=el.MODEL_BULK)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    conn = db.init_db(args.db or config.DB_PATH)

    if args.command == "tag":
        s = tag_pending(conn, args.sample, args.model)
        print(f"\nИтого: tagged={s['tagged']} errors={s['errors']} "
              f"signals={s['signals']} missing={s['skipped_missing']}")
    elif args.command == "signals":
        n_ph, n_sig = rebuild_signals(conn)
        print(f"Пересобрано: {n_ph} фото → {n_sig} сигналов")
    elif args.command == "status":
        _cmd_status(conn)
