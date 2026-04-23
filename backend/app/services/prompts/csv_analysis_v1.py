"""Prompt template for CSV data analysis — Version 1.

This prompt instructs Claude to analyze a parsed CSV summary and return
structured insights relevant to municipal infrastructure and sustainability.

VERSION HISTORY:
  v1 (2026-04-21): Initial version. General municipal data analysis with
  focus on infrastructure inefficiencies, risks, and recommendations.

DESIGN PRINCIPLES:
  1. The prompt receives a pre-parsed summary (from csv_parser.py), NOT
     raw CSV bytes. This keeps token usage low and ensures Claude reasons
     about the right abstraction level.
  2. Output is forced into a strict JSON schema via Claude's tool_use
     feature. No free-text parsing, no regex, no "please format as JSON."
  3. The prompt is domain-specific to municipal/urban data. Generic CSV
     analysis tools exist; our value is the sustainability + infrastructure
     lens.
  4. We include explicit instructions about what makes an insight
     "actionable" vs. "obvious." Bob doesn't need Claude to tell him
     "this column has numbers." He needs "your water usage spikes 40%
     every July, suggesting irrigation-driven demand that could be
     offset by rainwater capture on municipal buildings."
"""

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """\
You are an expert municipal infrastructure analyst working for Mays Forge OS, \
an AI platform that helps small cities become more self-sustaining. You \
specialize in water systems, energy infrastructure, waste management, \
stormwater, and urban sustainability.

You are analyzing data uploaded by a city's public works department. Your job \
is to find actionable insights — not obvious observations, but genuine \
findings that would help a small-town public works director make better \
decisions about infrastructure investment, maintenance priorities, and \
sustainability improvements.

Rules:
- Be specific. "Water usage is high" is useless. "Water usage in Zone 3 \
  exceeds the network average by 38%, correlating with the pipe age data \
  showing 60% of Zone 3 infrastructure is past its 30-year service life" \
  is valuable.
- Quantify everything you can. Use the actual numbers from the data.
- Distinguish between CONFIRMED findings (directly supported by the data) \
  and INFERRED findings (reasonable conclusions that would need further \
  investigation to confirm).
- Prioritize findings by potential impact: cost savings, risk reduction, \
  or sustainability improvement.
- If the data is insufficient for meaningful analysis (too few rows, \
  missing key columns, ambiguous meaning), say so honestly rather than \
  fabricating insights.
- Frame recommendations in terms a non-technical public works director \
  would understand and could act on.
"""

USER_PROMPT_TEMPLATE = """\
Analyze the following municipal data file and provide structured insights.

{csv_context}

Based on this data, provide:
1. A brief summary of what this dataset contains and represents.
2. Key findings — specific, quantified observations about patterns, \
   anomalies, inefficiencies, or risks visible in the data.
3. Actionable recommendations — concrete steps the city could take based \
   on these findings, with estimated impact where possible.
4. Data quality notes — any issues with the data that limit analysis \
   (missing values, ambiguous columns, insufficient history, etc.).
"""

# The JSON schema Claude must conform to. Defined as the tool's input_schema
# in Claude's tool_use API. This is NOT a Pydantic model — it's the raw
# JSON Schema that Claude sees. The Pydantic model for parsing the response
# lives in models/analysis.py.
ANALYSIS_TOOL_SCHEMA = {
    "name": "record_analysis",
    "description": (
        "Record the structured analysis of a municipal data file. "
        "Call this tool exactly once with your complete analysis."
    ),
    "input_schema": {
        "type": "object",
        "required": ["summary", "findings", "recommendations", "data_quality"],
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "2-3 sentence overview of what this dataset contains "
                    "and what it tells us about the city's infrastructure."
                ),
            },
            "findings": {
                "type": "array",
                "description": "Key findings from the data, ordered by impact.",
                "items": {
                    "type": "object",
                    "required": ["title", "detail", "confidence", "category"],
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short label, e.g. 'Zone 3 water loss anomaly'.",
                        },
                        "detail": {
                            "type": "string",
                            "description": (
                                "Full explanation with specific numbers from the data. "
                                "2-4 sentences."
                            ),
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["confirmed", "inferred"],
                            "description": (
                                "'confirmed' if directly supported by the data, "
                                "'inferred' if a reasonable conclusion needing verification."
                            ),
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "water",
                                "energy",
                                "waste",
                                "stormwater",
                                "infrastructure",
                                "sustainability",
                                "general",
                            ],
                            "description": "Which infrastructure domain this finding relates to.",
                        },
                    },
                },
            },
            "recommendations": {
                "type": "array",
                "description": "Actionable steps the city should consider.",
                "items": {
                    "type": "object",
                    "required": ["action", "rationale", "priority", "estimated_impact"],
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": (
                                "Specific action to take, e.g. 'Install smart water "
                                "meters in Zone 3 to identify leak sources'."
                            ),
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this action matters, tied to a finding above.",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low"],
                        },
                        "estimated_impact": {
                            "type": "string",
                            "description": (
                                "Rough estimate of savings, risk reduction, or "
                                "sustainability gain. Be specific where possible."
                            ),
                        },
                    },
                },
            },
            "data_quality": {
                "type": "object",
                "required": ["overall_quality", "issues"],
                "properties": {
                    "overall_quality": {
                        "type": "string",
                        "enum": ["excellent", "good", "fair", "poor"],
                        "description": "Overall assessment of data completeness and reliability.",
                    },
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Specific data quality problems that limit analysis. "
                            "Empty array if no issues found."
                        ),
                    },
                },
            },
        },
    },
}


def build_user_prompt(csv_context: str) -> str:
    """Insert the CSV summary into the user prompt template."""
    return USER_PROMPT_TEMPLATE.format(csv_context=csv_context)
