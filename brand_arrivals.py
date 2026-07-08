"""
brand_arrivals.py — парсер «новинок» middle/fast-fashion брендов (раздел 3.2).

Перенос store_scraper.py из ~/Desktop/fashion-ai, обобщённый с «кардиганов»
на разделы новинок. Фото → inbox/brands/{slug}/ → ext_photos
(level='middle'|'fast_fashion', source=slug) → photo_tagger.py tag.

Запуск раз в 2–4 недели, ЛОКАЛЬНО (Playwright с видимым браузером — сайты
за Cloudflare, headless блокируют):
    python brand_arrivals.py --download                  # все бренды
    python brand_arrivals.py --download --brand zara     # один бренд
    python brand_arrivals.py --list                      # реестр брендов

Если бренд блокирует даже видимый браузер — полуручной режим (п. 3.2):
сохрани фото руками в inbox/brands/{slug}/ — их подхватит
python inbox_process.py (дата = mtime файла).

URL разделов новинок меняются — при пустой выдаче проверь url в BRANDS.
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import config
import db
from photo_tagger import register_photo

INBOX_BRANDS = Path(config.INBOX_DIR) / "brands"
TARGET_PER_BRAND = 60

# ── Реестр брендов (списки из презентаций, п. 3.2) ────────────────────────────
# level: 'fast_fashion' | 'middle'. url — раздел новинок (women).
BRANDS = [
    # fast-fashion
    {"slug": "zara", "name": "Zara", "level": "fast_fashion",
     "url": "https://www.zara.com/us/en/woman-new-in-l1180.html"},
    {"slug": "hm", "name": "H&M", "level": "fast_fashion",
     "url": "https://www2.hm.com/en_us/women/new-arrivals/view-all.html"},
    {"slug": "bershka", "name": "Bershka", "level": "fast_fashion",
     "url": "https://www.bershka.com/us/women/new-c1010193213.html"},
    {"slug": "stradivarius", "name": "Stradivarius", "level": "fast_fashion",
     "url": "https://www.stradivarius.com/us/woman/new-in-n1898"},
    {"slug": "mango", "name": "Mango", "level": "fast_fashion",
     "url": "https://shop.mango.com/us/en/c/women/new-now_d55927954"},
    {"slug": "lime", "name": "Lime", "level": "fast_fashion",
     "url": "https://lime-shop.com/ru/catalog/new"},
    {"slug": "love-republic", "name": "Love Republic", "level": "fast_fashion",
     "url": "https://loverepublic.ru/catalog/novinki/"},
    {"slug": "befree", "name": "Befree", "level": "fast_fashion",
     "url": "https://befree.ru/zhenskaya/novinki"},
    {"slug": "zarina", "name": "Zarina", "level": "fast_fashion",
     "url": "https://zarina.ru/catalog/new/"},
    {"slug": "shein", "name": "Shein", "level": "fast_fashion",
     "url": ""},  # агрессивный антибот — только inbox/brands/shein/
    {"slug": "urban-revivo", "name": "Urban Revivo", "level": "fast_fashion",
     "url": "https://www.urbanrevivo.com/collections/new-in-women"},
    # middle
    {"slug": "ganni", "name": "Ganni", "level": "middle",
     "url": "https://www.ganni.com/en-us/new-arrivals"},
    {"slug": "rotate", "name": "ROTATE", "level": "middle",
     "url": "https://rotate-birgerchristensen.com/collections/new-in"},
    {"slug": "sandro", "name": "Sandro", "level": "middle",
     "url": "https://us.sandro-paris.com/en/womens/new-arrivals/"},
    {"slug": "maje", "name": "Maje", "level": "middle",
     "url": "https://us.maje.com/en/categories/new-collection/"},
    {"slug": "frankie-shop", "name": "The Frankie Shop", "level": "middle",
     "url": "https://thefrankieshop.com/collections/new-arrivals"},
    {"slug": "12storeez", "name": "12 Storeez", "level": "middle",
     "url": "https://12storeez.com/new"},
    {"slug": "toptop", "name": "TopTop", "level": "middle",
     "url": "https://toptop.ru/catalog/new"},
    {"slug": "ushatava", "name": "Ushatava", "level": "middle",
     "url": "https://ushatava.com/collections/new"},
    {"slug": "2mood", "name": "2Mood", "level": "middle",
     "url": "https://2mood.ru/catalog/novinki"},
]

BRAND_BY_SLUG = {b["slug"]: b for b in BRANDS}

# ── Фильтры мусорных изображений (из store_scraper) ───────────────────────────
SKIP_PATTERNS = [
    "logo", "icon", "avatar", "flag", "payment", "social", "spinner",
    "placeholder", "blank", "pixel", "tracking", "1x1", "spacer",
    "badge", "favicon", "banner", "svg",
]
SMALL_SIZE_PATTERNS = [
    "wid=16", "wid=40", "wid=80", "wid=100",
    "w=16", "w=40", "w=50", "w=60", "w=80", "w=100",
    "_50x", "_60x", "_80x", "_100x", "-020?", "-020&",
    "imwidth=80", "imwidth=160", "imwidth=240",
]


def scroll_page(page, steps: int = 15):
    page.wait_for_timeout(1500)
    for i in range(steps):
        page.evaluate(
            f"window.scrollTo(0, document.body.scrollHeight * {(i + 1) / steps:.3f})")
        page.wait_for_timeout(800)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)


def close_popups(page):
    page.evaluate("""
        () => {
            var texts = ['Accept', 'Accept All', 'Accept Cookies', 'I Accept',
                         'OK', 'Close', 'Dismiss', 'No thanks', 'Принять',
                         'Согласен', 'Хорошо', 'Понятно'];
            var btns = document.querySelectorAll('button, a, [role="button"]');
            for (var b of btns) {
                var t = b.textContent.trim();
                for (var x of texts)
                    if (t === x || t.startsWith(x)) { b.click(); break; }
            }
            var overlays = document.querySelectorAll(
                '[class*="modal"],[class*="popup"],[class*="overlay"],' +
                '[class*="cookie"],[class*="consent"]');
            for (var o of overlays) o.style.display = 'none';
        }
    """)


def extract_images_from_dom(page, target: int) -> list[str]:
    """img.src / data-src / srcset (наибольший) с фильтрами мусора."""
    skip = SKIP_PATTERNS + SMALL_SIZE_PATTERNS
    return page.evaluate("""
        (args) => {
            var seen = new Set(); var results = [];
            function bestSrc(img) {
                var ds = img.getAttribute('data-src') || img.getAttribute('data-lazy')
                      || img.getAttribute('data-original');
                if (ds && ds.startsWith('http')) return ds;
                var ss = img.getAttribute('srcset') || '';
                if (ss) {
                    var bestW = 0, best = '';
                    for (var p of ss.split(',')) {
                        var t = p.trim().split(/\\s+/);
                        var w = parseInt(t[1] || '0');
                        if (w > bestW) { bestW = w; best = t[0]; }
                    }
                    if (best && best.startsWith('http')) return best;
                }
                if (img.src && img.src.startsWith('http')) return img.src;
                return '';
            }
            for (var img of document.querySelectorAll('img')) {
                var src = bestSrc(img);
                if (!src || src.length < 20) continue;
                var low = src.toLowerCase();
                if (args.skip.some(s => low.includes(s))) continue;
                if (seen.has(src)) continue;
                seen.add(src); results.push(src);
                if (results.length >= args.target) break;
            }
            return results;
        }
    """, {"skip": skip, "target": target}) or []


def download_image(url: str, dest: Path) -> bool:
    import urllib.request
    if dest.exists():
        return True
    try:
        host = url.split("/")[2]
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": f"https://{host}/",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 5000:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def scrape_brand(page, conn, brand: dict, target: int) -> int:
    """→ число новых фото (скачано + зарегистрировано в ext_photos)."""
    slug, url = brand["slug"], brand["url"]
    if not url:
        print(f"  {brand['name']}: только ручной режим — inbox/brands/{slug}/")
        return 0
    out_dir = INBOX_BRANDS / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print(f"\n🏪 {brand['name']} ({brand['level']})\n  → {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        close_popups(page)
        page.wait_for_timeout(1000)
    except Exception as e:
        print(f"  ! страница не открылась: {e}")
        return 0

    # перехват байтов — для CDN, блокирующих прямые запросы
    captured: dict[str, bytes] = {}

    def on_response(response):
        u = response.url
        ct = response.headers.get("content-type", "")
        if not any(t in ct for t in ("image/jpeg", "image/png", "image/webp", "image/avif")):
            return
        low = u.lower()
        if any(p in low for p in SKIP_PATTERNS) or any(p in u for p in SMALL_SIZE_PATTERNS):
            return
        if u in captured:
            return
        try:
            data = response.body()
            if len(data) >= 8000:
                captured[u] = data
        except Exception:
            pass

    page.on("response", on_response)
    scroll_page(page, steps=15)
    urls = extract_images_from_dom(page, target=target)
    page.remove_listener("response", on_response)
    print(f"  → DOM: {len(urls)} URL, перехвачено байт: {len(captured)}")

    if not urls and not captured:
        print(f"  ! пусто — блок или изменился URL; ручной режим: inbox/brands/{slug}/")
        return 0

    ordered = urls + [u for u in captured if u not in set(urls)]
    new = 0
    for img_url in ordered[: target * 2]:
        if new >= target:
            break
        name = re.sub(r"[^a-zA-Z0-9]+", "_", img_url.split("/")[-1].split("?")[0])[:60]
        dest = out_dir / f"{today}_{name}.jpg"
        saved = False
        if img_url in captured:
            if not dest.exists():
                dest.write_bytes(captured[img_url])
            saved = True
        else:
            saved = download_image(img_url, dest)
        if not saved:
            continue
        pid = register_photo(conn, dest, level=brand["level"], source=slug,
                             photo_date=today, url=img_url)
        if pid:
            new += 1
        elif not dest.exists():
            pass
    print(f"  ✅ новых фото: {new}")
    return new


def cmd_download(only: str | None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("❌ pip install playwright && playwright install chromium")

    conn = db.init_db()
    brands = [b for b in BRANDS if only is None or b["slug"] == only]
    if not brands:
        sys.exit(f"❌ Нет бренда '{only}'. Смотри: python brand_arrivals.py --list")

    total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-US")
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        for brand in brands:
            total += scrape_brand(page, conn, brand, TARGET_PER_BRAND)
            time.sleep(2)
        browser.close()

    n_pending = conn.execute(
        "SELECT COUNT(*) FROM ext_photos WHERE status='pending'").fetchone()[0]
    print(f"\n✅ Итого новых: {total}. В очереди на тегирование: {n_pending}")
    print("   Дальше: python photo_tagger.py tag")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--brand", default=None, help="slug одного бренда")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for b in BRANDS:
            mode = b["url"] or "ручной (inbox)"
            print(f"  {b['slug']:15s} {b['level']:13s} {mode}")
    elif args.download:
        cmd_download(args.brand)
    else:
        print(__doc__)
