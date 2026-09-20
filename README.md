# arhugula-omarchy

Omarchy-native agent workspace and voice-control project. The approved
[design](docs/superpowers/specs/2026-09-19-omarchy-agent-workspace-design.md)
and [implementation plan](docs/superpowers/plans/2026-09-19-omarchy-agent-workspace-implementation-plan.md)
define the staged control-plane architecture. LIT owns work; Git owns code.

The current implementation includes repository-only orchestration and the
simulation-only control-plane foundation: strict contracts, VM policy dispatch
with injected executors, and a persistent event journal.
It requires Python 3.11+, Git, and LIT (integration tested with LIT 0.14.0).
No package installation or live Omarchy configuration is needed.

```sh
lit quickstart
lit doctor
lit next
python3 -W error::ResourceWarning -m unittest discover -s tests -v
lit export | python3 -m ops.orchestration.routing
python3 -m ops.orchestration.runner plan
python3 -m ops.bootstrap
python3 -m runtime health
python3 -m ops.build /tmp/arhugula-control-plane.pyz
```

Read [routing](docs/orchestration/routing.md),
[handoff](docs/orchestration/handoff.md), and
[bounded continuation](docs/orchestration/continuation.md) before live use.
The [handoff record](docs/orchestration/handoff.json) and
[execution ledger](docs/orchestration/progress.md) preserve current work and
evidence. Run mode requires an explicitly trusted local worker configuration;
plan mode is read-only. No model-provider process is launched by the tests.

Foundation decisions and interfaces: [stack](docs/decisions/0001-control-plane-stack.md),
[contracts](docs/foundation/contracts.md), [dispatch](docs/foundation/runtime.md),
and [journal](docs/foundation/journal.md). The latest foundation state is in its
[handoff](docs/foundation/handoff.json) and [ledger](docs/foundation/progress.md).
The standalone zipapp runs without downloads; choose a new output path when
building because existing artifacts are never overwritten. Health reports
simulation mode. No live action adapter, service, microphone or host connection
is installed or enabled by the foundation.

The [voice adapter contracts](docs/voice/contracts.md),
[bounded command capture](docs/voice/capture.md), and
[VM-gated routing/confirmation](docs/voice/routing.md) are tested with injected
adapters and synthetic replay. `python3 -m ops.voice_smoke` is a dry run by
default. Its opt-in live mode only opens the root Omarchy menu and requires
separate approval plus a persistent journal. It does not install live voice
capture, Whisper, TTS, keybindings or services. Current voice progress and
remaining acceptance boundaries are in the [voice handoff](docs/voice/handoff.json).
