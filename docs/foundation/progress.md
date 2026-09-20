# Foundation execution ledger

Plan: docs/superpowers/plans/2026-09-20-control-plane-foundation.md
Spec: docs/superpowers/specs/2026-09-19-omarchy-agent-workspace-design.md
Branch: feat/control-plane-foundation; baseline c018806.

User explicitly continued beyond the prior autonomy-unclassified boundary.
The first unit is repository-only and reviewed autonomous-safe. Stack choices
are delegated implementation decisions in the approved project design.

Pre-flight interfaces: stack -> strict contracts -> in-memory dispatch ->
journal -> circle-back. Codecs are shared by runtime and both journals.
The existing LIT spine omits the approved plan's A.4 journal unit; create it
through LIT and rank it after core, before circle-back. No database edits.

Ruling: Python standard library and zipapp avoid new dependency/network
requirements while preserving the VM authority boundary. Cost if wrong:
a documented port of the contracts/adapter seams, not a live deployment change.

t78: tests first failed on missing runtime/build modules. Health is explicitly
simulation-only; zipapp tested from outside the checkout using isolated Python.
