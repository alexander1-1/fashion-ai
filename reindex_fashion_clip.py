"""
Переиндексация подиума на Fashion-CLIP
=======================================
Строит новый векторный индекс всех луков из output/all_designers.csv
моделью patrickjohncyh/fashion-clip (CLIP ViT-B/32, дообученный на
800K fashion-пар Farfetch; F1 0.83 vs 0.66 у ванильного CLIP).

Пишет в НОВЫЕ файлы (старый индекс не трогает):
    output/fclip_index.npy      — эмбеддинги (N, 512), unit-norm, float32
    output/fclip_metadata.json  — [{designer, show, look_number, image_url}]

app_hf.py автоматически подхватывает fclip_* при старте, если файлы есть.

Установка (один раз):
    pip3 install torch transformers pillow requests numpy

Запуск:
    python3 reindex_fashion_clip.py                # весь каталог (~17 880)
    python3 reindex_fashion_clip.py --limit 100    # быстрый тест
    python3 reindex_fashion_clip.py --selftest     # проверка готового индекса

Прерывать можно в любой момент — прогресс сохраняется каждые 200 луков,
повторный запуск продолжит с места остановки.
"""

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import numpy as np
import requests
from PIL import Image

CSV_PATH   = "./output/all_designers.csv"
INDEX_PATH = "./output/fclip_index.npy"
META_PATH  = "./output/fclip_metadata.json"
MODEL_ID   = "patrickjohncyh/fashion-clip"
BATCH_SIZE = 32          # изображений на один forward
DL_THREADS = 8           # параллельных скачиваний
SAVE_EVERY = 200         # автосохранение каждые N луков

_session = requests.Session()
_session.headers["User-Agent"] = "Mozilla/5.0"


def pick_device():
    import torch
    if torch.backends.mps.is_available():
        return "mps"          # Apple Silicon — в разы быстрее CPU
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_model():
    import torch
    from transformers import CLIPModel, CLIPProcessor
    device = pick_device()
    print(f"Загружаю {MODEL_ID} (первый раз ~600MB) → device={device}")
    model = CLIPModel.from_pretrained(MODEL_ID).to(device).eval()
    processor = CLIPProcessor.from_pretrained(MODEL_ID)
    return model, processor, device


def fetch_image(url):
    """Качаем уменьшенную версию (w_320) — CLIP всё равно ресайзит до 224."""
    small = url.replace("w_1024", "w_320")
    for attempt_url in (small, url):
        try:
            resp = _session.get(attempt_url, timeout=15)
            if resp.status_code != 200:
                continue
            return Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception:
            continue
    return None


def encode_batch(model, processor, device, images):
    import torch
    inputs = processor(images=images, return_tensors="pt").to(device)
    with torch.no_grad():
        feats = model.get_image_features(**inputs)
    feats = feats.cpu().numpy().astype(np.float32)
    return feats / (np.linalg.norm(feats, axis=1, keepdims=True) + 1e-9)


def save(embeddings, metadata):
    np.save(INDEX_PATH, np.asarray(embeddings, dtype=np.float32))
    with open(META_PATH, "w") as f:
        json.dump(metadata, f)


def build(limit=None):
    model, processor, device = load_model()

    embeddings, metadata, done_urls = [], [], set()
    if os.path.exists(INDEX_PATH) and os.path.exists(META_PATH):
        embeddings = list(np.load(INDEX_PATH))
        metadata = json.load(open(META_PATH))
        done_urls = {m["image_url"] for m in metadata}
        print(f"Продолжаю: уже готово {len(metadata)}")

    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]
    pending = [r for r in rows if r["image_url"] not in done_urls]
    total = len(pending)
    print(f"К обработке: {total} луков (всего в каталоге {len(rows)})")

    t0, processed, failed = time.time(), 0, 0
    pool = ThreadPoolExecutor(max_workers=DL_THREADS)

    for i in range(0, total, BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        images_raw = list(pool.map(lambda r: fetch_image(r["image_url"]), batch))
        images, valid = [], []
        for img, row in zip(images_raw, batch):
            if img is not None:
                images.append(img)
                valid.append(row)
            else:
                failed += 1
        if not images:
            continue

        feats = encode_batch(model, processor, device, images)
        for vec, row in zip(feats, valid):
            embeddings.append(vec)
            metadata.append({
                "designer": row["designer"],
                "show": row["show"],
                "look_number": row["look_number"],
                "image_url": row["image_url"],
            })

        processed += len(batch)
        if len(metadata) % SAVE_EVERY < BATCH_SIZE:
            save(embeddings, metadata)

        rate = processed / max(time.time() - t0, 1)
        eta_min = (total - processed) / max(rate, 0.1) / 60
        print(f"  [{processed}/{total}] {rate:.1f} лук/с · ETA {eta_min:.0f} мин "
              f"· ошибок {failed} · {valid[-1]['designer']} #{valid[-1]['look_number']}")

    save(embeddings, metadata)
    print(f"\nГотово: {len(metadata)} луков → {INDEX_PATH}")
    if failed:
        print(f"Не скачалось {failed} фото (повторный запуск попробует ещё раз)")


def selftest():
    """Прогон контрольных запросов по готовому индексу."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    if not os.path.exists(INDEX_PATH):
        print("Индекс не найден — сначала запусти сборку")
        return
    emb = np.load(INDEX_PATH)
    meta = json.load(open(META_PATH))
    print(f"Индекс: {emb.shape[0]} луков, dim={emb.shape[1]}")

    device = pick_device()
    model = CLIPModel.from_pretrained(MODEL_ID).to(device).eval()
    processor = CLIPProcessor.from_pretrained(MODEL_ID)

    queries = [
        "tweed jacket and skirt suit",
        "red evening gown",
        "leopard animal print dress",
        "oversized chunky knit cardigan",
        "black leather biker jacket",
    ]
    for q in queries:
        inputs = processor(text=[q], return_tensors="pt", padding=True).to(device)
        with torch.no_grad():
            tf = model.get_text_features(**inputs).cpu().numpy()[0]
        tf = tf / (np.linalg.norm(tf) + 1e-9)
        scores = emb @ tf
        top = np.argsort(scores)[::-1][:5]
        print(f"\n«{q}»")
        for idx in top:
            m = meta[int(idx)]
            print(f"  {scores[idx]:.3f}  {m['designer']} · {m['show']} · #{m['look_number']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="обработать только N луков (тест)")
    ap.add_argument("--selftest", action="store_true", help="контрольные запросы по индексу")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        build(limit=args.limit)
