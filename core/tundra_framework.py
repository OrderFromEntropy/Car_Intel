"""
Tundra Evaluation Framework — hard-coded rules for 2nd-gen Toyota Tundra scoring.

This module owns all rule constants and assembles the ranker system prompt
so that agents.py stays clean and the rules live in one place.
"""

from __future__ import annotations

# ── State provenance categories ──────────────────────────────────────────────

APPROVED_STATES: set[str] = {"AZ", "NM", "NV", "TX", "OK"}
# Southern CA metros are handled as a special case under CONDITIONAL

CONDITIONAL_STATES: dict[str, str] = {
    "CA": (
        "Southern CA (LA / San Diego metro) is APPROVED. "
        "Bay Area, Sacramento, coastal/mountain regions = FLAG for manual zip verification."
    ),
    "CO": (
        "Eastern plains zip codes are acceptable. "
        "Denver metro and I-70/mountain corridor = DISQUALIFY (salt/winter use)."
    ),
    "VA": (
        "South of Richmond is acceptable. "
        "Northern VA (DC suburbs, zip codes 20100-20199, 22000-22399) = DISQUALIFY."
    ),
    "NC": (
        "Piedmont and coastal plain are acceptable. "
        "Western NC mountains (zip codes 28700s, 28800s) = DISQUALIFY."
    ),
    "TN": (
        "West TN / Memphis area is acceptable. "
        "East TN mountains (zip codes 37600-37999) = DISQUALIFY."
    ),
}

DISQUALIFIED_STATES: set[str] = {
    "IL", "IN", "MI", "OH", "PA", "NY", "NJ", "MA", "MN", "WI",
    "MO", "KS", "NE", "IA", "ND", "SD", "MT", "WY", "ID", "UT",
    "ME", "NH", "VT", "CT", "RI", "DE", "MD", "WV", "KY",
    "WA", "OR",  # Pacific NW — rain/salt on mountain passes
    "AK", "HI",
}

ALL_CONDITIONAL_STATE_CODES: set[str] = set(CONDITIONAL_STATES.keys())

# ── Color preference scoring ──────────────────────────────────────────────────

COLOR_RANK: dict[str, int] = {
    "smoked mesquite": 5,     # dark olive-brown, discontinued ~2019
    "quicksand": 4,            # tan
    "magnetic gray": 3,
    "cement": 3,
    "lunar rock": 3,
    "black": 2,
    "midnight black metallic": 2,
    "dark green": 2,
    "white": 1,
    "super white": 1,
    "silver sky metallic": 1,
    "silver": 1,
}
COLOR_LOUD_PENALTY = -2       # applied to bright/loud colors not in the above list

# ── Global mandatory requirements ────────────────────────────────────────────

GLOBAL_MANDATORY = {
    "cab": "CrewMax only",
    "engine": "5.7L V8 only",
    "drivetrain": "4x4 only (no 2WD / RWD)",
    "tank": "38-gallon required. 32-gallon = hard disqualifier",
    "tow_package": "Required",
    "title": "No salvage, rebuilt, or branded titles",
    "carfax_structural": "Structural damage OR airbag deployment = automatic disqualifier",
    "aftermarket": (
        "Undocumented suspension lift, differential, drivetrain, or supercharger = disqualifier. "
        "Bolt-ons (exhaust, intake, floor mats, cosmetic) are acceptable."
    ),
    "provenance": "Must have spent full life in approved or conditional states only",
}

# ── F-tier hard disqualifiers (any one triggers F with no appeal) ─────────────

F_TIER_DISQUALIFIERS = [
    "150,000+ miles",
    "Salt state / northern / midwest provenance or more than one oil-change interval in a disqualified state",
    "Salvage, rebuilt, or branded title",
    "Structural damage or airbag deployment on Carfax",
    "32-gallon fuel tank",
    "Non-CrewMax cab (regular cab, access cab, double cab)",
    "RWD / 2WD drivetrain",
    "Undocumented suspension, differential, or drivetrain aftermarket work",
]

# ── Tier definitions (used verbatim in the LLM prompt) ───────────────────────

TIER_DEFINITIONS = """
TIER SCORING RUBRIC — apply in order after all disqualifiers pass:

S TIER — Grail Truck (all criteria must be met):
  • Year: 2021 only
  • Mileage: < 50,000
  • Owners: 1
  • Trim: 1794 Edition only
  • TRD Off-Road package: Required
  • CPO: Toyota CPO Gold only
  • Price: ≥ 5% below KBB/Edmunds Fair Market Value
  • Service: Documented every 3,000–7,000 miles at Toyota dealership
  • Extras: Original window sticker or VIN build sheet present

A TIER — Strong Buy:
  • Year: 2018–2021
  • Mileage: < 50,000
  • Owners: ≤ 2 (must be gap-free if 2-owner)
  • Trim: 1794, Limited, or Platinum
  • TRD Off-Road package: Required
  • CPO: Toyota CPO Silver acceptable
  • Price: Within ±5% of KBB/Edmunds Fair Market Value
  • Service: Documented every 3,000–7,000 miles

B TIER — Solid Deal:
  • Year: 2016–2021
  • Mileage: < 75,000
  • Owners: ≤ 2
  • Trim: 1794, Limited, Platinum; SR5 only if price meaningfully reflects trim discount
  • TRD Off-Road package: Preferred not required. Presence = B+ modifier
  • CPO: Not expected; presence = automatic B+ modifier
  • Price: 5–8% below KBB/Edmunds
  • PPI: Seller must consent to pre-purchase inspection
  • Service: Documented at minimum every 7,000 miles
  B TIER MODIFIERS (apply after base assignment):
    - CPO present → upgrade to B+
    - Factory TRD Off-Road → upgrade to B+ or B++
    - Aftermarket beyond bolt-ons (diff, drivetrain, supercharged, suspension) → floor at B, no upgrade

C TIER — Proceed Carefully:
  • Year: 2014–2021
  • Mileage: < 100,000
  • Owners: ≤ 3
  • Trim: 1794, Limited, Platinum; SR5 acceptable if price reflects discount
  • Price: 8–12% below KBB/Edmunds
  • PPI: Required — non-negotiable. Refusal to allow PPI = walk.
  • Service: Documented at minimum every 7,000 miles. Gaps = lower offer or walk.
  • Structural Carfax events = DISQUALIFY (no exceptions at this tier)
  • Undocumented aftermarket suspension = walk regardless of price

D TIER — High-Risk Buy:
  • Year: 2014–2021
  • Mileage: < 150,000
  • Owners: ≤ 3
  • Trim: Any (color/trim irrelevant — buy on provenance and price only)
  • Price: 10–15% below KBB/Edmunds minimum
  • PPI: Mandatory. Expanded scope: compression test, leakdown test, transmission fluid
         analysis, transfer case inspection, differential inspection
  • Service: Pristine gap-free records essentially required. Cannot produce records = walk.
  • Post-purchase budget: Flag $2,500–$5,000 immediate maintenance/refresh as expected cost
  • Price as a work truck. Cosmetic damage = negotiating chip, not a dealbreaker.

F TIER — Do Not Purchase (not purchaseable — hard stop).
""".strip()


def build_ranker_system_prompt() -> str:
    """Assemble the full ranker system prompt including all rules."""

    approved_str = ", ".join(sorted(APPROVED_STATES))
    disq_str = ", ".join(sorted(DISQUALIFIED_STATES))
    cond_lines = "\n".join(f"  {st}: {desc}" for st, desc in CONDITIONAL_STATES.items())
    mandatory_lines = "\n".join(f"  • {k}: {v}" for k, v in GLOBAL_MANDATORY.items())
    f_lines = "\n".join(f"  • {d}" for d in F_TIER_DISQUALIFIERS)

    return f"""You are the CarIntel Tundra Ranking Engine — an expert in 2nd-generation Toyota Tundra
(2014–2021) evaluation. You apply a strict multi-step scoring rubric.

═══════════════════════════════════════════════════════════════
EVALUATION PIPELINE — run these steps in order for each listing:
═══════════════════════════════════════════════════════════════

STEP 1 — GLOBAL MANDATORY CHECKS (any failure = F, stop):
{mandatory_lines}

STEP 2 — F TIER HARD DISQUALIFIERS (any match = F, stop):
{f_lines}

STEP 3 — STATE PROVENANCE CHECK:
  Approved (clean):    {approved_str}
  Also approved:       Southern CA (LA / San Diego metro)
  Conditional (flag):
{cond_lines}
  Disqualified:        {disq_str}
  → Disqualified state = F tier.
  → Conditional state = add a FLAG entry, assign tier based on other criteria,
    note "Verify state registration zip before purchase."
  → If state cannot be determined from the snippet, add a FLAG: "Confirm state provenance."

STEP 4 — TIER ASSIGNMENT:
{TIER_DEFINITIONS}

STEP 5 — COLOR SCORING (bonus/penalty only, never changes tier by itself):
  Best:    Smoked Mesquite (+2), Quicksand (+1)
  Good:    Magnetic Gray / Cement / Lunar Rock (neutral)
  OK:      Black / Dark Green / White (neutral)
  Flag:    Bright or loud colors (flag as negative score modifier)

STEP 6 — OUTPUT FORMAT:
Return ONLY a JSON object with a single key "rankings" containing a list.
Each entry must have EXACTLY these keys:
  • "index":          integer (0-based index in the batch)
  • "tier":           one of S, A, B, C, D, F
  • "disqualifiers":  list of strings (empty list if none) — hard rule violations found
  • "flags":          list of strings (empty list if none) — yellow flags needing manual verification
  • "tier_reasoning": one concise sentence explaining the tier assignment

IMPORTANT RULES FOR UNCERTAIN DATA:
  - If a required field (cab type, engine, drivetrain, tank size) is NOT mentioned in the snippet,
    do NOT assume it qualifies — add a FLAG like "Confirm CrewMax cab" rather than assuming.
  - If provenance state cannot be determined, FLAG it — do not default to approved.
  - Never upgrade a tier due to missing information. Only downgrade or flag.
  - If listing is clearly a non-Tundra or wrong generation, assign F and note in disqualifiers.

Respond with ONLY the JSON. No prose. No markdown fences outside the JSON."""


def build_summarizer_context(tier: str) -> str:
    """Return tier-specific guidance for the summarizer agent."""
    guidance = {
        "S": (
            "This is a Grail Truck — S tier. Highlight all premium qualifiers: "
            "CPO Gold status, 1794 Edition, TRD Off-Road, pristine service history, "
            "documented provenance, and price relative to market. Convey genuine excitement "
            "while staying factual. Close with the single strongest selling point."
        ),
        "A": (
            "Strong Buy — A tier. Lead with the clean provenance and why the value proposition "
            "is compelling. Mention the trim, mileage, and any CPO coverage. "
            "Note what makes this stand out versus average market listings."
        ),
        "B": (
            "Solid Deal — B tier. Explain what earns the B and what the buyer should verify. "
            "Note any modifiers (CPO, TRD Off-Road) or concerns (aftermarket work). "
            "Remind buyer that PPI consent is required before proceeding."
        ),
        "C": (
            "Proceed Carefully — C tier. Be candid about why this truck needs scrutiny. "
            "Identify the specific weaknesses (mileage, owners, service gaps, price). "
            "Emphasize that PPI is non-negotiable and note any conditional flags."
        ),
        "D": (
            "High-Risk Buy — D tier. Be direct: this is a work-truck price play. "
            "State the expected $2,500–$5,000 post-purchase budget. "
            "Highlight what would make it worth pursuing (discount depth, clean provenance) "
            "and what would make it a walk (no service records, PPI refusal)."
        ),
        "F": (
            "Do Not Purchase — F tier. Clearly state the disqualifying factor(s). "
            "Be definitive: this is not a purchaseable option. "
            "Do not soften or hedge the recommendation."
        ),
    }
    return guidance.get(tier, "Summarize this listing factually and concisely.")
