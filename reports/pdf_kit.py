"""
reports/pdf_kit.py — общий ReportLab-инструментарий отчётов (Фаза 6).

Извлечён из build_all_stores_pdf.py (fashion-ai): шрифты с кириллицей,
editorial-палитра, фабрика стилей, миниатюры, шапки секций, канвас с фоном
и футером. Используется trend_report.py; legacy_all_stores_pdf.py остаётся
самодостаточным скриптом.
"""

import io
import os
import pathlib

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (HRFlowable, Image as RLImage, Paragraph,
                                Spacer, Table, TableStyle)

# ── Шрифты (кириллица) ─────────────────────────────────────────────────────────
_FASHION_AI = pathlib.Path(os.environ.get(
    "FASHION_AI_DIR", pathlib.Path.home() / "Desktop" / "fashion-ai")).expanduser()

FONT_PATHS = [
    (str(_FASHION_AI / "fonts" / "DejaVuSans.ttf"),
     str(_FASHION_AI / "fonts" / "DejaVuSans-Bold.ttf")),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]
FONT, FONT_B = "Helvetica", "Helvetica-Bold"
for _reg, _bold in FONT_PATHS:
    if pathlib.Path(_reg).exists():
        pdfmetrics.registerFont(TTFont("RF", _reg))
        FONT = "RF"
        if pathlib.Path(_bold).exists():
            pdfmetrics.registerFont(TTFont("RF-B", _bold))
            FONT_B = "RF-B"
        break

# ── Editorial warm палитра ─────────────────────────────────────────────────────
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
C_GREEN_L = colors.HexColor("#e8f2ea")
C_AMBER  = colors.HexColor("#b87d3a")
C_AMBER_L = colors.HexColor("#f5ede0")
C_LINE   = colors.HexColor("#e4ddd0")
C_RED_L  = colors.HexColor("#f5e8e6")

# Цвета стадий (как в trends_web.STAGE_COLORS, но HexColor)
STAGE_HEX = {
    "ИННОВАТОРЫ": "#9b8cde",
    "РАННИЕ ПОСЛЕДОВАТЕЛИ": "#6ca0dc",
    "РАННЕЕ БОЛЬШИНСТВО": "#6aaa6a",
    "ПОЗДНЕЕ БОЛЬШИНСТВО": "#c9a84c",
    "СПАД": "#c96a5a",
}

W, H = A4
MARGIN = 1.8 * cm
INNER = W - 2 * MARGIN


# ── Стили ──────────────────────────────────────────────────────────────────────

def sty(name="", font=None, size=10, color=None, bold=False, align=TA_LEFT,
        leading=None, sb=0, sa=4):
    fn = FONT_B if bold else (font or FONT)
    return ParagraphStyle(name or "s", fontName=fn, fontSize=size,
                          textColor=color or C_TEXT, leading=leading or size * 1.4,
                          alignment=align, spaceBefore=sb, spaceAfter=sa)


ST_BODY = sty(size=9, color=C_TEXT, leading=13, sa=3)
ST_SMALL = sty(size=8, color=C_SUB, leading=11, sa=2)
ST_XSML = sty(size=7, color=C_SUB, leading=10, sa=1)
ST_CAP = sty(size=7, color=C_SUB, leading=10, align=TA_CENTER)


# ── Хелперы ────────────────────────────────────────────────────────────────────

def thumb(path, w, h):
    """Обрезанная по пропорции миниатюра; при ошибке — Spacer."""
    try:
        img = PILImage.open(path).convert("RGB")
        sw, sh = img.size
        tr, sr = w / h, sw / sh
        if sr > tr:
            nw = int(sh * tr)
            img = img.crop(((sw - nw) // 2, 0, (sw - nw) // 2 + nw, sh))
        else:
            nh = int(sw / tr)
            img = img.crop((0, (sh - nh) // 2, sw, (sh - nh) // 2 + nh))
        img.thumbnail((int(w * 4), int(h * 4)), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=82)
        buf.seek(0)
        ri = RLImage(buf, width=w, height=h)
        ri.hAlign = "CENTER"
        return ri
    except Exception:
        return Spacer(w, h)


def section_header(story, label, title, color=None):
    story.append(Spacer(1, 0.35 * cm))
    hdr = Table([[Paragraph(
        f'<font color="#c9a96e" size="8">{label.upper()}</font>'
        f'  <font color="#ffffff" size="13">{title}</font>',
        sty(size=13, color=C_WHITE, leading=18))]], colWidths=[INNER])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color or C_COVER),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14)]))
    story.append(hdr)
    story.append(HRFlowable(width="100%", thickness=0.8, color=C_ACCENT, spaceAfter=7))


def sub_header(story, title, color=None):
    story.append(Paragraph(title, sty(size=8, bold=True, color=color or C_COVER,
                                      sa=5, sb=8)))


def make_canvas(footer_text: str):
    """Класс канваса с фоном и футером (текст футера параметризован)."""

    class FashionCanvas(pdfcanvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._saved_page_states = []
            self._draw_bg()

        def _draw_bg(self):
            self.saveState()
            self.setFillColor(C_BG)
            self.rect(0, 0, W, H, fill=1, stroke=0)
            self.restoreState()

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()
            self._draw_bg()

        def save(self):
            total = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(total)
                super().showPage()
            super().save()

        def _draw_footer(self, total):
            pg = self._pageNumber
            if pg == 1:
                return
            self.saveState()
            self.setStrokeColor(C_ACCENT)
            self.setLineWidth(0.5)
            self.line(MARGIN, 1.2 * cm, W - MARGIN, 1.2 * cm)
            self.setFont(FONT, 6.5)
            self.setFillColor(C_SUB)
            self.drawString(MARGIN, 0.8 * cm, footer_text)
            self.drawRightString(W - MARGIN, 0.8 * cm, f"{pg} / {total}")
            self.restoreState()

    return FashionCanvas
