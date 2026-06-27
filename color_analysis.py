"""
Цветовой анализ подиумных фото
================================
Читает all_designers.csv, для каждого лука:
  - скачивает фото по URL (временно, в память)
  - извлекает 3 доминантных цвета
  - матчит к ближайшему Pantone TCX цвету
  - сохраняет результат в color_results.csv

Установка:
    pip3 install colorthief pillow requests

Запуск:
    python3 color_analysis.py

Результат: output/color_results.csv
"""

import csv
import os
import time
import math
import requests
from io import BytesIO
from PIL import Image

# ─── Pantone TCX — топ 50 fashion цветов ──────────────────────────────────────
# Формат: (name, pantone_code, R, G, B)
PANTONE_TCX = [
    # Neutrals
    ("Bright White",     "11-0601", 242, 240, 234),
    ("Pearled Ivory",    "11-0710", 237, 229, 207),
    ("Butter Cream",     "12-0722", 245, 230, 183),
    ("Pastel Yellow",    "11-0616", 245, 238, 185),
    ("Wax Yellow",       "11-0618", 243, 233, 169),
    ("Warm Sand",        "14-1118", 210, 185, 155),
    ("Tan Melange",      "16-1320", 185, 157, 128),
    ("Warm Taupe",       "16-1318", 178, 152, 126),
    ("Mushroom",         "15-1212", 196, 172, 152),
    ("Doeskin",          "15-1114", 201, 174, 147),
    ("Toasted Coconut",  "18-1048", 155, 100,  58),
    ("Caramel",          "16-1439", 195, 135,  85),
    ("Adobe",            "16-1526", 201, 140, 108),
    ("Sandstorm",        "14-1120", 218, 185, 145),

    # Reds & Pinks
    ("Rosewood",         "14-1512", 209, 163, 152),
    ("Powder Pink",      "12-1605", 237, 212, 207),
    ("Rose Quartz",      "13-1520", 247, 202, 201),
    ("Flamingo Pink",    "14-1911", 226, 181, 177),
    ("Coral",            "16-1546", 231, 114,  88),
    ("Fiesta",           "17-1564", 221,  65,  50),
    ("True Red",         "19-1664", 188,  28,  28),
    ("Raspberry Sorbet", "18-1754", 194,  63,  82),
    ("Hot Coral",        "17-1656", 244, 100,  72),
    ("Fuchsia Rose",     "17-2034", 199,  67, 117),
    ("Pink Lemonade",    "13-2010", 247, 200, 207),

    # Blues
    ("Baby Blue",        "13-4308", 185, 210, 225),
    ("Placid Blue",      "15-3920", 134, 168, 200),
    ("Cerulean",         "15-4020", 154, 196, 215),
    ("Classic Blue",     "19-4052", 15,  76, 129),
    ("Navy Peony",       "19-4340", 22,  48,  92),
    ("Midnight Blue",    "19-4024", 28,  36,  76),
    ("Aegean",           "19-4241", 58, 104, 128),
    ("Dusk Blue",        "17-4041", 85, 128, 162),

    # Greens
    ("Sage Mist",        "16-0110", 174, 185, 157),
    ("Quiet Green",      "15-0232", 165, 192, 155),
    ("Artichoke Green",  "18-0430", 110, 130,  85),
    ("Greenery",         "15-0343", 136, 176,  75),
    ("Forest Green",     "19-0230", 46,  86,  50),
    ("Olive Branch",     "17-0535", 110, 125,  70),

    # Purples
    ("Violet Tulip",     "15-3817", 182, 175, 214),
    ("Pastel Lilac",     "14-3612", 211, 196, 221),
    ("Amethyst Orchid",  "18-3633", 146, 104, 165),
    ("Ultra Violet",     "18-3838", 92,  80, 148),

    # Blacks & Greys
    ("Bright White",     "11-0601", 242, 240, 234),
    ("Silver Gray",      "14-4102", 192, 189, 189),
    ("Monument",         "18-0306", 120, 120, 112),
    ("Pewter",           "17-0207", 148, 147, 136),
    ("Charcoal Gray",    "18-0306", 78,  78,  76),
    ("Black",            "19-0303", 20,  20,  20),

    # Browns
    ("Chocolate Brown",  "19-1217", 75,  45,  32),
    ("Coffee Bean",      "19-0915", 72,  48,  35),
    ("Cognac",           "18-1142", 155,  78,  40),

    # Metallics (approx)
    ("Gold Fusion",      "16-0836", 189, 157,  80),
    ("Silver",           "14-4102", 192, 192, 192),
]


def color_distance(rgb1, rgb2):
    """Евклидово расстояние в RGB пространстве."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(rgb1, rgb2)))


def match_pantone(rgb):
    """Находит ближайший Pantone TCX цвет по RGB."""
    best = min(PANTONE_TCX, key=lambda p: color_distance(rgb, (p[2], p[3], p[4])))
    return best[0], best[1]


def get_dominant_colors(image_url, n=3):
    """Извлекает N доминантных цветов из фото по URL."""
    try:
        resp = requests.get(image_url, timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"})
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img = img.resize((150, 150))  # ускоряем анализ

        # Простой анализ через квантизацию
        quantized = img.quantize(colors=n * 3).convert("RGB")
        colors = quantized.getcolors(maxcolors=150 * 150)
        if not colors:
            return []

        # Сортируем по частоте, берём топ-N
        colors.sort(reverse=True)
        top = []
        for count, rgb in colors[:n * 3]:
            # Пропускаем слишком светлые (фон)
            if sum(rgb) > 700:
                continue
            top.append(rgb)
            if len(top) >= n:
                break

        return top[:n]
    except Exception as e:
        print(f"  ⚠️  Ошибка: {e}")
        return []


def analyze(csv_path="./output/all_designers.csv",
            out_path="./output/color_results.csv",
            limit=None,
            delay=0.5):
    """
    Основная функция анализа.
    limit=None — анализировать всё, limit=100 — только первые 100 луков.
    """
    if not os.path.exists(csv_path):
        print(f"❌ Файл не найден: {csv_path}")
        return

    # Читаем уже обработанные (для продолжения после прерывания)
    done_urls = set()
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done_urls.add(row["image_url"])
        print(f"⏭️  Уже обработано: {len(done_urls)} луков (продолжаем)")

    # Читаем входной CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if limit:
        rows = rows[:limit]

    total = len(rows)
    print(f"🎨 Всего луков для анализа: {total}")

    fieldnames = [
        "designer", "show", "look_number", "image_url",
        "color1_rgb", "color1_pantone", "color1_code",
        "color2_rgb", "color2_pantone", "color2_code",
        "color3_rgb", "color3_pantone", "color3_code",
    ]

    with open(out_path, "a", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        if os.stat(out_path).st_size == 0:
            writer.writeheader()

        for i, row in enumerate(rows):
            url = row["image_url"]
            if url in done_urls:
                continue

            print(f"  [{i+1}/{total}] {row['designer']} — look {row['look_number']}")
            colors = get_dominant_colors(url, n=3)

            result = {
                "designer": row["designer"],
                "show": row["show"],
                "look_number": row["look_number"],
                "image_url": url,
            }

            for j, rgb in enumerate(colors[:3], 1):
                pantone_name, pantone_code = match_pantone(rgb)
                result[f"color{j}_rgb"] = f"{rgb[0]},{rgb[1]},{rgb[2]}"
                result[f"color{j}_pantone"] = pantone_name
                result[f"color{j}_code"] = pantone_code

            # Заполняем пустые слоты если цветов меньше 3
            for j in range(len(colors) + 1, 4):
                result[f"color{j}_rgb"] = ""
                result[f"color{j}_pantone"] = ""
                result[f"color{j}_code"] = ""

            writer.writerow(result)
            out_f.flush()
            time.sleep(delay)

    print(f"\n✅ Готово! Результат: {out_path}")


def top_colors_report(results_path="./output/color_results.csv", top_n=15):
    """Выводит топ-N самых популярных Pantone цветов сезона."""
    if not os.path.exists(results_path):
        print(f"❌ Сначала запусти analyze()")
        return

    from collections import Counter
    counter = Counter()

    with open(results_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for j in range(1, 4):
                name = row.get(f"color{j}_pantone", "")
                code = row.get(f"color{j}_code", "")
                if name:
                    counter[(name, code)] += 1

    print(f"\n🎨 ТОП-{top_n} ЦВЕТОВ СЕЗОНА:")
    print(f"{'#':>3}  {'Pantone':>8}  {'Название':<25}  {'Луков':>6}")
    print("─" * 50)
    for i, ((name, code), count) in enumerate(counter.most_common(top_n), 1):
        print(f"{i:>3}  {code:>8}  {name:<25}  {count:>6}")


if __name__ == "__main__":
    print("=" * 50)
    print("  Fashion Color Analysis")
    print("=" * 50)
    print()
    print("  1. Анализировать все луки (~6-8 часов)")
    print("  2. Тест на 50 луках (~3 минуты)")
    print("  3. Показать отчёт по уже готовым данным")
    print()
    choice = input("Выбери (1-3): ").strip()

    if choice == "1":
        analyze()
    elif choice == "2":
        analyze(limit=50)
        top_colors_report()
    elif choice == "3":
        top_colors_report()
    else:
        print("Неверный выбор")
