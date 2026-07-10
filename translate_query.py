"""
RU→EN перевод поисковых запросов для CLIP.
============================================
CLIP/Fashion-CLIP обучены на английских подписях — кириллический запрос
даёт шумовую выдачу (проверено: score падает до уровня случайных луков).

Стратегия:
1. Нет кириллицы → запрос возвращается как есть.
2. Есть кириллица → словарный перевод fashion-лексики (фразы, затем слова).
3. Остались непереведённые кириллические слова и есть ANTHROPIC_API_KEY →
   один вызов Haiku на весь запрос (результат кэшируется в памяти).
4. Ключа нет → непереведённые слова отбрасываются (лучше частичный
   EN-запрос, чем кириллический шум).
"""

import os
import re

_CYR = re.compile("[а-яё]", re.IGNORECASE)

# Фразы (проверяются первыми, до пословного перевода)
RU_PHRASES = {
    "вечернее платье": "evening gown",
    "маленькое черное платье": "little black dress",
    "маленькое чёрное платье": "little black dress",
    "платье комбинация": "slip dress",
    "платье-комбинация": "slip dress",
    "тренч кот": "trench coat",
    "косуха": "biker leather jacket",
    "анималистичный принт": "animal print",
    "леопардовый принт": "leopard print",
    "гусиная лапка": "houndstooth",
    "широкие брюки": "wide leg trousers",
    "брюки палаццо": "palazzo trousers",
    "юбка карандаш": "pencil skirt",
    "юбка-карандаш": "pencil skirt",
    "юбка миди": "midi skirt",
    "юбка макси": "maxi skirt",
    "высокая посадка": "high waisted",
    "объемные плечи": "strong shoulders",
    "объёмные плечи": "strong shoulders",
    "открытая спина": "open back",
    "запах": "wrap",
}

# Слова
RU_WORDS = {
    # Одежда
    "платье": "dress", "платья": "dresses", "жакет": "jacket",
    "пиджак": "blazer", "блейзер": "blazer", "пальто": "coat",
    "куртка": "jacket", "плащ": "trench coat", "тренч": "trench coat",
    "юбка": "skirt", "брюки": "trousers", "штаны": "pants",
    "джинсы": "jeans", "шорты": "shorts", "рубашка": "shirt",
    "блуза": "blouse", "блузка": "blouse", "топ": "top",
    "футболка": "t-shirt", "свитер": "sweater", "джемпер": "jumper",
    "кардиган": "cardigan", "водолазка": "turtleneck",
    "жилет": "vest", "костюм": "suit", "комбинезон": "jumpsuit",
    "накидка": "cape", "пончо": "poncho", "корсет": "corset",
    "белье": "lingerie", "бельё": "lingerie", "купальник": "swimsuit",
    "сумка": "bag", "обувь": "shoes", "туфли": "shoes",
    "сапоги": "boots", "ботинки": "boots", "ремень": "belt",
    "шарф": "scarf", "шляпа": "hat", "очки": "sunglasses",
    "украшения": "jewelry", "перчатки": "gloves",
    # Материалы
    "кожа": "leather", "кожаный": "leather", "кожаная": "leather",
    "кожаное": "leather", "замша": "suede", "замшевый": "suede",
    "деним": "denim", "джинсовый": "denim", "твид": "tweed",
    "твидовый": "tweed", "твидовая": "tweed", "букле": "boucle",
    "трикотаж": "knitwear", "трикотажный": "knit", "вязаный": "knitted",
    "вязаная": "knitted", "шелк": "silk", "шёлк": "silk",
    "шелковый": "silk", "шёлковый": "silk", "сатин": "satin",
    "атлас": "satin", "атласное": "satin", "бархат": "velvet",
    "бархатный": "velvet", "шифон": "chiffon", "органза": "organza",
    "кружево": "lace", "кружевной": "lace", "кружевное": "lace",
    "сетка": "mesh", "мех": "fur", "меховой": "fur", "меховая": "fur",
    "хлопок": "cotton", "лен": "linen", "лён": "linen",
    "шерсть": "wool", "шерстяной": "wool", "кашемир": "cashmere",
    "вязка": "knit", "крупный": "chunky", "крупной": "chunky",
    "рубчик": "ribbed knit", "стежка": "quilted", "стёжка": "quilted",
    "пайетки": "sequins", "стразы": "rhinestones",
    "прозрачный": "sheer", "прозрачное": "sheer", "прозрачная": "sheer",
    "металлик": "metallic", "металлизированный": "metallic",
    # Цвета
    "черный": "black", "чёрный": "black", "черное": "black",
    "чёрное": "black", "черная": "black", "чёрная": "black",
    "белый": "white", "белое": "white", "белая": "white",
    "красный": "red", "красное": "red", "красная": "red",
    "розовый": "pink", "розовое": "pink", "розовая": "pink",
    "бежевый": "beige", "бежевое": "beige", "бежевая": "beige",
    "коричневый": "brown", "коричневое": "brown", "коричневая": "brown",
    "серый": "grey", "серое": "grey", "серая": "grey",
    "синий": "blue", "синее": "blue", "синяя": "blue",
    "голубой": "light blue", "голубое": "light blue",
    "зеленый": "green", "зелёный": "green", "зеленое": "green",
    "зелёное": "green", "оливковый": "olive", "хаки": "khaki",
    "желтый": "yellow", "жёлтый": "yellow", "золотой": "gold",
    "золотое": "gold", "серебряный": "silver", "серебристый": "silver",
    "фиолетовый": "purple", "сиреневый": "lilac", "лиловый": "lilac",
    "лавандовый": "lavender", "бордовый": "burgundy", "винный": "wine",
    "кремовый": "cream", "кремовое": "cream", "молочный": "ivory",
    "пудровый": "powder pink", "коралловый": "coral",
    "бирюзовый": "turquoise", "оранжевый": "orange",
    # Принты и детали
    "полоска": "stripes", "полосатый": "striped", "клетка": "plaid",
    "клетчатый": "checked", "цветочный": "floral", "цветочек": "floral",
    "горох": "polka dots", "леопард": "leopard", "леопардовый": "leopard",
    "леопардовое": "leopard", "зебра": "zebra print", "змеиный": "snake print",
    "камуфляж": "camouflage", "принт": "print", "вышивка": "embroidery",
    "бахрома": "fringe", "оборки": "ruffles", "рюши": "frills",
    "банты": "bows", "бант": "bow", "драпировка": "draping",
    "складки": "pleats", "плиссе": "pleated", "асимметрия": "asymmetric",
    "асимметричный": "asymmetric", "асимметричное": "asymmetric",
    # Силуэты / стиль
    "оверсайз": "oversized", "приталенный": "fitted",
    "приталенное": "fitted", "свободный": "relaxed",
    "свободное": "relaxed", "укороченный": "cropped",
    "укороченная": "cropped", "длинный": "long", "длинное": "long",
    "короткий": "short", "короткое": "short", "мини": "mini",
    "миди": "midi", "макси": "maxi", "вечерний": "evening",
    "вечернее": "evening", "коктейльное": "cocktail",
    "классический": "classic", "классическое": "classic",
    "элегантный": "elegant", "элегантное": "elegant",
    "минимализм": "minimalist", "минималистичный": "minimalist",
    "романтичный": "romantic", "романтичное": "romantic",
    "спортивный": "sporty", "уличный": "streetwear",
    "деловой": "office", "офисный": "office",
    "гранж": "grunge", "бохо": "boho", "ретро": "retro",
    "винтаж": "vintage", "винтажный": "vintage",
    # Служебные
    "открытый": "open", "открытая": "open", "открытой": "open",
    "спина": "back", "спиной": "back", "вырез": "neckline",
    "рукав": "sleeve", "рукава": "sleeves", "воротник": "collar",
    "карманы": "pockets", "пуговицы": "buttons", "молния": "zipper",
    "с": "with", "и": "and", "в": "in", "на": "on", "без": "without",
    "стиль": "style", "стиле": "style", "образ": "look", "лук": "look",
}

_haiku_cache = {}

# Лёгкий стемминг: русские падежные/родовые окончания (длинные — первыми)
_RU_SUFFIXES = (
    "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими",
    "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ой", "ей",
    "ом", "ем", "ам", "ям", "ах", "ях", "ов", "ев",
    "у", "ю", "е", "и", "ы", "а", "я", "ь",
)


def _stem(word):
    for suf in _RU_SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


# Карта стемов словаря: "юбка"→"юбк" позволяет находить "юбкой", "юбку" и т.д.
_STEM_MAP = {}
for _k, _v in RU_WORDS.items():
    _STEM_MAP.setdefault(_stem(_k), _v)


def _dedupe(words):
    """Убирает повторы слов, сохраняя порядок (leather leather → leather)."""
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _dict_translate(query):
    """Словарный перевод. Возвращает (переведённый_запрос, остались_ли_кириллические_слова)."""
    q = query.lower()
    for ru, en in RU_PHRASES.items():
        q = q.replace(ru, en)
    tokens = re.findall(r"[a-zа-яё0-9\-]+", q, re.IGNORECASE)
    out, leftover = [], False
    for t in tokens:
        if not _CYR.search(t):
            out.append(t)
        elif t in RU_WORDS:
            out.extend(RU_WORDS[t].split())
        elif _stem(t) in _STEM_MAP:
            out.extend(_STEM_MAP[_stem(t)].split())
        else:
            leftover = True  # неизвестное кириллическое слово
    return " ".join(_dedupe(out)), leftover


def _haiku_translate(query):
    """Полный перевод запроса через Haiku (кэшируется)."""
    if query in _haiku_cache:
        return _haiku_cache[query]
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            system=("Translate the fashion search query to English for a CLIP "
                    "image-retrieval system. Reply with ONLY the translated "
                    "query, no quotes, no explanations."),
            messages=[{"role": "user", "content": query}],
        )
        en = resp.content[0].text.strip().strip('"')
        if en and not _CYR.search(en):
            _haiku_cache[query] = en
            return en
    except Exception as e:
        print(f"translate_query: Haiku failed: {e}")
    return None


def translate_query(query):
    """Главная точка входа: RU-запрос → EN-запрос для CLIP."""
    if not query or not _CYR.search(query):
        return query
    translated, leftover = _dict_translate(query)
    if leftover:
        full = _haiku_translate(query)
        if full:
            return full
    # Словарный результат (возможно частичный) — лучше, чем кириллица
    return translated if translated.strip() else query
