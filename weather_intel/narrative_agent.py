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

from . import hazards as HZ


PROMPT_EXECUTIVE_SUMMARY = """You are generating an executive summary for Texas state leadership about active weather threats. This is a YEAR-ROUND system: hazards may include extreme heat, flooding, tropical systems (hurricanes/tropical storms/depressions), severe thunderstorms/tornadoes, winter storms, extreme cold, fire weather (red flag), high wind, and more.

INPUT DATA (JSON):
{json_data}

Output 4 to 7 SHORT, quick-hitting bullet lines (each on its own line, beginning with "- "). Bold the most important terms using **double asterisks** (county names, risk levels, hazards, key numbers). Cover:
- A lead bullet stating the overall statewide threat level and how many counties are at High/Moderate likelihood of operational impacts.
- One bullet per county that has a notable threat, naming the county, its risk level, and its dominant hazard.
- A bullet on the key infrastructure concern (power grid, highways, water systems, evacuation if tropical).
Be concise and factual. Do NOT include recommendations or advice. Output only the bullet lines."""

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
                                   tropical_systems: List[Dict]) -> List[str]:
        """Return a list of quick-hitting bullet strings (with **bold** markup)."""
        print("Generating executive summary...")
        if self.llm_available:
            try:
                risk_dist = {'High': [], 'Moderate': [], 'Medium': [], 'Low': []}
                for a in analyses:
                    risk_dist[a['risk_level']].append(a['county'])
                input_data = {
                    'season': season,
                    'risk_distribution': risk_dist,
                    'counties': [{'county': a['county'], 'city': a['city'],
                                  'risk_level': a['risk_level'],
                                  'dominant_hazard': a['dominant_hazard_name']} for a in analyses],
                    'active_tropical_systems': [s['name'] for s in tropical_systems] if tropical_systems else [],
                }
                raw = self.call_llm(PROMPT_EXECUTIVE_SUMMARY, json.dumps(input_data, indent=2))
                bullets = self._parse_bullet_lines(raw)
                if len(bullets) >= 2:
                    return bullets
            except Exception as e:
                print(f"LLM call failed: {e}; using template")
        return self._template_summary(analyses, season, tropical_systems)

    @staticmethod
    def _parse_bullet_lines(raw: str) -> List[str]:
        bullets = []
        for line in raw.splitlines():
            line = line.strip().lstrip('-*•').strip()
            if line:
                bullets.append(line)
        return bullets

    def _template_summary(self, analyses: List[Dict], season: str,
                          tropical_systems: List[Dict]) -> List[str]:
        risk_dist = {'High': [], 'Moderate': [], 'Medium': [], 'Low': []}
        for a in analyses:
            risk_dist[a['risk_level']].append(a)

        bullets: List[str] = []

        # Lead bullet — overall posture, scaled by counts.
        n_high, n_mod = len(risk_dist['High']), len(risk_dist['Moderate'])
        if n_high:
            overall = 'High'
        elif n_mod:
            overall = 'Elevated'
        elif risk_dist['Medium']:
            overall = 'Moderate'
        else:
            overall = 'Low'
        lead = f"Statewide threat level: **{overall}** ({season})."
        tallies = []
        if n_high:
            tallies.append(f"**{n_high}** at High")
        if n_mod:
            tallies.append(f"**{n_mod}** at Moderate")
        if tallies:
            lead += " " + " and ".join(tallies) + " likelihood of operational impacts."
        else:
            lead += " No counties at elevated likelihood of operational impacts."
        bullets.append(lead)

        # Active tropical systems (basin-wide).
        if tropical_systems:
            names = ', '.join(s['name'] for s in tropical_systems)
            bullets.append(f"**Active tropical system(s):** {names} — coastal exposure under heightened monitoring.")

        # One bullet per county with a notable threat (scales the summary length).
        notable = [a for a in analyses if a['risk_level'] != 'Low' or a['active_alerts']]
        for a in notable:
            metric = self._metric_tag(a)
            bullets.append(
                f"**{a['county']} ({a['city']})**: **{a['risk_level']}** — {a['dominant_hazard_name']}"
                + (f", {metric}" if metric else "") + ".")

        # Aggregate infrastructure concern across elevated counties.
        concerns = set()
        for a in analyses:
            if a['risk_level'] in ('High', 'Moderate'):
                for key in ('public_safety', 'utilities', 'transportation'):
                    if a['infrastructure_impacts'].get(key):
                        concerns.add(key)
        if concerns:
            label = {'public_safety': 'public safety', 'utilities': 'the power grid and water systems',
                     'transportation': 'major highway corridors'}
            bullets.append("**Key concerns:** anticipated impacts to " +
                           ", ".join(label[c] for c in ('public_safety', 'utilities', 'transportation') if c in concerns) + ".")
        return bullets

    @staticmethod
    def _metric_tag(a: Dict) -> str:
        m = a.get('metrics', {})
        d = a['dominant_hazard']
        if d == 'extreme_heat' and m.get('max_heat_index_f'):
            return f"heat index to **{int(m['max_heat_index_f'])}°F**"
        if d == 'extreme_cold' and m.get('min_wind_chill_f') is not None:
            return f"wind chill to **{int(m['min_wind_chill_f'])}°F**"
        if d == 'fire_weather' and m.get('min_rh') is not None:
            return f"RH to **{int(m['min_rh'])}%**"
        if d in ('severe_storm', 'tropical', 'wind') and m.get('max_wind_gust_mph'):
            return f"gusts to **{int(m['max_wind_gust_mph'])} mph**"
        if a['active_alerts']:
            return f"**{a['active_alerts']}** active alert(s)"
        return ""

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
