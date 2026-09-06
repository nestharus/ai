#!/usr/bin/env python3
"""Internal verified-rebase reservation/fencing, not a general command runner.

Linux/local-filesystem protocol: flock serializes transitions; persistent records
reserve Git common-dir and jj repository across process exit/yield. No leases,
PID tests, lock stealing, recursive cleanup, shell evaluation, or push support.
The helper produces mechanical evidence; the selected endpoint owns the workflow
and semantic handoff. Mechanical provenance is never semantic resolution.
"""
import argparse
import base64
from datetime import datetime, timezone
from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import json
import os
import re
import shlex
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


def invoke(repo, args, input=None):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
                 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        env.pop(name, None)
    return subprocess.run(args, cwd=repo, env=env, input=input, capture_output=True)


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
    require(jjrepo.exists(), 'colocated-jj-required:no-manual-rebase')
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
    # Establish an external refusal destination before probing the substrate.
    # Unsupported/manual Git worktrees and absent jj must not select a fallback.
    planning = external_planning(planning, {})
    identity, substrate_error = None, None
    try:
        identity = substrate(repo)
    except (Blocked, OSError, ValueError, KeyError) as error:
        substrate_error = error
    if identity is not None:
        external_planning(planning, identity)
    bundle = planning / owner_id / attempt_id
    bundle.parent.mkdir(exist_ok=True, mode=0o700)
    require(not bundle.parent.is_symlink(), 'symlink-owner-directory')
    bundle.mkdir(mode=0o700)
    request = {'owner_id': owner_id, 'attempt_id': attempt_id,
               'repo': str(Path(repo).resolve()), 'branch': branch, 'target': target,
               'source': source, 'bundle': str(bundle),
               'helper_sha256': digest(Path(__file__).read_bytes())}
    write(bundle / 'request.json', request, exclusive=True)
    owner = None
    try:
        if substrate_error is not None:
            raise substrate_error
        probe_jj(identity['root']['path'], bundle)
        owner = {'schema': 1, **{k: request[k] for k in
                 ('owner_id', 'attempt_id', 'branch', 'target', 'source', 'bundle', 'helper_sha256')},
                 'substrate': identity, 'anchor': f'refs/pre-rebase/{attempt_id}'}
        write(bundle / 'owner.json', owner, exclusive=True)
        reserve(owner)
    except (Blocked, OSError, ValueError, KeyError) as error:
        write(bundle / 'allocation-blocked.json', {'execution': 'BLOCKED', 'reason': str(error),
              'request': request, 'owner': owner, 'push_eligible': False}, exclusive=True)
        raise
    return str(bundle)


def probe_jj(repo, bundle):
    args = ['jj', '--version']
    try:
        result = invoke(repo, args)
    except OSError as error:
        write(bundle / 'jj-probe.json', {'args': args, 'error': str(error)}, exclusive=True)
        raise Blocked('jj-unavailable:no-rebase-fallback') from error
    write(bundle / 'jj-probe.json', {'args': args, 'returncode': result.returncode,
          'stdout_base64': base64.b64encode(result.stdout).decode(),
          'stderr_base64': base64.b64encode(result.stderr).decode()}, exclusive=True)
    require(result.returncode == 0, 'jj-unavailable:no-rebase-fallback')


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
            state['pre'] = self.pre_refs(state['checkpoint'])
        # Read-only source/cleanup resolution must not authorize an intervening operation.
        self.validate()
        nonce = str(uuid.uuid4())
        if args[0] == 'jj':
            args[1:1] = ['--at-operation', state['checkpoint']['op'],
                         '--config', 'operation.username=' + nonce,
                         '--config', 'operation.hostname=verified-rebase']
        state['inflight'] = {'label': label, 'args': args, 'command_id': nonce}
        write(self.bundle / 'state.json', state)
        output = self.execute(label, args)
        state['checkpoint'] = self.command_checkpoint(state, label, args, nonce)
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

    def command_checkpoint(self, state, label, args, nonce):
        """Accept only this command's operation lineage and attributable Git exports.

        The observed head is an untrusted candidate, never the authorization for
        itself. Read immutable operation metadata at exact IDs; do not reconcile
        concurrent heads. An unexplained operation/ref keeps the intent in flight.
        """
        require(substrate(self.repo) == self.identity, 'substrate-identity-changed')
        for path in resources(self.identity):
            self.validate_reservation(path, released=False)
        before = state['checkpoint']
        after = snapshot(self.identity)
        write(self.bundle / f'{label}-observed.json', after, exclusive=True)
        expected = before.copy()
        if args[0] == 'git':
            refs = ref_map(before['refs'])
            refs[self.owner['anchor']] = state['pre']['PRE_TIP']
            expected['refs'] = ref_text(refs)
        else:
            cursor = after['op']
            seen = set()
            while cursor != before['op']:
                require(cursor not in seen, 'cyclic-operation-lineage')
                seen.add(cursor)
                op = json.loads(jj(self.repo, '--at-operation', cursor, 'op', 'log',
                                   '--limit', '1', '--no-graph', '-T', 'json(self)'))
                write(self.bundle / f'{label}-operation-{cursor}.json', op, exclusive=True)
                require(op['id'] == cursor and op['username'] == nonce
                        and op['hostname'] == 'verified-rebase'
                        and shlex.split(op['tags']['args']) == args
                        and len(op['parents']) == 1, 'unowned-command-operation')
                cursor = op['parents'][0]
            expected['op'] = after['op']
            expected['refs'] = self.command_refs(before, after)
            if before['symbolic_head']:
                expected['head'] = ref_map(expected['refs'])[before['symbolic_head']]
        require(after == expected, 'unexplained-command-effects')
        clean(self.identity)
        require(snapshot(self.identity) == after, 'state-changed-during-command-readback')
        return expected

    def command_refs(self, before, after):
        refs = ref_map(before['refs'])
        old_exports = operation_exports(self.repo, before['op'])
        new_exports = operation_exports(self.repo, after['op'])
        for name in old_exports.keys() | new_exports.keys():
            if old_exports.get(name) != new_exports.get(name):
                require(refs.get(name) == old_exports.get(name), 'unimported-git-ref')
                if name in new_exports:
                    refs[name] = new_exports[name]
                else:
                    refs.pop(name, None)
        # jj creates GC roots for newly written commits. Only roots whose exact
        # name AND value are newly visible in the owned operation may be added.
        new_commits = operation_commits(self.repo, after['op']) - operation_commits(self.repo, before['op'])
        for name, oid in ref_map(after['refs']).items():
            if name not in refs and name == 'refs/jj/keep/' + oid and oid in new_commits:
                refs[name] = oid
        return ref_text(refs)

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

    def pre_refs(self, checkpoint):
        owner = self.owner
        pre_tip = git(self.repo, 'rev-parse', '--verify', f'{owner["branch"]}^{{commit}}')
        base = git(self.repo, 'merge-base', owner['branch'], owner['target'])
        source = None
        if owner['source']:
            source = self.resolve_source(checkpoint)
            git(self.repo, 'merge-base', '--is-ancestor', source, pre_tip)
            base = git(self.repo, 'rev-parse', source + '^')
        return {'PRE_TIP': pre_tip, 'PRE_BASE': base, 'SOURCE_COMMIT': source,
                'SOURCE_OPERATION': checkpoint['op'] if source else None,
                'CLEANUP_CANDIDATES': self.pre_cleanup_candidates(base, pre_tip, checkpoint['op'])}

    def resolve_source(self, checkpoint):
        # No --limit: cardinality is a contract, not a best-effort first match.
        args = ['jj', '--ignore-working-copy', '--no-pager', '--at-operation', checkpoint['op'],
                'log', '-r', self.owner['source'], '--no-graph', '-T', 'commit_id ++ "\\n"']
        result = invoke(self.repo, args)
        write(self.bundle / f'source-resolution-{uuid.uuid4()}.json', {
            'source': self.owner['source'], 'checkpoint': checkpoint, 'args': args,
            'returncode': result.returncode,
            'stdout_base64': base64.b64encode(result.stdout).decode(),
            'stderr_base64': base64.b64encode(result.stderr).decode()}, exclusive=True)
        require(result.returncode == 0, 'source-resolution-failed')
        commits = result.stdout.decode().splitlines()
        require(len(commits) == 1, 'source-requires-single-commit')
        source = commits[0]
        require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', source), 'invalid-source-commit-id')
        require(git(self.repo, 'rev-parse', '--verify', source + '^{commit}') == source,
                'source-git-identity-mismatch')
        return source

    def pre_cleanup_candidates(self, base, tip, op):
        ids = jj(self.repo, '--at-operation', op, 'log', '-r', f'{base}..{tip}',
                 '--no-graph', '-T', 'change_id ++ "\\n"').splitlines()
        candidates = {}
        for change in set(ids):
            versions = jj(self.repo, '--at-operation', op, 'log', '-r', f'change_id({change})',
                          '--no-graph', '-T', 'commit_id ++ "\\n"').splitlines()
            candidates.update({oid: change for oid in versions})
        return candidates

    def cleanup_revision(self, state, revision):
        pre = state['pre']
        candidates = pre['CLEANUP_CANDIDATES']
        require(revision in candidates, 'cleanup-not-owned-pre-rebase-commit')
        current = git(self.repo, 'rev-list', self.owner['branch']).splitlines()
        require(revision not in current, 'cleanup-would-abandon-current-branch')
        change = candidates[revision]
        versions = jj(self.repo, '--at-operation', state['checkpoint']['op'], 'log', '-r', f'change_id({change})', '--no-graph', '-T', 'commit_id ++ "\\n"').splitlines()
        require(revision in versions and any(oid in current for oid in versions if oid != revision),
                'cleanup-no-proven-current-divergent-survivor')

    def capture_conflicts(self):
        with guards(self.identity):
            state = self.validate()
            require('rebase' in state['completed'], 'rebase-required')
            require(not (self.bundle / 'result.json').exists(), 'attempt-already-terminal')
            post = git(self.repo, 'rev-parse', '--verify', self.owner['branch'])
            args = ['jj', '--ignore-working-copy', '--no-pager', '--color=never',
                    '--at-operation', state['checkpoint']['op']]
            directory = self.bundle / 'conflict-artifacts'
            directory.mkdir()  # exclusive, including interrupted generations
            raw = invoke(self.repo, args + ['resolve', '--list', '-r', post])
            (directory / 'jj-resolve-list-raw.txt').write_bytes(raw.stdout)
            (directory / 'jj-resolve-list.stderr').write_bytes(raw.stderr)
            (directory / 'jj-resolve-list.status').write_text(str(raw.returncode) + '\n')
            conflict = jj(self.repo, '--at-operation', state['checkpoint']['op'],
                          'log', '-r', post, '--no-graph', '-T', 'json(conflict)')
            no_conflicts = (conflict == 'false' and raw.returncode == 2 and not raw.stdout
                            and raw.stderr == b'Error: No conflicts found at this revision\n')
            require(raw.returncode == 0 or no_conflicts, 'resolve-list-failed')
            paths = conflict_paths(raw.stdout.decode())
            (directory / 'files.txt').write_text(''.join(p + '\n' for p in paths))
            mapping = []
            for index, path in enumerate(paths):
                # The ordinal is injective over this validated, duplicate-free list,
                # independent of path spelling or platform component length limits.
                name = f'{index}.conflict'
                result = invoke(self.repo, args + ['file', 'show', '-r', post, '--', path])
                with (directory / name).open('xb') as stream:
                    stream.write(result.stdout)
                (directory / f'{index}.stderr').write_bytes(result.stderr)
                (directory / f'{index}.status').write_text(str(result.returncode) + '\n')
                mapping.append({'path': path, 'artifact': name, 'sha256': digest(result.stdout)})
                require(result.returncode == 0 and result.stdout, 'conflict-artifact-failed')
            write(directory / 'index.json', mapping, exclusive=True)
            require(self.validate() == state, 'state-changed-during-conflict-capture')
            return mapping

    def assemble(self, parent_bundle=None):
        """Produce the complete mechanical bundle once, from pinned objects only."""
        with guards(self.identity):
            state = self.validate()
            require('rebase' in state['completed'], 'rebase-required')
            require('mechanics' not in state and not (self.bundle / 'result.json').exists(),
                    'bundle-already-assembled')
            evidence = MechanicalEvidence(self, state)
            decision = evidence.assemble(parent_bundle)
            require(self.validate() == state, 'state-changed-during-assembly')
            state['assembly_checkpoint'] = state['checkpoint']
            state['mechanics'] = decision
            state['assembly_hashes'] = evidence_hashes(self.bundle)
            write(self.bundle / 'state.json', state)
            return decision

    def finish(self, mechanical=None, execution=None, reason=''):
        with guards(self.identity):
            return self.finish_locked(mechanical, execution, reason)

    def finish_locked(self, mechanical=None, execution=None, reason=''):
        state = self.validate()
        if 'rebase' in state['completed']:
            require('mechanics' in state, 'complete-mechanical-bundle-required')
            require(state['assembly_checkpoint'] == state['checkpoint'], 'assembled-state-changed')
            require(state['assembly_hashes'] == evidence_hashes(self.bundle), 'assembled-evidence-changed')
            derived = state['mechanics']['verdict']
            require(mechanical is None or mechanical == derived, 'mechanical-label-mismatch')
            mechanical = derived
            if execution is None:
                execution = 'BLOCKED' if derived == 'DIRTY-UNPROVENANCED' else 'COMPLETE'
            if derived == 'DIRTY-UNPROVENANCED' and not reason:
                reason = ';'.join(state['mechanics']['problems'])
            require(execution != 'COMPLETE' or derived != 'DIRTY-UNPROVENANCED',
                    'unprovenanced-mechanics-blocked')
        else:
            require(mechanical in (None, 'NOT-RUN') and execution == 'BLOCKED', 'rebase-not-complete')
            mechanical = 'NOT-RUN'
            # Partial/preflight terminals explicitly have no mechanical evidence.
            write(self.bundle / 'refs.json', {'branch': self.owner['branch'], 'target': self.owner['target'],
                  'pre': state.get('pre'), 'verdict': mechanical, 'execution': execution}, exclusive=True)
            with (self.bundle / 'summary.md').open('x') as stream:
                stream.write('Verified rebase NOT-RUN\nBLOCKED: ' + reason + '\n')
        require(execution in ('COMPLETE', 'BLOCKED'), 'invalid-execution-terminal')
        if execution == 'COMPLETE':
            clean(self.identity)
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
            require(rollback['rollback_evidence_hashes'] == rollback_evidence_hashes(self.bundle), 'rollback-evidence-changed')
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
        nonce = str(uuid.uuid4())
        args = ['jj', '--ignore-working-copy', '--no-pager', '--at-operation', state['checkpoint']['op'],
                '--config', 'operation.username=' + nonce, '--config', 'operation.hostname=verified-rebase',
                'op', 'restore', pre]
        state['inflight'].update(args=args, command_id=nonce)
        write(self.bundle / 'state.json', state)
        self.execute('rollback', args)
        state['checkpoint'] = self.command_checkpoint(state, 'rollback', args, nonce)
        require(all(state['checkpoint'][key] == expected[key] for key in ('refs', 'head', 'symbolic_head')),
                'rollback-readback-mismatch')
        state['completed'].append('rollback')
        state['rollback_evidence_hashes'] = rollback_evidence_hashes(self.bundle)
        state['inflight'] = None
        write(self.bundle / 'rollback-result.json', state, exclusive=True)
        write(self.bundle / 'state.json', state)
        publish_reservations(self.owner, released=True,
                             result_hash=digest((self.bundle / 'result.json').read_bytes()))
        return state


# jj's versioned Git conflict serialization. A different layout is not silently
# filtered: it must first gain a decoder/proof and an executed fixture.
CONFLICT_README = b'''This commit was made by jj, https://jj-vcs.dev/.
The commit contains file conflicts, and therefore looks wrong when used with
plain Git or other tools that are unfamiliar with jj.

The .jjconflict-* directories represent the different inputs to the conflict.
For details, see
https://docs.jj-vcs.dev/latest/git-compatibility/#format-mapping-details

If you see this file in your working copy, it probably means that you used a
regular `git` command to check out a conflicted commit. Use `jj abandon` to
recover.
'''


class MechanicalEvidence:
    """One bounded source-bound decoder, correspondence proof and bundle producer.

    Raw Git residual/range output remains intact. Logical trees are derived from
    the pinned jj reader only after exact storage/header validation. No conflict
    is resolved, no path is excluded merely by its name, and no range row is used
    as a substitute for a bijection of exact changes and their parent edges.
    """
    def __init__(self, attempt, state):
        self.a, self.state = attempt, state
        self.bundle, self.repo = attempt.bundle, attempt.repo
        self.op = state['checkpoint']['op']
        self.pre = state['pre']
        self.observations = self.bundle / 'mechanical-observations'
        self.observations.mkdir()
        self.sequence = 0
        self.logical = {}

    def observe(self, args, input=None, allowed=(0,)):
        result = invoke(self.repo, args, input=input)
        self.sequence += 1
        write(self.observations / f'{self.sequence:05}.json', {
            'args': args, 'input_base64': None if input is None else base64.b64encode(input).decode(),
            'returncode': result.returncode, 'stdout_base64': base64.b64encode(result.stdout).decode(),
            'stderr_base64': base64.b64encode(result.stderr).decode()}, exclusive=True)
        require(result.returncode in allowed, f'mechanical-command-failed:{self.sequence}')
        return result

    def git(self, *args, **kwargs):
        return self.observe(['git', *args], **kwargs).stdout

    def jj(self, *args, op=None, **kwargs):
        return self.observe(['jj', '--ignore-working-copy', '--no-pager', '--color=never',
                             '--at-operation', op or self.op, *args], **kwargs).stdout

    def emit(self, path, data):
        if isinstance(data, str):
            data = data.encode()
        destination = self.bundle / path
        if destination.exists():
            require(destination.read_bytes() == data, f'producer-output-mismatch:{path}')
        else:
            with destination.open('xb') as stream:
                stream.write(data)

    def tree_map(self, tree):
        entries = {}
        for row in self.git('ls-tree', '-rz', tree).split(b'\0'):
            if not row:
                continue
            meta, path = row.split(b'\t', 1)
            mode, kind, oid = meta.decode().split()
            path = path.decode()
            require(re.fullmatch(r'[A-Za-z0-9._/-]+', path) is not None,
                    'unsupported-mechanical-path')
            entries[path] = [mode, kind, oid]
        return entries

    def make_tree(self, entries):
        children = {}
        leaves = []
        for path, (mode, kind, oid) in entries.items():
            if '/' in path:
                directory, tail = path.split('/', 1)
                children.setdefault(directory, {})[tail] = [mode, kind, oid]
            else:
                leaves.append(f'{mode} {kind} {oid}\t{path}\0')
        for directory, values in children.items():
            require(directory not in entries, 'file-directory-collision')
            leaves.append(f'040000 tree {self.make_tree(values)}\t{directory}\0')
        return self.git('mktree', '-z', input=''.join(sorted(leaves)).encode()).decode().strip()

    def decode(self, commit):
        if commit in self.logical:
            return self.logical[commit]
        raw = self.git('cat-file', 'commit', commit)
        tree = self.git('rev-parse', commit + '^{tree}').decode().strip()
        headers = raw.split(b'\n\n', 1)[0].splitlines()
        term_headers = [h[9:].decode().split() for h in headers if h.startswith(b'jj:trees ')]
        value = self.decode_conflict(commit, raw, tree, term_headers) if term_headers else self.decode_plain(commit, tree)
        self.logical[commit] = value
        return value

    def decode_plain(self, commit, tree):
        require(self.jj('log', '-r', commit, '--no-graph', '-T', 'json(conflict)').strip() == b'false',
                'missing-conflict-tree-headers')
        return {'tree': tree, 'conflicts': [], 'commit': commit, 'raw_tree': tree}

    def conflict_storage(self, tree, term_headers):
        require(len(term_headers) == 1 and len(term_headers[0]) >= 3
                and len(term_headers[0]) % 2 == 1, 'unsupported-conflict-tree-headers')
        maps = [self.tree_map(term) for term in term_headers[0]]
        expected = dict(maps[0])
        require(not any(p == 'JJ-CONFLICT-README' or p.startswith('.jjconflict-')
                        for values in maps for p in values), 'conflict-storage-name-collision')
        for i, values in enumerate(maps):
            prefix = f'.jjconflict-{"side" if i % 2 == 0 else "base"}-{i // 2}/'
            expected.update({prefix + path: entry for path, entry in values.items()})
        readme_oid = self.git('hash-object', '--stdin', input=CONFLICT_README).decode().strip()
        expected['JJ-CONFLICT-README'] = ['100644', 'blob', readme_oid]
        stored = self.tree_map(tree)
        require(stored == expected, 'unexplained-conflict-storage')
        return maps, stored

    def logical_entry(self, commit, path, maps):
        entries = [values[path] for values in maps if path in values]
        modes = {entry[0] for entry in entries}
        require(len(modes) == 1 and modes <= {'100644', '100755'}
                and all(entry[1] == 'blob' for entry in entries), 'unsupported-conflict-file-mode')
        payload = self.jj('file', 'show', '-r', commit, '--', path)
        oid = self.git('hash-object', '-w', '--stdin', input=payload).decode().strip()
        return [next(iter(modes)), 'blob', oid]

    def decode_conflict(self, commit, raw, tree, term_headers):
        maps, stored = self.conflict_storage(tree, term_headers)
        require(self.jj('log', '-r', commit, '--no-graph', '-T', 'json(conflict)').strip() == b'true',
                'conflict-tree-reader-mismatch')
        listed = self.jj('file', 'list', '-r', commit).decode().splitlines()
        require(len(listed) == len(set(listed)), 'duplicate-logical-path')
        conflicts = conflict_paths(self.jj('resolve', '--list', '-r', commit).decode())
        union = set().union(*(set(values) for values in maps))
        require(set(conflicts) <= set(listed) <= union, 'unexplained-logical-path')
        logical = {path: self.logical_entry(commit, path, maps) for path in listed}
        # Missing logical paths must be deletions represented in the terms.
        require(all(any(path not in values for values in maps) for path in union - set(listed)),
                'unexplained-logical-deletion')
        return {'tree': self.make_tree(logical), 'conflicts': conflicts, 'commit': commit,
                'raw_tree': tree, 'header_sha256': digest(raw), 'terms': term_headers[0],
                'stored_entries': stored, 'logical_entries': logical, 'operation': self.op}

    def prediction(self, base, tip, target):
        result = self.observe(['git', 'merge-tree', '--write-tree', '--merge-base=' + base, tip, target],
                              allowed=tuple(range(256)))
        first = result.stdout.splitlines()[0].decode() if result.stdout else ''
        valid = result.returncode in (0, 1) and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', first)
        if valid:
            valid = self.git('cat-file', '-t', first).strip() == b'tree'
        return result, first if valid else None

    def paths(self, before, after):
        return [p for p in self.git('diff', '--name-only', '-z', before, after).decode().split('\0') if p]

    def patch(self, before, after):
        return self.git('diff', '--no-ext-diff', '--no-textconv', '--binary', '--find-renames', before, after)

    def commit_info(self, oid, op=None):
        return json.loads(self.jj('log', '-r', oid, '--no-graph', '-T', 'json(self)', op=op))

    def correspondence(self, post):
        old = self.git('rev-list', '--reverse', '--topo-order', self.pre['PRE_BASE'] + '..' + self.pre['PRE_TIP']).decode().splitlines()
        new = self.git('rev-list', '--reverse', '--topo-order', self.pre['NEW_TARGET'] + '..' + post).decode().splitlines()
        old_info = {oid: self.commit_info(oid, self.pre['JJ_PRE_OP_ID']) for oid in old}
        new_info = {oid: self.commit_info(oid) for oid in new}
        by_change = {}
        for oid, info in new_info.items():
            by_change.setdefault(info['change_id'], []).append(oid)
        pairs = {oid: by_change[info['change_id']][0] for oid, info in old_info.items()
                 if len(by_change.get(info['change_id'], [])) == 1}
        problems = []
        if len(pairs) != len(old) or set(pairs.values()) != set(new) or len(set(pairs.values())) != len(old):
            problems.append('non-bijective-change-correspondence')
        rows = [self.change_correspondence(oid, replacement, old_info[oid], new_info[replacement], pairs)
                for oid, replacement in pairs.items()]
        problems.extend(row['old'] + ':' + reason for row in rows for reason in row['problems'])
        return {'old_population': old, 'new_population': new, 'pairs': rows, 'problems': problems}

    def parent_correspondence(self, before, after, pairs):
        expected = ([pairs.get(p, p) for p in before['parents']]
                    if any(p in pairs for p in before['parents']) else [self.pre['NEW_TARGET']])
        reduced = [p for p in expected if not any(p != q and self.observe(
            ['git', 'merge-base', '--is-ancestor', p, q], allowed=(0, 1)).returncode == 0 for q in expected)]
        return {'old_parents': before['parents'], 'new_parents': after['parents'],
                'expected_parents': expected, 'reduced_parents': reduced}

    def change_residual(self, oid, before, after, decoded):
        old_base = self.parent_basis(before['parents'])
        new_base = self.parent_basis(after['parents'])
        row = {'old_parent_basis': old_base, 'new_parent_basis': new_base, 'problems': []}
        if not old_base or not new_base:
            row['problems'].append('unproven-parent-basis')
            return row
        prediction, tree = self.prediction(old_base, oid, new_base)
        residual = self.paths(tree, decoded['tree']) if tree else []
        row.update(prediction_status=prediction.returncode, predicted_tree=tree, residual_paths=residual)
        if tree is None or not set(residual) <= set(decoded['conflicts']):
            row['problems'].append('unexplained-change-residual')
        return row

    def change_correspondence(self, oid, replacement, before, after, pairs):
        decoded = self.decode(replacement)
        row = self.change_residual(oid, before, after, decoded)
        row.update(old=oid, new=replacement, change_id=before['change_id'])
        row.update(self.parent_correspondence(before, after, pairs))
        if before['description'] != after['description'] or before['author'] != after['author']:
            row['problems'].append('authored-metadata-changed')
        if after['parents'] not in (row['expected_parents'], row['reduced_parents']):
            row['problems'].append('parent-correspondence-changed')
        # Inherited unresolved conflicts do not prove this change's own patch.
        own_paths = set().union(*(set(self.paths(parent, oid)) for parent in before['parents']))
        if not set(decoded['conflicts']) <= own_paths:
            row['problems'].append('inherited-unresolved-conflict')
        return row

    def parent_basis(self, parents):
        if not parents:
            return None
        merged = parents[0]
        for parent in parents[1:]:
            merged = self.merge_parent_basis(merged, parent)
        return merged

    def merge_parent_basis(self, left, right):
        if left is None:
            return None
        result = self.observe(['git', 'merge-tree', '--write-tree', left, right], allowed=tuple(range(256)))
        if result.returncode != 0:
            return None  # unresolved virtual merge basis is not an aggregate-only pass
        tree = result.stdout.splitlines()[0].decode()
        require(self.git('cat-file', '-t', tree).strip() == b'tree', 'invalid-parent-basis-tree')
        # Object-only representation of the proven merge basis: no ref/index/WC
        # changes. Preserve parents for subsequent ort ancestry calculation.
        return self.git('-c', 'user.name=Verified rebase', '-c', 'user.email=verified-rebase@invalid',
                        '-c', 'commit.gpgsign=false', 'commit-tree', tree,
                        '-p', left, '-p', right, input=b'Virtual parent basis\n').decode().strip()

    def validate_conflicts(self, post, decoded):
        directory = self.bundle / 'conflict-artifacts'
        mapping = read(directory / 'index.json')
        paths = (directory / 'files.txt').read_text().splitlines()
        require(paths == decoded['conflicts'] and paths == [item['path'] for item in mapping],
                'conflict-path-association-mismatch')
        require(len({item['artifact'] for item in mapping}) == len(paths), 'conflict-artifact-collision')
        expected_names = {'index.json', 'files.txt', 'jj-resolve-list-raw.txt',
                          'jj-resolve-list.stderr', 'jj-resolve-list.status'}
        expected_names.update(f'{i}.{suffix}' for i in range(len(mapping))
                              for suffix in ('conflict', 'stderr', 'status'))
        require({p.name for p in directory.iterdir()} == expected_names, 'unassociated-conflict-artifact')
        raw = self.observe(['jj', '--ignore-working-copy', '--no-pager', '--color=never',
                            '--at-operation', self.op, 'resolve', '--list', '-r', post], allowed=(0, 2))
        require((directory / 'jj-resolve-list-raw.txt').read_bytes() == raw.stdout
                and (directory / 'jj-resolve-list.stderr').read_bytes() == raw.stderr
                and (directory / 'jj-resolve-list.status').read_text() == str(raw.returncode) + '\n',
                'conflict-list-source-mismatch')
        for index, item in enumerate(mapping):
            require(item['artifact'] == f'{index}.conflict', 'conflict-artifact-name-mismatch')
            payload = self.jj('file', 'show', '-r', post, '--', item['path'])
            require((directory / f'{index}.status').read_text() == '0\n'
                    and (directory / f'{index}.stderr').read_bytes() == b'', 'conflict-payload-status-mismatch')
            require(payload == (directory / item['artifact']).read_bytes()
                    and digest(payload) == item['sha256'], 'conflict-artifact-content-mismatch')

    def parent(self, path, target):
        if path is None:
            return None
        parent = Path(path).resolve(strict=True)
        require(parent != self.bundle, 'parent-bundle-is-self')
        result = read(parent / 'result.json')
        refs = read(parent / 'refs.json')
        require(result['execution'] == 'COMPLETE' and result['mechanical'] != 'DIRTY-UNPROVENANCED',
                'parent-not-complete')
        require(result['owner'] == read(parent / 'owner.json') and result['owner']['bundle'] == str(parent),
                'parent-owner-mismatch')
        require(evidence_hashes(parent) == result['evidence_hashes'], 'parent-evidence-changed')
        require(result['POST_TIP'] == refs['POST_TIP'], 'parent-refs-mismatch')
        self.emit('parent-delta.patch', (parent / 'branch-actual.patch').read_bytes())
        ok = refs['POST_TIP'] == target
        self.emit('summary.md.fragment', 'parent-pointer-check: ' + ('PASS' if ok else 'FAIL') + '\n')
        return {'bundle': str(parent), 'result_sha256': digest((parent / 'result.json').read_bytes()),
                'POST_TIP': refs['POST_TIP'], 'pointer_matches': ok,
                'branch_actual_sha256': digest((parent / 'branch-actual.patch').read_bytes())}

    def assemble(self, parent_bundle):
        pre = self.pre
        post = self.git('rev-parse', self.a.owner['branch']).decode().strip()
        predicted, tree = self.prediction(pre['PRE_BASE'], pre['PRE_TIP'], pre['NEW_TARGET'])
        self.emit('merge-tree.out', predicted.stdout)
        self.emit('merge-tree.err', predicted.stderr)
        self.emit('merge-tree.status', str(predicted.returncode) + '\n')
        require(tree is not None, 'merge-tree-failed')
        decoded = self.decode(post)
        self.validate_conflicts(post, decoded)
        delta = 'main-delta.patch' if self.a.owner['target'] == 'origin/main' else 'target-delta.patch'
        patches = {delta: self.patch(pre['PRE_BASE'], pre['NEW_TARGET']),
                   'branch-intended.patch': self.patch(pre['PRE_BASE'], pre['PRE_TIP']),
                   'branch-actual.patch': self.patch(pre['NEW_TARGET'], post),
                   'residual-storage.patch': self.patch(tree, post),
                   'residual.patch': self.patch(tree, decoded['tree'])}
        for name, payload in patches.items():
            self.emit(name, payload)
        correspondence = self.correspondence(post)
        ranges = [pre['PRE_BASE'] + '..' + pre['PRE_TIP'], pre['NEW_TARGET'] + '..' + post]
        raw_range = self.git('range-diff', '--no-color', *ranges) if any(
            correspondence[key] for key in ('old_population', 'new_population')) else b''
        self.emit('range-diff.txt', raw_range)
        self.emit('correspondence.json', encode(correspondence))
        self.emit('logical-trees.json', encode(self.logical))
        residual = sorted(set(self.paths(tree, decoded['tree'])))
        parent = self.parent(parent_bundle, pre['NEW_TARGET'])
        problems = list(correspondence['problems'])
        if not set(residual) <= set(decoded['conflicts']):
            problems.append('unexplained-aggregate-residual')
        if parent and not parent['pointer_matches']:
            problems.append('parent-pointer-mismatch')
        verdict = 'DIRTY-UNPROVENANCED' if problems else ('DIRTY-EXPLAINED' if residual or decoded['conflicts'] else 'CLEAN')
        decision = {'verdict': verdict, 'residual_paths': residual, 'conflict_paths': decoded['conflicts'],
                    'problems': problems, 'parent': parent}
        self.emit('mechanics.json', encode(decision))
        change = self.commit_info(post)['change_id']
        refs = {'branch': self.a.owner['branch'], 'target': self.a.owner['target'], **pre,
                'POST_TIP': post, 'POST_CHANGE_ID': change, 'PREDICTED_TREE': tree,
                'LOGICAL_POST_TREE': decoded['tree'], 'POST_OP_ID': self.op,
                'timestamp': datetime.now(timezone.utc).isoformat(), 'verdict': verdict,
                'owner_id': self.a.owner['owner_id'], 'attempt_id': self.a.owner['attempt_id']}
        if parent:
            refs['parent_bundle'] = parent
        self.emit('refs.json', encode(refs))
        self.emit('jj-pre-op-id.txt', pre['JJ_PRE_OP_ID'] + '\n')
        # Both views are operation-pinned, even if assembly follows cleanup.
        self.emit('jj-op-log-before.txt', self.jj('op', 'log', '--limit', '20', '--no-graph', '-T', 'json(self) ++ "\\n"', op=read(self.bundle / 'anchor.json')['checkpoint']['op']))
        self.emit('jj-op-log-after.txt', self.jj('op', 'log', '--limit', '20', '--no-graph', '-T', 'json(self) ++ "\\n"'))
        rename = any(b'rename from ' in p for p in patches.values())
        summary = 'Verified rebase\n' + '\n'.join(f'{k}: {v}' for k, v in refs.items()) + '\n'
        summary += f'rename-present: {str(rename).lower()}\n'
        summary += ''.join(f'{name} hunks: {len(re.findall(rb"^@@ ", payload, re.M))}\n' for name, payload in patches.items())
        if parent:
            summary += (self.bundle / 'summary.md.fragment').read_text()
        summary += 'Mechanical provenance only; unresolved conflicts require semantic review.\n'
        summary += 'Execution is finalized in result.json; sync/tests/review/push remain caller-owned.\n'
        summary += 'Rollback (requires caller authority): ' + shlex.quote(str(self.bundle / 'rollback.sh')) + '\n'
        self.emit('summary.md', summary)
        argv = ['python3', str(Path(__file__).resolve()), 'rollback', '--bundle', str(self.bundle),
                '--owner-id', self.a.owner['owner_id'], '--attempt-id', self.a.owner['attempt_id']]
        self.emit('rollback.sh', '#!/bin/bash\nset -euo pipefail\nexec ' + shlex.join(argv) + '\n')
        (self.bundle / 'rollback.sh').chmod(0o700)
        return decision


def conflict_paths(raw):
    paths = []
    for row in raw.splitlines():
        if not row:
            continue
        match = re.fullmatch(r'([A-Za-z0-9._/-]+)\s+([2-9]|[1-9][0-9]+)-sided conflict'
                             r'(?: including ([1-9][0-9]*) (deletion|deletions))?', row)
        require(match is not None, 'unsupported-jj-resolve-list-row')
        require(match[3] is None or (int(match[3]) < int(match[2])
                and match[4] == ('deletion' if match[3] == '1' else 'deletions')),
                'unsupported-jj-deletion-count')
        path = match[1]
        require(not path.startswith('/') and all(p not in ('', '.', '..') for p in path.split('/')),
                'unsupported-jj-resolve-list-path')
        require(path not in paths, 'duplicate-jj-resolve-list-path')
        paths.append(path)
    return paths


def ref_map(text):
    return dict(line.split(' ', 1) for line in text.splitlines())


def ref_text(refs):
    return '\n'.join(f'{name} {oid}' for name, oid in sorted(refs.items()))


def operation_exports(repo, op):
    """Read Git-exported bookmarks/tags from an immutable jj operation."""
    refs = {}
    for kind in ('bookmark', 'tag'):
        raw = jj(repo, '--at-operation', op, kind, 'list', '--all-remotes',
                 '-T', 'json(self) ++ "\\n"')
        for line in raw.splitlines():
            ref = json.loads(line)
            remote = ref.get('remote')
            if remote is None:
                continue  # local jj refs need not have been exported to Git
            target = ref['target']
            require(len(target) <= 1, 'conflicted-exported-ref')
            if not target or target[0] is None:
                continue
            if kind == 'tag':
                if remote != 'git':
                    continue
                name = 'refs/tags/' + ref['name']
            elif remote == 'git':
                name = 'refs/heads/' + ref['name']
            else:
                name = 'refs/remotes/' + remote + '/' + ref['name']
            refs[name] = target[0]
    return refs


def operation_commits(repo, op):
    return set(jj(repo, '--at-operation', op, 'log', '-r', 'all()', '--no-graph',
                  '-T', 'commit_id ++ "\\n"').splitlines())


def restore_refs(before, after):
    # jj retains Git GC roots for this attempt's rebased commits on op restore.
    # Preserve exactly the pinned post-state keep refs, not arbitrary future ones.
    baseline = [line for line in before.splitlines() if not line.startswith('refs/jj/keep/')]
    retained = [line for line in after.splitlines() if line.startswith('refs/jj/keep/')]
    return '\n'.join(sorted(baseline + retained))


def rollback_evidence_hashes(bundle):
    return {p.name: digest(p.read_bytes()) for p in sorted(bundle.iterdir())
            if p.is_file() and (p.name in ('rollback-command.json', 'rollback-observed.json')
                or re.fullmatch(r'rollback-operation-[0-9a-f]+\.json', p.name))}


def evidence_hashes(bundle):
    paths = sorted(bundle.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'symlink-evidence')
    excluded = {'result.json', 'state.json', 'rollback-result.json'}
    state = read(bundle / 'state.json')
    if 'rollback' in state['completed'] or (state['inflight'] or {}).get('label') == 'rollback':
        excluded.update(rollback_evidence_hashes(bundle))
    return {str(p.relative_to(bundle)): digest(p.read_bytes()) for p in paths
            if p.is_file() and str(p.relative_to(bundle)) not in excluded}


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['allocate', 'inspect', 'check', 'anchor', 'fetch', 'rebase', 'abandon',
                                         'finish', 'release', 'rollback', 'capture-conflicts', 'assemble'])
    parser.add_argument('--owner-id', required=True)
    parser.add_argument('--attempt-id', required=True)
    for name in ('bundle', 'repo', 'planning', 'branch', 'target', 'source', 'revision', 'mechanical', 'execution', 'reason', 'parent-bundle'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    if args.action == 'allocate':
        return allocate(args.repo, args.planning, args.owner_id, args.attempt_id, args.branch, args.target, args.source)
    attempt = Attempt(args.bundle, args.owner_id, args.attempt_id)
    if args.action in ('anchor', 'fetch', 'rebase', 'abandon'):
        return attempt.mutate(args.action, args.revision)
    if args.action == 'assemble':
        return attempt.assemble(args.parent_bundle)
    if args.action == 'finish':
        return attempt.finish(args.mechanical, args.execution, args.reason or '')
    return getattr(attempt, args.action.replace('-', '_'))()


if __name__ == '__main__':
    try:
        print(json.dumps(cli(), sort_keys=True))
    except (Blocked, OSError, ValueError, KeyError, TypeError) as error:
        print(f'BLOCKED:{error}', file=sys.stderr)
        sys.exit(2)
