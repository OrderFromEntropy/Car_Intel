#!/usr/bin/env python3
"""
TEXAS YEAR-ROUND WEATHER OPERATIONAL RISK ASSESSMENT SYSTEM
Single-file build (v2.0) — copy this one file anywhere and run it.

WHAT IT DOES
  Collects National Weather Service + National Hurricane Center data, scores
  operational risk for Texas counties across EVERY season (extreme heat,
  flooding, tropical systems, severe storms/tornado, winter storms, extreme
  cold, fire weather/Red Flag, high wind, fog/dust, air quality), and produces:
    1. an executive PDF brief, and
    2. hazard-themed infographic PNGs (bold keywords, bullets, graphic).

HOW TO RUN
  python texas_weather_intel.py            # live data from NWS/NHC
  python texas_weather_intel.py --demo     # offline demo (no network needed)
  python texas_weather_intel.py --demo --no-llm
  python texas_weather_intel.py --counties Travis Harris

REQUIREMENTS
  Python 3.9+ and:
      pip install requests reportlab Pillow
  Optional (richer narratives) — a local Ollama model, e.g. gemma3:27b:
      pip install langchain-ollama
  Without Ollama the system automatically uses deterministic templates.

DESIGN PRINCIPLE
  Information only. Narrative prose contains no recommendations; the infographic
  safety strip reproduces standard NWS public messaging for the hazard.
"""

import sys
HZ = sys.modules[__name__]   # lets the original modules' "HZ.func" calls resolve



# ===========================================================================
# SECTION: config.py
# ===========================================================================

"""
Configuration for the Texas Year-Round Weather Operational Risk Assessment System.

This module centralizes every tunable value: counties monitored, API endpoints,
risk thresholds, scoring weights, PDF layout, and the visual style palette used by
the infographic generator.

DESIGN PRINCIPLE (carried over from the original winter system):
The system provides INFORMATION ONLY about anticipated operational impacts. Safety
guidance shown on infographics is reproduced verbatim from standard National Weather
Service public messaging for the relevant hazard; it is not original advice.
"""

# =============================================================================
# RISK FRAMEWORK
# =============================================================================

# Four-tier framework. Scores 0-100 map onto these bands.
RISK_THRESHOLDS = {
    'High': {
        'range': (76, 100),
        'description': 'High likelihood of operational impacts or disruptions',
        'color': (220, 53, 69),    # Red
    },
    'Moderate': {
        'range': (51, 75),
        'description': 'Moderate likelihood of operational impacts',
        'color': (255, 140, 0),    # Dark orange
    },
    'Medium': {
        'range': (26, 50),
        'description': 'Medium likelihood of operational impacts',
        'color': (255, 193, 7),    # Amber
    },
    'Low': {
        'range': (0, 25),
        'description': 'Low likelihood of operational impacts',
        'color': (25, 135, 84),    # Green
    },
}

# =============================================================================
# SCORING PARAMETERS
# =============================================================================

SCORING_CONFIG = {
    # Points awarded per active alert (capped) before severity bonuses.
    'alert_base_points': 18,
    'alert_cap': 3,
    # Severity bonuses applied per alert (uses the highest matching tier).
    'extreme_severity_bonus': 55,
    'severe_severity_bonus': 38,
    'moderate_severity_bonus': 20,
    'minor_severity_bonus': 8,
    # Urgency / certainty multipliers (NWS CAP fields).
    'immediate_urgency_bonus': 12,
    'observed_certainty_bonus': 8,
    # Maximum contribution from forecast-text keyword scanning.
    'keyword_max_contribution': 22,
}

# =============================================================================
# COUNTY CONFIGURATION
# =============================================================================
#
# Alert zones are derived automatically from FIPS as NWS *county* zones
# ("TXC" + last three FIPS digits), which is more robust than hard-coding
# forecast zones and makes adding counties trivial. Coordinates drive the
# gridpoint forecast lookup. `region` informs seasonal/hazard context.

COUNTIES = {
    'El Paso': {
        'fips': '48141', 'lat': 31.7619, 'lon': -106.4850,
        'major_highways': ['I-10'], 'nws_office': 'El Paso',
        'region': 'Far West Texas', 'coastal': False,
    },
    'Tarrant': {
        'fips': '48439', 'lat': 32.7555, 'lon': -97.3308,
        'major_highways': ['I-35W', 'I-20', 'I-30'], 'nws_office': 'Fort Worth',
        'region': 'North Texas', 'coastal': False,
    },
    'McLennan': {
        'fips': '48309', 'lat': 31.5493, 'lon': -97.1467,
        'major_highways': ['I-35'], 'nws_office': 'Fort Worth',
        'region': 'Central Texas', 'coastal': False,
    },
    'Travis': {
        'fips': '48453', 'lat': 30.2672, 'lon': -97.7431,
        'major_highways': ['I-35', 'US-183'], 'nws_office': 'Austin/San Antonio',
        'region': 'Central Texas', 'coastal': False,
    },
    'Bexar': {
        'fips': '48029', 'lat': 29.4241, 'lon': -98.4936,
        'major_highways': ['I-10', 'I-35', 'I-37'], 'nws_office': 'Austin/San Antonio',
        'region': 'South Central Texas', 'coastal': False,
    },
    'Harris': {
        'fips': '48201', 'lat': 29.7604, 'lon': -95.3698,
        'major_highways': ['I-10', 'I-45', 'I-69'], 'nws_office': 'Houston/Galveston',
        'region': 'Upper Texas Coast', 'coastal': True,
    },
    'Galveston': {
        'fips': '48167', 'lat': 29.3013, 'lon': -94.7977,
        'major_highways': ['I-45'], 'nws_office': 'Houston/Galveston',
        'region': 'Upper Texas Coast', 'coastal': True,
    },
    'Nueces': {
        'fips': '48355', 'lat': 27.8006, 'lon': -97.3964,
        'major_highways': ['I-37', 'US-181'], 'nws_office': 'Corpus Christi',
        'region': 'Coastal Bend', 'coastal': True,
    },
    'Cameron': {
        'fips': '48061', 'lat': 25.9017, 'lon': -97.4975,
        'major_highways': ['US-77', 'US-83'], 'nws_office': 'Brownsville',
        'region': 'Rio Grande Valley', 'coastal': True,
    },
}


def county_alert_zone(fips: str) -> str:
    """Return the NWS county alert zone id for a FIPS code (e.g. 48453 -> TXC453)."""
    return f"TXC{fips[-3:]}"


# =============================================================================
# API CONFIGURATION
# =============================================================================

API_CONFIG = {
    'nws_base_url': 'https://api.weather.gov',
    # National Hurricane Center current-storms feed (tropical systems).
    'nhc_current_storms_url': 'https://www.nhc.noaa.gov/CurrentStorms.json',
    'timeout_seconds': 12,
    'rate_limit_delay': 1,
    'user_agent': 'Texas State Weather Risk Assessment System (Contact: risk.management@texas.gov)',
    'forecast_days': 6,
}

# =============================================================================
# PDF CONFIGURATION
# =============================================================================

PDF_CONFIG = {
    'title': 'TEXAS WEATHER OPERATIONAL RISK ASSESSMENT',
    'subtitle': 'Year-Round Threat Intelligence — Risk Management & HR Leadership Brief',
    'font_size_title': 16,
    'font_size_subtitle': 12,
    'font_size_body': 10,
    'font_size_small': 8,
    'margin_top': 72,
    'margin_bottom': 72,
    'margin_left': 72,
    'margin_right': 72,
}

DISCLAIMER_TEXT = (
    "Disclaimer: This memo contains information intended solely for internal use by "
    "authorized personnel of the Texas Facilities Commission. It may include sensitive "
    "operational details that require discretion. Recipients are prohibited from sharing, "
    "forwarding, or disclosing any portion of this communication outside of the agency "
    "unless there are clear operational needs and prior authorizations. Unauthorized "
    "dissemination may compromise agency operations."
)

# Output directory for generated reports and infographics (local paths).
OUTPUT_DIR = 'output'


# ===========================================================================
# SECTION: hazards.py
# ===========================================================================

"""
Hazard taxonomy and meteorological calculations for year-round Texas weather.

This module is what turns the original winter-only proof of concept into a
four-season threat-intelligence engine. It defines:

  * HAZARD_CATEGORIES  - every hazard family the system understands, each with a
                         display name, theme colors (for infographics), an icon,
                         and a base severity weight.
  * EVENT_TO_CATEGORY  - maps raw NWS alert `event` strings (e.g. "Excessive Heat
                         Warning", "Flash Flood Warning", "Red Flag Warning") to a
                         category, year-round.
  * Meteorological math - heat index, wind chill, an estimated WBGT, and the
                         activity "flag condition" (white/green/yellow/red/black).
  * Seasonal helpers   - current Texas season + forecast-text hazard detection.

Nothing here makes recommendations; it classifies and quantifies conditions.
"""

import math
from datetime import datetime
from typing import Dict, List, Optional

# =============================================================================
# HAZARD CATEGORIES
# =============================================================================
# `weight` is a 0-100 ceiling expressing how operationally significant a fully
# realized event in this category typically is. `theme` colors drive infographic
# styling (banner / accent). Colors are RGB tuples.

HAZARD_CATEGORIES = {
    'extreme_heat': {
        'name': 'Extreme Heat',
        'icon': '🔥',
        'weight': 90,
        'banner': (192, 57, 43),
        'accent': (255, 138, 0),
        'season': 'summer',
    },
    'tropical': {
        'name': 'Tropical System',
        'icon': '🌀',
        'weight': 100,
        'banner': (108, 52, 131),
        'accent': (155, 89, 182),
        'season': 'summer/fall',
    },
    'flood': {
        'name': 'Flooding',
        'icon': '🌊',
        'weight': 95,
        'banner': (21, 101, 122),
        'accent': (38, 166, 154),
        'season': 'all',
    },
    'severe_storm': {
        'name': 'Severe Thunderstorm / Tornado',
        'icon': '⛈️',
        'weight': 95,
        'banner': (155, 28, 49),
        'accent': (231, 76, 60),
        'season': 'spring',
    },
    'winter_storm': {
        'name': 'Winter Storm',
        'icon': '❄️',
        'weight': 95,
        'banner': (31, 75, 140),
        'accent': (52, 152, 219),
        'season': 'winter',
    },
    'extreme_cold': {
        'name': 'Extreme Cold / Freeze',
        'icon': '🥶',
        'weight': 85,
        'banner': (40, 62, 110),
        'accent': (93, 173, 226),
        'season': 'winter',
    },
    'fire_weather': {
        'name': 'Fire Weather (Red Flag)',
        'icon': '🔥',
        'weight': 80,
        'banner': (146, 43, 33),
        'accent': (230, 126, 34),
        'season': 'spring/summer',
    },
    'wind': {
        'name': 'High Wind',
        'icon': '💨',
        'weight': 65,
        'banner': (84, 92, 99),
        'accent': (149, 165, 166),
        'season': 'all',
    },
    'fog_dust': {
        'name': 'Dense Fog / Blowing Dust',
        'icon': '🌫️',
        'weight': 50,
        'banner': (108, 122, 137),
        'accent': (178, 186, 187),
        'season': 'all',
    },
    'air_quality': {
        'name': 'Air Quality',
        'icon': '😷',
        'weight': 45,
        'banner': (125, 102, 8),
        'accent': (212, 172, 13),
        'season': 'summer',
    },
    'general': {
        'name': 'General Weather Watch',
        'icon': '🌡️',
        'weight': 20,
        'banner': (52, 73, 94),
        'accent': (127, 140, 141),
        'season': 'all',
    },
}

# =============================================================================
# NWS EVENT -> CATEGORY MAP
# =============================================================================
# Matched case-insensitively. Longer / more specific phrases are checked first
# by classify_event() so "Extreme Cold Warning" wins over a bare "cold".

EVENT_TO_CATEGORY = {
    # Heat
    'excessive heat warning': 'extreme_heat',
    'extreme heat warning': 'extreme_heat',
    'excessive heat watch': 'extreme_heat',
    'extreme heat watch': 'extreme_heat',
    'heat advisory': 'extreme_heat',
    # Tropical
    'hurricane warning': 'tropical',
    'hurricane watch': 'tropical',
    'hurricane force wind warning': 'tropical',
    'tropical storm warning': 'tropical',
    'tropical storm watch': 'tropical',
    'tropical depression': 'tropical',
    'storm surge warning': 'tropical',
    'storm surge watch': 'tropical',
    # Flood
    'flash flood warning': 'flood',
    'flash flood watch': 'flood',
    'flood warning': 'flood',
    'flood watch': 'flood',
    'flood advisory': 'flood',
    'coastal flood warning': 'flood',
    'coastal flood watch': 'flood',
    'coastal flood advisory': 'flood',
    'river flood warning': 'flood',
    # Severe convective
    'tornado warning': 'severe_storm',
    'tornado watch': 'severe_storm',
    'severe thunderstorm warning': 'severe_storm',
    'severe thunderstorm watch': 'severe_storm',
    'severe weather statement': 'severe_storm',
    # Winter
    'blizzard warning': 'winter_storm',
    'ice storm warning': 'winter_storm',
    'winter storm warning': 'winter_storm',
    'winter storm watch': 'winter_storm',
    'winter weather advisory': 'winter_storm',
    # Cold / freeze
    'extreme cold warning': 'extreme_cold',
    'cold weather advisory': 'extreme_cold',
    'wind chill warning': 'extreme_cold',
    'wind chill advisory': 'extreme_cold',
    'hard freeze warning': 'extreme_cold',
    'freeze warning': 'extreme_cold',
    'freeze watch': 'extreme_cold',
    'frost advisory': 'extreme_cold',
    # Fire
    'red flag warning': 'fire_weather',
    'fire weather watch': 'fire_weather',
    'extreme fire danger': 'fire_weather',
    # Wind
    'high wind warning': 'wind',
    'high wind watch': 'wind',
    'wind advisory': 'wind',
    # Fog / dust
    'dense fog advisory': 'fog_dust',
    'dust storm warning': 'fog_dust',
    'blowing dust advisory': 'fog_dust',
    'dust advisory': 'fog_dust',
    # Air quality
    'air quality alert': 'air_quality',
    'air stagnation advisory': 'air_quality',
}


def classify_event(event_name: str) -> str:
    """Map a raw NWS event string to a hazard category id."""
    if not event_name:
        return 'general'
    text = event_name.strip().lower()
    if text in EVENT_TO_CATEGORY:
        return EVENT_TO_CATEGORY[text]
    # Fall back to substring matching, longest key first for specificity.
    for key in sorted(EVENT_TO_CATEGORY, key=len, reverse=True):
        if key in text:
            return EVENT_TO_CATEGORY[key]
    # Last-resort keyword heuristics for unmapped phrasing.
    heuristics = [
        ('heat', 'extreme_heat'), ('hurricane', 'tropical'), ('tropical', 'tropical'),
        ('surge', 'tropical'), ('flood', 'flood'), ('tornado', 'severe_storm'),
        ('thunderstorm', 'severe_storm'), ('blizzard', 'winter_storm'),
        ('ice', 'winter_storm'), ('snow', 'winter_storm'), ('winter', 'winter_storm'),
        ('freeze', 'extreme_cold'), ('frost', 'extreme_cold'), ('chill', 'extreme_cold'),
        ('cold', 'extreme_cold'), ('red flag', 'fire_weather'), ('fire', 'fire_weather'),
        ('wind', 'wind'), ('fog', 'fog_dust'), ('dust', 'fog_dust'),
        ('air quality', 'air_quality'),
    ]
    for kw, cat in heuristics:
        if kw in text:
            return cat
    return 'general'


# =============================================================================
# METEOROLOGICAL CALCULATIONS
# =============================================================================

def heat_index_f(temp_f: float, rh_percent: float) -> float:
    """
    NWS heat index ("feels like") in degrees Fahrenheit using the Rothfusz
    regression with the standard low-end and high-RH/low-RH adjustments.
    """
    if temp_f is None or rh_percent is None:
        return temp_f if temp_f is not None else 0.0
    T, R = float(temp_f), float(rh_percent)
    # Simple formula is adequate below ~80F.
    simple = 0.5 * (T + 61.0 + ((T - 68.0) * 1.2) + (R * 0.094))
    if (simple + T) / 2 < 80:
        return round(simple, 1)
    hi = (-42.379 + 2.04901523 * T + 10.14333127 * R
          - 0.22475541 * T * R - 0.00683783 * T * T
          - 0.05481717 * R * R + 0.00122874 * T * T * R
          + 0.00085282 * T * R * R - 0.00000199 * T * T * R * R)
    if R < 13 and 80 <= T <= 112:
        hi -= ((13 - R) / 4) * ((17 - abs(T - 95)) / 17) ** 0.5
    elif R > 85 and 80 <= T <= 87:
        hi += ((R - 85) / 10) * ((87 - T) / 5)
    return round(hi, 1)


def wind_chill_f(temp_f: float, wind_mph: float) -> float:
    """NWS wind chill in degrees Fahrenheit (valid for T <= 50F, wind > 3 mph)."""
    if temp_f is None:
        return 0.0
    T = float(temp_f)
    V = float(wind_mph or 0)
    if T > 50 or V <= 3:
        return round(T, 1)
    wc = (35.74 + 0.6215 * T - 35.75 * (V ** 0.16) + 0.4275 * T * (V ** 0.16))
    return round(wc, 1)


def estimate_wbgt_f(temp_f: float, rh_percent: float, in_sun: bool = True) -> float:
    """
    Estimate Wet Bulb Globe Temperature (shade/sun) in Fahrenheit.

    True WBGT requires a black-globe sensor; this is a documented approximation
    suitable for operational flag-condition screening for outdoor workers and
    athletics. It blends a wet-bulb estimate with dry-bulb and a solar load term.
    """
    if temp_f is None or rh_percent is None:
        return temp_f if temp_f is not None else 0.0
    T = float(temp_f)
    R = max(1.0, min(100.0, float(rh_percent)))
    Tc = (T - 32.0) / 1.8
    # Stull (2011) wet-bulb temperature in degrees C (atan in radians).
    Twb_c = (Tc * math.atan(0.151977 * ((R + 8.313659) ** 0.5))
             + math.atan(Tc + R)
             - math.atan(R - 1.676331)
             + 0.00391838 * (R ** 1.5) * math.atan(0.023101 * R)
             - 4.686035)
    Twb_f = Twb_c * 1.8 + 32.0
    solar = 6.0 if in_sun else 0.0
    wbgt = 0.7 * Twb_f + 0.2 * (T + solar) + 0.1 * T
    return round(wbgt, 1)


# Activity flag system (military / OSHA / athletic), keyed on estimated WBGT (F).
FLAG_CONDITIONS = [
    ('Black', 90.0, (20, 20, 20),
     'Extreme heat stress; nonessential outdoor physical activity typically suspended'),
    ('Red', 88.0, (192, 57, 43),
     'Very high heat stress; outdoor work/exertion sharply curtailed'),
    ('Yellow', 85.0, (212, 172, 13),
     'High heat stress; frequent rest and hydration cycles warranted'),
    ('Green', 82.0, (39, 174, 96),
     'Moderate heat stress; use discretion for strenuous activity'),
    ('White', 80.0, (236, 240, 241),
     'Lower heat stress; remain alert to heat illness'),
]


def flag_condition(wbgt_f: float) -> Optional[Dict]:
    """
    Return the activity flag for an estimated WBGT, or None below 80F.

    This delivers the "red-flag / black-flag" heat-activity capability: it tells
    leadership when conditions cross outdoor-work suspension thresholds.
    """
    if wbgt_f is None:
        return None
    for name, threshold, color, meaning in FLAG_CONDITIONS:
        if wbgt_f >= threshold:
            return {'flag': name, 'threshold_f': threshold, 'color': color, 'meaning': meaning, 'wbgt_f': wbgt_f}
    return None


# =============================================================================
# SEASONAL CONTEXT
# =============================================================================

def texas_season(dt: Optional[datetime] = None) -> str:
    """Return the operational Texas season label for a date."""
    dt = dt or datetime.now()
    m = dt.month
    if m in (12, 1, 2):
        return 'Winter'
    if m in (3, 4, 5):
        return 'Spring (Severe Weather Season)'
    if m in (6, 7, 8):
        return 'Summer (Heat & Tropical Season)'
    return 'Fall (Tropical & Transition Season)'


def is_hurricane_season(dt: Optional[datetime] = None) -> bool:
    """Atlantic hurricane season runs June 1 - November 30."""
    dt = dt or datetime.now()
    return 6 <= dt.month <= 11


# Forecast-text hazard keyword bank, used when no formal alert is active but the
# narrative forecast still implies a hazard (year-round).
FORECAST_HAZARD_KEYWORDS = {
    'extreme_heat': ['excessive heat', 'dangerous heat', 'heat index', 'record heat', 'feels like 1'],
    'tropical': ['tropical', 'hurricane', 'tropical storm', 'storm surge', 'landfall'],
    'flood': ['flash flood', 'flooding', 'heavy rain', 'torrential', 'rises', 'inundation', 'turn around'],
    'severe_storm': ['tornado', 'severe thunderstorm', 'large hail', 'damaging wind', 'supercell', 'derecho'],
    'winter_storm': ['snow', 'ice storm', 'freezing rain', 'sleet', 'blizzard', 'wintry mix', 'icy'],
    'extreme_cold': ['hard freeze', 'extreme cold', 'wind chill', 'dangerously cold', 'sub-freezing', 'arctic'],
    'fire_weather': ['red flag', 'critical fire', 'fire weather', 'elevated fire', 'low humidity'],
    'wind': ['high wind', 'damaging wind', 'gusts to', 'strong wind'],
    'fog_dust': ['dense fog', 'blowing dust', 'reduced visibility', 'haboob'],
}


def detect_forecast_hazards(text: str) -> List[str]:
    """Return hazard category ids implied by free-text forecast wording."""
    found = []
    low = (text or '').lower()
    for cat, kws in FORECAST_HAZARD_KEYWORDS.items():
        if any(kw in low for kw in kws):
            found.append(cat)
    return found


def category_display(cat: str) -> Dict:
    """Safe lookup of a category's display metadata."""
    return HAZARD_CATEGORIES.get(cat, HAZARD_CATEGORIES['general'])


SEVERITY_RANK = {'extreme': 4, 'severe': 3, 'moderate': 2, 'minor': 1, 'unknown': 0}


def severity_rank(severity: str) -> int:
    return SEVERITY_RANK.get((severity or 'unknown').strip().lower(), 0)


# ===========================================================================
# SECTION: data_agent.py
# ===========================================================================

"""
Weather data collection agent.

Collects, per county:
  * Active NWS alerts (all event types, year-round) via county alert zones.
  * The NWS narrative forecast (6-day) for human-readable conditions.
  * NWS gridpoint quantitative data (max temperature, max heat index, min wind
    chill, relative humidity) so the system can compute heat/cold/flag metrics
    even when no formal alert exists.

It also fetches the National Hurricane Center active-storms feed once per run so
tropical systems threatening Texas can be surfaced.

Every method degrades gracefully: a failed request yields a status='error'
record rather than raising, so a single outage never aborts the run.
"""

import time
from typing import Dict, List, Tuple

import requests



class WeatherDataAgent:
    def __init__(self):
        self.counties = COUNTIES
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': API_CONFIG['user_agent']})

    # ------------------------------------------------------------------ alerts
    def fetch_nws_alerts(self, county_name: str) -> Dict:
        print(f"Fetching NWS alerts for {county_name}...")
        zone = county_alert_zone(self.counties[county_name]['fips'])
        url = f"{API_CONFIG['nws_base_url']}/alerts/active/zone/{zone}"
        try:
            resp = self.session.get(url, timeout=API_CONFIG['timeout_seconds'])
            if resp.status_code == 200:
                alerts = []
                for feature in resp.json().get('features', []):
                    p = feature.get('properties', {})
                    alerts.append({
                        'event': p.get('event', 'Unknown'),
                        'severity': p.get('severity', 'Unknown'),
                        'urgency': p.get('urgency', 'Unknown'),
                        'certainty': p.get('certainty', 'Unknown'),
                        'headline': p.get('headline', ''),
                        'description': p.get('description', ''),
                        'instruction': p.get('instruction', '') or '',
                        'onset': p.get('onset', ''),
                        'expires': p.get('expires', ''),
                    })
                return {'source': 'NWS', 'county': county_name, 'alerts': alerts, 'status': 'success'}
            return self._err('NWS', county_name, 'alerts', f'HTTP {resp.status_code}')
        except Exception as e:
            return self._err('NWS', county_name, 'alerts', str(e))

    # --------------------------------------------------------------- forecast
    def fetch_nws_forecast(self, county_name: str) -> Dict:
        print(f"Fetching {API_CONFIG['forecast_days']}-day forecast for {county_name}...")
        lat = self.counties[county_name]['lat']
        lon = self.counties[county_name]['lon']
        try:
            points = self.session.get(
                f"{API_CONFIG['nws_base_url']}/points/{lat},{lon}",
                timeout=API_CONFIG['timeout_seconds'])
            if points.status_code != 200:
                return self._err('NWS Forecast', county_name, 'forecasts', f'HTTP {points.status_code}')
            props = points.json()['properties']
            forecast_url = props['forecast']
            grid_url = props.get('forecastGridData')

            fc = self.session.get(forecast_url, timeout=API_CONFIG['timeout_seconds'])
            forecasts = []
            if fc.status_code == 200:
                for period in fc.json()['properties']['periods'][:API_CONFIG['forecast_days'] * 2]:
                    forecasts.append({
                        'name': period.get('name', ''),
                        'temperature': period.get('temperature', 0),
                        'temperatureUnit': period.get('temperatureUnit', 'F'),
                        'windSpeed': period.get('windSpeed', ''),
                        'windDirection': period.get('windDirection', ''),
                        'shortForecast': period.get('shortForecast', ''),
                        'detailedForecast': period.get('detailedForecast', ''),
                        'startTime': period.get('startTime', ''),
                        'isDaytime': period.get('isDaytime', True),
                        'probabilityOfPrecipitation':
                            (period.get('probabilityOfPrecipitation') or {}).get('value'),
                    })
            grid = self._extract_grid_metrics(grid_url) if grid_url else {}
            return {'source': 'NWS Forecast', 'county': county_name,
                    'forecasts': forecasts, 'grid': grid, 'status': 'success'}
        except Exception as e:
            return self._err('NWS Forecast', county_name, 'forecasts', str(e))

    def _extract_grid_metrics(self, grid_url: str) -> Dict:
        """Pull quantitative peaks from the raw gridpoint feed for heat/cold math."""
        try:
            g = self.session.get(grid_url, timeout=API_CONFIG['timeout_seconds'])
            if g.status_code != 200:
                return {}
            gp = g.json()['properties']

            def peak(field, fn):
                vals = [v.get('value') for v in gp.get(field, {}).get('values', [])
                        if v.get('value') is not None]
                return fn(vals) if vals else None

            c_to_f = lambda c: round(c * 9 / 5 + 32, 1) if c is not None else None
            return {
                'max_temp_f': c_to_f(peak('maxTemperature', max)),
                'min_temp_f': c_to_f(peak('minTemperature', min)),
                'max_heat_index_f': c_to_f(peak('apparentTemperature', max)),
                'min_wind_chill_f': c_to_f(peak('windChill', min)),
                'min_rh': peak('relativeHumidity', min),
                'max_rh': peak('relativeHumidity', max),
                'max_wind_gust_mph': (lambda v: round(v * 0.621371, 0) if v is not None else None)(
                    peak('windGust', max)),
            }
        except Exception:
            return {}

    # --------------------------------------------------------------- tropical
    def fetch_active_tropical_systems(self) -> Dict:
        """Fetch NHC active storms (basin-wide); analysis filters for Gulf/TX relevance."""
        print("Fetching National Hurricane Center active storms...")
        try:
            resp = self.session.get(API_CONFIG['nhc_current_storms_url'],
                                    timeout=API_CONFIG['timeout_seconds'])
            if resp.status_code == 200:
                data = resp.json()
                storms = []
                for s in data.get('activeStorms', []):
                    storms.append({
                        'name': s.get('name', ''),
                        'classification': s.get('classification', ''),
                        'intensity_mph': s.get('intensity', ''),
                        'pressure_mb': s.get('pressure', ''),
                        'basin': s.get('binNumber', '') or s.get('basin', ''),
                        'last_update': s.get('lastUpdate', ''),
                    })
                return {'source': 'NHC', 'storms': storms, 'status': 'success'}
            return {'source': 'NHC', 'storms': [], 'status': 'error', 'error': f'HTTP {resp.status_code}'}
        except Exception as e:
            return {'source': 'NHC', 'storms': [], 'status': 'error', 'error': str(e)}

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _err(source, county, key, msg):
        return {'source': source, 'county': county, key: [], 'status': 'error', 'error': msg}

    def gather_all_data(self) -> Tuple[List[Dict], Dict]:
        """Collect all sources for every county. Returns (records, data_quality)."""
        all_data: List[Dict] = []
        dq = {'total_requests': 0, 'successful_requests': 0, 'failed_requests': 0,
              'counties_reporting': [], 'counties_partial': [], 'counties_failed': [],
              'tropical_systems': []}

        tropical = self.fetch_active_tropical_systems()
        if tropical['status'] == 'success':
            dq['tropical_systems'] = tropical['storms']

        for county in self.counties:
            print(f"\n{'='*50}\nProcessing {county} County\n{'='*50}")
            success = 0

            alerts = self.fetch_nws_alerts(county)
            all_data.append(alerts)
            dq['total_requests'] += 1
            if alerts['status'] == 'success':
                dq['successful_requests'] += 1; success += 1
            else:
                dq['failed_requests'] += 1
            time.sleep(API_CONFIG['rate_limit_delay'])

            forecast = self.fetch_nws_forecast(county)
            all_data.append(forecast)
            dq['total_requests'] += 1
            if forecast['status'] == 'success':
                dq['successful_requests'] += 1; success += 1
            else:
                dq['failed_requests'] += 1
            time.sleep(API_CONFIG['rate_limit_delay'])

            (dq['counties_reporting'] if success == 2
             else dq['counties_partial'] if success == 1
             else dq['counties_failed']).append(county)

        return all_data, dq


# ===========================================================================
# SECTION: analysis_agent.py
# ===========================================================================

"""
Risk analysis agent — generalized for year-round, multi-hazard assessment.

For each county it:
  1. Classifies every active alert into a hazard category.
  2. Derives quantitative metrics (heat index, WBGT flag, wind chill) from grid
     and forecast data, so threats are caught even without a formal alert.
  3. Scores 0-100 using alert severity/urgency/certainty plus hazard weight and
     forecast keywords, then maps to the four-tier risk framework.
  4. Identifies the dominant hazard and builds hazard-appropriate infrastructure
     impacts, a timeline, three headline metric tiles, and NWS safety guidance.

INFORMATION ONLY: impacts describe anticipated operational effects; the safety
strip reproduces standard NWS public messaging for the hazard.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple



# Standard NWS-style safety guidance per hazard (factual public messaging).
SAFETY_GUIDANCE = {
    'extreme_heat': ['Stay hydrated', 'Limit outdoor activity midday', 'Use A/C (fans may be inadequate)',
                     'Check on vulnerable people', 'Never leave anyone in a parked vehicle'],
    'tropical': ['Follow local evacuation orders', 'Secure property and supplies', 'Avoid flooded roads',
                 'Prepare for prolonged power outages', 'Stay away from the coast and storm surge zones'],
    'flood': ['Turn Around, Don’t Drown', 'Avoid low-water crossings', 'Move to higher ground',
              'Do not drive through flood water', 'Monitor rising water levels'],
    'severe_storm': ['Move indoors away from windows', 'Have a tornado shelter plan', 'Avoid travel during storms',
                     'Watch for hail and damaging wind', 'Monitor warnings continuously'],
    'winter_storm': ['Limit road travel', 'Protect pipes from freezing', 'Keep emergency supplies on hand',
                     'Dress in layers', 'Watch for black ice on bridges'],
    'extreme_cold': ['Protect the 4 P’s: people, pets, pipes, plants', 'Dress in warm layers',
                     'Limit time outdoors', 'Use safe heating sources', 'Watch for hypothermia'],
    'fire_weather': ['Avoid outdoor burning', 'Report smoke immediately', 'Secure trailer chains and equipment',
                     'Be ready to evacuate', 'Monitor local fire conditions'],
    'wind': ['Secure loose outdoor objects', 'Use caution driving high-profile vehicles', 'Watch for downed lines',
             'Expect possible power outages'],
    'fog_dust': ['Reduce speed and use low beams', 'Increase following distance', 'Pull over if visibility is near zero'],
    'air_quality': ['Limit outdoor exertion', 'Sensitive groups stay indoors', 'Keep windows closed'],
    'general': ['Monitor official forecasts', 'Stay informed via NWS updates'],
}


class RiskAnalysisAgent:
    def __init__(self):
        self.risk_thresholds = RISK_THRESHOLDS
        self.scoring = SCORING_CONFIG

    # ------------------------------------------------------------ scoring ---
    def _alert_score(self, alert: Dict) -> int:
        s = HZ.severity_rank(alert.get('severity'))
        score = {4: self.scoring['extreme_severity_bonus'],
                 3: self.scoring['severe_severity_bonus'],
                 2: self.scoring['moderate_severity_bonus'],
                 1: self.scoring['minor_severity_bonus']}.get(s, 0)
        if (alert.get('urgency') or '').lower() == 'immediate':
            score += self.scoring['immediate_urgency_bonus']
        if (alert.get('certainty') or '').lower() == 'observed':
            score += self.scoring['observed_certainty_bonus']
        return score

    def calculate_severity_score(self, alerts: List[Dict], forecast_text: str,
                                 metrics: Dict) -> int:
        score = 0
        if alerts:
            score += min(len(alerts), self.scoring['alert_cap']) * self.scoring['alert_base_points']
            score += sum(self._alert_score(a) for a in alerts)

        # Forecast keyword signal (multi-hazard).
        kw_hits = len(HZ.detect_forecast_hazards(forecast_text))
        score += min(kw_hits * 6, self.scoring['keyword_max_contribution'])

        # Quantitative escalators that apply with or without an alert.
        hi = metrics.get('max_heat_index_f')
        if hi is not None:
            if hi >= 113: score += 30
            elif hi >= 105: score += 20
            elif hi >= 100: score += 12
        wc = metrics.get('min_wind_chill_f')
        if wc is not None:
            if wc <= 0: score += 30
            elif wc <= 15: score += 18
            elif wc <= 32: score += 8
        flag = metrics.get('flag_condition')
        if flag and flag['flag'] in ('Black', 'Red'):
            score += 10
        return min(score, 100)

    def determine_risk_level(self, score: int) -> Tuple[str, str]:
        for level, cfg in self.risk_thresholds.items():
            lo, hi = cfg['range']
            if lo <= score <= hi:
                return level, cfg['description']
        return 'Low', self.risk_thresholds['Low']['description']

    # ------------------------------------------------------------ metrics ---
    def _derive_metrics(self, forecasts: List[Dict], grid: Dict) -> Dict:
        """Compute heat index, WBGT flag, wind chill and temp extremes."""
        metrics = dict(grid) if grid else {}

        # If grid heat index missing, estimate from peak temp + min humidity.
        if metrics.get('max_heat_index_f') is None and metrics.get('max_temp_f') is not None:
            rh = metrics.get('max_rh') or 50
            metrics['max_heat_index_f'] = HZ.heat_index_f(metrics['max_temp_f'], rh)

        # Fallback temp extremes from narrative periods.
        if metrics.get('max_temp_f') is None and forecasts:
            highs = [f['temperature'] for f in forecasts if f.get('isDaytime')]
            if highs:
                metrics['max_temp_f'] = max(highs)
        if metrics.get('min_temp_f') is None and forecasts:
            lows = [f['temperature'] for f in forecasts if not f.get('isDaytime')]
            if lows:
                metrics['min_temp_f'] = min(lows)

        # WBGT-based activity flag from peak temp + humidity.
        if metrics.get('max_temp_f') is not None:
            rh = metrics.get('max_rh') or metrics.get('min_rh') or 50
            metrics['wbgt_f'] = HZ.estimate_wbgt_f(metrics['max_temp_f'], rh, in_sun=True)
            metrics['flag_condition'] = HZ.flag_condition(metrics['wbgt_f'])
        return metrics

    # --------------------------------------------------- dominant hazard ----
    def _dominant_hazard(self, alerts: List[Dict], forecast_hazards: List[str],
                         metrics: Dict, season: str) -> str:
        """Pick the hazard that should headline the brief."""
        candidates: Dict[str, float] = {}

        for a in alerts:
            cat = a['category']
            w = HZ.category_display(cat)['weight']
            candidates[cat] = max(candidates.get(cat, 0), w + HZ.severity_rank(a.get('severity')) * 5)

        for cat in forecast_hazards:
            w = HZ.category_display(cat)['weight'] * 0.4
            candidates[cat] = max(candidates.get(cat, 0), w)

        # Metric-driven candidates with no alert.
        flag = metrics.get('flag_condition')
        if flag and flag['flag'] in ('Black', 'Red', 'Yellow'):
            candidates['extreme_heat'] = max(candidates.get('extreme_heat', 0), 40)
        if metrics.get('min_wind_chill_f') is not None and metrics['min_wind_chill_f'] <= 20:
            candidates['extreme_cold'] = max(candidates.get('extreme_cold', 0), 40)

        if not candidates:
            return 'general'
        return max(candidates, key=candidates.get)

    # --------------------------------------------- infrastructure impacts ---
    def analyze_infrastructure_impacts(self, dominant: str, text: str, metrics: Dict) -> Dict:
        impacts = {'transportation': [], 'utilities': [], 'public_safety': [], 'general': []}
        low = (text or '').lower()

        if dominant == 'extreme_heat':
            impacts['utilities'].append('Electric grid strain likely from peak air-conditioning demand')
            impacts['transportation'].append('Pavement buckling and stressed vehicle cooling systems possible on major routes')
            impacts['public_safety'].append('Elevated risk of heat illness for outdoor workers and vulnerable populations')
        elif dominant == 'tropical':
            impacts['public_safety'].append('Potential evacuations, storm surge inundation, and life-threatening conditions near the coast')
            impacts['utilities'].append('Prolonged, widespread power outages anticipated from wind and flooding')
            impacts['transportation'].append('Highway evacuation congestion and road closures from flooding and debris')
        elif dominant == 'flood':
            impacts['transportation'].append('Low-water crossings and underpasses subject to rapid inundation and closure')
            impacts['public_safety'].append('Swift-water rescue risk; vehicles can be swept away in moving water')
            impacts['utilities'].append('Localized outages and water/wastewater system impacts possible')
        elif dominant == 'severe_storm':
            impacts['utilities'].append('Power outages likely from damaging wind, hail, and downed lines')
            impacts['transportation'].append('Hazardous travel and possible road blockage from debris')
            impacts['public_safety'].append('Tornado and large-hail risk to people and structures')
        elif dominant == 'winter_storm':
            impacts['transportation'].append('Hazardous, icy roads and bridges; significant travel disruption on interstates')
            impacts['utilities'].append('Power outage and water-line freeze risk from ice accumulation and cold')
        elif dominant == 'extreme_cold':
            impacts['utilities'].append('Pipe-burst risk and elevated heating demand straining the power grid')
            impacts['public_safety'].append('Hypothermia/frostbite risk; warming-center demand anticipated')
        elif dominant == 'fire_weather':
            impacts['public_safety'].append('Rapid wildfire ignition and spread potential; possible evacuations')
            impacts['transportation'].append('Smoke-related visibility reductions and potential road closures')
        elif dominant == 'wind':
            impacts['utilities'].append('Scattered power outages from downed limbs and lines')
            impacts['transportation'].append('Hazardous conditions for high-profile vehicles on exposed routes')
        elif dominant == 'fog_dust':
            impacts['transportation'].append('Sharply reduced visibility raising collision risk on highways')

        if 'power' in low or 'outage' in low:
            impacts['utilities'].append('Power outages explicitly referenced in official products')
        if not any(impacts.values()):
            impacts['general'].append('Minimal operational impact anticipated at this time')
        # De-duplicate while preserving order.
        for k in impacts:
            seen = set(); impacts[k] = [x for x in impacts[k] if not (x in seen or seen.add(x))]
        return impacts

    # --------------------------------------------------------- timeline -----
    def extract_timeline(self, forecasts: List[Dict], alerts: List[Dict]) -> Dict:
        tl = {'deterioration_start': None, 'improvement_expected': None, 'narrative': ''}
        if alerts:
            onsets = [a['onset'] for a in alerts if a.get('onset')]
            expires = [a['expires'] for a in alerts if a.get('expires')]
            if onsets: tl['deterioration_start'] = min(onsets)
            if expires: tl['improvement_expected'] = max(expires)

        parts = []
        if tl['deterioration_start']:
            try:
                dt = datetime.fromisoformat(tl['deterioration_start'].replace('Z', '+00:00'))
                parts.append(f"Conditions begin {dt.strftime('%A %-I:%M %p')}")
            except Exception:
                parts.append('Conditions developing')
        if tl['improvement_expected']:
            try:
                dt = datetime.fromisoformat(tl['improvement_expected'].replace('Z', '+00:00'))
                parts.append(f"easing by {dt.strftime('%A %-I:%M %p')}")
            except Exception:
                pass
        tl['narrative'] = ', '.join(parts) if parts else 'Timeline unavailable — monitor official updates'
        return tl

    # ------------------------------------------------ headline metric tiles -
    def build_metric_tiles(self, dominant: str, alerts: List[Dict], metrics: Dict,
                           timeline: Dict) -> List[Dict]:
        """Three tiles {value, label, bar} for the infographic, tuned per hazard."""
        accent = HZ.category_display(dominant)['accent']
        banner = HZ.category_display(dominant)['banner']
        tiles: List[Dict] = []

        def window():
            try:
                if timeline['deterioration_start'] and timeline['improvement_expected']:
                    a = datetime.fromisoformat(timeline['deterioration_start'].replace('Z', '+00:00'))
                    b = datetime.fromisoformat(timeline['improvement_expected'].replace('Z', '+00:00'))
                    return f"{a.strftime('%-I %p').upper()} – {b.strftime('%-I %p').upper()}"
            except Exception:
                pass
            return 'See forecast'

        if dominant == 'extreme_heat':
            hi = metrics.get('max_heat_index_f')
            flag = metrics.get('flag_condition')
            tiles.append({'value': f"{int(hi)}°F" if hi else 'N/A', 'label': 'PEAK HEAT INDEX', 'bar': banner})
            tiles.append({'value': f"{int(metrics['max_temp_f'])}°F" if metrics.get('max_temp_f') else 'N/A',
                          'label': 'FORECAST HIGH', 'bar': accent})
            tiles.append({'value': flag['flag'].upper() if flag else 'NONE',
                          'label': 'ACTIVITY FLAG', 'bar': flag['color'] if flag else accent})
        elif dominant == 'extreme_cold':
            tiles.append({'value': f"{int(metrics['min_wind_chill_f'])}°F" if metrics.get('min_wind_chill_f') is not None else 'N/A',
                          'label': 'MIN WIND CHILL', 'bar': banner})
            tiles.append({'value': f"{int(metrics['min_temp_f'])}°F" if metrics.get('min_temp_f') is not None else 'N/A',
                          'label': 'FORECAST LOW', 'bar': accent})
            tiles.append({'value': window(), 'label': 'IMPACT WINDOW', 'bar': accent})
        elif dominant in ('winter_storm', 'severe_storm', 'flood', 'tropical', 'fire_weather', 'wind'):
            top = max(alerts, key=lambda a: HZ.severity_rank(a.get('severity')), default=None)
            tiles.append({'value': (top['severity'].upper() if top else 'WATCH'), 'label': 'NWS SEVERITY', 'bar': banner})
            gust = metrics.get('max_wind_gust_mph')
            if dominant in ('severe_storm', 'tropical', 'wind') and gust:
                tiles.append({'value': f"{int(gust)} MPH", 'label': 'PEAK WIND GUST', 'bar': accent})
            elif dominant == 'fire_weather':
                tiles.append({'value': f"{int(metrics['min_rh'])}%" if metrics.get('min_rh') is not None else 'LOW',
                              'label': 'MIN HUMIDITY', 'bar': accent})
            else:
                tiles.append({'value': f"{len(alerts)}", 'label': 'ACTIVE ALERTS', 'bar': accent})
            tiles.append({'value': window(), 'label': 'WARNING WINDOW', 'bar': accent})
        else:
            tiles.append({'value': f"{len(alerts)}", 'label': 'ACTIVE ALERTS', 'bar': banner})
            tiles.append({'value': f"{int(metrics['max_temp_f'])}°F" if metrics.get('max_temp_f') is not None else 'N/A',
                          'label': 'FORECAST HIGH', 'bar': accent})
            tiles.append({'value': window(), 'label': 'OUTLOOK', 'bar': accent})
        return tiles[:3]

    # ----------------------------------------------------- per-county -------
    def analyze_county_data(self, county_data: List[Dict], season: str,
                            tropical_systems: List[Dict]) -> Dict:
        county_name = county_data[0]['county']
        alerts: List[Dict] = []
        forecasts: List[Dict] = []
        grid: Dict = {}
        text_parts: List[str] = []

        for d in county_data:
            if d['source'] == 'NWS':
                for a in d.get('alerts', []):
                    a['category'] = HZ.classify_event(a['event'])
                    alerts.append(a)
                    text_parts.append(f"{a['event']} {a['headline']} {a['description']}")
            elif d['source'] == 'NWS Forecast':
                forecasts = d.get('forecasts', [])
                grid = d.get('grid', {}) or {}
                text_parts.extend(f.get('detailedForecast', '') for f in forecasts)

        all_text = ' '.join(text_parts)
        metrics = self._derive_metrics(forecasts, grid)
        forecast_hazards = HZ.detect_forecast_hazards(all_text)
        score = self.calculate_severity_score(alerts, all_text, metrics)
        risk_level, risk_desc = self.determine_risk_level(score)
        dominant = self._dominant_hazard(alerts, forecast_hazards, metrics, season)
        infrastructure = self.analyze_infrastructure_impacts(dominant, all_text, metrics)
        timeline = self.extract_timeline(forecasts, alerts)
        tiles = self.build_metric_tiles(dominant, alerts, metrics, timeline)

        cfg = COUNTIES[county_name]
        # Coastal counties get a tropical nudge when systems are active in-season.
        coastal_tropical = bool(tropical_systems) and cfg['coastal']

        return {
            'county': county_name,
            'region': cfg['region'],
            'coastal': cfg['coastal'],
            'risk_level': risk_level,
            'risk_description': risk_desc,
            'severity_score': score,
            'active_alerts': len(alerts),
            'alerts': alerts,
            'forecasts': forecasts,
            'metrics': metrics,
            'dominant_hazard': dominant,
            'dominant_hazard_name': HZ.category_display(dominant)['name'],
            'hazards_present': sorted({a['category'] for a in alerts} | set(forecast_hazards)),
            'infrastructure_impacts': infrastructure,
            'timeline': timeline,
            'metric_tiles': tiles,
            'safety_guidance': SAFETY_GUIDANCE.get(dominant, SAFETY_GUIDANCE['general']),
            'coastal_tropical_watch': coastal_tropical,
            'major_highways': cfg['major_highways'],
            'nws_office': cfg['nws_office'],
        }

    def analyze_all_counties(self, all_data: List[Dict], season: str,
                             tropical_systems: Optional[List[Dict]] = None) -> List[Dict]:
        grouped: Dict[str, List[Dict]] = {}
        for d in all_data:
            grouped.setdefault(d['county'], []).append(d)
        analyses = [self.analyze_county_data(cd, season, tropical_systems or [])
                    for cd in grouped.values()]
        analyses.sort(key=lambda x: x['severity_score'], reverse=True)
        return analyses


# ===========================================================================
# SECTION: narrative_agent.py
# ===========================================================================

"""
Narrative generation agent.

Uses a local Ollama LLM when available to write the executive summary and
per-county narratives, with deterministic template fallbacks so the system
always produces output. Prompts are hazard-agnostic and explicitly year-round.

INFORMATION ONLY: prompts forbid recommendations/advice in the narrative prose.
"""

import json
from typing import Dict, List

try:
    from langchain_ollama import OllamaLLM
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False



PROMPT_EXECUTIVE_SUMMARY = """You are generating an executive summary for Texas state leadership about active weather threats. This is a YEAR-ROUND system: hazards may include extreme heat, flooding, tropical systems (hurricanes/tropical storms/depressions), severe thunderstorms/tornadoes, winter storms, extreme cold, fire weather (red flag), high wind, and more.

INPUT DATA (JSON):
{json_data}

Write ONE paragraph (4-6 sentences) giving a 30,000-foot view:
1. The overall threat level across Texas and the current season context.
2. The specific dominant hazards present (name them explicitly).
3. Which counties/regions face the highest likelihood of operational impacts.
4. Key infrastructure concerns (power grid, highways, water systems, coastal/evacuation if tropical).

Lead with the most widespread/severe hazard. Be concise and factual. Do NOT include recommendations, advice, or action items. Output only the paragraph text."""

PROMPT_COUNTY_NARRATIVE = """You are describing the weather situation for one Texas county as part of a year-round threat assessment.

INPUT DATA (JSON):
{json_data}

Write 2-3 sentences describing: the active alerts and their severity, the dominant hazard and key metrics (e.g. heat index, wind chill, wind gusts), and the temperature/condition trend. Be factual and informational. Do NOT include advice or recommendations. Output only the narrative text."""


class NarrativeGenerationAgent:
    def __init__(self, ollama_model: str = "gemma3:27b"):
        self.ollama_model = ollama_model
        self.llm_available = False
        if ollama_model == '__disabled__':
            print("LLM disabled (--no-llm) — using template narratives")
        elif LANGCHAIN_AVAILABLE:
            try:
                self.llm = OllamaLLM(model=ollama_model)
                self.llm_available = True
                print("✓ Langchain-Ollama LLM initialized")
            except Exception as e:
                print(f"Warning: could not initialize Ollama: {e}")
        else:
            print("langchain-ollama not available — using template narratives")

    def call_llm(self, prompt: str, data_json: str) -> str:
        return self.llm.invoke(prompt.format(json_data=data_json)).strip()

    # ------------------------------------------------------ executive summary
    def generate_executive_summary(self, analyses: List[Dict], season: str,
                                   tropical_systems: List[Dict]) -> str:
        print("Generating executive summary...")
        risk_dist = {'High': [], 'Moderate': [], 'Medium': [], 'Low': []}
        for a in analyses:
            risk_dist[a['risk_level']].append(a['county'])

        hazard_counties: Dict[str, List[str]] = {}
        for a in analyses:
            hazard_counties.setdefault(a['dominant_hazard_name'], []).append(a['county'])

        input_data = {
            'season': season,
            'risk_distribution': risk_dist,
            'highest_risk_counties': [a['county'] for a in analyses[:3]],
            'dominant_hazards_by_county': hazard_counties,
            'active_tropical_systems': [s['name'] for s in tropical_systems] if tropical_systems else [],
            'total_counties': len(analyses),
        }
        data_json = json.dumps(input_data, indent=2)

        if self.llm_available:
            try:
                return self.call_llm(PROMPT_EXECUTIVE_SUMMARY, data_json)
            except Exception as e:
                print(f"LLM call failed: {e}; using template")
        return self._template_summary(risk_dist, hazard_counties, season, tropical_systems)

    def _template_summary(self, risk_dist, hazard_counties, season, tropical_systems) -> str:
        parts = [f"Current season: {season}."]
        if risk_dist['High']:
            parts.append(f"High likelihood of operational impacts across {', '.join(risk_dist['High'])} "
                         f"{'County' if len(risk_dist['High']) == 1 else 'Counties'}.")
        elif risk_dist['Moderate']:
            parts.append(f"Moderate likelihood of operational impacts developing across {', '.join(risk_dist['Moderate'])}.")
        else:
            parts.append("Weather conditions being monitored statewide with limited operational impacts anticipated.")

        hz = [f"{name} ({', '.join(cs)})" for name, cs in hazard_counties.items()
              if name != 'General Weather Watch']
        if hz:
            parts.append("Dominant hazards: " + "; ".join(hz) + ".")
        if tropical_systems:
            parts.append("Active tropical system(s) in the basin: " +
                         ", ".join(s['name'] for s in tropical_systems) +
                         "; coastal counties under heightened monitoring.")
        parts.append("Anticipated infrastructure concerns include the power grid, major highway corridors, and water systems where applicable.")
        return " ".join(parts)

    # ------------------------------------------------------ county narrative
    def generate_county_narrative(self, analysis: Dict) -> str:
        m = analysis.get('metrics', {})
        data = {
            'county': analysis['county'],
            'region': analysis['region'],
            'risk_level': analysis['risk_level'],
            'dominant_hazard': analysis['dominant_hazard_name'],
            'active_alerts': [{'event': a['event'], 'severity': a['severity']} for a in analysis['alerts']],
            'metrics': {k: m.get(k) for k in
                        ('max_temp_f', 'min_temp_f', 'max_heat_index_f', 'min_wind_chill_f',
                         'max_wind_gust_mph', 'min_rh')},
            'flag_condition': (m.get('flag_condition') or {}).get('flag'),
            'forecasts': [{'name': f['name'], 'temperature': f['temperature'],
                           'shortForecast': f['shortForecast']} for f in analysis['forecasts'][:3]],
        }
        if self.llm_available:
            try:
                return self.call_llm(PROMPT_COUNTY_NARRATIVE, json.dumps(data, indent=2))
            except Exception as e:
                print(f"LLM call failed for {analysis['county']}: {e}")
        return self._template_county_narrative(analysis)

    def _template_county_narrative(self, a: Dict) -> str:
        m = a.get('metrics', {})
        bits = [f"{a['county']} County ({a['region']}) is at {a['risk_level']} likelihood of operational "
                f"impacts, with {a['dominant_hazard_name']} as the dominant hazard."]
        if a['alerts']:
            top = max(a['alerts'], key=lambda x: HZ.severity_rank(x.get('severity')))
            bits.append(f"{a['active_alerts']} active alert(s) in effect, including a "
                        f"{top['severity']}-severity {top['event']}.")
        else:
            bits.append("No active alerts; assessment is forecast-driven.")
        if a['dominant_hazard'] == 'extreme_heat' and m.get('max_heat_index_f'):
            bits.append(f"Heat index peaks near {int(m['max_heat_index_f'])}°F.")
        elif a['dominant_hazard'] == 'extreme_cold' and m.get('min_wind_chill_f') is not None:
            bits.append(f"Wind chills bottom out near {int(m['min_wind_chill_f'])}°F.")
        return " ".join(bits)


# ===========================================================================
# SECTION: infographic.py
# ===========================================================================

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
    # Layout constants (pixels).
    W = 1100
    MARGIN = 70
    CARD_RADIUS = 18
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
    def _draw_card(self, img, draw, x, y, w, banner_text, banner_color,
                   tiles: List[Dict], tips: List[str]) -> int:
        """Render the hazard card; return its bottom y coordinate."""
        pad = 26
        banner_h = 64
        tile_h = 150
        tips_h = 56 if tips else 0
        card_h = banner_h + pad + tile_h + (pad + tips_h if tips else pad)
        # Card body.
        draw.rounded_rectangle([x, y, x + w, y + card_h], radius=self.CARD_RADIUS, fill=self.NAVY)
        # Banner (rounded top, themed color).
        draw.rounded_rectangle([x, y, x + w, y + banner_h + self.CARD_RADIUS],
                               radius=self.CARD_RADIUS, fill=banner_color)
        draw.rectangle([x, y + banner_h, x + w, y + banner_h + self.CARD_RADIUS], fill=self.NAVY)
        bf, bsize = self._fit_font(draw, banner_text, w - 44, 30, bold=True, min_size=16)
        btw = self._tw(draw, banner_text, bf)
        draw.text((x + (w - btw) / 2, y + (banner_h - bsize - 6) / 2), banner_text, font=bf, fill=self.WHITE)

        # Tiles.
        ty = y + banner_h + pad
        n = max(1, len(tiles))
        gap = 20
        tw = (w - 2 * pad - (n - 1) * gap) / n
        for i, tile in enumerate(tiles):
            tx = x + pad + i * (tw + gap)
            draw.rounded_rectangle([tx, ty, tx + tw, ty + tile_h], radius=12, fill=self.TILE)
            # Accent top bar.
            draw.rounded_rectangle([tx + 16, ty + 16, tx + tw - 16, ty + 22],
                                   radius=3, fill=tuple(tile.get('bar', banner_color)))
            # Value (auto-shrink to fit).
            val = str(tile.get('value', ''))
            vsize = 46
            vf = self.fonts.get(vsize, bold=True)
            while self._tw(draw, val, vf) > tw - 28 and vsize > 20:
                vsize -= 2
                vf = self.fonts.get(vsize, bold=True)
            vtw = self._tw(draw, val, vf)
            draw.text((tx + (tw - vtw) / 2, ty + 48), val, font=vf, fill=self.WHITE)
            # Label.
            lf = self.fonts.get(16, bold=True)
            label = str(tile.get('label', ''))
            ltw = self._tw(draw, label, lf)
            draw.text((tx + (tw - ltw) / 2, ty + tile_h - 36), label, font=lf, fill=self.TILE_LABEL)

        # Tips strip.
        if tips:
            sy = ty + tile_h + pad
            draw.rounded_rectangle([x + pad, sy, x + w - pad, sy + tips_h], radius=10, fill=self.NAVY_LIGHT)
            tip_text = '   •   '.join(tips)
            tf = self.fonts.get(17)
            # Trim tips that would overflow.
            while self._tw(draw, tip_text, tf) > w - 2 * pad - 30 and '   •   ' in tip_text:
                tips = tips[:-1]
                tip_text = '   •   '.join(tips)
            ttw = self._tw(draw, tip_text, tf)
            draw.text((x + (w - ttw) / 2, sy + (tips_h - 21) / 2), tip_text, font=tf, fill=(214, 224, 235))

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
        bullet_indent = 34
        line_h = 30
        bullet_gap = 14
        bullet_size = 19

        wrapped_bullets = []
        bullets_h = 0
        for b in bullets:
            lines = self._wrap(sdraw, _parse_words(b), body_w - bullet_indent, bullet_size)
            wrapped_bullets.append(lines)
            bullets_h += len(lines) * line_h + bullet_gap

        # Compute total canvas height.
        top = 56
        title_h = 54
        subtitle_h = 40
        card_top = top + title_h + subtitle_h + 18
        # Card height is computed inside _draw_card; estimate to size canvas.
        banner_h, tile_h, pad = 64, 150, 26
        tips_h = 56 if analysis.get('safety_guidance') else 0
        card_h = banner_h + pad + tile_h + (pad + tips_h if tips_h else pad)
        bullets_top = card_top + card_h + 40
        section_label_h = 40
        total_h = int(bullets_top + section_label_h + bullets_h + 60)

        img = Image.new('RGB', (self.W, total_h), self.WHITE)
        draw = ImageDraw.Draw(img)

        # Title + subtitle.
        title = f"Executive Report: {theme['name']}"
        tf, _ = self._fit_font(draw, title, self.W - 2 * self.MARGIN, 38, bold=True, min_size=22)
        ttw = self._tw(draw, title, tf)
        draw.text(((self.W - ttw) / 2, top), title, font=tf, fill=self.INK)
        sub = f"{county} County, TX ({analysis['region']}) — {timestamp.strftime('%A, %B %-d, %Y')}"
        sf = self.fonts.get(20)
        stw = self._tw(draw, sub, sf)
        draw.text(((self.W - stw) / 2, top + title_h - 4), sub, font=sf, fill=self.GRAY)

        # Card.
        banner_text = f"{analysis['dominant_hazard_name'].upper()}  |  {county.upper()} COUNTY, TX"
        self._draw_card(img, draw, self.MARGIN, card_top, body_w, banner_text,
                        banner_color, analysis.get('metric_tiles', []),
                        analysis.get('safety_guidance', []))

        # Bullet section.
        by = bullets_top
        slf = self.fonts.get(22, bold=True)
        draw.text((self.MARGIN, by), "Key Points", font=slf, fill=self.INK)
        # Accent underline.
        draw.rectangle([self.MARGIN, by + 32, self.MARGIN + 120, by + 36], fill=banner_color)
        by += section_label_h

        for lines in wrapped_bullets:
            draw.ellipse([self.MARGIN + 4, by + 9, self.MARGIN + 13, by + 18], fill=banner_color)
            for li, line in enumerate(lines):
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

        # Lead bullet: dominant hazard + risk level.
        bullets.append(
            f"**{a['dominant_hazard_name']}** is the primary threat for **{a['county']} County**, "
            f"currently assessed at **{a['risk_level']}** likelihood of operational impacts."
        )

        # Active alerts.
        if a['alerts']:
            names = ', '.join(sorted({al['event'] for al in a['alerts']}))
            bullets.append(f"Active National Weather Service products: **{names}**.")
        else:
            bullets.append("**No active NWS warnings**; assessment driven by forecast conditions.")

        # Hazard-specific quantitative bullet.
        if a['dominant_hazard'] == 'extreme_heat' and m.get('max_heat_index_f'):
            flag = m.get('flag_condition')
            flag_txt = f" reaching **{flag['flag']} flag** conditions" if flag else ""
            bullets.append(
                f"Heat index expected to peak near **{int(m['max_heat_index_f'])}°F** with a forecast "
                f"high of **{int(m['max_temp_f'])}°F**{flag_txt}."
            )
        elif a['dominant_hazard'] == 'extreme_cold' and m.get('min_wind_chill_f') is not None:
            bullets.append(
                f"Wind chills as low as **{int(m['min_wind_chill_f'])}°F** with overnight lows near "
                f"**{int(m['min_temp_f'])}°F**."
            )
        elif a['dominant_hazard'] == 'fire_weather' and m.get('min_rh') is not None:
            bullets.append(
                f"**Critical fire weather**: relative humidity dropping to **{int(m['min_rh'])}%** "
                f"with gusty winds elevating rapid wildfire spread potential."
            )
        elif a['dominant_hazard'] in ('severe_storm', 'tropical', 'wind') and m.get('max_wind_gust_mph'):
            bullets.append(f"Peak wind gusts near **{int(m['max_wind_gust_mph'])} mph** anticipated.")

        # Timeline.
        if a['timeline'].get('narrative'):
            bullets.append(f"**Timeline:** {a['timeline']['narrative']}.")

        # Top infrastructure impacts.
        impacts = a['infrastructure_impacts']
        for key, label in (('public_safety', 'Public safety'), ('utilities', 'Utilities'),
                           ('transportation', 'Transportation')):
            if impacts.get(key):
                bullets.append(f"**{label}:** {impacts[key][0]}.")

        # Coastal tropical watch note.
        if a.get('coastal_tropical_watch'):
            bullets.append("**Coastal tropical watch:** active system(s) in the basin warrant monitoring for this coastal county.")

        return bullets


# ===========================================================================
# SECTION: pdf_report.py
# ===========================================================================

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



def _fmt_alert_dt(iso: str) -> Optional[str]:
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        return dt.strftime("%A %-m/%-d %-I:%M %p")
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


# ===========================================================================
# SECTION: sample_data.py
# ===========================================================================

"""
Bundled sample data for demo mode and offline testing.

Produces records in the exact shape emitted by WeatherDataAgent so the analysis,
narrative, infographic, and PDF stages can run end-to-end without network access.
The scenario is a multi-hazard summer day designed to exercise every code path:
extreme heat, a tropical system, flooding, fire weather, and severe storms.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple


def _iso(hours_from_now: float) -> str:
    return (datetime.now() + timedelta(hours=hours_from_now)).astimezone().isoformat()


def _alerts(county: str, alerts: List[Dict]) -> Dict:
    return {'source': 'NWS', 'county': county, 'alerts': alerts, 'status': 'success'}


def _forecast(county: str, periods: List[Dict], grid: Dict) -> Dict:
    return {'source': 'NWS Forecast', 'county': county, 'forecasts': periods,
            'grid': grid, 'status': 'success'}


def _periods(high: int, low: int, day_cond: str, night_cond: str) -> List[Dict]:
    out = []
    for i in range(6):
        out.append({'name': f'Day {i+1}', 'temperature': high - i, 'temperatureUnit': 'F',
                    'windSpeed': '10 to 20 mph', 'windDirection': 'S', 'shortForecast': day_cond,
                    'detailedForecast': day_cond, 'startTime': _iso(i * 24 + 6),
                    'isDaytime': True, 'probabilityOfPrecipitation': 20})
        out.append({'name': f'Night {i+1}', 'temperature': low - i, 'temperatureUnit': 'F',
                    'windSpeed': '5 to 10 mph', 'windDirection': 'S', 'shortForecast': night_cond,
                    'detailedForecast': night_cond, 'startTime': _iso(i * 24 + 18),
                    'isDaytime': False, 'probabilityOfPrecipitation': 10})
    return out


def build_sample_data() -> Tuple[List[Dict], Dict]:
    data: List[Dict] = []

    # --- Travis: Extreme Heat Warning (mirrors the reference infographic) ----
    data.append(_alerts('Travis', [{
        'event': 'Excessive Heat Warning', 'severity': 'Extreme', 'urgency': 'Expected',
        'certainty': 'Likely', 'headline': 'Excessive Heat Warning until 8 PM CDT',
        'description': 'Dangerously hot conditions with heat index values up to 113 expected.',
        'instruction': 'Drink plenty of fluids and stay out of the sun.',
        'onset': _iso(2), 'expires': _iso(10)}]))
    data.append(_forecast('Travis', _periods(101, 78, 'Sunny and Hot', 'Clear'),
                          {'max_temp_f': 101, 'min_temp_f': 78, 'max_heat_index_f': 113,
                           'min_wind_chill_f': None, 'min_rh': 38, 'max_rh': 60,
                           'max_wind_gust_mph': 18}))

    # --- Bexar: Heat Advisory --------------------------------------------------
    data.append(_alerts('Bexar', [{
        'event': 'Heat Advisory', 'severity': 'Moderate', 'urgency': 'Expected', 'certainty': 'Likely',
        'headline': 'Heat Advisory in effect', 'description': 'Heat index values up to 106.',
        'instruction': '', 'onset': _iso(3), 'expires': _iso(9)}]))
    data.append(_forecast('Bexar', _periods(99, 77, 'Hot and Humid', 'Mostly Clear'),
                          {'max_temp_f': 99, 'min_temp_f': 77, 'max_heat_index_f': 106,
                           'min_wind_chill_f': None, 'min_rh': 45, 'max_rh': 70, 'max_wind_gust_mph': 15}))

    # --- McLennan: no alert, forecast-driven heat -----------------------------
    data.append(_alerts('McLennan', []))
    data.append(_forecast('McLennan', _periods(97, 75, 'Sunny', 'Clear'),
                          {'max_temp_f': 97, 'min_temp_f': 75, 'max_heat_index_f': 102,
                           'min_wind_chill_f': None, 'min_rh': 40, 'max_rh': 65, 'max_wind_gust_mph': 12}))

    # --- Nueces: Tropical Storm Warning + Storm Surge -------------------------
    data.append(_alerts('Nueces', [
        {'event': 'Tropical Storm Warning', 'severity': 'Severe', 'urgency': 'Immediate',
         'certainty': 'Likely', 'headline': 'Tropical Storm Warning for the Coastal Bend',
         'description': 'Tropical storm conditions with damaging winds and heavy rain expected. '
                        'Power outages likely.',
         'instruction': 'Follow advice of local officials.', 'onset': _iso(6), 'expires': _iso(36)},
        {'event': 'Storm Surge Watch', 'severity': 'Severe', 'urgency': 'Expected', 'certainty': 'Possible',
         'headline': 'Storm Surge Watch', 'description': 'Life-threatening storm surge possible.',
         'instruction': '', 'onset': _iso(8), 'expires': _iso(40)}]))
    data.append(_forecast('Nueces', _periods(88, 76, 'Tropical Storm', 'Heavy Rain'),
                          {'max_temp_f': 88, 'min_temp_f': 76, 'max_heat_index_f': 95,
                           'min_wind_chill_f': None, 'min_rh': 80, 'max_rh': 98, 'max_wind_gust_mph': 62}))

    # --- Cameron: Flash Flood Watch -------------------------------------------
    data.append(_alerts('Cameron', [{
        'event': 'Flash Flood Watch', 'severity': 'Severe', 'urgency': 'Expected', 'certainty': 'Possible',
        'headline': 'Flash Flood Watch for the Rio Grande Valley',
        'description': 'Heavy rainfall may lead to flash flooding of low-water crossings.',
        'instruction': 'Turn around, don\'t drown.', 'onset': _iso(4), 'expires': _iso(28)}]))
    data.append(_forecast('Cameron', _periods(90, 77, 'Heavy Rain Likely', 'Showers'),
                          {'max_temp_f': 90, 'min_temp_f': 77, 'max_heat_index_f': 99,
                           'min_wind_chill_f': None, 'min_rh': 75, 'max_rh': 95, 'max_wind_gust_mph': 35}))

    # --- Galveston: Coastal Flood Advisory ------------------------------------
    data.append(_alerts('Galveston', [{
        'event': 'Coastal Flood Advisory', 'severity': 'Moderate', 'urgency': 'Expected', 'certainty': 'Likely',
        'headline': 'Coastal Flood Advisory', 'description': 'Minor coastal flooding of vulnerable areas.',
        'instruction': '', 'onset': _iso(5), 'expires': _iso(20)}]))
    data.append(_forecast('Galveston', _periods(91, 80, 'Scattered Storms', 'Partly Cloudy'),
                          {'max_temp_f': 91, 'min_temp_f': 80, 'max_heat_index_f': 104,
                           'min_wind_chill_f': None, 'min_rh': 70, 'max_rh': 92, 'max_wind_gust_mph': 30}))

    # --- Harris: Severe Thunderstorm Warning ----------------------------------
    data.append(_alerts('Harris', [{
        'event': 'Severe Thunderstorm Warning', 'severity': 'Severe', 'urgency': 'Immediate',
        'certainty': 'Observed', 'headline': 'Severe Thunderstorm Warning',
        'description': 'Damaging winds to 70 mph and quarter-size hail. Power outages expected.',
        'instruction': 'Move indoors.', 'onset': _iso(1), 'expires': _iso(3)}]))
    data.append(_forecast('Harris', _periods(93, 78, 'Severe Storms', 'Thunderstorms'),
                          {'max_temp_f': 93, 'min_temp_f': 78, 'max_heat_index_f': 107,
                           'min_wind_chill_f': None, 'min_rh': 65, 'max_rh': 90, 'max_wind_gust_mph': 70}))

    # --- El Paso: Red Flag Warning (fire weather) -----------------------------
    data.append(_alerts('El Paso', [{
        'event': 'Red Flag Warning', 'severity': 'Severe', 'urgency': 'Expected', 'certainty': 'Likely',
        'headline': 'Red Flag Warning for critical fire weather',
        'description': 'Low humidity and gusty winds will create critical fire weather conditions.',
        'instruction': 'Avoid outdoor burning.', 'onset': _iso(3), 'expires': _iso(12)}]))
    data.append(_forecast('El Paso', _periods(100, 72, 'Sunny and Windy', 'Clear'),
                          {'max_temp_f': 100, 'min_temp_f': 72, 'max_heat_index_f': 100,
                           'min_wind_chill_f': None, 'min_rh': 8, 'max_rh': 22, 'max_wind_gust_mph': 45}))

    # --- Tarrant: High Wind Warning -------------------------------------------
    data.append(_alerts('Tarrant', [{
        'event': 'High Wind Warning', 'severity': 'Moderate', 'urgency': 'Expected', 'certainty': 'Likely',
        'headline': 'High Wind Warning', 'description': 'West winds 25 to 35 mph with gusts up to 55 mph.',
        'instruction': '', 'onset': _iso(2), 'expires': _iso(14)}]))
    data.append(_forecast('Tarrant', _periods(95, 74, 'Windy', 'Breezy'),
                          {'max_temp_f': 95, 'min_temp_f': 74, 'max_heat_index_f': 99,
                           'min_wind_chill_f': None, 'min_rh': 30, 'max_rh': 55, 'max_wind_gust_mph': 55}))

    data_quality = {
        'total_requests': 18, 'successful_requests': 18, 'failed_requests': 0,
        'counties_reporting': ['Travis', 'Bexar', 'McLennan', 'Nueces', 'Cameron',
                               'Galveston', 'Harris', 'El Paso', 'Tarrant'],
        'counties_partial': [], 'counties_failed': [],
        'tropical_systems': [{'name': 'Tropical Storm Hilda', 'classification': 'TS',
                              'intensity_mph': '60', 'pressure_mb': '995', 'basin': 'AL',
                              'last_update': _iso(0)}],
    }
    return data, data_quality


# ===========================================================================
# SECTION: orchestrator.py
# ===========================================================================

"""
Main orchestrator: coordinates data collection, analysis, narrative generation,
infographic rendering, and PDF assembly.

Supports two modes:
  * live  - pulls real data from NWS / NHC.
  * demo  - uses bundled sample_data so the full pipeline (including infographics
            and PDF) can be exercised offline or for showcasing.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional



class WeatherRiskOrchestrator:
    def __init__(self, ollama_model: str = "gemma3:27b", output_dir: str = OUTPUT_DIR):
        self.data_agent = WeatherDataAgent()
        self.analysis_agent = RiskAnalysisAgent()
        self.narrative_agent = NarrativeGenerationAgent(ollama_model)
        self.infographic = InfographicGenerator()
        self.pdf_generator = PDFReportGenerator()
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def run_full_assessment(self, mode: str = "live",
                            infographic_counties: Optional[List[str]] = None) -> Dict[str, str]:
        print("\n" + "=" * 70)
        print("TEXAS YEAR-ROUND WEATHER RISK ASSESSMENT SYSTEM")
        print("=" * 70)
        timestamp = datetime.now()
        season = HZ.texas_season(timestamp)
        print(f"Season context: {season}   |   Mode: {mode}\n")

        # PHASE 1 — DATA
        print("PHASE 1: DATA COLLECTION\n" + "-" * 70)
        if mode == "demo":
            raw_data, data_quality = build_sample_data()
            print("Loaded bundled sample data (demo mode).")
        else:
            raw_data, data_quality = self.data_agent.gather_all_data()
        print(f"\n✓ Requests: {data_quality['total_requests']} | "
              f"OK: {data_quality['successful_requests']} | Failed: {data_quality['failed_requests']}")
        if data_quality.get('tropical_systems'):
            print(f"  Active tropical systems: {', '.join(s['name'] for s in data_quality['tropical_systems'])}")

        # PHASE 2 — ANALYSIS
        print("\nPHASE 2: RISK ANALYSIS\n" + "-" * 70)
        analyses = self.analysis_agent.analyze_all_counties(
            raw_data, season, data_quality.get('tropical_systems'))
        for a in analyses:
            icon = {'High': '🔴', 'Moderate': '🟠', 'Medium': '🟡', 'Low': '🟢'}[a['risk_level']]
            print(f"  {icon} {a['county']:10} {a['risk_level']:9} "
                  f"[{a['dominant_hazard_name']}] (score {a['severity_score']}/100)")

        # PHASE 3 — NARRATIVES
        print("\nPHASE 3: NARRATIVE GENERATION\n" + "-" * 70)
        executive_summary = self.narrative_agent.generate_executive_summary(
            analyses, season, data_quality.get('tropical_systems', []))
        narratives: Dict[str, Dict] = {}
        for a in analyses:
            narratives[a['county']] = {
                'county_narrative': self.narrative_agent.generate_county_narrative(a)}
        print("✓ Narratives generated")

        # PHASE 4 — INFOGRAPHICS
        print("\nPHASE 4: INFOGRAPHIC GENERATION\n" + "-" * 70)
        # By default produce infographics for the highest-risk counties.
        if infographic_counties is None:
            infographic_counties = [a['county'] for a in analyses
                                    if a['severity_score'] >= 26][:5]
            if not infographic_counties and analyses:
                infographic_counties = [analyses[0]['county']]
        infographics: Dict[str, str] = {}
        for a in analyses:
            if a['county'] in infographic_counties:
                fn = os.path.join(
                    self.output_dir,
                    f"infographic_{a['county'].replace(' ', '')}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png")
                result = self.infographic.generate(a, timestamp, fn)
                if result:
                    infographics[a['county']] = result

        # PHASE 5 — PDF
        print("\nPHASE 5: PDF REPORT GENERATION\n" + "-" * 70)
        pdf_name = os.path.join(
            self.output_dir, f"weather_risk_report_{timestamp.strftime('%Y%m%d_%H%M%S')}.pdf")
        self.pdf_generator.generate_pdf(analyses, executive_summary, narratives,
                                        data_quality, season, timestamp, pdf_name, infographics)

        return {'pdf': pdf_name, 'infographics': infographics}


# ===========================================================================
# SECTION: run.py
# ===========================================================================

#!/usr/bin/env python3
"""
Entry point for the Texas Year-Round Weather Risk Assessment System.

Usage:
    python -m weather_intel.run               # live data from NWS/NHC
    python -m weather_intel.run --demo         # offline demo using bundled data
    python -m weather_intel.run --demo --no-llm  # skip Ollama, use templates
    python -m weather_intel.run --counties Travis Harris

Requirements:
    pip install -r weather_intel/requirements.txt
    (Optional) Ollama running locally with a model such as gemma3:27b for richer
    narratives; without it, deterministic templates are used.
"""

import argparse



def main():
    parser = argparse.ArgumentParser(description="Texas year-round weather risk assessment")
    parser.add_argument('--demo', action='store_true', help='Use bundled sample data (offline)')
    parser.add_argument('--no-llm', action='store_true', help='Skip Ollama; use template narratives')
    parser.add_argument('--model', default='gemma3:27b', help='Ollama model name')
    parser.add_argument('--counties', nargs='*', default=None,
                        help='Limit infographics to these counties (default: highest-risk)')
    parser.add_argument('--output', default='output', help='Output directory')
    args = parser.parse_args()

    model = '__disabled__' if args.no_llm else args.model
    orchestrator = WeatherRiskOrchestrator(ollama_model=model, output_dir=args.output)
    mode = 'demo' if args.demo else 'live'

    results = orchestrator.run_full_assessment(mode=mode, infographic_counties=args.counties)

    print("\n" + "=" * 70)
    print("ASSESSMENT COMPLETE")
    print("=" * 70)
    print(f"PDF report: {results['pdf']}")
    if results['infographics']:
        print("Infographics:")
        for county, path in results['infographics'].items():
            print(f"  • {county}: {path}")


if __name__ == "__main__":
    main()
