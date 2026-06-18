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

from .orchestrator import WeatherRiskOrchestrator
from .config import OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser(description="Texas year-round weather risk assessment")
    parser.add_argument('--demo', action='store_true', help='Use bundled sample data (offline)')
    parser.add_argument('--no-llm', action='store_true', help='Skip Ollama; use template narratives')
    parser.add_argument('--model', default='gemma3:27b', help='Ollama model name')
    parser.add_argument('--counties', nargs='*', default=None,
                        help='Limit infographics to these counties (default: highest-risk)')
    parser.add_argument('--output', default=OUTPUT_DIR,
                        help=f'Output directory (default: {OUTPUT_DIR})')
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
