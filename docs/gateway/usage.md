# Gateway seams for adapter authors

`runtime.gateway` does not connect to a host or run a model. An adapter supplies
the effects; the gateway owns request admission, parsing and client lifecycle.
Use only an explicitly authorized endpoint and provider. A syntactically valid
URL does not grant network permission.

## Host admission

Construct `Admission(provider, catalog_version, Bearer(secret))`. The provider is
the existing `runtime.contracts.Provider`, with placement `host`. Call
`admit(authorization_header, request_bytes)` before provider invocation. It returns
`Admitted.request`, a frozen service-specific `Request`, or raises a fixed-code
`GatewayError`. Do not return exception details from the underlying provider.
`response_bytes(request, output_or_RemoteError)` validates and encodes a response.

The external adapter owns listener limits, TLS verification, provider invocation
and response writing; none are implemented here. Share one admission owner across
requests in one service lifetime. Recreating it per request defeats replay memory.

## VM client

Configure `Host(provider, Endpoint(url, peer_sha256), Bearer(secret), transport)`.
The transport's `peer_identity` must come from the authenticated TLS channel, not
from a header or model response. `begin(outgoing)` receives the expected endpoint,
credential, bounded body and remaining millisecond budget. It must bind that
identity to the actual channel used. This offline slice checks an attestation;
it cannot establish the authenticity of an invented attestation.

An optional `Local(vm_provider, begin)` supplies fallback. Its callback receives
the retargeted frozen request and remaining budget, not the host credential.
Both begin callbacks return a job, or `RemoteError` proving atomic failure without
acquiring resources. Throwing instead cannot prove cleanup and latches the client.
An idle job's `poll()` returns `None`; a completed host job returns `HttpReply`,
and a local job returns wire bytes. `cancel()` must cancel and clean up all work,
including synthesis, and return exact `True` only after cleanup is proven.

`GatewayClient(host, catalog_version, clock, local=None)` accepts a bounded
monotonic integer-millisecond clock. Call `start(request)`, then `poll()`. One
terminal `Success`, `Degraded`, or `Failed` is delivered; subsequent polling
returns `None`. Consume that result before starting another request. `cancel()`
requests cancellation, with the same terminal-delivery rule. `cleanup_proven`
reports owned cleanup, not OS-wide isolation or authentication.

Callbacks must return promptly and must not join another thread waiting on this
client's lock. The client serializes callbacks; it cannot interrupt arbitrary
Python code. Cancellation re-entering a callback is honored when the callback
returns its cleanup capability. Callers must continue polling to observe deadlines.
No background supervisor or retry loop runs on their behalf.

Requests and results are not actions or approvals. Before any eventual VM action,
the caller still needs fresh VM catalog/policy validation and the existing trusted
confirmation/executor path. A client pins one catalog revision; it does not monitor
catalog refresh or revoke other clients. C.4 provider activation and live adapter
acceptance remain separate work.

## Offline verification

Run `python -W error::ResourceWarning -m unittest discover -s tests -q` and
`python -m tests.gateway_mutations`. The latter recompiles seven mutations in
memory; it neither edits files nor changes the baseline. Build through `python -m
ops.build /tmp/<new-artifact>.pyz`, then run that archive's `health` command.
Ruff command: `ruff check . --select E4,E7,E9,F`. It was unavailable locally during
implementation; Buford owns the required CI check and final integration evidence.
