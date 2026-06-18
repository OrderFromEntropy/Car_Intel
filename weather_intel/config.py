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
    'Travis': {
        'fips': '48453', 'lat': 30.2672, 'lon': -97.7431, 'city': 'Austin',
        'major_highways': ['I-35', 'US-183'], 'nws_office': 'Austin/San Antonio',
        'region': 'Central Texas', 'coastal': False,
    },
    'Bexar': {
        'fips': '48029', 'lat': 29.4241, 'lon': -98.4936, 'city': 'San Antonio',
        'major_highways': ['I-10', 'I-35', 'I-37'], 'nws_office': 'Austin/San Antonio',
        'region': 'South Central Texas', 'coastal': False,
    },
    'McLennan': {
        'fips': '48309', 'lat': 31.5493, 'lon': -97.1467, 'city': 'Waco',
        'major_highways': ['I-35'], 'nws_office': 'Fort Worth',
        'region': 'Central Texas', 'coastal': False,
    },
    'Tarrant': {
        'fips': '48439', 'lat': 32.7555, 'lon': -97.3308, 'city': 'Fort Worth',
        'major_highways': ['I-35W', 'I-20', 'I-30'], 'nws_office': 'Fort Worth',
        'region': 'North Texas', 'coastal': False,
    },
    'Harris': {
        'fips': '48201', 'lat': 29.7604, 'lon': -95.3698, 'city': 'Houston',
        'major_highways': ['I-10', 'I-45', 'I-69'], 'nws_office': 'Houston/Galveston',
        'region': 'Upper Texas Coast', 'coastal': True,
    },
    'El Paso': {
        'fips': '48141', 'lat': 31.7619, 'lon': -106.4850, 'city': 'El Paso',
        'major_highways': ['I-10'], 'nws_office': 'El Paso',
        'region': 'Far West Texas', 'coastal': False,
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
    'subtitle': 'Risk Management Leadership Brief',
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

# Output directory for generated reports and infographics.
# Default is a fixed Windows path so files always land in the same place
# regardless of where the program is launched from. Override at runtime with
# --output (e.g. python texas_weather_intel.py --output "D:\\Reports").
OUTPUT_DIR = r'C:\Users\cfied\OneDrive\Documents\Texas Weather Reports'
