"""Assemble the Codex-capable plugin: the Foot build, then the additive Codex patches and helper."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

from ops.orchestration.memento_foot.build import build as build_foot, sha

HERE = Path(__file__).parent
PATCHES = {"context-ceiling.codex.patch": "hooks/scripts/context-ceiling.py",
           "ceiling.codex.patch": "skills/ceiling/bin/ceiling",
           "clear-session-ceiling.codex.patch": "hooks/scripts/clear-session-ceiling.py",
           "finalize-session.codex.patch": "skills/message-in-a-bottle/bin/finalize-session",
           "message-in-a-bottle-skill.codex.patch": "skills/message-in-a-bottle/SKILL.md"}
HELPER = "skills/message-in-a-bottle/bin/codex-foot-helper"


def build(upstream, out, pin=None):
    """Build the verified Foot plugin, then apply each Codex patch and add the Codex helper."""
    receipt = build_foot(upstream, out, pin)
    out = Path(out)
    for name in PATCHES:
        patch = (HERE / name).read_text()
        subprocess.run(["patch", "-p1", "--quiet", "-d", str(out)], input=patch[patch.index("--- a/"):],
                       text=True, check=True, capture_output=True)
    shutil.copy(HERE / "codex_foot_helper.py", out / HELPER)
    (out / HELPER).chmod(0o755)
    return {**receipt, "codex_patches": {name: sha(HERE / name) for name in PATCHES},
            "codex_patched": {path: sha(out / path) for path in PATCHES.values()},
            "codex_helper_sha256": sha(out / HELPER)}


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1], sys.argv[2]), indent=2))
