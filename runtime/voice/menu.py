"""One narrow opt-in desktop executor. No dynamic shell or arbitrary routes."""
import subprocess

from ..contracts import Command, Error, decode, encode
from ..core import Outcome


class OmarchyMenuExecutor:
    def __call__(self, command):
        try:
            command = decode(encode(command))
            if not isinstance(command, Command) or command.capability_id != "menu.open" or dict(command.arguments) != {"name": "main"}:
                raise ValueError("unsupported action")
        except ValueError:
            return Outcome("failed", error=Error(1, "menu.unsupported", "Only the root Omarchy menu action is supported", False))
        try:
            result = subprocess.run(["/usr/share/omarchy/bin/omarchy", "menu", "summon", "root"],
                                    capture_output=True, text=True, timeout=5, check=False)
        except FileNotFoundError:
            return Outcome("failed", error=Error(1, "menu.unavailable", "Omarchy executable is unavailable", False))
        except (OSError, subprocess.SubprocessError):
            return Outcome("uncertain", error=Error(1, "menu.uncertain", "Menu request outcome is unknown; inspect before retry", False))
        if result.returncode != 0:
            return Outcome("uncertain", error=Error(1, "menu.uncertain", "Menu request was not acknowledged; inspect before retry", False))
        return Outcome("success", {"mode": "live", "request_acknowledged": True,
                                   "visibility_verified": False})
