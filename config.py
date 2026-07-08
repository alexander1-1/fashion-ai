"""
config.py — пороговые константы тренд-движка (раздел 4 инструкции).
Все значения калибруются на известных кейсах (чеклист п. 9).
"""

DB_PATH = "trend_signals.db"

# ─── Автозаведение трендов (п. 4.1) ──────────────────────────────────────────
# Элемент заводится как тренд, если его доля в новом сезоне выросла к прошлому.
AUTOREG_MIN_SHARE = 0.015      # мин. доля луков сезона с элементом (1.5%)
AUTOREG_GROWTH_RATIO = 1.25    # рост доли к прошлому сезону ≥ +25%
AUTOREG_MIN_COUNT = 15         # мин. число луков с элементом в новом сезоне
AUTOREG_MIN_SEASON_LOOKS = 300 # сезон учитывается, если в нём ≥ N луков
AUTOREG_NEW_MIN_SHARE = 0.02   # элемент без истории (прошлый сезон = 0): порог доли

# Поля тегов → измерение тренда из методики
FIELD_TO_DIMENSION = {
    "materials": "материал",
    "pattern": "принт",
    "silhouette": "силуэт",
    "construction": "крой",
    "decoration": "отделка",
    "colors": "цвет",
    "styles": "стилистика",
    "category": "изделие",
}

# Мин. confidence предмета, чтобы его теги шли в подсчёт частот
MIN_ITEM_CONFIDENCE = 0.6

# ─── Скоринг стадии диффузии (п. 4.2) ────────────────────────────────────────
# P — подиум, M — middle, F — fast-fashion, I — инфлюенсеры,
# S — соц.поиск (Pinterest/Google/TikTok), Q — запросы WB, C — насыщенность ниши.

STAGE_WINDOW_MF_DAYS = 60      # окно появлений middle/fast-fashion
STAGE_WINDOW_I_DAYS = 30       # окно появлений у инфлюенсеров

P_GROWTH_RATIO = 1.2           # «P растёт» = доля выросла ≥ +20% к прошлому сезону

MFI_ZERO_MAX = 2               # (M+F+I) ≈ 0 → не больше N появлений
Q_ZERO_MAX = 500               # Q ≈ 0 → частотность WB < N запросов/мес

Q_EARLY_GROWTH_MOM = 0.5       # первый рост Q: ≥ +50% м/м …
Q_EARLY_MAX_FREQ = 5_000       # …при частотности < 5K/мес

Q_MASS_MIN_FREQ = 20_000       # массовый рост: частотность ≥ N/мес
Q_MASS_GROWTH_MOM = 0.15       # …и рост ≥ +15% м/м
C_SATURATED_CARDS = 300        # ниша насыщена: карточек ≥ N
Q_DECLINE_MONTHS = 2           # спад: Q падает ≥ N месяцев подряд

STAGES = [
    "ИННОВАТОРЫ",
    "РАННИЕ ПОСЛЕДОВАТЕЛИ",
    "РАННЕЕ БОЛЬШИНСТВО",
    "ПОЗДНЕЕ БОЛЬШИНСТВО",
    "СПАД",
]

# ─── Тип тренда (п. 4.3) ─────────────────────────────────────────────────────
TYPE4_MIN_Q_GROWTH = 0.1       # растущие запросы
TYPE4_MAX_CARDS = 150          # низкая конкуренция: карточек < N
TYPE4_MIN_TOP_REVENUE = 1_000_000  # высокая выручка топов, руб/мес

# ─── MPStats API (раздел 5, Фаза 3) ──────────────────────────────────────────
MPSTATS_BASE = "https://mpstats.io/api/analytics/v1/wb/"
MPSTATS_Q_WINDOWS = 13         # число 30-дневных окон частотности (≈13 мес.)
MPSTATS_WINDOW_DAYS = 30       # длина окна агрегации недельной частотности
MPSTATS_TOP_N = 20             # топ карточек выдачи для c_top_revenue
MPSTATS_SERP_ROWS = 100        # сколько карточек запрашивать из выдачи
MPSTATS_DELAY_SEC = 0.35       # пауза между вызовами API

# ─── Источники сигналов (раздел 3, Фаза 4) ───────────────────────────────────
INBOX_DIR = "inbox"            # inbox/telegram|brands|instagram|tiktok|pinterest|wildbox

TG_CHANNELS_FILE = "channels.txt"
TG_DEFAULT_DAYS = 30           # окно сбора постов
TG_MAX_PHOTOS_PER_CHANNEL = 150

PYTRENDS_GEO = "RU"            # RU-динамика запросов (п. 3.4)
PYTRENDS_TIMEFRAME = "today 12-m"
PYTRENDS_DELAY_SEC = 10        # rate limit Google Trends суров
PYTRENDS_CACHE_DAYS = 1        # обновление не чаще раза в сутки
