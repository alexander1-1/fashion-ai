"""
Fashion AI — пересчёт Insights после обогащения датасета (v2: full recognition)
================================================================================
Читает enriched_looks.csv (схема v2: style_tags, items_json) и строит
аналитику по 6 измерениям: style, category, material, pattern, silhouette,
construction, decoration. Все item-level измерения считаются по количеству
ПРЕДМЕТОВ (items), а не луков — один look может дать несколько items.

Запуск:
    python3 update_insights.py
"""

import csv
import json
import os
from collections import Counter

DATA_DIR = "./output"
ENRICHED_CSV = f"{DATA_DIR}/enriched_looks.csv"
INSIGHTS_JSON = f"{DATA_DIR}/enriched_insights.json"


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pct(count, total):
    return round(count / total * 100, 1) if total else 0


def top_n(counter, total, n=12, exclude=("Other", "")):
    return [
        {"name": name, "count": count, "pct": pct(count, total)}
        for name, count in counter.most_common(n + len(exclude))
        if name not in exclude
    ][:n]


def main():
    rows = load_csv(ENRICHED_CSV)
    if not rows:
        print(f"❌ {ENRICHED_CSV} not found. Run enrich_looks.py first.")
        return

    total_looks = len(rows)
    print(f"✓ Loaded {total_looks} enriched looks")

    style_counter = Counter()
    category_counter = Counter()
    material_counter = Counter()
    pattern_counter = Counter()
    silhouette_counter = Counter()
    construction_counter = Counter()
    decoration_counter = Counter()

    designer_style = {}      # designer -> Counter of style_tags
    designer_category = {}   # designer -> Counter of categories

    total_items = 0
    parse_errors = 0

    for row in rows:
        designer = row.get("designer", "")

        style_tags = [s for s in (row.get("style_tags") or "").split(",") if s]
        for s in style_tags:
            style_counter[s] += 1
        if designer and style_tags:
            bucket = designer_style.setdefault(designer, Counter())
            for s in style_tags:
                bucket[s] += 1

        try:
            items = json.loads(row.get("items_json") or "[]")
        except json.JSONDecodeError:
            parse_errors += 1
            items = []

        for it in items:
            total_items += 1
            category = it.get("category", "Other") or "Other"
            category_counter[category] += 1
            if designer:
                designer_category.setdefault(designer, Counter())[category] += 1

            for m in it.get("materials", []) or []:
                material_counter[m] += 1

            pattern = it.get("pattern", "Other") or "Other"
            pattern_counter[pattern] += 1

            for s in it.get("silhouette", []) or []:
                silhouette_counter[s] += 1

            for c in it.get("construction", []) or []:
                construction_counter[c] += 1

            for d in it.get("decoration", []) or []:
                decoration_counter[d] += 1

    insights = {
        "total_looks": total_looks,
        "total_items": total_items,
        "parse_errors": parse_errors,
        "styles": top_n(style_counter, total_looks, 12),
        "categories": top_n(category_counter, total_items, 14),
        "materials": top_n(material_counter, total_items, 14),
        "patterns": top_n(pattern_counter, total_items, 10),
        "silhouettes": top_n(silhouette_counter, total_items, 12),
        "construction": top_n(construction_counter, total_items, 12),
        "decoration": top_n(decoration_counter, total_items, 12),
    }

    with open(INSIGHTS_JSON, "w", encoding="utf-8") as f:
        json.dump(insights, f, ensure_ascii=False, indent=2)

    print(f"✓ Saved to {INSIGHTS_JSON}")
    print(f"  Total looks: {total_looks} · Total items: {total_items} · Avg items/look: {total_items/total_looks:.1f}")
    print()

    def show(title, key, bar_div=2):
        print(f"── TOP {title} ──")
        for item in insights[key][:8]:
            bar = "█" * int(item["pct"] / bar_div)
            print(f"  {item['name']:28s} {item['pct']:5.1f}%  {bar}")
        print()

    show("STYLES", "styles", 2)
    show("CATEGORIES", "categories", 2)
    show("MATERIALS", "materials", 3)
    show("PATTERNS", "patterns", 2)
    show("SILHOUETTES", "silhouettes", 3)
    show("CONSTRUCTION", "construction", 3)
    show("DECORATION", "decoration", 3)

    print("✅ Insights ready. Add to app to show in dashboard.")


if __name__ == "__main__":
    main()
