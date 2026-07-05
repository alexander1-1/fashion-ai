"""
download_golden_photos.py — скачать все фото golden set (100 луков)
====================================================================
Сохраняет в папку golden_photos/ с именами вида
001_Chanel_Look-27.jpg (номер по порядку, бренд, номер лука).

Запуск:
    python3 download_golden_photos.py
    python3 download_golden_photos.py --hires   # макс. разрешение (w_1920)
"""

import argparse
import json
import os
import re
import time
import urllib.request

SRC = "output/golden_set_draft.json"
OUT_DIR = "golden_photos"


def safe(s):
    return re.sub(r"[^\w\-]+", "-", str(s)).strip("-")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hires", action="store_true",
                   help="Качать w_1920 вместо исходного размера")
    args = p.parse_args()

    with open(SRC, encoding="utf-8") as f:
        looks = json.load(f)
    os.makedirs(OUT_DIR, exist_ok=True)

    done = skip = err = 0
    for i, look in enumerate(looks, 1):
        url = look["image_url"]
        if args.hires:
            url = re.sub(r"/w_\d+,", "/w_1920,", url)
        name = (f"{i:03d}_{safe(look['designer'])}"
                f"_Look-{safe(look['look_number'])}.jpg")
        path = os.path.join(OUT_DIR, name)
        if os.path.exists(path):
            skip += 1
            continue
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=20).read()
            with open(path, "wb") as f:
                f.write(data)
            done += 1
            print(f"[{i:3d}/100] {name}  ({len(data)//1024} КБ)")
            time.sleep(0.2)
        except Exception as e:
            err += 1
            print(f"[{i:3d}/100] ⚠️ {name}: {e}")

    print(f"\n✅ Скачано: {done}, пропущено (уже были): {skip}, ошибок: {err}")
    print(f"   Папка: {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
