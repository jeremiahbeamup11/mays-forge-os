"""Prompt template for image analysis — Version 1.

This prompt instructs Claude Vision to analyze photos of municipal
infrastructure, vacant lots, buildings, and urban environments. It produces
structured observations relevant to sustainability planning and
redevelopment.

VERSION HISTORY:
  v1 (2026-04-24): Initial version. General municipal/urban image analysis
  with focus on lot assessment, infrastructure condition, and
  redevelopment potential.

DESIGN PRINCIPLES:
  1. Claude receives the image directly via the vision API — no
     preprocessing or feature extraction needed.
  2. Output is forced into a strict JSON schema via tool_use.
  3. The prompt is domain-specific: we're not asking "what's in this
     photo" generically, we're asking "what does this tell us about
     urban infrastructure and redevelopment potential."
  4. We ask Claude to estimate physical characteristics (lot size,
     condition, vegetation) that would be relevant to a public works
     director or urban planner.
"""

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """\
You are an expert urban planner and infrastructure assessor working for \
Mays Forge OS, an AI platform that helps small cities become more \
self-sustaining. You specialize in evaluating vacant lots, aging \
infrastructure, buildings, and urban environments for redevelopment and \
sustainability potential.

You are analyzing a photo uploaded by a city's public works department. \
Your job is to observe what's in the image and assess it through the lens \
of municipal planning, infrastructure health, and sustainability opportunity.

Rules:
- Describe what you actually see. Do not fabricate details that aren't \
  visible in the image.
- Estimate physical characteristics where possible (approximate lot size, \
  building condition, vegetation coverage) but clearly label estimates \
  as approximate.
- Assess condition honestly: if something looks deteriorated, say so \
  with specifics about what you observe.
- Identify sustainability opportunities visible in the image: solar \
  potential (roof orientation, shading), rainwater capture potential, \
  green space, etc.
- If the image is not relevant to municipal planning (e.g., a selfie, \
  a screenshot, food), say so and provide minimal analysis.
- Frame observations in terms useful to a non-technical public works \
  director or mayor.
"""

USER_PROMPT = """\
Analyze this image from a municipal planning perspective. Describe what \
you see, assess the condition of any infrastructure or land visible, and \
identify any opportunities for sustainable redevelopment or improvement.
"""

ANALYSIS_TOOL_SCHEMA = {
    "name": "record_image_analysis",
    "description": (
        "Record the structured analysis of a municipal/urban image. "
        "Call this tool exactly once with your complete analysis."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "scene_description",
            "site_type",
            "observations",
            "sustainability_opportunities",
            "condition_assessment",
        ],
        "properties": {
            "scene_description": {
                "type": "string",
                "description": (
                    "2-3 sentence overview of what the image shows. "
                    "Be specific about location type, visible structures, "
                    "and general condition."
                ),
            },
            "site_type": {
                "type": "string",
                "enum": [
                    "vacant_lot",
                    "residential",
                    "commercial",
                    "industrial",
                    "infrastructure",
                    "park_greenspace",
                    "mixed_use",
                    "other",
                ],
                "description": "Primary classification of what the image shows.",
            },
            "observations": {
                "type": "array",
                "description": (
                    "Specific observations about the site, ordered by relevance "
                    "to municipal planning."
                ),
                "items": {
                    "type": "object",
                    "required": ["category", "detail", "planning_relevance"],
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": [
                                "land_use",
                                "vegetation",
                                "structures",
                                "infrastructure",
                                "access_connectivity",
                                "environmental",
                                "safety",
                            ],
                            "description": "What aspect of the site this observation relates to.",
                        },
                        "detail": {
                            "type": "string",
                            "description": (
                                "What you specifically observe. 1-3 sentences. "
                                "Reference visible features directly."
                            ),
                        },
                        "planning_relevance": {
                            "type": "string",
                            "description": (
                                "Why this observation matters for municipal "
                                "planning or redevelopment decisions."
                            ),
                        },
                    },
                },
            },
            "sustainability_opportunities": {
                "type": "array",
                "description": "Potential sustainability improvements visible from the image.",
                "items": {
                    "type": "object",
                    "required": ["opportunity", "rationale", "feasibility"],
                    "properties": {
                        "opportunity": {
                            "type": "string",
                            "description": (
                                "Specific sustainability action, e.g., "
                                "'Install rooftop solar on south-facing roof surface'."
                            ),
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this is feasible based on what's visible.",
                        },
                        "feasibility": {
                            "type": "string",
                            "enum": ["high", "medium", "low", "needs_investigation"],
                        },
                    },
                },
            },
            "condition_assessment": {
                "type": "object",
                "required": ["overall_condition", "details"],
                "properties": {
                    "overall_condition": {
                        "type": "string",
                        "enum": ["excellent", "good", "fair", "poor", "critical"],
                    },
                    "details": {
                        "type": "string",
                        "description": (
                            "Explanation of condition assessment. What specific "
                            "visual evidence supports this rating?"
                        ),
                    },
                },
            },
            "estimated_characteristics": {
                "type": "object",
                "description": "Rough physical estimates. All are approximate.",
                "properties": {
                    "estimated_lot_size": {
                        "type": "string",
                        "description": "Approximate lot size if estimable, e.g., '~0.5 acres'.",
                    },
                    "vegetation_coverage_pct": {
                        "type": "integer",
                        "description": "Estimated percentage of visible area covered by vegetation.",
                    },
                    "impervious_surface_pct": {
                        "type": "integer",
                        "description": (
                            "Estimated percentage covered by pavement, concrete, "
                            "or buildings (relevant for stormwater)."
                        ),
                    },
                },
            },
        },
    },
}
