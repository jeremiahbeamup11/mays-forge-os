"""AI analysis service — Claude integration for municipal data analysis.

This module is the bridge between parsed data and structured intelligence.

Supports two analysis modes:
- CSV analysis: text-based, uses csv_parser output as context.
- Image analysis: vision-based, sends the image directly to Claude.

Design principles:
1. Every AI call returns structured data via tool_use, never free text.
2. Every AI call is logged with model, tokens, duration, and estimated cost.
3. The caller decides what to do with the result — this module doesn't
   write to the database.
4. Errors are caught and wrapped in typed exceptions.
"""

import base64
import time
from dataclasses import dataclass
from typing import Any

import anthropic

from app.config import settings
from app.core.logging import get_logger
from app.services.prompts.csv_analysis_v1 import (
    ANALYSIS_TOOL_SCHEMA as CSV_TOOL_SCHEMA,
)
from app.services.prompts.csv_analysis_v1 import (
    PROMPT_VERSION as CSV_PROMPT_VERSION,
)
from app.services.prompts.csv_analysis_v1 import (
    SYSTEM_PROMPT as CSV_SYSTEM_PROMPT,
)
from app.services.prompts.csv_analysis_v1 import (
    build_user_prompt as build_csv_prompt,
)
from app.services.prompts.image_analysis_v1 import (
    ANALYSIS_TOOL_SCHEMA as IMAGE_TOOL_SCHEMA,
)
from app.services.prompts.image_analysis_v1 import (
    PROMPT_VERSION as IMAGE_PROMPT_VERSION,
)
from app.services.prompts.image_analysis_v1 import (
    SYSTEM_PROMPT as IMAGE_SYSTEM_PROMPT,
)
from app.services.prompts.image_analysis_v1 import (
    USER_PROMPT as IMAGE_USER_PROMPT,
)

_log = get_logger(__name__)

_MODEL = "claude-sonnet-4-6"

# Cost per token for logging (approximate).
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


def _compute_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens * _INPUT_COST_PER_MILLION / 1_000_000
        + output_tokens * _OUTPUT_COST_PER_MILLION / 1_000_000,
        4,
    )


def _extract_tool_result(response: anthropic.types.Message, tool_name: str) -> dict[str, Any]:
    """Extract the tool_use block from a Claude response."""
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            if isinstance(block.input, dict):
                return block.input
            raise AnalysisError(
                "malformed_response",
                "Tool use input is not a dictionary.",
            )
    raise AnalysisError(
        "no_tool_use",
        f"Claude did not call the '{tool_name}' tool. This is unexpected.",
    )


async def analyze_csv(csv_context: str, filename: str = "unknown.csv") -> AnalysisResult:
    """Send a CSV summary to Claude and get structured municipal analysis back."""
    client = _get_client()
    user_prompt = build_csv_prompt(csv_context)

    _log.info(
        "ai_analysis_starting",
        filename=filename,
        model=_MODEL,
        prompt_version=CSV_PROMPT_VERSION,
        analysis_type="csv",
    )

    start = time.perf_counter()

    try:
        response = client.messages.create(  # type: ignore[call-overload]
            model=_MODEL,
            max_tokens=4096,
            system=CSV_SYSTEM_PROMPT,
            tools=[
                {
                    "type": "custom",
                    "name": CSV_TOOL_SCHEMA["name"],
                    "description": CSV_TOOL_SCHEMA["description"],
                    "input_schema": CSV_TOOL_SCHEMA["input_schema"],
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

    duration = round(time.perf_counter() - start, 2)
    analysis_data = _extract_tool_result(response, "record_analysis")

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    estimated_cost = _compute_cost(input_tokens, output_tokens)

    _log.info(
        "ai_analysis_complete",
        filename=filename,
        model=_MODEL,
        prompt_version=CSV_PROMPT_VERSION,
        analysis_type="csv",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_seconds=duration,
        estimated_cost_usd=estimated_cost,
        findings_count=len(analysis_data.get("findings", [])),
        recommendations_count=len(analysis_data.get("recommendations", [])),
    )

    return AnalysisResult(
        analysis=analysis_data,
        prompt_version=CSV_PROMPT_VERSION,
        model=_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_seconds=duration,
        estimated_cost_usd=estimated_cost,
    )


async def analyze_image(
    image_bytes: bytes,
    content_type: str,
    filename: str = "unknown.jpg",
) -> AnalysisResult:
    """Send an image to Claude Vision and get structured urban analysis back.

    Args:
        image_bytes: Raw bytes of the image file (JPEG, PNG, or WebP).
        content_type: MIME type of the image.
        filename: Original filename, used only for logging.

    Returns:
        AnalysisResult with the structured analysis and usage metadata.

    Raises:
        AnalysisError on any failure.
    """
    client = _get_client()

    # Encode image as base64 for the Vision API.
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Map common MIME types to what Claude expects.
    media_type_map: dict[str, str] = {
        "image/jpeg": "image/jpeg",
        "image/png": "image/png",
        "image/webp": "image/webp",
    }
    media_type = media_type_map.get(content_type)
    if not media_type:
        raise AnalysisError(
            "unsupported_image_type",
            f"Image type '{content_type}' is not supported for vision analysis.",
        )

    _log.info(
        "ai_analysis_starting",
        filename=filename,
        model=_MODEL,
        prompt_version=IMAGE_PROMPT_VERSION,
        analysis_type="image",
        image_size_bytes=len(image_bytes),
    )

    start = time.perf_counter()

    try:
        response = client.messages.create(  # type: ignore[call-overload]
            model=_MODEL,
            max_tokens=4096,
            system=IMAGE_SYSTEM_PROMPT,
            tools=[
                {
                    "type": "custom",
                    "name": IMAGE_TOOL_SCHEMA["name"],
                    "description": IMAGE_TOOL_SCHEMA["description"],
                    "input_schema": IMAGE_TOOL_SCHEMA["input_schema"],
                },
            ],
            tool_choice={"type": "tool", "name": "record_image_analysis"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": IMAGE_USER_PROMPT,
                        },
                    ],
                }
            ],
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

    duration = round(time.perf_counter() - start, 2)
    analysis_data = _extract_tool_result(response, "record_image_analysis")

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    estimated_cost = _compute_cost(input_tokens, output_tokens)

    _log.info(
        "ai_analysis_complete",
        filename=filename,
        model=_MODEL,
        prompt_version=IMAGE_PROMPT_VERSION,
        analysis_type="image",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_seconds=duration,
        estimated_cost_usd=estimated_cost,
        observations_count=len(analysis_data.get("observations", [])),
        opportunities_count=len(analysis_data.get("sustainability_opportunities", [])),
    )

    return AnalysisResult(
        analysis=analysis_data,
        prompt_version=IMAGE_PROMPT_VERSION,
        model=_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_seconds=duration,
        estimated_cost_usd=estimated_cost,
    )
