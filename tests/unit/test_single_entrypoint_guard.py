"""Single entrypoint guard tests."""

from tools.check_single_entrypoint import check_single_entrypoint


def test_single_entrypoint_guard():
    violations = check_single_entrypoint()
    assert violations == [], "Single entrypoint violations:\n" + "\n".join(violations)

