"""
Vogue Runway Scraper — скрипт запуска
======================================
Запусти: python run_scraper.py

Три режима:
  1. Один показ → CSV с URL фото
  2. Все показы одного дизайнера → CSV
  3. Все дизайнеры из файла → master CSV

Фото НЕ скачиваются по умолчанию (только URL).
Для скачивания используй режим 4.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import vogue

OUTPUT_DIR = "./output"
DESIGNERS_FILE = "./designers_fw26.txt"


def load_designers(path: str) -> list[str]:
    """Читает список дизайнеров из .txt файла, пропуская комментарии."""
    designers = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                designers.append(line)
    return designers


def mode_1_single_show():
    print("\n── Режим 1: один показ ──")
    designer = input("Имя дизайнера (напр: Chanel): ").strip()
    if not designer:
        return

    shows = vogue.designer_to_shows(designer)
    if not shows:
        print("Показы не найдены.")
        return

    print(f"\nДоступные показы для {designer}:")
    for i, show in enumerate(shows[:20], 1):
        print(f"  {i:2}. {show}")

    choice = input("\nНомер показа (или введи название вручную): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(shows):
        show = shows[int(choice) - 1]
    else:
        show = choice

    count = vogue.designer_show_to_csv(designer, show, OUTPUT_DIR)
    if count:
        print(f"\n✅ {count} луков сохранено в {OUTPUT_DIR}/")


def mode_2_all_shows():
    print("\n── Режим 2: все показы дизайнера ──")
    designer = input("Имя дизайнера (напр: Gucci): ").strip()
    if not designer:
        return
    vogue.designer_to_csv(designer, OUTPUT_DIR)


def mode_3_all_designers():
    print(f"\n── Режим 3: все дизайнеры из {DESIGNERS_FILE} ──")
    if not os.path.exists(DESIGNERS_FILE):
        print(f"Файл не найден: {DESIGNERS_FILE}")
        return
    designers = load_designers(DESIGNERS_FILE)
    print(f"Загружено {len(designers)} дизайнеров")
    confirm = input("Начать? (y/n): ").strip().lower()
    if confirm != "y":
        return
    vogue.all_designers_to_csv(designers, OUTPUT_DIR)


def mode_4_download_images():
    print("\n── Режим 4: скачать фото одного показа ──")
    designer = input("Имя дизайнера: ").strip()
    show = input("Название показа (напр: Fall 2026 Ready-to-Wear): ").strip()
    if not designer or not show:
        return
    vogue.download_images(designer, show, os.path.join(OUTPUT_DIR, "images"))


def mode_5_list_shows():
    print("\n── Режим 5: список показов дизайнера ──")
    designer = input("Имя дизайнера: ").strip()
    if not designer:
        return
    shows = vogue.designer_to_shows(designer)
    for i, show in enumerate(shows, 1):
        print(f"  {i:3}. {show}")


def main():
    print("=" * 50)
    print("  Vogue Runway Scraper")
    print("=" * 50)
    print()
    print("  1. Один показ → CSV")
    print("  2. Все показы одного дизайнера → CSV")
    print("  3. Все дизайнеры из designers_fw26.txt → master CSV")
    print("  4. Скачать фото одного показа (JPG)")
    print("  5. Посмотреть список показов дизайнера")
    print()
    choice = input("Выбери режим (1-5): ").strip()

    modes = {
        "1": mode_1_single_show,
        "2": mode_2_all_shows,
        "3": mode_3_all_designers,
        "4": mode_4_download_images,
        "5": mode_5_list_shows,
    }

    fn = modes.get(choice)
    if fn:
        fn()
    else:
        print("Неверный выбор.")


if __name__ == "__main__":
    main()
