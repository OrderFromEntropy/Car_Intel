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

from .config import OUTPUT_DIR
from . import hazards as HZ
from .data_agent import WeatherDataAgent
from .analysis_agent import RiskAnalysisAgent
from .narrative_agent import NarrativeGenerationAgent
from .infographic import InfographicGenerator
from .pdf_report import PDFReportGenerator


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
            from .sample_data import build_sample_data
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
