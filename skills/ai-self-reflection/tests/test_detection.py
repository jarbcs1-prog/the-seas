"""Tests for ai-self-reflection friction detection and scoring."""
import pytest
from scripts.cli import (
    _detect_friction,
    _score_reflection,
    _get_recommendation,
    _parse_log,
    _find_patterns,
    _generate_constraints,
)


class TestDetectFriction:
    def test_no_friction(self):
        result = _detect_friction("This is a straightforward statement.")
        assert result["count"] == 0
        assert result["indicators"] == []

    def test_concession_detected(self):
        result = _detect_friction("However, this might not be correct.")
        assert "concession_detected" in result["indicators"]

    def test_hedging_detected(self):
        result = _detect_friction("Perhaps this is the right approach.")
        assert "hedging_detected" in result["indicators"]

    def test_template_language_detected(self):
        result = _detect_friction("In conclusion, the results show...")
        assert "template_language" in result["indicators"]

    def test_multiple_indicators(self):
        result = _detect_friction("However, perhaps this might be wrong.")
        assert result["count"] >= 2

    def test_empty_text(self):
        result = _detect_friction("")
        assert result["count"] == 0


class TestScoreReflection:
    def test_empty_text_scores_zero(self):
        assert _score_reflection("") == 0.0

    def test_short_text_low_score(self):
        score = _score_reflection("Hi")
        assert 0.0 <= score <= 1.0

    def test_long_text_higher_score(self):
        long_text = "A " * 500
        score = _score_reflection(long_text)
        assert score > 0.5

    def test_friction_penalty(self):
        text = "However, perhaps this might be wrong."
        score = _score_reflection(text)
        # Friction penalty should reduce the score
        assert score < 1.0

    def test_no_friction_no_penalty(self):
        long_text = "A " * 500
        score = _score_reflection(long_text)
        assert score > 0.5


class TestGetRecommendation:
    def test_sanity_mode(self):
        result = _get_recommendation("Some text", "sanity", "low")
        assert "accuracy check" in result.lower()

    def test_high_friction(self):
        # Need 3+ different indicator types to trigger high friction
        text = "However, perhaps this might be wrong. In conclusion, the results show..."
        result = _get_recommendation(text, "logic", "med")
        assert "high friction" in result.lower()

    def test_logic_mode(self):
        result = _get_recommendation("Some text", "logic", "med")
        assert "logic" in result.lower()

    def test_refine_mode(self):
        result = _get_recommendation("Some text", "refine", "high")
        assert "refine" in result.lower()


class TestParseLog:
    def test_empty_log(self):
        assert _parse_log("") == []

    def test_single_entry(self):
        content = "## 2026-07-20 - Test entry\n\nSome content."
        entries = _parse_log(content)
        assert len(entries) == 1
        assert entries[0]["type"] == "section"

    def test_multiple_entries(self):
        content = "## 2026-07-20 - Entry one\n\nContent.\n## 2026-07-21 - Entry two\n\nMore content."
        entries = _parse_log(content)
        assert len(entries) == 2

    def test_non_section_lines_ignored(self):
        content = "Some regular text\n## 2026-07-20 - Entry\nMore text"
        entries = _parse_log(content)
        assert len(entries) == 1


class TestFindPatterns:
    def test_empty_entries(self):
        assert _find_patterns([]) == []

    def test_extracts_dates(self):
        entries = [
            {"date": "2026-07-20", "type": "section"},
            {"date": "2026-07-21", "type": "section"},
        ]
        patterns = _find_patterns(entries)
        assert len(patterns) == 2
        assert "2026-07-20" in patterns

    def test_limits_to_five(self):
        entries = [{"date": f"2026-07-{d:02d}", "type": "section"} for d in range(1, 10)]
        patterns = _find_patterns(entries)
        assert len(patterns) <= 5

    def test_filters_non_sections(self):
        entries = [
            {"date": "2026-07-20", "type": "section"},
            {"date": "some other type", "type": "other"},
        ]
        patterns = _find_patterns(entries)
        assert len(patterns) == 1


class TestGenerateConstraints:
    def test_general_scope(self):
        constraints = _generate_constraints("general")
        assert "Avoid templated language" in constraints
        assert "Use concrete examples" in constraints

    def test_code_scope(self):
        constraints = _generate_constraints("code")
        assert "Prefer explicit over implicit" in constraints
        assert "Validate inputs" in constraints

    def test_writing_scope(self):
        constraints = _generate_constraints("writing")
        assert "Vary sentence length" in constraints
        assert "Use active voice" in constraints

    def test_unknown_scope_uses_general(self):
        constraints = _generate_constraints("unknown")
        assert constraints == _generate_constraints("general")


class TestValidateThreshold:
    def test_passes_threshold(self):
        from scripts.cli import cmd_validate

        class Args:
            input = "Good reflection with sufficient length and detail"
            threshold = 0.3

        result = cmd_validate(Args())
        assert result == 0

    def test_fails_threshold(self):
        from scripts.cli import cmd_validate

        class Args:
            input = "Short"
            threshold = 0.9

        result = cmd_validate(Args())
        assert result == 0
