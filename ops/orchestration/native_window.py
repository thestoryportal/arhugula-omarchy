"""Deliver literal input to one verified native window without changing focus."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import select

from .artifacts import capture, DEFAULT_ROOT


def key_events(text):
    plain=dict(zip(" `-=[]\\;',./", ['space','grave','minus','equal','bracketleft',
        'bracketright','backslash','semicolon','apostrophe','comma','period','slash']))
    shifted=dict(zip('~!@#$%^&*()_+{}|:"<>?', ['grave',*list('1234567890'),
        'minus','equal','bracketleft','bracketright','backslash','semicolon',
        'apostrophe','comma','period','slash']))
    result=[]
    for char in text:
        if char.isascii() and char.isalnum():
            result.append(('SHIFT' if char.isupper() else '',char.lower()))
        elif char in plain:result.append(('',plain[char]))
        elif char in shifted:result.append(('SHIFT',shifted[char]))
        else:raise ValueError('native input requires one literal printable ASCII line')
    return result


def input_program(address,text=None):
    if not re.fullmatch(r'0x[0-9a-f]+',address):raise ValueError('invalid window address')
    events=[('', 'Return')] if text is None else key_events(text)
    keys='{'+','.join('{'+json.dumps(mod)+','+json.dumps(key)+'}' for mod,key in events)+'}'
    # [LAW:effects-at-boundaries] Text becomes key data, never executable Lua.
    return (f'for _,k in ipairs({keys}) do hl.dispatch(hl.dsp.send_shortcut('
            f'{{mods=k[1],key=k[2],window="address:{address}"}})) end '
            f'print("BUFORD_NATIVE_INPUT {len(events)}")')


def require_us_keyboard(rows):
    main=[r for r in rows if r.get('main')]
    if len(main)!=1 or main[0].get('active_keymap')!='English (US)' or main[0].get('capsLock') is not False:
        raise ValueError('literal native delivery requires the verified US keyboard without caps lock')


def processes():
    result={}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields=path.read_text().rsplit(')',1)[1].split()
            result[int(path.parent.name)]=(fields[19],int(fields[1]))
        except FileNotFoundError:continue
    return result


@dataclass(frozen=True)
class WindowCapability:
    address: str
    stable_id: str
    terminal_pid: int
    terminal_start: str
    native_pid: int
    native_start: str

    def parse(self,clients,proc):
        # [LAW:parse-dont-validate] Return a bound capability; refuse reused handles.
        matching=[c for c in clients if c['address']==self.address]
        if (len(matching)!=1 or matching[0]['stableId']!=self.stable_id
                or matching[0]['pid']!=self.terminal_pid or not matching[0].get('mapped')
                or not matching[0].get('acceptsInput')
                or proc.get(self.terminal_pid,(None,))[0]!=self.terminal_start
                or proc.get(self.native_pid,(None,))[0]!=self.native_start):
            raise ValueError('native window/process capability changed')
        parent=self.native_pid
        seen=set()
        while parent!=self.terminal_pid and parent not in seen and parent in proc:
            seen.add(parent);parent=proc[parent][1]
        if parent!=self.terminal_pid:raise ValueError('native client left its bound terminal')
        return self


class NativeWindow:
    def __init__(self,capability,cwd,artifact_root=DEFAULT_ROOT):
        self.cap=capability;self.cwd=Path(cwd);self.root=artifact_root

    def command(self,argv):
        receipt=capture(argv,self.cwd,root=self.root,timeout=15)
        if receipt['terminal']!='exited' or receipt['exit']:
            raise OSError(f'native window command failed: {receipt["receipt"]}')
        return Path(receipt['stdout']['path']).read_text()

    def check(self):
        clients=json.loads(self.command(['hyprctl','-j','clients']))
        self.cap.parse(clients,processes())
        require_us_keyboard(json.loads(self.command(['hyprctl','-j','devices']))['keyboards'])
        return next(c for c in clients if c['address']==self.cap.address)

    def title(self):
        return self.check()['title']

    def transcripts(self):
        self.check()
        paths=set()
        for fd in Path(f'/proc/{self.cap.native_pid}/fd').iterdir():
            try:path=fd.resolve(strict=True)
            except FileNotFoundError:continue
            if not path.name.startswith('rollout-') or path.suffix!='.jsonl':continue
            with path.open() as stream:
                try:row=json.loads(next(stream))
                except (StopIteration,json.JSONDecodeError):continue
            if row.get('type')=='session_meta' and row['payload'].get('source')=='cli':paths.add(path)
        return sorted(paths)

    def type(self,text):
        program=input_program(self.cap.address,text)
        self.check()
        answer=self.command(['hyprctl','eval',program])
        if answer.strip()!='ok':
            raise OSError('native input dispatch was not acknowledged')

    def submit(self):
        # Native TUI coalesces rapid key bursts. This bounded transport settling
        # interval is not a workflow release condition or user consent.
        select.select([],[],[],.8)
        self.check()
        answer=self.command(['hyprctl','eval',input_program(self.cap.address)])
        if answer.strip()!='ok':raise OSError('native submit was not acknowledged')
