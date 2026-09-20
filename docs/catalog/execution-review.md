# Execution-catalog replacement ER-01, 2026-09-20

Shared independent GPT-5.6 Terra/medium review desk inspected immutable
`261a2fd..eaddca72f994a9c43a494302d72875a5be120d48` using the installed review
skill/template. Verdict: **Ready, no findings**. Reviewer reports isolated173
tests/7.666s, runtime/fresh zipapp health OK and clean diff. Lead evidence:
12 focused tests RED then GREEN, full173/173 in10.503s, runtime and fresh package
`/tmp/arhugula-catalog-replacement.IwMqBO/control-plane.pyz` health.

Astra/high accepts the scoped result. Uniform typed revisions, exact monotonic
CAS, immutable snapshots, preview invalidation and retained policy/history are
covered. Catalog-use lifetimes explicitly prevent same-thread RLock callback
replacement and serialize another thread through the synchronous dispatch.
No fix pass or duplicate review is needed.

Declined behaviors remain unfinished, not implicitly accepted:

- No model/MCP mutation API or automatic inventory-data-to-executor mapping.
- No global/cross-plane revocation: a caller must quiesce separate owners.
- No durable revision/review persistence or restarted-owner recovery guarantee.
- No live I/O, provider/transport/deployment acceptance or retrospective undo.
- This document claims no GitHub or CI result, protected-main landing, or final
  LIT closure.

## Combined rehearsal

The private clone from CR-01 additionally merged `eaddca7`, producing synthetic
HEAD `b6be5d08f307b0e84b92d98c1540c2b7f9093037`:344 tests passed in10.009s.
Runtime and fresh `/tmp/arhugula-replacement-rehearsal.qcehQL/control-plane.pyz`
health passed; no merge conflicts or shared-source/ref mutations.

It then incorporated Terra lifecycle projection
`497d97c174b21e400d1d47b7d181b6cb84d68ca5`, producing private synthetic HEAD
`36a8fbee7fb77fae60573faed4c5bc288b952114`:347 tests passed in10.091s with
ResourceWarning errors. Runtime and fresh package
`/tmp/arhugula-final-rehearsal.d91mCy/control-plane.pyz` health passed; diff/status
clean. The clone remains `/tmp/arhugula-integration-rehearsal.UgLY3x/repository`.

Terra's lifecycle change received VL-01 Ready/no findings with316 independently
run tests. Astra also inspected its projection/view delta: only session-keyed
phase/status/code is added, with no action/pending authorization mutation.
This is integration rehearsal evidence, not main/CI evidence. Source branches
and main were not merged or pushed by the rehearsal. Ruff/Python3.11 remain CI
verification requirements, not locally proven results.

`.298.din` and `.298.1td` stay awaiting-integration. Robbo explicitly authorized
clean verified feature-branch publication and protected PRs on 2026-09-20,
leaving main's foreign diagnostics untouched. No merge action or protection bypass
is claimed here. Root owns integration; verify actual main and post-main CI before
closing tickets.
Fresh publication preflight at `c90dc08`:173 tests passed in7.548s; runtime,
fresh zipapp health and diff/status checks passed. The next planned catalog arc unit is `.ejy`;
its real host/credential/network scope is not authorized by these offline tests.
