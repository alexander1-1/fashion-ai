"""
Fashion AI — веб-приложение
============================
Запуск:
    pip3 install flask
    python3 app.py

Открыть: http://localhost:5000
"""

import csv
import json
import os
import random
from collections import Counter, defaultdict
from flask import Flask, render_template, jsonify, request, session

app = Flask(__name__)
app.secret_key = "fashion-ai-secret-2026"

# ─── Данные ───────────────────────────────────────────────────────────────────

DATA_DIR = "./output"

PANTONE_RGB = {
    "Black":           (20,  20,  20),
    "Coffee Bean":     (72,  48,  35),
    "Charcoal Gray":   (78,  78,  76),
    "Monument":        (120, 120, 112),
    "Pewter":          (148, 147, 136),
    "Pastel Lilac":    (211, 196, 221),
    "Silver Gray":     (192, 189, 189),
    "Powder Pink":     (237, 212, 207),
    "Silver":          (192, 192, 192),
    "Sage Mist":       (174, 185, 157),
    "Bright White":    (242, 240, 234),
    "Pearled Ivory":   (237, 229, 207),
    "Warm Taupe":      (178, 152, 126),
    "Mushroom":        (196, 172, 152),
    "Chocolate Brown": (75,  45,  32),
    "Butter Cream":    (245, 230, 183),
    "True Red":        (188, 28,  28),
    "Coral":           (231, 114, 88),
    "Classic Blue":    (15,  76,  129),
    "Greenery":        (136, 176, 75),
    "Warm Sand":       (210, 185, 155),
    "Tan Melange":     (185, 157, 128),
    "Rosewood":        (209, 163, 152),
    "Flamingo Pink":   (226, 181, 177),
    "Olive Branch":    (110, 125, 70),
    "Toasted Coconut": (155, 100, 58),
    "Gold Fusion":     (189, 157, 80),
    "Ultra Violet":    (92,  80,  148),
    "Cerulean":        (154, 196, 215),
    "Forest Green":    (46,  86,  50),
}


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_insights():
    """Загружает и агрегирует данные для Insights."""
    rows = load_csv(f"{DATA_DIR}/color_results.csv")
    if not rows:
        return None

    color_counter = Counter()
    designer_counter = Counter()
    show_counter = Counter()

    for row in rows:
        designer_counter[row["designer"]] += 1
        show_counter[row["show"]] += 1
        for j in range(1, 4):
            name = row.get(f"color{j}_pantone", "")
            code = row.get(f"color{j}_code", "")
            if name:
                color_counter[(name, code)] += 1

    top_colors = []
    for (name, code), count in color_counter.most_common(12):
        rgb = PANTONE_RGB.get(name, (128, 128, 128))
        top_colors.append({
            "name": name,
            "code": code,
            "count": count,
            "hex": rgb_to_hex(rgb),
            "rgb": f"rgb{rgb}",
        })

    top_designers = [
        {"name": d, "looks": c}
        for d, c in designer_counter.most_common(10)
    ]

    total_looks = len(rows)
    total_designers = len(designer_counter)
    total_shows = len(show_counter)

    return {
        "top_colors": top_colors,
        "top_designers": top_designers,
        "total_looks": total_looks,
        "total_designers": total_designers,
        "total_shows": total_shows,
    }


def get_all_looks(designer=None, show=None, limit=60, offset=0):
    rows = load_csv(f"{DATA_DIR}/all_designers.csv")
    if designer:
        rows = [r for r in rows if r["designer"].lower() == designer.lower()]
    if show:
        rows = [r for r in rows if r["show"].lower() == show.lower()]
    total = len(rows)
    return rows[offset:offset + limit], total


def get_designers():
    rows = load_csv(f"{DATA_DIR}/all_designers.csv")
    designers = sorted(set(r["designer"] for r in rows))
    return designers


def get_shows(designer=None):
    rows = load_csv(f"{DATA_DIR}/all_designers.csv")
    if designer:
        rows = [r for r in rows if r["designer"] == designer]
    shows = sorted(set(r["show"] for r in rows), reverse=True)
    return shows


# ─── CLIP (загружаем один раз при старте) ─────────────────────────────────────

_clip_model = None
_clip_embeddings = None
_clip_metadata = None

def _load_clip():
    global _clip_model, _clip_embeddings, _clip_metadata
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
        index_path = f"{DATA_DIR}/clip_index.npy"
        meta_path = f"{DATA_DIR}/clip_metadata.json"
        if not (os.path.exists(index_path) and os.path.exists(meta_path)):
            print("CLIP index not found, using text search fallback")
            return
        _clip_embeddings = np.load(index_path)
        with open(meta_path, "r") as f2:
            _clip_metadata = json.load(f2)
        _clip_model = SentenceTransformer("clip-ViT-B-32")
        print(f"CLIP loaded — {len(_clip_metadata)} looks")
    except Exception as e:
        print(f"CLIP not available: {e}")

# _load_clip()  # disabled on Railway

# ─── Маршруты ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("insights.html", insights=get_insights())


@app.route("/explore")
def explore():
    designer = request.args.get("designer", "")
    show = request.args.get("show", "")
    looks, total = get_all_looks(designer or None, show or None, limit=60)
    designers = get_designers()
    shows = get_shows(designer or None)
    return render_template("explore.html",
                           looks=looks, total=total,
                           designers=designers, shows=shows,
                           selected_designer=designer, selected_show=show)


@app.route("/studio")
def studio():
    return render_template("studio.html")


@app.route("/moodboard")
def moodboard():
    saved = session.get("moodboard", [])
    return render_template("moodboard.html", saved=saved)


# ─── API ──────────────────────────────────────────────────────────────────────

HF_SPACES_URL = "https://alexanderl12-fashion-ai.hf.space"

@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    designer_filter = request.args.get("designer", "").strip().lower()
    show_filter = request.args.get("show", "").strip().lower()

    designer = request.args.get("designer", "").strip()
    show = request.args.get("show", "").strip()

    # Проксируем на HF Spaces (там работает CLIP с 16GB RAM)
    try:
        import requests as req
        params = {"q": query}
        if designer:
            params["designer"] = designer
        if show:
            params["show"] = show
        resp = req.get(f"{HF_SPACES_URL}/api/search", params=params, timeout=25)
        if resp.status_code == 200:
            return jsonify(resp.json())
    except Exception as e:
        print(f"HF proxy failed: {e}")

    # Фолбэк: локальный цветовой + текстовый поиск
    return jsonify(_text_search(query, designer=designer, show=show))


def _text_search(query, designer=None, show=None):
    """Возвращает список dict (не Response)."""
    q = query.lower()

    # Маппинг ключевых слов → Pantone названия
    color_keywords = {
        "black": "Black", "чёрный": "Black", "черный": "Black",
        "pink": ["Powder Pink", "Flamingo Pink", "Pastel Lilac"],
        "розовый": ["Powder Pink", "Flamingo Pink"],
        "white": "Bright White", "белый": "Bright White",
        "cream": "Butter Cream", "butter": "Butter Cream", "кремовый": "Butter Cream",
        "beige": "Warm Sand", "бежевый": "Warm Sand",
        "brown": ["Coffee Bean", "Chocolate Brown"], "коричневый": ["Coffee Bean"],
        "grey": ["Charcoal Gray", "Pewter", "Monument"], "gray": ["Charcoal Gray", "Pewter"],
        "серый": ["Charcoal Gray", "Pewter"],
        "green": ["Sage Mist", "Forest Green", "Olive Branch"], "зелёный": ["Sage Mist"],
        "lilac": "Pastel Lilac", "purple": ["Ultra Violet", "Pastel Lilac"],
        "red": "True Red", "красный": "True Red",
        "blue": ["Classic Blue", "Navy Peony", "Cerulean"], "синий": ["Classic Blue"],
        "gold": "Gold Fusion", "золотой": "Gold Fusion",
        "leather": None, "кожа": None,
    }

    target_colors = []
    for kw, colors in color_keywords.items():
        if kw in q:
            if isinstance(colors, list):
                target_colors.extend(colors)
            elif colors:
                target_colors.append(colors)

    # Ищем по color_results.csv если есть
    color_csv = f"{DATA_DIR}/color_results.csv"
    if target_colors and os.path.exists(color_csv):
        rows = load_csv(color_csv)
        results = []
        for row in rows:
            for j in range(1, 4):
                if row.get(f"color{j}_pantone", "") in target_colors:
                    results.append({
                        "designer": row["designer"],
                        "show": row["show"],
                        "look_number": row["look_number"],
                        "image_url": row["image_url"],
                    })
                    break
        if results:
            return results[:96]

    # Последний фолбэк: поиск по имени дизайнера
    rows = load_csv(f"{DATA_DIR}/all_designers.csv")
    results = [r for r in rows if q in r["designer"].lower() or q in r["show"].lower()]
    return results[:96]


@app.route("/api/looks")
def api_looks():
    designer = request.args.get("designer", "")
    show = request.args.get("show", "")
    offset = int(request.args.get("offset", 0))
    looks, total = get_all_looks(designer or None, show or None, limit=40, offset=offset)
    return jsonify({"looks": looks, "total": total})


@app.route("/api/moodboard/add", methods=["POST"])
def moodboard_add():
    data = request.json
    if "moodboard" not in session:
        session["moodboard"] = []
    board = session["moodboard"]
    if data not in board:
        board.append(data)
        session["moodboard"] = board
    return jsonify({"count": len(board)})


@app.route("/api/moodboard/remove", methods=["POST"])
def moodboard_remove():
    data = request.json
    board = session.get("moodboard", [])
    board = [item for item in board if item.get("image_url") != data.get("image_url")]
    session["moodboard"] = board
    return jsonify({"count": len(board)})


@app.route("/api/moodboard/clear", methods=["POST"])
def moodboard_clear():
    session["moodboard"] = []
    return jsonify({"count": 0})


FASHION_SYSTEM_PROMPT = """You are a fashion AI assistant and creative director with deep expertise in runway fashion.

You have analyzed 16,807 looks from 47 designers across Paris, Milan, New York, and London for seasons FW2025-2027.

Key data from this season's runway analysis:
- Dominant colors: Black (63% of looks), Coffee Bean (23%), Charcoal Gray (23%), Monument (19%), Pewter (18%)
- Rising colors: Pastel Lilac (+45% vs FW25), Powder Pink (+28%), Sage Mist (+18%), Earth Tones
- Trending items: Midi skirts (+31%), Embellished jackets (+24%), Oversized knitwear, Leather coats
- Top designers by show volume: Chanel, Valentino, Dolce & Gabbana, Balenciaga, Ralph Lauren, Thom Browne

Your role: help designers, buyers and creative directors with trend analysis, collection direction, color strategy, and creative briefs. Be specific, reference real designers and Pantone codes. Keep responses focused and actionable. When describing colors, use Pantone TCX codes."""


@app.route("/api/studio", methods=["POST"])
def api_studio():
    """Claude API для Studio чата."""
    data = request.json
    messages = data.get("messages", [])

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            # Фильтруем только user/assistant сообщения, убираем system контекст
            history = []
            for m in messages:
                if m["role"] in ("user", "assistant") and not m["content"].startswith("System context:"):
                    history.append({"role": m["role"], "content": m["content"]})
            history = history[-12:]  # последние 12 сообщений
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
            pass  # фолбэк ниже

    # Без API ключа — rule-based ответы
    last = messages[-1]["content"] if messages else ""
    return jsonify({"reply": generate_fallback_reply(last), "mode": "offline"})


def generate_fallback_reply(query):
    """Простые ответы без API ключа."""
    q = query.lower()
    if any(w in q for w in ["color", "colour", "цвет"]):
        return "The dominant palette this FW26 season is anchored in deep neutrals: Black leads with 63% of looks, followed by Coffee Bean and Charcoal Gray. The surprise signal is Pastel Lilac — unexpectedly strong for a fall season, up 45% versus FW25. Powder Pink and Sage Mist round out the key color story."
    if any(w in q for w in ["chanel"]):
        return "Chanel FW26 continued the house's signature refined elegance — structured tweed silhouettes in a muted palette of cream, black and gold. Karl's legacy echoes in the layering, while Virginie Viard's direction adds a quieter, more introspective mood. Key pieces: boucle coats, logo belt bags, satin evening looks."
    if any(w in q for w in ["trend", "rising", "trending"]):
        return "Rising signals from FW26 runway data:\n\n• Pastel Lilac +45% — the unexpected breakout color\n• Midi skirts +31% — returning from the 90s edit\n• Embellished jackets +24% — evening codes bleeding into daywear\n• Powder Pink +28% — soft femininity across multiple houses\n• Earth tones +18% — Warm Taupe, Sage Mist gaining ground"
    if any(w in q for w in ["butter", "cream", "knitwear"]):
        return "Butter Cream knitwear direction for FW26:\n\nSilhouette: relaxed oversized ribbed knit, dropped shoulders, midi length. Fabrication: chunky merino or cashmere-blend in Pantone 12-0722 TCX. Details: minimal — clean neckline, perhaps a single statement button. Styling: layer over a fluid wide-leg trouser in Warm Taupe. References: The Row, Jil Sander, Loro Piana's quiet luxury approach."
    return "Based on FW25-26 runway analysis across 54 designers and 16,807 looks, this season tells a story of refined restraint — dark neutrals dominating, with surprising pops of Pastel Lilac and Powder Pink emerging as key trend signals. What specific aspect would you like to explore?"


if __name__ == "__main__":
    print("🚀 Fashion AI запущен: http://localhost:5000")
    print("   Для Studio с Claude: export ANTHROPIC_API_KEY=your_key")
    app.run(debug=True, port=5000)
