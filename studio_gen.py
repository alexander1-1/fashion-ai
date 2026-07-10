"""
studio_gen.py — Фаза 6: Студия дизайна (раздел 6 инструкции).

По тренду генерирует варианты дизайна для WB:
  1. Sonnet 5 собирает бриф: EN-промпты для image-модели + ТЗ конструктору
     (категория, силуэт, крой, материал, цвет, отделка). Промпт адаптируется
     под стадию диффузии: «ранние последователи» — ближе к подиуму;
     «раннее большинство» и дальше — упрощённый крой, посадка важнее сложности,
     запах/кулиска/завязки для размерного ряда (практические советы адаптации).
  2. Replicate (FLUX schnell, ~$0.003/изображение) — 4 варианта на тренд.
  3. Сохранение: PNG в output/studio/<trend_id>/, строка в таблицу designs
     (привязка к тренду = мудборд Студии), ТЗ экспортируется текстом.

MOCK=1 — без API: детерминированный бриф + PIL-заглушки вместо генерации.
Токены в .env: ANTHROPIC_API_KEY, REPLICATE_API_TOKEN.

CLI:
    python studio_gen.py generate <trend_id> [--n 4]
    python studio_gen.py techspec <design_id>
    python studio_gen.py list <trend_id>
    MOCK=1 python studio_gen.py generate construction--stand-collar
"""

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import config
import db
from mpstats_client import load_env

MOCK = os.environ.get("MOCK", "0") == "1"

# Практические советы по адаптации (раздел 6 инструкции) — по стадиям.
STAGE_DESIGN_HINTS = {
    "ИННОВАТОРЫ": (
        "Аудитория — новаторы: можно смело, близко к подиумной подаче, "
        "выразительный элемент тренда — главный акцент."),
    "РАННИЕ ПОСЛЕДОВАТЕЛИ": (
        "Ближе к подиуму: сохранить характер тренда, но изделие должно быть "
        "носибельным; пилотная тестовая партия — акцент на сам элемент тренда."),
    "РАННЕЕ БОЛЬШИНСТВО": (
        "Массовая аудитория: упрощать крой, посадка важнее сложности, "
        "повседневный формат; запах/кулиска/завязки для широкого размерного ряда; "
        "дифференцироваться модификациями (цвет, материал, деталь, фурнитура)."),
    "ПОЗДНЕЕ БОЛЬШИНСТВО": (
        "Коммерческая база: максимально простой крой и посадка, базовые цвета "
        "плюс 1–2 трендовых, конкуренция ценой — минимизировать стоимость лекал."),
    "СПАД": (
        "В производство не входить; если генерируем — только как элемент "
        "в другой категории, не как основное изделие."),
}

SYSTEM = """Ты — дизайнер одежды и технический дизайнер для маркетплейса Wildberries.
По тренду и его стадии диффузии подготовь бриф на генерацию изображений и ТЗ конструктору.

Ответ — СТРОГО JSON без markdown:
{
  "category_ru": "категория изделия по-русски (например: джемпер)",
  "image_prompts": ["<prompt 1>", "<prompt 2>", "<prompt 3>", "<prompt 4>"],
  "tech_spec": {
    "category": "категория изделия",
    "silhouette": "силуэт и посадка",
    "construction": "крой и конструктивные элементы (главный — элемент тренда)",
    "materials": "материалы с составом-ориентиром",
    "colors": "цветовые решения (базовые + трендовые)",
    "decoration": "отделка и фурнитура",
    "size_notes": "решения для размерного ряда (запах/кулиска/завязки, если уместно)"
  },
  "adaptation_note": "1-2 предложения: как адаптирован тренд под стадию"
}

Правила image_prompts:
- английский язык, формат для FLUX: продуктовое фэшн-фото, один предмет одежды
  на модели, чистый нейтральный фон, естественный свет, full-body или 3/4;
- элемент тренда должен читаться на изображении явно;
- 4 промпта = 4 РАЗНЫХ варианта (цвет/материал/длина/подача), не повторяться;
- без имён брендов и дизайнеров, без текста на изображении.
Правила tech_spec: конкретика для конструктора, по-русски, без воды."""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


# ─── Бриф: Sonnet 5 (или MOCK) ───────────────────────────────────────────────

def _mock_brief(t, stage: str, n: int) -> dict:
    el, name = t["element"], t["name_ru"]
    return {
        "category_ru": "джемпер",
        "image_prompts": [
            f"fashion product photo, garment featuring {el}, variant {i+1}, "
            f"neutral background, natural light, full body" for i in range(n)],
        "tech_spec": {
            "category": "джемпер",
            "silhouette": "полуприлегающий",
            "construction": f"главный элемент — {name} ({el})",
            "materials": "трикотаж, 50% хлопок",
            "colors": "чёрный, молочный",
            "decoration": "без отделки",
            "size_notes": "эластичная резинка",
        },
        "adaptation_note": f"MOCK-бриф для стадии «{stage or '—'}».",
    }


def build_brief(t, score, n: int = None) -> dict:
    """t — строка trends, score — последний trend_scores (или None)."""
    n = n or config.STUDIO_N_VARIANTS
    stage = (score["stage"] if score else "") or ""
    if MOCK:
        return _mock_brief(t, stage, n)

    load_env()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("❌ Добавь ANTHROPIC_API_KEY в .env (или MOCK=1)")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    metrics = ""
    if score:
        metrics = (f"P (доля подиума) = {score['p_share'] or 0:.1%}, "
                   f"Q (частотность WB) = {score['q_freq'] or 0:,.0f}/мес, "
                   f"карточек в нише = {score['c_cards'] if score['c_cards'] is not None else '—'}")
    user = (f"Тренд: {t['name_ru']} ({t['name_en']}), измерение: {t['type_dimension']}, "
            f"элемент таксономии: {t['element']} (поле {t['field']}).\n"
            f"Стадия диффузии: {stage or 'не определена'}.\n"
            f"Метрики: {metrics or 'нет'}.\n"
            f"Установка по стадии: {STAGE_DESIGN_HINTS.get(stage, 'носибельно и коммерчески.')}\n"
            f"Вариантов: {n}.")

    # 529 Overloaded / сетевые сбои — временные: повторяем до 4 раз
    for attempt in range(1, 5):
        try:
            resp = client.messages.create(
                model=config.STUDIO_BRIEF_MODEL, max_tokens=2000,
                system=SYSTEM, messages=[{"role": "user", "content": user}])
            break
        except Exception as e:
            if attempt == 4:
                raise
            wait = 15 * attempt
            print(f"  API занят ({type(e).__name__}), повтор {attempt}/4 через {wait} c…")
            time.sleep(wait)
    text = next(b.text for b in resp.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    brief = json.loads(text)
    brief["image_prompts"] = (brief.get("image_prompts") or [])[:n]
    return brief


# ─── Изображения: Replicate (или MOCK-заглушки) ──────────────────────────────

def _mock_image(prompt: str, path: Path) -> None:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (768, 1024), (58, 56, 52))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 728, 984], outline=(150, 140, 120), width=3)
    words, lines, cur = prompt.split(), [], ""
    for w in words:
        if len(cur) + len(w) > 34:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    d.text((60, 80), "MOCK\n\n" + "\n".join(lines[:18]), fill=(220, 214, 200))
    img.save(path, "PNG")


def _replicate_generate(prompt: str, path: Path) -> None:
    """FLUX schnell через REST API Replicate (Prefer: wait — синхронно)."""
    import requests
    load_env()
    token = os.environ.get("REPLICATE_API_TOKEN", "")
    if not token:
        sys.exit("❌ Добавь REPLICATE_API_TOKEN в .env (или MOCK=1)")
    r = requests.post(
        f"https://api.replicate.com/v1/models/{config.REPLICATE_MODEL}/predictions",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json",
                 "Prefer": "wait=60"},
        json={"input": {"prompt": prompt, "aspect_ratio": config.REPLICATE_ASPECT,
                        "num_outputs": 1, "output_format": "png"}},
        timeout=120)
    r.raise_for_status()
    pred = r.json()

    # если wait не дождался — доопрашиваем
    while pred.get("status") in ("starting", "processing"):
        time.sleep(2)
        pr = requests.get(pred["urls"]["get"],
                          headers={"Authorization": f"Bearer {token}"}, timeout=30)
        pr.raise_for_status()
        pred = pr.json()
    if pred.get("status") != "succeeded":
        raise RuntimeError(f"Replicate: {pred.get('status')} {pred.get('error')}")

    out = pred.get("output")
    url = out[0] if isinstance(out, list) else out
    img = requests.get(url, timeout=120)
    img.raise_for_status()
    path.write_bytes(img.content)


# ─── Основной сценарий ───────────────────────────────────────────────────────

def generate_for_trend(conn, trend_id: str, n: int = None) -> list[dict]:
    """Бриф → n изображений → строки в designs. Возвращает созданные дизайны."""
    n = n or config.STUDIO_N_VARIANTS
    t = conn.execute("SELECT * FROM trends WHERE trend_id=?", (trend_id,)).fetchone()
    if not t:
        raise ValueError(f"нет тренда {trend_id}")
    score = conn.execute(
        """SELECT * FROM trend_scores WHERE trend_id=?
           ORDER BY date DESC LIMIT 1""", (trend_id,)).fetchone()
    stage = (score["stage"] if score else "") or ""

    brief = build_brief(t, score, n)
    tech_spec = json.dumps(brief.get("tech_spec", {}), ensure_ascii=False)
    model = "mock" if MOCK else config.REPLICATE_MODEL.split("/")[-1]

    out_dir = Path(config.STUDIO_DIR) / trend_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    created = []
    for i, prompt in enumerate(brief["image_prompts"][:n], 1):
        path = out_dir / f"{ts}_{i}.png"
        status = "ok"
        try:
            if MOCK:
                _mock_image(prompt, path)
            else:
                _replicate_generate(prompt, path)
        except Exception as e:                       # изображение не критично:
            print(f"  ! вариант {i}: {e}")           # ТЗ и промпт сохраняем всё равно
            path, status = None, "error"
        cur = conn.execute(
            """INSERT INTO designs (trend_id, stage, category, image_prompt,
                                    tech_spec, image_path, model, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (trend_id, stage, brief.get("category_ru", ""), prompt, tech_spec,
             str(path) if path else None, model, status))
        d = conn.execute("SELECT * FROM designs WHERE design_id=?",
                         (cur.lastrowid,)).fetchone()
        created.append(dict(d))
    conn.commit()
    return created


def techspec_text(d) -> str:
    """ТЗ конструктору — плоский текст для экспорта (п. 6.3 инструкции)."""
    spec = json.loads(d["tech_spec"] or "{}")
    lines = [
        f"ТЗ КОНСТРУКТОРУ — дизайн #{d['design_id']} (тренд: {d['trend_id']})",
        f"Дата: {d['created_at']} · Стадия тренда: {d['stage'] or '—'}",
        "",
    ]
    labels = [("category", "Категория"), ("silhouette", "Силуэт и посадка"),
              ("construction", "Крой"), ("materials", "Материалы"),
              ("colors", "Цвета"), ("decoration", "Отделка и фурнитура"),
              ("size_notes", "Размерный ряд")]
    for key, label in labels:
        if spec.get(key):
            lines.append(f"{label}: {spec[key]}")
    lines += ["", f"Промпт изображения: {d['image_prompt']}",
              f"Файл изображения: {d['image_path'] or '—'}"]
    return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="сгенерировать варианты по тренду")
    g.add_argument("trend_id")
    g.add_argument("--n", type=int, default=config.STUDIO_N_VARIANTS)
    ts = sub.add_parser("techspec", help="вывести ТЗ дизайна")
    ts.add_argument("design_id", type=int)
    ls = sub.add_parser("list", help="дизайны тренда")
    ls.add_argument("trend_id")
    args = ap.parse_args()

    conn = db.init_db()
    if args.cmd == "generate":
        if MOCK:
            print("🧪 MOCK=1 — API не используется, изображения-заглушки")
        for d in generate_for_trend(conn, args.trend_id, args.n):
            print(f"  #{d['design_id']} [{d['status']}] {d['image_path'] or '—'}")
    elif args.cmd == "techspec":
        d = conn.execute("SELECT * FROM designs WHERE design_id=?",
                         (args.design_id,)).fetchone()
        if not d:
            sys.exit(f"нет дизайна {args.design_id}")
        print(techspec_text(d))
    elif args.cmd == "list":
        for d in conn.execute(
                "SELECT * FROM designs WHERE trend_id=? ORDER BY created_at DESC",
                (args.trend_id,)):
            print(f"  #{d['design_id']} {d['created_at']} [{d['status']}] "
                  f"{d['model']} {d['image_path'] or '—'}")


if __name__ == "__main__":
    main()
