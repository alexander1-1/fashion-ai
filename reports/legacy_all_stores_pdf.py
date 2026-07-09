#!/usr/bin/env python3
"""
legacy_all_stores_pdf.py — Сводный тренд-отчёт US Retail (перенос из ~/Desktop/fashion-ai, Фаза 6).

Данные (JSON-кэши и фото магазинов) остаются в старом проекте fashion-ai;
путь к нему настраивается переменной окружения FASHION_AI_DIR.
PDF сохраняется в output/reports/. Запуск:
    python -m reports.legacy_all_stores_pdf
"""

import json, os, pathlib, io
from PIL import Image as PILImage
from collections import Counter

BASE    = pathlib.Path(os.environ.get(
    "FASHION_AI_DIR", pathlib.Path.home() / "Desktop" / "fashion-ai")).expanduser()
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "output" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PDF = OUT_DIR / "all_stores_trend_report.pdf"
REPORT  = json.loads((BASE / "all_stores_report_data.json").read_text())

BRANDS_META = [
    ("Zara",          "zara",          "#1C1C1C"),
    ("COS",           "cos",           "#2C3E50"),
    ("H&M",           "hm",            "#E50010"),
    ("Mango",         "mango",         "#C8A87A"),
    ("Massimo Dutti", "massimo-dutti", "#1A3A5C"),
    ("Reserved",      "reserved",      "#C41E3A"),
    ("Bershka",       "bershka",       "#FF6B35"),
]

# ── Load images + cache data ───────────────────────────────────────────────────
manifest    = json.loads((BASE / "stores" / "manifest.json").read_text())
manifest_nums = {}
for e in manifest:
    s = e.get("store") or e.get("slug","")
    manifest_nums.setdefault(s, set()).add(e.get("product_num",0))

brand_images = {}
brand_cache  = {}
for bname, bkey, _ in BRANDS_META:
    store_dir  = BASE / "stores" / bkey
    valid_nums = manifest_nums.get(bname, manifest_nums.get(bkey, set()))
    imgs = sorted([p for p in store_dir.glob("product_*.jpg")
                   if int(p.stem.split("_")[1]) in valid_nums]) if valid_nums else []
    brand_images[bname] = imgs
    cfile = BASE / f"{bkey.replace('-','_')}_analysis_cache.json"
    if cfile.exists():
        raw = json.loads(cfile.read_text())
        items = []
        for v in raw.values(): items.extend(v)
        brand_cache[bname] = {d.get("img","").split("/")[-1]: d for d in items}
    else:
        brand_cache[bname] = {}

total_imgs = sum(len(v) for v in brand_images.values())
print(f"Изображений: {total_imgs} | Брендов: {len(BRANDS_META)}")

# ── ReportLab ──────────────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak, HRFlowable, KeepTogether, KeepInFrame,
    CondPageBreak
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

FONT_PATHS = [
    (str(BASE/"fonts"/"DejaVuSans.ttf"),       str(BASE/"fonts"/"DejaVuSans-Bold.ttf")),
    ("/Library/Fonts/Arial.ttf",               "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]
FONT = "Helvetica"; FONT_B = "Helvetica-Bold"
for reg, bold in FONT_PATHS:
    if pathlib.Path(reg).exists():
        pdfmetrics.registerFont(TTFont("RF", reg))
        FONT = "RF"
        if pathlib.Path(bold).exists():
            pdfmetrics.registerFont(TTFont("RF-B", bold))
            FONT_B = "RF-B"
        print(f"Font: {pathlib.Path(reg).name}")
        break

# ── Design tokens (editorial warm) ────────────────────────────────────────────
C_BG     = colors.HexColor("#f6f2ea")
C_SURF   = colors.HexColor("#fffdf8")
C_BORDER = colors.HexColor("#e4ddd0")
C_TEXT   = colors.HexColor("#1c1a17")
C_SUB    = colors.HexColor("#8a8377")
C_XLT    = colors.HexColor("#bcb4a4")
C_COVER  = colors.HexColor("#1c1a17")
C_ACCENT = colors.HexColor("#9c4a3f")
C_GOLD   = colors.HexColor("#c9a96e")
C_WHITE  = colors.white
C_GREEN  = colors.HexColor("#5a8a5f")
C_GREEN_L= colors.HexColor("#e8f2ea")
C_AMBER  = colors.HexColor("#b87d3a")
C_AMBER_L= colors.HexColor("#f5ede0")
C_LINE   = colors.HexColor("#e4ddd0")
C_CARD   = colors.HexColor("#fffdf8")
C_CARD2  = colors.HexColor("#f6f2ea")
C_RED_L  = colors.HexColor("#f5e8e6")

W, H   = A4
MARGIN = 1.8*cm
INNER  = W - 2*MARGIN

# ── Style factory ──────────────────────────────────────────────────────────────
def sty(name="", font=None, size=10, color=None, bold=False, align=TA_LEFT,
        leading=None, sb=0, sa=4):
    fn  = FONT_B if bold else (font or FONT)
    col = color or C_TEXT
    ld  = leading or size * 1.4
    return ParagraphStyle(name or "s", fontName=fn, fontSize=size, textColor=col,
                          leading=ld, alignment=align, spaceBefore=sb, spaceAfter=sa)

ST_BODY  = sty(size=9,  color=C_TEXT, leading=13, sa=3)
ST_SMALL = sty(size=8,  color=C_SUB,  leading=11, sa=2)
ST_XSML  = sty(size=7,  color=C_SUB,  leading=10, sa=1)
ST_CAP   = sty(size=7,  color=C_SUB,  leading=10, align=TA_CENTER)

# ── Helpers ────────────────────────────────────────────────────────────────────
def thumb(path, w, h):
    try:
        img = PILImage.open(path).convert("RGB")
        sw, sh = img.size
        tr = w/h; sr = sw/sh
        if sr > tr:
            nw = int(sh*tr); img = img.crop(((sw-nw)//2,0,(sw-nw)//2+nw,sh))
        else:
            nh = int(sw/tr); img = img.crop((0,(sh-nh)//2,sw,(sh-nh)//2+nh))
        img.thumbnail((int(w*4),int(h*4)), PILImage.LANCZOS)
        buf = io.BytesIO(); img.save(buf,"JPEG",quality=82); buf.seek(0)
        ri = RLImage(buf, width=w, height=h); ri.hAlign="CENTER"; return ri
    except:
        return Spacer(w,h)

COLOR_MAP = {
    "бежевый":"#E8D9C4","beige":"#E8D9C4","кремовый":"#F5EDD8","cream":"#F5EDD8",
    "белый":"#F5F5F5","white":"#F5F5F5","молочный":"#FDF8EC","ivory":"#FDF8EC",
    "чёрный":"#1A1A1A","черный":"#1A1A1A","black":"#1A1A1A",
    "коричневый":"#7A5230","brown":"#7A5230","шоколадный":"#5C3317","chocolate":"#5C3317",
    "серый":"#9A9A9A","grey":"#9A9A9A","gray":"#9A9A9A","тёмно-серый":"#555555","charcoal":"#4A4A4A",
    "синий":"#3A5A8A","blue":"#3A5A8A","navy":"#1F2E4A","тёмно-синий":"#1F2E4A",
    "красный":"#8B2020","red":"#8B2020","бордовый":"#6B1020","burgundy":"#6B1020","wine":"#6B1020",
    "зелёный":"#3A6B3A","green":"#3A6B3A","оливковый":"#6B6B3A","olive":"#6B6B3A","хаки":"#6B6B3A",
    "карамельный":"#C07030","caramel":"#C07030","горчичный":"#B8860B","mustard":"#B8860B",
    "розовый":"#D47B8A","pink":"#D47B8A","пыльная роза":"#C8909A","dusty rose":"#C8909A",
    "лавандовый":"#8A7AA5","lavender":"#8A7AA5","фиолетовый":"#6A3A8A",
    "оранжевый":"#C86420","orange":"#C86420","терракота":"#9C4A3F","terracotta":"#9C4A3F",
    "экрю":"#F5EDD8","ecru":"#F5EDD8","песочный":"#D4B896","sand":"#D4B896",
    "золотой":"#C9A96E","gold":"#C9A96E","бронзовый":"#8B6914","bronze":"#8B6914",
}

def color_swatch(name, sw_w, sw_h):
    hex_c = "#CCCCCC"
    for key, val in COLOR_MAP.items():
        if key in name.lower(): hex_c = val; break
    try: bg = colors.HexColor(hex_c)
    except: bg = colors.HexColor("#CCCCCC")
    lum = int(hex_c[1:3],16)*.299 + int(hex_c[3:5],16)*.587 + int(hex_c[5:7],16)*.114
    tc = C_WHITE if lum < 140 else C_TEXT
    t = Table([[Paragraph(name[:9], sty(size=5,color=tc,bold=True,align=TA_CENTER))]],
              colWidths=[sw_w], rowHeights=[sw_h])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),bg),
        ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1),
        ("LEFTPADDING",(0,0),(-1,-1),1),("RIGHTPADDING",(0,0),(-1,-1),1),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    return t

def section_header(story, label, title, color=None):
    hc = color or C_COVER
    story.append(Spacer(1, 0.35*cm))
    hdr = Table([[Paragraph(
        f'<font color="#c9a96e" size="8">{label.upper()}</font>'
        f'  <font color="#ffffff" size="13">{title}</font>',
        sty(size=13, color=C_WHITE, leading=18))]], colWidths=[INNER])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),hc),
        ("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9),
        ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14)]))
    story.append(hdr)
    story.append(HRFlowable(width="100%", thickness=0.8, color=C_ACCENT, spaceAfter=7))

def sub_header(story, title, color=None):
    story.append(Paragraph(title, sty(size=8, bold=True, color=color or C_COVER, sa=5, sb=8)))

def potential_cell(text):
    t = text.lower()
    c = C_GREEN if "высок" in t else (C_AMBER if "средн" in t else C_ACCENT)
    return Paragraph(f"<b>{text}</b>", sty(size=7,color=c,bold=True,align=TA_CENTER))

def freq_cell(text):
    t = text.lower()
    c = C_GREEN if "часто" in t else (C_AMBER if "точечн" in t else C_SUB)
    return Paragraph(f"<b>{text}</b>", sty(size=8,color=c,bold=True))

def pot_bg(text):
    t = text.lower()
    if "высок" in t: return C_GREEN_L
    if "средн" in t: return C_AMBER_L
    return C_RED_L

def signal_group_block(story, gtitle, gcolor, gbg, items, fields, desc):
    if not items: return
    hdr = Table([[Paragraph(gtitle, sty(size=9,color=C_WHITE,bold=True))]],
                colWidths=[INNER])
    hdr.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),gcolor),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10)]))
    story.append(KeepTogether([hdr, Spacer(1,2),
                               Paragraph(desc, sty(size=8,color=C_SUB,sa=5))]))
    item_cells = []
    cw = (INNER-0.4*cm)/2 - 0.2*cm
    for item in items:
        brands_str = ", ".join(item.get("brands_seen",[]))
        parts = [f"<b>{item.get('element','')}</b>"]
        if brands_str:
            parts.append(f'<font color="#9c4a3f" size="7">{brands_str}</font>')
        for f in fields:
            v = item.get(f,"")
            if v: parts.append(v)
        cell = Table([[Paragraph("<br/>".join(parts), sty(size=8,color=C_TEXT,leading=12))]],
                     colWidths=[cw])
        cell.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),gbg),
            ("BOX",(0,0),(-1,-1),0.5,C_LINE),
            ("LINEBEFORE",(0,0),(0,-1),2.5,gcolor),
            ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
            ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),8)]))
        item_cells.append(cell)
    grid_rows = []
    for j in range(0, len(item_cells), 2):
        row = item_cells[j:j+2]
        if len(row)==1: row.append(Spacer(cw,1))
        grid_rows.append(row)
    if grid_rows:
        g = Table(grid_rows, colWidths=[cw]*2)
        g.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
            ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
            ("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.append(g)
    story.append(Spacer(1,0.1*cm))

# ── Canvas ─────────────────────────────────────────────────────────────────────
class FashionCanvas(pdfcanvas.Canvas):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._saved_page_states = []
        self._draw_bg()
    def _draw_bg(self):
        self.saveState(); self.setFillColor(C_BG)
        self.rect(0,0,W,H,fill=1,stroke=0); self.restoreState()
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage(); self._draw_bg()
    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state); self._draw_footer(total); super().showPage()
        super().save()
    def _draw_footer(self, total):
        pg = self._pageNumber
        if pg == 1: return
        self.saveState()
        self.setStrokeColor(C_ACCENT); self.setLineWidth(0.5)
        self.line(MARGIN, 1.2*cm, W-MARGIN, 1.2*cm)
        self.setFont(FONT, 6.5); self.setFillColor(C_SUB)
        self.drawString(MARGIN, 0.8*cm, "US RETAIL · СВОДНЫЙ ТРЕНД-ОТЧЁТ · 7 БРЕНДОВ · AW2026/27")
        self.drawRightString(W-MARGIN, 0.8*cm, f"{pg} / {total}")
        self.restoreState()

# ── Document ───────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(str(OUT_PDF), pagesize=A4,
    leftMargin=MARGIN, rightMargin=MARGIN,
    topMargin=1.0*cm, bottomMargin=1.5*cm)
story = []

cc     = REPORT.get("commercial_conclusion", {})
pal    = REPORT.get("color_palette_summary", {})
sil    = REPORT.get("silhouette_summary", {})
mkt    = REPORT.get("market_overview", {})
macro  = REPORT.get("macro_context", {})
mats   = REPORT.get("material_analysis", [])
constr = REPORT.get("construction_details", [])
compet = REPORT.get("competitive_positioning", {})
seas   = REPORT.get("seasonal_direction", {})
bstats = REPORT.get("brand_stats", {})
profiles = REPORT.get("brand_profiles", [])

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — COVER
# ══════════════════════════════════════════════════════════════════════════════
COLS_C = 7; strip_w = INNER/COLS_C; strip_h = strip_w*1.4

def make_strip(offset):
    row = []
    for bname,_,_ in BRANDS_META:
        imgs = brand_images.get(bname,[])
        idx = offset
        row.append(thumb(imgs[idx],strip_w-2,strip_h-2) if idx<len(imgs) else Spacer(strip_w,strip_h))
    t = Table([row], colWidths=[strip_w]*COLS_C, rowHeights=[strip_h])
    t.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),1),("RIGHTPADDING",(0,0),(-1,-1),1),
        ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1)])); return t

bar_cells = [Table([[Paragraph(b[0], sty(size=5,color=C_WHITE,bold=True,align=TA_CENTER))]],
             colWidths=[strip_w], rowHeights=[0.5*cm]) for b in BRANDS_META]
for i,(b,_,bc) in enumerate(BRANDS_META):
    bar_cells[i].setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor(bc)),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
brand_bar = Table([bar_cells], colWidths=[strip_w]*COLS_C, rowHeights=[0.5*cm])

cover = Table([
    [Spacer(1,0.08*cm)],
    [make_strip(0)],[Spacer(1,0.05*cm)],
    [make_strip(2)],[Spacer(1,0.05*cm)],
    [brand_bar],[Spacer(1,0.22*cm)],
    [Paragraph("US RETAIL", sty(size=9,color=C_GOLD,align=TA_CENTER,sa=2))],
    [Paragraph("СВОДНЫЙ ТРЕНД-ОТЧЁТ", sty(size=38,color=C_WHITE,align=TA_CENTER,leading=42,sa=4))],
    [Spacer(1,0.08*cm)],
    [Table([[Spacer(INNER*.35,0),HRFlowable(width=INNER*.3,thickness=1,color=C_GOLD),
             Spacer(INNER*.35,0)]],colWidths=[INNER*.35,INNER*.3,INNER*.35])],
    [Spacer(1,0.1*cm)],
    [Paragraph(f"7 брендов  ·  {REPORT.get('total_items',453)} изделий  ·  Кардиганы и трикотаж",
               sty(size=11,color=C_GOLD,align=TA_CENTER,sa=2))],
    [Spacer(1,0.12*cm)],
    [Paragraph(REPORT.get("report_date","Июнь 2026"), sty(size=8,color=C_SUB,align=TA_CENTER))],
    [Spacer(1,0.15*cm)],
], colWidths=[INNER])
cover.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),C_COVER),
    ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
    ("ALIGN",(0,0),(-1,-1),"CENTER")]))
story.append(cover); story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — ПРОФИЛИ БРЕНДОВ 1/2 (4 бренда, 2×2)
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Обзор брендов", "Профиль каждого бренда  (1 / 2)")

CARD_GAP = 0.3*cm; CARD_W2 = (INNER-CARD_GAP)/2

def brand_card(bname, bkey, bcolor_hex, card_w, n_cols=4, n_rows=2):
    try: bc = colors.HexColor(bcolor_hex)
    except: bc = C_COVER
    imgs = brand_images.get(bname, [])
    bs   = bstats.get(bname, {})
    prof = next((p for p in profiles if p.get("brand","").lower()==bname.lower()), {})

    pw=(card_w-(n_cols+1)*.1*cm)/n_cols; ph=pw*1.55
    total=n_cols*n_rows
    step=max(1,len(imgs)//total) if len(imgs)>=total else 1
    picks=[imgs[min(i*step,len(imgs)-1)] if imgs else None for i in range(total)]
    photo_rows=[]
    for r in range(n_rows):
        row=[thumb(picks[r*n_cols+c],pw-2,ph-2) if picks[r*n_cols+c] else Spacer(pw,ph)
             for c in range(n_cols)]
        photo_rows.append(row)
    ph_tbl=Table(photo_rows,colWidths=[pw]*n_cols,rowHeights=[ph]*n_rows)
    ph_tbl.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),1),("RIGHTPADDING",(0,0),(-1,-1),1),
        ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1)]))

    count=bs.get("count",len(imgs))
    hdr=Table([[Paragraph(
        f'<font color="#ffffff" size="10"><b>{bname.upper()}</b></font>'
        f'  <font color="{bcolor_hex}" size="7">{count} изд. · {prof.get("positioning","")}</font>',
        sty(size=10,color=C_WHITE,leading=14))]],colWidths=[card_w])
    hdr.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),C_COVER),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("LINEBEFORE",(0,0),(0,-1),3,bc)]))

    lines=[]
    if prof.get("signature_style"): lines.append(f'<b>Стиль:</b> {prof["signature_style"]}')
    if prof.get("key_silhouette"):  lines.append(f'<b>Силуэт:</b> {prof["key_silhouette"]}')
    if prof.get("color_story"):     lines.append(f'<b>Цвет:</b> {prof["color_story"]}')
    if prof.get("best_seller_type"):lines.append(f'<b>Хит:</b> {prof["best_seller_type"]}')
    tr=prof.get("standout_trends",[])[:3]
    if tr: lines.append(f'<font color="#9c4a3f">{"  ·  ".join(tr)}</font>')
    if prof.get("differentiation"): lines.append(f'<font color="#8a8377">{prof["differentiation"]}</font>')

    # swatches — dynamic count to fit right column
    SW_BODY_PAD = 16  # body_tbl left(10)+right(6) padding in right column
    sw_col_avail = card_w * 0.35 - SW_BODY_PAD
    n_sw = max(2, min(4, int(sw_col_avail / (0.35*cm * 1.7))))
    sw_sz = sw_col_avail / (n_sw * 1.7)
    top_cols=bs.get("colors",[])[:n_sw]
    sw_list=[]
    for cname,_ in top_cols:
        hex_c="#CCCCCC"
        for k,v in COLOR_MAP.items():
            if k in cname.lower(): hex_c=v; break
        try: cbg=colors.HexColor(hex_c)
        except: cbg=colors.HexColor("#CCCCCC")
        lum=int(hex_c[1:3],16)*.299+int(hex_c[3:5],16)*.587+int(hex_c[5:7],16)*.114
        tc=C_WHITE if lum<140 else C_TEXT
        sc=Table([[Paragraph(cname[:6],sty(size=4,color=tc,align=TA_CENTER))]],
                 colWidths=[sw_sz*1.7],rowHeights=[sw_sz])
        sc.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),cbg),
            ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1),
            ("LEFTPADDING",(0,0),(-1,-1),1),("RIGHTPADDING",(0,0),(-1,-1),1),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        sw_list.append(sc)
    while len(sw_list)<n_sw: sw_list.append(Spacer(sw_sz*1.7,sw_sz))
    sw_tbl=Table([sw_list],colWidths=[sw_sz*1.7]*n_sw)
    sw_tbl.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),1),("RIGHTPADDING",(0,0),(-1,-1),1),
        ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1)]))

    body_tbl=Table([[
        Paragraph("<br/>".join(lines),sty(size=8,color=C_TEXT,leading=12,sa=0)),
        sw_tbl
    ]],colWidths=[card_w*.65,card_w*.35])
    body_tbl.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]))

    card=Table([[hdr],[ph_tbl],[body_tbl]],colWidths=[card_w])
    card.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,C_BORDER),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
        ("BACKGROUND",(0,1),(-1,1),colors.HexColor("#f0ece4")),
        ("BACKGROUND",(0,2),(-1,2),C_CARD)]))
    return card

for row_b in [BRANDS_META[:2], BRANDS_META[2:4]]:
    cards=[brand_card(b[0],b[1],b[2],CARD_W2) for b in row_b]
    rt=Table([[cards[0], Spacer(CARD_GAP,1), cards[1]]],
             colWidths=[CARD_W2, CARD_GAP, CARD_W2])
    rt.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("VALIGN",(0,0),(-1,-1),"TOP")])); story.append(rt); story.append(Spacer(1,.2*cm))
story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — ПРОФИЛИ БРЕНДОВ 2/2 (3 бренда)
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Обзор брендов", "Профиль каждого бренда  (2 / 2)")
CARD_W3=(INNER-2*CARD_GAP)/3
cards3=[brand_card(b[0],b[1],b[2],CARD_W3,n_cols=3,n_rows=2) for b in BRANDS_META[4:]]
while len(cards3)<3: cards3.append(Spacer(CARD_W3,1))
rt3=Table([[cards3[0], Spacer(CARD_GAP,1), cards3[1], Spacer(CARD_GAP,1), cards3[2]]],
          colWidths=[CARD_W3, CARD_GAP, CARD_W3, CARD_GAP, CARD_W3])
rt3.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
    ("VALIGN",(0,0),(-1,-1),"TOP")])); story.append(rt3); story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — ОБЗОР РЫНКА
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Структура рынка", "Сегменты, ключевые наблюдения и макро-контекст")

# Key observation callout
obs=mkt.get("key_observation","")
if obs:
    ot=Table([[Paragraph(f'<b>Главное наблюдение:</b> {obs}',ST_BODY)]],colWidths=[INNER])
    ot.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f0ece4")),
        ("BOX",(0,0),(-1,-1),1.5,C_ACCENT),
        ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
    story.append(ot); story.append(Spacer(1,.12*cm))

# Segments
sub_header(story, "РЫНОЧНЫЕ СЕГМЕНТЫ")
segs=mkt.get("market_segments",[])
seg_colors_hex=[("#2C3E50","#eef0f4"),("#5a8a5f","#e8f2ea"),("#1A3A5C","#e8edf4")]
seg_rows=[]
SEG_GAP=0.25*cm; cw_seg=(INNER-2*SEG_GAP)/3
for si,seg in enumerate(segs[:3]):
    hc,lc=seg_colors_hex[si]
    try: hbg=colors.HexColor(hc); lbg=colors.HexColor(lc)
    except: hbg=C_COVER; lbg=C_CARD2
    brands_s=", ".join(seg.get("brands",[]))
    price_s=seg.get("price_point","")
    ct=Table([
        [Paragraph(seg.get("segment","").upper(),sty(size=9,color=C_WHITE,bold=True,align=TA_CENTER))],
        [Paragraph(f"<b>{brands_s}</b>",sty(size=8,color=C_TEXT,bold=True,sa=2))],
        [Paragraph(seg.get("key_trait",""),ST_SMALL)],
        [Paragraph(price_s,sty(size=7,color=C_SUB))],
    ],colWidths=[cw_seg])
    ct.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),hbg),
        ("BACKGROUND",(0,1),(-1,-1),lbg),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("BOX",(0,0),(-1,-1),.5,C_LINE)]))
    seg_rows.append(ct)
while len(seg_rows)<3: seg_rows.append(Spacer(cw_seg,1))
if segs:
    st=Table([[seg_rows[0], Spacer(SEG_GAP,1), seg_rows[1], Spacer(SEG_GAP,1), seg_rows[2]]],
             colWidths=[cw_seg,SEG_GAP,cw_seg,SEG_GAP,cw_seg])
    st.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
        ("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(st); story.append(Spacer(1,.1*cm))

# Macro context — fallback to cross_brand_trends if macro_context empty
sub_header(story, "МАКРО-КОНТЕКСТ И КЛЮЧЕВЫЕ ТРЕНДЫ")
gl=macro.get("global_trends",[])
hr=macro.get("how_market_responds","")
gap=macro.get("gaps_in_market","")
cbt=REPORT.get("cross_brand_trends",{})
# Если macro_context пуст — берём cross_brand_trends
if not gl and not hr:
    # cbt is a list of trend dicts
    cbt_list = cbt if isinstance(cbt, list) else []
    fallback_items=[item.get("element","") for item in cbt_list[:5] if item.get("element")]
    if fallback_items: gl=fallback_items
    hr=mkt.get("key_observation","")
if gl:
    n=min(len(gl),4)
    gl_cells=[[Paragraph(f"• {t}",sty(size=8,color=C_TEXT,leading=12)) for t in gl[:n]]]
    gt=Table(gl_cells,colWidths=[INNER/n]*n)
    gt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),C_CARD2),
        ("BOX",(0,0),(-1,-1),.5,C_LINE),("INNERGRID",(0,0),(-1,-1),.3,C_LINE),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(gt); story.append(Spacer(1,.06*cm))
if hr:
    story.append(Paragraph(f"<b>Ответ рынка:</b> {hr}",ST_BODY))
    story.append(Spacer(1,.04*cm))
if False and gap:  # убрано по запросу
    gt2=Table([[Paragraph(f'<b>Незанятая ниша:</b> {gap}',ST_BODY)]],colWidths=[INNER])
    gt2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#fdf6e8")),
        ("LINEBEFORE",(0,0),(0,-1),3,C_AMBER),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    story.append(gt2)
pass
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — ЦВЕТ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Цветовой анализ", "Палитра и цветовые стратегии брендов")

dom=pal.get("dominant_colors",[])
acc=pal.get("accent_colors",[])
all_c=dom+acc
SW=1.3*cm; SH=0.75*cm
# Fallback для цветов из brand_stats если color_palette_summary скуден
if len(all_c)<4:
    for bname,_,_ in BRANDS_META:
        for cname,_ in bstats.get(bname,{}).get("colors",[])[:2]:
            if cname not in all_c: all_c.append(cname)
sw_colors=all_c[:8]
sw_row=[color_swatch(c,SW,SH) for c in sw_colors]
while len(sw_row)<8: sw_row.append(Spacer(SW,SH))
sw_tbl1=Table([sw_row[:4]],colWidths=[SW]*4)
sw_tbl1.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
    ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
sw_tbl2=Table([sw_row[4:]],colWidths=[SW]*4)
sw_tbl2.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
    ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))

mood=pal.get("palette_mood","") or REPORT.get("market_stats",{}).get("palette_mood","Нейтральная теплая палитра")
hero=pal.get("hero_color","") or pal.get("dominant_colors",[""])[0] if pal.get("dominant_colors") else (all_c[0] if all_c else "бежевый")
left_col=KeepInFrame(INNER*.55, 5*cm,
          [sw_tbl1,Spacer(1,3),sw_tbl2,Spacer(1,6),Paragraph(mood,ST_SMALL)])
right_col=KeepInFrame(INNER*.45, 5*cm, [Spacer(1,1)])  # ЦВЕТ СЕЗОНА убран

ov=Table([[left_col,right_col]],colWidths=[INNER*.55,INNER*.45])
ov.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
    ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),8),
    ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
story.append(ov); story.append(Spacer(1,.12*cm))

# Color by segment
cbs=pal.get("color_by_segment",{})
if cbs:
    sub_header(story,"ЦВЕТ ПО СЕГМЕНТАМ")
    rows=[]; seg_keys=list(cbs.keys())
    for sk in seg_keys:
        clist=cbs[sk]
        sw_mini=[color_swatch(c,SW*.7,SH*.7) for c in clist[:5]]
        while len(sw_mini)<5: sw_mini.append(Spacer(SW*.7,SH*.7))
        sw_m=Table([sw_mini],colWidths=[SW*.7]*5)
        sw_m.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),1),("RIGHTPADDING",(0,0),(-1,-1),1),
            ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1)]))
        rows.append([Paragraph(f"<b>{sk}</b>",sty(size=8,color=C_TEXT,bold=True)),sw_m])
    ct=Table(rows,colWidths=[INNER*.3,INNER*.7])
    ct.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[C_CARD,C_CARD2]),
        ("BOX",(0,0),(-1,-1),.5,C_LINE),("INNERGRID",(0,0),(-1,-1),.3,C_LINE)]))
    story.append(ct)
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 6 — СИЛУЭТ И КОНСТРУКЦИЯ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Силуэт и крой", "Форма, пропорции и конструктивные детали")

# Silhouette
sub_header(story,"АНАЛИЗ СИЛУЭТОВ")
# Fallback: если silhouette_summary пуст — берём из market_overview
sil_dom=sil.get("dominant","") or mkt.get("dominant_silhouette","")
sil_sec=sil.get("secondary","") or mkt.get("dominant_style","")
sil_items=[
    ("Доминирующий", sil_dom),
    ("Вторичный",    sil_sec),
    ("Растущий",     sil.get("rising","")),
]
sbs=sil.get("by_segment",{})
for seg,sv in sbs.items():
    sil_items.append((seg,sv))
si_rows=[[Paragraph(f"<b>{k}</b>",sty(size=8,bold=True,color=C_TEXT)),
          Paragraph(v,ST_BODY)] for k,v in sil_items if v]
if si_rows:
    st=Table(si_rows,colWidths=[INNER*.28,INNER*.72])
    st.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[C_CARD,C_CARD2]),
        ("BOX",(0,0),(-1,-1),.5,C_LINE),("INNERGRID",(0,0),(-1,-1),.3,C_LINE)]))
    story.append(st)
td=sil.get("trend_direction","")
if td:
    story.append(Spacer(1,.08*cm))
    tt=Table([[Paragraph(f"<b>Тенденция:</b> {td}",ST_BODY)]],colWidths=[INNER])
    tt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),C_CARD2),
        ("LINEBEFORE",(0,0),(0,-1),3,C_ACCENT),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    story.append(tt)
story.append(Spacer(1,.12*cm))

# Construction
sub_header(story,"КОНСТРУКТИВНЫЕ ЭЛЕМЕНТЫ")
if constr:
    ch=[Paragraph(h,sty(size=7,color=C_WHITE,bold=True,align=TA_CENTER))
        for h in ["ЭЛЕМЕНТ","БРЕНДЫ","ЗНАЧИМОСТЬ","КАК АДАПТИРОВАТЬ"]]
    cr=[ch]
    crs=[("BACKGROUND",(0,0),(-1,0),C_COVER),
         ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
         ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
         ("BOX",(0,0),(-1,-1),.5,C_LINE),("INNERGRID",(0,0),(-1,-1),.3,C_LINE),
         ("VALIGN",(0,0),(-1,-1),"TOP")]
    for i,c in enumerate(constr,1):
        cr.append([
            Paragraph(f"<b>{c.get('element','')}</b>",sty(size=8,bold=True,color=C_TEXT)),
            Paragraph(", ".join(c.get("brands_using",[])),sty(size=7,color=C_ACCENT)),
            Paragraph(c.get("significance",""),ST_XSML),
            Paragraph(c.get("adapt_for_market",""),ST_XSML),
        ])
        crs.append(("BACKGROUND",(0,i),(-1,i),C_CARD if i%2 else C_CARD2))
    ct=Table(cr,colWidths=[INNER*p for p in [.22,.2,.28,.30]],repeatRows=1)
    ct.setStyle(TableStyle(crs)); story.append(ct)
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 7 — МАТЕРИАЛЫ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Материалы", "Составы и текстуры — что продаёт рынок")
# Fallback: извлекаем материалы из analysis_table
if not mats:
    seen_mat=set()
    for row in REPORT.get("analysis_table",[]):
        cat=row.get("category","").lower()
        if "матер" in cat or "ткань" in cat or "состав" in cat or "вязка" in cat or "knit" in cat:
            el=row.get("element","")
            if el and el not in seen_mat:
                seen_mat.add(el)
                mats.append({
                    "material": el,
                    "brands_using": row.get("brands_seen",[]),
                    "frequency": row.get("frequency",""),
                    "commercial_note": row.get("commercial_potential",""),
                    "styling_note": row.get("how_to_adapt",""),
                })
if mats:
    mh=[Paragraph(h,sty(size=7,color=C_WHITE,bold=True,align=TA_CENTER))
        for h in ["МАТЕРИАЛ","БРЕНДЫ","ЧАСТОТА","КОММЕРЧЕСКИЙ ПОТЕНЦИАЛ","КАК СТИЛИЗУЮТ"]]
    mr=[mh]
    mrs=[("BACKGROUND",(0,0),(-1,0),C_COVER),
         ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
         ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
         ("BOX",(0,0),(-1,-1),.5,C_LINE),("INNERGRID",(0,0),(-1,-1),.3,C_LINE),
         ("VALIGN",(0,0),(-1,-1),"TOP")]
    for i,m in enumerate(mats,1):
        mr.append([
            Paragraph(f"<b>{m.get('material','')}</b>",sty(size=8,bold=True,color=C_TEXT)),
            Paragraph(", ".join(m.get("brands_using",[])),sty(size=7,color=C_ACCENT)),
            freq_cell(m.get("frequency","")),
            Paragraph(m.get("commercial_note",""),ST_XSML),
            Paragraph(m.get("styling_note",""),ST_XSML),
        ])
        mrs.append(("BACKGROUND",(0,i),(-1,i),C_CARD if i%2 else C_CARD2))
    mt=Table(mr,colWidths=[INNER*p for p in [.18,.20,.09,.26,.27]],repeatRows=1)
    mt.setStyle(TableStyle(mrs)); story.append(mt); story.append(Spacer(1,.15*cm))

# Photo strip: one photo per brand showing texture/material
sub_header(story,"ПРИМЕРЫ ТЕКСТУР И МАТЕРИАЛОВ")
ex_w=(INNER-6*.15*cm)/7; ex_h=ex_w*1.38
ex_row=[]; ex_cap=[]
for bname,_,bc_hex in BRANDS_META:
    imgs=brand_images.get(bname,[])
    idx=min(8,len(imgs)-1) if imgs else -1
    ex_row.append(thumb(imgs[idx],ex_w-2,ex_h-2) if idx>=0 else Spacer(ex_w,ex_h))
    ex_cap.append(Paragraph(bname,sty(size=6,color=C_SUB,align=TA_CENTER)))
et=Table([ex_row,ex_cap],colWidths=[ex_w]*7)
et.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"TOP"),
    ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
    ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
story.append(et)
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 8 — ТАБЛИЦА ТРЕНД-ЭЛЕМЕНТОВ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Детальный разбор", "Таблица кросс-брендовых тренд-элементов")

HEADERS=["ЭЛЕМЕНТ","КАТ.","БРЕНДЫ","ЧАСТОТА","ПОТЕНЦИАЛ","РИСК","КАК АДАПТИРОВАТЬ"]
hr=[Paragraph(h,sty(size=6.5,color=C_WHITE,bold=True,align=TA_CENTER)) for h in HEADERS]
cw_l=[INNER*p for p in [.13,.08,.18,.08,.08,.10,.35]]
rows=[hr]
rstyles=[("BACKGROUND",(0,0),(-1,0),C_COVER),
    ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
    ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
    ("BOX",(0,0),(-1,-1),.5,C_LINE),("INNERGRID",(0,0),(-1,-1),.3,C_LINE),
    ("VALIGN",(0,0),(-1,-1),"TOP")]
for i,row in enumerate(REPORT.get("analysis_table",[]),1):
    pot=row.get("commercial_potential","")
    rows.append([
        Paragraph(f"<b>{row.get('element','')}</b>",sty(size=7.5,bold=True,color=C_TEXT)),
        Paragraph(row.get("category",""),ST_XSML),
        Paragraph(", ".join(row.get("brands_seen",[])),sty(size=6.5,color=C_ACCENT)),
        freq_cell(row.get("frequency","")),
        potential_cell(pot),
        Paragraph(row.get("adaptation_risk",""),ST_XSML),
        Paragraph(row.get("how_to_adapt",""),ST_XSML),
    ])
    rstyles.append(("BACKGROUND",(4,i),(4,i),pot_bg(pot)))
    rb=C_CARD if i%2 else C_CARD2
    rstyles.append(("BACKGROUND",(0,i),(3,i),rb))
    rstyles.append(("BACKGROUND",(5,i),(-1,i),rb))
at=Table(rows,colWidths=cw_l,repeatRows=1)
at.setStyle(TableStyle(rstyles)); story.append(at)
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 9 — СИЛЬНЫЕ СИГНАЛЫ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Сильные сигналы", "Тренды, подтверждённые несколькими брендами")
signal_group_block(story,
    "СИЛЬНЫЕ ТРЕНД-СИГНАЛЫ", C_GREEN, C_GREEN_L,
    REPORT.get("group1_strong_signals",[]),
    ["description","why_strong","market_proof"],
    "Встречаются у 2+ брендов в разных ценовых сегментах — основа ассортиментных гипотез")
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 10 — ТОЧЕЧНЫЕ СИГНАЛЫ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Точечные сигналы", "Заметные, но не массовые тренды")
signal_group_block(story,
    "ТОЧЕЧНЫЕ СИГНАЛЫ", C_AMBER, C_AMBER_L,
    REPORT.get("group2_precise_signals",[]),
    ["description","usage"],
    "Встречаются у 1-2 брендов — тестовые партии или модификации базы")
story.append(Spacer(1,.1*cm))
signal_group_block(story,
    "ИМИДЖЕВЫЕ ПРИЁМЫ", C_ACCENT, C_RED_L,
    REPORT.get("group3_image_techniques",[]),
    ["description","best_use"],
    "Сложны для прямой адаптации — используй как референс для съёмки")
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 11 — КОНКУРЕНТНОЕ ПОЗИЦИОНИРОВАНИЕ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Конкурентный анализ", "Кто чем владеет и где белые пятна")

leaders=compet.get("trend_leaders",[])
followers=compet.get("followers",[])
differ=compet.get("differentiators",[])
ws=compet.get("white_space","")

def compet_block(story, title, color, items, fields):
    if not items: return
    sub_header(story, title, color)
    for item in items:
        parts=[f"<b>{item.get('brand','')}</b>"]
        for f in fields:
            v=item.get(f,"")
            if v: parts.append(v)
        tb=Table([[Paragraph("  ".join(parts),sty(size=8,color=C_TEXT,leading=12))]],
                 colWidths=[INNER])
        tb.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),C_CARD2),
            ("LINEBEFORE",(0,0),(0,-1),2.5,color),
            ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(KeepTogether([tb,Spacer(1,3)]))

compet_block(story,"ИННОВАТОРЫ",C_GREEN,leaders,["owns","reason"])
compet_block(story,"РАННЕЕ БОЛЬШИНСТВО",C_AMBER,followers,["follows","lag"])
compet_block(story,"РАННИЕ ПОСЛЕДОВАТЕЛИ",C_ACCENT,differ,["niche","opportunity"])
if False and ws:  # Незанятая ниша убрана по запросу
    story.append(Spacer(1,.08*cm))
    wt=Table([[Paragraph(f"<b>Незанятая ниша:</b> {ws}",ST_BODY)]],colWidths=[INNER])
    wt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#fdf6e8")),
        ("BOX",(0,0),(-1,-1),1.5,C_GOLD),
        ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
    story.append(wt)

# Mini mosaic
story.append(Spacer(1,.1*cm))
sub_header(story,"ПРИМЕРЫ ОТ КАЖДОГО БРЕНДА")
ew=(INNER-6*.12*cm)/7; eh=ew*1.35
er=[]; ec=[]
for bname,_,bhex in BRANDS_META:
    imgs=brand_images.get(bname,[])
    pick=imgs[min(12,len(imgs)-1)] if imgs else None
    er.append(thumb(pick,ew-2,eh-2) if pick else Spacer(ew,eh))
    try: bc=colors.HexColor(bhex)
    except: bc=C_SUB
    ec.append(Paragraph(f'<font color="{bhex}"><b>{bname}</b></font>',
                        sty(size=6,align=TA_CENTER)))
et=Table([er,ec],colWidths=[ew]*7)
et.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"TOP"),
    ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
    ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
story.append(et)
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 12 — СЕЗОННОЕ НАПРАВЛЕНИЕ (удалено по запросу)
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 13 — ГЛАВНЫЕ ТРЕНД-СИГНАЛЫ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Ключевые выводы", "Пять главных тренд-сигналов рынка")

signals=cc.get("main_trend_signals",[])
for i,sig in enumerate(signals,1):
    name=sig.get("signal","") if isinstance(sig,dict) else str(sig)
    desc=sig.get("description","") if isinstance(sig,dict) else ""
    urgency=sig.get("urgency","") if isinstance(sig,dict) else ""

    num=Table([[Paragraph(str(i),sty(size=22,bold=True,color=C_WHITE,align=TA_CENTER))]],
              colWidths=[1.2*cm],rowHeights=[1.2*cm])
    num.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),C_COVER),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))

    urg_color=C_ACCENT if "срочн" in urgency.lower() else (C_GREEN if "сезон" in urgency.lower() else C_SUB)
    txt_items=[Paragraph(f"<b>{name}</b>",sty(size=10,bold=True,color=C_TEXT,sa=2))]
    if desc: txt_items.append(Paragraph(desc,sty(size=9,color=C_TEXT,leading=13,sa=2)))
    if urgency: txt_items.append(Paragraph(urgency,sty(size=7,color=urg_color,bold=True)))
    txt_kif=KeepInFrame(INNER-1.4*cm-14, 8*cm, txt_items)

    st=Table([[num,txt_kif]],colWidths=[1.4*cm,INNER-1.4*cm])
    st.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("BACKGROUND",(0,0),(-1,-1),C_CARD if i%2 else C_CARD2),
        ("BOX",(0,0),(-1,-1),.5,C_LINE)]))
    story.append(KeepTogether([st,Spacer(1,0.12*cm)]))
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 14 — ГИПОТЕЗЫ ДЛЯ МАРКЕТПЛЕЙСА
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Товарные гипотезы", "8 гипотез для маркетплейса — с обоснованием")

hyps=cc.get("marketplace_hypotheses",[])
for i,h in enumerate(hyps,1):
    pri=h.get("priority","").lower()
    pc=C_GREEN if "высок" in pri else C_AMBER
    try: pb_hex="#e8f2ea" if "высок" in pri else "#f5ede0"
    except: pb_hex="#f5ede0"

    id_cell=Table([
        [Paragraph(f"#{h.get('id',i)}",sty(size=14,bold=True,color=C_WHITE,align=TA_CENTER))],
        [Paragraph(h.get("priority",""),sty(size=7,color=C_WHITE,align=TA_CENTER))],
    ], colWidths=[1.3*cm])
    id_cell.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),pc),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))

    tb_str=", ".join(h.get("target_brands",[]))
    kpi=h.get("kpi","")
    rat=h.get("rationale","")
    detail_items=[
        Paragraph(f"<b>{h.get('hypothesis','')}</b>",sty(size=9,bold=True,color=C_TEXT,sa=2)),
    ]
    if rat: detail_items.append(Paragraph(rat,sty(size=8,color=C_TEXT,leading=12,sa=2)))
    detail_items.append(Paragraph(f"<b>Категория:</b> {h.get('category','')}  "
                  f"<b>Сегмент:</b> {h.get('target_segment','')}",
                  sty(size=7.5,color=C_SUB,sa=2)))
    if tb_str:
        detail_items.append(Paragraph(f"<b>Референсы:</b> {tb_str}",
                  sty(size=7,color=C_SUB,sa=0)))
    detail_kif=KeepInFrame(INNER-1.5*cm-14, 8*cm, detail_items)
    row=Table([[id_cell,detail_kif]],colWidths=[1.5*cm,INNER-1.5*cm])
    row.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor(pb_hex)),
        ("BOX",(0,0),(-1,-1),.5,C_LINE)]))
    story.append(KeepTogether([row,Spacer(1,0.1*cm)]))
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 15 — ПЛАН ДЕЙСТВИЙ + КОНТЕНТ-СОВЕТЫ
# ══════════════════════════════════════════════════════════════════════════════
section_header(story, "Для бизнеса", "План действий и советы по контенту")

sub_header(story,"ПЛАН ДЕЙСТВИЙ")
action_data=[
    ("ВНЕДРИТЬ В СЕЗОН",      C_GREEN,  C_GREEN_L, cc.get("embed_next_season",[])),
    ("ТЕСТИРОВАТЬ ОСТОРОЖНО", C_AMBER,  C_AMBER_L, cc.get("test_cautiously",[])),
    ("ТОЛЬКО ВИЗУАЛ",         C_ACCENT, C_RED_L,   cc.get("visual_reference_only",[])),
]
col3=(INNER-2*.25*cm)/3
ac_cells=[]
for atitle,ac,abg,aitems in action_data:
    cnt=[Table([[Paragraph(atitle,sty(size=7,color=C_WHITE,bold=True,align=TA_CENTER,leading=10))]],
               colWidths=[col3],rowHeights=[1.0*cm])]
    cnt[0].setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),ac),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    for it in aitems:
        cnt.append(Paragraph(f"• {it}",sty(size=8,color=C_TEXT,leading=12,sb=2)))
    cnt.append(Spacer(1,.2*cm))
    ac_cells.append(cnt)

abt=Table([[KeepInFrame(col3,10*cm,c,mode="truncate") for c in ac_cells]],
           colWidths=[col3]*3)
abt.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
    ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
    ("BACKGROUND",(0,0),(0,0),C_GREEN_L),("BACKGROUND",(1,0),(1,0),C_AMBER_L),
    ("BACKGROUND",(2,0),(2,0),C_RED_L),
    ("BOX",(0,0),(-1,-1),.5,C_LINE),("INNERGRID",(0,0),(-1,-1),.5,C_LINE)]))
story.append(abt); story.append(Spacer(1,.18*cm))

sub_header(story,"КАК СНИМАТЬ И ПРОДАВАТЬ — КАРТОЧКА И КОНТЕНТ")
tips=cc.get("card_and_content_tips","")
if tips:
    tt=Table([[Paragraph(tips,sty(size=9,color=C_TEXT,leading=14))]],colWidths=[INNER])
    tt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),C_CARD2),
        ("BOX",(0,0),(-1,-1),.5,C_BORDER),
        ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),
        ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10)]))
    story.append(tt)
story.append(CondPageBreak(5*cm))

# ══════════════════════════════════════════════════════════════════════════════
# PAGES 16+ — ФОТОКАТАЛОГ ПО БРЕНДАМ
# ══════════════════════════════════════════════════════════════════════════════
COLS_CAT=6
IMG_W=(INNER-(COLS_CAT-1)*.2*cm)/COLS_CAT; IMG_H=IMG_W*1.4

for bname,bkey,bhex in BRANDS_META:
    imgs=brand_images.get(bname,[])
    bcache_d=brand_cache.get(bname,{})
    if not imgs: continue
    try: bc=colors.HexColor(bhex)
    except: bc=C_COVER
    section_header(story,"Фотокаталог",f"Все изделия — {bname}")
    photo_rows=[]
    for i in range(0,len(imgs),COLS_CAT):
        batch=imgs[i:i+COLS_CAT]
        ri=[thumb(p,IMG_W,IMG_H) for p in batch]
        rc=[]
        for p in batch:
            d=bcache_d.get(p.name,{})
            cap=f"{d.get('silhouette','')}  {', '.join((d.get('colors') or [])[:1])}".strip()
            rc.append(Paragraph(cap,ST_CAP))
        while len(ri)<COLS_CAT: ri.append(Spacer(IMG_W,IMG_H)); rc.append(Paragraph("",ST_CAP))
        photo_rows.append(ri); photo_rows.append(rc)
    pt=Table(photo_rows,colWidths=[IMG_W]*COLS_CAT)
    pt.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
        ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
    story.append(pt); story.append(PageBreak())

# ── Build ──────────────────────────────────────────────────────────────────────
print("\n⏳ Сборка PDF...")
doc.build(story, canvasmaker=FashionCanvas)
size_kb=OUT_PDF.stat().st_size//1024
print(f"\n✅ PDF сохранён: {OUT_PDF}\n   Размер: {size_kb} KB")
