"""
taxonomy.py — закрытая таксономия «Тренд-копилки» для vision-пайплайна
=======================================================================
Источник: «Тренд-копилка для AI-анализа коллекций» (Тренд-копилка.docx).
Канонические значения — английские (совместимость с существующим датасетом
enriched_looks.csv и tool-use enum'ами); RU_* — русские названия из копилки
для UI и отчётов.

7 измерений + стили + цвета:
  CATEGORIES, MATERIALS, PATTERNS, SILHOUETTES, CONSTRUCTION, DECORATION,
  STYLES, COLORS

Правило: модель выбирает ТОЛЬКО из этих списков либо NOT_VISIBLE.
"""

NOT_VISIBLE = "not_visible"  # «не видно» — обязательная опция вместо угадывания

# ─── Категории предметов (не в docx — рабочий список проекта) ────────────────

CATEGORIES = [
    "Coat", "Jacket/Blazer", "Suit", "Dress", "Gown/Evening",
    "Jumpsuit/Romper", "Top/Blouse", "Shirt", "Knitwear/Cardigan",
    "Pants/Trousers", "Skirt", "Shorts", "Vest", "Cape/Poncho",
    "Swimwear", "Lingerie/Corset",
    "Bag", "Shoes/Boots", "Belt", "Hat", "Scarf", "Gloves",
    "Jewelry/Accessory", "Sunglasses", "Other",
]

RU_CATEGORIES = {
    "Coat": "Пальто", "Jacket/Blazer": "Жакет/блейзер", "Suit": "Костюм",
    "Dress": "Платье", "Gown/Evening": "Вечернее платье",
    "Jumpsuit/Romper": "Комбинезон", "Top/Blouse": "Топ/блуза",
    "Shirt": "Рубашка", "Knitwear/Cardigan": "Трикотаж/кардиган",
    "Pants/Trousers": "Брюки", "Skirt": "Юбка", "Shorts": "Шорты",
    "Vest": "Жилет", "Cape/Poncho": "Кейп/пончо", "Swimwear": "Купальник",
    "Lingerie/Corset": "Бельё/корсет", "Bag": "Сумка",
    "Shoes/Boots": "Обувь", "Belt": "Ремень", "Hat": "Головной убор",
    "Scarf": "Шарф/платок", "Gloves": "Перчатки",
    "Jewelry/Accessory": "Украшение/аксессуар", "Sunglasses": "Очки",
    "Other": "Другое",
}

# ─── Копилка материалов и фактур (docx, 27) ──────────────────────────────────

MATERIALS = [
    "Leather/Faux Leather", "Suede", "Denim", "Chunky Knit", "Fine Knit",
    "Ribbed Knit", "Suiting Fabric", "Satin", "Chiffon", "Organza",
    "Lace", "Mesh", "Velvet", "Tweed", "Bouclé", "Fur/Faux Fur",
    "Nylon", "Cotton", "Linen", "Textured Knit", "Sheer Fabric",
    "Metallic Fabric", "Technical Fabric", "Trench/Rain Fabric",
    "Soft Base Knit", "Artisanal Texture Fabric", "Crinkled Texture",
    "Other",
]

RU_MATERIALS = {
    "Leather/Faux Leather": "Кожа и экокожа", "Suede": "Замша",
    "Denim": "Деним", "Chunky Knit": "Плотный трикотаж",
    "Fine Knit": "Тонкий трикотаж", "Ribbed Knit": "Рубчик",
    "Suiting Fabric": "Костюмная ткань", "Satin": "Сатин",
    "Chiffon": "Шифон", "Organza": "Органза", "Lace": "Кружево",
    "Mesh": "Сетка", "Velvet": "Бархат", "Tweed": "Твид",
    "Bouclé": "Букле", "Fur/Faux Fur": "Мех и экомех", "Nylon": "Нейлон",
    "Cotton": "Хлопок", "Linen": "Лён", "Textured Knit": "Фактурная вязка",
    "Sheer Fabric": "Прозрачные материалы",
    "Metallic Fabric": "Металлизированные ткани",
    "Technical Fabric": "Технические ткани",
    "Trench/Rain Fabric": "Плащевые материалы",
    "Soft Base Knit": "Мягкий трикотаж для базы",
    "Artisanal Texture Fabric": "Ткани с ремесленным эффектом",
    "Crinkled Texture": "Жатая фактура", "Other": "Другое",
}

# ─── Принты (не в docx — рабочий список проекта) ─────────────────────────────

PATTERNS = [
    "Solid", "Stripes", "Checks/Plaid", "Floral", "Animal Print",
    "Abstract", "Geometric", "Polka Dots", "Paisley", "Camouflage",
    "Houndstooth", "Tie-dye", "Ombre", "Patchwork", "Logo/Monogram",
    "Embroidery Print", "Other",
]

RU_PATTERNS = {
    "Solid": "Однотонный", "Stripes": "Полоска", "Checks/Plaid": "Клетка",
    "Floral": "Цветочный", "Animal Print": "Анималистичный",
    "Abstract": "Абстрактный", "Geometric": "Геометрический",
    "Polka Dots": "Горох", "Paisley": "Пейсли", "Camouflage": "Камуфляж",
    "Houndstooth": "Гусиная лапка", "Tie-dye": "Тай-дай", "Ombre": "Омбре",
    "Patchwork": "Пэчворк", "Logo/Monogram": "Лого/монограмма",
    "Embroidery Print": "Вышивка-принт", "Other": "Другое",
}

# ─── Копилка типов силуэта (docx, 24) ────────────────────────────────────────

SILHOUETTES = [
    "Straight", "Fitted/Waisted", "Semi-Fitted", "Relaxed", "Oversized",
    "Elongated", "Cropped", "A-line", "X-Silhouette", "Trapeze",
    "Cocoon", "Column", "Hourglass", "Volume Top + Slim Bottom",
    "Slim Top + Volume Bottom", "Shoulder Emphasis", "Waist Emphasis",
    "Hip Emphasis", "Low Rise", "High Rise", "Wide Leg/Flare",
    "Slim Leg", "Layered Silhouette", "Athletic Relaxed",
]

RU_SILHOUETTES = {
    "Straight": "Прямой", "Fitted/Waisted": "Приталенный",
    "Semi-Fitted": "Полуприлегающий", "Relaxed": "Свободный",
    "Oversized": "Оверсайз", "Elongated": "Вытянутый",
    "Cropped": "Укороченный", "A-line": "А-силуэт",
    "X-Silhouette": "Х-силуэт", "Trapeze": "Трапеция", "Cocoon": "Кокон",
    "Column": "Колонна", "Hourglass": "Песочные часы",
    "Volume Top + Slim Bottom": "Объёмный верх + узкий низ",
    "Slim Top + Volume Bottom": "Узкий верх + объёмный низ",
    "Shoulder Emphasis": "Акцент на плечи",
    "Waist Emphasis": "Акцент на талии", "Hip Emphasis": "Акцент на бёдра",
    "Low Rise": "Заниженная посадка", "High Rise": "Высокая посадка",
    "Wide Leg/Flare": "Широкий низ", "Slim Leg": "Узкий низ",
    "Layered Silhouette": "Многослойный силуэт",
    "Athletic Relaxed": "Спортивный расслабленный",
}

# ─── Копилка элементов кроя и конструкции (docx, 33) ─────────────────────────

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

RU_CONSTRUCTION = {
    "Darts": "Вытачки", "Princess Seams": "Рельефы", "Draping": "Драпировки",
    "Asymmetry": "Асимметрия", "Wrap Closure": "Запах", "Peplum": "Баска",
    "Pleats": "Складки/плиссировка", "Tucks": "Защипы",
    "Drawstrings": "Кулиски", "Gathers": "Сборки", "Flounces": "Воланы",
    "Puff Sleeves": "Рукава-фонарики (буфы)",
    "Extended Cuffs": "Удлинённые манжеты",
    "Wide Shoulders": "Широкие плечи", "Dropped Shoulder": "Спущенное плечо",
    "Stand Collar": "Воротник-стойка", "High Neck": "Высокий ворот",
    "Polo Collar": "Воротник поло", "Shirt Collar": "Отложной воротник",
    "Halter": "Халтер", "Off-Shoulder": "Открытые плечи",
    "Boat Neck": "Вырез лодочка", "Square Neckline": "Квадратный вырез",
    "V-Neck": "V-вырез", "Cutout Neckline": "Фигурные вырезы",
    "Slits": "Разрезы", "Patch Pockets": "Накладные карманы",
    "Cargo Pockets": "Карманы карго", "Waist Seam": "Отрезная талия",
    "Layered Details": "Многослойные детали",
    "Convertible Elements": "Трансформируемые элементы",
    "Statement Closure": "Акцентная застёжка",
    "Structural Zipper": "Молния как конструкция",
}

# ─── Копилка отделки и декоративных приёмов (docx, 25) ───────────────────────

DECORATION = [
    "Lace Trim", "Ruffles", "Frills", "Fringe", "Embroidery", "Appliqué",
    "Contrast Stitching", "Piping", "Bows", "Ties", "Lacing",
    "Decorative Zippers", "Metal Hardware", "Grommets",
    "Statement Buttons", "Sequins", "Rhinestones", "Perforation",
    "Textured Inserts", "Sheer Inserts", "Side Stripes", "Sport Stripes",
    "Logos", "Monograms", "Decorative Pockets",
]

RU_DECORATION = {
    "Lace Trim": "Кружево", "Ruffles": "Оборки", "Frills": "Рюши",
    "Fringe": "Бахрома", "Embroidery": "Вышивка", "Appliqué": "Аппликации",
    "Contrast Stitching": "Контрастная строчка", "Piping": "Канты",
    "Bows": "Банты", "Ties": "Завязки", "Lacing": "Шнуровка",
    "Decorative Zippers": "Молнии", "Metal Hardware": "Металлическая фурнитура",
    "Grommets": "Люверсы", "Statement Buttons": "Декоративные пуговицы",
    "Sequins": "Пайетки", "Rhinestones": "Стразы",
    "Perforation": "Перфорация", "Textured Inserts": "Фактурные вставки",
    "Sheer Inserts": "Прозрачные вставки", "Side Stripes": "Лампасы",
    "Sport Stripes": "Спортивные полосы", "Logos": "Логотипы",
    "Monograms": "Монограммы", "Decorative Pockets": "Декоративные карманы",
}

# ─── Копилка стилистик (docx, 34 + 3 расширения из инструкции §2.2) ──────────
# Docx: «копилка не закрытый список». Расширения: Coquette, Mob Wife,
# Sport Chic — названы в TREND_PLATFORM_INSTRUCTION.md §2.2.

STYLES = [
    "Minimalism", "Quiet Luxury", "New Classic", "Ladylike", "New Femininity",
    "Power Dressing", "Office Aesthetic", "Soft Tailoring", "Preppy",
    "Collegiate/Schoolgirl", "Old Money", "Country Aesthetic", "Country Club",
    "Boho", "Romantic", "Boudoir", "Grunge", "Streetwear", "Sport as Status",
    "Wellness", "Utilitarian", "Outdoor", "Moto", "70s Retro", "90s Retro",
    "Y2K", "2010s Nostalgia", "Eclectic", "Loud Luxury", "Quiet Status",
    "Body-conscious Basics", "Intellectual Fashion", "Artisanal/Craft",
    "Resort",
    # расширения из инструкции:
    "Coquette", "Mob Wife", "Sport Chic",
]

RU_STYLES = {
    "Minimalism": "Минимализм", "Quiet Luxury": "Дорогая простота",
    "New Classic": "Новая классика", "Ladylike": "Ladylike",
    "New Femininity": "Новая женственность",
    "Power Dressing": "Power dressing",
    "Office Aesthetic": "Офисная эстетика",
    "Soft Tailoring": "Мягкий костюмный стиль", "Preppy": "Преппи",
    "Collegiate/Schoolgirl": "Школьные и университетские коды",
    "Old Money": "Old money", "Country Aesthetic": "Загородная эстетика",
    "Country Club": "Эстетика закрытых клубов", "Boho": "Boho",
    "Romantic": "Романтический стиль", "Boudoir": "Будуарные элементы",
    "Grunge": "Гранж", "Streetwear": "Уличная эстетика",
    "Sport as Status": "Спорт как статус", "Wellness": "Wellness-эстетика",
    "Utilitarian": "Утилитарность", "Outdoor": "Outdoor-коды",
    "Moto": "Мото-эстетика", "70s Retro": "Ретро 70-х",
    "90s Retro": "Ретро 90-х", "Y2K": "2000-е (Y2K)",
    "2010s Nostalgia": "Ностальгия по 2010-м", "Eclectic": "Эклектика",
    "Loud Luxury": "Заметный статус", "Quiet Status": "Сдержанный статус",
    "Body-conscious Basics": "Телесная база",
    "Intellectual Fashion": "Интеллектуальная мода",
    "Artisanal/Craft": "Ремесленная эстетика", "Resort": "Курортная эстетика",
    "Coquette": "Coquette", "Mob Wife": "Mob wife", "Sport Chic": "Спортшик",
}

# ─── Цвета (Pantone TCX из color_analysis.py, дедуплицированные) ─────────────

COLORS = [
    "Bright White", "Pearled Ivory", "Butter Cream", "Pastel Yellow",
    "Wax Yellow", "Warm Sand", "Tan Melange", "Warm Taupe", "Mushroom",
    "Doeskin", "Toasted Coconut", "Caramel", "Adobe", "Sandstorm",
    "Rosewood", "Powder Pink", "Rose Quartz", "Flamingo Pink", "Coral",
    "Fiesta", "True Red", "Raspberry Sorbet", "Hot Coral", "Fuchsia Rose",
    "Pink Lemonade",
    "Baby Blue", "Placid Blue", "Cerulean", "Classic Blue", "Navy Peony",
    "Midnight Blue", "Aegean", "Dusk Blue",
    "Sage Mist", "Quiet Green", "Artichoke Green", "Greenery",
    "Forest Green", "Olive Branch",
    "Violet Tulip", "Pastel Lilac", "Amethyst Orchid", "Ultra Violet",
    "Silver Gray", "Monument", "Pewter", "Charcoal Gray", "Black",
    "Chocolate Brown", "Coffee Bean", "Cognac",
    "Gold Fusion", "Silver",
]

# ─── Служебное ────────────────────────────────────────────────────────────────

DIMENSIONS = {
    "category": CATEGORIES,
    "materials": MATERIALS,
    "pattern": PATTERNS,
    "silhouette": SILHOUETTES,
    "construction": CONSTRUCTION,
    "decoration": DECORATION,
    "styles": STYLES,
    "colors": COLORS,
}

RU = {
    "category": RU_CATEGORIES,
    "materials": RU_MATERIALS,
    "pattern": RU_PATTERNS,
    "silhouette": RU_SILHOUETTES,
    "construction": RU_CONSTRUCTION,
    "decoration": RU_DECORATION,
    "styles": RU_STYLES,
}


def ru(dimension: str, value: str) -> str:
    """Русское название значения (для UI/отчётов)."""
    if value == NOT_VISIBLE:
        return "не видно"
    return RU.get(dimension, {}).get(value, value)


# ─── Tool-use схемы (строгие enum) ────────────────────────────────────────────

def _enum(values, with_not_visible=False):
    vals = list(values) + ([NOT_VISIBLE] if with_not_visible else [])
    return {"type": "string", "enum": vals}


def _enum_array(values, max_items, with_not_visible=False):
    return {
        "type": "array",
        "items": _enum(values, with_not_visible),
        "maxItems": max_items,
    }


def tool_schema_full() -> dict:
    """Проход A (полное фото): категории, силуэт, принт, цвета, стили."""
    return {
        "name": "tag_look",
        "description": (
            "Record structured tags for a runway look. Use ONLY the enum "
            "values provided. If an attribute cannot be determined from the "
            f"photo, use \"{NOT_VISIBLE}\" or an empty array — never guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "styles": _enum_array(STYLES, 3),
                "items": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": _enum(CATEGORIES),
                            "pattern": _enum(PATTERNS, with_not_visible=True),
                            "silhouette": _enum_array(SILHOUETTES, 2),
                            "colors": _enum_array(COLORS, 3),
                            "confidence": {
                                "type": "number",
                                "minimum": 0, "maximum": 1,
                                "description": "Confidence in this item's tags",
                            },
                        },
                        "required": ["category", "pattern", "confidence"],
                    },
                },
            },
            "required": ["styles", "items"],
        },
    }


def tool_schema_details() -> dict:
    """Проход B (кропы): material / construction / decoration по НОМЕРУ
    предмета из списка прохода A (item_index, 1-based)."""
    return {
        "name": "tag_details",
        "description": (
            "Record construction and finishing details for the NUMBERED "
            "garment list given in the prompt. Reference items strictly by "
            "item_index. Use ONLY the enum values provided; use "
            f"\"{NOT_VISIBLE}\" for material you truly cannot judge."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_index": {
                                "type": "integer", "minimum": 1,
                                "description": "Number from the item list",
                            },
                            "materials": _enum_array(
                                MATERIALS, 2, with_not_visible=True),
                            "construction": _enum_array(CONSTRUCTION, 4),
                            "decoration": _enum_array(DECORATION, 4),
                            "confidence": {
                                "type": "number",
                                "minimum": 0, "maximum": 1,
                            },
                        },
                        "required": ["item_index", "confidence"],
                    },
                },
            },
            "required": ["items"],
        },
    }
