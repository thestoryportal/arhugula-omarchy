import importlib
from pathlib import Path
import unittest

PRODUCT = Path('/home/robbo/Work/arhugula-build-eval')


def rows_for(cycle_pass, head='head', severity=None, unavailable=False):
    roles = {'1': ['codex_review_wrapper', 'merge-gate-concurrency', 'merge-gate-spec-conformance', 'merge-gate-witness-adequacy'],
             '2': ['codex_review_wrapper', 'merge-gate-witness-adequacy'], '3': ['merge-gate-concurrency']}[cycle_pass]
    rows = [dict(arc_id='arc', cycle_pass=cycle_pass, head_sha=head, diff_digest='digest',
                 producer=role, record_kind='reviewer_unavailable' if unavailable else 'no_finding') for role in roles]
    if severity:
        rows[0].update(record_kind='finding', finding_id=f'{cycle_pass}-{head}', severity=severity)
        rows.append(dict(record_kind='finding_adjudication', finding_id=f'{cycle_pass}-{head}', disposition='accepted'))
    return rows


class ReviewBudgetTests(unittest.TestCase):
    def evaluate(self, rows, observed=(), impacts=()):
        from ops.orchestration.review_budget import load_gate, evaluate
        return evaluate(load_gate(PRODUCT), rows, 'arc', 'head', 'digest', list(observed), list(impacts))

    def test_fifth_p1_quarantines_and_sixth_is_not_admitted(self):
        observed = [['old', '3', f'h{n}', 'd'] for n in range(4)]
        result = self.evaluate(rows_for('3', severity='P1'), observed)
        self.assertEqual(result['completed_passes'], 5)
        self.assertEqual(result['decision'], 'quarantine')
        self.assertFalse(result['admit_review'])

    def test_two_consecutive_pass3_p1_stop_before_five(self):
        result = self.evaluate(rows_for('3', 'old', 'P1') + rows_for('3', severity='P1'))
        self.assertEqual(result['completed_passes'], 2)
        self.assertEqual(result['decision'], 'quarantine')

    def test_unavailable_and_partial_reviews_do_not_complete(self):
        result = self.evaluate(rows_for('1', unavailable=True)+rows_for('1')[:2])
        self.assertEqual(result['completed_passes'], 0)
        self.assertNotEqual(result['decision'], 'code_verified')

    def test_clear_does_not_reset_prior_bindings_and_duplicates_do_not_count(self):
        result = self.evaluate(rows_for('3'), [['arc', '3', 'head', 'digest']])
        self.assertEqual(result['completed_passes'], 1)
        self.assertEqual(result['decision'], 'code_verified')

    def test_p2_is_not_nonblocking_from_severity_alone(self):
        result = self.evaluate(rows_for('1', severity='P2'))
        self.assertEqual(result['decision'], 'fix_required')
        self.assertIn('1-head', result['blocking_findings'])

    def test_independently_adjudicated_prose_is_followup_but_cycle_still_required(self):
        rows = rows_for('1', severity='P2')
        result = self.evaluate(rows, impacts=[{'finding_id':'1-head', 'impact':'prose_no_behavior',
            'actor':'independent_absorber', 'producer':'codex_review_wrapper', 'evidence':'receipt-sha256'}])
        self.assertEqual(result['blocking_findings'], [])
        self.assertEqual(result['followups'], ['1-head'])
        self.assertNotEqual(result['decision'], 'code_verified')

    def test_self_disposition_cannot_excuse_prose(self):
        with self.assertRaisesRegex(ValueError, 'independent'):
            self.evaluate(rows_for('1', severity='P2'), impacts=[{'finding_id':'1-head',
                'impact':'prose_no_behavior', 'actor':'codex_review_wrapper', 'producer':'codex_review_wrapper', 'evidence':'x'}])

    def test_undisposed_finding_never_becomes_code_verified(self):
        result = self.evaluate(rows_for('3', severity='P3')[:-1])
        self.assertEqual(result['decision'], 'adjudication_required')

    def test_fifth_clean_mandatory_terminal_can_verify(self):
        result = self.evaluate(rows_for('3', severity='P3'),
                               [['old', '3', f'h{n}', 'd'] for n in range(4)])
        self.assertEqual(result['completed_passes'], 5)
        self.assertEqual(result['decision'], 'code_verified')
        self.assertFalse(result['admit_review'])
