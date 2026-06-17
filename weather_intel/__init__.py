"""
Texas Year-Round Weather Operational Risk Assessment System.

A multi-hazard threat-intelligence engine that ingests National Weather Service
and National Hurricane Center data, scores operational risk for monitored Texas
counties, and produces an executive PDF brief plus shareable infographic cards
(bold keywords, bullet points, themed graphic) for any hazard in any season:
extreme heat, flooding, tropical systems, severe storms, winter storms, extreme
cold, fire weather (red flag), high wind, dense fog/dust, and air quality.

Information only — no recommendations beyond reproduced standard NWS safety
messaging on infographics.
"""

from .orchestrator import WeatherRiskOrchestrator

__all__ = ["WeatherRiskOrchestrator"]
__version__ = "2.0.0"
