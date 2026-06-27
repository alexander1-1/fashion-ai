"""
Загрузка датасета на Hugging Face
===================================
Загружает all_designers.csv как приватный датасет на HuggingFace Hub.

Установка:
    pip3 install huggingface_hub datasets

Запуск:
    python3 upload_to_hf.py

Потребуется HF токен: https://huggingface.co/settings/tokens
"""

import os
import csv

# ─── Настройки ────────────────────────────────────────────────────────────────

CSV_PATH = "./output/all_designers.csv"
DATASET_NAME = "runway-fw2526"   # имя датасета на HF (будет: username/runway-fw2526)
PRIVATE = True                    # True = приватный датасет

# ─── Основной код ─────────────────────────────────────────────────────────────

def main():
    try:
        from huggingface_hub import HfApi, login
        from datasets import Dataset
        import pandas as pd
    except ImportError:
        print("❌ Установи: pip3 install huggingface_hub datasets pandas")
        return

    # Авторизация
    print("🔑 Авторизация в Hugging Face...")
    print("Токен можно получить на: https://huggingface.co/settings/tokens")
    token = input("Введи HF токен (write access): ").strip()
    if not token:
        print("❌ Токен не введён")
        return

    login(token=token)
    api = HfApi()

    # Получаем username
    user = api.whoami()
    username = user["name"]
    repo_id = f"{username}/{DATASET_NAME}"
    print(f"✅ Авторизован как: {username}")
    print(f"📦 Датасет будет загружен как: {repo_id}")

    # Загружаем CSV
    print(f"\n📂 Читаю {CSV_PATH}...")
    if not os.path.exists(CSV_PATH):
        print(f"❌ Файл не найден: {CSV_PATH}")
        return

    df = pd.read_csv(CSV_PATH)
    print(f"✅ Загружено строк: {len(df)}")
    print(f"   Дизайнеров: {df['designer'].nunique()}")
    print(f"   Показов:    {df['show'].nunique()}")

    # Создаём HF Dataset
    dataset = Dataset.from_pandas(df)

    # Создаём репозиторий
    print(f"\n🚀 Создаю репозиторий {repo_id}...")
    api.create_repo(
        repo_id=DATASET_NAME,
        repo_type="dataset",
        private=PRIVATE,
        exist_ok=True,
    )

    # Загружаем
    print("⬆️  Загружаю датасет...")
    dataset.push_to_hub(repo_id, private=PRIVATE, token=token)

    print(f"\n🎉 Готово!")
    print(f"   URL: https://huggingface.co/datasets/{repo_id}")
    print(f"\nДля загрузки в коде:")
    print(f'   from datasets import load_dataset')
    print(f'   ds = load_dataset("{repo_id}", use_auth_token=True)')


if __name__ == "__main__":
    main()
