"""Prompt template for redevelopment blueprint generation — Version 1.

Takes the output of an image analysis and generates a redevelopment
concept with sustainability features, cost estimates, and phasing.

This is the "vision" layer — turning observations into actionable
redevelopment plans that a mayor can take to a council meeting.
"""

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """\
You are an expert urban redevelopment planner and sustainable design \
strategist working for Mays Forge OS. You specialize in transforming \
underutilized urban sites in small cities into sustainable, productive \
community assets.

You are generating a redevelopment concept based on a site assessment \
that has already been completed. Your job is to propose a specific, \
actionable redevelopment plan that is realistic for a small city \
(population 2,000-20,000) with limited budgets.

Rules:
- Be specific about what to build and where on the site.
- Include sustainability features that are practical, not aspirational. \
  Rain gardens, permeable paving, and rooftop solar are practical. \
  Vertical farms and hydrogen fuel cells are not for a small town.
- Provide rough cost estimates in ranges. Be honest about uncertainty.
- Phase the project so the city can start small and expand. Phase 1 \
  should be achievable for under $500,000.
- Reference specific funding sources (USDA Rural Development, EPA \
  Brownfields, IDOT grants, CDBG, etc.) that small Illinois towns \
  can actually access.
- The concept should be something a public works director can present \
  to a city council in 10 minutes and get a "yes, let's explore this."
"""

USER_PROMPT_TEMPLATE = """\
Based on the following site assessment, generate a redevelopment concept.

## Site Assessment Results

**Site Type:** {site_type}
**Condition:** {condition}

**Description:** {scene_description}

**Key Observations:**
{observations_text}

**Sustainability Opportunities Identified:**
{opportunities_text}

**Estimated Characteristics:**
{characteristics_text}

Generate a complete redevelopment blueprint for this site.
"""

BLUEPRINT_TOOL_SCHEMA = {
    "name": "record_blueprint",
    "description": (
        "Record the redevelopment blueprint concept. "
        "Call this tool exactly once with your complete plan."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "concept_name",
            "vision_statement",
            "phases",
            "sustainability_features",
            "funding_strategy",
            "estimated_total_cost",
        ],
        "properties": {
            "concept_name": {
                "type": "string",
                "description": (
                    "A compelling name for the redevelopment concept, "
                    "e.g., 'Railroad Heritage Green District'."
                ),
            },
            "vision_statement": {
                "type": "string",
                "description": (
                    "2-3 sentence vision of what this site becomes. "
                    "Written for a mayor or council member, not a planner."
                ),
            },
            "phases": {
                "type": "array",
                "description": "Phased implementation plan, ordered chronologically.",
                "items": {
                    "type": "object",
                    "required": [
                        "phase_number",
                        "name",
                        "description",
                        "key_elements",
                        "estimated_cost",
                        "timeline",
                    ],
                    "properties": {
                        "phase_number": {"type": "integer"},
                        "name": {
                            "type": "string",
                            "description": "Short phase name, e.g., 'Foundation & Safety'.",
                        },
                        "description": {
                            "type": "string",
                            "description": "What happens in this phase. 2-3 sentences.",
                        },
                        "key_elements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific things built or installed in this phase.",
                        },
                        "estimated_cost": {
                            "type": "string",
                            "description": "Cost range, e.g., '$150,000 - $250,000'.",
                        },
                        "timeline": {
                            "type": "string",
                            "description": "Duration, e.g., '6-9 months'.",
                        },
                    },
                },
            },
            "sustainability_features": {
                "type": "array",
                "description": "Specific sustainability elements included in the plan.",
                "items": {
                    "type": "object",
                    "required": ["feature", "benefit", "phase"],
                    "properties": {
                        "feature": {
                            "type": "string",
                            "description": "What it is, e.g., 'Bioswale stormwater system'.",
                        },
                        "benefit": {
                            "type": "string",
                            "description": "Quantified benefit where possible.",
                        },
                        "phase": {
                            "type": "integer",
                            "description": "Which phase this is built in.",
                        },
                    },
                },
            },
            "funding_strategy": {
                "type": "object",
                "required": ["sources", "approach"],
                "properties": {
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "amount", "likelihood"],
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Funding source name.",
                                },
                                "amount": {
                                    "type": "string",
                                    "description": "Potential amount, e.g., '$50,000 - $200,000'.",
                                },
                                "likelihood": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                            },
                        },
                    },
                    "approach": {
                        "type": "string",
                        "description": (
                            "2-3 sentence strategy for how to fund this project. "
                            "Be specific about which grants to apply for first."
                        ),
                    },
                },
            },
            "estimated_total_cost": {
                "type": "string",
                "description": "Total project cost range across all phases.",
            },
        },
    },
}


def build_blueprint_prompt(
    *,
    site_type: str,
    condition: str,
    scene_description: str,
    observations: list[dict[str, str]],
    opportunities: list[dict[str, str]],
    characteristics: dict[str, object],
) -> str:
    """Build the user prompt from image analysis results."""
    obs_lines = []
    for i, obs in enumerate(observations, 1):
        obs_lines.append(f"{i}. [{obs.get('category', '')}] {obs.get('detail', '')}")

    opp_lines = []
    for i, opp in enumerate(opportunities, 1):
        opp_lines.append(f"{i}. [{opp.get('feasibility', '')}] {opp.get('opportunity', '')}")

    char_lines = []
    if characteristics.get("estimated_lot_size"):
        char_lines.append(f"- Lot size: {characteristics['estimated_lot_size']}")
    if characteristics.get("vegetation_coverage_pct") is not None:
        char_lines.append(f"- Vegetation: {characteristics['vegetation_coverage_pct']}%")
    if characteristics.get("impervious_surface_pct") is not None:
        char_lines.append(f"- Impervious surface: {characteristics['impervious_surface_pct']}%")

    return USER_PROMPT_TEMPLATE.format(
        site_type=site_type,
        condition=condition,
        scene_description=scene_description,
        observations_text="\n".join(obs_lines) or "None provided.",
        opportunities_text="\n".join(opp_lines) or "None provided.",
        characteristics_text="\n".join(char_lines) or "Not available.",
    )
