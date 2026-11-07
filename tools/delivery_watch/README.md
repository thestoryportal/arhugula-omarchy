# Delivery watcher

This directory owns the local delivery watcher and its regression tests. Keep
host configuration, native transcripts and the event database outside Git. The
watcher requires Python 3.10 or newer and the host's authenticated `lit`, `gh` and
`codex` commands. Run it with the project's interpreter:

```sh
python -B tools/delivery_watch/watcher.py --config /absolute/host-config.json --dry-run --once
python -B tools/delivery_watch/watcher.py --config /absolute/host-config.json
```

The existing database and lock retain event history and uncertain sends. Stop
the old watcher before starting a reviewed replacement against that database;
never create a second sender to retry an uncertain event. Configuration controls
the assessment pause independently of event observations. A notification proves
neither recipient uptake nor work admission.

After verifying same-window continuity, a Buford successor reconciles its own
route using its actual native transcript and the calling `CODEX_THREAD_ID`:

```sh
python -B tools/delivery_watch/adopt_root.py /absolute/session-control.json /absolute/actual-rollout.jsonl
```

The command refuses a mismatched transcript or ambiguous role. It changes only
Buford's identity, transcript and notification destination. Verify native model,
effort, permissions, release and measured headroom separately before work.

`process_observer.py` preserves the seven R6 observation/classification function ASTs
and fifteen synthetic witnesses identified by `process_observer_provenance.json`.
It has no scenario executor. Host-bound scenario, authorization and result files
remain frozen evidence; importing this module cannot replay those attempts. Its
polling limits and unresolved historical observer evidence remain unchanged.

```sh
python -B -m unittest discover -s tools/delivery_watch -p 'test_*.py'
```
