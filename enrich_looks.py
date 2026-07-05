"""
Fashion AI — обогащение датасета через Claude Vision (v3: structured output)
=============================================================================
Изменения v3 (TREND_PLATFORM_INSTRUCTION.md, раздел 2):
  - закрытая таксономия из taxonomy.py (Тренд-копилка), tool use со строгими
    enum — никакого свободного текста и regex-парсинга
  - двухпроходный анализ: проход A (полное фото: категории, силуэт, принт,
    цвета, стили) + проход B (2 кропа: верх/низ — крой, отделка, материал)
  - обязательное значение "not_visible" вместо угадывания
  - confidence на каждый предмет; < 0.6 → очередь на пересмотр Sonnet 5
  - модель claude-haiku-4-5, Batch API (−50%), prompt caching таксономии
  - MOCK=1 — работа без API на фикстурах

Запуск:
    python3 enrich_looks.py --sample 20                # синхронно, 20 луков
    python3 enrich_looks.py --full --confirm-full      # Batch API, все луки
    python3 enrich_looks.py --collect                  # забрать результаты батча
    python3 enrich_looks.py --review                   # пересмотр low-conf Sonnet 5
    MOCK=1 python3 enrich_looks.py --sample 5          # без API (фикстуры)

Результат: output/enriched_looks_v3.csv
Формат: designer, show, look_number, image_url, style_tags, items_json, confidence
"""

import argparse
import base64
import csv
import io
import json
import os
import re
import sys
import time

from taxonomy import (
    CATEGORIES, MATERIALS, PATTERNS, SILHOUETTES, CONSTRUCTION, DECORATION,
    STYLES, COLORS, NOT_VISIBLE,
    tool_schema_full, tool_schema_details,
)

# ─── Константы ────────────────────────────────────────────────────────────────

MODEL_BULK = "claude-haiku-4-5"      # массовое тегирование
MODEL_REVIEW = "claude-sonnet-5"     # контроль качества / low-confidence
CONFIDENCE_THRESHOLD = 0.6

FULL_MAX_SIDE = 1200                 # px, полное фото
CROP_MAX_SIDE = 800                  # px, кропы
JPEG_QUALITY = 85

MAX_TOKENS_A = 1500
MAX_TOKENS_B = 1200

MOCK = os.environ.get("MOCK", "") == "1"
FIXTURES_PATH = "tests/fixtures/vision_fixtures.json"

# ─── Промпты ──────────────────────────────────────────────────────────────────
# Таксономия в системном промпте кэшируется (prompt caching): при массовом
# прогоне чтение кэша стоит 10% от обычной цены input-токенов.


def _fmt(name, values):
    return f"{name}: {', '.join(values)}"


SYSTEM_TAXONOMY = f"""You are an expert fashion trend analyst. You tag runway \
photos using a CLOSED controlled vocabulary ("Тренд-копилка" taxonomy). \
Strict rules:
1. Use ONLY values from the enums of the tool you are given. Never invent, \
translate or paraphrase labels.
2. If an attribute is not clearly visible in the photo, answer "{NOT_VISIBLE}" \
(where allowed) or leave the array empty. NEVER guess small details you \
cannot actually see.
3. Report every distinct garment and accessory as a separate item.
4. confidence is your honest estimate (0-1) that the tags for that item are \
correct; low confidence is acceptable and expected for ambiguous photos.

Reference taxonomy:
{_fmt("STYLES", STYLES)}
{_fmt("CATEGORIES", CATEGORIES)}
{_fmt("MATERIALS", MATERIALS)}
{_fmt("PATTERNS", PATTERNS)}
{_fmt("SILHOUETTES", SILHOUETTES)}
{_fmt("CONSTRUCTION", CONSTRUCTION)}
{_fmt("DECORATION", DECORATION)}
{_fmt("COLORS", COLORS)}"""

PROMPT_A = """Full-body runway photo. Pass A — overall reading.
Identify EVERY distinct visible garment and accessory (typically 3-6 items: \
main top/dress, bottom, outerwear, shoes, bag, notable accessories). Report \
every visible LAYER as a separate item (a coat worn over a dress = 2 items).

Category disambiguation rules (follow strictly):
- Coat = outerwear at mid-thigh length or longer (incl. trench, puffer). \
Jacket/Blazer = outerwear/tailoring ending at hip or above.
- Gown/Evening = floor-length or clearly formal evening dress. \
Dress = any other dress.
- Shirt = woven button-up with shirt collar. Top/Blouse = other woven tops. \
Knitwear/Cardigan = visibly knitted sweaters, cardigans, knit tops.
- Suit = matching jacket + trousers/skirt presented as one set; otherwise \
tag the pieces separately.
- Lingerie/Corset = corsets, bras, slip-like underwear worn as clothing.

For each item: category, pattern, silhouette (garments only, [] for \
accessories), dominant colors. Plus 0-3 look-level styles.
Call the tag_look tool."""


def build_prompt_b(a_items: list) -> str:
    listing = "\n".join(
        f"{i + 1}. {it['category']}" for i, it in enumerate(a_items))
    return f"""Two close-up crops of the SAME runway look.
Image 1 = upper half (collars, necklines, shoulders, sleeves, cuffs, \
closures). Image 2 = lower half (waist, rise, pockets, hem, slits).

The look contains these items (from the full-photo pass):
{listing}

Pass B — for EACH numbered item report material, construction, decoration \
(reference by item_index). Work through this checklist per garment:
- neckline/collar: Stand Collar? Shirt Collar? Polo Collar? High Neck? \
V-Neck? Boat Neck? Square Neckline? Halter? Off-Shoulder? Cutout Neckline?
- shoulders/sleeves: Wide Shoulders? Dropped Shoulder? Puff Sleeves? \
Extended Cuffs?
- body: Draping? Asymmetry? Wrap Closure? Peplum? Pleats? Tucks? Gathers? \
Drawstrings? Waist Seam? Layered Details? Slits? Darts? Princess Seams?
- pockets/closures: Patch Pockets? Cargo Pockets? Statement Closure? \
Structural Zipper?
- decoration: Ruffles? Frills? Lace Trim? Fringe? Piping? Contrast \
Stitching? Bows? Ties? Statement Buttons? Metal Hardware? Sequins? \
Embroidery? Sheer Inserts?

Material: commit to the closest enum by visible texture. Typical mappings: \
tailored blazer/trousers/pencil skirt → Suiting Fabric; jeans → Denim; \
shiny fluid drape → Satin; sheer floaty → Chiffon or Sheer Fabric; ribbed \
knit → Ribbed Knit; chunky sweater → Chunky Knit; fine sweater → Fine Knit; \
leather shoes/bags/jackets → Leather/Faux Leather; fuzzy pile → Fur/Faux \
Fur. Use "not_visible" ONLY when texture is truly impossible to judge.

Empty arrays only when NO construction/decoration detail is visible for \
that item. Do NOT report silhouettes or styles. Call the tag_details tool."""


# ─── Изображения ──────────────────────────────────────────────────────────────

def upgrade_url(url: str) -> str:
    """Vogue отдаёт большие размеры — поднимаем w_1024 до w_1920."""
    return re.sub(r"/w_\d+,", "/w_1920,", url)


def fetch_image(url: str, timeout: int = 20) -> bytes:
    import urllib.request
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; FashionAI/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _resize_jpeg(img, max_side: int) -> bytes:
    from PIL import Image
    if max(img.size) > max_side:
        ratio = max_side / max(img.size)
        img = img.resize(
            (round(img.width * ratio), round(img.height * ratio)),
            Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def prepare_images(url: str) -> dict:
    """→ {'full': b64, 'top': b64, 'bottom': b64} (JPEG)."""
    from PIL import Image
    try:
        raw = fetch_image(upgrade_url(url))
    except Exception:
        raw = fetch_image(url)  # fallback на исходный размер
    img = Image.open(io.BytesIO(raw))
    w, h = img.size
    # кропы с перекрытием 10% — линия талии попадает в оба
    top = img.crop((0, 0, w, int(h * 0.55)))
    bottom = img.crop((0, int(h * 0.45), w, h))
    return {
        "full": base64.standard_b64encode(
            _resize_jpeg(img, FULL_MAX_SIDE)).decode(),
        "top": base64.standard_b64encode(
            _resize_jpeg(top, CROP_MAX_SIDE)).decode(),
        "bottom": base64.standard_b64encode(
            _resize_jpeg(bottom, CROP_MAX_SIDE)).decode(),
    }


def _img_block(b64: str) -> dict:
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": b64}}


# ─── Параметры запросов (общие для sync и batch) ─────────────────────────────

def _system_blocks():
    return [{"type": "text", "text": SYSTEM_TAXONOMY,
             "cache_control": {"type": "ephemeral"}}]


def request_params_a(images: dict, model: str) -> dict:
    return {
        "model": model,
        "max_tokens": MAX_TOKENS_A,
        "system": _system_blocks(),
        "tools": [tool_schema_full()],
        "tool_choice": {"type": "tool", "name": "tag_look"},
        "messages": [{"role": "user", "content": [
            _img_block(images["full"]),
            {"type": "text", "text": PROMPT_A},
        ]}],
    }


def request_params_b(images: dict, model: str, a_items: list) -> dict:
    return {
        "model": model,
        "max_tokens": MAX_TOKENS_B,
        "system": _system_blocks(),
        "tools": [tool_schema_details()],
        "tool_choice": {"type": "tool", "name": "tag_details"},
        "messages": [{"role": "user", "content": [
            _img_block(images["top"]),
            _img_block(images["bottom"]),
            {"type": "text", "text": build_prompt_b(a_items)},
        ]}],
    }


def extract_tool_input(message) -> dict:
    """Достать input tool_use блока из ответа (объект SDK или dict батча)."""
    content = message.content if hasattr(message, "content") else message["content"]
    for block in content:
        btype = block.type if hasattr(block, "type") else block.get("type")
        if btype == "tool_use":
            return block.input if hasattr(block, "input") else block["input"]
    raise ValueError("No tool_use block in response")


# ─── Валидация против таксономии (защита в глубину) ──────────────────────────

def _keep(values, allowed, max_n):
    allowed_set = set(allowed) | {NOT_VISIBLE}
    out = []
    for v in values or []:
        if isinstance(v, str) and v in allowed_set and v not in out:
            out.append(v)
        if len(out) >= max_n:
            break
    return out


def _one(value, allowed, default):
    if isinstance(value, str) and value in set(allowed) | {NOT_VISIBLE}:
        return value
    return default


def _conf(value):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def validate_a(raw: dict) -> dict:
    items = []
    for it in (raw.get("items") or [])[:8]:
        if not isinstance(it, dict):
            continue
        items.append({
            "category": _one(it.get("category"), CATEGORIES, "Other"),
            "pattern": _one(it.get("pattern"), PATTERNS, NOT_VISIBLE),
            "silhouette": _keep(it.get("silhouette"), SILHOUETTES, 2),
            "colors": _keep(it.get("colors"), COLORS, 3),
            "confidence": _conf(it.get("confidence")),
        })
    return {"styles": _keep(raw.get("styles"), STYLES, 3), "items": items}


def validate_b(raw: dict) -> dict:
    items = []
    for it in (raw.get("items") or [])[:8]:
        if not isinstance(it, dict):
            continue
        try:
            idx = int(it.get("item_index"))
        except (TypeError, ValueError):
            continue
        items.append({
            "item_index": idx,
            "materials": _keep(it.get("materials"), MATERIALS, 2),
            "construction": _keep(it.get("construction"), CONSTRUCTION, 4),
            "decoration": _keep(it.get("decoration"), DECORATION, 4),
            "confidence": _conf(it.get("confidence")),
        })
    return {"items": items}


# ─── Merge проходов A и B ─────────────────────────────────────────────────────

def merge_passes(a: dict, b: dict) -> dict:
    """A — база (категории/силуэт/принт/цвета/стили), B добавляет
    material/construction/decoration по item_index (1-based, порядок A).
    Дубликат индекса от двух кропов → объединение, материал от более
    уверенного ответа."""
    items = []
    for it in a["items"]:
        items.append({
            "category": it["category"],
            "materials": [NOT_VISIBLE],
            "pattern": it["pattern"],
            "silhouette": it["silhouette"],
            "construction": [],
            "decoration": [],
            "colors": it["colors"],
            "confidence": it["confidence"],
        })

    for det in b["items"]:
        i = det["item_index"] - 1
        if not 0 <= i < len(items):
            continue
        it = items[i]
        it["construction"] = list(dict.fromkeys(
            it["construction"] + det["construction"]))[:4]
        it["decoration"] = list(dict.fromkeys(
            it["decoration"] + det["decoration"]))[:4]
        if det["materials"] and (it["materials"] == [NOT_VISIBLE]
                                 or det["confidence"] > it["confidence"]):
            it["materials"] = det["materials"]
        if det["confidence"]:
            it["confidence"] = min(it["confidence"], det["confidence"])

    styles = a["styles"]
    confs = [it["confidence"] for it in items] or [0.0]
    return {"styles": styles, "items": items, "confidence": min(confs)}


# ─── Клиент (реальный / mock) ────────────────────────────────────────────────

class MockClient:
    """MOCK=1: переигрывает записанные фикстуры, API не тратится."""

    def __init__(self, path=FIXTURES_PATH):
        self.fixtures = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.fixtures = json.load(f)

    def call(self, params: dict, key: str) -> dict:
        if key in self.fixtures:
            return self.fixtures[key]
        tool = params["tools"][0]["name"]
        if tool == "tag_look":  # детерминированная заглушка
            return {"styles": ["Minimalism"], "items": [{
                "category": "Dress", "pattern": "Solid",
                "silhouette": ["Straight"], "colors": ["Black"],
                "confidence": 0.9}]}
        return {"items": [{
            "item_index": 1, "materials": ["Satin"],
            "construction": ["Stand Collar"], "decoration": [],
            "confidence": 0.9}]}


class LiveClient:
    def __init__(self):
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            sys.exit("❌ Set ANTHROPIC_API_KEY (или MOCK=1 для работы без API)")
        self.client = anthropic.Anthropic(api_key=api_key)
        self._fixtures = {}
        if os.path.exists(FIXTURES_PATH):
            with open(FIXTURES_PATH, encoding="utf-8") as f:
                self._fixtures = json.load(f)

    def call(self, params: dict, key: str, retries: int = 3) -> dict:
        for attempt in range(retries):
            try:
                msg = self.client.messages.create(**params)
                result = extract_tool_input(msg)
                self._record(key, result)
                return result
            except Exception as e:
                print(f"    API error: {e} (attempt {attempt + 1})")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"API failed after {retries} retries: {key}")

    def _record(self, key: str, result: dict):
        """Пишем фикстуру один раз — потом тесты гоняются бесплатно (MOCK=1)."""
        self._fixtures[key] = result
        os.makedirs(os.path.dirname(FIXTURES_PATH), exist_ok=True)
        with open(FIXTURES_PATH, "w", encoding="utf-8") as f:
            json.dump(self._fixtures, f, ensure_ascii=False, indent=1)


# ─── Обработка одного лука (sync) ─────────────────────────────────────────────

def analyze_look(client, url: str, model: str = MODEL_BULK) -> dict:
    images = prepare_images(url) if not MOCK else \
        {"full": "", "top": "", "bottom": ""}
    a = validate_a(client.call(request_params_a(images, model), f"A:{url}"))
    if not a["items"]:
        return merge_passes(a, {"items": []})
    b = validate_b(client.call(
        request_params_b(images, model, a["items"]), f"B:{url}"))
    return merge_passes(a, b)


# ─── CSV I/O ──────────────────────────────────────────────────────────────────

FIELDNAMES = ["designer", "show", "look_number", "image_url",
              "style_tags", "items_json", "confidence"]


def result_row(row: dict, tags: dict) -> dict:
    return {
        "designer": row["designer"], "show": row["show"],
        "look_number": row["look_number"], "image_url": row["image_url"],
        "style_tags": ",".join(tags["styles"]),
        "items_json": json.dumps(tags["items"], ensure_ascii=False),
        "confidence": f"{tags['confidence']:.2f}",
    }


def load_rows(input_csv: str, sample: int) -> list:
    with open(input_csv, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("image_url")]
    return rows[:sample] if sample else rows


def load_processed(output_csv: str) -> set:
    if not os.path.exists(output_csv):
        return set()
    with open(output_csv, encoding="utf-8") as f:
        return {r["image_url"] for r in csv.DictReader(f)}


def append_review_queue(data_dir: str, row: dict, tags: dict):
    path = f"{data_dir}/review_queue.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "image_url": row["image_url"], "designer": row["designer"],
            "show": row["show"], "look_number": row["look_number"],
            "confidence": tags["confidence"],
        }, ensure_ascii=False) + "\n")


# ─── Batch API ────────────────────────────────────────────────────────────────

def _batch_request(custom_id, params):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    return Request(custom_id=custom_id,
                   params=MessageCreateParamsNonStreaming(**params))


def _save_state(data_dir, state):
    with open(f"{data_dir}/batch_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def batch_submit(client, rows, processed, data_dir):
    """Фаза A: полное фото для всех луков одним батчем.
    Фаза B (детали по списку предметов из A) отправляется автоматически
    при --collect, когда фаза A готова."""
    requests, index = [], {}
    print(f"⏳ Подготовка изображений, фаза A ({len(rows)} луков)…")
    for i, row in enumerate(rows):
        url = row["image_url"]
        if url in processed:
            continue
        try:
            images = prepare_images(url)
        except Exception as e:
            print(f"  ⚠️  skip {url}: {e}")
            continue
        index[str(i)] = row
        requests.append(_batch_request(
            f"{i}-A", request_params_a(images, MODEL_BULK)))
        if (i + 1) % 100 == 0:
            print(f"  … {i + 1}/{len(rows)}")

    if not requests:
        print("Нечего отправлять — всё уже обработано.")
        return

    batch = client.client.messages.batches.create(requests=requests)
    _save_state(data_dir, {"phase": "A", "batch_id": batch.id,
                           "index": index})
    print(f"✅ Батч фазы A отправлен: {batch.id} ({len(requests)} запросов)")
    print("   Дальше: python3 enrich_looks.py --collect "
          "(соберёт A и отправит фазу B)")


def _retrieve_results(client, batch_id):
    results = {}
    for res in client.client.messages.batches.results(batch_id):
        if res.result.type != "succeeded":
            print(f"  ⚠️  {res.custom_id}: {res.result.type}")
            continue
        idx = res.custom_id.rsplit("-", 1)[0]
        results[idx] = extract_tool_input(res.result.message)
    return results


def batch_collect(client, data_dir, output_csv):
    state_path = f"{data_dir}/batch_state.json"
    if not os.path.exists(state_path):
        sys.exit("❌ Нет batch_state.json — сначала --full --confirm-full")
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    batch_id, index = state["batch_id"], state["index"]

    batch = client.client.messages.batches.retrieve(batch_id)
    print(f"Батч {batch_id} (фаза {state['phase']}): "
          f"{batch.processing_status}")
    if batch.processing_status != "ended":
        c = batch.request_counts
        print(f"  processing={c.processing} succeeded={c.succeeded} "
              f"errored={c.errored}")
        return

    if state["phase"] == "A":
        # собрать A → подготовить и отправить B
        results_a = {i: validate_a(r) for i, r in
                     _retrieve_results(client, batch_id).items()}
        requests = []
        print(f"⏳ Фаза B: подготовка кропов ({len(results_a)} луков)…")
        for n, (idx, a) in enumerate(results_a.items()):
            if not a["items"]:
                continue
            url = index[idx]["image_url"]
            try:
                images = prepare_images(url)
            except Exception as e:
                print(f"  ⚠️  skip {url}: {e}")
                continue
            requests.append(_batch_request(
                f"{idx}-B",
                request_params_b(images, MODEL_BULK, a["items"])))
            if (n + 1) % 100 == 0:
                print(f"  … {n + 1}/{len(results_a)}")
        batch_b = client.client.messages.batches.create(requests=requests)
        _save_state(data_dir, {"phase": "B", "batch_id": batch_b.id,
                               "index": index,
                               "results_a": {i: a for i, a in
                                             results_a.items()}})
        print(f"✅ Батч фазы B отправлен: {batch_b.id} "
              f"({len(requests)} запросов)")
        print("   Когда завершится: python3 enrich_looks.py --collect")
        return

    # фаза B → финальный merge
    results_b = _retrieve_results(client, batch_id)
    results_a = state["results_a"]
    processed = load_processed(output_csv)
    mode = "a" if os.path.exists(output_csv) else "w"
    n_done = n_review = 0
    with open(output_csv, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if mode == "w":
            writer.writeheader()
        for idx, row in index.items():
            if row["image_url"] in processed or idx not in results_a:
                continue
            a = results_a[idx]
            b = validate_b(results_b.get(idx, {"items": []}))
            tags = merge_passes(a, b)
            writer.writerow(result_row(row, tags))
            n_done += 1
            if tags["confidence"] < CONFIDENCE_THRESHOLD:
                append_review_queue(os.path.dirname(output_csv), row, tags)
                n_review += 1
    print(f"✅ Собрано: {n_done} луков → {output_csv}")
    print(f"   На пересмотр Sonnet (conf < {CONFIDENCE_THRESHOLD}): "
          f"{n_review} → --review")


# ─── Review low-confidence (Sonnet 5) ────────────────────────────────────────

def run_review(client, data_dir, output_csv):
    queue_path = f"{data_dir}/review_queue.jsonl"
    if not os.path.exists(queue_path):
        print("Очередь пересмотра пуста.")
        return
    with open(queue_path, encoding="utf-8") as f:
        queue = [json.loads(line) for line in f if line.strip()]
    # дедуп по url
    queue = list({q["image_url"]: q for q in queue}.values())
    print(f"🔍 Пересмотр {len(queue)} луков моделью {MODEL_REVIEW}")

    with open(output_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_url = {r["image_url"]: r for r in rows}

    for i, q in enumerate(queue):
        url = q["image_url"]
        print(f"[{i + 1}/{len(queue)}] {q['designer']} · Look "
              f"{q['look_number']}", end=" ")
        try:
            tags = analyze_look(client, url, model=MODEL_REVIEW)
        except Exception as e:
            print(f"→ ошибка: {e}")
            continue
        print(f"→ conf {tags['confidence']:.2f}")
        if url in by_url:
            by_url[url].update(result_row(
                {k: by_url[url][k] for k in
                 ("designer", "show", "look_number", "image_url")}, tags))
        time.sleep(0.3)

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    os.rename(queue_path, queue_path + ".done")
    print(f"✅ Пересмотр завершён → {output_csv}")


# ─── Оценка стоимости ─────────────────────────────────────────────────────────

def estimate_cost(n_looks: int) -> str:
    # vision-токены ≈ w*h/750; full 1200×800 ≈ 1280, кропы 800×530 ≈ 570×2
    img_tok = 1280 + 570 * 2
    sys_tok = 2000 * 0.1        # кэш таксономии: чтение = 10% цены
    out_tok = 700 * 2
    in_total = n_looks * (img_tok + sys_tok + 200)
    out_total = n_looks * out_tok
    # Haiku 4.5 batch: $0.50 / $2.50 за Мток
    cost = in_total / 1e6 * 0.50 + out_total / 1e6 * 2.50
    return f"~${cost:.0f} (Haiku 4.5 + Batch −50%)"


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--sample", type=int, default=0,
                   help="Обработать только первые N луков (sync)")
    p.add_argument("--golden", action="store_true",
                   help="Обработать луки из output/golden_set.json (sync)")
    p.add_argument("--full", action="store_true",
                   help="Полный прогон через Batch API")
    p.add_argument("--confirm-full", action="store_true",
                   help="Подтверждение полного прогона (обязательно с --full)")
    p.add_argument("--collect", action="store_true",
                   help="Забрать результаты отправленного батча")
    p.add_argument("--review", action="store_true",
                   help="Пересмотреть low-confidence луки Sonnet 5")
    p.add_argument("--resume", action="store_true",
                   help="Пропустить уже обработанные")
    p.add_argument("--data-dir", default="./output")
    args = p.parse_args()

    data_dir = args.data_dir
    input_csv = f"{data_dir}/all_designers.csv"
    output_csv = f"{data_dir}/enriched_looks_v3.csv"

    def get_client():
        if MOCK:
            print("🧪 MOCK=1 — API не используется, фикстуры из",
                  FIXTURES_PATH)
            return MockClient()
        return LiveClient()

    if args.collect:
        return batch_collect(get_client(), data_dir, output_csv)
    if args.review:
        return run_review(get_client(), data_dir, output_csv)

    if args.golden:
        golden_path = f"{data_dir}/golden_set.json"
        if not os.path.exists(golden_path):
            sys.exit(f"❌ {golden_path} не найден.")
        with open(golden_path, encoding="utf-8") as f:
            rows = [{k: str(g[k]) for k in
                     ("designer", "show", "look_number", "image_url")}
                    for g in json.load(f)]
    else:
        if not os.path.exists(input_csv):
            sys.exit(f"❌ {input_csv} не найден. Сначала запусти скрапер.")
        rows = load_rows(input_csv, args.sample)
    processed = load_processed(output_csv) if args.resume else set()

    if args.full:
        if not args.confirm_full:
            sys.exit(f"⛔ Полный прогон {len(rows)} луков ≈ "
                     f"{estimate_cost(len(rows))}.\n"
                     f"   Добавь --confirm-full для подтверждения "
                     f"(сначала golden set! см. eval_tagging.py)")
        if MOCK:
            sys.exit("⛔ Batch API недоступен в MOCK-режиме")
        return batch_submit(get_client(), rows, processed, data_dir)

    if not args.sample and not args.golden:
        sys.exit("⛔ Без --sample N / --golden только --full (Batch API). "
                 "Для теста: --sample 20")

    # sync-режим для маленьких выборок
    client = get_client()
    print(f"📊 Sync-обработка {len(rows)} луков, модель {MODEL_BULK}")
    mode = "a" if args.resume and os.path.exists(output_csv) else "w"
    n_review = 0
    with open(output_csv, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if mode == "w":
            writer.writeheader()
        for i, row in enumerate(rows):
            url = row["image_url"]
            if url in processed:
                continue
            print(f"[{i + 1}/{len(rows)}] {row['designer']} · "
                  f"Look {row['look_number']}", end=" ")
            try:
                tags = analyze_look(client, url)
            except Exception as e:
                print(f"→ ошибка: {e}")
                continue
            cats = [it["category"] for it in tags["items"]]
            print(f"→ {len(cats)} items ({', '.join(cats[:4])}) "
                  f"· conf {tags['confidence']:.2f}")
            writer.writerow(result_row(row, tags))
            f.flush()
            if tags["confidence"] < CONFIDENCE_THRESHOLD:
                append_review_queue(data_dir, row, tags)
                n_review += 1
            if not MOCK:
                time.sleep(0.4)

    print(f"\n✅ Готово → {output_csv}")
    if n_review:
        print(f"   Low-confidence: {n_review} → python3 enrich_looks.py --review")


if __name__ == "__main__":
    main()
