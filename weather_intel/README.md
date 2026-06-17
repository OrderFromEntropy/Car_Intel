# Texas Year-Round Weather Operational Risk Assessment System

Version 2.0 — a four-season, multi-hazard evolution of the original winter-only
proof of concept. It ingests National Weather Service and National Hurricane
Center data, scores operational risk for monitored Texas counties, and produces:

1. An **executive PDF brief** (information-only, leadership-ready), and
2. **Shareable infographic cards** — bold keywords, bullet points, and a
   hazard-themed graphic, in the style of the reference report.

## What changed vs. the winter prototype

| Area | Winter prototype | This system |
| --- | --- | --- |
| Hazards | Ice / snow / cold only | **Heat, flooding, tropical (hurricane/TS/depression), severe storms/tornado, winter, extreme cold, fire weather (Red Flag), high wind, fog/dust, air quality** |
| Season | Winter | **Year-round**, with season context detection |
| Alert parsing | Winter keywords | Full NWS event → hazard category map, year-round |
| Quantitative metrics | None | **Heat index, wind chill, estimated WBGT + activity flag (white→black), wind gusts, humidity** |
| Tropical | None | **NHC active-storm feed** + coastal-county watch |
| Output | PDF only | PDF **+ themed infographic PNGs** with bolded keywords |
| Robustness | Single source | Per-county graceful degradation; offline **demo mode** |

## Hazard coverage

`extreme_heat`, `tropical`, `flood`, `severe_storm`, `winter_storm`,
`extreme_cold`, `fire_weather`, `wind`, `fog_dust`, `air_quality`, plus a
`general` fallback. Each has its own theme color, scoring weight, infographic
metric tiles, and standard NWS safety guidance.

### "Red flag" vs. "black flag"
Both senses are supported:
- **Red Flag Warning** — NWS *fire weather* product (the `fire_weather` category).
- **Activity flags (white/green/yellow/red/black)** — heat-stress flags computed
  from an **estimated WBGT** for outdoor-work/athletic operations. A *black flag*
  appears automatically when conditions cross the extreme heat-stress threshold.

## Install

```bash
pip install -r weather_intel/requirements.txt
```

Optional: a local [Ollama](https://ollama.com) model (e.g. `gemma3:27b`) for
richer narratives. Without it, the system uses deterministic templates.

## Run

```bash
# Live data from NWS + NHC
python -m weather_intel.run

# Offline demo using bundled multi-hazard sample data (great for showcasing)
python -m weather_intel.run --demo

# Skip the LLM and use templates
python -m weather_intel.run --demo --no-llm

# Limit infographics to specific counties
python -m weather_intel.run --counties Travis Harris
```

Outputs are written to `output/` (configurable with `--output`):
`weather_risk_report_<timestamp>.pdf` and `infographic_<County>_<timestamp>.png`.

## Architecture

```
weather_intel/
  config.py          Counties, API endpoints, risk thresholds, PDF/styling config
  hazards.py         Hazard taxonomy, NWS event mapping, heat index/wind chill/WBGT, seasons
  data_agent.py      NWS alerts + gridpoint forecast + NHC tropical feed
  analysis_agent.py  Multi-hazard scoring, dominant hazard, impacts, timeline, metric tiles
  narrative_agent.py LLM (Ollama) executive + county narratives, template fallback
  infographic.py     Pillow report-card generator (bold keywords, bullets, themed graphic)
  pdf_report.py      Year-round executive PDF (embeds infographics)
  orchestrator.py    Pipeline coordinator (live / demo modes)
  sample_data.py     Bundled multi-hazard scenario for offline runs
  run.py             CLI entry point
```

## Adding a county

Add an entry to `COUNTIES` in `config.py` with its FIPS code and coordinates.
The NWS county alert zone (`TXC` + last three FIPS digits) and forecast lookup
are derived automatically.

## Design principle

The system is **information only**. Narrative prose contains no recommendations;
the infographic safety strip reproduces standard NWS public messaging for the
relevant hazard. Decision-making remains with leadership.
