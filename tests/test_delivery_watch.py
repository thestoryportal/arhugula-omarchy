"""Include the operator watcher's behavioral regressions in normal repository CI."""

from pathlib import Path
import unittest


def load_tests(_loader, _tests, _pattern):
    return unittest.TestLoader().discover(
        str(Path(__file__).resolve().parents[1] / "tools" / "delivery_watch"),
        pattern="test_*.py",
    )
