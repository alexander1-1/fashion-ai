"""
Fashion Semantic Search — CLIP через sentence-transformers
===========================================================
Создаёт векторные embeddings для каждого лука через CLIP,
сохраняет локальный индекс, позволяет искать по текстовому описанию.

Установка:
    pip3 install sentence-transformers pillow requests numpy

Запуск:
    python3 fashion_search.py
"""

import os
import csv
import json
import time
import requests
import numpy as np
from io import BytesIO
from PIL import Image

# ─── Настройки ────────────────────────────────────────────────────────────────

CSV_PATH      = "./output/all_designers.csv"
INDEX_PATH    = "./output/clip_index.npy"
METADATA_PATH = "./output/clip_metadata.json"
BATCH_SIZE    = 8
TOP_K         = 10

CLOTHING_CATEGORIES = [
    "dress", "jacket", "coat", "skirt", "trousers",
    "suit", "blouse", "gown", "jumpsuit", "knitwear",
    "shirt", "shorts", "vest", "cape", "leather outfit",
]


# ─── Загрузка модели ──────────────────────────────────────────────────────────

def load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("❌ Установи: pip3 install sentence-transformers")
        return None

    print("🤖 Загружаю CLIP модель (первый раз ~600MB)...")
    model = SentenceTransformer("clip-ViT-B-32")
    print("✅ Модель загружена")
    return model


def fetch_image(url):
    try:
        resp = requests.get(url, timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"})
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img = img.resize((224, 224))  # CLIP требует одинаковый размер
        return img
    except Exception:
        return None


# ─── Построение индекса ───────────────────────────────────────────────────────

def build_index(limit=None):
    model = load_model()
    if not model:
        return

    # Загружаем уже сделанные
    if os.path.exists(INDEX_PATH) and os.path.exists(METADATA_PATH):
        embeddings = list(np.load(INDEX_PATH))
        with open(METADATA_PATH, "r") as f:
            metadata = json.load(f)
        done_urls = {m["image_url"] for m in metadata}
        print(f"⏭️  Уже есть {len(embeddings)} embeddings, продолжаем...")
    else:
        embeddings = []
        metadata = []
        done_urls = set()

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]

    pending = [r for r in rows if r["image_url"] not in done_urls]
    total = len(pending)
    print(f"📸 Луков для обработки: {total}")

    for i in range(0, total, BATCH_SIZE):
        batch_rows = pending[i:i + BATCH_SIZE]
        images, valid_rows = [], []

        for row in batch_rows:
            img = fetch_image(row["image_url"])
            if img:
                images.append(img)
                valid_rows.append(row)

        if not images:
            continue

        feats = model.encode(images, convert_to_numpy=True, show_progress_bar=False)
        feats = feats / np.linalg.norm(feats, axis=1, keepdims=True)

        for j, row in enumerate(valid_rows):
            embeddings.append(feats[j])
            metadata.append({
                "designer": row["designer"],
                "show": row["show"],
                "look_number": row["look_number"],
                "image_url": row["image_url"],
            })

        done = i + len(batch_rows)
        print(f"  [{done}/{total}] ✅ {valid_rows[-1]['designer']} — look {valid_rows[-1]['look_number']}")

        if len(embeddings) % 200 == 0:
            np.save(INDEX_PATH, np.array(embeddings))
            with open(METADATA_PATH, "w") as f:
                json.dump(metadata, f)

        time.sleep(0.1)

    np.save(INDEX_PATH, np.array(embeddings))
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f)

    print(f"\n✅ Индекс построен: {len(embeddings)} луков → {INDEX_PATH}")


# ─── Поиск ────────────────────────────────────────────────────────────────────

def search(query):
    if not os.path.exists(INDEX_PATH):
        print("❌ Сначала построй индекс (режим 1 или 2)")
        return

    model = load_model()
    if not model:
        return

    embeddings = np.load(INDEX_PATH)
    with open(METADATA_PATH, "r") as f:
        metadata = json.load(f)

    text_feat = model.encode([query], convert_to_numpy=True)[0]
    text_feat = text_feat / np.linalg.norm(text_feat)

    scores = embeddings @ text_feat
    top_indices = np.argsort(scores)[::-1][:TOP_K]

    print(f"\n🔍 Результаты для: \"{query}\"\n")
    for rank, idx in enumerate(top_indices, 1):
        m = metadata[idx]
        print(f"  {rank:2}. [{scores[idx]:.3f}] {m['designer']} — {m['show']} — look {m['look_number']}")
        print(f"       {m['image_url']}\n")


# ─── Классификация ────────────────────────────────────────────────────────────

def classify_all(limit=None):
    model = load_model()
    if not model:
        return

    out_path = "./output/classification_results.csv"
    done_urls = set()
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            for row in csv.DictReader(f):
                done_urls.add(row["image_url"])
        print(f"⏭️  Уже классифицировано: {len(done_urls)}")

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]

    pending = [r for r in rows if r["image_url"] not in done_urls]
    labels = [f"a model wearing {c} on a runway" for c in CLOTHING_CATEGORIES]
    label_feats = model.encode(labels, convert_to_numpy=True)
    label_feats = label_feats / np.linalg.norm(label_feats, axis=1, keepdims=True)

    print(f"👗 Луков для классификации: {len(pending)}")

    with open(out_path, "a", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f,
            fieldnames=["designer", "show", "look_number", "image_url", "clothing_type"])
        if os.stat(out_path).st_size == 0:
            writer.writeheader()

        for i, row in enumerate(pending):
            img = fetch_image(row["image_url"])
            if not img:
                continue

            img_feat = model.encode([img], convert_to_numpy=True)[0]
            img_feat = img_feat / np.linalg.norm(img_feat)
            scores = label_feats @ img_feat
            category = CLOTHING_CATEGORIES[np.argmax(scores)]

            print(f"  [{i+1}/{len(pending)}] {row['designer']} look {row['look_number']} → {category}")
            writer.writerow({
                "designer": row["designer"],
                "show": row["show"],
                "look_number": row["look_number"],
                "image_url": row["image_url"],
                "clothing_type": category,
            })
            out_f.flush()

    print(f"\n✅ Готово → {out_path}")


# ─── Меню ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Fashion AI — CLIP Search & Classification")
    print("=" * 55)
    print()
    print("  1. Построить поисковый индекс (все 16K луков, ~3-4ч)")
    print("  2. Построить индекс — тест (200 луков, ~5 мин)")
    print("  3. Поиск по описанию")
    print("  4. Классифицировать одежду — тест (50 луков)")
    print()
    choice = input("Выбери (1-4): ").strip()

    if choice == "1":
        build_index()
    elif choice == "2":
        build_index(limit=200)
    elif choice == "3":
        query = input("Запрос (напр: 'butter cream knitwear', 'black leather coat'): ").strip()
        search(query)
    elif choice == "4":
        classify_all(limit=50)
    else:
        print("Неверный выбор")
