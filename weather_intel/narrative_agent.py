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
