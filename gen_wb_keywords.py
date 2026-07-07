"""
gen_wb_keywords.py — генерация поисковых ключей WB для трендов (п. 4.1 инструкции).

Sonnet 5 получает пачку трендов и для каждого предлагает 3–6 реальных
поисковых запросов Wildberries. Результат — в output/wb_keywords_proposed.json
на ручную правку; в БД пишется только по --apply.

Правила ключей (зашиты в промпт):
  - формулировки, которые реально вводят покупатели WB: изделие + признак
    («рубашка в клетку»), а не название элемента («клетка» — это клетки
    для грызунов);
  - крой/отделка — в связке с популярными категориями («джемпер воротник
    стойка», «платье с драпировкой»);
  - цвета Pantone — как их ищут по-русски («пудровое платье»), не «rose quartz»;
  - стили — узнаваемые запросы («старые деньги стиль», «бохо платье»);
  - lowercase, без кавычек, без слишком общих одиночных слов.

CLI:
    python gen_wb_keywords.py                # сгенерировать предложения
    python gen_wb_keywords.py --limit 10     # пробный прогон на 10 трендах
    python gen_wb_keywords.py --force        # включая уже курированные
    python gen_wb_keywords.py --apply        # записать proposed-файл в БД
"""

import argparse
import json
import os
import sys
from pathlib import Path

import db

MODEL = "claude-sonnet-5"           # как MODEL_REVIEW в enrich_looks.py
BATCH = 25                          # трендов на один вызов
PROPOSED = Path("output/wb_keywords_proposed.json")

SYSTEM = """Ты — SEO-специалист по Wildberries в нише женской и мужской одежды.
Для каждого тренда предложи 3–6 поисковых запросов, которые РЕАЛЬНО вводят
покупатели WB и выдача по которым соответствует именно этому тренду.

Правила:
1. Запрос = изделие + признак («рубашка в клетку», «джемпер воротник стойка»).
   Никогда не давай признак отдельным словом: по «клетка» WB показывает клетки
   для грызунов, по «полоска» — малярный скотч.
2. Для кроя/отделки/принта комбинируй с 2–4 самыми продаваемыми категориями,
   где элемент органичен (платье, рубашка, джемпер, брюки, юбка, пальто…).
3. Названия цветов Pantone переводи в покупательские формулировки:
   «rose quartz» → «платье пудрово-розовое», «chocolate brown» → «костюм шоколадный».
4. Стили — узнаваемые у аудитории запросы: «старые деньги стиль», «бохо платье»,
   «спортшик костюм». Если стиль на WB не ищут — дай ближайшие предметные запросы.
5. Всё в нижнем регистре, без кавычек и знаков препинания внутри запроса.

Ответ — СТРОГО JSON без пояснений и без markdown:
{"<trend_id>": ["ключ 1", "ключ 2", ...], ...}"""


def naive(t) -> bool:
    """True, если ключи — автозаглушка (копия name_ru), т.е. не курированы."""
    return json.loads(t["wb_keywords"] or "[]") in ([], [t["name_ru"].lower()])


def build_user_msg(batch) -> str:
    lines = ["Тренды (trend_id | измерение | название | элемент таксономии):"]
    for t in batch:
        lines.append(f"- {t['trend_id']} | {t['type_dimension']} | "
                     f"{t['name_ru']} | {t['element']}")
    return "\n".join(lines)


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def generate(limit: int | None, force: bool):
    import anthropic
    from mpstats_client import load_env
    load_env()                       # ANTHROPIC_API_KEY можно держать в .env
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("❌ Добавь ANTHROPIC_API_KEY=sk-ant-... в .env (или export)")
    client = anthropic.Anthropic(api_key=api_key)

    conn = db.connect()
    rows = conn.execute(
        "SELECT * FROM trends WHERE status != 'archived' ORDER BY trend_id").fetchall()
    todo = [t for t in rows if force or naive(t)]
    if limit:
        todo = todo[:limit]
    skipped = len(rows) - len(todo)
    print(f"Трендов к генерации: {len(todo)} (пропущено курированных: {skipped})")

    proposed = json.loads(PROPOSED.read_text()) if PROPOSED.exists() else {}
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        resp = client.messages.create(
            model=MODEL, max_tokens=4000,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_user_msg(batch)}])
        data = parse_json(resp.content[0].text)
        for t in batch:
            kws = [k.strip().lower() for k in data.get(t["trend_id"], []) if k.strip()]
            if kws:
                proposed[t["trend_id"]] = {"name_ru": t["name_ru"], "keywords": kws}
                print(f"  {t['trend_id']:45s} → {', '.join(kws)}")
            else:
                print(f"  {t['trend_id']:45s} → ПУСТО (проверь вручную)")
        PROPOSED.parent.mkdir(exist_ok=True)
        PROPOSED.write_text(json.dumps(proposed, ensure_ascii=False, indent=2))

    print(f"\nСохранено: {PROPOSED} — поправь руками при необходимости,"
          f"\nзатем: python gen_wb_keywords.py --apply")


def apply():
    if not PROPOSED.exists():
        sys.exit(f"❌ Нет {PROPOSED} — сначала сгенерируй предложения")
    proposed = json.loads(PROPOSED.read_text())
    conn = db.connect()
    n = 0
    for trend_id, item in proposed.items():
        kws = [k.strip().lower() for k in item["keywords"] if k.strip()]
        if not kws:
            continue
        cur = conn.execute(
            "UPDATE trends SET wb_keywords=? WHERE trend_id=?",
            (json.dumps(kws, ensure_ascii=False), trend_id))
        n += cur.rowcount
    conn.commit()
    print(f"Записано ключей для {n} трендов."
          f"\nДальше: python mpstats_client.py collect --all && python trends.py score")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Генерация wb_keywords через Sonnet 5")
    ap.add_argument("--limit", type=int, help="только первые N трендов (проба)")
    ap.add_argument("--force", action="store_true", help="перегенерить и курированные")
    ap.add_argument("--apply", action="store_true", help="записать proposed-файл в БД")
    args = ap.parse_args()
    apply() if args.apply else generate(args.limit, args.force)
