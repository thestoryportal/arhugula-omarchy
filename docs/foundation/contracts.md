# Version 1 wire contracts

`runtime.contracts.decode`, `encode`, and `loads` are the mandatory trust
boundary. The eight frozen record types are Command, Result, Event, Capability,
Policy, Profile, Provider, and Error. Golden examples live in
`tests/fixtures/contracts-v1.json`; closed structural schemas live in
`schemas/contracts-v1.json`. No network schema resolution is performed.

Every record requires `kind` and integer `version: 1`. Unknown versions, fields,
enum values, duplicate JSON keys, non-finite numbers and malformed identifiers
are rejected. Booleans are not integers. A future incompatible shape requires a
new version and explicit decoder; there is no best-effort version fallback.
Dataclass constructors alone are not validation. Decode/encode before trusting
records, including locally constructed ones. Decode recursively snapshots maps
and arrays; encode produces a detached JSON object.

Commands carry stable command and correlation IDs, a capability ID and catalog
version, typed arguments, request timestamp and execution context. They carry
no authorization or confirmation flag. Context records session/profile,
optional lane/agent/provider/model, source, provenance and sensitivity. These
are correlation claims, not proof of identity or permission; adapters must bind
them to authenticated VM state before dispatch. No model or host provider may
mint VM authorization.

Results have success/blocked/failed/canceled/uncertain states. The codec adds
semantic invariants to the structural schema: blocked/failed/uncertain require
an Error, success cannot have one. Started events must be pending; finished
events must be terminal. Event timestamps are epoch milliseconds; durations are
nonnegative milliseconds. Events include command/correlation IDs, capability
catalog version, policy revision and full context. Journal sequence numbers
are storage metadata rather than part of the wire event.

Capabilities declare exact required primitive argument names/types, enablement,
catalog version, provenance and safe/confirm/blocked risk. Policies default to
denial through explicit allowlists and confirmation requirements. Profiles bind
a policy and gate voice. Providers are VM or host inference endpoints with
health/version metadata; their declarations grant no execution rights.

The bundled validator intentionally implements only the schema keywords used by
these documents, not arbitrary JSON Schema. Domain/policy checks and cross-record
consistency belong to the VM runtime. Structural validity alone never authorizes
execution. The foundation opens no transport and enables no live executor.
