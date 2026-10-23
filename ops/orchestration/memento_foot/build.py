"""Assemble the installed plugin: pinned upstream bytes, the additive Foot patch, the helper."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).parent
LAUNCHER = "skills/message-in-a-bottle/bin/finalize-session"
HELPER = "skills/message-in-a-bottle/bin/foot-helper"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(upstream, out, pin=None):
    """Copy the verified pin, apply the Foot patch to the launcher, add the helper."""
    pin = json.loads((HERE / "PIN.json").read_text()) if pin is None else pin
    source, out = Path(upstream), Path(out)
    if out.exists():
        raise ValueError(f"{out} exists; build into a new directory")
    found = {str(p.relative_to(source)) for p in source.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts}
    expected = {**pin["files"], **pin["replaced"]}
    if found != set(expected) or any(sha(source / n) != d for n, d in expected.items()):
        raise ValueError("upstream tree does not match the pinned hashes")
    shutil.copytree(source, out, ignore=shutil.ignore_patterns("__pycache__"))
    patch = (HERE / "finalize-session.foot.patch").read_text()
    subprocess.run(["patch", "-p1", "--quiet", "-d", str(out)], input=patch[patch.index("--- a/"):],
                   text=True, check=True, capture_output=True)
    shutil.copy(HERE / "foot_helper.py", out / HELPER)
    (out / HELPER).chmod(0o755)
    return {"upstream_commit": pin["commit"], "launcher_upstream_sha256": expected[LAUNCHER],
            "launcher_patched_sha256": sha(out / LAUNCHER), "patch_sha256": sha(HERE / "finalize-session.foot.patch"),
            "helper_sha256": sha(out / HELPER)}


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1], sys.argv[2]), indent=2))
