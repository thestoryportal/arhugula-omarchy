"""Native startup budget, separate from assignment headroom and lifetime usage."""
from .session_context import inspect_transcript
import argparse
import json
import sys
from pathlib import Path


class StartupBudgetRejected(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['reason'])


UNAVAILABLE = 'startup native context metric unavailable or invalid'
EXCEEDED = 'startup-context-budget exceeded'


def _decide(session, consumed, window, known):
    """The one 15-percent rule, applied to a fresh measurement or a recorded one."""
    report = dict(session_id=session, consumed_tokens=consumed,
                  context_window_tokens=window,
                  limit_tokens=window * 15 // 100 if type(window) is int and window > 0 else None,
                  limit_percent=15, measurement_basis='latest-native-request-input-plus-response-output')
    # [LAW:parse-dont-validate] Unknown native metrics cannot prove a percentage.
    if (not known or type(window) is not int or window <= 0
            or type(consumed) is not int or consumed < 0):
        raise StartupBudgetRejected({**report, 'reason': UNAVAILABLE})
    if consumed > report['limit_tokens']:
        raise StartupBudgetRejected({**report, 'reason': EXCEEDED})
    return report


def budget(transcript, session):
    observed = inspect_transcript('codex', transcript)
    known = (observed['session_id'] == session and not observed['identity_conflict']
             and not observed['metric_error'] and not observed['partial_tail'])
    return _decide(session, observed['estimated_consumed_context_tokens'],
                   observed['reported_context_window_tokens'], known)


def first_turn(summary, session):
    """The rule applied where ``session``'s inspected transcript completed its first turn."""
    first = summary['startup']
    known = (summary['session_id'] == session and not summary['identity_conflict']
             and first['metric_error'] is None)
    return _decide(session, first['estimated_consumed_context_tokens'],
                   first['reported_context_window_tokens'], known)


def packet(controller, manifest):
    from .auto_reset import wait_bootstrap
    from .artifacts import capture, file_binding
    accepted = wait_bootstrap(controller, manifest)
    quickstart, _ = controller.loop.lit.command('quickstart')
    root = Path(controller.config['cwd'])
    guidance = [f'\nSOURCE: {root / name}\n{(root / name).read_text()}'
                for name in ('docs/orchestration/context-policy.md', 'docs/orchestration/roles/buford.md', 'docs/governance/laws/chat/SKILL.md')]
    inbox = capture([sys.executable, '/home/robbo/Work/arhugula-trial/evaluation/production-readiness-arch/dashboard/inbox.py', 'pending'], root)
    if inbox['exit'] != 0 or inbox['terminal'] != 'exited':
        raise ValueError('startup inbox check failed: ' + inbox['receipt'])
    pending = json.loads(Path(inbox['stdout']['path']).read_text())
    data, _ = controller.loop.lit.read(controller.loop.status()['goal_ticket'])
    issue = next(i for i in data['issues'] if i['id'] == controller.loop.status()['goal_ticket'])
    summary = json.dumps(dict(session_id=accepted['session_id'], epoch=accepted['epoch'],
                         ticket=issue['id'], status=issue['status'], title=issue['title'],
                         production_paused=controller.loop._control()['repair_paused'],
                         inbox_pending=[item['id'] for item in pending], inbox=file_binding(inbox['receipt']),
                         inbox_messages=inbox['stdout'], workflow_pointer=controller.config['continuation'],
                         deadline=controller.config['deadline'], startup_limit_percent=15))
    # [LAW:effects-at-boundaries] Failed preflight must not spend context on a partial packet.
    print('\n'.join([quickstart, *guidance, summary]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['packet', 'finish'])
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    from .auto_reset import configured
    controller = configured(args.config)
    if args.command == 'finish':
        print(json.dumps(controller.loop.finish_startup()))
        return
    if args.manifest is None:
        parser.error('packet requires --manifest')
    packet(controller, args.manifest)


if __name__ == '__main__':
    main()
