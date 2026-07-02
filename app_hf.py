"""
Fashion AI — веб-приложение
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

# ─── Русские переводы тегов (для отображения; фильтрация идёт по англ. значению) ──
TAG_RU = {
    # Style
    "Minimalism": "Минимализм", "Quiet Luxury": "Дорогая простота",
    "New Classic": "Новая классика", "Ladylike": "Ladylike / собранная женственность",
    "New Femininity": "Новая женственность", "Power Dressing": "Power dressing",
    "Office Aesthetic": "Офисная эстетика", "Soft Tailoring": "Мягкий костюмный стиль",
    "Preppy": "Преппи", "Collegiate/Schoolgirl": "Школьные и университетские коды",
    "Old Money": "Old money", "Country Aesthetic": "Загородная эстетика",
    "Country Club": "Эстетика закрытых клубов", "Boho": "Бохо",
    "Romantic": "Романтический стиль", "Boudoir": "Будуарные элементы",
    "Grunge": "Гранж", "Streetwear": "Уличная эстетика",
    "Sport as Status": "Спорт как статус", "Wellness": "Wellness-эстетика",
    "Utilitarian": "Утилитарность", "Outdoor": "Outdoor-коды",
    "Moto": "Мото-эстетика", "70s Retro": "Ретро 70-х", "90s Retro": "Ретро 90-х",
    "Y2K": "2000-е", "2010s Nostalgia": "Ностальгия по 2010-м",
    "Eclectic": "Эклектика", "Loud Luxury": "Заметный статус",
    "Quiet Status": "Сдержанный статус", "Body-conscious Basics": "Телесная база",
    "Intellectual Fashion": "Интеллектуальная мода", "Artisanal/Craft": "Ремесленная эстетика",
    "Resort": "Курортная эстетика",
    # Silhouette
    "Straight": "Прямой", "Fitted/Waisted": "Приталенный", "Semi-Fitted": "Полуприлегающий",
    "Relaxed": "Свободный", "Oversized": "Оверсайз", "Elongated": "Вытянутый",
    "Cropped": "Укороченный", "A-line": "А-силуэт", "X-Silhouette": "Х-силуэт",
    "Trapeze": "Трапеция", "Cocoon": "Кокон", "Column": "Колонна",
    "Hourglass": "Песочные часы", "Volume Top + Slim Bottom": "Объёмный верх + узкий низ",
    "Slim Top + Volume Bottom": "Узкий верх + объёмный низ",
    "Shoulder Emphasis": "Акцент на плечи", "Waist Emphasis": "Акцент на талии",
    "Hip Emphasis": "Акцент на бёдра", "Low Rise": "Заниженная посадка",
    "High Rise": "Высокая посадка", "Wide Leg/Flare": "Широкий низ",
    "Slim Leg": "Узкий низ", "Layered Silhouette": "Многослойный силуэт",
    "Athletic Relaxed": "Спортивный расслабленный",
    # Construction
    "Darts": "Вытачки", "Princess Seams": "Рельефы", "Draping": "Драпировки",
    "Asymmetry": "Асимметрия", "Wrap Closure": "Запах", "Peplum": "Баска",
    "Pleats": "Складки", "Tucks": "Защипы", "Drawstrings": "Кулиски",
    "Gathers": "Сборки", "Flounces": "Воланы", "Puff Sleeves": "Рукава-фонарики",
    "Extended Cuffs": "Удлинённые манжеты", "Wide Shoulders": "Широкие плечи",
    "Dropped Shoulder": "Спущенное плечо", "Stand Collar": "Воротник-стойка",
    "High Neck": "Высокий ворот", "Polo Collar": "Воротник поло",
    "Shirt Collar": "Отложной воротник", "Halter": "Халтер",
    "Off-Shoulder": "Открытые плечи", "Boat Neck": "Вырез лодочка",
    "Square Neckline": "Квадратный вырез", "V-Neck": "V-вырез",
    "Cutout Neckline": "Фигурные вырезы", "Slits": "Разрезы",
    "Patch Pockets": "Накладные карманы", "Cargo Pockets": "Карманы карго",
    "Waist Seam": "Отрезная талия", "Layered Details": "Многослойные детали",
    "Convertible Elements": "Трансформируемые элементы",
    "Statement Closure": "Акцентная застёжка", "Structural Zipper": "Молния как конструкция",
    # Decoration
    "Lace Trim": "Кружево (отделка)", "Ruffles": "Оборки", "Frills": "Рюши",
    "Fringe": "Бахрома", "Embroidery": "Вышивка", "Appliqué": "Аппликации",
    "Contrast Stitching": "Контрастная строчка", "Piping": "Канты", "Bows": "Банты",
    "Ties": "Завязки", "Lacing": "Шнуровка", "Decorative Zippers": "Молнии",
    "Metal Hardware": "Металлическая фурнитура", "Grommets": "Люверсы",
    "Statement Buttons": "Декоративные пуговицы", "Sequins": "Пайетки",
    "Rhinestones": "Стразы", "Perforation": "Перфорация",
    "Textured Inserts": "Фактурные вставки", "Sheer Inserts": "Прозрачные вставки",
    "Side Stripes": "Лампасы", "Sport Stripes": "Спортивные полосы",
    "Logos": "Логотипы", "Monograms": "Монограммы",
    "Decorative Pockets": "Декоративные карманы",
    # Materials
    "Leather/Faux Leather": "Кожа и экокожа", "Suede": "Замша", "Denim": "Деним",
    "Chunky Knit": "Плотный трикотаж", "Fine Knit": "Тонкий трикотаж",
    "Ribbed Knit": "Рубчик", "Suiting Fabric": "Костюмная ткань", "Satin": "Сатин",
    "Chiffon": "Шифон", "Organza": "Органза", "Lace": "Кружево", "Mesh": "Сетка",
    "Velvet": "Бархат", "Tweed": "Твид", "Bouclé": "Букле",
    "Fur/Faux Fur": "Мех и экомех", "Nylon": "Нейлон", "Cotton": "Хлопок",
    "Linen": "Лён", "Textured Knit": "Фактурная вязка",
    "Sheer Fabric": "Прозрачные материалы", "Metallic Fabric": "Металлизированные ткани",
    "Technical Fabric": "Технические ткани", "Trench/Rain Fabric": "Плащевые материалы",
    "Soft Base Knit": "Мягкий трикотаж для базы",
    "Artisanal Texture Fabric": "Ткани с ремесленным эффектом",
    "Crinkled Texture": "Жатая фактура",
    # Category
    "Coat": "Пальто", "Jacket/Blazer": "Жакет/Блейзер", "Suit": "Костюм",
    "Dress": "Платье", "Gown/Evening": "Вечернее платье",
    "Jumpsuit/Romper": "Комбинезон", "Top/Blouse": "Топ/Блуза", "Shirt": "Рубашка",
    "Knitwear/Cardigan": "Трикотаж/Кардиган", "Pants/Trousers": "Брюки",
    "Skirt": "Юбка", "Shorts": "Шорты", "Vest": "Жилет",
    "Cape/Poncho": "Накидка/Пончо", "Swimwear": "Купальник",
    "Lingerie/Corset": "Бельё/Корсет", "Bag": "Сумка", "Shoes/Boots": "Обувь",
    "Belt": "Ремень", "Hat": "Головной убор", "Scarf": "Шарф",
    "Gloves": "Перчатки", "Jewelry/Accessory": "Украшения", "Sunglasses": "Очки",
    # Pattern
    "Solid": "Однотонный", "Stripes": "Полоска", "Checks/Plaid": "Клетка",
    "Floral": "Цветочный принт", "Animal Print": "Анималистичный принт",
    "Abstract": "Абстрактный", "Geometric": "Геометрический", "Polka Dots": "Горох",
    "Paisley": "Пейсли", "Camouflage": "Камуфляж", "Houndstooth": "Гусиная лапка",
    "Tie-dye": "Тай-дай", "Ombre": "Омбре", "Patchwork": "Пэчворк",
    "Logo/Monogram": "Логотип/Монограмма", "Embroidery Print": "Вышитый принт",
    # Misc
    "Other": "Другое", "Paris": "Париж", "Milan": "Милан",
    "New York": "Нью-Йорк", "London": "Лондон",
}


def tag_ru(value):
    return TAG_RU.get(value, value)


app.jinja_env.filters["ru"] = tag_ru

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
    "Stella Tennant": "London", "Margaret Howell": "London",
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
    """Map designer name to fashion week city."""
    if designer in CITY_MAP:
        return CITY_MAP[designer]
    # Partial match
    for key, city in CITY_MAP.items():
        if key.lower() in designer.lower() or designer.lower() in key.lower():
            return city
    return "Other"


PANTONE_RGB = {
    # Neutrals & darks
    "Black":              (20,  20,  20),
    "Coffee Bean":        (72,  48,  35),
    "Charcoal Gray":      (78,  78,  76),
    "Monument":           (120, 120, 112),
    "Pewter":             (148, 147, 136),
    "Silver Gray":        (192, 189, 189),
    "Silver":             (192, 192, 192),
    "Bright White":       (242, 240, 234),
    "Pearled Ivory":      (237, 229, 207),
    # Warm neutrals
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
    # Pinks & lilacs
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
    # Blues
    "Classic Blue":       (15,  76,  129),
    "Cerulean":           (154, 196, 215),
    "Pale Blue":          (188, 212, 230),
    "Dusk Blue":          (96,  130, 182),
    "Bijou Blue":         (42,  86,  143),
    "Blue Bell":          (162, 171, 208),
    "Little Boy Blue":    (108, 160, 220),
    "Placid Blue":        (131, 168, 202),
    # Greens
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
    # Reds & oranges
    "True Red":           (188, 28,  28),
    "Fiesta":             (221, 65,  36),
    "Living Coral":       (255, 111, 97),
    "Flame Orange":       (243, 118, 74),
    "Burnt Sienna":       (196, 88,  64),
    "Cinnamon Stick":     (157, 82,  50),
    # Purples
    "Ultra Violet":       (92,  80,  148),
    "Amethyst Orchid":    (145, 117, 174),
    "Violet Tulip":       (178, 163, 201),
    "Deep Lavender":      (116, 100, 160),
    # Yellows & golds
    "Gold Fusion":        (189, 157, 80),
    "Illuminating":       (245, 220, 80),
    "Saffron":            (224, 166, 48),
    "Amber Yellow":       (233, 185, 64),
    "Primrose Yellow":    (247, 216, 100),
    # Metallics
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


def get_insights(designer=None, show=None):
    rows = load_csv(f"{DATA_DIR}/color_results.csv")
    if designer:
        rows = [r for r in rows if r["designer"].lower() == designer.lower()]
    if show:
        rows = [r for r in rows if r["show"].lower() == show.lower()]
    if not rows:
        return None

    color_counter = Counter()
    designer_counter = Counter()
    show_counter = Counter()
    city_counter = Counter()
    city_designer_sets = {}  # city → set of designers

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
        "enrichment": compute_enrichment(designer, show) if (designer or show) else _enrichment_insights,
        "enriched_count": len(_enrichment_index) if _enrichment_index else 0,
    }


def get_all_looks(designer=None, show=None, city=None, category=None, material=None,
                   style=None, silhouette=None, construction=None, decoration=None,
                   limit=60, offset=0):
    rows = load_csv(f"{DATA_DIR}/all_designers.csv")
    if designer:
        rows = [r for r in rows if r["designer"].lower() == designer.lower()]
    if show:
        rows = [r for r in rows if r["show"].lower() == show.lower()]
    if city:
        rows = [r for r in rows if get_city(r["designer"]) == city]
    if category or material or style or silhouette or construction or decoration:
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
            if construction and not any(construction in (it.get("construction") or []) for it in items):
                continue
            if decoration and not any(decoration in (it.get("decoration") or []) for it in items):
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
            print("CLIP index files not found, using text search fallback")
            return
        _clip_embeddings = np.load(index_path)
        with open(meta_path, "r") as f:
            _clip_metadata = json.load(f)
        _clip_model = SentenceTransformer("clip-ViT-B-32")
        print(f"CLIP model loaded — {len(_clip_metadata)} looks indexed")
    except Exception as e:
        print(f"CLIP not available: {e}")


_load_clip()

# ─── Enrichment (item-level fabric/pattern/silhouette/construction/decoration/style) ──

_enrichment_index = None      # image_url -> {"style_tags": [...], "items": [...]}
_enrichment_insights = None   # parsed output/enriched_insights.json


_enrichment_rows = []  # [{"designer","show","style_tags":[...],"items":[...]}] for filterable Insights


def load_enrichment():
    global _enrichment_index, _enrichment_insights, _enrichment_rows
    idx = {}
    rows_list = []
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
                rows_list.append({
                    "designer": r.get("designer", ""),
                    "show": r.get("show", ""),
                    "style_tags": style_tags,
                    "items": items,
                })
    _enrichment_index = idx
    _enrichment_rows = rows_list

    insights_path = f"{DATA_DIR}/enriched_insights.json"
    if os.path.exists(insights_path):
        with open(insights_path, encoding="utf-8") as f:
            _enrichment_insights = json.load(f)
    else:
        _enrichment_insights = None

    print(f"Enrichment loaded: {len(idx)} looks tagged"
          + (f" · insights ready ({_enrichment_insights['total_items']} items)" if _enrichment_insights else " · no insights.json yet"))


load_enrichment()


def _pct(count, total):
    return round(count / total * 100, 1) if total else 0


def compute_enrichment(designer=None, show=None):
    """Recompute the 7-dimension enrichment stats, optionally filtered by designer/show."""
    if not _enrichment_rows:
        return None
    rows = _enrichment_rows
    if designer:
        rows = [r for r in rows if r["designer"].lower() == designer.lower()]
    if show:
        rows = [r for r in rows if r["show"].lower() == show.lower()]
    if not rows:
        return None

    style_c = Counter()
    category_c = Counter()
    material_c = Counter()
    pattern_c = Counter()
    silhouette_c = Counter()
    construction_c = Counter()
    decoration_c = Counter()
    total_items = 0

    for r in rows:
        for s in r["style_tags"]:
            style_c[s] += 1
        for it in r["items"]:
            total_items += 1
            category_c[it.get("category", "Other") or "Other"] += 1
            for m in it.get("materials", []) or []:
                material_c[m] += 1
            pattern_c[it.get("pattern", "Other") or "Other"] += 1
            for s in it.get("silhouette", []) or []:
                silhouette_c[s] += 1
            for c in it.get("construction", []) or []:
                construction_c[c] += 1
            for d in it.get("decoration", []) or []:
                decoration_c[d] += 1

    total_looks = len(rows)

    def top(counter, base, n=14):
        return [
            {"name": name, "count": count, "pct": _pct(count, base)}
            for name, count in counter.most_common(n + 1)
            if name not in ("Other", "")
        ][:n]

    return {
        "total_looks": total_looks,
        "total_items": total_items,
        "styles": top(style_c, total_looks, 12),
        "categories": top(category_c, total_items, 14),
        "materials": top(material_c, total_items, 14),
        "patterns": top(pattern_c, total_items, 10),
        "silhouettes": top(silhouette_c, total_items, 12),
        "construction": top(construction_c, total_items, 12),
        "decoration": top(decoration_c, total_items, 12),
    }


def enrich_row(row):
    """Attach lightweight (Russian-translated) tag summary to a look row for card captions."""
    enr = _enrichment_index.get(row.get("image_url")) if _enrichment_index else None
    if enr:
        cats = [it["category"] for it in enr["items"] if it.get("category") not in ("Other", None)]
        row["_categories"] = [tag_ru(c) for c in cats[:4]]
        row["_style"] = tag_ru(enr["style_tags"][0]) if enr["style_tags"] else ""
    else:
        row["_categories"] = []
        row["_style"] = ""
    return row


def get_facets():
    """Filter option lists for Explore sidebar, derived from enrichment insights."""
    if not _enrichment_insights:
        return {"styles": [], "categories": [], "materials": [], "silhouettes": [],
                 "construction": [], "decoration": []}
    return {
        "styles": [x["name"] for x in _enrichment_insights.get("styles", [])],
        "categories": [x["name"] for x in _enrichment_insights.get("categories", [])],
        "materials": [x["name"] for x in _enrichment_insights.get("materials", [])],
        "silhouettes": [x["name"] for x in _enrichment_insights.get("silhouettes", [])],
        "construction": [x["name"] for x in _enrichment_insights.get("construction", [])],
        "decoration": [x["name"] for x in _enrichment_insights.get("decoration", [])],
    }


# ─── Маршруты ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    designer = request.args.get("designer", "")
    show = request.args.get("show", "")
    return render_template("insights.html",
                           insights=get_insights(designer or None, show or None),
                           designers=get_designers(),
                           shows=get_shows(),
                           selected_designer=designer,
                           selected_show=show)


CITIES = ["Paris", "Milan", "New York", "London"]

@app.route("/explore")
def explore():
    designer = request.args.get("designer", "")
    show = request.args.get("show", "")
    city = request.args.get("city", "")
    category = request.args.get("category", "")
    material = request.args.get("material", "")
    style = request.args.get("style", "")
    silhouette = request.args.get("silhouette", "")
    construction = request.args.get("construction", "")
    decoration = request.args.get("decoration", "")
    looks, total = get_all_looks(designer or None, show or None, city or None,
                                  category or None, material or None, style or None,
                                  silhouette or None, construction or None, decoration or None,
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
                           selected_style=style,
                           selected_silhouette=silhouette,
                           selected_construction=construction,
                           selected_decoration=decoration)


@app.route("/studio")
def studio():
    return render_template("studio.html")


@app.route("/moodboard")
def moodboard():
    saved = session.get("moodboard", [])
    return render_template("moodboard.html", saved=saved)


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    designer = request.args.get("designer", "").strip().lower()
    show = request.args.get("show", "").strip().lower()
    city = request.args.get("city", "").strip()

    # CLIP поиск (если модель загружена при старте)
    if _clip_model is not None and _clip_embeddings is not None:
        try:
            import numpy as np
            text_feat = _clip_model.encode([query], convert_to_numpy=True)[0]
            text_feat = text_feat / (np.linalg.norm(text_feat) + 1e-9)
            scores = _clip_embeddings @ text_feat
            # Retrieve top 500 then apply filters
            top_idx = list(map(int, (-scores).argsort()[:500]))
            results = []
            for idx in top_idx:
                m = _clip_metadata[idx]
                if designer and designer not in m["designer"].lower():
                    continue
                if show and show not in m["show"].lower():
                    continue
                if city and get_city(m["designer"]) != city:
                    continue
                results.append({
                    "designer": m["designer"],
                    "show": m["show"],
                    "look_number": m["look_number"],
                    "image_url": m["image_url"],
                    "score": float(scores[idx]),
                    "mode": "clip",
                })
                if len(results) >= 96:
                    break
            return jsonify(results)
        except Exception as e:
            print(f"CLIP search error: {e}")

    # Фолбэк: цветовой + текстовый поиск
    return jsonify(_text_search(query, designer=designer, show=show, city=city))


def _text_search(query, designer="", show="", city=""):
    """Возвращает список dict (не Response)."""
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
                        "designer": row["designer"],
                        "show": row["show"],
                        "look_number": row["look_number"],
                        "image_url": row["image_url"],
                        "mode": "color",
                    })
                    break
        if results:
            return results[:96]

    # Поиск по дизайнеру/показу
    rows = apply_filters(load_csv(f"{DATA_DIR}/all_designers.csv"))
    results = [r for r in rows if q in r["designer"].lower() or q in r["show"].lower()]
    if results:
        return results[:96]

    # Случайная выборка как вдохновение
    if rows:
        sample = random.sample(rows, min(24, len(rows)))
        for r in sample:
            r["mode"] = "random"
        return sample

    return []


@app.route("/api/similar")
def api_similar():
    """Find visually similar looks using CLIP embeddings."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify([])
    if _clip_model is not None and _clip_embeddings is not None and _clip_metadata:
        try:
            import numpy as np
            # Find this look in metadata by image_url
            idx = next((i for i, m in enumerate(_clip_metadata) if m["image_url"] == url), None)
            if idx is not None:
                look_vec = _clip_embeddings[idx]
                scores = _clip_embeddings @ look_vec
                scores[idx] = -1  # exclude self
                top_idx = list(map(int, (-scores).argsort()[:96]))
                results = []
                for i in top_idx:
                    m = _clip_metadata[i]
                    results.append({
                        "designer": m["designer"], "show": m["show"],
                        "look_number": m["look_number"], "image_url": m["image_url"],
                        "score": float(scores[i]), "mode": "similar",
                    })
                return jsonify(results)
        except Exception as e:
            print(f"Similar search error: {e}")
    return jsonify([])


@app.route("/api/looks")
def api_looks():
    designer = request.args.get("designer", "")
    show = request.args.get("show", "")
    city = request.args.get("city", "")
    category = request.args.get("category", "")
    material = request.args.get("material", "")
    style = request.args.get("style", "")
    silhouette = request.args.get("silhouette", "")
    construction = request.args.get("construction", "")
    decoration = request.args.get("decoration", "")
    offset = int(request.args.get("offset", 0))
    looks, total = get_all_looks(designer or None, show or None, city or None,
                                  category or None, material or None, style or None,
                                  silhouette or None, construction or None, decoration or None,
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
