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
