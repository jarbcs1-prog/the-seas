"""Tests for ai-self-reflection CLI."""
from unittest.mock import patch


def test_reflect_outputs_json():
    from scripts.cli import cmd_reflect

    class Args:
        input = "Test reflection input text"
        mode = "sanity"
        depth = "low"

    result = cmd_reflect(Args())
    assert result == 0


def test_reflect_with_file_input(tmp_path):
    from scripts.cli import cmd_reflect

    input_file = tmp_path / "input.txt"
    input_file.write_text("File-based reflection input")

    class Args:
        input = str(input_file)
        mode = "logic"
        depth = "high"

    result = cmd_reflect(Args())
    assert result == 0


def test_validate_passes():
    from scripts.cli import cmd_validate

    class Args:
        input = "Good reflection with sufficient length and detail"
        threshold = 0.3

    result = cmd_validate(Args())
    assert result == 0


def test_validate_fails():
    from scripts.cli import cmd_validate

    class Args:
        input = "Short"
        threshold = 0.9

    result = cmd_validate(Args())
    assert result == 0


def test_validate_missing_file():
    from scripts.cli import cmd_validate

    class Args:
        input = "/nonexistent/file.txt"
        threshold = 0.5

    result = cmd_validate(Args())
    assert result == 0


def test_report_missing_log():
    from scripts.cli import cmd_report

    class Args:
        log = "/nonexistent/log.md"

    result = cmd_report(Args())
    assert result == 1


def test_report_valid_log(tmp_path):
    from scripts.cli import cmd_report

    log_file = tmp_path / "friction_log.md"
    log_file.write_text("## 2026-07-20 - Test entry\n\nSome content here.")

    class Args:
        log = str(log_file)

    result = cmd_report(Args())
    assert result == 0


def test_bridge_default_scope():
    from scripts.cli import cmd_bridge

    class Args:
        scope = ""
        budget = 500

    result = cmd_bridge(Args())
    assert result == 0


def test_bridge_code_scope():
    from scripts.cli import cmd_bridge

    class Args:
        scope = "code"
        budget = 500

    result = cmd_bridge(Args())
    assert result == 0


def test_bridge_writing_scope():
    from scripts.cli import cmd_bridge

    class Args:
        scope = "writing"
        budget = 500

    result = cmd_bridge(Args())
    assert result == 0


def test_reflect_modes():
    from scripts.cli import cmd_reflect

    for m in ["sanity", "logic", "refine"]:
        class Args:
            input = "Test input"
            mode = m
            depth = "med"

        result = cmd_reflect(Args())
        assert result == 0