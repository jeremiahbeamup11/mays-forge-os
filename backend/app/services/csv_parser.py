"""CSV parsing and structural analysis.

Takes raw CSV bytes and produces a structured summary suitable for
AI analysis. This module does NOT interpret the data — it describes
what's in the file so Claude can interpret it.

Design decisions:
- We cap the number of rows we examine for stats at 10,000. Municipal
  CSVs are rarely larger, and if they are, a sample is sufficient for
  AI analysis. We note when data is sampled vs. exhaustive.
- We detect column types heuristically (numeric, date-like, text) rather
  than trusting headers, because municipal data is messy.
- We include sample rows so Claude can see concrete values, not just
  abstract statistics.
"""

import csv
import io
import math
from dataclasses import dataclass, field

from app.core.logging import get_logger

_log = get_logger(__name__)

# Maximum rows to examine for statistics. Beyond this we sample.
MAX_ROWS_FOR_STATS = 10_000

# Maximum sample rows to include in the AI prompt.
MAX_SAMPLE_ROWS = 5


class CsvParseError(Exception):
    """Raised when a CSV file cannot be parsed."""


@dataclass
class ColumnProfile:
    """Statistical profile of a single CSV column."""

    name: str
    non_null_count: int = 0
    null_count: int = 0
    inferred_type: str = "text"  # "numeric", "date", "text"

    # Numeric stats (populated only if inferred_type == "numeric")
    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None

    # Text stats
    unique_count: int = 0
    sample_values: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "name": self.name,
            "inferred_type": self.inferred_type,
            "non_null_count": self.non_null_count,
            "null_count": self.null_count,
        }
        if self.inferred_type == "numeric":
            result["min"] = self.min_value
            result["max"] = self.max_value
            result["mean"] = round(self.mean_value, 2) if self.mean_value else None
        result["unique_count"] = self.unique_count
        if self.sample_values:
            result["sample_values"] = self.sample_values[:5]
        return result


@dataclass
class CsvSummary:
    """Structured summary of a parsed CSV file."""

    filename: str
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    sample_rows: list[dict[str, str]]
    was_sampled: bool  # True if we only examined a subset of rows
    parse_warnings: list[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Format this summary as a text block for inclusion in an AI prompt.

        This is the bridge between the parser and the prompt template.
        Claude reads this text to understand what's in the file.
        """
        lines = [
            f"## File: {self.filename}",
            f"Rows: {self.row_count:,} | Columns: {self.column_count}",
        ]
        if self.was_sampled:
            lines.append(f"(Statistics computed from first {MAX_ROWS_FOR_STATS:,} rows)")
        if self.parse_warnings:
            lines.append(f"Warnings: {'; '.join(self.parse_warnings)}")

        lines.append("")
        lines.append("### Column Profiles")
        for col in self.columns:
            type_label = col.inferred_type.upper()
            line = f"- **{col.name}** [{type_label}]"
            line += f" — {col.non_null_count} values, {col.null_count} nulls"
            if col.inferred_type == "numeric" and col.min_value is not None:
                line += (
                    f", range [{col.min_value:,.2f} - {col.max_value:,.2f}]"
                    f", mean {col.mean_value:,.2f}"
                )
            if col.unique_count > 0:
                line += f", {col.unique_count} unique"
            if col.sample_values:
                samples = ", ".join(f'"{v}"' for v in col.sample_values[:3])
                line += f" (e.g. {samples})"
            lines.append(line)

        if self.sample_rows:
            lines.append("")
            lines.append("### Sample Rows (first 5)")
            for i, row in enumerate(self.sample_rows, 1):
                formatted = " | ".join(f"{k}: {v}" for k, v in row.items())
                lines.append(f"  {i}. {formatted}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": [c.to_dict() for c in self.columns],
            "sample_rows": self.sample_rows,
            "was_sampled": self.was_sampled,
            "parse_warnings": self.parse_warnings,
        }


def parse_csv(file_bytes: bytes, filename: str = "upload.csv") -> CsvSummary:
    """Parse CSV bytes and return a structured summary.

    Raises CsvParseError if the bytes cannot be decoded or parsed as CSV.
    """
    try:
        text = file_bytes.decode("utf-8-sig")  # utf-8-sig strips BOM if present
    except UnicodeDecodeError:
        try:
            text = file_bytes.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise CsvParseError("File encoding is not recognized as UTF-8 or Latin-1.") from exc

    try:
        dialect = csv.Sniffer().sniff(text[:8192])
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise CsvParseError("CSV has no header row or is empty.")

    columns = [ColumnProfile(name=name.strip()) for name in reader.fieldnames if name]

    sample_rows: list[dict[str, str]] = []
    numeric_values: dict[str, list[float]] = {col.name: [] for col in columns}
    unique_tracker: dict[str, set[str]] = {col.name: set() for col in columns}
    warnings: list[str] = []

    row_count = 0
    was_sampled = False

    for row in reader:
        row_count += 1
        if row_count > MAX_ROWS_FOR_STATS:
            was_sampled = True
            # Keep counting rows but stop collecting stats.
            continue

        if len(sample_rows) < MAX_SAMPLE_ROWS:
            clean_row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            sample_rows.append(clean_row)

        for col in columns:
            value = (row.get(col.name) or "").strip()
            if not value:
                col.null_count += 1
                continue
            col.non_null_count += 1
            unique_tracker[col.name].add(value)
            parsed_num = _try_parse_number(value)
            if parsed_num is not None:
                numeric_values[col.name].append(parsed_num)

    # Count remaining rows if we were sampled.
    if was_sampled:
        for _ in reader:
            row_count += 1

    # Finalize column profiles.
    for col in columns:
        col.unique_count = len(unique_tracker[col.name])
        nums = numeric_values[col.name]

        # Heuristic: if >70% of non-null values parsed as numbers, call it numeric.
        if col.non_null_count > 0 and len(nums) / col.non_null_count > 0.7:
            col.inferred_type = "numeric"
            col.min_value = min(nums)
            col.max_value = max(nums)
            col.mean_value = sum(nums) / len(nums)
        else:
            col.inferred_type = "text"

        col.sample_values = list(unique_tracker[col.name])[:5]

    if row_count == 0:
        warnings.append("CSV has headers but zero data rows.")

    empty_cols = [c.name for c in columns if c.non_null_count == 0]
    if empty_cols:
        warnings.append(f"Empty columns (all null): {', '.join(empty_cols)}")

    _log.info(
        "csv_parsed",
        filename=filename,
        row_count=row_count,
        column_count=len(columns),
        was_sampled=was_sampled,
    )

    return CsvSummary(
        filename=filename,
        row_count=row_count,
        column_count=len(columns),
        columns=columns,
        sample_rows=sample_rows,
        was_sampled=was_sampled,
        parse_warnings=warnings,
    )


def _try_parse_number(value: str) -> float | None:
    """Attempt to parse a string as a number, handling common formats."""
    cleaned = value.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        result = float(cleaned)
        if math.isfinite(result):
            return result
    except (ValueError, OverflowError):
        pass
    return None
