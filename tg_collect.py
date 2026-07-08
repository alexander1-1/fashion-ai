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

РЕЗЕРВНЫЙ РЕЖИМ без api_id/api_hash (--web или просто нет TG_API_ID в .env):
парсинг веб-превью t.me/s/{channel} (перенос из fashion-ai/fetch_telegram.py).
Работает сразу, но только для каналов с включённым превью и без гарантий
Telegram; качество дат/полноты ниже, чем у Telethon. Токен ЧАТ-БОТА
(BotFather) здесь бесполезен: боты не читают чужие каналы.
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


def _credentials(required: bool = True) -> tuple[int, str] | None:
    import os
    load_env()
    api_id = os.environ.get("TG_API_ID", "")
    api_hash = os.environ.get("TG_API_HASH", "")
    if not api_id or not api_hash:
        if required:
            sys.exit("❌ Добавь в .env: TG_API_ID и TG_API_HASH "
                     "(https://my.telegram.org → API development tools)")
        return None
    return int(api_id), api_hash


# ─── Резервный режим: веб-превью t.me/s/ (без API-ключей) ────────────────────

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _ssl_ctx():
    """macOS-питон часто без корневых сертификатов (см. fashion-ai):
    пробуем certifi, иначе — unverified (публичные превью, риск минимален)."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    try:
        ctx = ssl.create_default_context()
        import urllib.request
        urllib.request.urlopen("https://t.me", timeout=10, context=ctx)
        return ctx
    except Exception:
        return ssl._create_unverified_context()


_SSL_CTX = None


def _fetch_url(url: str, timeout: int = 30, referer: str = "") -> bytes:
    global _SSL_CTX
    import urllib.request
    if _SSL_CTX is None:
        _SSL_CTX = _ssl_ctx()
    headers = {"User-Agent": _UA, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return r.read()


def _fetch_html(url: str, retries: int = 3) -> str:
    import time
    for attempt in range(retries):
        try:
            return _fetch_url(url).decode("utf-8", errors="ignore")
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(4 * (attempt + 1))


def _parse_preview_posts(html: str, channel: str) -> list[dict]:
    """Посты с фото из HTML t.me/s/: [{msg_id, url, img_url, date}]."""
    import re
    posts = []
    for block in re.split(r'<div class="tgme_widget_message_wrap', html)[1:]:
        m = re.search(
            r'href="(https://t\.me/' + re.escape(channel) + r'/(\d+))"', block)
        if not m:
            continue
        date_m = re.search(r'<time[^>]+datetime="([^"]+)"', block)
        post_date = None
        if date_m:
            try:
                post_date = datetime.fromisoformat(
                    date_m.group(1).replace("Z", "+00:00"))
            except ValueError:
                pass
        imgs = re.findall(r"background-image:url\('(https?://[^']+)'\)", block)
        imgs = [u for u in imgs if "cdn" in u or "telesco" in u] or imgs
        if not imgs:
            continue
        posts.append({"msg_id": m.group(2), "url": m.group(1),
                      "img_url": imgs[0], "date": post_date})
    return posts


def _collect_channel_web(conn, channel: str, since: datetime,
                         limit: int) -> tuple[int, int]:
    import re
    import time
    out_dir = INBOX_TG / channel
    out_dir.mkdir(parents=True, exist_ok=True)
    new = skipped = 0
    url = f"https://t.me/s/{channel}"

    for _page in range(30):
        html = _fetch_html(url)
        posts = _parse_preview_posts(html, channel)
        if not posts:
            break
        reached_cutoff = any(p["date"] and p["date"] < since for p in posts)

        for p in posts:
            if new >= limit:
                break
            if p["date"] and p["date"] < since:
                continue
            dest = out_dir / f"{p['msg_id']}.jpg"
            if dest.exists():
                skipped += 1
                continue
            try:
                data = _fetch_url(p["img_url"], timeout=20, referer="https://t.me/")
                if len(data) < 3000:
                    continue
                dest.write_bytes(data)
            except Exception:
                continue
            d = (p["date"] or datetime.now(timezone.utc)).date().isoformat()
            if register_photo(conn, dest, level="influencer",
                              source=f"tg:{channel}", photo_date=d, url=p["url"]):
                new += 1
            else:
                skipped += 1

        if reached_cutoff or new >= limit:
            break
        ids = [int(i) for i in re.findall(r't\.me/\w+/(\d+)', html)]
        if not ids or min(ids) <= 1:
            break
        url = f"https://t.me/s/{channel}?before={min(ids)}"
        time.sleep(2)

    return new, skipped


def run_web(days: int, only: list[str] | None, limit: int):
    conn = db.init_db()
    channels = read_channels(config.TG_CHANNELS_FILE)
    if only:
        channels = [c for c in channels if c in only]
    since = datetime.now(timezone.utc) - timedelta(days=days)
    print(f"[веб-превью t.me/s/ — без API] Каналов: {len(channels)}, "
          f"период: {days} дн.\n")
    import time
    total_new = 0
    for ch in channels:
        print(f"📢 @{ch}")
        try:
            new, skipped = _collect_channel_web(conn, ch, since, limit)
            total_new += new
            print(f"   новых фото: {new}, пропущено: {skipped}")
        except Exception as e:
            print(f"   ! канал недоступен: {e}")
        time.sleep(3)
    n_pending = conn.execute(
        "SELECT COUNT(*) FROM ext_photos WHERE status='pending'").fetchone()[0]
    print(f"\n✅ Всего новых: {total_new}. В очереди на тегирование: {n_pending}")
    print("   Дальше: python photo_tagger.py tag")


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
    ap.add_argument("--web", action="store_true",
                    help="принудительно веб-превью t.me/s/ (без API)")
    args = ap.parse_args()

    if args.login:
        login()
    else:
        only = [c.strip().lstrip("@") for c in args.channels.split(",") if c.strip()]
        if args.web or _credentials(required=False) is None:
            if not args.web:
                print("TG_API_ID/TG_API_HASH нет в .env → веб-превью t.me/s/. "
                      "Telethon включится, когда добавишь ключи.\n")
            run_web(args.days, only or None, args.limit)
        else:
            asyncio.run(run(args.days, only or None, args.limit))
