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

from .config import COUNTIES, RISK_THRESHOLDS, SCORING_CONFIG
from . import hazards as HZ


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
                parts.append(f"Conditions begin {HZ.fmt_time(dt, '%A %-I:%M %p')}")
            except Exception:
                parts.append('Conditions developing')
        if tl['improvement_expected']:
            try:
                dt = datetime.fromisoformat(tl['improvement_expected'].replace('Z', '+00:00'))
                parts.append(f"easing by {HZ.fmt_time(dt, '%A %-I:%M %p')}")
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
                    return f"{HZ.fmt_time(a, '%-I %p').upper()} – {HZ.fmt_time(b, '%-I %p').upper()}"
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
