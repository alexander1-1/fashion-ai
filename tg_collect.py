"""
tg_collect.py — Telethon-коллектор фото из TG-каналов (раздел 3.3, Фаза 4).

Telegram — основной канал инфлюенсер-сигналов (надёжный API). Скачивает фото
из публичных каналов (channels.txt) за период, складывает в
inbox/telegram/{channel}/ и регистрирует в ext_photos
(level='influencer', source='tg:{channel}', дата = дата поста).
Тегирование — отдельно: python photo_tagger.py tag.

Настройка (один раз):
  1. https://my.telegram.org → API development tools → api_id + api_hash.
  2. В .env:  TG_API_ID=…  TG_API_HASH=…
  3. python tg_collect.py --login   # код придёт в Telegram; сессия
     сохранится в tg_session.session (в .gitignore, НЕ коммитить).

Обычный запуск (инкрементальный — уже скачанные сообщения пропускаются):
    python tg_collect.py --days 30
    python tg_collect.py --days 30 --channels rogov24,zashmot
    python tg_collect.py --days 30 --limit 100   # max фото на канал

Альбомы: каждое фото альбома скачивается отдельным файлом (единый msg-URL).
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import db
from mpstats_client import load_env
from photo_tagger import register_photo

INBOX_TG = Path(config.INBOX_DIR) / "telegram"
SESSION = "tg_session"


def read_channels(path: str = "channels.txt") -> list[str]:
    channels = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lstrip("@")
        if line:
            channels.append(line)
    return channels


def _credentials() -> tuple[int, str]:
    import os
    load_env()
    api_id = os.environ.get("TG_API_ID", "")
    api_hash = os.environ.get("TG_API_HASH", "")
    if not api_id or not api_hash:
        sys.exit("❌ Добавь в .env: TG_API_ID и TG_API_HASH "
                 "(https://my.telegram.org → API development tools)")
    return int(api_id), api_hash


def _client():
    try:
        from telethon import TelegramClient
    except ImportError:
        sys.exit("❌ pip install telethon")
    api_id, api_hash = _credentials()
    return TelegramClient(SESSION, api_id, api_hash)


async def collect_channel(client, conn, channel: str, since: datetime,
                          limit: int) -> tuple[int, int]:
    """→ (новых фото, пропущено уже имеющихся)."""
    out_dir = INBOX_TG / channel
    out_dir.mkdir(parents=True, exist_ok=True)
    new = skipped = 0

    async for msg in client.iter_messages(channel, offset_date=None):
        if msg.date < since:
            break
        if new >= limit:
            break
        if not msg.photo:
            continue
        dest = out_dir / f"{msg.id}.jpg"
        url = f"https://t.me/{channel}/{msg.id}"
        if dest.exists():
            skipped += 1
            continue
        try:
            await client.download_media(msg, file=str(dest))
        except Exception as e:
            print(f"    ! {channel}/{msg.id}: {e}")
            continue
        pid = register_photo(
            conn, dest, level="influencer", source=f"tg:{channel}",
            photo_date=msg.date.date().isoformat(), url=url)
        if pid:
            new += 1
        else:
            skipped += 1  # дубликат по sha1 (репост того же фото)

    return new, skipped


async def run(days: int, only: list[str] | None, limit: int):
    conn = db.init_db()
    channels = read_channels(config.TG_CHANNELS_FILE)
    if only:
        channels = [c for c in channels if c in only]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    client = _client()
    await client.start()  # использует сохранённую сессию
    print(f"Каналов: {len(channels)}, период: {days} дн. (с {since.date()})\n")

    total_new = 0
    for ch in channels:
        print(f"📢 @{ch}")
        try:
            new, skipped = await collect_channel(client, conn, ch, since, limit)
            total_new += new
            print(f"   новых фото: {new}, пропущено: {skipped}")
        except Exception as e:
            print(f"   ! канал недоступен: {e}")
        await asyncio.sleep(1.5)  # бережём rate limit

    await client.disconnect()
    n_pending = conn.execute(
        "SELECT COUNT(*) FROM ext_photos WHERE status='pending'").fetchone()[0]
    print(f"\n✅ Всего новых: {total_new}. В очереди на тегирование: {n_pending}")
    print("   Дальше: python photo_tagger.py tag --sample 20  (потом полный)")


def login():
    """Одноразовая интерактивная авторизация (запускать локально)."""
    client = _client()

    async def _do():
        await client.start()  # спросит телефон и код
        me = await client.get_me()
        print(f"✅ Авторизован как {me.first_name} (@{me.username}). "
              f"Сессия: {SESSION}.session")
        await client.disconnect()

    asyncio.run(_do())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--login", action="store_true",
                    help="одноразовая авторизация (интерактивно)")
    ap.add_argument("--days", type=int, default=config.TG_DEFAULT_DAYS)
    ap.add_argument("--channels", default="",
                    help="список через запятую (по умолчанию все из channels.txt)")
    ap.add_argument("--limit", type=int, default=config.TG_MAX_PHOTOS_PER_CHANNEL,
                    help="max новых фото на канал")
    args = ap.parse_args()

    if args.login:
        login()
    else:
        only = [c.strip().lstrip("@") for c in args.channels.split(",") if c.strip()]
        asyncio.run(run(args.days, only or None, args.limit))
