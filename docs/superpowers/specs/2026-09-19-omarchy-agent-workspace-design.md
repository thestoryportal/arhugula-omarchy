# Omarchy Agent Workspace and Voice Control Design

**Status:** Approved for specification review

**Date:** 2026-09-19

## Destination

Build an Omarchy-native local agent workspace that coordinates multiple agents,
local LLMs, execution lanes, Git worktrees, LIT issues, voice interaction,
observability, evaluation, memory, and recovery from one authoritative control
plane.

Voice control is the first flagship interface and vertical slice of the larger
workspace. It must work independently of an agent CLI while remaining usable
inside Codex and other focused applications.

## Architectural premise

The system uses a central control plane with typed commands, an event-oriented
runtime, explicit policy enforcement, and multiple clients:

```text
Voice / Panel / Keyboard / Terminal / MCP clients
                         |
                 Control-plane API
                         |
       Policy -> Intent -> Typed Action -> Executor
                         |
   Omarchy / Hyprland / Apps / Git / LIT / Agents
                         |
        Event journal -> Observability projections
```

The first implementation is event-oriented rather than fully event-sourced.
Authoritative state remains in focused stores and external systems; runtime
events provide observability, evaluation, recovery, and replayable diagnostics.

## Deployment and authority boundaries

### Linux VM: authoritative Omarchy control zone

The VM owns:

- PipeWire microphone capture, audio devices, playback, mute, and ducking.
- Whisper by default.
- The control-plane API.
- Command and capability catalogs.
- Profiles, policies, risk tiers, confirmations, and freshness rules.
- The MCP policy broker and approved local MCP servers.
- Hyprland, Omarchy, application, Git, LIT, and agent execution.
- The observability panel and runtime event journal.
- Local fallbacks when the Mac host is unavailable.

### Mac host: accelerated model services zone

The host provides:

- Primary local LLM inference using M3 acceleration.
- Heavy TTS, voice-cloning, and evaluator models.
- Large model artifacts and voice profiles when configured there.
- Private host-only services reachable by the VM.

The host receives text and bounded structured context by default. It never has
unrestricted Omarchy or shell authority and never executes VM actions.

### Authority rules

- Models propose intents or typed actions; they never authorize them.
- The VM validates every proposal against the current catalog and policy.
- Only the VM executor performs state-changing actions.
- MCP tools pass through the same VM policy boundary.
- Voice, panel, keyboard, terminal, and MCP clients use shared contracts.
- Runtime networking is deny-by-default. Approved update checks use a separate
  controlled path.
- Host failure degrades model-dependent capabilities without disabling safe local
  controls.

## Horizontal technical layers

1. **Hardware and audio:** microphones, PipeWire, devices, mute, playback,
   ducking, and switching.
2. **Capture:** dictation, command, conversation, adaptive silence detection,
   limits, cancellation, and interruption.
3. **Speech:** Whisper, normalization, pronunciation dictionaries, confidence,
   language profiles, and replayable recordings.
4. **Context:** focused application, workspace, monitor, Omarchy state,
   approved screen/OCR context, memory retrieval, and catalog version.
5. **Intent:** aliases, semantic routing, candidates, clarification, ranking,
   structured output, repair, and fallback models.
6. **Capability catalog:** Omarchy commands, Hyprland bindings, menus, installed
   applications, MCP resources, typed tools, risk, enablement, freshness, and
   provenance.
7. **Policy:** permissions, risk, confirmation, profiles, lock-screen rules,
   mute behavior, screen-sharing rules, network policy, and data boundaries.
8. **MCP and integrations:** resources, typed tools, application adapters,
   generic catalog actions, trust, capabilities, and sandboxing.
9. **Execution:** Omarchy, Hyprland, application, Git, LIT, and agent actions;
   validation, retry, verification, rollback, and partial failure.
10. **Agent orchestration:** sessions, models, lanes, workspaces, claims,
    lifecycle, pause/resume, handoff, recovery, and assignment.
11. **Models and providers:** LLM, Whisper, TTS, cloning, evaluator models,
    placement, versions, health, and fallbacks.
12. **Memory and learning:** archive, frontmatter, summaries, retrieval,
    structured memory, corrections, datasets, pruning, evaluation, and promotion.
13. **Runtime events:** normalized state, model, tool, execution, approval,
    profile, failure, and recovery events.
14. **Persistence:** configuration, profiles, catalogs, journal, observability,
    memory, datasets, metadata, backups, retention, and deletion.
15. **Presentation:** status panel, observability workspace, detached comparison,
    notifications, diagrams, keyboard controls, terminals, and voice responses.
16. **Lifecycle:** setup, health, updates, migrations, backups, candidate restore,
    regression tests, and rollback.

Lower layers cannot bypass policy or reach upward to become an authority. A model
cannot call an executor directly; an MCP server cannot alter policy; a UI cannot
bypass validation; and an observation cannot be treated as execution truth.

## Vertical end-to-end slices

The implementation order is:

1. Control-plane health.
2. Existing Home/End dictation.
3. One safe `KP_EQUAL` Omarchy command.
4. Semantic routing and spoken clarification.
5. Confirmation and correction.
6. Dynamic Omarchy catalog.
7. Persistent observability workspace.
8. Mac-host model gateway.
9. Conversational mode and persistent memory.
10. TTS and selectable voice profiles.
11. Voice cloning and iterative sample capture.
12. Supported application integrations.
13. MCP resources, typed tools, and policy-gated generic actions.
14. Agent lifecycle and Omarchy lane orchestration.
15. LIT/Git workflow integration.
16. Multi-agent observability and dynamic topology diagrams.
17. Memory and learning promotion loops.
18. Recovery, maintenance, and release hardening.

Every slice must leave a usable, testable capability with a control-plane
contract, executor or simulator, events, failure behavior, automated tests,
manual acceptance, and rollback or disable behavior where applicable.

## Voice interaction

### Dictation

- `Home` starts dictation.
- `End` stops dictation.
- Whisper runs locally in the VM.
- Output types into the focused application with clipboard fallback.
- Dictation remains independent of command mode.

### Command mode

- `KP_EQUAL` starts one-shot command capture.
- Capture ends after adaptive silence or a maximum duration.
- Command speech never leaks into the focused application.
- Unknown or unsafe phrases are discarded or clarified.
- Clarification requires a new `KP_EQUAL` turn.
- Corrections are previewed before execution.
- Confirmation works by panel, keyboard, or voice.

### Conversation

- Entry and exit are configurable by voice, panel, and keyboard.
- Conversation ends by explicit spoken command or a setup-selected unbound key.
- Wake words are optional and disabled by default.
- Conversational execution is configurable by profile and risk tier.
- Persistent local conversation history uses context-optimized retrieval.
- Current speech wins over conflicting memory only after clarification.

### Responses and audio

- Response behavior is configurable by event type and profile.
- Clarifications, errors, confirmations, warnings, and conversation may use
  different voices and verbosity.
- Routine status remains visual unless configured otherwise.
- TTS runs on the host for heavy models and in the VM for lightweight fallbacks.
- Audio plays through the VM.
- Speech supports interruption by `KP_EQUAL`, a dedicated key, or “stop/cancel”.
- Ducking, pausing, or mixing is configurable by profile and application.

## Catalog, intent, and execution

The VM maintains the authoritative catalog of Omarchy commands, menus,
Hyprland bindings, custom bindings, installed applications, MCP capabilities,
risk tiers, enablement, and provenance.

The catalog is versioned and refreshed when relevant configuration changes. New
custom bindings are discovered automatically and receive first-use review.
Optional guided voice calibration teaches aliases, vocabulary, and recurring
transcription errors; training is never required for safe commands.

The host receives the transcript, active mode, focused context, current state,
and the most relevant catalog candidates rather than the entire catalog on every
request. The model returns an intent or typed tool call referencing a catalog ID.
The VM validates the catalog version, arguments, state freshness, risk, and
confirmation before execution.

The MCP surface is layered:

- Resources expose read-only state and discovery.
- Typed tools expose stable Omarchy and application capabilities.
- A generic action tool handles newly discovered commands only behind policy.

No unrestricted shell generation is permitted.

## Agent workspace

Hyprland and Omarchy are the primary workspace surface. tmux and terminals are
supported adapters, not the authoritative workspace model.

Each lane has a stable identity, LIT unit, Git branch or worktree, model,
session lifecycle, Hyprland placement, presentation surface, health state, and
handoff record.

The workspace provides compact status, lane overview, detailed lane, topology,
and review views. Agent state is independent from window state: closing a window
does not silently terminate an agent.

## Event and memory model

Every meaningful transition emits a versioned event with event ID, timestamp,
session/profile/lane/agent IDs, source interface, provider/model versions,
catalog/policy versions, action, result, timing, provenance, and sensitivity.

Authoritative state remains in Omarchy, LIT, Git, profiles, catalogs, and focused
stores. Observability projections are rebuildable and never authorize execution.

Full conversation history is stored locally in an append-only archive. Frontmatter,
rolling summaries, durable summaries, and exact/semantic indexes make retrieval
token-efficient. Structured memory records confidence, age, provenance, review
status, category, and source turns.

Memory is extracted automatically, but use before review is configurable by
category and profile. Stale, duplicate, contradictory, or low-confidence memory
is identified by scheduled and manual pruning policies. Full purge can remove
active data, derivatives, caches, backups, and evaluation copies.

## Policy, privacy, and trust

- Every capability has a stable ID, risk tier, enabled state, and provenance.
- Risk tiers control execution, preview, confirmation, or blocking.
- High-impact actions are disabled or confirmation-required by default.
- Any speaker may act after activation; speaker identity is not required.
- Microphone audio stays in the VM by default.
- Screen/OCR context is on-demand, visibly indicated, redacted, and not retained
  by default.
- Telemetry is disabled wherever technically possible.
- Third-party MCP servers require source, license, capability, filesystem,
  subprocess, and network review before activation.
- Runtime networking is deny-by-default with narrow approved update access.
- Local filesystem permissions protect persistent records by default.
- Public voice-profile export is a separate mode requiring provenance, consent,
  source, model, license, and intended-use metadata.

## Testing and promotion

Testing uses synthetic transcripts, recorded speech replay, and live microphone
tests. State-changing tests run in simulation, then disposable profiles or an
isolated VM; live execution is limited to explicitly approved harmless actions.

Promotion gates are component-specific:

- Command safety, accuracy, clarification, verification, and latency.
- Whisper phrase accuracy and device robustness.
- TTS intelligibility, pronunciation, latency, and resource use.
- Voice-cloning coverage and quality.
- MCP permissions and tool validation.
- Resource budgets and failure behavior.
- Manual observability review and rollback readiness.

Evaluation uses deterministic checks, execution evidence, an independent local
evaluator, and human review for disagreement or consequential cases. Promotion
tests use pinned replay bundles. Adaptive baselines can detect regressions but
cannot relax immutable safety thresholds.

## LIT workflow and decomposition

The backlog uses LIT’s native model:

- Epic: releasable voice or workspace capability.
- Arc: parent feature under an epic.
- Unit: leaf task, feature, bug, or chore with one test target.
- Topic: stable domain label.
- Lane: parallel workstream.
- Blocks: genuine cross-boundary prerequisites only.
- Parent-child: containment.
- Rank: ordered work within a lane.
- Related-to: non-blocking evidence or coordination.

Each unit names its observable outcome, boundary, test target, interfaces/fakes,
acceptance criteria, failure behavior, validation commands, dependencies,
observability events, and rollback/disable path.

Every epic includes a circle-back unit for reconciliation, refactoring, design
updates, full regression, and release preparation. Decisions and discoveries are
captured in issue comments; follow-up work is filed while context is fresh.

### Repository-only autonomous bootstrap

The initial orchestration implementation lives under `ops/orchestration/` as
dependency-free Python tooling. This does not select the later control-plane
stack. LIT labels carry capability, model, reasoning effort, role, and safety
eligibility; explicit metadata resolves ambiguous default classifications.
Ancestor HIL/security constraints cannot be bypassed by a leaf's safe marker.
See `docs/orchestration/routing.md` for the versioned routing contract.

Memento compatibility uses durable project context rather than a Claude-only
launcher: active ticket/epic, branch/worktree, model/effort/role, goal, completed
work, verification, risks, next ticket and stop reason. Fresh supervisors must
revalidate LIT/Git authority and retain prior evidence. Codex fresh-process and
tmux launch plans are inspectable, with no automatic detached writer.

The bounded supervisor uses a repository-wide exclusive lease and validates
all linked worktrees. A trusted local worker implements one unit; the supervisor
owns verification, evidence, scoped commit, LIT close and durable handoff.
Worker commands come from explicit local configuration, never ticket prose.
This is an orchestration boundary for cooperating agents, not a replacement
for process sandboxing or the future VM policy executor. Provider access and
live system integration require separate authority. Offline integration tests
exercise real LIT/Git and fresh processes without contacting model providers.
See `docs/orchestration/continuation.md` and `docs/orchestration/handoff.md`.

## Configuration and lifecycle

Configuration composes as base, hardware/VM, context, voice, workspace,
integration, policy, and experimental profiles. Active settings report their
source and precedence.

Setup is layered:

- Graphical panel for normal configuration.
- Terminal tools for diagnostics and advanced control.
- Optional conversational setup after health checks pass.

Models and voices are detected, recommended, reviewed, downloaded only with
approval, evaluated, versioned, and rollback-capable. Restores create candidate
profiles and never replace the active profile without evaluation and approval.

Omarchy changes use user-owned configuration under `~/.config/hypr/` and
`~/.config/omarchy/`. Packaged files under `/usr/share/omarchy/` remain
read-only. Hyprland changes require `hyprctl reload` and `hyprctl configerrors`.

## Open implementation constraints

The following remain implementation choices rather than unresolved product
requirements:

- Exact programming language and process boundaries.
- Exact local event-store technology.
- Exact panel toolkit and graph renderer.
- Exact host/VM transport.
- Exact Whisper, LLM, TTS, evaluator, and cloning providers.
- Exact MCP SDK and transport.
- Exact model resource budgets after hardware inspection.

These choices must preserve the approved authority boundaries, typed contracts,
policy enforcement, event model, local-first operation, and staged vertical-slice
sequence.
