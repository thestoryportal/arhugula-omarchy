"""Scheduling ceiling derived from canonical product review passes, never approval."""
import importlib.util
from pathlib import Path
import sys


def load_gate(product):
    path = Path(product).resolve() / 'tools/review_loop_gate.py'
    name = '_buford_canonical_review_gate'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def evaluate(gate, rows, arc, head, digest, observed=(), impacts=()):
    # [LAW:single-enforcer] Only the product reducer decides reviewer-set completion.
    runs = gate.pass_runs(rows, arc)
    bindings = {tuple(x) for x in observed}
    if any(len(x) != 4 or any(not isinstance(v, str) or not v for v in x) for x in bindings):
        raise ValueError('invalid prior review bindings')
    bindings.update((arc, r.cycle_pass, r.head_sha, r.diff_digest) for r in runs if r.complete)
    findings = {f['finding_id']: f for r in runs for f in r.findings}
    prose = set()
    for impact in impacts:
        finding = findings.get(impact['finding_id'])
        if (finding is None or impact['impact'] != 'prose_no_behavior'
                or impact['actor'] == finding['producer']
                or impact['producer'] != finding['producer'] or not impact['evidence']
                or finding['severity'] not in ('P2', 'P3')):
            raise ValueError('prose impact requires independent P2/P3 adjudication evidence')
        prose.add(impact['finding_id'])
    disposed = gate._last_dispositions(rows)
    undisposed = sorted(fid for fid in findings if disposed.get(fid) not in ('accepted', 'rejected', 'suppressed'))
    current = [r for r in runs if (r.head_sha, r.diff_digest) == (head, digest)]
    accepted = [f for r in current for f in r.findings if disposed.get(f['finding_id']) == 'accepted']
    blocking = sorted({f['finding_id'] for r in current for f in r.findings
                       if disposed.get(f['finding_id']) == 'accepted'
                       and (f['severity'] == 'P1' or (f['severity'] == 'P2' and r.cycle_pass != '3'
                                                     and f['finding_id'] not in prose))})
    followups = sorted({f['finding_id'] for r in runs for f in r.findings
                        if disposed.get(f['finding_id']) == 'accepted'
                        and (f['severity'] == 'P3' or f['finding_id'] in prose
                             or (f['severity'] == 'P2' and r.cycle_pass == '3'))})
    remaining = gate.next_pass(rows, arc, doc_only=False, head_sha=head, diff_digest=digest)
    earlier_stop = gate.unfixed_after_pass_3(rows, arc) >= 2
    count = len(bindings)
    # [LAW:types-are-the-program] These dispositions never stand in for merge/CI gates.
    if earlier_stop or count > 5:
        decision = 'quarantine'
    elif undisposed:
        decision = 'quarantine' if count >= 5 else 'adjudication_required'
    elif blocking:
        decision = 'quarantine' if count >= 5 else 'fix_required'
    elif remaining is None:
        decision = 'code_verified'
    else:
        decision = 'quarantine' if count >= 5 else 'review_required'
    return dict(decision=decision, completed_passes=count, observed=sorted(map(list, bindings)),
                admit_review=count < 5 and not earlier_stop and decision == 'review_required',
                next_pass=remaining, blocking_findings=blocking, followups=followups,
                undisposed_findings=undisposed, earlier_stop=earlier_stop)
