"""Autonomous same-window native reset; never replay an uncertain input effect."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import sys
import time
import uuid

from .artifacts import DEFAULT_ROOT,file_binding
from .continuation import Lease
from .goal_lineage import GoalLineage
from .loop import Loop,NativeLit,identity
from .native_window import NativeWindow,WindowCapability
from .records import atomic_json,private_directory


class AutoReset:
    def __init__(self,loop,path,config,window,clock=time.monotonic):
        self.loop=loop;self.path=Path(path);self.config=config;self.window=window;self.clock=clock

    def status(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {'phase':'monitoring'}

    def save(self,state):atomic_json(self.path,state)

    def bindings(self):
        for bound in [self.config['authority'],self.config['continuation'],*self.config['source_acceptance']]:
            if file_binding(bound['path'])!=bound:raise ValueError('autoreset authority/source binding changed')

    def prepare(self):
        state=self.loop.status();routing=next(s for s in self.loop._control()['sessions'] if s['role']=='buford')
        release=json.loads(Path(self.config['release']).read_text())
        if ((release['session_id'],release['epoch'])!=(state['session_id'],state['epoch'])
                or release.get('completed')!=sorted(state['completed'])):
            waiting={'phase':'waiting_release'};self.save(waiting);return waiting
        goal=json.loads(Path(release['goal_receipt']).read_text())['goal']
        if goal['threadId']!=state['session_id']:raise ValueError('actual current goal receipt required')
        GoalLineage(self.config['goal_ledger']).record(release['goal_receipt'],self.config['deadline'])
        directory=Path(self.config['packages'])/str(uuid.uuid4())
        reset=self.loop.prepare_clear(directory,release['owned_processes'],automatic={
            'config':self.config.get('config_path','fixture-config.json'),
            'continuation':self.config['continuation']['path'],'goal_receipt':release['goal_receipt'],
            'goal_ledger':self.config['goal_ledger'],'deadline':self.config['deadline']})
        frontier=json.loads((directory/'frontier.json').read_text())
        prepared={'phase':'waiting_idle','old_transcript':routing['transcript'],
            'old_user_hash':identity(routing['transcript'])['last_user_hash'],
            'routing':file_binding(self.loop.control),'reset':reset,'nonce':frontier['nonce'],
            'title':'Buford-auto-'+frontier['nonce'],'started':None,
            'goal_receipt':file_binding(release['goal_receipt'])}
        self.save(prepared);return prepared

    def unchanged_parent(self,state):
        if file_binding(self.loop.control)!=state['routing']:raise ValueError('routing/pause changed after preparation')
        actual=identity(state['old_transcript'])
        if actual['last_user_hash']!=state['old_user_hash']:raise ValueError('user input changed after preparation')
        return actual

    def fresh(self,state):
        frontier=json.loads((Path(state['reset']['directory'])/'frontier.json').read_text())
        root=Path(self.config['sessions'])
        # Only the current native day is searched; old sessions are not replayed.
        day=root.joinpath(*frontier['prepared_at'][:10].split('-'))
        root=day if day.is_dir() else root
        for path in root.glob('*.jsonl'):
            if path.stat().st_mtime < Path(state['reset']['manifest']['path']).stat().st_mtime:continue
            candidate=identity(path)
            if state['nonce'] in (candidate['first_user'] or '') and candidate['model'] is not None:return path
        return None

    def publish(self,state,result):
        proof=result['last_bootstrap']
        if proof.get('manifest')!=state['reset']['manifest'] or proof.get('nonce')!=state['nonce']:
            raise ValueError('bootstrap receipt does not bind this native reset')
        elapsed=self.clock()-state['started']
        if elapsed>120:raise ValueError('native reset deadline exceeded')
        directory=private_directory(self.config['receipt_directory'])
        snapshot=directory/(state['nonce']+'.goal-ledger.json')
        if not snapshot.exists():atomic_json(snapshot,json.loads(Path(self.config['goal_ledger']).read_text()))
        receipt={'version':1,'verified':True,'manifest':state['reset']['manifest'],
            'nonce':state['nonce'],'previous_session':proof['previous_session'],
            'session_id':result['session_id'],'epoch':result['epoch'],
            'transcript':proof['transcript'],'seconds':round(elapsed,3),
            'goal_receipt':state['goal_receipt'],'goal_ledger':file_binding(snapshot),
            'bootstrap':proof,'transport':'verified-window-native-clear-and-full-prompt'}
        path=directory/(state['nonce']+'.json')
        if path.exists():
            previous=json.loads(path.read_text())
            if any(previous[k]!=receipt[k] for k in receipt if k!='seconds'):
                raise ValueError('existing native receipt differs; do not overwrite')
        else:atomic_json(path,receipt)
        self.loop.acknowledge_native_reset(path)
        state.update(phase='verified',receipt=file_binding(path));self.save(state)
        return state

    def step(self,fresh_transcript=None):
        self.bindings();state=self.status();journal=self.loop.status()
        phase=state['phase']
        if phase in ('monitoring','verified','waiting_release'):
            if journal['epoch_completed']<5 and journal['reset'] is None and not journal.get('reset_requested'):return state
            return self.prepare()
        if phase in ('clear_intent','prompt_intent'):
            raise ValueError('uncertain native input effect; inspect actual title/transcript before recovery')
        if state['started'] is not None and self.clock()-state['started']>120:
            raise ValueError('native reset deadline exceeded; production remains held')
        if phase=='waiting_idle':
            actual=self.unchanged_parent(state)
            if actual['status']!='complete':return state
            self.loop.ready_clear(state['old_transcript']);self.window.check()
            state.update(phase='clear_intent',started=self.clock());self.save(state)
            # [LAW:effects-at-boundaries] Durable intent precedes every native input.
            self.window.type('/clear '+state['title']);self.window.submit()
            state['phase']='waiting_title';self.save(state);return state
        if phase=='waiting_title':
            self.unchanged_parent(state)
            if state['title'] not in self.window.title():return state
            state['phase']='prompt_intent';self.save(state)
            text=(Path(state['reset']['directory'])/'resume-prompt.txt').read_text().rstrip('\n')
            self.window.type(text);self.window.submit()
            state['phase']='waiting_fresh';self.save(state);return state
        if phase=='waiting_fresh':
            if journal.get('last_bootstrap',{}).get('manifest')==state['reset']['manifest']:
                return self.publish(state,journal)
            self.unchanged_parent(state)
            path=fresh_transcript or self.fresh(state)
            if path is None:return state
            result=self.loop.bootstrap(path)
            return self.publish(state,result)
        raise ValueError('unknown autoreset phase')


class Wakeups:
    """Kernel filesystem and compositor events; no model polling turns."""
    def __init__(self,paths):
        library=ctypes.CDLL(None,use_errno=True)
        self.fd=library.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        if self.fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
        self.socket=None
        try:
            for path in set(map(Path,paths)):
                if path.exists():
                    if library.inotify_add_watch(self.fd,os.fsencode(path),0x00000fff)<0:
                        raise OSError(ctypes.get_errno(),'inotify_add_watch')
            self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.socket.connect(str(Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']/'.socket2.sock'))
            self.socket.setblocking(False)
        except BaseException:
            self.close();raise

    def wait(self):
        for handle in select.select([self.fd,self.socket],[],[],5)[0]:
            if handle==self.fd:os.read(self.fd,65536)
            elif not self.socket.recv(65536):raise OSError('compositor event socket closed')

    def close(self):
        os.close(self.fd)
        if self.socket:self.socket.close()


def configured(path):
    config=json.loads(Path(path).read_text());config['config_path']=str(Path(path).absolute())
    loop=Loop(config['state'],config['control'],NativeLit(config['cwd'],config.get('artifact_root',DEFAULT_ROOT)))
    window=NativeWindow(WindowCapability(**config['window']),config['cwd'],config.get('artifact_root',DEFAULT_ROOT))
    return AutoReset(loop,config['supervisor'],config,window)


def wait_bootstrap(controller,manifest):
    bound=file_binding(manifest);deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        state=controller.status()
        if state.get('reset',{}).get('manifest')==bound and state['phase']=='verified':
            if file_binding(state['receipt']['path'])!=state['receipt']:raise ValueError('native receipt changed')
            receipt=json.loads(Path(state['receipt']['path']).read_text())
            actual=identity(receipt['transcript']);journal=controller.loop.status()
            if (not receipt['verified'] or (actual['session_id'],actual['model'],actual['effort'])!=
                (receipt['session_id'],'gpt-6.1-sol','high') or journal['session_id']!=receipt['session_id']):
                raise ValueError('actual fresh native bootstrap mismatch')
            return receipt
        time.sleep(.1)  # Mechanical receipt arrival only; never grants workflow authority.
    raise ValueError('external native bootstrap receipt not published by deadline')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','status','wait-bootstrap','release'])
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--manifest',type=Path)
    parser.add_argument('--ownership',type=Path);parser.add_argument('--goal-receipt',type=Path)
    args=parser.parse_args();controller=configured(args.config)
    try:
        if args.command=='release':
            journal=controller.loop.status()
            owned=json.loads(args.ownership.read_text())['owned_processes']
            if any(Path(f'/proc/{int(h["pid"])}').exists() for h in owned):raise ValueError('owned writer still active')
            goal=json.loads(args.goal_receipt.read_text())['goal']
            if goal['threadId']!=journal['session_id']:raise ValueError('actual current goal receipt required')
            GoalLineage(controller.config['goal_ledger']).record(args.goal_receipt,controller.config['deadline'])
            result=dict(session_id=journal['session_id'],epoch=journal['epoch'],completed=sorted(journal['completed']),
                owned_processes=owned,goal_receipt=str(args.goal_receipt.absolute()))
            atomic_json(controller.config['release'],result)
        elif args.command=='status':result=controller.status()
        elif args.command=='wait-bootstrap':result=wait_bootstrap(controller,args.manifest)
        else:
            with Lease(controller.path.with_suffix('.runtime.lock')):
                while True:
                    old=controller.status();result=controller.step()
                    if result!=old:
                        print(json.dumps({'phase':result['phase'],'nonce':result.get('nonce'),'receipt':result.get('receipt')}),flush=True)
                        continue
                    routing=next(s for s in controller.loop._control()['sessions'] if s['role']=='buford')
                    roots=Path(controller.config['sessions'])
                    today=time.strftime('%Y/%m/%d',time.gmtime())
                    wake=Wakeups([controller.path.parent,controller.loop.path.parent,controller.loop.control,
                        routing['transcript'],Path(routing['transcript']).parent,roots/ today,
                        Path(controller.config['release']).parent])
                    try:wake.wait()
                    finally:wake.close()
            return 0
        print(json.dumps(result));return 0
    except (OSError,ValueError,KeyError) as error:
        print(json.dumps({'held':str(error),'supervisor':str(controller.path)}),file=sys.stderr,flush=True)
        return 2


if __name__=='__main__':sys.exit(main())
