"""
Fashion AI — обогащение датасета через Claude Vision (v2: full recognition)
============================================================================
Читает output/all_designers.csv, для каждого лука распознаёт ВСЕ видимые
предметы гардероба (жакет, юбка, обувь, сумка и т.д.) и тегирует каждый
по 6 измерениям на основе контролируемого словаря "Тренд-копилка":
  - category      (тип предмета)
  - materials     (материал/фактура, может быть несколько)
  - pattern       (принт/узор)
  - silhouette    (силуэт — может быть несколько признаков)
  - construction  (элементы кроя — несколько)
  - decoration    (отделка — несколько)
Плюс look-level стилистика (style_tags) — общая эстетика образа.

Запуск:
    python3 enrich_looks.py                  # все луки
    python3 enrich_looks.py --sample 50      # тест на первых 50
    python3 enrich_looks.py --resume         # продолжить с места остановки

Результат: output/enriched_looks.csv
Формат: designer, show, look_number, image_url, style_tags, items_json

items_json — JSON-массив предметов, например:
[{"category":"Jacket/Blazer","materials":["Tweed"],"pattern":"Checks/Plaid",
  "silhouette":["Oversized"],"construction":["Wide Shoulders"],"decoration":["Piping"]},
 {"category":"Skirt","materials":["Tweed"],"pattern":"Solid",
  "silhouette":["A-line"],"construction":[],"decoration":["Statement Buttons"]},
 {"category":"Shoes/Boots","materials":["Leather/Faux Leather"],"pattern":"Solid",
  "silhouette":[],"construction":[],"decoration":[]}]

Цена: ~$0.05-0.08 на 100 луков (claude-haiku vision, больше output-токенов чем в v1)
"""

import csv
import json
import os
import sys
import time
import argparse
import base64

# ─── Контролируемый словарь (из "Тренд-копилка для AI-анализа коллекций") ────

ITEM_CATEGORIES = [
    "Coat", "Jacket/Blazer", "Suit", "Dress", "Gown/Evening",
    "Jumpsuit/Romper", "Top/Blouse", "Shirt", "Knitwear/Cardigan",
    "Pants/Trousers", "Skirt", "Shorts", "Vest", "Cape/Poncho",
    "Swimwear", "Lingerie/Corset",
    "Bag", "Shoes/Boots", "Belt", "Hat", "Scarf", "Gloves",
    "Jewelry/Accessory", "Sunglasses", "Other",
]

MATERIALS = [
    "Leather/Faux Leather", "Suede", "Denim", "Chunky Knit", "Fine Knit",
    "Ribbed Knit", "Suiting Fabric", "Satin", "Chiffon", "Organza",
    "Lace", "Mesh", "Velvet", "Tweed", "Bouclé", "Fur/Faux Fur",
    "Nylon", "Cotton", "Linen", "Textured Knit", "Sheer Fabric",
    "Metallic Fabric", "Technical Fabric", "Trench/Rain Fabric",
    "Soft Base Knit", "Artisanal Texture Fabric", "Crinkled Texture",
    "Other",
]

PATTERNS = [
    "Solid", "Stripes", "Checks/Plaid", "Floral", "Animal Print",
    "Abstract", "Geometric", "Polka Dots", "Paisley", "Camouflage",
    "Houndstooth", "Tie-dye", "Ombre", "Patchwork", "Logo/Monogram",
    "Embroidery Print", "Other",
]

SILHOUETTES = [
    "Straight", "Fitted/Waisted", "Semi-Fitted", "Relaxed", "Oversized",
    "Elongated", "Cropped", "A-line", "X-Silhouette", "Trapeze",
    "Cocoon", "Column", "Hourglass", "Volume Top + Slim Bottom",
    "Slim Top + Volume Bottom", "Shoulder Emphasis", "Waist Emphasis",
    "Hip Emphasis", "Low Rise", "High Rise", "Wide Leg/Flare",
    "Slim Leg", "Layered Silhouette", "Athletic Relaxed",
]

CONSTRUCTION = [
    "Darts", "Princess Seams", "Draping", "Asymmetry", "Wrap Closure",
    "Peplum", "Pleats", "Tucks", "Drawstrings", "Gathers", "Flounces",
    "Puff Sleeves", "Extended Cuffs", "Wide Shoulders", "Dropped Shoulder",
    "Stand Collar", "High Neck", "Polo Collar", "Shirt Collar", "Halter",
    "Off-Shoulder", "Boat Neck", "Square Neckline", "V-Neck",
    "Cutout Neckline", "Slits", "Patch Pockets", "Cargo Pockets",
    "Waist Seam", "Layered Details", "Convertible Elements",
    "Statement Closure", "Structural Zipper",
]

DECORATION = [
    "Lace Trim", "Ruffles", "Frills", "Fringe", "Embroidery", "Appliqué",
    "Contrast Stitching", "Piping", "Bows", "Ties", "Lacing",
    "Decorative Zippers", "Metal Hardware", "Grommets",
    "Statement Buttons", "Sequins", "Rhinestones", "Perforation",
    "Textured Inserts", "Sheer Inserts", "Side Stripes", "Sport Stripes",
    "Logos", "Monograms", "Decorative Pockets",
]

STYLES = [
    "Minimalism", "Quiet Luxury", "New Classic", "Ladylike", "New Femininity",
    "Power Dressing", "Office Aesthetic", "Soft Tailoring", "Preppy",
    "Collegiate/Schoolgirl", "Old Money", "Country Aesthetic", "Country Club",
    "Boho", "Romantic", "Boudoir", "Grunge", "Streetwear", "Sport as Status",
    "Wellness", "Utilitarian", "Outdoor", "Moto", "70s Retro", "90s Retro",
    "Y2K", "2010s Nostalgia", "Eclectic", "Loud Luxury", "Quiet Status",
    "Body-conscious Basics", "Intellectual Fashion", "Artisanal/Craft", "Resort",
]

# ─── Промпт ───────────────────────────────────────────────────────────────────

SYSTEM = (
    "You are an expert fashion trend analyst working like tfashion.ai. "
    "You analyze runway photos and extract EVERY visible garment and accessory "
    "as a separate item, tagging each with precise, controlled-vocabulary labels. "
    "You never invent labels outside the provided lists."
)

PROMPT = f"""Analyze this runway look photo in FULL detail. Identify EVERY distinct visible garment and accessory (not just the main piece) — typically this includes: main top/dress, bottom (if separate), outerwear (if layered), shoes, bag (if visible), and any notable accessory (belt, hat, scarf, gloves, jewelry, sunglasses).

Return ONLY valid JSON with this exact structure:

{{
  "style_tags": ["<0-3 values from: {', '.join(STYLES)}>"],
  "items": [
    {{
      "category": "<one of: {', '.join(ITEM_CATEGORIES)}>",
      "materials": ["<1-2 values from: {', '.join(MATERIALS)}>"],
      "pattern": "<one of: {', '.join(PATTERNS)}>",
      "silhouette": ["<0-2 values from: {', '.join(SILHOUETTES)}> (leave empty [] for bags/shoes/accessories)"],
      "construction": ["<0-3 values from: {', '.join(CONSTRUCTION)}> (leave empty [] if none clearly visible)"],
      "decoration": ["<0-3 values from: {', '.join(DECORATION)}> (leave empty [] if none clearly visible)"]
    }}
  ]
}}

Rules:
- Detect ALL distinct garment/accessory pieces visible in the photo (usually 3-6 items). Do not merge separate pieces into one entry.
- style_tags describes the OVERALL look's aesthetic (look-level), not per item.
- Use ONLY values from the provided lists — never invent new terms. If nothing fits well, use "Other" (for category/materials/pattern) or an empty list (for silhouette/construction/decoration/style_tags).
- silhouette/construction/decoration apply mainly to garments, not accessories — use empty lists for bags, shoes, jewelry, sunglasses unless a construction/decoration detail is clearly visible on them.
- Return ONLY the JSON object, no markdown fences, no other text."""

MAX_TOKENS = 1400

# ─── Загрузка изображения (base64) ───────────────────────────────────────────

def fetch_image_b64(url: str) -> tuple[str, str]:
    """Download image and return (base64_data, media_type)."""
    import urllib.request
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FashionAI/1.0)"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        if content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            content_type = "image/jpeg"
        return base64.standard_b64encode(data).decode("utf-8"), content_type


# ─── Валидация / очистка ответа модели ───────────────────────────────────────

def _coerce_list(values, allowed, max_n):
    if not isinstance(values, list):
        return []
    out = []
    allowed_set = set(allowed)
    for v in values:
        if isinstance(v, str) and v in allowed_set and v not in out:
            out.append(v)
        if len(out) >= max_n:
            break
    return out


def _coerce_single(value, allowed, default="Other"):
    if isinstance(value, str) and value in allowed:
        return value
    return default


def validate_result(raw: dict) -> dict:
    """Clean/validate raw parsed JSON against controlled vocabulary."""
    style_tags = _coerce_list(raw.get("style_tags"), STYLES, 3)

    items_in = raw.get("items")
    if not isinstance(items_in, list):
        items_in = []

    items_out = []
    for it in items_in[:8]:  # hard cap
        if not isinstance(it, dict):
            continue
        category = _coerce_single(it.get("category"), ITEM_CATEGORIES, "Other")
        materials = _coerce_list(it.get("materials"), MATERIALS, 2)
        if not materials:
            materials = ["Other"]
        pattern = _coerce_single(it.get("pattern"), PATTERNS, "Solid")
        silhouette = _coerce_list(it.get("silhouette"), SILHOUETTES, 2)
        construction = _coerce_list(it.get("construction"), CONSTRUCTION, 3)
        decoration = _coerce_list(it.get("decoration"), DECORATION, 3)
        items_out.append({
            "category": category,
            "materials": materials,
            "pattern": pattern,
            "silhouette": silhouette,
            "construction": construction,
            "decoration": decoration,
        })

    if not items_out:
        items_out = [{
            "category": "Other", "materials": ["Other"], "pattern": "Other",
            "silhouette": [], "construction": [], "decoration": [],
        }]

    return {"style_tags": style_tags, "items": items_out}


FALLBACK = {"style_tags": [], "items": [{
    "category": "Other", "materials": ["Other"], "pattern": "Other",
    "silhouette": [], "construction": [], "decoration": [],
}]}


# ─── Анализ одного лука ───────────────────────────────────────────────────────

def analyze_look(client, image_url: str, retries: int = 3) -> dict:
    """Call Claude Haiku Vision and return validated tags."""
    for attempt in range(retries):
        try:
            b64, media_type = fetch_image_b64(image_url)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }],
            )
            text = response.content[0].text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            raw = json.loads(text)
            return validate_result(raw)
        except json.JSONDecodeError:
            print(f"    JSON parse error, attempt {attempt+1}")
            time.sleep(2)
        except Exception as e:
            print(f"    Error: {e}, attempt {attempt+1}")
            time.sleep(5 * (attempt + 1))
    return FALLBACK


def summarize(tags: dict) -> str:
    cats = [it["category"] for it in tags["items"]]
    styles = ", ".join(tags["style_tags"][:2]) or "—"
    return f"{len(tags['items'])} items ({', '.join(cats[:4])}{'…' if len(cats) > 4 else ''}) · style: {styles}"


# ─── Основной код ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0,
                        help="Process only first N looks (0 = all)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip already processed looks")
    parser.add_argument("--batch-delay", type=float, default=0.5,
                        help="Seconds to wait between API calls")
    parser.add_argument("--data-dir", default="./output",
                        help="Path to output/ directory with CSVs")
    args = parser.parse_args()

    DATA_DIR = args.data_dir
    INPUT_CSV = f"{DATA_DIR}/all_designers.csv"
    OUTPUT_CSV = f"{DATA_DIR}/enriched_looks.csv"

    if not os.path.exists(INPUT_CSV):
        print(f"❌ {INPUT_CSV} not found. Run the scraper first.")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("❌ Set ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        print("❌ pip install anthropic")
        sys.exit(1)

    with open(INPUT_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.sample:
        rows = rows[:args.sample]
    print(f"📊 Total looks to process: {len(rows)}")

    processed = {}
    if args.resume and os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                processed[r["image_url"]] = r
        print(f"✓ Already processed: {len(processed)}")

    fieldnames = [
        "designer", "show", "look_number", "image_url",
        "style_tags", "items_json",
    ]
    mode = "a" if args.resume and os.path.exists(OUTPUT_CSV) else "w"
    out_f = open(OUTPUT_CSV, mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=fieldnames)
    if mode == "w":
        writer.writeheader()

    total = len(rows)
    done = 0
    skipped = 0
    errors = 0

    for i, row in enumerate(rows):
        url = row.get("image_url", "")
        if not url:
            continue

        if args.resume and url in processed:
            skipped += 1
            continue

        print(f"[{i+1}/{total}] {row['designer']} · {row['show']} · Look {row['look_number']}", end=" ")

        tags = analyze_look(client, url)
        print(f"→ {summarize(tags)}")

        out_row = {
            "designer": row["designer"],
            "show": row["show"],
            "look_number": row["look_number"],
            "image_url": url,
            "style_tags": ",".join(tags["style_tags"]),
            "items_json": json.dumps(tags["items"], ensure_ascii=False),
        }
        writer.writerow(out_row)
        out_f.flush()

        done += 1
        if tags["items"][0]["category"] == "Other" and len(tags["items"]) == 1:
            errors += 1

        time.sleep(args.batch_delay)

        if done % 100 == 0:
            print(f"\n── Checkpoint: {done} processed, {skipped} skipped, {errors} errors ──\n")

    out_f.close()

    print(f"\n✅ Done!")
    print(f"   Processed: {done}")
    print(f"   Skipped:   {skipped}")
    print(f"   Errors:    {errors}")
    print(f"   Output:    {OUTPUT_CSV}")
    print(f"\nNext: run python3 update_insights.py to rebuild analytics")


if __name__ == "__main__":
    main()
