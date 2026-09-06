"""Run: python3 -m unittest discover -s evals/verified-rebase-substrate-isolation -v.

All mutations target disposable Git/jj repositories. Pipes are deterministic
barriers, not sleeps. These test the actual helper, not a simulated lock.
"""
import base64
import importlib.util
import json
import multiprocessing
import os
import re
import shlex
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

HELPER = Path(__file__).resolve().parents[2] / 'tools/verified_rebase.py'
spec = importlib.util.spec_from_file_location('verified_rebase', HELPER)
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)
CTX = multiprocessing.get_context('fork')


def capture(repo, args, **kwargs):
    result = subprocess.run(args, cwd=repo, capture_output=True, **kwargs)
    if os.environ.get('VR_TEST_ARTIFACT_ROOT'):
        records = Path(os.environ['VR_TEST_ARTIFACT_ROOT']) / 'commands'
        records.mkdir(parents=True, exist_ok=True)
        def data(value):
            return base64.b64encode(value.encode() if isinstance(value, str) else value).decode()
        (records / (str(uuid.uuid4()) + '.json')).write_text(json.dumps({
            'cwd': str(repo), 'args': list(args), 'returncode': result.returncode,
            'environment': {k: kwargs.get('env', os.environ).get(k) for k in
                ('PATH', 'HOME', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_NOSYSTEM', 'JJ_CONFIG',
                 'VR_HELPER', 'repo_root', 'planning_dir', 'OWNER_ID', 'ATTEMPT_ID', 'BRANCH', 'TARGET', 'SOURCE', 'PARENT_BUNDLE')},
            'stdin_base64': data(kwargs['input']) if kwargs.get('input') is not None else None,
            'stdout_base64': data(result.stdout), 'stderr_base64': data(result.stderr)}))
    return result


_original_invoke = vr.invoke

def helper_invoke(repo, args, **kwargs):
    result = _original_invoke(repo, args, **kwargs)
    if os.environ.get('VR_TEST_ARTIFACT_ROOT'):
        records = Path(os.environ['VR_TEST_ARTIFACT_ROOT']) / 'commands'
        records.mkdir(parents=True, exist_ok=True)
        (records / (str(uuid.uuid4()) + '.json')).write_text(json.dumps({
            'cwd': str(repo), 'args': list(args), 'returncode': result.returncode,
            'stdout_base64': base64.b64encode(result.stdout).decode(),
            'stderr_base64': base64.b64encode(result.stderr).decode()}))
    return result

vr.invoke = helper_invoke


def run(repo, *args, allowed=(0,)):
    result = capture(repo, args, text=True)
    if result.returncode not in allowed:
        raise AssertionError(f'{args}: {result.returncode}: {result.stderr}')
    return result.stdout.strip()


def git(repo, *args, **kw):
    return run(repo, 'git', *args, **kw)


def make_repo(root, name='repo', branch='feature', conflict=False):
    repo = root / name
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    git(repo, 'config', 'user.name', 'Fixture')
    git(repo, 'config', 'commit.gpgsign', 'false')
    (repo / 'file').write_text('base\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'base')
    git(repo, 'checkout', '-b', branch)
    (repo / ('file' if conflict else 'feature')).write_text('feature\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'feature')
    git(repo, 'checkout', 'main')
    (repo / ('file' if conflict else 'target')).write_text('target\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'target')
    git(repo, 'clone', '--bare', '--no-hardlinks', str(repo), str(root / (name + '-origin.git')))
    git(repo, 'remote', 'add', 'origin', str(root / (name + '-origin.git')))
    run(repo, 'jj', 'git', 'init', '--colocate')
    return repo


def acquired_worker(repo, planning, owner, attempt, pipe, crash_at=None):
    original = vr.write

    def barrier_write(path, value, exclusive=False):
        if crash_at == 'before-state' and path.name == 'state.json':
            pipe.send('reserved-without-state')
            pipe.recv()
            os._exit(19)
        original(path, value, exclusive)

    vr.write = barrier_write
    bundle = vr.allocate(repo, planning, owner, attempt, 'feature', 'main')
    pipe.send(bundle)
    pipe.recv()  # hold a complete owner across process suspension


class OwnershipRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.preserve_and_clean)
        self.planning = self.root / 'planning'
        self.planning.mkdir()
        self.repo = make_repo(self.root)

    def preserve_and_clean(self):
        if os.environ.get('VR_TEST_ARTIFACT_ROOT'):
            destination = Path(os.environ['VR_TEST_ARTIFACT_ROOT']) / str(uuid.uuid4())
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.root, destination, symlinks=True)
            (destination / 'fixture-origin.json').write_text(json.dumps({
                'original_root': str(self.root), 'test': self.id()}))
        self.tmp.cleanup()

    def attempt(self, repo=None, branch='feature', target='main', source=None):
        owner, attempt = str(uuid.uuid4()), str(uuid.uuid4())
        bundle = vr.allocate(repo or self.repo, self.planning, owner, attempt, branch, target, source)
        return vr.Attempt(bundle, owner, attempt)

    def rebase(self, attempt):
        attempt.check()
        attempt.mutate('anchor')
        attempt.mutate('fetch')
        pre = git(attempt.repo, 'rev-parse', attempt.owner['branch'])
        base = git(attempt.repo, 'merge-base', attempt.owner['branch'], attempt.owner['target'])
        target = git(attempt.repo, 'rev-parse', attempt.owner['target'])
        prediction = git(attempt.repo, 'merge-tree', '--write-tree', f'--merge-base={base}', pre, target, allowed=(0, 1))
        attempt.mutate('rebase')
        post = git(attempt.repo, 'rev-parse', attempt.owner['branch'])
        return {'pre': pre, 'base': base, 'target': target, 'post': post,
                'prediction': prediction.splitlines()[0]}

    def assemble(self, a, parent=None):
        if not (a.bundle / 'conflict-artifacts').exists():
            a.capture_conflicts()
        return a.assemble(parent)

    def terminal(self, a):
        self.assemble(a)
        a.finish()
        a.release()

    def test_checked_in_workflow_shell_normal_and_conflict(self):
        workflow = (HELPER.parents[1] / 'workflows/verified-rebase.md').read_text()
        for conflict in (False, True):
            repo = make_repo(self.root, f'workflow-{conflict}', conflict=conflict)
            before_remote = git(repo, 'ls-remote', 'origin')
            owner, attempt = str(uuid.uuid4()), str(uuid.uuid4())
            env = dict(os.environ, VR_HELPER=str(HELPER), repo_root=str(repo),
                       planning_dir=str(self.planning), OWNER_ID=owner, ATTEMPT_ID=attempt,
                       BRANCH='feature', TARGET='main')
            phases = []
            for phase in range(1, 11):
                section = workflow.split(f'### {phase}. ', 1)[1].split('\n### ', 1)[0]
                block = re.search(r'```bash\n(.*?)```', section, re.S)
                if block:
                    phases.append(block[1])
            script = '\n'.join(phases)
            result = capture(repo, ['bash', '-c', script], env=env, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            bundle = self.planning / owner / attempt
            a = vr.Attempt(bundle, owner, attempt)
            self.assertEqual('1' if conflict else '0', (bundle / 'merge-tree.status').read_text().strip())
            self.assertEqual('file' if conflict else '', (bundle / 'conflict-artifacts/files.txt').read_text().strip())
            if conflict:
                expected = capture(repo, ['jj', '--ignore-working-copy', '--no-pager', '--color=never',
                    '--at-operation', vr.read(bundle / 'state.json')['checkpoint']['op'],
                    'file', 'show', '-r', git(repo, 'rev-parse', 'feature'), '--', 'file']).stdout
                self.assertIn(b'-base', expected)
                self.assertIn(b'+target', expected)
                self.assertIn(b'feature', expected)
                self.assert_conflict_payloads(bundle, {'file': expected})
                # Exercise the documented text-conflict algebra on the durable
                # producer output, not a mechanical label supplied to finish().
                predicted = (bundle / 'merge-tree.out').read_text().splitlines()[0]
                post = git(repo, 'rev-parse', 'feature')
                logical = vr.read(bundle / 'refs.json')['LOGICAL_POST_TREE']
                residual_paths = set(git(repo, 'diff', '--name-only', predicted, logical).splitlines())
                conflicts = set((bundle / 'conflict-artifacts/files.txt').read_text().splitlines())
                self.assertLessEqual(residual_paths, conflicts)
                self.assertIn(' < ', (bundle / 'range-diff.txt').read_text())
                self.assertEqual([], vr.read(bundle / 'correspondence.json')['problems'])
                self.assertEqual('DIRTY-EXPLAINED', vr.read(bundle / 'result.json')['mechanical'])
            if not conflict:
                self.assertEqual(b'', (bundle / 'residual.patch').read_bytes())
                self.assertIn(' = ', (bundle / 'range-diff.txt').read_text())
            self.assert_complete_bundle(a, 'DIRTY-EXPLAINED' if conflict else 'CLEAN')
            self.assertEqual(before_remote, git(repo, 'ls-remote', 'origin'))
            rollback = capture(self.root, [str(bundle / 'rollback.sh')], text=True)
            self.assertEqual(0, rollback.returncode, rollback.stderr)
            self.assertEqual(a.owner['branch'], 'feature')
            self.assertEqual(before_remote, git(repo, 'ls-remote', 'origin'))
            self.assertFalse((repo / '.tmp').exists())

    def assert_complete_bundle(self, a, mechanical):
        result = vr.read(a.bundle / 'result.json')
        refs = vr.read(a.bundle / 'refs.json')
        self.assertEqual(mechanical, result['mechanical'])
        self.assertEqual(mechanical, refs['verdict'])
        self.assertEqual(git(a.repo, 'rev-parse', a.owner['branch']), refs['POST_TIP'])
        self.assertEqual(result['POST_TIP'], refs['POST_TIP'])
        self.assertEqual(result['checkpoint']['op'], refs['POST_OP_ID'])
        self.assertFalse(result['push_eligible'])
        required = ['summary.md', 'refs.json', 'branch-intended.patch', 'branch-actual.patch',
                    'residual.patch', 'residual-storage.patch', 'range-diff.txt', 'correspondence.json',
                    'logical-trees.json', 'mechanics.json', 'rollback.sh', 'jj-op-log-before.txt',
                    'jj-op-log-after.txt', 'jj-pre-op-id.txt', 'conflict-artifacts/index.json']
        for name in required:
            self.assertTrue((a.bundle / name).is_file(), name)
        for name, expected in result['evidence_hashes'].items():
            self.assertEqual(expected, vr.digest((a.bundle / name).read_bytes()), name)
        self.assertEqual(result['evidence_hashes'], vr.evidence_hashes(a.bundle))
        self.assertIn(refs['POST_CHANGE_ID'], (a.bundle / 'summary.md').read_text())

    def assert_conflict_payloads(self, bundle, expected):
        directory = bundle / 'conflict-artifacts'
        mapping = vr.read(directory / 'index.json')
        self.assertEqual(set(expected), {item['path'] for item in mapping})
        self.assertEqual(len(expected), len({item['artifact'] for item in mapping}))
        self.assertEqual(set(expected), set((directory / 'files.txt').read_text().splitlines()))
        for item in mapping:
            actual = (directory / item['artifact']).read_bytes()
            self.assertEqual(expected[item['path']], actual)
            self.assertEqual(item['sha256'], vr.digest(actual))

    def test_multiple_conflict_paths_preserve_payloads_and_associations(self):
        repo = make_conflict_population(self.root, ('a/b', 'a_b', 'a__b'))
        before_remote = git(repo, 'ls-remote', 'origin')
        a = self.attempt(repo)
        self.rebase(a)
        a.capture_conflicts()
        op = vr.read(a.bundle / 'state.json')['checkpoint']['op']
        post = git(repo, 'rev-parse', 'feature')
        expected = {}
        for path in ('a/b', 'a_b', 'a__b'):
            expected[path] = capture(repo, ['jj', '--ignore-working-copy', '--no-pager', '--color=never',
                '--at-operation', op, 'file', 'show', '-r', post, '--', path]).stdout
            for side in ('base', 'feature', 'target'):
                self.assertIn((side + ':' + path).encode(), expected[path])
        self.assert_conflict_payloads(a.bundle, expected)
        self.assertEqual(before_remote, git(repo, 'ls-remote', 'origin'))
        with self.assertRaises(FileExistsError):
            a.capture_conflicts()  # no overwrite after partial or complete capture
        for index, payload in enumerate((b'', b'not the conflict')):
            altered = self.root / ('bundle-copy-' + str(index))
            shutil.copytree(a.bundle, altered)
            item = vr.read(altered / 'conflict-artifacts/index.json')[0]
            (altered / 'conflict-artifacts' / item['artifact']).write_bytes(payload)
            with self.assertRaises(AssertionError):
                self.assert_conflict_payloads(altered, expected)
        self.assert_conflict_payloads(a.bundle, expected)

    def test_remote_interval_oracle_detects_publication(self):
        before = git(self.repo, 'ls-remote', 'origin')
        a = self.attempt()
        self.rebase(a)
        self.terminal(a)
        self.assertEqual(before, git(self.repo, 'ls-remote', 'origin'))
        # This intentional negative uses only the disposable local bare remote.
        git(self.repo, 'push', 'origin', 'feature:refs/heads/published')
        with self.assertRaises(AssertionError):
            self.assertEqual(before, git(self.repo, 'ls-remote', 'origin'))

    def test_conflict_row_adapter_refuses_duplicates_and_partial_rows(self):
        self.assertEqual(['a/b', 'a_b', 'a__b'], vr.conflict_paths(
            'a/b    2-sided conflict\na_b\t2-sided conflict\na__b    3-sided conflict\n'))
        for raw in ('file 2-sided conflict\nfile 2-sided conflict\n',
                    'file message that is not a conflict\n', '../file 2-sided conflict\n'):
            with self.assertRaises(vr.Blocked):
                vr.conflict_paths(raw)

    def test_terminal_evidence_or_foreign_file_after_finish_blocks_release(self):
        for failure in ('evidence', 'foreign'):
            repo = make_repo(self.root, 'late-' + failure)
            a = self.attempt(repo)
            self.rebase(a)
            self.assemble(a)
            a.finish('CLEAN', 'COMPLETE')
            path = a.bundle / 'summary.md' if failure == 'evidence' else repo / 'foreign'
            path.write_text('late-writer')
            with self.assertRaises(vr.Blocked):
                a.release()
            with self.assertRaisesRegex(vr.Blocked, 'substrate-reserved'):
                self.attempt(repo)
            self.assertEqual('late-writer', path.read_text())

    def test_partial_owner_record_blocks_and_preserves_bytes(self):
        a = self.attempt()
        record = vr.resources(a.identity)[0] / 'reservation.json'
        record.write_bytes(b'{partial')
        before = vr.snapshot(a.identity)
        with self.assertRaises(ValueError):
            self.attempt()
        with self.assertRaises(ValueError):
            a.release()
        self.assertEqual(b'{partial', record.read_bytes())
        self.assertEqual(before, vr.snapshot(a.identity))

    def test_cleanup_rejects_foreign_or_current_commit(self):
        a = self.attempt()
        refs = self.rebase(a)
        before = vr.snapshot(a.identity)
        for revision in (refs['post'], refs['target']):
            with self.assertRaisesRegex(vr.Blocked, 'cleanup-not-owned-pre-rebase-commit'):
                a.mutate('abandon', revision)
        self.assertEqual(before, vr.snapshot(a.identity))

    def test_independent_substrates_rebase_simultaneously(self):
        peers = []
        for index in range(2):
            repo = make_repo(self.root, f'parallel-{index}')
            a = self.attempt(repo)
            parent, child = CTX.Pipe()
            process = CTX.Process(target=parallel_worker, args=(a, child))
            process.start()
            self.addCleanup(lambda p=process: p.kill() if p.is_alive() else None)
            peers.append((process, parent, a))
        for _, pipe, _ in peers:
            self.assertTrue(pipe.poll(20))
            self.assertEqual('ready', pipe.recv())
        for _, pipe, _ in peers:
            pipe.send('rebase')
        for process, pipe, a in peers:
            self.assertTrue(pipe.poll(20))
            self.assertEqual('COMPLETE', pipe.recv())
            process.join(10)
            self.assertEqual(0, process.exitcode)
            self.assertFalse(json.loads((a.bundle / 'result.json').read_text())['push_eligible'])

    def test_normal_mechanics_and_current_rollback(self):
        a = self.attempt()
        refs = self.rebase(a)
        self.assertEqual('', git(self.repo, 'diff', refs['prediction'], refs['post'] + '^{tree}'))
        self.assertIn(' = ', git(self.repo, 'range-diff', f'{refs["base"]}..{refs["pre"]}', f'{refs["target"]}..{refs["post"]}'))
        self.terminal(a)
        a.rollback()
        self.assertEqual(refs['pre'], git(self.repo, 'rev-parse', 'feature'))
        state = a.rollback()
        self.assertEqual(1, state['completed'].count('rollback'))
        self.assertEqual(refs['pre'], git(self.repo, 'rev-parse', a.owner['anchor']))
        self.assertFalse((self.repo / '.tmp').exists())

    def test_overlap_suspension_and_different_branch_share_reservation(self):
        owner, attempt = str(uuid.uuid4()), str(uuid.uuid4())
        parent, child = CTX.Pipe()
        process = CTX.Process(target=acquired_worker, args=(self.repo, self.planning, owner, attempt, child))
        process.start()
        self.addCleanup(lambda: process.kill() if process.is_alive() else None)
        self.assertTrue(parent.poll(20), 'owner never reached barrier')
        bundle = parent.recv()
        before = vr.snapshot(vr.substrate(self.repo))
        alias = self.root / 'alias'
        alias.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(vr.Blocked, 'substrate-reserved'):
            self.attempt(alias, branch='main')
        self.assertEqual(before, vr.snapshot(vr.substrate(self.repo)))
        parent.send('end-turn')
        process.join(10)
        self.assertEqual(0, process.exitcode)
        # Exit/transport success still does not release operation ownership.
        with self.assertRaisesRegex(vr.Blocked, 'substrate-reserved'):
            self.attempt()
        a = vr.Attempt(bundle, owner, attempt)
        self.rebase(a)
        self.terminal(a)

    def test_interruption_before_state_preserves_unknown_reservation(self):
        owner, attempt = str(uuid.uuid4()), str(uuid.uuid4())
        parent, child = CTX.Pipe()
        process = CTX.Process(target=acquired_worker, args=(self.repo, self.planning, owner, attempt, child, 'before-state'))
        process.start()
        self.addCleanup(lambda: process.kill() if process.is_alive() else None)
        self.assertTrue(parent.poll(20))
        self.assertEqual('reserved-without-state', parent.recv())
        parent.send('interrupt')
        process.join(10)
        self.assertEqual(19, process.exitcode)
        with self.assertRaisesRegex(vr.Blocked, 'substrate-reserved'):
            self.attempt()
        a = vr.Attempt(self.planning / owner / attempt, owner, attempt)
        with self.assertRaises(FileNotFoundError):
            a.check()

    def test_blocked_preflight_without_ignore_writes_only_external_evidence(self):
        remote = git(self.repo, 'ls-remote', 'origin')
        before = vr.snapshot(vr.substrate(self.repo))
        a = self.attempt(target='absent')
        with self.assertRaises(vr.Blocked):
            vr.git(self.repo, 'rev-parse', '--verify', 'absent')
        a.finish('NOT-RUN', 'BLOCKED', 'target-not-found')
        a.release()
        self.assertEqual(before, vr.snapshot(vr.substrate(self.repo)))
        self.assertEqual('', git(self.repo, 'status', '--porcelain'))
        self.assertFalse((self.repo / '.gitignore').exists())
        self.assertFalse((self.repo / '.tmp').exists())
        self.assertTrue((a.bundle / 'result.json').is_file())
        self.assertEqual(remote, git(self.repo, 'ls-remote', 'origin'))

    def test_planning_inside_checkout_and_slug_collisions(self):
        (self.repo / 'planning').mkdir()
        with self.assertRaisesRegex(vr.Blocked, 'planning-inside-checkout'):
            vr.allocate(self.repo, self.repo / 'planning', str(uuid.uuid4()), str(uuid.uuid4()), 'feature', 'main')
        (self.repo / 'planning').rmdir()
        attempts = []
        for index, branch in enumerate(('a/b', 'a_b', 'a__b')):
            repo = make_repo(self.root, f'independent-{index}', branch)
            a = self.attempt(repo, branch)
            attempts.append(a)
        self.assertEqual(3, len({str(a.bundle) for a in attempts}))
        for a in attempts:
            refs = self.rebase(a)
            self.assertEqual('', git(a.repo, 'diff', refs['prediction'], refs['post']))
            self.terminal(a)

    def test_bundle_collision_never_overwrites(self):
        a = self.attempt()
        before = (a.bundle / 'owner.json').read_bytes()
        with self.assertRaises(FileExistsError):
            vr.allocate(self.repo, self.planning, a.owner['owner_id'], a.owner['attempt_id'], 'main', 'main')
        self.assertEqual(before, (a.bundle / 'owner.json').read_bytes())

    def test_stale_release_cleanup_and_rollback_cannot_touch_successor(self):
        a = self.attempt()
        self.rebase(a)
        self.terminal(a)
        b = self.attempt()
        sentinel = b.bundle / 'foreign'
        sentinel.write_bytes(b'preserve')
        before = vr.snapshot(b.identity)
        for operation in (a.release, a.rollback, a.check):
            with self.assertRaisesRegex(vr.Blocked, 'reservation-owner-or-lifecycle-mismatch'):
                operation()
        with self.assertRaisesRegex(vr.Blocked, 'owner-attempt-mismatch'):
            vr.Attempt(b.bundle, a.owner['owner_id'], a.owner['attempt_id'])
        self.assertEqual(b'preserve', sentinel.read_bytes())
        self.assertEqual(before, vr.snapshot(b.identity))
        b.finish('NOT-RUN', 'BLOCKED', 'fixture')
        b.release()
        with self.assertRaisesRegex(vr.Blocked, 'reservation-owner-or-lifecycle-mismatch'):
            a.rollback()  # even if B made no jj or ref changes

    def test_stale_rollback_rejects_clean_later_operation_and_anchor_replacement(self):
        for mutation in ('operation', 'anchor'):
            repo = make_repo(self.root, mutation)
            a = self.attempt(repo)
            self.rebase(a)
            self.terminal(a)
            if mutation == 'operation':
                run(repo, 'jj', '--ignore-working-copy', 'bookmark', 'create', 'later', '-r', 'main')
            else:
                git(repo, 'update-ref', a.owner['anchor'], 'main')
            before = vr.snapshot(a.identity)
            with self.assertRaisesRegex(vr.Blocked, 'intervening-substrate-operation'):
                a.rollback()
            self.assertEqual(before, vr.snapshot(a.identity))

    def test_foreign_files_preserved_no_snapshot_and_mechanical_not_execution(self):
        a = self.attempt()
        self.rebase(a)
        self.assemble(a)
        before = vr.snapshot(a.identity)
        directory = self.repo / '.tmp/verified-rebase/foreign'
        directory.mkdir(parents=True)
        for index in range(8):
            (directory / str(index)).write_text(f'foreign-{index}')
        with self.assertRaisesRegex(vr.Blocked, 'dirty-working-copy'):
            a.finish('CLEAN', 'COMPLETE')
        result = a.finish('CLEAN', 'BLOCKED', 'concurrent-substrate-mutation')
        a.release()
        self.assertEqual('CLEAN', result['mechanical'])
        self.assertEqual('BLOCKED', result['execution'])
        self.assertFalse(result['push_eligible'])
        self.assertEqual(before, vr.snapshot(a.identity))
        self.assertEqual([f'foreign-{i}' for i in range(8)], [(directory / str(i)).read_text() for i in range(8)])
        with self.assertRaisesRegex(vr.Blocked, 'dirty-working-copy'):
            a.rollback()

    def test_completed_rebase_resume_never_repeats_and_terminal_before_release(self):
        a = self.attempt()
        self.rebase(a)
        resumed = vr.Attempt(a.bundle, a.owner['owner_id'], a.owner['attempt_id'])
        with self.assertRaisesRegex(vr.Blocked, 'command-already-completed'):
            resumed.mutate('rebase')
        self.assemble(a)
        a.finish('CLEAN', 'COMPLETE')
        with self.assertRaisesRegex(vr.Blocked, 'substrate-reserved'):
            self.attempt()
        resumed.release()

    def test_inflight_rebase_cannot_be_retried_or_released(self):
        a = self.attempt()
        a.mutate('anchor')
        a.mutate('fetch')
        parent, child = CTX.Pipe()
        process = CTX.Process(target=interrupted_rebase_worker, args=(a, child))
        process.start()
        self.addCleanup(lambda: process.kill() if process.is_alive() else None)
        self.assertTrue(parent.poll(20))
        self.assertEqual('rebased-before-checkpoint', parent.recv())
        parent.send('interrupt')
        process.join(10)
        self.assertEqual(21, process.exitcode)
        before = vr.snapshot(a.identity)
        for operation in (a.check, a.release, lambda: a.mutate('rebase')):
            with self.assertRaisesRegex(vr.Blocked, 'interrupted-command-needs-recovery'):
                operation()
        with self.assertRaisesRegex(vr.Blocked, 'substrate-reserved'):
            self.attempt()
        self.assertEqual(before, vr.snapshot(a.identity))

    def test_command_return_checkpoint_rejects_foreign_operation_and_ref(self):
        for action in ('anchor', 'fetch', 'rebase', 'rollback'):
            for mutation in ('none', 'operation', 'ref'):
                with self.subTest(action=action, mutation=mutation):
                    repo = make_repo(self.root, action + '-' + mutation)
                    a = self.attempt(repo)
                    if action != 'anchor':
                        a.mutate('anchor')
                    if action in ('rebase', 'rollback'):
                        a.mutate('fetch')
                    if action == 'rollback':
                        a.mutate('rebase')
                        self.terminal(a)
                    checkpoint = vr.read(a.bundle / 'state.json')['checkpoint']
                    parent, child = CTX.Pipe()
                    process = CTX.Process(target=command_boundary_worker, args=(a, action, child))
                    process.start()
                    self.addCleanup(lambda p=process: p.kill() if p.is_alive() else None)
                    self.assertTrue(parent.poll(20))
                    self.assertEqual('command-returned', parent.recv())
                    if mutation == 'operation':
                        run(repo, 'jj', '--ignore-working-copy', 'bookmark', 'create', 'foreign', '-r', 'main')
                    if mutation == 'ref':
                        git(repo, 'update-ref', 'refs/heads/foreign', 'main')
                    foreign = vr.snapshot(a.identity)
                    parent.send('readback')
                    self.assertTrue(parent.poll(20))
                    outcome = parent.recv()
                    process.join(10)
                    self.assertEqual(0, process.exitcode)
                    if mutation == 'none':
                        self.assertEqual('accepted', outcome)
                    else:
                        self.assertIn('blocked', outcome)
                        self.assertEqual(foreign, vr.snapshot(a.identity))
                        self.assertEqual(checkpoint, vr.read(a.bundle / 'state.json')['checkpoint'])
                        self.assertIsNotNone(vr.read(a.bundle / 'state.json')['inflight'])
                        for operation in (a.check, a.release, a.rollback,
                                          lambda: a.finish('CLEAN', 'COMPLETE')):
                            with self.assertRaises(vr.Blocked):
                                operation()
                        self.assertEqual(foreign, vr.snapshot(a.identity))

    def test_stacked_child_exact_parent_pointer_and_scoped_source(self):
        # Add a child before ownership starts; the parent rebase must auto-follow it.
        git(self.repo, 'checkout', '-b', 'child', 'feature')
        (self.repo / 'child-file').write_text('child\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'child')
        git(self.repo, 'checkout', 'main')
        run(self.repo, 'jj', 'git', 'import')
        parent = self.attempt()
        self.rebase(parent)
        self.terminal(parent)
        child = self.attempt(branch='child', target='feature')
        refs = self.rebase(child)
        parent_result = json.loads((parent.bundle / 'result.json').read_text())
        self.assertEqual(parent_result['POST_TIP'], refs['target'])
        self.assertEqual('', git(self.repo, 'diff', refs['prediction'], refs['post']))
        self.assertEqual('child', git(self.repo, 'show', 'child:child-file'))
        self.terminal(child)

        # Rewritten parent with stale parent history; SOURCE excludes the stale parent.
        repo = make_stale_stack(self.root)
        source = git(repo, 'rev-parse', 'feature')
        a = self.attempt(repo, target='parent', source=source)
        a.check()
        a.mutate('anchor')
        a.mutate('fetch')
        state = a.mutate('rebase')
        self.assertEqual(source, state['pre']['SOURCE_COMMIT'])
        self.assertEqual('new', git(repo, 'show', 'feature:parent-file'))
        self.assertEqual('unique', git(repo, 'show', 'feature:unique'))
        pre = state['pre']
        ranges = git(repo, 'range-diff', f'{pre["PRE_BASE"]}..{pre["PRE_TIP"]}', f'{pre["NEW_TARGET"]}..feature')
        self.assertIn(' = ', ranges)
        self.terminal(a)

    def test_conflict_and_noop_mechanics(self):
        repo = make_repo(self.root, 'conflict', conflict=True)
        a = self.attempt(repo)
        self.rebase(a)
        raw = vr.jj(repo, 'resolve', '--list', '-r', 'feature')
        self.assertIn('file', raw)
        self.assertTrue(vr.jj(repo, 'file', 'show', '-r', 'feature', 'file'))
        self.assemble(a)
        a.finish('DIRTY-EXPLAINED', 'COMPLETE')
        a.release()
        a.rollback()
        b = self.attempt()
        self.rebase(b)
        self.terminal(b)
        c = self.attempt()
        refs = self.rebase(c)
        self.assertEqual(refs['pre'], refs['post'])
        self.terminal(c)


def make_conflict_population(root, paths):
    repo = root / 'population'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    git(repo, 'config', 'user.name', 'Fixture')
    git(repo, 'config', 'commit.gpgsign', 'false')
    for path in paths:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text('base:' + path + '\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'base')
    git(repo, 'checkout', '-b', 'feature')
    for path in paths:
        (repo / path).write_text('feature:' + path + '\n')
    git(repo, 'commit', '-am', 'feature')
    git(repo, 'checkout', 'main')
    for path in paths:
        (repo / path).write_text('target:' + path + '\n')
    git(repo, 'commit', '-am', 'target')
    git(repo, 'clone', '--bare', '--no-hardlinks', str(repo), str(root / 'population-origin.git'))
    git(repo, 'remote', 'add', 'origin', str(root / 'population-origin.git'))
    run(repo, 'jj', 'git', 'init', '--colocate')
    return repo


def make_stale_stack(root):
    repo = make_repo(root, 'scoped')
    base = git(repo, 'rev-parse', 'main~1')
    git(repo, 'checkout', '-B', 'parent', base)
    (repo / 'parent-file').write_text('old\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'old parent')
    git(repo, 'checkout', '-B', 'feature')
    (repo / 'unique').write_text('unique\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'unique child')
    git(repo, 'checkout', '-B', 'parent', base)
    (repo / 'parent-file').write_text('new\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'rewritten parent')
    git(repo, 'checkout', 'main')
    run(repo, 'jj', 'git', 'import')
    return repo


def parallel_worker(a, pipe):
    a.mutate('anchor')
    a.mutate('fetch')
    pipe.send('ready')
    pipe.recv()
    a.mutate('rebase')
    a.capture_conflicts()
    a.assemble()
    result = a.finish('CLEAN', 'COMPLETE')
    a.release()
    pipe.send(result['execution'])


def command_boundary_worker(a, action, pipe, revision=None):
    original = vr.invoke
    def barrier(repo, args):
        result = original(repo, args)
        selected = (action == 'anchor' and 'update-ref' in args or
                    action == 'fetch' and args[-2:] == ['git', 'fetch'] or
                    action == 'rebase' and 'rebase' in args or
                    action == 'rollback' and 'restore' in args or
                    action == 'abandon' and 'abandon' in args)
        if selected:
            pipe.send('command-returned')
            pipe.recv()
        return result
    vr.invoke = barrier
    try:
        a.rollback() if action == 'rollback' else a.mutate(action, revision)
        pipe.send('accepted')
    except vr.Blocked as error:
        pipe.send('blocked:' + str(error))


def interrupted_rebase_worker(a, pipe):
    original = vr.invoke

    def barrier_command(repo, args):
        output = original(repo, args)
        if 'rebase' in args:
            pipe.send('rebased-before-checkpoint')
            pipe.recv()
            os._exit(21)
        return output

    vr.invoke = barrier_command
    a.mutate('rebase')


if __name__ == '__main__':
    unittest.main()
