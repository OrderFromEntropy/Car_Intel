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
