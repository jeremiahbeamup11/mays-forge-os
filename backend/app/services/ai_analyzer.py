"""AI analysis service — Claude integration for municipal data analysis.

This module is the bridge between parsed data (from csv_parser.py) and
structured intelligence (stored in the files table's analysis column).

Design principles:
1. Every AI call returns structured data via tool_use, never free text.
2. Every AI call is logged with model, tokens, duration, and estimated cost.
3. The caller decides what to do with the result — this module doesn't
   write to the database. Separation of concerns.
4. Errors are caught and wrapped in typed exceptions, never leaked as
   raw API errors to the caller.

Cost tracking:
  Claude Sonnet 4 pricing (as of April 2026):
    Input:  $3.00 / million tokens
    Output: $15.00 / million tokens
  These rates are hardcoded here for logging purposes only — they don't
  affect billing (Anthropic bills your account directly). Update them if
  pricing changes.
"""

import time
from dataclasses import dataclass
from typing import Any

import anthropic

from app.config import settings
from app.core.logging import get_logger
from app.services.prompts.csv_analysis_v1 import (
    ANALYSIS_TOOL_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
)

_log = get_logger(__name__)

# Model selection. Sonnet is the sweet spot for this use case:
# fast enough for interactive use, smart enough for real analysis,
# cheap enough to not bankrupt a bootstrapped startup.
_MODEL = "claude-sonnet-4-6"

# Cost per token for logging. Update if Anthropic changes pricing.
_INPUT_COST_PER_MILLION = 3.00
_OUTPUT_COST_PER_MILLION = 15.00


class AnalysisError(Exception):
    """Raised when the AI analysis fails for any reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


@dataclass(frozen=True)
class AnalysisResult:
    """The structured output from a successful AI analysis call."""

    analysis: dict[str, Any]
    prompt_version: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_seconds: float
    estimated_cost_usd: float


def _get_client() -> anthropic.Anthropic:
    """Build an Anthropic client using the configured API key."""
    if not settings.ANTHROPIC_API_KEY:
        raise AnalysisError(
            "missing_api_key",
            "ANTHROPIC_API_KEY is not configured. Set it in .env.",
        )
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


async def analyze_csv(csv_context: str, filename: str = "unknown.csv") -> AnalysisResult:
    """Send a CSV summary to Claude and get structured municipal analysis back.

    Args:
        csv_context: The output of CsvSummary.to_prompt_context() — a
            markdown-formatted description of the CSV's structure and contents.
        filename: Original filename, used only for logging.

    Returns:
        AnalysisResult with the structured analysis and usage metadata.

    Raises:
        AnalysisError on any failure (API error, malformed response, etc).
    """
    client = _get_client()
    user_prompt = build_user_prompt(csv_context)

    _log.info(
        "ai_analysis_starting",
        filename=filename,
        model=_MODEL,
        prompt_version=PROMPT_VERSION,
    )

    start = time.perf_counter()

    try:
        response = client.messages.create(  # type: ignore[call-overload]
            model=_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[
                {
                    "type": "custom",
                    "name": ANALYSIS_TOOL_SCHEMA["name"],
                    "description": ANALYSIS_TOOL_SCHEMA["description"],
                    "input_schema": ANALYSIS_TOOL_SCHEMA["input_schema"],
                },
            ],
            tool_choice={"type": "tool", "name": "record_analysis"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.AuthenticationError as exc:
        raise AnalysisError("auth_failed", "Anthropic API key is invalid.") from exc
    except anthropic.RateLimitError as exc:
        raise AnalysisError(
            "rate_limited",
            "Anthropic API rate limit hit. Try again in a moment.",
        ) from exc
    except anthropic.APIError as exc:
        raise AnalysisError("api_error", f"Anthropic API error: {exc}") from exc

    duration = time.perf_counter() - start

    # Extract the tool use block from the response.
    tool_block = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "record_analysis":
            tool_block = block
            break

    if tool_block is None:
        _log.error(
            "ai_analysis_no_tool_use",
            filename=filename,
            response_content=[str(b) for b in response.content],
        )
        raise AnalysisError(
            "no_tool_use",
            "Claude did not return a tool_use block. This is unexpected.",
        )

    analysis_data = tool_block.input
    if not isinstance(analysis_data, dict):
        raise AnalysisError(
            "malformed_response",
            "Tool use input is not a dictionary.",
        )

    # Token usage and cost estimation.
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    estimated_cost = (
        input_tokens * _INPUT_COST_PER_MILLION / 1_000_000
        + output_tokens * _OUTPUT_COST_PER_MILLION / 1_000_000
    )

    _log.info(
        "ai_analysis_complete",
        filename=filename,
        model=_MODEL,
        prompt_version=PROMPT_VERSION,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_seconds=round(duration, 2),
        estimated_cost_usd=round(estimated_cost, 4),
        findings_count=len(analysis_data.get("findings", [])),
        recommendations_count=len(analysis_data.get("recommendations", [])),
    )

    return AnalysisResult(
        analysis=analysis_data,
        prompt_version=PROMPT_VERSION,
        model=_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_seconds=round(duration, 2),
        estimated_cost_usd=round(estimated_cost, 4),
    )
