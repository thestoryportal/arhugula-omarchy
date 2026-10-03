"""Observe process identities at the live procfs boundary."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessStat:
    pid: int
    state: str
    parent: int
    group: int
    start: str


def process_stats():
    for path in Path('/proc').glob('[0-9]*/stat'):
        # [LAW:effects-at-boundaries] Exit races belong to this read boundary;
        # permission and malformed-record failures still reach every consumer.
        try:
            text = path.read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        fields = text.rsplit(')', 1)[1].split()
        yield ProcessStat(
            int(path.parent.name), fields[0], int(fields[1]), int(fields[2]), fields[19]
        )
