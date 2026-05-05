"""Tests for the CSV parsing and AI analysis pipeline.

Two layers tested separately:
1. CSV parser (deterministic, no mocking needed)
2. AI analyzer (Anthropic API mocked — we don't call Claude in unit tests)

Integration with the upload endpoint is already covered in test_files.py.
These tests focus on the services themselves.
"""

from unittest.mock import MagicMock

import pytest

from app.services.csv_parser import CsvParseError, parse_csv

# ============================================================================
# CSV Parser — deterministic tests
# ============================================================================


class TestCsvParserBasic:
    """Core parsing functionality."""

    def test_simple_csv(self) -> None:
        csv_bytes = b"name,age,city\nAlice,30,Peotone\nBob,45,Monee\n"
        result = parse_csv(csv_bytes, "test.csv")
        assert result.row_count == 2
        assert result.column_count == 3
        assert result.filename == "test.csv"
        assert not result.was_sampled

    def test_column_names_extracted(self) -> None:
        csv_bytes = b"water_usage,zone,month\n100,A,Jan\n"
        result = parse_csv(csv_bytes, "water.csv")
        col_names = [c.name for c in result.columns]
        assert "water_usage" in col_names
        assert "zone" in col_names
        assert "month" in col_names

    def test_numeric_type_inference(self) -> None:
        csv_bytes = b"amount,label\n100,foo\n200,bar\n300,baz\n"
        result = parse_csv(csv_bytes, "nums.csv")
        amount_col = next(c for c in result.columns if c.name == "amount")
        assert amount_col.inferred_type == "numeric"
        assert amount_col.min_value == 100.0
        assert amount_col.max_value == 300.0

    def test_text_type_inference(self) -> None:
        csv_bytes = b"city,state\nPeotone,IL\nMonee,IL\n"
        result = parse_csv(csv_bytes, "cities.csv")
        city_col = next(c for c in result.columns if c.name == "city")
        assert city_col.inferred_type == "text"

    def test_sample_rows_included(self) -> None:
        rows = "id,val\n" + "\n".join(f"{i},{i * 10}" for i in range(20))
        result = parse_csv(rows.encode(), "big.csv")
        assert len(result.sample_rows) == 5  # capped at MAX_SAMPLE_ROWS
        assert result.row_count == 20

    def test_null_counting(self) -> None:
        csv_bytes = b"a,b\n1,\n2,x\n3,\n"
        result = parse_csv(csv_bytes, "nulls.csv")
        b_col = next(c for c in result.columns if c.name == "b")
        assert b_col.null_count == 2
        assert b_col.non_null_count == 1


class TestCsvParserEdgeCases:
    """Edge cases and error handling."""

    def test_empty_file_raises(self) -> None:
        with pytest.raises(CsvParseError):
            parse_csv(b"", "empty.csv")

    def test_headers_only_warns(self) -> None:
        csv_bytes = b"col1,col2,col3\n"
        result = parse_csv(csv_bytes, "headers_only.csv")
        assert result.row_count == 0
        assert any("zero data rows" in w for w in result.parse_warnings)

    def test_bom_handling(self) -> None:
        """UTF-8 BOM should be stripped transparently."""
        csv_bytes = b"\xef\xbb\xbfname,value\ntest,42\n"
        result = parse_csv(csv_bytes, "bom.csv")
        assert result.columns[0].name == "name"  # not '\ufeffname'

    def test_dollar_values_parsed_as_numeric(self) -> None:
        csv_bytes = b"item,cost\nPipe repair,$47000\nValve,$1200\n"
        result = parse_csv(csv_bytes, "costs.csv")
        cost_col = next(c for c in result.columns if c.name == "cost")
        assert cost_col.inferred_type == "numeric"
        assert cost_col.min_value == 1200.0
        assert cost_col.max_value == 47000.0

    def test_comma_numbers_parsed(self) -> None:
        csv_bytes = b'population\n"4,200"\n"12,500"\n'
        result = parse_csv(csv_bytes, "pop.csv")
        pop_col = result.columns[0]
        assert pop_col.inferred_type == "numeric"
        assert pop_col.min_value == 4200.0

    def test_all_null_column_warned(self) -> None:
        csv_bytes = b"a,b\n1,\n2,\n3,\n"
        result = parse_csv(csv_bytes, "empty_col.csv")
        assert any("Empty columns" in w for w in result.parse_warnings)


class TestCsvPromptContext:
    """Verify the prompt context output is well-formed."""

    def test_context_includes_filename(self) -> None:
        csv_bytes = b"x,y\n1,2\n"
        result = parse_csv(csv_bytes, "water_usage.csv")
        context = result.to_prompt_context()
        assert "water_usage.csv" in context

    def test_context_includes_column_profiles(self) -> None:
        csv_bytes = b"pressure,zone\n45.2,A\n38.1,B\n"
        result = parse_csv(csv_bytes, "pressure.csv")
        context = result.to_prompt_context()
        assert "pressure" in context
        assert "zone" in context
        assert "NUMERIC" in context or "numeric" in context.lower()

    def test_context_includes_sample_rows(self) -> None:
        csv_bytes = b"city,pop\nPeotone,4200\nMonee,5800\n"
        result = parse_csv(csv_bytes, "cities.csv")
        context = result.to_prompt_context()
        assert "Peotone" in context
        assert "Sample Rows" in context


# ============================================================================
# AI Analyzer — mocked tests
# ============================================================================


class TestAiAnalyzerMocked:
    """Test the analyze_csv function with a mocked Anthropic client."""

    async def test_successful_analysis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import ai_analyzer

        fake_analysis = {
            "summary": "Water usage data for Peotone, IL.",
            "findings": [
                {
                    "title": "High summer usage",
                    "detail": "Usage spikes 40% in July.",
                    "confidence": "confirmed",
                    "category": "water",
                }
            ],
            "recommendations": [
                {
                    "action": "Install smart meters in Zone 3",
                    "rationale": "Identify leak sources.",
                    "priority": "high",
                    "estimated_impact": "Potential $18k/year savings.",
                }
            ],
            "data_quality": {
                "overall_quality": "good",
                "issues": [],
            },
        }

        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "record_analysis"
        mock_tool_block.input = fake_analysis

        mock_usage = MagicMock()
        mock_usage.input_tokens = 500
        mock_usage.output_tokens = 300

        mock_response = MagicMock()
        mock_response.content = [mock_tool_block]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        monkeypatch.setattr(ai_analyzer, "_get_client", lambda: mock_client)

        result = await ai_analyzer.analyze_csv(
            csv_context="## File: test.csv\nRows: 100\nColumns: 3",
            filename="test.csv",
        )

        assert isinstance(result, ai_analyzer.AnalysisResult)
        assert result.analysis["summary"] == "Water usage data for Peotone, IL."
        assert len(result.analysis["findings"]) == 1
        assert len(result.analysis["recommendations"]) == 1
        assert result.input_tokens == 500
        assert result.output_tokens == 300
        assert result.estimated_cost_usd > 0
        assert result.prompt_version == "v1"

    async def test_missing_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import ai_analyzer

        monkeypatch.setattr("app.services.ai_analyzer.settings.ANTHROPIC_API_KEY", None)

        with pytest.raises(ai_analyzer.AnalysisError, match="not configured"):
            await ai_analyzer.analyze_csv("some context", "test.csv")

    async def test_no_tool_use_block_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import ai_analyzer

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "I couldn't analyze this."

        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        monkeypatch.setattr(ai_analyzer, "_get_client", lambda: mock_client)

        with pytest.raises(ai_analyzer.AnalysisError, match="record_analysis"):
            await ai_analyzer.analyze_csv("some context", "test.csv")
