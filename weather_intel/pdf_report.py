"""
PDF report generator — year-round, multi-hazard executive brief.

Keeps the original report's structure (executive summary, risk framework,
per-county detail, extended forecast, disclaimer footer) but generalizes it to
any hazard and adds: a season banner, a statewide hazard overview, per-county
dominant-hazard + key metrics, an activity-flag note for heat, and optional
embedding of the generated county infographic.
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image as RLImage)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

from .config import PDF_CONFIG, RISK_THRESHOLDS, DISCLAIMER_TEXT, COUNTIES
from . import hazards as HZ


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

    def generate_pdf(self, analyses: List[Dict], executive_summary: str,
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
        story.append(Paragraph(f"<b>Season Context:</b> {season}", self.body_style))
        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(f"Best available information as of {_fmt_timestamp(timestamp)}", self.body_style))
        story.append(Spacer(1, 0.25 * inch))

        # Executive summary.
        story.append(Paragraph("EXECUTIVE SUMMARY", self.heading_style))
        story.append(Paragraph(executive_summary, self.body_style))
        story.append(Spacer(1, 0.2 * inch))

        # Statewide hazard overview.
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

        # Risk framework.
        story.append(Paragraph("RISK FRAMEWORK", self.heading_style))
        for level in ['High', 'Moderate', 'Medium', 'Low']:
            story.append(Paragraph(f"<b>{level}:</b> {RISK_THRESHOLDS[level]['description']}", self.body_style))
        story.append(Spacer(1, 0.2 * inch))

        # County detail.
        story.append(Paragraph("DETAILED COUNTY ANALYSIS", self.heading_style))
        for a in analyses:
            county = a['county']
            cstyle = ParagraphStyle('CH', parent=self.heading_style,
                                    textColor=self.get_risk_color(a['risk_level']), fontSize=12)
            story.append(Paragraph(f"{county.upper()} COUNTY — {a['region']}", cstyle))
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

            # Alerts.
            if a['alerts']:
                story.append(Paragraph("<b>Active Alerts:</b>", self.body_style))
                for al in a['alerts']:
                    onset, exp = _fmt_alert_dt(al.get('onset', '')), _fmt_alert_dt(al.get('expires', ''))
                    if onset and exp:
                        story.append(Paragraph(f"• {al['event']} — {al['severity']} (Effective: {onset} – {exp})", self.body_style))
                    else:
                        story.append(Paragraph(f"• {al['event']} — {al['severity']}", self.body_style))
                story.append(Paragraph(f"<i>Source: National Weather Service — {a['nws_office']} Office</i>", self.body_style))
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

            # Extended forecast.
            if a['forecasts']:
                story.append(Paragraph("<b>Extended Forecast:</b>", self.body_style))
                for fday in self._consolidate_forecast(a['forecasts']):
                    hi = f"High {fday['high']}°F" if fday['high'] is not None else ""
                    lo = f"Low {fday['low']}°F" if fday['low'] is not None else ""
                    temp = f"{hi}, {lo}" if hi and lo else (hi or lo)
                    conds = " / ".join([c for c in (fday['day'], fday['night']) if c]) or "Conditions unavailable"
                    story.append(Paragraph(f"• {fday['date']}: {temp} — {conds}", self.body_style))

            # Embed infographic if present.
            if county in infographics:
                try:
                    story.append(Spacer(1, 0.12 * inch))
                    img = RLImage(infographics[county])
                    max_w = doc.width
                    scale = min(1.0, max_w / img.imageWidth)
                    img.drawWidth = img.imageWidth * scale
                    img.drawHeight = img.imageHeight * scale
                    story.append(img)
                except Exception as e:
                    print(f"Could not embed infographic for {county}: {e}")

            story.append(Spacer(1, 0.2 * inch))

        # Footer.
        story.append(Spacer(1, 0.25 * inch))
        story.append(Paragraph(
            "<b>Data Sources:</b> National Weather Service (NWS) alerts and gridpoint forecasts; "
            "National Hurricane Center (NHC) active-storm feed; National Oceanic and Atmospheric "
            "Administration (NOAA). Heat index, wind chill, and activity-flag (WBGT) values are "
            "computed from forecast data using standard meteorological formulas.", self.body_style))

        doc.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        print(f"✓ PDF report generated: {filename}")
