"""
Fashion AI — Railway version (CLIP disabled, proxies to HF Spaces)
"""

import csv
import json
import os
import random
from collections import Counter
from flask import Flask, render_template, jsonify, request, session

app = Flask(__name__)
app.secret_key = "fashion-ai-secret-2026"

DATA_DIR = "./output"
HF_SPACES_URL = "https://alexanderl12-fashion-ai.hf.space"

# ─── City mapping ──────────────────────────────────────────────────────────────
CITY_MAP = {
    # Paris
    "Chanel": "Paris", "Dior": "Paris", "Saint Laurent": "Paris",
    "Givenchy": "Paris", "Valentino": "Paris", "Balenciaga": "Paris",
    "Celine": "Paris", "Loewe": "Paris", "Lanvin": "Paris",
    "Isabel Marant": "Paris", "Miu Miu": "Paris", "Balmain": "Paris",
    "Jacquemus": "Paris", "Rick Owens": "Paris", "Acne Studios": "Paris",
    "A.P.C.": "Paris", "Courrèges": "Paris", "Courreges": "Paris",
    "Stella McCartney": "Paris", "Giambattista Valli": "Paris",
    "Mugler": "Paris", "Jean Paul Gaultier": "Paris", "Schiaparelli": "Paris",
    "Maison Margiela": "Paris", "Kenzo": "Paris", "Issey Miyake": "Paris",
    "Yohji Yamamoto": "Paris", "Comme des Garçons": "Paris",
    "Hermès": "Paris", "Louis Vuitton": "Paris", "Nina Ricci": "Paris",
    "Altuzarra": "Paris", "Roland Mouret": "Paris", "Ami": "Paris",
    # Milan
    "Gucci": "Milan", "Prada": "Milan", "Versace": "Milan",
    "Dolce & Gabbana": "Milan", "Ferragamo": "Milan", "Salvatore Ferragamo": "Milan",
    "Bottega Veneta": "Milan", "Fendi": "Milan", "Armani": "Milan",
    "Giorgio Armani": "Milan", "Emporio Armani": "Milan",
    "Moschino": "Milan", "Max Mara": "Milan", "Tod's": "Milan",
    "Alberta Ferretti": "Milan", "Etro": "Milan", "Jil Sander": "Milan",
    "Marni": "Milan", "Missoni": "Milan", "Dsquared2": "Milan",
    "Sportmax": "Milan", "N.21": "Milan", "Philosophy di Lorenzo Serafini": "Milan",
    "Diesel": "Milan", "Blumarine": "Milan", "Byblos": "Milan",
    "Roberto Cavalli": "Milan", "Vivetta": "Milan", "Ermanno Scervino": "Milan",
    "Antonio Marras": "Milan", "Corneliani": "Milan", "Canali": "Milan",
    "Trussardi": "Milan", "Brioni": "Milan",
    # London
    "Burberry": "London", "Alexander McQueen": "London",
    "Vivienne Westwood": "London", "Victoria Beckham": "London",
    "Erdem": "London", "Simone Rocha": "London", "Roksanda": "London",
    "Richard Quinn": "London", "Emilia Wickstead": "London",
    "Molly Goddard": "London", "Nensi Dojaka": "London",
    "JW Anderson": "London", "Christopher Kane": "London",
    "Mary Katrantzou": "London", "Temperley London": "London",
    "Julien Macdonald": "London", "Amanda Wakeley": "London",
    "Margaret Howell": "London",
    # New York
    "Ralph Lauren": "New York", "Calvin Klein": "New York",
    "Marc Jacobs": "New York", "Tom Ford": "New York",
    "Michael Kors": "New York", "Thom Browne": "New York",
    "Tory Burch": "New York", "Kate Spade": "New York",
    "Carolina Herrera": "New York", "Oscar de la Renta": "New York",
    "Proenza Schouler": "New York", "The Row": "New York",
    "Rodarte": "New York", "Jason Wu": "New York",
    "Alexander Wang": "New York", "Donna Karan": "New York",
    "Vera Wang": "New York", "Derek Lam": "New York",
    "Monse": "New York", "Area": "New York", "Ulla Johnson": "New York",
    "Brandon Maxwell": "New York", "Cushnie": "New York",
}

def get_city(designer):
    if designer in CITY_MAP:
        return CITY_MAP[designer]
    for key, city in CITY_MAP.items():
        if key.lower() in designer.lower() or designer.lower() in key.lower():
            return city
    return "Other"


PANTONE_RGB = {
    "Black":              (20,  20,  20),
    "Coffee Bean":        (72,  48,  35),
    "Charcoal Gray":      (78,  78,  76),
    "Monument":           (120, 120, 112),
    "Pewter":             (148, 147, 136),
    "Silver Gray":        (192, 189, 189),
    "Silver":             (192, 192, 192),
    "Bright White":       (242, 240, 234),
    "Pearled Ivory":      (237, 229, 207),
    "Warm Taupe":         (178, 152, 126),
    "Mushroom":           (196, 172, 152),
    "Warm Sand":          (210, 185, 155),
    "Tan Melange":        (185, 157, 128),
    "Toasted Coconut":    (155, 100, 58),
    "Butter Cream":       (245, 230, 183),
    "Chocolate Brown":    (75,  45,  32),
    "Caramel":            (165, 100, 55),
    "Almond":             (220, 194, 160),
    "Wheat":              (224, 196, 148),
    "Sand Dollar":        (223, 200, 178),
    "Pale Gold":          (210, 183, 130),
    "Pastel Lilac":       (211, 196, 221),
    "Powder Pink":        (237, 212, 207),
    "Flamingo Pink":      (226, 181, 177),
    "Rosewood":           (209, 163, 152),
    "Coral":              (231, 114, 88),
    "Blossom":            (245, 210, 210),
    "Orchid":             (218, 168, 203),
    "Peach Amber":        (241, 178, 135),
    "Rose Quartz":        (247, 202, 201),
    "Candy Pink":         (238, 158, 176),
    "Hot Pink":           (215, 75,  120),
    "Fuchsia Rose":       (199, 67,  117),
    "Mauve Mist":         (196, 168, 178),
    "Classic Blue":       (15,  76,  129),
    "Cerulean":           (154, 196, 215),
    "Pale Blue":          (188, 212, 230),
    "Dusk Blue":          (96,  130, 182),
    "Bijou Blue":         (42,  86,  143),
    "Blue Bell":          (162, 171, 208),
    "Little Boy Blue":    (108, 160, 220),
    "Placid Blue":        (131, 168, 202),
    "Sage Mist":          (174, 185, 157),
    "Forest Green":       (46,  86,  50),
    "Olive Branch":       (110, 125, 70),
    "Greenery":           (136, 176, 75),
    "Fern":               (112, 150, 97),
    "Jade Lime":          (138, 190, 100),
    "Hunter Green":       (52,  84,  52),
    "Basil":              (76,  100, 73),
    "Jade Green":         (0,   163, 104),
    "Pistachio Green":    (146, 188, 132),
    "True Red":           (188, 28,  28),
    "Fiesta":             (221, 65,  36),
    "Living Coral":       (255, 111, 97),
    "Flame Orange":       (243, 118, 74),
    "Burnt Sienna":       (196, 88,  64),
    "Cinnamon Stick":     (157, 82,  50),
    "Ultra Violet":       (92,  80,  148),
    "Amethyst Orchid":    (145, 117, 174),
    "Violet Tulip":       (178, 163, 201),
    "Deep Lavender":      (116, 100, 160),
    "Gold Fusion":        (189, 157, 80),
    "Illuminating":       (245, 220, 80),
    "Saffron":            (224, 166, 48),
    "Amber Yellow":       (233, 185, 64),
    "Primrose Yellow":    (247, 216, 100),
    "Bronze Mist":        (165, 130, 90),
    "Champagne":          (230, 210, 175),
    "Rose Gold":          (220, 160, 140),
}


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_insights():
    rows = load_csv(f"{DATA_DIR}/color_results.csv")
    if not rows:
        return None

    color_counter = Counter()
    designer_counter = Counter()
    show_counter = Counter()
    city_counter = Counter()
    city_designer_sets = {}

    for row in rows:
        d = row["designer"]
        designer_counter[d] += 1
        show_counter[row["show"]] += 1
        city = get_city(d)
        city_counter[city] += 1
        city_designer_sets.setdefault(city, set()).add(d)
        for j in range(1, 4):
            name = row.get(f"color{j}_pantone", "")
            code = row.get(f"color{j}_code", "")
            if name:
                color_counter[(name, code)] += 1

    top_colors = []
    for (name, code), count in color_counter.most_common(16):
        rgb = PANTONE_RGB.get(name, (128, 128, 128))
        top_colors.append({
            "name": name, "code": code, "count": count,
            "hex": rgb_to_hex(rgb), "rgb": f"rgb{rgb}",
        })

    cities = []
    for city in ["Paris", "Milan", "New York", "London", "Other"]:
        if city in city_counter:
            cities.append({
                "name": city,
                "looks": city_counter[city],
                "designers": len(city_designer_sets.get(city, set())),
            })

    return {
        "top_colors": top_colors,
        "top_designers": [{"name": d, "looks": c} for d, c in designer_counter.most_common(10)],
        "total_looks": len(rows),
        "total_designers": len(designer_counter),
        "total_shows": len(show_counter),
        "cities": cities,
        "enrichment": _enrichment_insights,
        "enriched_count": len(_enrichment_index) if _enrichment_index else 0,
    }


def get_all_looks(designer=None, show=None, city=None, category=None, material=None,
                   style=None, silhouette=None, limit=60, offset=0):
    rows = load_csv(f"{DATA_DIR}/all_designers.csv")
    if designer:
        rows = [r for r in rows if r["designer"].lower() == designer.lower()]
    if show:
        rows = [r for r in rows if r["show"].lower() == show.lower()]
    if city:
        rows = [r for r in rows if get_city(r["designer"]) == city]
    if category or material or style or silhouette:
        filtered = []
        for r in rows:
            enr = _enrichment_index.get(r["image_url"]) if _enrichment_index else None
            if not enr:
                continue
            if style and style not in enr["style_tags"]:
                continue
            items = enr["items"]
            if category and not any(it.get("category") == category for it in items):
                continue
            if material and not any(material in (it.get("materials") or []) for it in items):
                continue
            if silhouette and not any(silhouette in (it.get("silhouette") or []) for it in items):
                continue
            filtered.append(r)
        rows = filtered
    total = len(rows)
    page = [enrich_row(dict(r)) for r in rows[offset:offset + limit]]
    return page, total


def get_designers():
    rows = load_csv(f"{DATA_DIR}/all_designers.csv")
    return sorted(set(r["designer"] for r in rows))


def get_shows(designer=None):
    rows = load_csv(f"{DATA_DIR}/all_designers.csv")
    if designer:
        rows = [r for r in rows if r["designer"] == designer]
    return sorted(set(r["show"] for r in rows), reverse=True)


# ─── CLIP: DISABLED on Railway (OOM) — proxies to HF Spaces ───────────────────

# ─── Enrichment (item-level fabric/pattern/silhouette/construction/decoration/style) ──

_enrichment_index = None      # image_url -> {"style_tags": [...], "items": [...]}
_enrichment_insights = None   # parsed output/enriched_insights.json


def load_enrichment():
    global _enrichment_index, _enrichment_insights
    idx = {}
    path = f"{DATA_DIR}/enriched_looks.csv"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    items = json.loads(r.get("items_json") or "[]")
                except json.JSONDecodeError:
                    items = []
                style_tags = [s for s in (r.get("style_tags") or "").split(",") if s]
                idx[r["image_url"]] = {"style_tags": style_tags, "items": items}
    _enrichment_index = idx

    insights_path = f"{DATA_DIR}/enriched_insights.json"
    if os.path.exists(insights_path):
        with open(insights_path, encoding="utf-8") as f:
            _enrichment_insights = json.load(f)
    else:
        _enrichment_insights = None

    print(f"Enrichment loaded: {len(idx)} looks tagged")


load_enrichment()


def enrich_row(row):
    """Attach lightweight tag summary to a look row for card captions."""
    enr = _enrichment_index.get(row.get("image_url")) if _enrichment_index else None
    if enr:
        cats = [it["category"] for it in enr["items"] if it.get("category") not in ("Other", None)]
        row["_categories"] = cats[:4]
        row["_style"] = enr["style_tags"][0] if enr["style_tags"] else ""
    else:
        row["_categories"] = []
        row["_style"] = ""
    return row


def get_facets():
    """Filter option lists for Explore sidebar, derived from enrichment insights."""
    if not _enrichment_insights:
        return {"styles": [], "categories": [], "materials": [], "silhouettes": []}
    return {
        "styles": [x["name"] for x in _enrichment_insights.get("styles", [])],
        "categories": [x["name"] for x in _enrichment_insights.get("categories", [])],
        "materials": [x["name"] for x in _enrichment_insights.get("materials", [])],
        "silhouettes": [x["name"] for x in _enrichment_insights.get("silhouettes", [])],
    }


# ─── Маршруты ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("insights.html", insights=get_insights())


CITIES = ["Paris", "Milan", "New York", "London"]

@app.route("/explore")
def explore():
    designer = request.args.get("designer", "")
    show = request.args.get("show", "")
    city = request.args.get("city", "")
    category = request.args.get("category", "")
    material = request.args.get("material", "")
    style = request.args.get("style", "")
    looks, total = get_all_looks(designer or None, show or None, city or None,
                                  category or None, material or None, style or None,
                                  limit=60)
    designers = get_designers()
    shows = get_shows(designer or None)
    facets = get_facets()
    return render_template("explore.html",
                           looks=looks, total=total,
                           designers=designers, shows=shows,
                           cities=CITIES, facets=facets,
                           enriched_count=len(_enrichment_index) if _enrichment_index else 0,
                           selected_designer=designer,
                           selected_show=show,
                           selected_city=city,
                           selected_category=category,
                           selected_material=material,
                           selected_style=style)


@app.route("/studio")
def studio():
    return render_template("studio.html")


@app.route("/moodboard")
def moodboard():
    return render_template("moodboard.html")


# ─── API ──────────────────────────────────────────────────────────────────────

def _wake_hf():
    """Ping HF Spaces to wake it from sleep."""
    try:
        import requests as req
        req.get(f"{HF_SPACES_URL}/", timeout=5)
    except Exception:
        pass


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    designer = request.args.get("designer", "").strip()
    show = request.args.get("show", "").strip()
    city = request.args.get("city", "").strip()

    try:
        import requests as req
        params = {"q": query}
        if designer: params["designer"] = designer
        if show: params["show"] = show
        if city: params["city"] = city
        _wake_hf()
        resp = req.get(f"{HF_SPACES_URL}/api/search", params=params, timeout=90)
        if resp.status_code == 200:
            return jsonify(resp.json())
    except Exception as e:
        print(f"HF proxy /api/search failed: {e}")

    return jsonify(_text_search(query, designer=designer.lower(), show=show.lower(), city=city))


@app.route("/api/similar")
def api_similar():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify([])
    try:
        import requests as req
        _wake_hf()
        resp = req.get(f"{HF_SPACES_URL}/api/similar", params={"url": url}, timeout=90)
        if resp.status_code == 200:
            return jsonify(resp.json())
    except Exception as e:
        print(f"HF proxy /api/similar failed: {e}")
    return jsonify([])


def _text_search(query, designer="", show="", city=""):
    """Fallback: color + text search. Returns list of dicts."""
    q = query.lower()

    color_keywords = {
        "black": ["Black"], "чёрный": ["Black"], "черный": ["Black"],
        "pink": ["Powder Pink", "Flamingo Pink", "Pastel Lilac"],
        "розовый": ["Powder Pink", "Flamingo Pink"],
        "white": ["Bright White"], "белый": ["Bright White"],
        "cream": ["Butter Cream"], "butter": ["Butter Cream"],
        "beige": ["Warm Sand"], "бежевый": ["Warm Sand"],
        "brown": ["Coffee Bean", "Chocolate Brown"],
        "grey": ["Charcoal Gray", "Pewter"], "gray": ["Charcoal Gray", "Pewter"],
        "green": ["Sage Mist", "Forest Green", "Olive Branch"],
        "lilac": ["Pastel Lilac"], "purple": ["Ultra Violet", "Pastel Lilac"],
        "red": ["True Red"], "красный": ["True Red"],
        "blue": ["Classic Blue", "Cerulean"], "синий": ["Classic Blue"],
        "gold": ["Gold Fusion"], "coral": ["Coral"],
        "silver": ["Silver", "Silver Gray"], "ivory": ["Pearled Ivory"],
        "taupe": ["Warm Taupe"], "mushroom": ["Mushroom"],
    }

    target_colors = []
    for kw, colors in color_keywords.items():
        if kw in q:
            target_colors.extend(colors)

    def apply_filters(rows):
        if designer:
            rows = [r for r in rows if designer in r["designer"].lower()]
        if show:
            rows = [r for r in rows if show in r["show"].lower()]
        if city:
            rows = [r for r in rows if get_city(r["designer"]) == city]
        return rows

    color_csv = f"{DATA_DIR}/color_results.csv"
    if target_colors and os.path.exists(color_csv):
        rows = apply_filters(load_csv(color_csv))
        results = []
        for row in rows:
            for j in range(1, 4):
                if row.get(f"color{j}_pantone", "") in target_colors:
                    results.append({
                        "designer": row["designer"], "show": row["show"],
                        "look_number": row["look_number"], "image_url": row["image_url"],
                        "mode": "color",
                    })
                    break
        if results:
            return results[:96]

    rows = apply_filters(load_csv(f"{DATA_DIR}/all_designers.csv"))
    results = [r for r in rows if q in r["designer"].lower() or q in r["show"].lower()]
    if results:
        return results[:96]

    if rows:
        sample = random.sample(rows, min(24, len(rows)))
        for r in sample:
            r["mode"] = "random"
        return sample

    return []


@app.route("/api/looks")
def api_looks():
    designer = request.args.get("designer", "")
    show = request.args.get("show", "")
    city = request.args.get("city", "")
    category = request.args.get("category", "")
    material = request.args.get("material", "")
    style = request.args.get("style", "")
    offset = int(request.args.get("offset", 0))
    looks, total = get_all_looks(designer or None, show or None, city or None,
                                  category or None, material or None, style or None,
                                  limit=40, offset=offset)
    return jsonify({"looks": looks, "total": total})


@app.route("/api/facets")
def api_facets():
    return jsonify(get_facets())


@app.route("/api/enrichment-status")
def api_enrichment_status():
    total = len(load_csv(f"{DATA_DIR}/all_designers.csv"))
    enriched = len(_enrichment_index) if _enrichment_index else 0
    return jsonify({"enriched": enriched, "total": total,
                     "pct": round(enriched / total * 100, 1) if total else 0})


@app.route("/api/reload-enrichment", methods=["POST"])
def api_reload_enrichment():
    load_enrichment()
    return jsonify({"enriched": len(_enrichment_index) if _enrichment_index else 0})


@app.route("/api/moodboard/add", methods=["POST"])
def moodboard_add():
    # Legacy: moodboard now uses localStorage. Keep endpoint for compat.
    return jsonify({"count": 0})


@app.route("/api/moodboard/remove", methods=["POST"])
def moodboard_remove():
    return jsonify({"count": 0})


@app.route("/api/moodboard/clear", methods=["POST"])
def moodboard_clear():
    return jsonify({"count": 0})


FASHION_SYSTEM_PROMPT = """You are a fashion AI assistant and creative director with deep expertise in runway fashion.

You have analyzed 16,807 looks from 47 designers across Paris, Milan, New York, and London for seasons FW2025-2027.

Key data from this season's runway analysis:
- Dominant colors: Black (63% of looks), Coffee Bean (23%), Charcoal Gray (23%), Monument (19%), Pewter (18%)
- Rising colors: Pastel Lilac (+45% vs FW25), Powder Pink (+28%), Sage Mist (+18%), Earth Tones
- Trending items: Midi skirts (+31%), Embellished jackets (+24%), Oversized knitwear, Leather coats
- Top designers by show volume: Chanel, Valentino, Dolce & Gabbana, Balenciaga, Ralph Lauren, Thom Browne

Your role: help designers, buyers and creative directors with trend analysis, collection direction, color strategy, and creative briefs. Be specific, reference real designers and Pantone codes. Keep responses focused and actionable."""


@app.route("/api/studio", methods=["POST"])
def api_studio():
    data = request.json
    messages = data.get("messages", [])
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in messages
                if m["role"] in ("user", "assistant")
                and not m["content"].startswith("System context:")
            ][-12:]
            if not history:
                return jsonify({"reply": "How can I help you with your collection?"})
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                system=FASHION_SYSTEM_PROMPT,
                messages=history,
            )
            return jsonify({"reply": response.content[0].text})
        except Exception as e:
            print(f"Claude API error: {e}")

    last = messages[-1]["content"] if messages else ""
    return jsonify({"reply": _fallback_reply(last), "mode": "offline"})


def _fallback_reply(query):
    q = query.lower()
    if any(w in q for w in ["color", "colour", "цвет"]):
        return "The dominant palette this FW26 season: Black (63%), Coffee Bean (23%), Charcoal Gray. The breakout signal: Pastel Lilac +45% vs FW25. Powder Pink and Sage Mist round out the key color story."
    if "chanel" in q:
        return "Chanel FW26: structured tweed silhouettes in cream, black and gold. Key pieces: boucle coats, logo belt bags, satin evening looks."
    if any(w in q for w in ["trend", "rising", "trending"]):
        return "Rising signals FW26: Pastel Lilac +45%, Midi skirts +31%, Embellished jackets +24%, Powder Pink +28%, Earth tones +18%."
    return "Based on FW25-26 runway analysis across 54 designers and 16,807 looks — dark neutrals dominate with Pastel Lilac and Powder Pink as key trend signals. What would you like to explore?"


if __name__ == "__main__":
    print("Fashion AI: http://localhost:5000")
    app.run(debug=True, port=5000)
