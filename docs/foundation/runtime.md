# In-memory VM dispatch

`ControlPlane(catalog, policy, executor, journal, profile=...)` snapshots validated
configuration. `dispatch(Command, canceled=False, guard=None)` returns a typed Result.
The caller is a trusted VM adapter: no transport is exposed by this foundation.
Source and profile strings in untrusted input do not authenticate a caller.
Future transports must bind context and enforce lock/mode/session freshness.
The optional guard is a trusted adapter callable, never command/model data.
Only an exact `True` authorizes the current state; other values or exceptions
block. Dispatch checks it under journal ownership after the history read and
again after intent persistence immediately before the executor. Confirmation
also accepts the guard and carries it through to dispatch. Adapters own the
final check and actuation together: they must synchronize authoritative state
transitions and platform action/speech, with a consistent lock order for guard
callbacks invoked under the journal lock. A callback alone is not atomic with
external desktop state; see the actuation ownership contract in voice/routing.md.

Policy and profile must be enabled and agree. Commands must match the bound
profile, current catalog version, enabled allowlisted capability and exact
primitive argument shape. Voice requires a voice-enabled profile. Blocked risk
never executes. Direct confirmation-required dispatch returns blocked with
`confirmation.required`. The voice slice adds a VM-owned expiring preview/token
API; see `docs/voice/routing.md`. Models cannot set a confirmed argument/boolean.

Executors are injected callables, receive an immutable Command, and return
`Outcome(status, output, error)`. No shell, network or desktop executor is
installed. Tests use deterministic fake executors for success, failed, canceled,
uncertain and exceptions. Exceptions or malformed outcomes become uncertain,
without leaking exception contents. Cancellation is pre-dispatch only; an
executor must separately handle interruption and partial effects.

Journal adapters expose `dispatch_lock`, `append(Event) -> sequence`, and
`read(after=0) -> [(sequence, Event | Interaction)]`. All dispatchers sharing a journal serialize
through that lock. Persistent adapters must enforce exclusive process ownership.
Dispatch rereads execution Events under the lock and refuses any previously seen command
ID, even if it was canceled or blocked. Replays never execute; a fresh command ID
requires an explicit caller decision after reconciliation. This is conservative
at-most-once dispatch, not a guarantee of exactly-once external side effects.
Separately, a `voice.preview` Interaction imposes a durable approval restriction
for its interaction_id/command ID, including across dispatcher objects/restart.
It never grants approval or becomes an execution receipt. Lost tokens fail
closed; other interaction observations do not suppress execution.

An intent event must persist before execution. A failed intent write blocks;
failed completion persistence after an attempt returns uncertain. Read failures
block. No automatic retry occurs. Finished events retain correlation, context,
catalog version and policy revision, result ID and safe error code; arguments,
output and exception strings are not copied into the journal. Retention and
redaction policy for context remain the later observability/privacy slice.

This synchronous, whole-history prototype favors explicit safety over scale.
Indexed replay projections and concurrent adapter execution are future work.
