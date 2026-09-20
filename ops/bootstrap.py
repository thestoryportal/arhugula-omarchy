"""Offline developer bootstrap: check interpreter and run the repository suite."""
from pathlib import Path
import subprocess
import sys


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer required")
    root = Path(__file__).resolve().parents[1]
    return subprocess.call([sys.executable, "-W", "error::ResourceWarning", "-m",
                            "unittest", "discover", "-s", "tests", "-v"], cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
