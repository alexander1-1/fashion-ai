"""
Деплой Fashion-CLIP на HF Space alexanderl12/fashion-ai
========================================================
Загружает: app_hf.py (как app.py), translate_query.py и новый индекс
fclip_index.npy + fclip_metadata.json.

Токен НЕ хранится в коде — только из окружения:
    export HF_TOKEN=hf_...        # новый токен (старый из истории чатов отзови!)
    python3 deploy_hf_fclip.py
"""

import os
import sys

SPACE = "alexanderl12/fashion-ai"
MSG = "Fashion-CLIP: новый индекс + RU-перевод запросов + диверсификация похожих"

FILES = [
    ("Dockerfile.hf", "Dockerfile"),
    ("app_hf.py", "app.py"),
    ("translate_query.py", "translate_query.py"),
    ("output/fclip_index.npy", "output/fclip_index.npy"),
    # metadata сжимаем: 4 MB json не проходит через нестабильную сеть
    ("output/fclip_metadata.json.gz", "output/fclip_metadata.json.gz"),
    # полная разметка (на Space лежал старый частичный CSV — 186 луков);
    # 26 MB идёт через LFS-канал, который у нас проходит стабильно
    ("output/enriched_looks_v3.csv", "output/enriched_looks_v3.csv"),
    ("output/enriched_insights.json", "output/enriched_insights.json"),
]


def _make_gz():
    import gzip, shutil
    src = "output/fclip_metadata.json"
    dst = src + ".gz"
    if os.path.exists(src):
        with open(src, "rb") as fin, gzip.open(dst, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        print(f"Сжал {src} → {dst} ({os.path.getsize(dst)/1e6:.1f} MB)")


def main():
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        sys.exit("Нет HF_TOKEN в окружении. export HF_TOKEN=hf_... и повтори.")

    _make_gz()

    for local, _ in FILES:
        if not os.path.exists(local):
            sys.exit(f"Нет файла {local} — сначала запусти reindex_fashion_clip.py")

    import time
    from huggingface_hub import HfApi
    api = HfApi(token=token)
    for local, remote in FILES:
        size_mb = os.path.getsize(local) / 1e6
        print(f"↑ {local} → {remote} ({size_mb:.1f} MB)")
        for attempt in range(1, 6):
            try:
                api.upload_file(path_or_fileobj=local, path_in_repo=remote,
                                repo_id=SPACE, repo_type="space", commit_message=MSG)
                break
            except Exception as e:
                if attempt == 5:
                    raise
                print(f"  обрыв ({type(e).__name__}), повтор {attempt}/5 через 10 сек…")
                time.sleep(10)
    print("\nГотово. Space пересоберётся ~2-5 мин; в логах должно появиться:")
    print('  "Fashion-CLIP loaded — 17880 looks indexed"')


if __name__ == "__main__":
    main()
