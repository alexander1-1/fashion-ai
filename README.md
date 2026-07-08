# Vogue Runway Scraper → тренд-платформа WB

Скрапер фото с подиума с [vogue.com/fashion-shows](https://www.vogue.com/fashion-shows)
+ платформа тренд-аналитики (TREND_PLATFORM_INSTRUCTION.md).

## Фаза 4: источники сигналов ниже подиума

```bash
pip install -r requirements-local.txt && playwright install chromium

# Telegram (18 каналов из channels.txt; один раз: TG_API_ID/TG_API_HASH в .env)
python tg_collect.py --login          # одноразовая авторизация
python tg_collect.py --days 30        # скачать фото → inbox/telegram/

# Новинки брендов (middle/fast-fashion, раз в 2–4 недели, видимый браузер)
python brand_arrivals.py --download   # → inbox/brands/

# Google Trends (RU-динамика по wb_keywords active-трендов)
python gtrends.py collect             # → signals: social_search

# Ручные папки: inbox/instagram|tiktok|brands/*, inbox/pinterest/*.csv
python inbox_process.py               # регистрация фото + Pinterest CSV

# Vision-тегирование очереди (Haiku, кропы) → сигналы M/F/I
python photo_tagger.py tag --sample 20   # тест
python photo_tagger.py tag               # вся очередь
python photo_tagger.py status

# Пересчёт стадий с новыми сигналами
python trends.py score
```

## Установка

```bash
pip install requests beautifulsoup4 pillow
```

## Запуск

```bash
python run_scraper.py
```

Появится меню:

```
  1. Один показ → CSV
  2. Все показы одного дизайнера → CSV
  3. Все дизайнеры из designers_fw26.txt → master CSV
  4. Скачать фото одного показа (JPG)
  5. Посмотреть список показов дизайнера
```

### Быстрый старт — один показ

```bash
python run_scraper.py
# Выбери: 1
# Дизайнер: Chanel
# Показ: выбери из списка (напр: Fall 2026 Ready-to-Wear)
```

Результат: `output/chanel_fall-2026-ready-to-wear.csv`

### Весь сезон FW26

```bash
python run_scraper.py
# Выбери: 3
# Подтверди: y
```

Скрапит ~60 дизайнеров из `designers_fw26.txt`. Результат: `output/all_designers.csv`

Примерное время: **2–3 часа** (rate limiting 1.5 сек между запросами).

## Использование в коде

```python
import vogue

# Список показов дизайнера
shows = vogue.designer_to_shows('Gucci')

# URL фото одного показа
rows = vogue.get_show_image_urls('Gucci', 'Fall 2026 Ready-to-Wear')
# rows = [{'designer': 'Gucci', 'show': '...', 'look_number': 1, 'image_url': 'https://...'}]

# Сохранить URL в CSV
vogue.designer_show_to_csv('Gucci', 'Fall 2026 Ready-to-Wear', './output')

# Скачать фото (JPG)
vogue.download_images('Gucci', 'Fall 2026 Ready-to-Wear', './output/images')

# Скрапить всех дизайнеров из списка
designers = ['Chanel', 'Dior', 'Gucci', 'Prada']
vogue.all_designers_to_csv(designers, './output')
```

## Структура output/

```
output/
  all_designers.csv          ← master CSV со всеми URL
  chanel_fall-2026-...csv    ← отдельные CSV по показам
  images/
    chanel/
      fall-2026-ready-to-wear/
        look_001.jpg
        look_002.jpg
        ...
```

## Формат CSV

| designer | show | look_number | image_url |
|---|---|---|---|
| Chanel | Fall 2026 Ready-to-Wear | 1 | https://... |
| Chanel | Fall 2026 Ready-to-Wear | 2 | https://... |

## Дизайнеры FW26

В `designers_fw26.txt` — ~65 дизайнеров: Paris, Milan, New York, London.
Раскомментируй/закомментируй нужные.

## Следующий шаг: анализ цветов

После сбора URL можно прогнать через Fashion-CLIP для:
- извлечения доминантных цветов → привязка к Pantone TCX
- классификации типов одежды (dress, jacket, skirt...)
- семантического поиска по описанию

```python
from colorthief import ColorThief
import requests
from io import BytesIO

def get_dominant_colors(image_url, n=5):
    resp = requests.get(image_url)
    ct = ColorThief(BytesIO(resp.content))
    return ct.get_palette(color_count=n)
```
