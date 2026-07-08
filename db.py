"""
db.py — SQLite-хранилище платформы (раздел 1 инструкции).

Один файл trend_signals.db, таблицы:
  looks       — луки подиума (из enriched_looks_v3.csv)
  items       — предметы лука с 7 измерениями тегов
  signals     — сигналы по уровням диффузии (podium … wb_sales)
  trends      — сущность «тренд» (п. 4.1)
  trend_scores— снапшоты скоринга: стадия + тип на дату
  wb_metrics  — кэш ответов MPStats (Фаза 3) + pytrends (Фаза 4)
  ext_photos  — внешние фото (TG/бренды/inbox) для vision-тегирования (Фаза 4)

CSV остаётся только как экспорт.
"""

import json
import sqlite3
from pathlib import Path

import config

SIGNAL_LEVELS = (
    "podium", "middle", "fast_fashion", "influencer",
    "social_search", "wb_query", "wb_sales",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS looks (
    look_id       INTEGER PRIMARY KEY,
    designer      TEXT NOT NULL,
    show_name     TEXT NOT NULL,
    season_family TEXT NOT NULL,   -- 'fall-rtw', 'resort', 'spring-menswear'…
    season_year   INTEGER NOT NULL,
    season_label  TEXT NOT NULL,   -- 'FW26 RTW', 'Resort 2027'…
    look_number   INTEGER,
    image_url     TEXT UNIQUE,
    style_tags    TEXT,            -- JSON array (стили уровня лука)
    confidence    REAL
);
CREATE INDEX IF NOT EXISTS idx_looks_season ON looks(season_family, season_year);

CREATE TABLE IF NOT EXISTS items (
    item_id      INTEGER PRIMARY KEY,
    look_id      INTEGER NOT NULL REFERENCES looks(look_id) ON DELETE CASCADE,
    category     TEXT,
    pattern      TEXT,
    materials    TEXT,   -- JSON array
    silhouette   TEXT,   -- JSON array
    construction TEXT,   -- JSON array
    decoration   TEXT,   -- JSON array
    colors       TEXT,   -- JSON array
    confidence   REAL
);
CREATE INDEX IF NOT EXISTS idx_items_look ON items(look_id);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);

CREATE TABLE IF NOT EXISTS trends (
    trend_id       TEXT PRIMARY KEY,   -- slug: 'construction--high-neck'
    name_ru        TEXT NOT NULL,
    name_en        TEXT NOT NULL,
    type_dimension TEXT NOT NULL,      -- цвет|принт|силуэт|материал|отделка|крой|изделие|стилистика
    field          TEXT NOT NULL,      -- поле тегов: materials|pattern|construction…
    element        TEXT NOT NULL,      -- каноническое EN-значение из taxonomy
    wb_keywords    TEXT NOT NULL DEFAULT '[]',  -- JSON array, генерирует Sonnet 5 + ручная правка
    status         TEXT NOT NULL DEFAULT 'candidate',  -- active|candidate|archived
    origin         TEXT NOT NULL DEFAULT 'auto',       -- auto|manual
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (date('now')),
    UNIQUE(field, element)
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id  INTEGER PRIMARY KEY,
    trend_id   TEXT NOT NULL REFERENCES trends(trend_id) ON DELETE CASCADE,
    level      TEXT NOT NULL CHECK (level IN
               ('podium','middle','fast_fashion','influencer',
                'social_search','wb_query','wb_sales')),
    source     TEXT NOT NULL,          -- 'vogue', 'zara', 'tg:rogov24', 'pytrends', 'mpstats'…
    date       TEXT NOT NULL,          -- ISO YYYY-MM-DD
    value      REAL NOT NULL,          -- доля / счётчик / частотность — зависит от level
    url        TEXT,
    image_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_trend ON signals(trend_id, level, date);

CREATE TABLE IF NOT EXISTS trend_scores (
    id         INTEGER PRIMARY KEY,
    trend_id   TEXT NOT NULL REFERENCES trends(trend_id) ON DELETE CASCADE,
    date       TEXT NOT NULL DEFAULT (date('now')),
    p_share    REAL,   -- доля луков подиума, текущий сезон
    p_growth   REAL,   -- рост доли к прошлому сезону (ratio, 1.0 = без изменений)
    m_count    INTEGER,
    f_count    INTEGER,
    i_count    INTEGER,
    s_growth   REAL,
    q_freq     REAL,
    q_growth   REAL,   -- м/м
    q_decline_months INTEGER,
    c_cards    INTEGER,
    c_top_revenue REAL,
    stage      TEXT,
    trend_type INTEGER,
    rationale  TEXT,
    UNIQUE(trend_id, date)
);

CREATE TABLE IF NOT EXISTS ext_photos (
    photo_id   INTEGER PRIMARY KEY,
    level      TEXT NOT NULL CHECK (level IN
               ('middle','fast_fashion','influencer','social_search')),
    source     TEXT NOT NULL,     -- 'tg:rogov24', 'zara', 'instagram', 'tiktok'
    date       TEXT NOT NULL,     -- дата поста/новинки, ISO YYYY-MM-DD
    path       TEXT NOT NULL UNIQUE,  -- относительный путь к файлу
    url        TEXT,              -- ссылка на пост/товар
    sha1       TEXT UNIQUE,       -- дедуп по содержимому файла
    tags       TEXT,              -- JSON vision-тегов {styles, items, confidence}
    confidence REAL,
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending|tagged|error
    added_at   TEXT NOT NULL DEFAULT (date('now'))
);
CREATE INDEX IF NOT EXISTS idx_ext_photos_status ON ext_photos(status);
CREATE INDEX IF NOT EXISTS idx_ext_photos_source ON ext_photos(level, source, date);

CREATE TABLE IF NOT EXISTS wb_metrics (
    id      INTEGER PRIMARY KEY,
    key     TEXT NOT NULL,    -- поисковый ключ / категория / SKU / бренд
    kind    TEXT NOT NULL,    -- 'keyword'|'category'|'serp'|'sku'|'brand'
    date    TEXT NOT NULL DEFAULT (date('now')),
    payload TEXT NOT NULL,    -- JSON-ответ MPStats
    UNIQUE(key, kind, date)
);
"""


def connect(db_path: str | Path = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path = None) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def parse_season(show: str) -> tuple[str, int, str]:
    """'Fall 2026 Ready-to-Wear' → ('fall-rtw', 2026, 'FW26 RTW').

    season_family — сопоставимая линейка для сравнения год-к-году.
    """
    import re
    m = re.search(r"(19|20)\d{2}", show)
    year = int(m.group(0)) if m else 0
    rest = re.sub(r"\s*(19|20)\d{2}\s*", " ", show).strip().lower()

    menswear = "menswear" in rest
    base = rest.replace("menswear", "").replace("ready-to-wear", "rtw").strip()
    base = " ".join(base.split())
    fam_map = {
        "fall rtw": "fall-rtw", "fall": "fall-rtw",
        "spring rtw": "spring-rtw", "spring": "spring-rtw",
        "fall couture": "fall-couture", "spring couture": "spring-couture",
        "pre-fall": "pre-fall", "resort": "resort",
        "shanghai spring": "shanghai-spring",
    }
    family = fam_map.get(base, base.replace(" ", "-") or "unknown")
    if menswear:
        family += "-menswear"

    yy = year % 100
    label_map = {
        "fall-rtw": f"FW{yy} RTW", "spring-rtw": f"SS{yy} RTW",
        "fall-rtw-menswear": f"FW{yy} MW", "spring-rtw-menswear": f"SS{yy} MW",
    }
    label = label_map.get(family, show)
    return family, year, label


def json_or_empty(value) -> str:
    if not value:
        return "[]"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    conn = init_db()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"OK: {config.DB_PATH} → таблицы: {', '.join(tables)}")
