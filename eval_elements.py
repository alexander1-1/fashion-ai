"""
eval_elements.py — валидация детекции ключевых тренд-элементов
===============================================================
Метрика уровня ЛУКА: элемент считается найденным, если присутствует
в любом предмете лука (так тренд-движок считает частоты: «доля луков
с воротником-стойкой»). Сопоставление предметов не требуется — уходит
шум субъективной привязки деталей к слоям.

Статус элемента:
  ✅ доверенный   — recall ≥ 75% и precision ≥ 50% (support ≥ 5)
  ⚠️  наблюдение  — метрики ниже; тренд-движок помечает такие тренды
                    как требующие ручной проверки
  · мало данных   — support < 5 в golden set (вывод ненадёжен)

Запуск:
    python3 eval_elements.py
Результат: таблица + output/trusted_elements.json (для trends.py, Фаза 2)
"""

import argparse
import json
import os
import sys

from eval_tagging import load_golden, load_predictions, _clean

# Ключевые тренд-элементы (Тренд-копилка + кейсы из презентаций)
KEY_ELEMENTS = {
    "construction": [
        "Stand Collar", "Dropped Shoulder", "Puff Sleeves", "Wide Shoulders",
        "Wrap Closure", "Peplum", "Pleats", "Drawstrings", "Asymmetry",
        "Draping", "Patch Pockets", "Cargo Pockets", "V-Neck", "Halter",
        "Off-Shoulder",
    ],
    "decoration": [
        "Lace Trim", "Fringe", "Ruffles", "Statement Buttons", "Sequins",
        "Bows", "Metal Hardware", "Embroidery",
    ],
    "materials": [
        "Lace", "Denim", "Leather/Faux Leather", "Suede", "Satin", "Tweed",
        "Velvet", "Fur/Faux Fur", "Sheer Fabric",
    ],
    "pattern": [
        "Animal Print", "Floral", "Stripes", "Checks/Plaid", "Polka Dots",
    ],
}

MIN_RECALL, MIN_PRECISION, MIN_SUPPORT = 0.75, 0.50, 5


def look_elements(look, field):
    """Все значения поля по луку (любой предмет)."""
    out = set()
    for it in look.get("items", []):
        vals = it.get(field)
        if field == "pattern":
            vals = [vals] if vals else []
        out |= _clean(vals)
    return out


def _default_pred():
    for p in ("output/golden_pred_haiku.csv", "output/golden_pred_sonnet.csv",
              "output/enriched_looks_v3.csv"):
        if os.path.exists(p):
            return p
    return "output/golden_pred_haiku.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", default=None,
                    help="CSV с предсказаниями (по умолчанию — свежий "
                         "golden_pred_*.csv)")
    args = ap.parse_args()
    pred_path = args.pred or _default_pred()
    golden = load_golden("output/golden_set.json")
    try:
        preds = load_predictions(pred_path)
    except FileNotFoundError:
        sys.exit("❌ Нет предсказаний: python3 enrich_looks.py --golden")
    print(f"Предсказания: {pred_path}")

    rows, trusted = [], []
    for field, elements in KEY_ELEMENTS.items():
        for el in elements:
            tp = fp = fn = 0
            for url, g in golden.items():
                p = preds.get(url)
                if p is None:
                    continue
                in_g = el in look_elements(g, field)
                in_p = el in look_elements(p, field)
                tp += in_g and in_p
                fp += in_p and not in_g
                fn += in_g and not in_p
            support = tp + fn
            recall = tp / support if support else 0.0
            precision = tp / (tp + fp) if tp + fp else 0.0
            if support < MIN_SUPPORT:
                status = "· мало данных"
            elif recall >= MIN_RECALL and precision >= MIN_PRECISION:
                status = "✅ доверенный"
                trusted.append({"field": field, "element": el,
                                "recall": round(recall, 2),
                                "precision": round(precision, 2),
                                "support": support})
            else:
                status = "⚠️  наблюдение"
            rows.append((field, el, support, recall, precision, status))

    print(f"\n{'Поле':<13}{'Элемент':<22}{'Supp':>5}{'Recall':>8}"
          f"{'Prec':>7}  Статус")
    print("─" * 70)
    for field, el, sup, rec, prec, status in rows:
        print(f"{field:<13}{el:<22}{sup:>5}{rec:>8.0%}{prec:>7.0%}  {status}")
    print("─" * 70)

    n_ok = len(trusted)
    n_eval = sum(1 for r in rows if not r[5].startswith("·"))
    with open("output/trusted_elements.json", "w", encoding="utf-8") as f:
        json.dump(trusted, f, ensure_ascii=False, indent=1)
    print(f"Доверенных элементов: {n_ok}/{n_eval} (support ≥ {MIN_SUPPORT})"
          f" → output/trusted_elements.json")
    print("Тренд-движок (Фаза 2) будет авто-заводить тренды только по "
          "доверенным элементам;\nостальные — с пометкой «ручная проверка».")


if __name__ == "__main__":
    main()
