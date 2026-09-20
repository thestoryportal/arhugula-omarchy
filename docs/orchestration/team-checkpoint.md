# Buford team checkpoint

User-directed operating contract, established 2026-09-20. This checkpoint is
context, not proof of current LIT ownership, approval, or verification. Re-read
LIT and Git before acting. Existing diagnostics belong to the user.

## Roles and communication

- Buford: sole integration owner; delegates, reconciles evidence, pushes feature
  branches, opens PRs, monitors CI, merges through protection, verifies main.
- Henrietta: GPT-6 Astra, high effort; complex implementation and design.
- Munson: GPT-5.6 Terra, medium effort; bounded implementation and testing.
- Hannibal: GPT-5.6 Terra, medium effort; independent material-impact review.

Agents communicate only with Buford. Each assignment identifies ticket, goal,
scope, worktree, immutable baseline, applicable governance, expected evidence,
and stop conditions. Never create a second writer on an existing lane. Four
concurrent slots include Buford; additional helpers require a free slot.

## Arc and integration gates

1. Read `lit quickstart`, ticket/ancestor requirements, current claims, applicable
   governance and existing artifacts. Verify rather than trust historical notes.
2. Ground the ticket goal and concise implementation strategy. Buford attests
   the approach before assigning implementation in an isolated worktree.
3. Implement and verify prescribed tests, negative probes/mutations and reviews.
   Handoff includes immutable SHA, exact scope, commands/results, review findings
   and dispositions, remaining limitations, and artifact paths.
4. Buford verifies the evidence. Missing required evidence returns to the same
   implementer with a concise remediation list; no premature all-green claim.
5. Before integration, the implementer records personal learnings and grounds
   the next eligible ticket. Buford saves the next handoff and uses a fresh
   context with `lit next` and that handoff. This interface has no literal
   `/clear` operation; use a fresh isolated agent context and revalidate routing.
6. Buford owns push/PR/CI/protected merge/post-main CI. A CI failure goes to a
   Terra agent for diagnosis and proposed fix; Buford reviews that proposal
   before implementation. Fixes use an isolated worktree and local commits.
7. Close only after delivered content is on main with all required post-main
   checks successful. Independent agent review is required; separate GitHub-user
   approval is not. The user explicitly revoked that extra gate.

Do not leave workers waiting for CI when independent authorized work exists.
Do not invent work or bypass dependencies merely to occupy all slots. During
active supervision use bounded waits, check completion and report meaningful
changes. This checkpoint does not install a persistent background supervisor.

## Initial reconciliation

- Main inspected at `8f429f711bc0bdf2f4935050b976afd4956f6a45`.
- Existing untracked `docs/diagnostics/` must remain untouched.
- Open PRs: #4 CI hardening, #9 closure evidence, #10 catalog, #11 voice,
  #12 lifecycle projections. Existing worktrees and claims must be reused only
  after ownership checks, not overwritten or automatically taken over.
- PR #4 remote head: `91e9579c91d8493278b53a9e513a6dbb9bb5bb63`;
  its local checkout is stale at `9e54456`. Three remote checks passed at the
  inspected head; a fresh rerun (attempt 2) passed all three jobs.
- Main protection requires `Python test suite`, `Ruff lint`, and
  `Runtime and package smoke`, an up-to-date branch, and conversation resolution.
  The user revoked the separate GitHub approval gate; Buford removed only
  `required_pull_request_reviews` through the GitHub API and verified all three
  required checks and strict branch freshness remain configured.
- PRs #9 and #11 have only Python CI recorded at inspection. Incorporating
  CI hardening and rerunning all required checks precedes integration.
- Voice P1 work already exists. Live entrypoint remains unbound; concrete GUI,
  provider integration and live acceptance are not proven by unit tests.
  Historical recording consent was consumed; it is not reusable authorization.
- User supplied authoritative Laws source: https://github.com/promptctl/laws.
  The full active Laws library and upstream ticket reference are preserved under
  `docs/governance/laws/`, pinned at
  `4fb6c66df5d084a215c798c84e3cbc6090f695f9`. Read them before the corresponding
  work; initial inventory reports predate this grounding.
  User clarified that all Laws guide individuals, the team, and the workflow.
  Apply them throughout the work using the guidance appropriate to each medium.
- Fresh independent checks at PR #4 head: 164 tests pass; source and zipapp
  health pass in simulation. Remote Ruff passes; local Ruff is unavailable.
  Hannibal separately reviewed CI and the observability implementation absent
  from main, clearing both at the exact remote SHA. Initial concerns about pure
  recommendation/filter functions were withdrawn after checking their actual
  scope and lack of production consumers. These APIs confer no authority;
  future live consumers require their own trusted boundaries. Projection
  context/revision handling remains a non-blocking integration limitation.
  The former `REVIEW_REQUIRED` stop is superseded by explicit user direction.

## Current bounded assignments

- Henrietta: verified catalog PR10 (173 tests and four detected mutations), now
  attesting existing voice P1 evidence for PR11.
- Munson: removes superseded GitHub approval gates from branch guidance/fixtures.
- Hannibal: reviews closure evidence corrections for PR9.
- Buford: owns publication, required CI, merge and post-main verification.

## Integration evidence

PR4 is merged at `5ce5c3bd07f9812a5f8eaf6d0cdc7040af501cb9`.
All three checks passed on rerun `35509955644` attempt 2 and post-main run
`35527199735`. GitHub reported the PR already merged when Buford issued the
merge request; observed landing and CI are verified, not attributed to that call.

## Verified setup evidence and learnings

The supervisor compared all 13 copied Laws files directly with content fetched
from the pinned upstream revision; all matched exactly. `git diff --check` passed.
Munson reviewed initial Code/Prompt routing and provenance with no material issue;
the later full-library extension was source-compared and read back by Buford.

Munson reproduced PR #4's 164 passing tests and simulation source/zipapp health
from `/tmp/arhugula-ci-hardening-GRJOVI`, an archive of its actual remote SHA.
Main baseline passed 145 tests. Local Ruff was unavailable; remote CI supplies
that gate's evidence. Do not substitute a stale checkout's green test result for
the commit actually being delivered. Record the archive SHA before extraction.

Henrietta found reviewed implementations absent from main in existing clean
worktrees. Compare their content and handoffs before planning new code. Isolated
ASR success and seam tests do not prove assembled entrypoint/provider behavior.

Reconcile agent reports before advancing. No live release, live binding,
ticket closure, or ongoing unattended monitoring is claimed by this record.
