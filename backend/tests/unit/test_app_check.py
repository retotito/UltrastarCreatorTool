"""The libraries the packaged app needs: a missing one is reported, not quietly skipped."""

from services import app_check


def test_all_libraries_are_there_in_development():
    assert app_check.missing_packages() == []


def test_a_missing_library_is_named_with_what_needs_it(monkeypatch):
    monkeypatch.setattr(app_check, "REQUIRED", {"numpy": "everything", "not_a_real_module_xyz": "numbers in lyrics"})
    assert app_check.missing_packages() == ["not_a_real_module_xyz (numbers in lyrics)"]
