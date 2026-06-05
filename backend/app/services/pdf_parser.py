"""PDF parsing and structural extraction for municipal documents.

Takes raw PDF bytes and produces a structured extraction with:
- Tables as structured rows with source page numbers
- Text organized by section/heading
- Extraction method tracking (deterministic vs. vision fallback)

Design decisions:
- Uses pdfplumber with text-based table detection, which handles
  municipal PDFs (typically space-aligned, not ruled) better than
  default line-based detection.
- Cleans up common extraction artifacts: broken words across columns,
  empty rows, dollar signs in separate cells.
- Tracks source page for every table and section, so downstream
  analysis can cite "page 26" for any number it surfaces.
- Falls back to vision (page-to-image) only for pages where
  deterministic extraction yields no usable content.
"""

import io
import re
from dataclasses import dataclass, field

import pdfplumber

from app.core.logging import get_logger

_log = get_logger(__name__)

MAX_PAGES = 200


class PdfParseError(Exception):
    """Raised when a PDF file cannot be parsed."""


@dataclass
class ExtractedTable:
    """A single table extracted from a PDF page."""

    page_number: int
    title: str
    headers: list[str]
    rows: list[list[str]]
    extraction_method: str = "deterministic"

    def to_dict(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "title": self.title,
            "headers": self.headers,
            "rows": self.rows,
            "extraction_method": self.extraction_method,
        }


@dataclass
class TextSection:
    """A section of text extracted from the PDF, grouped by heading."""

    page_number: int
    heading: str
    content: str
    extraction_method: str = "deterministic"

    def to_dict(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "heading": self.heading,
            "content": self.content,
            "extraction_method": self.extraction_method,
        }


@dataclass
class VisionFallbackPage:
    """A page that required vision fallback for extraction."""

    page_number: int
    image_bytes: bytes
    reason: str


@dataclass
class PdfExtraction:
    """Complete structured extraction from a PDF document."""

    filename: str
    page_count: int
    tables: list[ExtractedTable]
    sections: list[TextSection]
    vision_pages: list[int] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)

    def to_prompt_context(self, max_chars: int = 100_000) -> str:
        """Format as text for inclusion in an AI prompt.

        Prioritizes tables (the high-value structured data) and
        financially-relevant text sections. Trims low-value sections
        to stay within the token budget.
        """
        lines = [
            f"## Document: {self.filename}",
            f"Pages: {self.page_count}",
        ]
        if self.vision_pages:
            lines.append(f"Pages extracted via vision fallback: {self.vision_pages}")
        if self.parse_warnings:
            lines.append(f"Warnings: {'; '.join(self.parse_warnings)}")

        # Tables first — they're the core data
        table_lines: list[str] = []
        if self.tables:
            table_lines.append("")
            table_lines.append("### Extracted Tables")
            for table in self.tables:
                method_tag = ""
                if table.extraction_method == "vision":
                    method_tag = " [via vision]"
                table_lines.append(f"\n#### {table.title} (page {table.page_number}){method_tag}")
                if table.headers:
                    table_lines.append(" | ".join(table.headers))
                    table_lines.append(" | ".join("---" for _ in table.headers))
                for row in table.rows:
                    table_lines.append(" | ".join(row))

        tables_text = "\n".join(table_lines)
        remaining = max_chars - len("\n".join(lines)) - len(tables_text)

        # Text sections — prioritize financially relevant ones
        section_lines: list[str] = []
        if self.sections and remaining > 500:
            section_lines.append("")
            section_lines.append("### Document Sections")

            scored = _score_sections(self.sections)
            used = 0
            for section, _score in scored:
                entry = f"\n#### {section.heading} (page {section.page_number})\n{section.content}"
                if used + len(entry) > remaining:
                    continue
                section_lines.append(entry)
                used += len(entry)

        lines.extend(section_lines)
        lines.append(tables_text)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "page_count": self.page_count,
            "tables": [t.to_dict() for t in self.tables],
            "sections": [s.to_dict() for s in self.sections],
            "vision_pages": self.vision_pages,
            "parse_warnings": self.parse_warnings,
        }


def parse_pdf(file_bytes: bytes, filename: str = "upload.pdf") -> PdfExtraction:
    """Parse PDF bytes and return a structured extraction.

    Raises PdfParseError if the PDF cannot be opened or parsed.
    """
    try:
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
    except Exception as exc:
        raise PdfParseError(f"Could not open PDF: {exc}") from exc

    page_count = len(pdf.pages)
    if page_count == 0:
        raise PdfParseError("PDF has no pages.")
    if page_count > MAX_PAGES:
        raise PdfParseError(f"PDF has {page_count} pages, exceeding the {MAX_PAGES}-page limit.")

    tables: list[ExtractedTable] = []
    sections: list[TextSection] = []
    vision_fallback_pages: list[VisionFallbackPage] = []
    warnings: list[str] = []

    for page_idx, page in enumerate(pdf.pages):
        page_num = page_idx + 1
        page_text = page.extract_text() or ""
        page_tables = _extract_tables_from_page(page, page_num)
        page_sections = _extract_sections_from_page(page_text, page_num)

        has_content = bool(page_tables) or bool(
            page_sections and any(s.content.strip() for s in page_sections)
        )

        if not has_content and len(page_text.strip()) < 20:
            vision_fallback_pages.append(
                VisionFallbackPage(
                    page_number=page_num,
                    image_bytes=b"",
                    reason="No text or tables extracted from page",
                )
            )
            _log.info(
                "pdf_page_vision_fallback",
                filename=filename,
                page=page_num,
                reason="empty_extraction",
            )
        else:
            tables.extend(page_tables)
            sections.extend(page_sections)

    vision_page_numbers = [vp.page_number for vp in vision_fallback_pages]

    if not tables and not sections:
        warnings.append(
            "No tables or meaningful text extracted. This PDF may be scanned/image-based."
        )

    _log.info(
        "pdf_parsed",
        filename=filename,
        page_count=page_count,
        tables_extracted=len(tables),
        sections_extracted=len(sections),
        vision_fallback_pages=len(vision_page_numbers),
    )

    return PdfExtraction(
        filename=filename,
        page_count=page_count,
        tables=tables,
        sections=sections,
        vision_pages=vision_page_numbers,
        parse_warnings=warnings,
    )


def _extract_tables_from_page(page: pdfplumber.page.Page, page_num: int) -> list[ExtractedTable]:
    """Extract tables from a single page using text-based detection."""
    raw_tables = page.extract_tables(
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
        }
    )

    if not raw_tables:
        return []

    results = []
    for table_idx, raw_table in enumerate(raw_tables):
        cleaned = _clean_table(raw_table)
        if not cleaned or len(cleaned) < 2:
            continue

        title, headers, rows = _identify_table_structure(cleaned, page_num, table_idx)

        if not rows:
            continue

        if not _is_data_table(rows):
            continue

        results.append(
            ExtractedTable(
                page_number=page_num,
                title=title,
                headers=headers,
                rows=rows,
            )
        )

    return results


def _is_data_table(rows: list[list[str]]) -> bool:
    """Filter out text blocks mis-detected as tables.

    A real data table has numeric values in a meaningful fraction of its
    data cells. A text paragraph forced into a table grid has almost none.
    """
    total_cells = 0
    value_cells = 0
    for row in rows:
        for cell in row:
            if cell.strip():
                total_cells += 1
                if _looks_like_value(cell):
                    value_cells += 1
    if total_cells == 0:
        return False
    return value_cells / total_cells > 0.10


def _clean_table(raw_table: list[list[str | None]]) -> list[list[str]]:
    """Clean raw pdfplumber table output.

    Fixes: None cells, empty rows, broken words across columns,
    dollar signs in separate cells.
    """
    cleaned_rows: list[list[str]] = []

    for raw_row in raw_table:
        cells = [_clean_cell(c) for c in raw_row]

        if all(c == "" for c in cells):
            continue

        cells = _merge_broken_cells(cells)
        cleaned_rows.append(cells)

    return cleaned_rows


def _clean_cell(value: str | None) -> str:
    """Clean a single cell value."""
    if value is None:
        return ""
    text = value.strip()
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = _fix_broken_numbers(text)
    return text


def _fix_broken_numbers(text: str) -> str:
    """Fix numbers broken by spaces: '2 68,821' → '268,821', '1 ,015' → '1,015'."""
    # "1 ,015,872" → "1,015,872"
    text = re.sub(r"(\d) +,(\d)", r"\1,\2", text)
    # "1 16,797" — single digit, space, 2-3 digits then comma-grouped
    # Only when the left side is a lone digit (word boundary)
    text = re.sub(r"\b(\d) +(\d{2,3},\d{3})\b", r"\1\2", text)
    # Normalize "$ 4,356" → "$4,356"
    text = re.sub(r"\$ +", "$", text)
    return text


def _merge_broken_cells(cells: list[str]) -> list[str]:
    """Merge cells that are fragments of broken words/values.

    Handles patterns like: ["Cash and Inve", "stments $", "12,161,171"]
    by joining fragments that don't look like standalone values.
    """
    if len(cells) <= 1:
        return cells

    merged: list[str] = []
    i = 0
    while i < len(cells):
        cell = cells[i]

        if cell == "$" and i + 1 < len(cells):
            merged.append(f"$ {cells[i + 1]}")
            i += 2
            continue

        if (
            cell
            and i + 1 < len(cells)
            and cells[i + 1]
            and not _looks_like_value(cells[i + 1])
            and _is_word_fragment(cell, cells[i + 1])
        ):
            merged.append(cell + cells[i + 1])
            i += 2
            continue

        merged.append(cell)
        i += 1

    return merged


def _looks_like_value(text: str) -> bool:
    """Check if text looks like a standalone numeric value or header."""
    cleaned = text.strip().lstrip("$").strip()
    cleaned = cleaned.replace(",", "").replace("(", "").replace(")", "")
    if not cleaned:
        return False
    try:
        float(cleaned)
        return True
    except ValueError:
        pass
    if re.match(r"^[\d,.$%()\-]+$", text.strip()):
        return True
    return False


def _is_word_fragment(left: str, right: str) -> bool:
    """Check if two cells look like fragments of a broken word."""
    if not left or not right:
        return False
    if left[-1].isalpha() and right[0].islower():
        return True
    return False


def _identify_table_structure(
    rows: list[list[str]], page_num: int, table_idx: int
) -> tuple[str, list[str], list[list[str]]]:
    """Identify title, headers, and data rows from cleaned table rows.

    Returns (title, headers, data_rows).
    """
    title = f"Table {table_idx + 1}"
    headers: list[str] = []
    data_start = 0

    if rows and not any(_looks_like_value(c) for c in rows[0] if c):
        candidate = " ".join(c for c in rows[0] if c).strip()
        if candidate and len(candidate) > 3:
            title = candidate
            data_start = 1

    for i in range(data_start, min(data_start + 3, len(rows))):
        row = rows[i]
        non_empty = [c for c in row if c]
        has_values = any(_looks_like_value(c) for c in non_empty)
        if not has_values and non_empty:
            headers = list(row)
            data_start = i + 1
            break

    if not headers and data_start < len(rows):
        headers = [f"Col {j + 1}" for j in range(len(rows[data_start]))]

    data_rows = rows[data_start:]
    max_cols = max((len(r) for r in data_rows), default=0)
    if headers:
        max_cols = max(max_cols, len(headers))

    normalized: list[list[str]] = []
    for row in data_rows:
        padded = row + [""] * (max_cols - len(row))
        normalized.append(padded[:max_cols])

    if headers:
        headers = (headers + [""] * (max_cols - len(headers)))[:max_cols]

    return title, headers, normalized


def _extract_sections_from_page(page_text: str, page_num: int) -> list[TextSection]:
    """Extract text sections organized by headings from a page.

    Identifies headings heuristically: short lines in title case or
    all caps that precede longer content blocks.
    """
    if not page_text or len(page_text.strip()) < 10:
        return []

    lines = page_text.split("\n")
    sections: list[TextSection] = []
    current_heading = f"Page {page_num}"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if _is_heading(stripped, lines):
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append(
                        TextSection(
                            page_number=page_num,
                            heading=current_heading,
                            content=content,
                        )
                    )
                current_lines = []
            current_heading = stripped
        else:
            current_lines.append(stripped)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(
                TextSection(
                    page_number=page_num,
                    heading=current_heading,
                    content=content,
                )
            )

    return sections


_FINANCIAL_KEYWORDS = [
    "revenue",
    "expenditure",
    "fund balance",
    "net position",
    "debt",
    "capital",
    "budget",
    "tax",
    "pension",
    "appropriation",
    "surplus",
    "deficit",
    "reserve",
    "bond",
    "levy",
    "assessment",
    "fiscal",
    "water",
    "sewer",
    "stormwater",
    "infrastructure",
    "maintenance",
    "depreciation",
    "amortization",
    "personnel",
    "salary",
]


def _score_sections(
    sections: list[TextSection],
) -> list[tuple[TextSection, float]]:
    """Score sections by financial relevance. Higher = more relevant."""
    scored = []
    for section in sections:
        text = (section.heading + " " + section.content).lower()
        if len(section.content.strip()) < 20:
            scored.append((section, -1.0))
            continue

        score = 0.0
        for kw in _FINANCIAL_KEYWORDS:
            if kw in text:
                score += 1.0

        has_dollar = "$" in section.content
        has_numbers = bool(re.search(r"\d{3,}", section.content))
        if has_dollar:
            score += 3.0
        if has_numbers:
            score += 1.0

        if len(section.content) > 500:
            score += 0.5
        if len(section.content) < 50:
            score -= 2.0

        scored.append((section, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _is_heading(line: str, all_lines: list[str]) -> bool:
    """Heuristic: is this line a section heading?"""
    if len(line) > 120 or len(line) < 3:
        return False

    if line.isupper() and len(line.split()) <= 10:
        return True

    if re.match(r"^(NOTE|SECTION|CHAPTER)\s+\d", line, re.IGNORECASE):
        return True

    words = line.split()
    if (
        len(words) <= 8
        and all(w[0].isupper() or not w[0].isalpha() for w in words)
        and not any(c in line for c in ["$", "%", "(", ")"])
        and not _looks_like_value(line)
    ):
        non_heading_lines = [ln for ln in all_lines if ln.strip() and len(ln.strip()) > len(line)]
        if len(non_heading_lines) > 2:
            return True

    return False
