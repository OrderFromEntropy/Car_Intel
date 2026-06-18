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
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

import requests

from .config import API_CONFIG, COUNTIES, county_alert_zone
from . import hazards as HZ


class WeatherDataAgent:
    def __init__(self):
        self.counties = COUNTIES
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': API_CONFIG['user_agent']})

    # ------------------------------------------------------------------ alerts
    @staticmethod
    def _parse_alert(feature: Dict) -> Dict:
        p = feature.get('properties', {})
        return {
            'event': p.get('event', 'Unknown'),
            'severity': p.get('severity', 'Unknown'),
            'urgency': p.get('urgency', 'Unknown'),
            'certainty': p.get('certainty', 'Unknown'),
            'headline': p.get('headline', ''),
            'description': p.get('description', ''),
            'instruction': p.get('instruction', '') or '',
            'onset': p.get('onset', ''),
            'expires': p.get('expires', ''),
        }

    def fetch_nws_alerts(self, county_name: str) -> Dict:
        """
        Fetch active alerts for a county.

        Queries BOTH the county alert zone and the county centroid point, then
        merges/dedupes. Heat and other zone-based products are sometimes carried
        on forecast (TXZ) zones rather than the county (TXC) zone; the point
        query catches anything affecting the location regardless of zone type,
        so dry-heat or zone-issued alerts are not missed.
        """
        print(f"Fetching NWS alerts for {county_name}...")
        cfg = self.counties[county_name]
        zone = county_alert_zone(cfg['fips'])
        base = API_CONFIG['nws_base_url']
        urls = [
            f"{base}/alerts/active/zone/{zone}",
            f"{base}/alerts/active?point={cfg['lat']},{cfg['lon']}",
        ]
        merged: Dict[tuple, Dict] = {}
        any_ok = False
        last_err = None
        for url in urls:
            try:
                resp = self.session.get(url, timeout=API_CONFIG['timeout_seconds'])
                if resp.status_code == 200:
                    any_ok = True
                    for feature in resp.json().get('features', []):
                        a = self._parse_alert(feature)
                        merged.setdefault((a['event'], a['onset'], a['expires']), a)
                else:
                    last_err = f'HTTP {resp.status_code}'
            except Exception as e:
                last_err = str(e)
        if any_ok:
            return {'source': 'NWS', 'county': county_name,
                    'alerts': list(merged.values()), 'status': 'success'}
        return self._err('NWS', county_name, 'alerts', last_err or 'unknown error')

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
                'daily_precip_in': self._daily_precip(gp),
            }
        except Exception:
            return {}

    @staticmethod
    def _daily_precip(gp: Dict) -> Dict[str, float]:
        """Aggregate gridpoint QPF (mm) into projected per-day rainfall (inches)."""
        totals = defaultdict(float)
        for v in gp.get('quantitativePrecipitation', {}).get('values', []):
            val = v.get('value')
            valid = (v.get('validTime') or '').split('/')[0]
            if val is None or not valid:
                continue
            try:
                dt = datetime.fromisoformat(valid.replace('Z', '+00:00'))
            except Exception:
                continue
            totals[HZ.fmt_forecast_date(dt)] += val
        return {date: round(mm / 25.4, 2) for date, mm in totals.items()}

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
