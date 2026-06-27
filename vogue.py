"""
Vogue Runway Scraper
====================
Скачивает фото с подиума с Vogue Runway (vogue.com/fashion-shows).

Основано на TonyAssi/Vogue-Runway-Scraper, адаптировано:
- без unidecode (используем unicodedata)
- без html5lib (используем встроенный html.parser)
- добавлен rate limiting и retry
- добавлено сохранение URL в CSV без скачивания

Зависимости: requests, beautifulsoup4, pillow
"""

import json
import requests
import time
import csv
import os
import unicodedata
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO


# ─── Настройки ────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
DELAY_BETWEEN_REQUESTS = 1.5   # секунды между запросами (вежливый режим)
MAX_RETRIES = 3


# ─── Утилиты ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Превращает строку в URL-slug без внешних зависимостей."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    for ch in [" ", "/", "\\", "(", ")", ",", ":", ";"]:
        text = text.replace(ch, "-")
    for ch in [".", "&", "+", "'", '"', "!", "?"]:
        text = text.replace(ch, "")
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")


def get_page(url: str) -> None:
    """Загружает страницу с retry и rate limiting."""
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(DELAY_BETWEEN_REQUESTS)
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return BeautifulSoup(r.content, "html.parser")
            else:
                print(f"  ⚠️  HTTP {r.status_code} для {url}")
        except Exception as e:
            print(f"  ❌ Ошибка запроса (попытка {attempt+1}/{MAX_RETRIES}): {e}")
        time.sleep(2 ** attempt)  # exponential backoff
    return None


def extract_json_from_script(soup: BeautifulSoup, key_fragment: str) -> None:
    """Извлекает JSON из <script> тегов по ключевому фрагменту."""
    for script in soup.find_all("script"):
        if script.string and key_fragment in script.string:
            js = script.string
            break
    else:
        return None

    try:
        js_clean = js.split(" = ", 1)[1]
        brace_count = 0
        for i, char in enumerate(js_clean):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    js_clean = js_clean[: i + 1]
                    break
        return json.loads(js_clean)
    except Exception as e:
        print(f"  ❌ Не удалось распарсить JSON: {e}")
        return None


# ─── Основные функции ─────────────────────────────────────────────────────────

def designer_to_shows(designer: str) -> list:
    """Возвращает список всех показов дизайнера."""
    slug = slugify(designer)
    url = f"https://www.vogue.com/fashion-shows/designer/{slug}"
    print(f"🔍 Загружаю показы: {url}")
    soup = get_page(url)
    if not soup:
        return []

    data = extract_json_from_script(soup, "window.__PRELOADED_STATE__")
    if not data:
        print("  ❌ JSON не найден на странице дизайнера")
        return []

    try:
        shows = [
            show["hed"]
            for show in data["transformed"]["runwayDesignerContent"]["designerCollections"]
        ]
        print(f"  ✅ Найдено показов: {len(shows)}")
        return shows
    except Exception as e:
        print(f"  ❌ Ошибка парсинга списка показов: {e}")
        return []


def get_show_image_urls(designer: str, show: str) -> list:
    """Возвращает список словарей {designer, show, look_number, image_url}."""
    show_slug = slugify(show)
    designer_slug = slugify(designer)
    url = f"https://www.vogue.com/fashion-shows/{show_slug}/{designer_slug}"

    soup = get_page(url)
    if not soup:
        return []

    data = extract_json_from_script(soup, "runwayShowGalleries")
    if not data:
        print(f"  ❌ Галерея не найдена: {designer} — {show}")
        return []

    try:
        items = data["transformed"]["runwayShowGalleries"]["galleries"][0]["items"]
    except Exception as e:
        print(f"  ❌ Ошибка структуры галереи: {e}")
        return []

    results = []
    for i, item in enumerate(items):
        try:
            img_url = item["image"]["sources"]["md"]["url"]
            results.append({
                "designer": designer,
                "show": show,
                "look_number": i + 1,
                "image_url": img_url,
            })
        except Exception:
            pass

    print(f"  ✅ Найдено луков: {len(results)}")
    return results


def designer_show_to_csv(designer: str, show: str, save_path: str) -> int:
    """Сохраняет URL фото из одного показа в CSV. Возвращает кол-во строк."""
    os.makedirs(save_path, exist_ok=True)
    filename = f"{slugify(designer)}_{slugify(show)}.csv"
    filepath = os.path.join(save_path, filename)

    if os.path.exists(filepath):
        print(f"  ⏭️  Уже есть: {filename}")
        return 0

    rows = get_show_image_urls(designer, show)
    if not rows:
        return 0

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["designer", "show", "look_number", "image_url"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"  💾 Сохранено: {filename} ({len(rows)} луков)")
    return len(rows)


def designer_to_csv(designer: str, save_path: str):
    """Сохраняет URL фото всех показов дизайнера в один CSV-файл."""
    os.makedirs(save_path, exist_ok=True)
    filename = f"{slugify(designer)}_all_shows.csv"
    filepath = os.path.join(save_path, filename)

    if os.path.exists(filepath):
        print(f"⏭️  Уже скрапнут: {designer}")
        return

    shows = designer_to_shows(designer)
    if not shows:
        return

    all_rows = []
    for show in shows:
        print(f"  📸 {designer} — {show}")
        rows = get_show_image_urls(designer, show)
        all_rows.extend(rows)

    if all_rows:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["designer", "show", "look_number", "image_url"])
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"✅ {designer}: {len(all_rows)} луков → {filename}")
    else:
        print(f"⚠️  Нет данных для {designer}")


def all_designers_to_csv(designers: list[str], save_path: str):
    """Скрапит список дизайнеров и сохраняет всё в один master-CSV."""
    os.makedirs(save_path, exist_ok=True)
    master_path = os.path.join(save_path, "all_designers.csv")

    # Определяем уже скрапнутые
    done = set()
    if os.path.exists(master_path):
        with open(master_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                done.add((row["designer"], row["show"]))

    with open(master_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["designer", "show", "look_number", "image_url"])
        if os.stat(master_path).st_size == 0:
            writer.writeheader()

        for designer in designers:
            print(f"\n📂 Дизайнер: {designer}")
            shows = designer_to_shows(designer)
            for show in shows:
                if not any(y in show for y in ["2025", "2026", "2027"]):
                    continue
                if (designer, show) in done:
                    print(f"  ⏭️  Уже есть: {show}")
                    continue
                rows = get_show_image_urls(designer, show)
                if rows:
                    writer.writerows(rows)
                    f.flush()
                    for row in rows:
                        done.add((row["designer"], row["show"]))
                    print(f"  ✅ {show}: {len(rows)} луков")

    print(f"\n🎉 Готово! Всё сохранено в {master_path}")


def download_images(designer: str, show: str, save_path: str):
    """Скачивает фото одного показа в папку."""
    show_slug = slugify(show)
    designer_slug = slugify(designer)
    out_dir = os.path.join(save_path, designer_slug, show_slug)

    if os.path.exists(out_dir) and os.listdir(out_dir):
        print(f"⏭️  Уже скачано: {out_dir}")
        return

    os.makedirs(out_dir, exist_ok=True)
    rows = get_show_image_urls(designer, show)

    print(f"⬇️  Скачиваю {len(rows)} фото...")
    for row in rows:
        try:
            time.sleep(0.3)
            resp = requests.get(row["image_url"], headers=HEADERS, timeout=15)
            img = Image.open(BytesIO(resp.content))
            filename = f"look_{row['look_number']:03d}.jpg"
            img.save(os.path.join(out_dir, filename))
            print(f"  ✅ {filename}")
        except Exception as e:
            print(f"  ⚠️  Ошибка: {e}")

    print(f"✅ Скачано в {out_dir}")
