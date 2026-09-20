# arhugula-omarchy

Omarchy-native agent workspace and voice-control project. The approved
[design](docs/superpowers/specs/2026-09-19-omarchy-agent-workspace-design.md)
and [implementation plan](docs/superpowers/plans/2026-09-19-omarchy-agent-workspace-implementation-plan.md)
define the staged control-plane architecture. LIT owns work; Git owns code.

The current implementation is the repository-only orchestration bootstrap.
It requires Python 3, Git, and LIT (integration tested with LIT 0.14.0).
No package installation or live Omarchy configuration is needed.

```sh
lit quickstart
lit doctor
lit next
python3 -W error::ResourceWarning -m unittest discover -s tests -v
lit export | python3 -m ops.orchestration.routing
python3 -m ops.orchestration.runner plan
```

Read [routing](docs/orchestration/routing.md),
[handoff](docs/orchestration/handoff.md), and
[bounded continuation](docs/orchestration/continuation.md) before live use.
The [handoff record](docs/orchestration/handoff.json) and
[execution ledger](docs/orchestration/progress.md) preserve current work and
evidence. Run mode requires an explicitly trusted local worker configuration;
plan mode is read-only. No model-provider process is launched by the tests.
