# Omarchy Agent Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved Omarchy-native local agent workspace and voice-control system as staged, testable vertical slices over a shared typed control plane.

**Architecture:** The Linux VM owns the control plane, policy, catalog, execution, LIT/Git integration, agents, events, and Omarchy workspace. The Mac host provides accelerated local LLM, TTS, cloning, and evaluator services through private authenticated endpoints. Voice, panel, keyboard, terminal, and MCP clients all use the same typed control-plane contracts.

**Tech Stack:** To be selected by the first foundation unit. The implementation must support local Linux services, private VM-to-host transport, PipeWire, Hyprland/Omarchy, structured local model APIs, MCP, Git, LIT, and a persistent local event/memory store. The stack decision is a tracked deliverable rather than an implicit assumption.

**Spec:** `docs/superpowers/specs/2026-09-19-omarchy-agent-workspace-design.md`

## Global Constraints

- The Linux VM is authoritative for Omarchy, Hyprland, policy, catalogs, agents, LIT/Git state, and execution.
- The Mac host receives text and bounded structured context by default and never receives unrestricted VM command authority.
- Models propose intents or typed actions; only the VM-side validator and executor may authorize and execute actions.
- Runtime networking is deny-by-default; approved update checks use a separate controlled path.
- No unrestricted shell generation is permitted.
- Lower layers cannot bypass policy or reach upward to become an authority.
- Full conversation history remains local and active context is retrieved economically through frontmatter, summaries, and indexes.
- Omarchy changes use user-owned configuration under `~/.config/hypr/` and `~/.config/omarchy/`; `/usr/share/omarchy/` is read-only.
- Hyprland changes require `hyprctl reload` followed by `hyprctl configerrors`.
- Every implementation unit has one observable outcome, one primary test target, explicit failure behavior, and a rollback or disable path where applicable.
- Every epic ends with a circle-back unit that reconciles discoveries into code, tests, documentation, and follow-up work.
- Intra-epic order is represented by rank and lanes; blocking dependencies are reserved for genuine cross-epic prerequisites.

## Repository layout

The initial scaffold will establish these responsibility boundaries:

- `docs/` — durable design, operational guides, contracts, and evaluation criteria.
- `schemas/` — versioned wire, event, action, catalog, policy, and profile schemas.
- `runtime/` — control-plane orchestration, lifecycle, policy, and event coordination.
- `services/` — VM services and Mac-host model gateway services.
- `adapters/` — Omarchy, Hyprland, PipeWire, LIT, Git, MCP, terminal, tmux, and provider adapters.
- `ui/` — compact panel, observability workspace, topology views, review flows, and setup.
- `memory/` — archive, frontmatter, summaries, retrieval, pruning, and datasets.
- `tests/` — unit, contract, replay, integration, isolation, and live-hardware test harnesses.
- `ops/` — service definitions, sandbox/network policy, model manifests, migrations, and backups.

The first foundation unit may refine these paths after the language and process-boundary decision, but it must preserve the responsibility split and document any change before dependent work starts.

## Workstream order

### Workstream 0: foundation decision and repository scaffold

- Freeze language, process boundaries, IPC/HTTP transport, schema format, test runner, packaging, and local persistence choices.
- Create the minimal project layout and developer bootstrap.
- Establish the contract test harness before feature implementation.

### Workstream 1: control-plane spine

- Define command, result, event, capability, policy, profile, provider, and error contracts.
- Implement in-memory fakes and deterministic validators.
- Prove correlation, versioning, and no-silent-failure behavior.

### Workstream 2: first useful voice slice

- Preserve existing Home/End dictation.
- Add one-shot `KP_EQUAL` adaptive command capture.
- Execute one safe Omarchy command through the VM validator.
- Show result state and persist the event.

### Workstream 3: catalog, models, and observability

- Discover Omarchy and Hyprland capabilities.
- Add semantic routing and clarification.
- Add the Mac-host model gateway and local fallback.
- Build the persistent observability workspace.

### Workstream 4: conversational voice and audio

- Add conversation mode, TTS, voice profiles, cloning, interruption, and audio policies.

### Workstream 5: integrations and workspace orchestration

- Add application adapters, MCP, agents, lanes, Hyprland placement, LIT/Git views, and topology diagrams.

### Workstream 6: memory, learning, and hardening

- Add context-optimized memory, correction loops, evaluation promotion, recovery, setup, backups, and release hardening.

## Epic implementation units

The following units are also created in LIT as ordered child issues. Each unit is intentionally sized for one focused implementation session plus review and handoff.

### Epic A: Control-plane foundation

- **A.1 Stack and process-boundary decision** — record the technology choice and repository layout; test by bootstrapping a clean checkout and running the contract test command.
- **A.2 Contract schemas and version rules** — define typed commands, results, events, capabilities, policies, profiles, providers, errors, and correlation identifiers; test round-trip validation and unknown-version rejection.
- **A.3 In-memory control-plane core** — implement dispatch, correlation, explicit result states, and deterministic fake executors; test successful, blocked, failed, canceled, and uncertain paths without IO.
- **A.4 Runtime event journal seam** — implement append/read/replay interfaces with an in-memory fake and local persistence adapter; test ordering, idempotency, correlation, and rebuildable reads.
- **A.5 Foundation circle-back** — reconcile contracts against the first implementation, record decisions, remove duplicate authority, update the spec, and release the foundation.

### Epic B: Voice control core

- **B.1 Dictation adapter contract** — preserve Home/End semantics and define transcription/output interfaces; test direct typing and clipboard fallback with mocked focus/output.
- **B.2 Adaptive command capture** — implement `KP_EQUAL`, silence detection, maximum duration, cancellation, and no-leak output behavior; test recorded audio and synthetic capture events.
- **B.3 Safe Omarchy executor slice** — route one catalog action such as opening the Omarchy menu through validation and execution; test with a fake executor and one approved live smoke test.
- **B.4 Semantic routing and clarification** — add normalization, candidate ranking, confidence, second-turn clarification, and repair; test aliases, ambiguity, malformed output, and fallback matching.
- **B.5 Confirmation and correction** — support panel, keyboard, and voice confirmation plus correction labels; test harmless, risky, blocked, muted, and stale-catalog actions.
- **B.6 Voice-core circle-back** — reconcile capture, routing, policy, and output seams; run replay tests, update voice requirements, and release the first usable command system.

### Epic C: Capability catalog and model gateway

- **C.1 Omarchy and Hyprland inventory adapters** — discover commands, menus, bindings, custom bindings, and state; test fixture inventories and configuration diffs.
- **C.2 Catalog versioning and refresh** — implement change detection, provenance, first-use review, and stale-version rejection; test custom binding addition and removal.
- **C.3 Host gateway protocol** — define private authenticated VM-to-host request/response behavior for LLM, evaluator, and TTS services; test timeouts, invalid responses, and host unavailability.
- **C.4 Local model provider registry** — implement provider manifests, placement, health, fallback, versions, resource estimates, and update policy; test candidate activation and rollback.
- **C.5 Model gateway circle-back** — compare actual provider behavior against the architecture, freeze runtime contracts, and release the local model service boundary.

### Epic D: Observability and evaluation

- **D.1 Event projections** — build current interaction, service health, lane, and action projections from the journal; test rebuild from replayed events.
- **D.2 Compact status surface** — show active mode, mute, service health, degraded capabilities, and pending state; test startup, failure, and mute transitions.
- **D.3 Detailed observability workspace** — show transcripts, candidates, intent, risk, prompts, outputs, timing, validation, execution, and verification with sensitivity controls; test filters and detail expansion.
- **D.4 Candidate comparison and review** — compare active and candidate outputs, support corrections, labels, approval, and rollback; test disagreement, approval, rejection, and stale candidate paths.
- **D.5 Replay and evaluator harness** — support synthetic, recorded, live, pinned, deterministic, and independent-evaluator runs; test promotion gates and regression detection.
- **D.6 Observability circle-back** — reconcile event names, projections, metrics, and review flows; update the spec and release the evaluation workspace.

### Epic E: Conversational voice, TTS, and cloning

- **E.1 Conversation session lifecycle** — implement entry, explicit spoken exit, configured key exit, mode display, and profile policy; test session continuity and cancellation.
- **E.2 TTS provider interface and routing** — support host-heavy and VM-light providers, audio return, interruption, ducking, fallback, and event-specific voice policy; test unavailable and muted output.
- **E.3 Voice profile library** — implement built-in voices, settings, pronunciation dictionaries, per-event overrides, provenance, and local retention; test profile activation and rollback.
- **E.4 Guided cloning workflow** — support upload, scripted recording, quality scoring, targeted sample requests, versioning, and source retention; test incomplete and low-quality samples.
- **E.5 Conversational memory integration** — connect session context, persistent archive, retrieval, memory conflict clarification, and provenance display; test stale and conflicting memories.
- **E.6 Voice circle-back** — evaluate provider choices, quality, resource use, and lifecycle behavior; release the selected voice stack and update model manifests.

### Epic F: Omarchy and application integrations

- **F.1 Policy-gated MCP broker** — implement resource discovery, typed tools, generic catalog action, server manifest, approval, and sandbox boundary; test unauthorized and network-denied tools.
- **F.2 Application capability interface** — define adapters for native API/CLI, documented shortcuts, and opt-in screen/OCR fallback; test fake applications and verification.
- **F.3 Initial supported applications** — implement selected browser, terminal, file manager, media, and system integrations; test safe actions, undo, failed verification, and risk tiers.
- **F.4 Screen context and redaction** — implement on-demand capture, exclusions, redaction, explicit permissions, and no-retention defaults; test sensitive-window and uncertain-classification paths.
- **F.5 Integration circle-back** — review provider trust, action granularity, verification, and rollback; release the first supported integration set.

### Epic G: Agent workspace and workflow orchestration

- **G.1 Agent session registry** — define agent identity, model assignment, lifecycle, health, handoff, and recovery state; test start, pause, resume, failure, and handoff.
- **G.2 Lane and work assignment** — connect agents to LIT units, claims, lanes, priorities, and dependencies; test claim contention and stale work.
- **G.3 Git and LIT projections** — show branch, worktree, commits, tests, review, issue state, and handoff; test authoritative-source disagreement and sync failure.
- **G.4 Hyprland workspace adapter** — place and recover terminal, tmux, panel, and agent windows without equating window state to agent state; test conflict-aware bindings and window closure.
- **G.5 Topology and lane observability** — render agent, model, issue, workspace, dependency, and blocked-path diagrams; test incremental updates and historical replay.
- **G.6 Workspace circle-back** — reconcile agent lifecycle, LIT/Git truth, Hyprland behavior, and topology projections; release the Omarchy-native workspace foundation.

### Epic H: Memory, learning, setup, recovery, and release hardening

- **H.1 Persistent archive and frontmatter** — store full local conversations with compact metadata and source references; test append, retrieval, deletion, and rebuild.
- **H.2 Structured memory and pruning** — extract facts, decisions, preferences, and recurring patterns with review states; test confidence, conflict, stale pruning, and full purge.
- **H.3 Learning datasets and promotion** — support command, Whisper, and TTS datasets, pinned replay bundles, independent evaluation, candidate profiles, approval, and rollback.
- **H.4 Setup and profile composition** — implement graphical, terminal, and optional conversational setup with base/profile/feature composition, estimates, conflict checks, and previews.
- **H.5 Recovery, backup, and restore** — implement service retry, fallback, candidate restore, selective backup, retention, and deletion; test partial failures and risky pending actions.
- **H.6 Security and network hardening** — enforce deny-by-default runtime networking, provider allowlists, credentials, telemetry disabling, and audit evidence; test violations and recovery.
- **H.7 Release hardening circle-back** — run full cross-slice regression, reconcile documentation and backlog, validate clean installation, and cut the first integrated release.

## Cross-cutting implementation rules

- Every unit starts with a failing or characterization test before implementation.
- IO is behind a functional seam and mocked or faked in unit tests.
- Real IO receives one explicit harness or integration unit per epic.
- Every new event, action, provider, and profile field has versioning and migration behavior.
- Every issue close records a decision, learning, handoff, or explicit statement that none was discovered.
- Discovered work is captured with `lit followup --on` while context is fresh.
- Every epic circle-back reconciles implementation truth with the durable spec.
- Agents read the epic body and the unit description; they do not need the entire project history to start.
- No issue duplicates the whole design document; tickets point to stable sections and state only their work truth.

## Promotion gates

The project cannot promote a slice when any of these are missing:

- Contract tests and unit tests pass.
- Failure and degraded paths are exercised.
- Observability events exist for the user-visible behavior.
- Policy and authority boundaries are tested.
- The relevant replay or integration harness passes.
- Manual acceptance is recorded.
- Rollback or disable behavior is available.
- LIT comments capture decisions and follow-up work.

## Execution handoff

Implementation begins only after the backlog has been reviewed. The first
execution ticket is A.1, followed by the spine units and the first end-to-end
voice slice. Agents should use LIT’s `lit next`, `lit show`, `lit start`,
`lit comment add`, `lit done`, and `lit followup --on` workflow from the project
root.
