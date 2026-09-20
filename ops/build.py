"""Build a self-contained stdlib zipapp without package downloads."""
import argparse
from pathlib import Path
import shutil
import tempfile
import zipapp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new artifact path")
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="arhugula-build-") as directory:
        staging = Path(directory)
        for package in ("runtime", "schemas"):
            shutil.copytree(source / package, staging / package,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        zipapp.create_archive(staging, target=args.output, main="runtime.cli:main",
                              interpreter="/usr/bin/env python3", compressed=True)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
