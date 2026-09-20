# In-memory VM dispatch

`ControlPlane(catalog, policy, executor, journal, profile=...)` snapshots validated
configuration. `dispatch(Command, canceled=False)` returns a typed Result.
The caller is a trusted VM adapter: no transport is exposed by this foundation.
Source and profile strings in untrusted input do not authenticate a caller.
Future transports must bind context and enforce lock/mode/session freshness.

Policy and profile must be enabled and agree. Commands must match the bound
profile, current catalog version, enabled allowlisted capability and exact
primitive argument shape. Voice requires a voice-enabled profile. Blocked risk
never executes. Confirmation-required work currently returns blocked with
`confirmation.required`: implementing a trusted confirmation adapter belongs to
the later confirmation slice, not a model-supplied argument or boolean.

Executors are injected callables, receive an immutable Command, and return
`Outcome(status, output, error)`. No shell, network or desktop executor is
installed. Tests use deterministic fake executors for success, failed, canceled,
uncertain and exceptions. Exceptions or malformed outcomes become uncertain,
without leaking exception contents. Cancellation is pre-dispatch only; an
executor must separately handle interruption and partial effects.

Journal adapters expose `dispatch_lock`, `append(Event) -> sequence`, and
`read(after=0) -> [(sequence, Event)]`. All dispatchers sharing a journal serialize
through that lock. Persistent adapters must enforce exclusive process ownership.
Dispatch rereads history under the lock and refuses any previously seen command
ID, even if it was canceled or blocked. Replays never execute; a fresh command ID
requires an explicit caller decision after reconciliation. This is conservative
at-most-once dispatch, not a guarantee of exactly-once external side effects.

An intent event must persist before execution. A failed intent write blocks;
failed completion persistence after an attempt returns uncertain. Read failures
block. No automatic retry occurs. Finished events retain correlation, context,
catalog version and policy revision, result ID and safe error code; arguments,
output and exception strings are not copied into the journal. Retention and
redaction policy for context remain the later observability/privacy slice.

This synchronous, whole-history prototype favors explicit safety over scale.
Indexed replay projections and concurrent adapter execution are future work.
