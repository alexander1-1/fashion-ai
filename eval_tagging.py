"""
eval_tagging.py — оценка точности vision-пайплайна против golden set
=====================================================================
Сравнивает предсказания (enriched_looks_v3.csv) с ручной разметкой
(output/golden_set.json) по 7 измерениям.

Критерии запуска массового прогона (TREND_PLATFORM_INSTRUCTION.md §2.6):
  category ≥ 95%, materials ≥ 80%, construction ≥ 75%, decoration ≥ 75%.

Запуск:
    python3 eval_tagging.py
    python3 eval_tagging.py --golden output/golden_set.json \\
                            --pred output/enriched_looks_v3.csv

Метрики:
  - category: доля gold-предметов, чья категория найдена в предсказании
  - pattern: точное совпадение среди сматченных предметов
  - остальные (set-поля): recall — доля gold-меток, найденных моделью
    (+ precision справочно). Поля с "not_visible" в gold пропускаются.

Выход: таблица + код возврата 0/1 (можно использовать в CI).
"""

import argparse
import csv
import json
import sys
from collections import defaultdict

from taxonomy import NOT_VISIBLE

THRESHOLDS = {
    "category": 0.95,
    "materials": 0.80,
    "construction": 0.75,
    "decoration": 0.75,
    # справочные (порогов в методике нет):
    "pattern": None,
    "silhouette": None,
    "styles": None,
}

SET_FIELDS = ["materials", "silhouette", "construction", "decoration"]


def load_golden(path):
    with open(path, encoding="utf-8") as f:
        golden = json.load(f)
    return {g["image_url"]: g for g in golden}


def load_predictions(path):
    preds = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            preds[r["image_url"]] = {
                "styles": [s for s in r["style_tags"].split(",") if s],
                "items": json.loads(r["items_json"]),
            }
    return preds


def match_items(gold_items, pred_items):
    """Жадный матчинг предметов по категории."""
    used = set()
    pairs = []
    for g in gold_items:
        for i, p in enumerate(pred_items):
            if i not in used and p["category"] == g["category"]:
                used.add(i)
                pairs.append((g, p))
                break
    return pairs


def _clean(values):
    return {v for v in (values or []) if v and v != NOT_VISIBLE}


def evaluate(golden, preds):
    cat_total = cat_hit = 0
    pat_total = pat_hit = 0
    set_tp = defaultdict(int)   # найденные gold-метки
    set_fn = defaultdict(int)   # пропущенные gold-метки
    set_fp = defaultdict(int)   # лишние предсказанные метки
    missing = []

    for url, g in golden.items():
        p = preds.get(url)
        if p is None:
            missing.append(url)
            continue

        # styles — look-level
        gs, ps = _clean(g.get("styles")), _clean(p.get("styles"))
        if gs:
            set_tp["styles"] += len(gs & ps)
            set_fn["styles"] += len(gs - ps)
            set_fp["styles"] += len(ps - gs)

        gold_items = g.get("items", [])
        pred_items = p.get("items", [])
        pred_cats = [it["category"] for it in pred_items]

        for gi in gold_items:
            cat_total += 1
            if gi["category"] in pred_cats:
                cat_hit += 1

        for gi, pi in match_items(gold_items, pred_items):
            gp = gi.get("pattern")
            if gp and gp != NOT_VISIBLE:
                pat_total += 1
                if pi.get("pattern") == gp:
                    pat_hit += 1
            for field in SET_FIELDS:
                gset = _clean(gi.get(field))
                pset = _clean(pi.get(field))
                if not gset and not pset:
                    continue
                set_tp[field] += len(gset & pset)
                set_fn[field] += len(gset - pset)
                set_fp[field] += len(pset - gset)

    rows = []

    def add(name, recall, extra=""):
        thr = THRESHOLDS.get(name)
        if recall is None:  # в golden set нет меток этого измерения
            status = "⚪ n/a"
        elif thr is None:
            status = ""
        else:
            status = "✅ PASS" if recall >= thr else "❌ FAIL"
        rows.append((name, recall, thr, extra, status))

    add("category", cat_hit / cat_total if cat_total else None,
        f"{cat_hit}/{cat_total}")
    add("pattern", pat_hit / pat_total if pat_total else None,
        f"{pat_hit}/{pat_total}")
    for field in SET_FIELDS + ["styles"]:
        tp, fn, fp = set_tp[field], set_fn[field], set_fp[field]
        recall = tp / (tp + fn) if tp + fn else None
        precision = tp / (tp + fp) if tp + fp else 0.0
        add(field, recall, f"precision {precision:.0%}")

    return rows, missing


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--golden", default="output/golden_set.json")
    p.add_argument("--pred", default="output/enriched_looks_v3.csv")
    args = p.parse_args()

    try:
        golden = load_golden(args.golden)
    except FileNotFoundError:
        sys.exit(f"❌ {args.golden} не найден. Сначала разметь golden set "
                 f"(python3 build_golden_set.py, затем annotate.html)")
    try:
        preds = load_predictions(args.pred)
    except FileNotFoundError:
        sys.exit(f"❌ {args.pred} не найден. Прогони golden-луки: "
                 f"python3 enrich_looks.py --sample …")

    rows, missing = evaluate(golden, preds)

    print(f"\n📏 Golden set: {len(golden)} луков, "
          f"предсказаний: {len(golden) - len(missing)}")
    if missing:
        print(f"⚠️  Нет предсказаний для {len(missing)} луков "
              f"(прогони их через enrich_looks.py)")
    print(f"\n{'Измерение':<14}{'Recall':>8}{'Порог':>8}  {'Инфо':<18}Статус")
    print("─" * 62)
    failed = False
    for name, recall, thr, extra, status in rows:
        thr_s = f"{thr:.0%}" if thr else "—"
        rec_s = f"{recall:.1%}" if recall is not None else "n/a"
        print(f"{name:<14}{rec_s:>7}{thr_s:>8}  {extra:<18}{status}")
        if status.startswith("❌"):
            failed = True
    print("─" * 62)
    if failed:
        print("❌ Пороги не пройдены — итерируй промпт/кропы, "
              "НЕ запускай полный прогон.")
        sys.exit(1)
    print("✅ Все пороги пройдены — можно запускать полный прогон:\n"
          "   python3 enrich_looks.py --full --confirm-full")


if __name__ == "__main__":
    main()
