#!/usr/bin/env python3
"""CarIntel — AI-Powered Car Search Aggregator.

Usage:
    python main.py

Requires:
    - Ollama running locally with gemma4:e2b pulled
    - pip install -r requirements.txt
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    from ui.main_window import run_app
    run_app()
