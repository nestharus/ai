#!/usr/bin/env python3
"""Internal verified-rebase reservation/fencing, not a general command runner.

Linux/local-filesystem protocol: flock serializes transitions; persistent records
reserve Git common-dir and jj repository across process exit/yield. No leases,
PID tests, lock stealing, recursive cleanup, shell evaluation, or push support.
The Markdown workflow owns prediction, conflict accounting and semantic handoff.
"""
import argparse
from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


class Blocked(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def read(path):
    require(not path.is_symlink(), f'symlink-record:{path}')
    return json.loads(path.read_bytes())


def write(path, value, exclusive=False):
    """Publish durable records; partial exclusive writes deliberately fail closed."""
    data = encode(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    destination = path if exclusive else path.with_name(path.name + '.next')
    fd = os.open(destination, flags, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        os.replace(destination, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def invoke(repo, args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
                 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        env.pop(name, None)
    return subprocess.run(args, cwd=repo, env=env, capture_output=True)


def command(repo, *args, allowed=(0,)):
    result = invoke(repo, args)
    require(result.returncode in allowed,
            f'command-failed:{args!r}:rc={result.returncode}:{result.stderr.decode(errors="replace")}')
    return result.stdout.decode().strip()


def git(repo, *args, **kwargs):
    return command(repo, 'git', *args, **kwargs)


def jj(repo, *args):
    return command(repo, 'jj', '--ignore-working-copy', '--no-pager', *args)


def path_identity(path):
    path = path.resolve(strict=True)
    stat = path.stat()
    require(path.is_dir(), f'not-directory:{path}')
    return {'path': str(path), 'device': stat.st_dev, 'inode': stat.st_ino}


def substrate(repo):
    """Resolve supported colocated Git/jj metadata without snapshot-capable jj."""
    repo = Path(repo).resolve(strict=True)
    require(git(repo, 'rev-parse', '--show-toplevel') == str(repo), 'not-repository-root')
    common = Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir'))
    jjrepo = repo / '.jj/repo'
    if jjrepo.is_file():
        jjrepo = jjrepo.parent / jjrepo.read_text().strip()
    jjrepo = jjrepo.resolve(strict=True)
    store = (jjrepo / 'store').resolve(strict=True)
    target = store / 'git_target'
    git_target = (store / target.read_text().strip()).resolve(strict=True)
    target_common = Path(git(git_target, 'rev-parse', '--path-format=absolute', '--git-common-dir'))
    require(target_common.resolve() == common.resolve(), 'jj-git-store-mismatch')
    require((jjrepo / 'op_heads/heads').is_dir(), 'unsupported-jj-operation-store')
    return {key: path_identity(value) for key, value in
            [('root', repo), ('common', common), ('jjrepo', jjrepo), ('store', store)]}


def resources(identity):
    return sorted({Path(identity[key]['path']) / 'verified-rebase-ownership'
                   for key in ('common', 'jjrepo', 'store')})


@contextmanager
def guards(identity):
    with ExitStack() as stack:
        lock_resources(stack, identity)
        yield


def lock_resources(stack, identity):
    for path in resources(identity):
        lock_resource(stack, path)


def lock_resource(stack, path):
    path.mkdir(exist_ok=True, mode=0o700)
    require(not path.is_symlink(), f'symlink-lock:{path}')
    fd = os.open(path / 'guard', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    stack.callback(os.close, fd)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise Blocked('transition-in-progress') from error


def snapshot(identity):
    repo = identity['root']['path']
    heads = sorted(p.name for p in (Path(identity['jjrepo']['path']) / 'op_heads/heads').iterdir())
    require(len(heads) == 1, 'ambiguous-jj-operation-heads')
    return {'op': heads[0], 'refs': git(repo, 'for-each-ref', '--format=%(refname) %(objectname)'),
            'head': git(repo, 'rev-parse', 'HEAD'),
            'symbolic_head': git(repo, 'symbolic-ref', '-q', 'HEAD', allowed=(0, 1))}


def clean(identity):
    repo = identity['root']['path']
    status = git(repo, 'status', '--porcelain=v1', '--untracked-files=all')
    others = git(repo, 'ls-files', '--others', '-z').split('\0')
    foreign = [p for p in others if p and not p.startswith('.jj/')]
    require(not status and not foreign, 'dirty-working-copy')
    # Pinned operation prevents implicit concurrent-operation reconciliation.
    op = snapshot(identity)['op']
    require(not jj(repo, '--at-operation', op, 'diff', '-r', '@', '--summary'), 'nonempty-jj-working-copy')


def valid_released(record):
    require(record.get('released') is True, 'substrate-reserved')
    bundle = Path(record['bundle'])
    require(digest((bundle / 'owner.json').read_bytes()) == record['owner_hash'], 'unknown-prior-owner')
    require(digest((bundle / 'result.json').read_bytes()) == record['result_hash'], 'unknown-prior-terminal')


def publish_reservations(owner, released=False, result_hash=None):
    record = {'bundle': owner['bundle'], 'owner_hash': digest(encode(owner)),
              'released': released, 'result_hash': result_hash}
    for path in resources(owner['substrate']):
        write(path / 'reservation.json', record)


def available(identity):
    for path in resources(identity):
        available_resource(path)


def available_resource(path):
    prior = path / 'reservation.json'
    if prior.exists():
        valid_released(read(prior))


def external_planning(planning, identity):
    planning = Path(planning).resolve(strict=True)
    # Also disallow any other Git/jj checkout, not just this substrate.
    require(not any((p / '.git').exists() or (p / '.jj').exists()
                    for p in (planning, *planning.parents)), 'planning-inside-checkout')
    require(not any(planning.is_relative_to(Path(v['path'])) for v in identity.values()),
            'planning-inside-substrate')
    return planning


def allocate(repo, planning, owner_id, attempt_id, branch, target, source=None):
    owner_id, attempt_id = str(uuid.UUID(owner_id)), str(uuid.UUID(attempt_id))
    identity = substrate(repo)
    planning = external_planning(planning, identity)
    bundle = planning / owner_id / attempt_id
    bundle.parent.mkdir(exist_ok=True, mode=0o700)
    require(not bundle.parent.is_symlink(), 'symlink-owner-directory')
    bundle.mkdir(mode=0o700)  # exclusive; never reuse a bundle or a branch slug
    owner = {'schema': 1, 'owner_id': owner_id, 'attempt_id': attempt_id,
             'branch': branch, 'target': target, 'source': source,
             'bundle': str(bundle), 'substrate': identity,
             'anchor': f'refs/pre-rebase/{attempt_id}',
             'helper_sha256': digest(Path(__file__).read_bytes())}
    write(bundle / 'owner.json', owner, exclusive=True)
    try:
        reserve(owner)
    except (Blocked, OSError, ValueError, KeyError) as error:
        write(bundle / 'allocation-blocked.json', {'execution': 'BLOCKED', 'reason': str(error),
              'owner': owner, 'push_eligible': False}, exclusive=True)
        raise
    return str(bundle)


def reserve(owner):
    with guards(owner['substrate']):
        available(owner['substrate'])
        publish_reservations(owner)
        # A crash before this write leaves a persistent, unrecoverable reservation.
        write(Path(owner['bundle']) / 'state.json',
              {'checkpoint': snapshot(owner['substrate']), 'completed': [], 'inflight': None}, exclusive=True)


class Attempt:
    def __init__(self, bundle, owner_id, attempt_id):
        self.bundle = Path(bundle).resolve(strict=True)
        self.owner = read(self.bundle / 'owner.json')
        require(self.owner['bundle'] == str(self.bundle), 'bundle-mismatch')
        require(self.owner['owner_id'] == owner_id and self.owner['attempt_id'] == attempt_id,
                'owner-attempt-mismatch')
        require(self.owner['helper_sha256'] == digest(Path(__file__).read_bytes()), 'helper-identity-changed')
        self.identity = self.owner['substrate']
        self.repo = self.identity['root']['path']

    def validate(self, released=False):
        require(substrate(self.repo) == self.identity, 'substrate-identity-changed')
        for path in resources(self.identity):
            self.validate_reservation(path, released)
        state = read(self.bundle / 'state.json')
        require(state['inflight'] is None, 'interrupted-command-needs-recovery')
        require(snapshot(self.identity) == state['checkpoint'], 'intervening-substrate-operation')
        return state

    def validate_reservation(self, path, released):
        record = read(path / 'reservation.json')
        require(record['owner_hash'] == digest(encode(self.owner)) and record['bundle'] == str(self.bundle)
                and record['released'] == released, 'reservation-owner-or-lifecycle-mismatch')
        if released:
            valid_released(record)

    def inspect(self):
        with guards(self.identity):
            return self.validate()

    def check(self):
        with guards(self.identity):
            state = self.validate()
            clean(self.identity)
            return state

    def mutate(self, action, revision=None):
        with guards(self.identity):
            return self.mutate_locked(action, revision)

    def mutate_locked(self, action, revision=None):
        state = self.validate()
        require(not (self.bundle / 'result.json').exists(), 'attempt-already-terminal')
        clean(self.identity)
        label, args = self.mutation(state, action, revision)
        require(label not in state['completed'], 'command-already-completed')
        if action == 'anchor':
            state['pre'] = self.pre_refs()
        state['inflight'] = {'label': label, 'args': args}
        write(self.bundle / 'state.json', state)
        output = self.execute(label, args)
        state['checkpoint'] = snapshot(self.identity)
        state['completed'].append(label)
        if action == 'fetch':
            state['pre']['NEW_TARGET'] = git(self.repo, 'rev-parse', '--verify', f'{self.owner["target"]}^{{commit}}')
            state['pre']['JJ_PRE_OP_ID'] = state['checkpoint']['op']
            require(git(self.repo, 'rev-parse', self.owner['branch']) == state['pre']['PRE_TIP'], 'branch-moved-during-fetch')
        state['inflight'] = None
        write(self.bundle / f'{label}.json', {'args': args, 'stdout': output,
              'checkpoint': state['checkpoint']}, exclusive=True)
        write(self.bundle / 'state.json', state)
        return state

    def execute(self, label, args):
        result = invoke(self.repo, args)
        receipt = {'args': args, 'returncode': result.returncode,
                   'stdout': result.stdout.decode(errors='replace'),
                   'stderr': result.stderr.decode(errors='replace')}
        write(self.bundle / f'{label}-command.json', receipt, exclusive=True)
        require(result.returncode == 0, f'command-failed:{label}:see-{label}-command.json')
        return receipt['stdout']

    def mutation(self, state, action, revision):
        owner = self.owner
        base_jj = ['jj', '--ignore-working-copy', '--no-pager']
        if action == 'anchor':
            tip = git(self.repo, 'rev-parse', '--verify', f'{owner["branch"]}^{{commit}}')
            return 'anchor', ['git', 'update-ref', owner['anchor'], tip, '0' * len(tip)]
        require('anchor' in state['completed'], 'anchor-required')
        if action == 'fetch':
            return 'fetch', base_jj + ['git', 'fetch']
        require('fetch' in state['completed'], 'fetch-required')
        if action == 'rebase':
            target = state['pre']['NEW_TARGET']
            scope = ['-s', state['pre']['SOURCE_COMMIT']] if owner['source'] else ['-b', owner['branch']]
            return 'rebase', base_jj + ['--config', 'revset-aliases."immutable_heads()"="none()"',
                                      'rebase', *scope, '-d', target]
        require(action == 'abandon' and 'rebase' in state['completed'], 'unsupported-mutation')
        require(revision and len(revision) in (40, 64) and all(c in '0123456789abcdef' for c in revision),
                'cleanup-requires-exact-commit-id')
        self.cleanup_revision(state, revision)
        return f'abandon-{revision}', base_jj + ['--config', 'revset-aliases."immutable_heads()"="none()"',
                                              'abandon', revision]

    def pre_refs(self):
        owner = self.owner
        pre_tip = git(self.repo, 'rev-parse', '--verify', f'{owner["branch"]}^{{commit}}')
        base = git(self.repo, 'merge-base', owner['branch'], owner['target'])
        source = None
        if owner['source']:
            source = git(self.repo, 'rev-parse', '--verify', f'{owner["source"]}^{{commit}}')
            git(self.repo, 'merge-base', '--is-ancestor', source, pre_tip)
            base = git(self.repo, 'rev-parse', source + '^')
        return {'PRE_TIP': pre_tip, 'PRE_BASE': base, 'SOURCE_COMMIT': source}

    def cleanup_revision(self, state, revision):
        pre = state['pre']
        old = git(self.repo, 'rev-list', f'{pre["PRE_BASE"]}..{pre["PRE_TIP"]}').splitlines()
        require(revision in old, 'cleanup-not-owned-pre-rebase-commit')
        current = git(self.repo, 'rev-list', self.owner['branch']).splitlines()
        require(revision not in current, 'cleanup-would-abandon-current-branch')
        change = jj(self.repo, 'log', '-r', revision, '--no-graph', '-T', 'change_id')
        versions = jj(self.repo, 'log', '-r', f'change_id({change})', '--no-graph', '-T', 'commit_id ++ "\\n"').splitlines()
        require(revision in versions and any(oid in current for oid in versions if oid != revision),
                'cleanup-no-proven-current-divergent-survivor')

    def finish(self, mechanical, execution, reason=''):
        with guards(self.identity):
            return self.finish_locked(mechanical, execution, reason)

    def finish_locked(self, mechanical, execution, reason=''):
        state = self.validate()
        require(execution in ('COMPLETE', 'BLOCKED'), 'invalid-execution-terminal')
        require(mechanical in ('CLEAN', 'DIRTY-EXPLAINED', 'DIRTY-UNPROVENANCED', 'NOT-RUN'),
                'invalid-mechanical-verdict')
        if execution == 'COMPLETE':
            clean(self.identity)
            require('rebase' in state['completed'] and mechanical != 'NOT-RUN', 'rebase-not-complete')
        result = {'owner': self.owner, 'checkpoint': state['checkpoint'], 'mechanical': mechanical,
                  'execution': execution, 'reason': reason, 'topology_validation': 'operator-owned',
                  'pre': state.get('pre'), 'POST_TIP': git(self.repo, 'rev-parse', '--verify', self.owner['branch'], allowed=(0, 128)),
                  'evidence_hashes': evidence_hashes(self.bundle),
                  'state_sha256': digest((self.bundle / 'state.json').read_bytes()),
                  'push_eligible': False, 'push_authority': 'caller-exact-lease-and-review',
                  'worktree_sync': 'pending-caller'}
        write(self.bundle / 'result.json', result, exclusive=True)
        return result

    def terminal_state(self, result):
        expected = result['state_sha256']
        if (self.bundle / 'rollback-result.json').exists():
            expected = digest((self.bundle / 'rollback-result.json').read_bytes())
            rollback = read(self.bundle / 'rollback-result.json')
            require(rollback['rollback_command_sha256'] == digest((self.bundle / 'rollback-command.json').read_bytes()), 'rollback-evidence-changed')
        require(digest((self.bundle / 'state.json').read_bytes()) == expected, 'terminal-state-changed')

    def release(self):
        with guards(self.identity):
            return self.release_locked()

    def release_locked(self):
        self.validate()
        result = read(self.bundle / 'result.json')
        self.terminal_state(result)
        require(result['owner'] == self.owner and result['execution'] in ('COMPLETE', 'BLOCKED'), 'terminal-mismatch')
        require(result['evidence_hashes'] == evidence_hashes(self.bundle), 'evidence-changed-after-terminal')
        if result['execution'] == 'COMPLETE':
            clean(self.identity)
        publish_reservations(self.owner, released=True,
                             result_hash=digest((self.bundle / 'result.json').read_bytes()))
        # Persistent released tombstone fences later rollback even after a clean successor.
        return result

    def rollback(self):
        with guards(self.identity):
            return self.rollback_locked()

    def rollback_locked(self):
        state = self.validate(released=True)
        clean(self.identity)
        result = read(self.bundle / 'result.json')
        self.terminal_state(result)
        require(result['owner'] == self.owner, 'terminal-mismatch')
        require(result['evidence_hashes'] == evidence_hashes(self.bundle), 'evidence-changed-after-terminal')
        require(git(self.repo, 'rev-parse', self.owner['anchor']) ==
                state['pre']['PRE_TIP'],
                'anchor-changed')
        if 'rollback' in state['completed']:
            return state  # Only after full owner/currentness/cleanliness checks.
        require('rebase' in state['completed'], 'no-rebase-to-rollback')
        pre = state['pre']['JJ_PRE_OP_ID']
        publish_reservations(self.owner)
        expected = read(self.bundle / 'fetch.json')['checkpoint'].copy()
        expected['refs'] = restore_refs(expected['refs'], state['checkpoint']['refs'])
        state['inflight'] = {'label': 'rollback', 'op': pre, 'expected': expected}
        write(self.bundle / 'state.json', state)
        self.execute('rollback', ['jj', '--ignore-working-copy', '--no-pager', 'op', 'restore', pre])
        state['checkpoint'] = snapshot(self.identity)
        require(all(state['checkpoint'][key] == expected[key] for key in ('refs', 'head', 'symbolic_head')),
                'rollback-readback-mismatch')
        state['completed'].append('rollback')
        state['rollback_command_sha256'] = digest((self.bundle / 'rollback-command.json').read_bytes())
        state['inflight'] = None
        write(self.bundle / 'rollback-result.json', state, exclusive=True)
        write(self.bundle / 'state.json', state)
        publish_reservations(self.owner, released=True,
                             result_hash=digest((self.bundle / 'result.json').read_bytes()))
        return state


def restore_refs(before, after):
    # jj retains Git GC roots for this attempt's rebased commits on op restore.
    # Preserve exactly the pinned post-state keep refs, not arbitrary future ones.
    baseline = [line for line in before.splitlines() if not line.startswith('refs/jj/keep/')]
    retained = [line for line in after.splitlines() if line.startswith('refs/jj/keep/')]
    return '\n'.join(sorted(baseline + retained))


def evidence_hashes(bundle):
    paths = sorted(bundle.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'symlink-evidence')
    return {str(p.relative_to(bundle)): digest(p.read_bytes()) for p in paths
            if p.is_file() and str(p.relative_to(bundle)) not in ('result.json', 'state.json', 'rollback-result.json', 'rollback-command.json')}


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['allocate', 'inspect', 'check', 'anchor', 'fetch', 'rebase', 'abandon',
                                         'finish', 'release', 'rollback'])
    parser.add_argument('--owner-id', required=True)
    parser.add_argument('--attempt-id', required=True)
    for name in ('bundle', 'repo', 'planning', 'branch', 'target', 'source', 'revision', 'mechanical', 'execution', 'reason'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    if args.action == 'allocate':
        return allocate(args.repo, args.planning, args.owner_id, args.attempt_id, args.branch, args.target, args.source)
    attempt = Attempt(args.bundle, args.owner_id, args.attempt_id)
    if args.action in ('anchor', 'fetch', 'rebase', 'abandon'):
        return attempt.mutate(args.action, args.revision)
    if args.action == 'finish':
        return attempt.finish(args.mechanical, args.execution, args.reason or '')
    return getattr(attempt, args.action)()


if __name__ == '__main__':
    try:
        print(json.dumps(cli(), sort_keys=True))
    except (Blocked, OSError, ValueError, KeyError, TypeError) as error:
        print(f'BLOCKED:{error}', file=sys.stderr)
        sys.exit(2)
