"""Prompt template for PDF document analysis — Version 1.

Analyzes structured data extracted from municipal PDF documents
(budgets, annual financial reports, capital plans). The extraction
layer has already parsed tables and text sections with page references;
Claude's job is to interpret the data through the municipal
infrastructure and sustainability lens.

VERSION HISTORY:
  v1 (2026-06-05): Initial version. Municipal financial document analysis
  with page-traceable citations.

DESIGN PRINCIPLES:
  1. Claude receives pre-extracted structured data (tables with page
     numbers, text sections), NOT raw PDF bytes or full-document text.
  2. Every finding must cite the source page number so the user can
     verify against the original document.
  3. Output forced into strict JSON schema via tool_use.
  4. Adapted from csv_analysis_v1 — same domain lens (infrastructure,
     sustainability), same actionability bar, but tuned for financial
     documents with fiscal year comparisons, fund structures, and
     capital planning.
"""

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """\
You are an expert municipal finance analyst working for Mays Forge OS, \
an AI platform that helps small cities become more self-sustaining. You \
specialize in analyzing municipal budgets, annual financial reports, \
capital improvement plans, and audit documents.

You are analyzing a PDF document uploaded by a city's public works \
department or finance office. The document has been pre-processed: \
tables have been extracted as structured data and text has been \
organized by section, all with source page numbers.

Rules:
- CITE PAGE NUMBERS. Every finding must reference the specific page(s) \
  where the supporting data appears. Use the format "(page X)" or \
  "(pages X-Y)". This is non-negotiable — the user needs to verify \
  your claims against the original document.
- Be specific with numbers. "Revenue increased" is useless. \
  "General Fund revenues increased 4.2% from $4,247,815 (FY2024) to \
  $4,449,976 (FY2026), driven primarily by a $31,000 increase in \
  property tax collections (page 15)" is valuable.
- Identify fiscal health indicators: fund balance trends, debt service \
  ratios, revenue concentration risks, unfunded liabilities.
- Flag infrastructure investment gaps: deferred maintenance, capital \
  plan underfunding, aging asset replacement schedules.
- Spot sustainability opportunities: energy costs that could be reduced \
  by efficiency upgrades, stormwater infrastructure needs, fleet \
  electrification potential.
- Distinguish CONFIRMED findings (directly stated in the document) from \
  INFERRED findings (reasonable conclusions that need verification).
- If the document is incomplete or the extraction missed key tables, \
  say so rather than guessing at numbers you don't have.
- Frame everything for a public works director or mayor, not a CPA.
"""

USER_PROMPT_TEMPLATE = """\
Analyze the following municipal document and provide structured insights \
with page citations.

{pdf_context}

Based on this document, provide:
1. A summary of what this document is and what fiscal period it covers.
2. Key financial findings — specific, quantified observations about the \
   municipality's fiscal health, infrastructure spending, revenue trends, \
   and fund balances. Every finding must cite the source page number.
3. Infrastructure and sustainability findings — what the financial data \
   reveals about infrastructure investment levels, deferred maintenance, \
   capital planning adequacy, and sustainability spending.
4. Actionable recommendations — concrete steps tied to specific findings.
5. Data quality notes about the extraction — any tables that appear \
   incomplete or sections that may need manual verification.
"""

ANALYSIS_TOOL_SCHEMA = {
    "name": "record_pdf_analysis",
    "description": (
        "Record the structured analysis of a municipal PDF document. "
        "Call this tool exactly once with your complete analysis."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "document_type",
            "fiscal_period",
            "summary",
            "financial_findings",
            "infrastructure_findings",
            "recommendations",
            "data_quality",
        ],
        "properties": {
            "document_type": {
                "type": "string",
                "enum": [
                    "annual_budget",
                    "annual_financial_report",
                    "capital_improvement_plan",
                    "audit_report",
                    "other",
                ],
                "description": "What kind of municipal document this is.",
            },
            "fiscal_period": {
                "type": "string",
                "description": (
                    "The fiscal year or period covered, "
                    "e.g., 'FY2026 (April 1, 2025 - March 31, 2026)'."
                ),
            },
            "summary": {
                "type": "string",
                "description": (
                    "3-5 sentence overview: what this document is, which "
                    "municipality, key headline numbers (total budget, "
                    "total net position, etc.) with page citations."
                ),
            },
            "financial_findings": {
                "type": "array",
                "description": (
                    "Key financial findings, ordered by impact. "
                    "Every finding must include page citations."
                ),
                "items": {
                    "type": "object",
                    "required": [
                        "title",
                        "detail",
                        "source_pages",
                        "confidence",
                        "category",
                    ],
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": (
                                "Short label, e.g., "
                                "'General Fund balance grew 0.8% year-over-year'."
                            ),
                        },
                        "detail": {
                            "type": "string",
                            "description": (
                                "Full explanation with specific dollar amounts "
                                "and percentages from the document. "
                                "2-4 sentences. Must include page references."
                            ),
                        },
                        "source_pages": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": ("Page numbers where the supporting data appears."),
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["confirmed", "inferred"],
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "revenue",
                                "expenditure",
                                "fund_balance",
                                "debt",
                                "capital",
                                "pension",
                                "infrastructure",
                                "sustainability",
                                "general",
                            ],
                        },
                    },
                },
            },
            "infrastructure_findings": {
                "type": "array",
                "description": (
                    "What the financial data reveals about infrastructure "
                    "and sustainability. Page citations required."
                ),
                "items": {
                    "type": "object",
                    "required": [
                        "title",
                        "detail",
                        "source_pages",
                        "category",
                    ],
                    "properties": {
                        "title": {"type": "string"},
                        "detail": {
                            "type": "string",
                            "description": (
                                "2-4 sentences with dollar amounts and page references."
                            ),
                        },
                        "source_pages": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "water",
                                "energy",
                                "waste",
                                "stormwater",
                                "roads_sidewalks",
                                "buildings",
                                "fleet",
                                "general",
                            ],
                        },
                    },
                },
            },
            "recommendations": {
                "type": "array",
                "description": "Actionable steps tied to findings above.",
                "items": {
                    "type": "object",
                    "required": [
                        "action",
                        "rationale",
                        "priority",
                        "estimated_impact",
                        "source_pages",
                    ],
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Specific action to take.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": ("Why this matters, tied to a finding above."),
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low"],
                        },
                        "estimated_impact": {
                            "type": "string",
                            "description": (
                                "Rough estimate of savings, risk reduction, or sustainability gain."
                            ),
                        },
                        "source_pages": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": ("Pages supporting this recommendation."),
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
                        "description": ("How well the extracted data supports analysis."),
                    },
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Specific extraction gaps or tables that need "
                            "manual verification. Empty array if none."
                        ),
                    },
                },
            },
        },
    },
}


def build_user_prompt(pdf_context: str) -> str:
    """Insert the PDF extraction summary into the user prompt template."""
    return USER_PROMPT_TEMPLATE.format(pdf_context=pdf_context)
