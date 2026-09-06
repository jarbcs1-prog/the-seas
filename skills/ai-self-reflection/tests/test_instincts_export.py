"""Tests for ai-self-reflection instincts export commands."""
import json

import pytest

from scripts.comprehensive_cli import (
    _build_filter_description,
    _build_instinct,
    _capability_id,
    _count_successful_validations,
    cmd_instincts_export,
    cmd_instincts_report,
)

SAMPLE_CAPABILITIES = [
    {
        "lesson": "Choose representation after identifying user information need",
        "scope": "Explanations, documentation",
        "category": "structural",
        "confidence": 0.8333333333333334,
        "evidence": 3,
        "level": 2,
        "created": "2026-08-08T12:18:20.171065",
        "last_updated": "2026-08-08T12:25:59.331064",
        "supporting_events": ["2026-08-08T12:17:52.050392"],
        "validation_score": 0.657,
        "promotion_history": [{"level": 2, "date": "2026-08-08T12:18:59.543987"}],
    },
    {
        "lesson": "Acknowledge uncertainty explicitly when evidence is thin",
        "scope": "Technical explanations, debugging",
        "category": "epistemic",
        "confidence": 0.7666666666666667,
        "evidence": 3,
        "level": 2,
        "created": "2026-08-08T12:19:45.920013",
        "supporting_events": ["2026-08-08T12:19:14.990688"],
        "validation_score": 0.657,
        "promotion_history": [{"level": 2, "date": "2026-08-08T12:21:04.243691"}],
    },
]

SAMPLE_VALIDATIONS = [
    {
        "timestamp": "2026-08-08T12:18:25.841779",
        "capability": "Choose representation after identifying user information need",
        "task": "System design review",
        "outcome": "Identified shared abstraction",
        "success": True,
        "delta": 0.05,
    },
    {
        "timestamp": "2026-08-08T12:18:47.878553",
        "capability": "Choose representation after identifying user information need",
        "task": "Code review",
        "outcome": "Caught premature abstraction",
        "success": True,
        "delta": 0.05,
    },
    {
        "timestamp": "2026-08-08T12:19:56.037265",
        "capability": "Acknowledge uncertainty explicitly when evidence is thin",
        "task": "Debugging",
        "outcome": "User caught unverified assumption",
        "success": True,
        "delta": 0.05,
    },
    {
        "timestamp": "2026-08-08T12:20:23.766529",
        "capability": "Acknowledge uncertainty explicitly when evidence is thin",
        "task": "API design",
        "outcome": "Good catch on assumption",
        "success": False,
        "delta": 0.05,
    },
]


@pytest.fixture
def patched_memory(tmp_path, monkeypatch):
    """Create temp JSON files and patch module-level path constants."""
    caps_file = tmp_path / "capabilities_memory.json"
    caps_file.write_text(json.dumps(SAMPLE_CAPABILITIES))
    vals_file = tmp_path / "validation_history.json"
    vals_file.write_text(json.dumps(SAMPLE_VALIDATIONS))

    import scripts.comprehensive_cli as mod
    monkeypatch.setattr(mod, "CAPABILITIES_MEMORY", caps_file)
    monkeypatch.setattr(mod, "VALIDATION_HISTORY", vals_file)
    return caps_file, vals_file


class TestCountSuccessfulValidations:
    def test_counts_successes(self):
        count = _count_successful_validations(
            "Choose representation after identifying user information need",
            SAMPLE_VALIDATIONS,
        )
        assert count == 2

    def test_no_validations_returns_zero(self):
        count = _count_successful_validations("nonexistent lesson", SAMPLE_VALIDATIONS)
        assert count == 0

    def test_all_failures(self):
        vals = [
            {"capability": "test", "success": False},
            {"capability": "test", "success": False},
        ]
        count = _count_successful_validations("test", vals)
        assert count == 0


class TestCapabilityId:
    def test_generates_stable_id(self):
        cap = {"lesson": "test lesson", "created": "2026-01-01T00:00:00"}
        id1 = _capability_id(cap)
        id2 = _capability_id(cap)
        assert id1 == id2

    def test_id_prefix(self):
        cap = {"lesson": "test lesson", "created": "2026-01-01T00:00:00"}
        assert _capability_id(cap).startswith("instinct-")

    def test_different_caps_different_ids(self):
        cap1 = {"lesson": "lesson A", "created": "2026-01-01T00:00:00"}
        cap2 = {"lesson": "lesson B", "created": "2026-01-01T00:00:00"}
        assert _capability_id(cap1) != _capability_id(cap2)


class TestBuildInstinct:
    def test_maps_all_fields(self):
        instinct = _build_instinct(SAMPLE_CAPABILITIES[0], SAMPLE_VALIDATIONS)
        assert instinct["id"].startswith("instinct-")
        assert instinct["trigger"] == "Explanations, documentation"
        assert instinct["action"] == "Choose representation after identifying user information need"
        assert instinct["confidence"] == 0.8333
        assert instinct["category"] == "structural"
        assert instinct["applications"] == 3
        assert instinct["successes"] == 2
        assert instinct["source"] == "session-observation"

    def test_confidence_rounded(self):
        cap = {
            "lesson": "test",
            "scope": "test scope",
            "category": "epistemic",
            "confidence": 0.833333333,
            "evidence": 1,
            "created": "2026-01-01",
        }
        instinct = _build_instinct(cap, [])
        assert instinct["confidence"] == 0.8333

    def test_zero_validations(self):
        instinct = _build_instinct(SAMPLE_CAPABILITIES[1], [])
        assert instinct["successes"] == 0


class TestBuildFilterDescription:
    def test_no_filters(self):
        class Args:
            min_confidence = None
            category = None
        assert _build_filter_description(Args()) == "all"

    def test_confidence_filter(self):
        class Args:
            min_confidence = 0.8
            category = None
        assert _build_filter_description(Args()) == "confidence >= 0.8"

    def test_category_filter(self):
        class Args:
            min_confidence = None
            category = "structural"
        assert _build_filter_description(Args()) == "category == structural"

    def test_both_filters(self):
        class Args:
            min_confidence = 0.7
            category = "epistemic"
        desc = _build_filter_description(Args())
        assert "confidence >= 0.7" in desc
        assert "category == epistemic" in desc


class TestInstinctsExport:
    def test_export_all(self, patched_memory):
        caps_file, vals_file = patched_memory
        assert caps_file.exists()
        assert vals_file.exists()
        class Args:
            min_confidence = None
            category = None
            output = None
        result = cmd_instincts_export(Args())
        assert result == 0

    def test_export_min_confidence_filter(self, patched_memory):
        caps_file, vals_file = patched_memory
        assert caps_file.exists()
        class Args:
            min_confidence = 0.8
            category = None
            output = None
        result = cmd_instincts_export(Args())
        assert result == 0

    def test_export_category_filter(self, patched_memory):
        caps_file, vals_file = patched_memory
        assert vals_file.exists()
        class Args:
            min_confidence = None
            category = "epistemic"
            output = None
        result = cmd_instincts_export(Args())
        assert result == 0

    def test_export_to_file(self, patched_memory, tmp_path):
        caps_file, _ = patched_memory
        assert caps_file.exists()
        out_file = tmp_path / "instincts_export.json"
        class Args:
            min_confidence = None
            category = None
            output = str(out_file)
        result = cmd_instincts_export(Args())
        assert result == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "instincts" in data
        assert "metadata" in data
        assert len(data["instincts"]) == 2

    def test_export_filters_combined(self, patched_memory, tmp_path):
        caps_file, _ = patched_memory
        assert caps_file.exists()
        out_file = tmp_path / "filtered.json"
        class Args:
            min_confidence = 0.8
            category = "structural"
            output = str(out_file)
        result = cmd_instincts_export(Args())
        assert result == 0
        data = json.loads(out_file.read_text())
        assert len(data["instincts"]) == 1
        assert data["instincts"][0]["category"] == "structural"
        assert data["instincts"][0]["confidence"] >= 0.8


class TestInstinctsReport:
    def test_report_returns_zero(self, patched_memory):
        caps_file, _ = patched_memory
        assert caps_file.exists()
        class Args:
            min_confidence = None
            category = None
        result = cmd_instincts_report(Args())
        assert result == 0

    def test_report_with_min_confidence(self, patched_memory):
        caps_file, _ = patched_memory
        assert caps_file.exists()
        class Args:
            min_confidence = 0.9
            category = None
        result = cmd_instincts_report(Args())
        assert result == 0
