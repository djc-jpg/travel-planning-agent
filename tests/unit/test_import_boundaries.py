"""Architecture guard tests."""

from tools.check_import_boundaries import check_import_boundaries


def test_import_boundaries_guard():
    violations = check_import_boundaries("app")
    assert violations == [], "Import boundary violations:\n" + "\n".join(violations)

