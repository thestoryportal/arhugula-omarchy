"""Deliver literal input to one verified native window without changing focus."""
from dataclasses import dataclass, asdict
import ast
import json
from pathlib import Path
import re
import select
import sqlite3
import uuid
from datetime import datetime,timezone

from .artifacts import capture, DEFAULT_ROOT, file_binding


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
    events=[('', 'Tab')] if text is None else key_events(text)
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


def launch_cwd(argv,process_cwd):
    directories=[]
    for index,arg in enumerate(argv):
        if arg in ('-C','--cd'):
            if index+1==len(argv):raise ValueError('native launch directory is missing')
            directories.append(argv[index+1])
        elif arg.startswith('--cd='):directories.append(arg[5:])
    if len(directories)>1:raise ValueError('ambiguous native launch directory')
    return (Path(process_cwd)/(directories[0] if directories else '.')).resolve()


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


@dataclass(frozen=True)
class RetainedContext:
    """Explicit proof for one expired maintenance boundary, never prompt delivery."""
    proof: dict

    @classmethod
    def parse(cls,grant,cap,cwd,frontier,previous):
        try:
            return cls._parse(grant,cap,cwd,frontier,previous)
        except (KeyError,TypeError,AttributeError,IndexError,SyntaxError) as error:
            raise ValueError('malformed retained native context evidence') from error

    @classmethod
    def _parse(cls,grant,cap,cwd,frontier,previous):
        # [LAW:parse-dont-validate] Bind the retained observation once; current
        # ownership is a separate capability, not a substitute creation event.
        evidence={}
        for key in ('receipt','config','frontier'):
            bound=grant[key]
            if file_binding(bound['path'])!=bound:
                raise ValueError('retained native context evidence changed')
            evidence[key]=json.loads(Path(bound['path']).read_text())
        receipt=evidence['receipt']
        if (receipt['exit']!=0 or receipt['terminal']!='exited' or receipt['cwd']!=str(cwd)
                or evidence['config']['window']!=asdict(cap) or evidence['frontier']!=frontier
                or file_binding(receipt['stdout']['path'])!=receipt['stdout']):
            raise ValueError('retained native context witness binding mismatch')
        proof=json.loads(Path(receipt['stdout']['path']).read_text())
        identifier=uuid.UUID(proof['session_id']);created=(identifier.int>>80)/1000
        if (identifier.version!=7 or proof['session_id']==previous or proof['user_input'] is not True
                or created<datetime.fromisoformat(frontier['prepared_at']).timestamp()
                or proof['created_at']!=datetime.fromtimestamp(created,timezone.utc).isoformat()
                or not re.fullmatch(f'pid:{cap.native_pid}:[a-zA-Z0-9-]+',proof['process_uuid'])
                or type(proof['creation_log_id']) is not int or proof['creation_log_id']<=0
                or not proof['transcript']):
            raise ValueError('retained native creation proof mismatch')
        # This bounded recovery accepts the already witnessed read-only program.
        # Parse its complete AST without executing artifact-supplied Python.
        argv=receipt['argv']
        if len(argv)!=3 or argv[1]!='-c':
            raise ValueError('retained native witness command mismatch')
        program=ast.parse(argv[2])
        try:
            source=ast.literal_eval(program.body[2].value.args[1].args[0].func.value.args[0])
            config=ast.literal_eval(program.body[4].value.args[0].func.value.args[0])
            boundary=ast.literal_eval(program.body[5].value.args[0].func.value.args[0])
        except (IndexError,AttributeError,ValueError) as error:
            raise ValueError('retained native witness inputs missing') from error
        if ((cwd/config).resolve()!=Path(grant['config']['path']).resolve()
                or (cwd/boundary).resolve()!=Path(grant['frontier']['path']).resolve()):
            raise ValueError('retained native witness input paths mismatch')
        expected=("import sys,json\nfrom pathlib import Path\n"
            f"sys.path.insert(0,str(Path({source!r}).resolve()))\n"
            "from ops.orchestration.native_window import NativeWindow,WindowCapability\n"
            f"config=json.loads(Path({config!r}).read_text())\n"
            f"frontier=json.loads(Path({boundary!r}).read_text())\n"
            "w=NativeWindow(WindowCapability(**config['window']),Path.cwd())\n"
            f"proof=w.context(frontier,{previous!r})\nprint(json.dumps(proof))\n"
            f"if proof is None or proof['session_id']!={proof['session_id']!r} or not proof['user_input']:raise SystemExit('expected current user intervention proof missing')\n")
        if ast.dump(program)!=ast.dump(ast.parse(expected)):
            raise ValueError('retained native witness program mismatch')
        return cls(proof)


class NativeWindow:
    def __init__(self,capability,cwd,artifact_root=DEFAULT_ROOT,*,codex_home=None):
        self.cap=capability;self.cwd=Path(cwd);self.root=artifact_root
        self.home=Path(codex_home).absolute() if codex_home is not None else Path.home()/'.codex'
        self.proc=Path('/proc')/str(capability.native_pid)

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
        paths=[]
        for path in self.rollouts():
            with path.open() as stream:
                try:row=json.loads(next(stream))
                except StopIteration:continue
            if row.get('type')=='session_meta' and row['payload'].get('source')=='cli':paths.append(path)
        return paths

    def rollouts(self):
        self.check();paths=set()
        for fd in (self.proc/'fd').iterdir():
            try:path=fd.resolve(strict=True)
            except FileNotFoundError:continue
            if not path.name.startswith('rollout-') or path.suffix!='.jsonl':continue
            paths.add(path)
        return sorted(paths)

    def owned_threads(self,frontier):
        self.check()
        argv=(self.proc/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        if (frontier['native_lane']!={'cwd':str(self.cwd),'source':'cli','originator':'codex-tui'}
                or launch_cwd(argv,(self.proc/'cwd').resolve(strict=True))!=self.cwd.resolve()):
            raise ValueError('native CLI lane provenance changed')
        owned=set()
        for fd in (self.proc/'fd').iterdir():
            try:path=fd.resolve(strict=True)
            except FileNotFoundError:continue
            if path.parent!=self.home/'thread-writer-locks' or path.suffix!='.lock':continue
            info=(self.proc/'fdinfo'/fd.name).read_text()
            if not re.search(r'lock:\s+\d+: FLOCK\s+ADVISORY\s+WRITE '+str(self.cap.native_pid)+r' ',info):
                raise ValueError('native thread writer ownership is unproven')
            owned.add(str(uuid.UUID(path.stem)))
        return owned

    def recovery_context(self,frontier,previous,grant):
        if grant is None:
            return self.context(frontier,previous)
        retained=RetainedContext.parse(grant,self.cap,self.cwd,frontier,previous)
        proof=retained.proof
        current=self.context(frontier,previous)
        if current is not None and any(current[key]!=proof[key] for key in
                ('session_id','created_at','process_uuid','creation_log_id','transcript')):
            raise ValueError('current native creation contradicts retained witness')
        owned=self.owned_threads(frontier)
        if proof['session_id'] not in owned:
            raise ValueError('retained native writer lock is no longer held')
        with sqlite3.connect((self.home/'logs_2.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            processes={row[0] for row in db.execute(
                "SELECT DISTINCT process_uuid FROM logs WHERE thread_id=? AND process_uuid LIKE ?",
                (proof['session_id'],f'pid:{self.cap.native_pid}:%'))}
            if processes!={proof['process_uuid']}:
                raise ValueError('current native process provenance differs from retained witness')
        paths=[str(p) for p in self.rollouts() if p.name.endswith('-'+proof['session_id']+'.jsonl')]
        if paths!=[proof['transcript']]:
            raise ValueError('retained native rollout is no longer exclusively owned')
        with Path(proof['transcript']).open() as stream:
            try:row=json.loads(next(stream))
            except StopIteration as error:
                raise ValueError('retained native rollout is empty') from error
        if (row.get('type')!='session_meta' or row['payload'].get('id')!=proof['session_id']
                or {k:row['payload'].get(k) for k in ('cwd','source','originator')}!=frontier['native_lane']):
            raise ValueError('retained native rollout provenance changed')
        self.check()
        return {**proof,'retained_context':grant}

    def context(self,frontier,previous):
        """Prove native TUI thread creation even before lazy rollout persistence."""
        owned=self.owned_threads(frontier)
        prepared=datetime.fromisoformat(frontier['prepared_at']).timestamp()
        # [LAW:parse-dont-validate] A held native writer lock plus the native TUI
        # thread/start event proves creation; title alone never authorizes input.
        with sqlite3.connect((self.home/'logs_2.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            rows=db.execute("SELECT id,ts,ts_nanos,thread_id,process_uuid,feedback_log_body FROM logs "
                "WHERE target='codex_core::shell_snapshot' AND ts>=? AND process_uuid LIKE ?",
                (int(prepared),f'pid:{self.cap.native_pid}:%')).fetchall()
            candidates=[]
            for log_id,ts,nanos,session,process,body in rows:
                if session not in owned or session==previous:continue
                if not all(token in body for token in ('rpc.method="thread/start"',
                        'rpc.transport="in-process"','app_server.client_name="codex-tui"',
                        'app_server.thread_start.create_thread',f'shell_snapshot{{thread_id={session}}}',
                        'Shell snapshot successfully created:')):continue
                identifier=uuid.UUID(session)
                created=(identifier.int>>80)/1000
                if identifier.version!=7 or created<prepared or ts+nanos/1e9<created:
                    raise ValueError('old or malformed native context creation evidence')
                candidates.append(dict(session_id=session,created_at=datetime.fromtimestamp(created,timezone.utc).isoformat(),
                    process_uuid=process,creation_log_id=log_id,transcript=None,user_input=False))
            if len(candidates)>1:raise ValueError('ambiguous fresh native CLI context')
            if not candidates:return None
            proof=candidates[0]
            proof['user_input']=bool(db.execute("SELECT 1 FROM logs WHERE process_uuid=? AND thread_id=? "
                "AND id>? AND (feedback_log_body LIKE '%op: TurnInput %' OR feedback_log_body LIKE '%codex.op=\"turn_input\"%') LIMIT 1",
                (proof['process_uuid'],proof['session_id'],proof['creation_log_id'])).fetchone())
        # A real owned empty file is optional evidence, never a prerequisite.
        paths=[p for p in self.rollouts() if p.name.endswith('-'+proof['session_id']+'.jsonl')]
        if len(paths)>1:raise ValueError('ambiguous fresh native rollout')
        if paths:
            with paths[0].open() as stream:
                try:row=json.loads(next(stream))
                except StopIteration:row=None
            if row is not None and (row.get('type')!='session_meta' or row['payload'].get('id')!=proof['session_id']
                    or {k:row['payload'].get(k) for k in ('cwd','source','originator')}!=frontier['native_lane']):
                raise ValueError('malformed or foreign native rollout')
            proof['transcript']=str(paths[0])
        self.check()
        return proof

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
