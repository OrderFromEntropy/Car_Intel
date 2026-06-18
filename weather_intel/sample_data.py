"""
Bundled sample data for demo mode and offline testing.

Produces records in the exact shape emitted by WeatherDataAgent so the analysis,
narrative, infographic, and PDF stages can run end-to-end without network access.
The scenario is a multi-hazard summer day across the six monitored counties,
designed to exercise the season-aware risk logic: extreme heat (which is capped
at Moderate operational likelihood), a flash-flood warning (High), high wind and
fire weather (Moderate), and forecast-only heat (Low/Medium).
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from . import hazards as HZ


def _iso(hours_from_now: float) -> str:
    return (datetime.now() + timedelta(hours=hours_from_now)).astimezone().isoformat()


def _precip(daily_inches: List[float]) -> Dict[str, float]:
    """Map projected daily rainfall to the same date labels the forecast uses."""
    out = {}
    for i, inches in enumerate(daily_inches):
        dt = datetime.now() + timedelta(hours=i * 24 + 6)
        out[HZ.fmt_forecast_date(dt)] = inches
    return out


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

    # --- Travis (Austin): Excessive Heat Warning -> heat is capped at Moderate -
    data.append(_alerts('Travis', [{
        'event': 'Excessive Heat Warning', 'severity': 'Extreme', 'urgency': 'Expected',
        'certainty': 'Likely', 'headline': 'Excessive Heat Warning until 8 PM CDT',
        'description': 'Dangerously hot conditions with heat index values up to 113 expected.',
        'instruction': 'Drink plenty of fluids and stay out of the sun.',
        'onset': _iso(2), 'expires': _iso(10)}]))
    data.append(_forecast('Travis', _periods(101, 78, 'Sunny and Hot', 'Clear'),
                          {'max_temp_f': 101, 'min_temp_f': 78, 'max_heat_index_f': 113,
                           'min_wind_chill_f': None, 'min_rh': 38, 'max_rh': 60,
                           'max_wind_gust_mph': 18, 'daily_precip_in': _precip([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])}))

    # --- Bexar (San Antonio): Heat Advisory -----------------------------------
    data.append(_alerts('Bexar', [{
        'event': 'Heat Advisory', 'severity': 'Moderate', 'urgency': 'Expected', 'certainty': 'Likely',
        'headline': 'Heat Advisory in effect', 'description': 'Heat index values up to 106.',
        'instruction': '', 'onset': _iso(3), 'expires': _iso(9)}]))
    data.append(_forecast('Bexar', _periods(99, 77, 'Hot and Humid', 'Mostly Clear'),
                          {'max_temp_f': 99, 'min_temp_f': 77, 'max_heat_index_f': 106,
                           'min_wind_chill_f': None, 'min_rh': 45, 'max_rh': 70,
                           'max_wind_gust_mph': 15, 'daily_precip_in': _precip([0.0, 0.1, 0.2, 0.0, 0.0, 0.0])}))

    # --- McLennan (Waco): no alert, forecast-driven heat ----------------------
    data.append(_alerts('McLennan', []))
    data.append(_forecast('McLennan', _periods(97, 75, 'Sunny', 'Clear'),
                          {'max_temp_f': 97, 'min_temp_f': 75, 'max_heat_index_f': 102,
                           'min_wind_chill_f': None, 'min_rh': 40, 'max_rh': 65,
                           'max_wind_gust_mph': 12, 'daily_precip_in': _precip([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])}))

    # --- Tarrant (Fort Worth): High Wind Warning ------------------------------
    data.append(_alerts('Tarrant', [{
        'event': 'High Wind Warning', 'severity': 'Moderate', 'urgency': 'Expected', 'certainty': 'Likely',
        'headline': 'High Wind Warning', 'description': 'West winds 25 to 35 mph with gusts up to 55 mph.',
        'instruction': '', 'onset': _iso(2), 'expires': _iso(14)}]))
    data.append(_forecast('Tarrant', _periods(95, 74, 'Windy', 'Breezy'),
                          {'max_temp_f': 95, 'min_temp_f': 74, 'max_heat_index_f': 99,
                           'min_wind_chill_f': None, 'min_rh': 30, 'max_rh': 55,
                           'max_wind_gust_mph': 55, 'daily_precip_in': _precip([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])}))

    # --- Harris (Houston): Flash Flood Warning -> High operational likelihood -
    data.append(_alerts('Harris', [{
        'event': 'Flash Flood Warning', 'severity': 'Severe', 'urgency': 'Immediate',
        'certainty': 'Observed', 'headline': 'Flash Flood Warning for Harris County',
        'description': 'Torrential rainfall producing flash flooding of low-water crossings and '
                       'underpasses. Power outages possible.',
        'instruction': 'Turn around, don\'t drown.', 'onset': _iso(1), 'expires': _iso(9)}]))
    data.append(_forecast('Harris', _periods(90, 77, 'Heavy Rain', 'Showers'),
                          {'max_temp_f': 90, 'min_temp_f': 77, 'max_heat_index_f': 101,
                           'min_wind_chill_f': None, 'min_rh': 78, 'max_rh': 96,
                           'max_wind_gust_mph': 40, 'daily_precip_in': _precip([3.5, 1.2, 0.4, 0.1, 0.0, 0.0])}))

    # --- El Paso: Red Flag Warning (fire weather) -----------------------------
    data.append(_alerts('El Paso', [{
        'event': 'Red Flag Warning', 'severity': 'Severe', 'urgency': 'Expected', 'certainty': 'Likely',
        'headline': 'Red Flag Warning for critical fire weather',
        'description': 'Low humidity and gusty winds will create critical fire weather conditions.',
        'instruction': 'Avoid outdoor burning.', 'onset': _iso(3), 'expires': _iso(12)}]))
    data.append(_forecast('El Paso', _periods(100, 72, 'Sunny and Windy', 'Clear'),
                          {'max_temp_f': 100, 'min_temp_f': 72, 'max_heat_index_f': 100,
                           'min_wind_chill_f': None, 'min_rh': 8, 'max_rh': 22,
                           'max_wind_gust_mph': 45, 'daily_precip_in': _precip([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])}))

    data_quality = {
        'total_requests': 12, 'successful_requests': 12, 'failed_requests': 0,
        'counties_reporting': ['Travis', 'Bexar', 'McLennan', 'Tarrant', 'Harris', 'El Paso'],
        'counties_partial': [], 'counties_failed': [],
        'tropical_systems': [],
    }
    return data, data_quality
