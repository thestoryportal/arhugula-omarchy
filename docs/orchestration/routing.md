# LIT model routing v1

LIT owns tickets and claims. Git owns code. This bootstrap uses Python 3's
standard library; it does not decide the control-plane implementation stack.
Run tests with `python3 -m unittest discover -s tests -v` from the repository.

Run the read-only backlog report:

```sh
lit export | python3 -m ops.orchestration.routing
```

The report classifies all open leaf issues, in stable rank/ID order. It is not
a scheduler and does not authorize work, ignore dependencies, claim tickets,
launch agents, or filter away stop markers. Actual selection begins with
`lit next`; inspect a returned container with `lit children` and select its
ranked atomic unit. `lit start` is the final claim authority. Never use `--take`
to steal a fresh claim. Never assign two writers to a ticket or shared files.

Use labels on the atomic ticket:

| Label | Values |
| --- | --- |
| `capability:` | architecture, contracts, security, cross-cutting, session-lifecycle, model-routing, orchestration, debugging, high-risk-review |
| `capability:` | exploration, inventory, tests, fixtures, documentation, bounded-implementation, validation, independent-review |
| `model:` | astra, terra |
| `effort:` | high, medium |
| `role:` | implement, review, validate, explore |
| autonomy | autonomous-safe, hil-required |

The first capability row selects `gpt-6-astra` with high effort. The second
selects `gpt-5.6-terra` with medium effort. Capability is the task's primary
deliverable, not every noun mentioned in its test plan. Use explicit labels
when title-based defaults would select the wrong capability.

Precedence:

1. Any leaf or ancestor `hil-required`, `needs-design`, `privileged`,
   `destructive`, `external-credentials`, or `external-network` stops work.
2. Unknown values or multiple values for one reserved field stop with
   `routing-conflict`. An inherited `security` or `high-risk` label imposes
   the Astra floor. Other routing fields are leaf-only.
3. Explicit capability wins over inferred defaults. Explicit Astra may promote
   bounded work; explicit Terra cannot demote high capability or security.
4. Defaults use leaf capability labels, validation, session-continuity,
   workflow/circle-back, then ordered title rules: contracts, security,
   architecture, lifecycle, routing, orchestration, inventory, tests, docs,
   exploration, validation, review. Description text is never keyword-routed.
5. Unknown capability stops with `routing-ambiguous`. Effort must match the
   selected model. Roles default to implement except review, validation, and
   exploration capabilities. High-risk final review stays Astra/high.
6. Missing leaf `autonomous-safe` stops with `autonomy-unclassified`; safety
   is never inherited. The marker declares reviewed scope, not permission to
   override runtime stop conditions or the user's authority boundary.

Apply metadata through `lit label add` / `lit update --labels` only. Inspect
current labels before replacement. `lit next --labels model:terra` is an
optional explicit-metadata view, not an alternative work authority: it only
matches materialized LIT labels, does not infer capabilities, and must not
be used to bypass the top ticket's stop condition. Dry-run may show a model
while denying autonomous eligibility; these are separate decisions.

Disable routing by not invoking the tool. No daemon or live system config is
installed. Export version 2 and routing version 1 are required; schema changes
need an explicit migration and regression tests.
