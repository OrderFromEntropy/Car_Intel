"""
PDF report generator — year-round, multi-hazard executive brief.

Keeps the original report's structure (executive summary, risk framework,
per-county detail, extended forecast, disclaimer footer) but generalizes it to
any hazard and adds: a season banner, a statewide hazard overview, per-county
dominant-hazard + key metrics, an activity-flag note for heat, and optional
embedding of the generated county infographic.
"""

import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, Image as RLImage)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

from .config import PDF_CONFIG, RISK_THRESHOLDS, DISCLAIMER_TEXT, COUNTIES
from . import hazards as HZ


def _md_bold(text: str) -> str:
    """Convert **markdown bold** to reportlab markup, escaping XML specials."""
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)


# Season-aware risk framework. Levels reflect the likelihood of impacts to
# building/facility operations, weighted for Texas conditions and the season.
# Season-aware risk framework. Each tier is defined by the likelihood of impact
# to building/facility operations, followed by the events that automatically land
# at that tier this season. Levels reflect Texas operational context.
def risk_framework(season: str) -> Dict:
    defs = {
        'High': 'Events with a higher likelihood of forcing facility closures, structural '
                'damage, evacuations, or personnel hazards',
        'Moderate': 'Events with a moderate likelihood of disrupting operations or creating '
                    'personnel hazards',
        'Medium': 'Events with a lower, typically localized likelihood of operational impact',
        'Low': 'Routine seasonal conditions with minimal anticipated impact to operations.',
    }
    events = {
        'Summer': {
            'High': ['Flooding', 'Hurricanes', 'Tropical Systems', 'Severe Thunderstorms', 'Tornadoes'],
            'Moderate': ['Extreme Heat', 'High Wind', 'Fire Weather (Red Flag)'],
            'Medium': ['Heat Advisories', 'Dense Fog', 'Blowing Dust', 'Air Quality'],
        },
        'Winter': {
            'High': ['Ice Storms', 'Freezing Rain', 'Hard Freezes', 'Flooding', 'Severe Thunderstorms', 'Tornadoes'],
            'Moderate': ['Extended Cold', 'High Wind', 'Winter Weather Advisories'],
            'Medium': ['Dense Fog', 'Frost', 'Air Quality'],
        },
        'Spring': {
            'High': ['Tornadoes', 'Severe Thunderstorms', 'Large Hail', 'Flooding'],
            'Moderate': ['Extreme Heat', 'High Wind', 'Fire Weather (Red Flag)'],
            'Medium': ['Dense Fog', 'Blowing Dust', 'Air Quality'],
        },
        'Fall': {
            'High': ['Tropical Systems', 'Hurricanes', 'Flooding', 'Severe Thunderstorms', 'Tornadoes'],
            'Moderate': ['Extreme Heat', 'High Wind', 'Fire Weather (Red Flag)'],
            'Medium': ['Dense Fog', 'Air Quality'],
        },
    }
    season_events = events.get(season, events['Summer'])
    out = {}
    for level in ('High', 'Moderate', 'Medium'):
        out[level] = f"{defs[level]} — {', '.join(season_events[level])}, etc."
    out['Low'] = defs['Low']
    return out


def _fmt_alert_dt(iso: str) -> Optional[str]:
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        return HZ.fmt_time(dt, "%A %-m/%-d %-I:%M %p")
    except Exception:
        return None


def _fmt_forecast_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        d = dt.day
        suffix = 'th' if 10 <= d % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')
        return dt.strftime(f"%A, %B {d}{suffix}")
    except Exception:
        return "Date unavailable"


def _fmt_timestamp(dt: datetime) -> str:
    return dt.strftime("%I:%M %p, %A, %B %d, %Y").lstrip("0")


class PDFReportGenerator:
    def __init__(self):
        ss = getSampleStyleSheet()
        self.title_style = ParagraphStyle('T', parent=ss['Heading1'],
                                          fontSize=PDF_CONFIG['font_size_title'],
                                          alignment=TA_CENTER, spaceAfter=10)
        self.subtitle_style = ParagraphStyle('ST', parent=ss['Heading2'],
                                             fontSize=PDF_CONFIG['font_size_subtitle'],
                                             alignment=TA_CENTER, textColor=colors.HexColor('#444444'),
                                             spaceAfter=6)
        self.heading_style = ParagraphStyle('H', parent=ss['Heading2'],
                                            fontSize=PDF_CONFIG['font_size_subtitle'],
                                            spaceBefore=12, spaceAfter=6)
        self.body_style = ParagraphStyle('B', parent=ss['BodyText'],
                                         fontSize=PDF_CONFIG['font_size_body'], alignment=TA_JUSTIFY)
        self.styles = ss

    def get_risk_color(self, level: str) -> colors.Color:
        r, g, b = RISK_THRESHOLDS[level]['color']
        return colors.Color(r / 255, g / 255, b / 255)

    def _footer(self, canvas, doc):
        canvas.saveState()
        style = ParagraphStyle('D', parent=self.styles['Normal'], fontSize=7,
                               textColor=colors.HexColor('#666666'), alignment=TA_JUSTIFY,
                               leftIndent=10, rightIndent=10)
        p = Paragraph(DISCLAIMER_TEXT, style)
        p.wrap(doc.width, doc.bottomMargin)
        p.drawOn(canvas, doc.leftMargin, 30)
        canvas.restoreState()

    def _consolidate_forecast(self, forecasts: List[Dict]) -> List[Dict]:
        groups = defaultdict(lambda: {'high': None, 'low': None, 'day': '', 'night': ''})
        for f in forecasts:
            date = _fmt_forecast_date(f.get('startTime', ''))
            temp = f.get('temperature', 0)
            cond = f.get('shortForecast', '')
            if f.get('isDaytime', True):
                if groups[date]['high'] is None or temp > groups[date]['high']:
                    groups[date]['high'] = temp
                groups[date]['day'] = cond
            else:
                if groups[date]['low'] is None or temp < groups[date]['low']:
                    groups[date]['low'] = temp
                groups[date]['night'] = cond
        return [{'date': d, **v} for d, v in groups.items()]

    @staticmethod
    def _highest_level(analyses: List[Dict]) -> str:
        for level in ('High', 'Moderate', 'Medium', 'Low'):
            if any(a['risk_level'] == level for a in analyses):
                return level
        return 'Low'

    def generate_pdf(self, analyses: List[Dict], executive_summary: List[str],
                     narratives: Dict[str, Dict], data_quality: Dict, season: str,
                     timestamp: datetime, filename: str,
                     infographics: Optional[Dict[str, str]] = None):
        doc = SimpleDocTemplate(filename, pagesize=letter,
                                topMargin=PDF_CONFIG['margin_top'],
                                bottomMargin=PDF_CONFIG['margin_bottom'] + 30,
                                leftMargin=PDF_CONFIG['margin_left'],
                                rightMargin=PDF_CONFIG['margin_right'])
        infographics = infographics or {}
        story = []

        story.append(Paragraph(PDF_CONFIG['title'], self.title_style))
        story.append(Paragraph(PDF_CONFIG['subtitle'], self.subtitle_style))
        story.append(Paragraph(f"<b>Season:</b> {season}", self.body_style))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(f"Best available information as of {_fmt_timestamp(timestamp)}", self.body_style))
        story.append(Spacer(1, 0.22 * inch))

        # ---- Executive summary: highlighted, bulleted, quick-hitting ----------
        accent = self.get_risk_color(self._highest_level(analyses))
        exec_heading = ParagraphStyle('EH', parent=self.heading_style, fontSize=13,
                                      textColor=accent, spaceBefore=0, spaceAfter=7)
        exec_bullet = ParagraphStyle('EB', parent=self.body_style, fontSize=11, leading=15,
                                     leftIndent=12, bulletIndent=0, spaceAfter=5,
                                     alignment=TA_LEFT, bulletFontSize=11)
        cell = [Paragraph("EXECUTIVE SUMMARY", exec_heading)]
        for b in executive_summary:
            cell.append(Paragraph(_md_bold(b), exec_bullet, bulletText='•'))
        box = Table([[cell]], colWidths=[doc.width])
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F2F4F7')),
            ('BOX', (0, 0), (-1, -1), 0.75, accent),
            ('LINEBEFORE', (0, 0), (0, -1), 5, accent),
            ('LEFTPADDING', (0, 0), (-1, -1), 16),
            ('RIGHTPADDING', (0, 0), (-1, -1), 14),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(box)
        story.append(Spacer(1, 0.22 * inch))

        # ---- Statewide hazard overview (unchanged) ----------------------------
        story.append(Paragraph("STATEWIDE HAZARD OVERVIEW", self.heading_style))
        hazard_map = defaultdict(list)
        for a in analyses:
            if a['dominant_hazard'] != 'general' or a['active_alerts']:
                hazard_map[a['dominant_hazard_name']].append(a['county'])
        if hazard_map:
            for name, counties in sorted(hazard_map.items()):
                story.append(Paragraph(f"<b>{name}:</b> {', '.join(counties)}", self.body_style))
        else:
            story.append(Paragraph("No significant hazards across monitored counties at this time.", self.body_style))
        if data_quality.get('tropical_systems'):
            names = ', '.join(s['name'] for s in data_quality['tropical_systems'])
            story.append(Paragraph(f"<b>Active Tropical Systems (NHC):</b> {names}", self.body_style))
        story.append(Spacer(1, 0.2 * inch))

        # ---- Risk framework: dynamic by season & Texas operational impact -----
        story.append(Paragraph("RISK FRAMEWORK", self.heading_style))
        story.append(Paragraph(
            "Risk levels reflect the likelihood of impacts to building and facility operations, "
            f"weighted for Texas conditions and the current season (<b>{season}</b>).",
            self.body_style))
        story.append(Spacer(1, 0.04 * inch))
        fw = risk_framework(season)
        for level in ['High', 'Moderate', 'Medium', 'Low']:
            lvl_style = ParagraphStyle('FW', parent=self.body_style,
                                       textColor=self.get_risk_color(level))
            story.append(Paragraph(f"<b>{level}:</b> {fw[level]}", lvl_style))

        # ---- Detailed county analysis: each county starts on a NEW page -------
        for a in analyses:
            story.append(PageBreak())
            county = a['county']
            story.append(Paragraph("DETAILED COUNTY ANALYSIS", self.heading_style))
            cstyle = ParagraphStyle('CH', parent=self.heading_style,
                                    textColor=self.get_risk_color(a['risk_level']), fontSize=13)
            story.append(Paragraph(f"{county.upper()} COUNTY — {a['city']}", cstyle))
            story.append(Paragraph(f"<b>Risk Level:</b> {a['risk_level']} &nbsp;|&nbsp; "
                                   f"<b>Dominant Hazard:</b> {a['dominant_hazard_name']}", self.body_style))

            # Key metrics line.
            m = a.get('metrics', {})
            metric_bits = []
            if m.get('max_temp_f') is not None: metric_bits.append(f"High {int(m['max_temp_f'])}°F")
            if m.get('min_temp_f') is not None: metric_bits.append(f"Low {int(m['min_temp_f'])}°F")
            if m.get('max_heat_index_f') is not None: metric_bits.append(f"Heat Index {int(m['max_heat_index_f'])}°F")
            if m.get('min_wind_chill_f') is not None: metric_bits.append(f"Wind Chill {int(m['min_wind_chill_f'])}°F")
            if m.get('max_wind_gust_mph'): metric_bits.append(f"Gusts {int(m['max_wind_gust_mph'])} mph")
            flag = m.get('flag_condition')
            if flag:
                metric_bits.append(f"Activity Flag: {flag['flag']}")
            if metric_bits:
                story.append(Paragraph("<b>Key Metrics:</b> " + " &nbsp;•&nbsp; ".join(metric_bits), self.body_style))
            story.append(Spacer(1, 0.08 * inch))

            # Alerts (no per-county source line; sources are cited once at end).
            if a['alerts']:
                story.append(Paragraph("<b>Active Alerts:</b>", self.body_style))
                for al in a['alerts']:
                    onset, exp = _fmt_alert_dt(al.get('onset', '')), _fmt_alert_dt(al.get('expires', ''))
                    if onset and exp:
                        story.append(Paragraph(f"• {al['event']} — {al['severity']} (Effective: {onset} – {exp})", self.body_style))
                    else:
                        story.append(Paragraph(f"• {al['event']} — {al['severity']}", self.body_style))
            else:
                story.append(Paragraph("<b>Active Alerts:</b> None", self.body_style))
            story.append(Spacer(1, 0.08 * inch))

            # Narrative.
            if county in narratives and narratives[county].get('county_narrative'):
                story.append(Paragraph(narratives[county]['county_narrative'], self.body_style))
                story.append(Spacer(1, 0.08 * inch))

            # Timeline.
            if a['timeline'].get('narrative'):
                story.append(Paragraph(f"<b>Timeline:</b> {a['timeline']['narrative']}", self.body_style))
                story.append(Spacer(1, 0.08 * inch))

            # Infrastructure impacts.
            story.append(Paragraph("<b>Anticipated Infrastructure Impacts:</b>", self.body_style))
            labels = {'public_safety': 'Public Safety', 'utilities': 'Utilities',
                      'transportation': 'Transportation', 'general': 'General'}
            any_impact = False
            for key, label in labels.items():
                for item in a['infrastructure_impacts'].get(key, []):
                    story.append(Paragraph(f"• {label}: {item}", self.body_style))
                    any_impact = True
            if not any_impact:
                story.append(Paragraph("• Minimal infrastructure impact anticipated", self.body_style))
            story.append(Spacer(1, 0.08 * inch))

            # Extended forecast with projected daily rainfall.
            if a['forecasts']:
                story.append(Paragraph("<b>Extended Forecast (with projected rainfall):</b>", self.body_style))
                precip = m.get('daily_precip_in') or {}
                for fday in self._consolidate_forecast(a['forecasts']):
                    hi = f"High {fday['high']}°F" if fday['high'] is not None else ""
                    lo = f"Low {fday['low']}°F" if fday['low'] is not None else ""
                    temp = f"{hi}, {lo}" if hi and lo else (hi or lo)
                    conds = " / ".join([c for c in (fday['day'], fday['night']) if c]) or "Conditions unavailable"
                    rain = precip.get(fday['date'])
                    rain_str = f" — Rain {rain:.2f}\"" if isinstance(rain, (int, float)) and rain >= 0.01 else " — Rain 0.00\""
                    story.append(Paragraph(f"• {fday['date']}: {temp} — {conds}{rain_str}", self.body_style))

            # Infographic on its OWN page, scaled as large as the page allows.
            if county in infographics:
                try:
                    img = RLImage(infographics[county])
                    # Fit within the frame's usable area (default frame padding is
                    # 6pt per side); leave a small safety margin.
                    avail_w = doc.width - 16
                    avail_h = doc.height - 16
                    scale = min(avail_w / img.imageWidth, avail_h / img.imageHeight)
                    img.drawWidth = img.imageWidth * scale
                    img.drawHeight = img.imageHeight * scale
                    story.append(PageBreak())
                    story.append(img)
                except Exception as e:
                    print(f"Could not embed infographic for {county}: {e}")

        # ---- Data sources: cited once for the entire report -------------------
        story.append(PageBreak())
        story.append(Paragraph("DATA SOURCES & METHODOLOGY", self.heading_style))
        story.append(Paragraph(
            "All weather data is sourced from the National Weather Service (NWS) alert and "
            "gridpoint forecast APIs and the National Hurricane Center (NHC) active-storm feed "
            "(NOAA). Heat index, wind chill, and activity-flag (estimated WBGT) values are computed "
            "from forecast data using standard meteorological formulas. Risk levels reflect the "
            "likelihood of impacts to building and facility operations, weighted for Texas "
            "conditions and the current season.", self.body_style))

        doc.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        print(f"✓ PDF report generated: {filename}")
