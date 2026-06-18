"""
Infographic generator.

Produces a shareable PNG "executive report card" for a county/hazard in the
style of the reference graphic: a bold title, a themed hazard card with a color
banner and three headline metric tiles, a safety-guidance strip, and a set of
bullet points with **keywords bolded** inline.

Everything is hazard-themed: an extreme-heat card is red/orange, a winter card
is blue, a tropical card is purple, etc. (themes come from hazards.HAZARD_CATEGORIES).

Dependencies: Pillow. Fonts: DejaVu Sans (regular + bold), found at the usual
Linux path with a graceful fallback to PIL's bitmap font.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from . import hazards as HZ

# ----------------------------------------------------------------- fonts -----
_FONT_DIRS = [
    '/usr/share/fonts/truetype/dejavu',
    '/usr/share/fonts/dejavu',
    '/Library/Fonts', 'C:/Windows/Fonts',
]
_REGULAR = 'DejaVuSans.ttf'
_BOLD = 'DejaVuSans-Bold.ttf'


def _find_font(filename: str) -> Optional[str]:
    for d in _FONT_DIRS:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


class _Fonts:
    """Lazy font cache keyed on (bold, size)."""
    def __init__(self):
        self.reg_path = _find_font(_REGULAR)
        self.bold_path = _find_font(_BOLD)
        self._cache: Dict[Tuple[bool, int], object] = {}

    def get(self, size: int, bold: bool = False):
        key = (bold, size)
        if key not in self._cache:
            path = self.bold_path if bold else self.reg_path
            try:
                self._cache[key] = ImageFont.truetype(path, size) if path else ImageFont.load_default()
            except Exception:
                self._cache[key] = ImageFont.load_default()
        return self._cache[key]


# --------------------------------------------------- rich-text (bold) -------
# A "word" is a list of (text, bold) segments so that mixed-weight words such as
# "County," (bold "County" + regular ",") render with no stray internal space.
Word = List[Tuple[str, bool]]


def _parse_words(text: str) -> List[Word]:
    """Parse '**bold** normal' markup into space-delimited words of segments."""
    # Flatten to a list of (char, bold), dropping the ** toggle markers.
    chars: List[Tuple[str, bool]] = []
    for i, part in enumerate(text.split('**')):
        bold = (i % 2 == 1)
        for ch in part:
            chars.append((ch, bold))

    words: List[Word] = []
    cur: Word = []
    for ch, bold in chars:
        if ch == ' ':
            if cur:
                words.append(cur)
                cur = []
            continue
        if cur and cur[-1][1] == bold:
            cur[-1] = (cur[-1][0] + ch, bold)
        else:
            cur.append((ch, bold))
    if cur:
        words.append(cur)
    return words


class InfographicGenerator:
    # Layout constants (pixels). Fonts are large RELATIVE to the canvas width so
    # that when the image is scaled to fit a PDF page the text stays big and
    # legible. Content is kept compact so the image is width-constrained (not
    # shrunk to fit page height).
    W = 1000
    MARGIN = 54
    CARD_RADIUS = 24
    # Card geometry (shared by the size estimate in generate() and _draw_card()).
    PAD = 30
    BANNER_H = 90
    TILE_H = 190
    TIPS_H = 72
    NAVY = (15, 32, 64)
    NAVY_LIGHT = (28, 52, 92)
    WHITE = (255, 255, 255)
    INK = (17, 24, 39)
    GRAY = (110, 119, 129)
    TILE = (23, 42, 78)
    TILE_LABEL = (160, 174, 192)

    def __init__(self):
        self.available = PIL_AVAILABLE
        if PIL_AVAILABLE:
            self.fonts = _Fonts()

    # --- measurement helpers ------------------------------------------------
    def _tw(self, draw, text, font) -> float:
        return draw.textlength(text, font=font)

    def _fit_font(self, draw, text, max_w, start_size, bold=True, min_size=14):
        """Return the largest bold/regular font at which `text` fits max_w."""
        size = start_size
        while size > min_size and self._tw(draw, text, self.fonts.get(size, bold)) > max_w:
            size -= 1
        return self.fonts.get(size, bold), size

    def _word_width(self, draw, word, size) -> float:
        return sum(self._tw(draw, seg, self.fonts.get(size, bold)) for seg, bold in word)

    def _wrap(self, draw, words, max_w, size) -> List[List[Tuple[Word, float]]]:
        """Wrap words (lists of segments) into lines of (word, width) within max_w."""
        space = self._tw(draw, ' ', self.fonts.get(size))
        lines, cur, cur_w = [], [], 0.0
        for word in words:
            w = self._word_width(draw, word, size)
            add = w + (space if cur else 0)
            if cur and cur_w + add > max_w:
                lines.append(cur)
                cur, cur_w = [(word, w)], w
            else:
                cur.append((word, w))
                cur_w += add
        if cur:
            lines.append(cur)
        return lines

    def _draw_line(self, draw, x, y, line, size, color):
        space = self._tw(draw, ' ', self.fonts.get(size))
        cx = x
        for word, w in line:
            for seg, bold in word:
                draw.text((cx, y), seg, font=self.fonts.get(size, bold), fill=color)
                cx += self._tw(draw, seg, self.fonts.get(size, bold))
            cx += space

    # --- card pieces --------------------------------------------------------
    def _card_height(self, has_tips: bool) -> int:
        tips = (self.PAD + self.TIPS_H) if has_tips else self.PAD
        return self.BANNER_H + self.PAD + self.TILE_H + tips

    def _draw_card(self, img, draw, x, y, w, banner_text, banner_color,
                   tiles: List[Dict], tips: List[str]) -> int:
        """Render the hazard card; return its bottom y coordinate."""
        pad, banner_h, tile_h = self.PAD, self.BANNER_H, self.TILE_H
        tips_h = self.TIPS_H if tips else 0
        card_h = self._card_height(bool(tips))
        # Card body.
        draw.rounded_rectangle([x, y, x + w, y + card_h], radius=self.CARD_RADIUS, fill=self.NAVY)
        # Banner (rounded top, themed color).
        draw.rounded_rectangle([x, y, x + w, y + banner_h + self.CARD_RADIUS],
                               radius=self.CARD_RADIUS, fill=banner_color)
        draw.rectangle([x, y + banner_h, x + w, y + banner_h + self.CARD_RADIUS], fill=self.NAVY)
        bf, bsize = self._fit_font(draw, banner_text, w - 56, 46, bold=True, min_size=24)
        btw = self._tw(draw, banner_text, bf)
        draw.text((x + (w - btw) / 2, y + (banner_h - bsize - 8) / 2), banner_text, font=bf, fill=self.WHITE)

        # Tiles.
        ty = y + banner_h + pad
        n = max(1, len(tiles))
        gap = 26
        tw = (w - 2 * pad - (n - 1) * gap) / n
        for i, tile in enumerate(tiles):
            tx = x + pad + i * (tw + gap)
            draw.rounded_rectangle([tx, ty, tx + tw, ty + tile_h], radius=18, fill=self.TILE)
            # Accent top bar.
            draw.rounded_rectangle([tx + 24, ty + 26, tx + tw - 24, ty + 37],
                                   radius=5, fill=tuple(tile.get('bar', banner_color)))
            # Value (auto-shrink to fit).
            val = str(tile.get('value', ''))
            vsize = 74
            vf = self.fonts.get(vsize, bold=True)
            while self._tw(draw, val, vf) > tw - 40 and vsize > 28:
                vsize -= 2
                vf = self.fonts.get(vsize, bold=True)
            vtw = self._tw(draw, val, vf)
            draw.text((tx + (tw - vtw) / 2, ty + 66), val, font=vf, fill=self.WHITE)
            # Label.
            lf = self.fonts.get(24, bold=True)
            label = str(tile.get('label', ''))
            ltw = self._tw(draw, label, lf)
            draw.text((tx + (tw - ltw) / 2, ty + tile_h - 46), label, font=lf, fill=self.TILE_LABEL)

        # Tips strip.
        if tips:
            sy = ty + tile_h + pad
            draw.rounded_rectangle([x + pad, sy, x + w - pad, sy + tips_h], radius=16, fill=self.NAVY_LIGHT)
            tip_text = '    •    '.join(tips)
            tf = self.fonts.get(25, bold=True)
            # Trim tips that would overflow.
            while self._tw(draw, tip_text, tf) > w - 2 * pad - 44 and '    •    ' in tip_text:
                tips = tips[:-1]
                tip_text = '    •    '.join(tips)
            ttw = self._tw(draw, tip_text, tf)
            draw.text((x + (w - ttw) / 2, sy + (tips_h - 29) / 2), tip_text, font=tf, fill=(220, 230, 240))

        return y + card_h

    # --- public API ---------------------------------------------------------
    def generate(self, analysis: Dict, timestamp: datetime, filename: str,
                 bullets: Optional[List[str]] = None) -> Optional[str]:
        """
        Render an infographic PNG for a county analysis.

        `bullets` are strings that may contain **bold** markup; if omitted, a set
        is derived from the analysis. Returns the filename, or None if Pillow is
        unavailable.
        """
        if not self.available:
            print("Pillow not available — skipping infographic generation.")
            return None

        cat = analysis['dominant_hazard']
        theme = HZ.category_display(cat)
        banner_color = tuple(theme['banner'])
        county = analysis['county']
        bullets = bullets or self.default_bullets(analysis)

        # First pass: measure bullet block height on a scratch image.
        scratch = Image.new('RGB', (10, 10))
        sdraw = ImageDraw.Draw(scratch)
        body_w = self.W - 2 * self.MARGIN
        bullet_indent = 50
        bullet_size = 34
        line_h = 46
        bullet_gap = 20

        # Keep the bullet block compact (cap to 5) so the image stays
        # width-constrained in the PDF and the text renders large rather than
        # being shrunk to fit the page height.
        bullets = bullets[:5]
        wrapped_bullets = []
        bullets_h = 0
        for b in bullets:
            lines = self._wrap(sdraw, _parse_words(b), body_w - bullet_indent, bullet_size)
            wrapped_bullets.append(lines)
            bullets_h += len(lines) * line_h + bullet_gap

        # Resolve title font up front so the layout can reserve the right height.
        title = f"Executive Report: {theme['name']}"
        tf, tsize = self._fit_font(sdraw, title, self.W - 2 * self.MARGIN, 56, bold=True, min_size=32)

        # Compute total canvas height.
        top = 56
        title_h = tsize + 16
        subtitle_h = 48
        card_top = top + title_h + subtitle_h + 14
        card_h = self._card_height(bool(analysis.get('safety_guidance')))
        bullets_top = card_top + card_h + 40
        section_label_h = 54
        total_h = int(bullets_top + section_label_h + bullets_h + 56)

        img = Image.new('RGB', (self.W, total_h), self.WHITE)
        draw = ImageDraw.Draw(img)

        # Title + subtitle.
        ttw = self._tw(draw, title, tf)
        draw.text(((self.W - ttw) / 2, top), title, font=tf, fill=self.INK)
        sub = (f"{county} County ({analysis['city']}), TX — "
               f"{HZ.fmt_time(timestamp, '%A, %B %-d, %Y')}")
        sf = self.fonts.get(30)
        stw = self._tw(draw, sub, sf)
        draw.text(((self.W - stw) / 2, top + title_h), sub, font=sf, fill=self.GRAY)

        # Card.
        banner_text = f"{analysis['dominant_hazard_name'].upper()}  |  {county.upper()} COUNTY, TX"
        self._draw_card(img, draw, self.MARGIN, card_top, body_w, banner_text,
                        banner_color, analysis.get('metric_tiles', []),
                        analysis.get('safety_guidance', []))

        # Bullet section.
        by = bullets_top
        slf = self.fonts.get(40, bold=True)
        draw.text((self.MARGIN, by), "Key Points", font=slf, fill=self.INK)
        draw.rectangle([self.MARGIN, by + 56, self.MARGIN + 190, by + 63], fill=banner_color)
        by += section_label_h

        for lines in wrapped_bullets:
            draw.ellipse([self.MARGIN + 6, by + 14, self.MARGIN + 24, by + 32], fill=banner_color)
            for line in lines:
                self._draw_line(draw, self.MARGIN + bullet_indent, by, line, bullet_size, self.INK)
                by += line_h
            by += bullet_gap

        img.save(filename)
        print(f"✓ Infographic generated: {filename}")
        return filename

    # --- default bullet content from analysis -------------------------------
    def default_bullets(self, analysis: Dict) -> List[str]:
        """Build bolded-keyword bullet points directly from the analysis."""
        a = analysis
        m = a.get('metrics', {})
        bullets: List[str] = []

        # Bullets are intentionally short (ideally one line each) so the image
        # stays compact and the text renders large on the PDF page.

        # Lead: dominant hazard + risk level.
        bullets.append(
            f"Primary threat: **{a['dominant_hazard_name']}** — **{a['county']} County** at "
            f"**{a['risk_level']}** likelihood of operational impacts.")

        # Active alerts.
        if a['alerts']:
            names = ', '.join(sorted({al['event'] for al in a['alerts']}))
            bullets.append(f"Active alert(s): **{names}**.")
        else:
            bullets.append("**No active NWS warnings** — forecast-driven assessment.")

        # Hazard-specific quantitative bullet (concise).
        if a['dominant_hazard'] == 'extreme_heat' and m.get('max_heat_index_f'):
            flag = m.get('flag_condition')
            flag_txt = f"; **{flag['flag']} flag** conditions" if flag else ""
            bullets.append(
                f"Heat index to **{int(m['max_heat_index_f'])}°F** (high "
                f"**{int(m['max_temp_f'])}°F**){flag_txt}.")
        elif a['dominant_hazard'] == 'extreme_cold' and m.get('min_wind_chill_f') is not None:
            bullets.append(
                f"Wind chill to **{int(m['min_wind_chill_f'])}°F** (low "
                f"**{int(m['min_temp_f'])}°F**).")
        elif a['dominant_hazard'] == 'fire_weather' and m.get('min_rh') is not None:
            bullets.append(
                f"**Critical fire weather**: humidity to **{int(m['min_rh'])}%** with gusty winds.")
        elif a['dominant_hazard'] in ('severe_storm', 'tropical', 'wind') and m.get('max_wind_gust_mph'):
            bullets.append(f"Peak wind gusts to **{int(m['max_wind_gust_mph'])} mph**.")

        # Timeline.
        if a['timeline'].get('narrative'):
            bullets.append(f"**Timeline:** {a['timeline']['narrative']}.")

        # Top infrastructure impacts (public safety + utilities only here).
        impacts = a['infrastructure_impacts']
        for key, label in (('public_safety', 'Public safety'), ('utilities', 'Utilities')):
            if impacts.get(key):
                bullets.append(f"**{label}:** {impacts[key][0]}.")

        return bullets
