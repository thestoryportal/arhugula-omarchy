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


def budget(transcript, session):
    observed = inspect_transcript('codex', transcript)
    window = observed['reported_context_window_tokens']
    consumed = observed['estimated_consumed_context_tokens']
    report = dict(session_id=session, consumed_tokens=consumed,
                  context_window_tokens=window,
                  limit_tokens=window * 15 // 100 if type(window) is int and window > 0 else None,
                  limit_percent=15, measurement_basis='latest-native-request-input-plus-response-output')
    # [LAW:parse-dont-validate] Unknown native metrics cannot prove a percentage.
    if (observed['session_id'] != session or observed['identity_conflict']
            or observed['metric_error'] or observed['partial_tail']
            or type(window) is not int or window <= 0
            or type(consumed) is not int or consumed < 0):
        raise StartupBudgetRejected({**report, 'reason': 'startup native context metric unavailable or invalid'})
    if consumed > report['limit_tokens']:
        raise StartupBudgetRejected({**report, 'reason': 'startup-context-budget exceeded'})
    return report


def packet(controller, manifest):
    from .auto_reset import wait_bootstrap
    from .artifacts import capture, file_binding
    accepted = wait_bootstrap(controller, manifest)
    quickstart, _ = controller.loop.lit.command('quickstart')
    print(quickstart)
    root = Path(controller.config['cwd'])
    # [LAW:effects-at-boundaries] One packet supplies full current startup guidance.
    for name in ('docs/orchestration/context-policy.md', 'docs/orchestration/roles/buford.md', 'docs/governance/laws/chat/SKILL.md'):
        print(f'\nSOURCE: {root / name}\n{(root / name).read_text()}')
    inbox = capture([sys.executable, '/home/robbo/Work/arhugula-trial/evaluation/production-readiness-arch/dashboard/inbox.py', 'pending'], root)
    if inbox['exit'] != 0 or inbox['terminal'] != 'exited':
        raise ValueError('startup inbox check failed: ' + inbox['receipt'])
    pending = json.loads(Path(inbox['stdout']['path']).read_text())
    data, _ = controller.loop.lit.read(controller.loop.status()['goal_ticket'])
    issue = next(i for i in data['issues'] if i['id'] == controller.loop.status()['goal_ticket'])
    print(json.dumps(dict(session_id=accepted['session_id'], epoch=accepted['epoch'],
                         ticket=issue['id'], status=issue['status'], title=issue['title'],
                         production_paused=controller.loop._control()['repair_paused'],
                         inbox_pending=[item['id'] for item in pending], inbox=file_binding(inbox['receipt']),
                         inbox_messages=inbox['stdout'], workflow_pointer=controller.config['continuation'],
                         deadline=controller.config['deadline'], startup_limit_percent=15)))


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
