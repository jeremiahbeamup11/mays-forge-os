"""PDF report generator for Mays Forge OS analysis results.

Produces professional, branded PDF reports from structured AI analysis
data. These reports are designed to be shared with city officials,
brought to council meetings, and used as justification for infrastructure
investment decisions.

Design principles:
1. Reports are self-contained — all context needed to understand the
   analysis is in the PDF, no web login required.
2. Professional formatting — clean layout, color-coded priorities,
   structured sections. Should look like something from a consulting firm.
3. Metadata transparency — every report shows which AI model produced it,
   what prompt version was used, and when it was generated. No black boxes.
"""

import io
from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF

from app.core.logging import get_logger

_log = get_logger(__name__)

# Brand colors
_NAVY = (15, 23, 42)
_SLATE_700 = (51, 65, 85)
_SLATE_400 = (148, 163, 184)
_WHITE = (255, 255, 255)
_RED = (220, 38, 38)
_ORANGE = (249, 115, 22)
_YELLOW = (202, 138, 4)
_GREEN = (22, 163, 74)
_BLUE = (59, 130, 246)
_LIGHT_BG = (248, 250, 252)


def _sanitize_text(text: str) -> str:
    """Replace Unicode characters that fpdf2's built-in fonts can't render."""
    replacements = {
        "\u2014": "--",  # em dash
        "\u2013": "-",  # en dash
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u2026": "...",  # ellipsis
        "\u2022": "-",  # bullet
        "\u00b7": "-",  # middle dot
        "\u2212": "-",  # minus sign
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


class ForgeReport(FPDF):
    """Custom PDF class with Mays Forge OS branding."""

    def __init__(self, org_name: str, filename: str) -> None:
        super().__init__()
        self.org_name = org_name
        self.source_filename = filename
        self.set_auto_page_break(auto=True, margin=25)

    def header(self) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_SLATE_400)
        self.cell(0, 6, "MAYS FORGE OS", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_SLATE_400)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-20)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_SLATE_400)
        self.cell(
            0,
            5,
            f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Mays Forge OS v0.1.0 | Page {self.page_no()}/{{nb}}",
            align="C",
        )

    def section_title(self, title: str) -> None:
        self.ln(6)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*_NAVY)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_BLUE)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 80, self.get_y())
        self.set_line_width(0.2)
        self.ln(4)

    def subsection_title(self, title: str) -> None:
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*_SLATE_700)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*_SLATE_700)
        self.multi_cell(0, 5.5, _sanitize_text(text))
        self.ln(2)

    def badge(self, label: str, color: tuple[int, int, int]) -> None:
        self.set_fill_color(*color)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 8)
        w = self.get_string_width(label.upper()) + 6
        self.cell(w, 5.5, label.upper(), fill=True, new_x="END")
        self.set_text_color(*_SLATE_700)
        self.cell(3, 5.5, "")  # spacer


def _priority_color(priority: str) -> tuple[int, int, int]:
    return {
        "critical": _RED,
        "high": _ORANGE,
        "medium": _YELLOW,
        "low": _SLATE_400,
    }.get(priority, _SLATE_400)


def _confidence_color(confidence: str) -> tuple[int, int, int]:
    return {
        "confirmed": _GREEN,
        "inferred": _BLUE,
    }.get(confidence, _SLATE_400)


def _condition_color(condition: str) -> tuple[int, int, int]:
    return {
        "excellent": _GREEN,
        "good": _GREEN,
        "fair": _YELLOW,
        "poor": _ORANGE,
        "critical": _RED,
    }.get(condition, _SLATE_400)


def _feasibility_color(feasibility: str) -> tuple[int, int, int]:
    return {
        "high": _GREEN,
        "medium": _BLUE,
        "low": _SLATE_400,
        "needs_investigation": _ORANGE,
    }.get(feasibility, _SLATE_400)


def generate_csv_report(
    *,
    org_name: str,
    filename: str,
    analysis: dict[str, Any],
    metadata: dict[str, Any],
) -> bytes:
    """Generate a PDF report for a CSV analysis."""
    pdf = ForgeReport(org_name, filename)
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- Title ---
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*_NAVY)
    pdf.ln(15)
    pdf.cell(0, 12, "Infrastructure Analysis Report", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(*_SLATE_700)
    pdf.ln(4)
    pdf.cell(0, 8, _sanitize_text(org_name), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_SLATE_400)
    pdf.cell(0, 6, _sanitize_text(f"Source: {filename}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        6,
        f"Model: {metadata.get('model', 'unknown')} | "
        f"Prompt: {metadata.get('prompt_version', 'unknown')} | "
        f"Generated: {datetime.now(UTC).strftime('%B %d, %Y')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(8)

    # --- Summary ---
    pdf.section_title("Summary")
    summary = analysis.get("summary", "No summary available.")
    pdf.body_text(summary)

    # --- Findings ---
    findings = analysis.get("findings", [])
    if findings:
        pdf.section_title(f"Findings ({len(findings)})")
        for i, finding in enumerate(findings, 1):
            if pdf.get_y() > 250:
                pdf.add_page()

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_NAVY)
            pdf.cell(8, 6, f"{i}.", new_x="END")

            pdf.badge(
                finding.get("confidence", "unknown"),
                _confidence_color(finding.get("confidence", "")),
            )
            pdf.badge(
                finding.get("category", "general"),
                _SLATE_400,
            )
            pdf.ln()

            pdf.set_x(18)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_NAVY)
            pdf.multi_cell(0, 5.5, _sanitize_text(finding.get("title", "")), new_x="LMARGIN")

            pdf.set_x(18)
            pdf.body_text(finding.get("detail", ""))
            pdf.ln(1)

    # --- Recommendations ---
    recommendations = analysis.get("recommendations", [])
    if recommendations:
        pdf.section_title(f"Recommendations ({len(recommendations)})")
        for i, rec in enumerate(recommendations, 1):
            if pdf.get_y() > 240:
                pdf.add_page()

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_NAVY)
            pdf.cell(8, 6, f"{i}.", new_x="END")

            pdf.badge(
                rec.get("priority", "medium"),
                _priority_color(rec.get("priority", "")),
            )
            pdf.ln()

            pdf.set_x(18)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_NAVY)
            pdf.multi_cell(0, 5.5, _sanitize_text(rec.get("action", "")), new_x="LMARGIN")

            pdf.set_x(18)
            pdf.body_text(rec.get("rationale", ""))

            impact = rec.get("estimated_impact", "")
            if impact:
                pdf.set_x(18)
                pdf.set_font("Helvetica", "BI", 9)
                pdf.set_text_color(*_SLATE_400)
                pdf.multi_cell(0, 5, _sanitize_text(f"Estimated impact: {impact}"), new_x="LMARGIN")
            pdf.ln(2)

    # --- Data Quality ---
    dq = analysis.get("data_quality", {})
    if dq:
        pdf.section_title("Data Quality Assessment")

        quality = dq.get("overall_quality", "unknown")
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_NAVY)
        pdf.cell(30, 6, "Overall: ", new_x="END")
        pdf.badge(quality, _condition_color(quality))
        pdf.ln(8)

        issues = dq.get("issues", [])
        if issues:
            for issue in issues:
                if pdf.get_y() > 260:
                    pdf.add_page()
                pdf.set_x(15)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*_SLATE_700)
                pdf.cell(5, 5, "-", new_x="END")
                pdf.multi_cell(0, 5, _sanitize_text(issue), new_x="LMARGIN")
                pdf.ln(1)

    # Generate bytes
    buf = io.BytesIO()
    pdf.output(buf)
    pdf_bytes = buf.getvalue()

    _log.info(
        "report_generated",
        org_name=org_name,
        filename=filename,
        pdf_size_bytes=len(pdf_bytes),
    )

    return pdf_bytes


def generate_image_report(
    *,
    org_name: str,
    filename: str,
    analysis: dict[str, Any],
    metadata: dict[str, Any],
) -> bytes:
    """Generate a PDF report for an image analysis."""
    pdf = ForgeReport(org_name, filename)
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- Title ---
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*_NAVY)
    pdf.ln(15)
    pdf.cell(0, 12, "Site Assessment Report", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(*_SLATE_700)
    pdf.ln(4)
    pdf.cell(0, 8, _sanitize_text(org_name), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_SLATE_400)
    pdf.cell(0, 6, _sanitize_text(f"Source: {filename}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        6,
        f"Model: {metadata.get('model', 'unknown')} | "
        f"Generated: {datetime.now(UTC).strftime('%B %d, %Y')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(8)

    # --- Scene Description ---
    pdf.section_title("Site Overview")

    site_type = analysis.get("site_type", "unknown").replace("_", " ").title()
    condition = analysis.get("condition_assessment", {})
    overall = condition.get("overall_condition", "unknown")

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_NAVY)
    pdf.cell(20, 6, "Type: ", new_x="END")
    pdf.badge(site_type, _SLATE_400)
    pdf.cell(5, 6, "", new_x="END")
    pdf.cell(25, 6, "Condition: ", new_x="END")
    pdf.badge(overall, _condition_color(overall))
    pdf.ln(8)

    pdf.body_text(analysis.get("scene_description", ""))

    if condition.get("details"):
        pdf.subsection_title("Condition Details")
        pdf.body_text(condition["details"])

    # --- Estimated Characteristics ---
    chars = analysis.get("estimated_characteristics", {})
    if chars:
        pdf.subsection_title("Estimated Characteristics")
        if chars.get("estimated_lot_size"):
            pdf.body_text(f"Lot Size: {chars['estimated_lot_size']}")
        if chars.get("vegetation_coverage_pct") is not None:
            pdf.body_text(f"Vegetation Coverage: {chars['vegetation_coverage_pct']}%")
        if chars.get("impervious_surface_pct") is not None:
            pdf.body_text(f"Impervious Surface: {chars['impervious_surface_pct']}%")

    # --- Observations ---
    observations = analysis.get("observations", [])
    if observations:
        pdf.section_title(f"Observations ({len(observations)})")
        for i, obs in enumerate(observations, 1):
            if pdf.get_y() > 240:
                pdf.add_page()

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_NAVY)
            pdf.cell(8, 6, f"{i}.", new_x="END")

            category = obs.get("category", "general").replace("_", " ")
            pdf.badge(category, _SLATE_400)
            pdf.ln()

            pdf.set_x(18)
            pdf.body_text(obs.get("detail", ""))

            if obs.get("planning_relevance"):
                pdf.set_x(18)
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(*_SLATE_400)
                pdf.multi_cell(
                    0,
                    5,
                    _sanitize_text(f"Planning relevance: {obs['planning_relevance']}"),
                    new_x="LMARGIN",
                )
            pdf.ln(2)

    # --- Sustainability Opportunities ---
    opportunities = analysis.get("sustainability_opportunities", [])
    if opportunities:
        pdf.section_title(f"Sustainability Opportunities ({len(opportunities)})")
        for i, opp in enumerate(opportunities, 1):
            if pdf.get_y() > 240:
                pdf.add_page()

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_NAVY)
            pdf.cell(8, 6, f"{i}.", new_x="END")

            feasibility = opp.get("feasibility", "unknown").replace("_", " ")
            pdf.badge(feasibility, _feasibility_color(opp.get("feasibility", "")))
            pdf.ln()

            pdf.set_x(18)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_NAVY)
            pdf.multi_cell(0, 5.5, _sanitize_text(opp.get("opportunity", "")), new_x="LMARGIN")

            pdf.set_x(18)
            pdf.body_text(opp.get("rationale", ""))
            pdf.ln(1)

    buf = io.BytesIO()
    pdf.output(buf)
    pdf_bytes = buf.getvalue()

    _log.info(
        "report_generated",
        org_name=org_name,
        filename=filename,
        report_type="image",
        pdf_size_bytes=len(pdf_bytes),
    )

    return pdf_bytes
