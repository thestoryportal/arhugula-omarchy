"""Dry-run voice-session preflight. No live bindings are installed or inferred."""
import argparse
import json


def preflight_live():
    """Report blockers, never turn a CLI flag into live authorization.

    Concrete operator startup binding, characterized provider and attended source
    selection remain later integration gates. No approval JSON is accepted here.
    """
    return {'ready': False, 'code': 'live.unbound',
            'required': ['trusted-operator-binding', 'characterized-file-transcriber',
                         'approved-source-and-owned-capture', 'fresh-state-and-actuation-guards']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='check live prerequisites; does not grant permission')
    args = parser.parse_args()
    report = {'version': 1, 'mode': 'preflight' if args.live else 'dry-run',
              'external_execution': False, 'listening': False,
              'live': preflight_live()}
    print(json.dumps(report, sort_keys=True))
    return 2 if args.live else 0


if __name__ == '__main__':
    raise SystemExit(main())
