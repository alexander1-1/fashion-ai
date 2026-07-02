"""
merge_golden_set.py — слияние частей разметки golden set
=========================================================
Объединяет вашу часть и часть коллеги в итоговый output/golden_set.json
(формат для eval_tagging.py, без служебного поля verified).

Запуск:
    python3 merge_golden_set.py output/golden_set_part1.json \\
                                output/golden_set_part2.json

Правило: при пересечении по image_url побеждает более поздний файл
(порядок аргументов), verified=true приоритетнее verified=false.
"""

import json
import sys

OUT = "output/golden_set.json"


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    merged = {}
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as f:
            part = json.load(f)
        n_new = n_upd = 0
        for look in part:
            url = look["image_url"]
            if url not in merged:
                merged[url] = look
                n_new += 1
            else:
                # не затираем проверенное непроверенным
                if look.get("verified", True) or \
                        not merged[url].get("verified", False):
                    merged[url] = look
                    n_upd += 1
        print(f"  {path}: {len(part)} луков (+{n_new} новых, "
              f"{n_upd} обновлено)")

    looks = list(merged.values())
    n_verified = sum(1 for l in looks if l.get("verified", True))
    n_items = sum(1 for l in looks if l.get("items"))
    for l in looks:
        l.pop("verified", None)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(looks, f, ensure_ascii=False, indent=1)
    print(f"✅ {OUT}: {len(looks)} луков, с предметами: {n_items}, "
          f"проверено: {n_verified}")
    if n_items < len(looks):
        print(f"⚠️  {len(looks) - n_items} луков без предметов — "
              f"их стоит доразметить")


if __name__ == "__main__":
    main()
