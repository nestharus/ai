"""Run: python3 -m unittest discover -s evals/verified-rebase-substrate-isolation -v.

All mutations target disposable Git/jj repositories. Pipes are deterministic
barriers, not sleeps. These test the actual helper, not a simulated lock.
"""
import importlib.util
import json
import multiprocessing
import os
import re
import shlex
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


def run(repo, *args, allowed=(0,)):
    result = subprocess.run(args, cwd=repo, capture_output=True, text=True)
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
        self.tmp = tempfile.TemporaryDirectory(prefix='infa950-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.planning = self.root / 'planning'
        self.planning.mkdir()
        self.repo = make_repo(self.root)

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

    def terminal(self, a):
        a.finish('CLEAN', 'COMPLETE')
        a.release()

    def test_checked_in_workflow_shell_normal_and_conflict(self):
        workflow = (HELPER.parents[1] / 'workflows/verified-rebase.md').read_text()
        for conflict in (False, True):
            repo = make_repo(self.root, f'workflow-{conflict}', conflict=conflict)
            owner, attempt = str(uuid.uuid4()), str(uuid.uuid4())
            env = dict(os.environ, VR_HELPER=str(HELPER), repo_root=str(repo),
                       planning_dir=str(self.planning), OWNER_ID=owner, ATTEMPT_ID=attempt,
                       BRANCH='feature', TARGET='main')
            phases = []
            for phase in range(1, 8):
                section = workflow.split(f'### {phase}. ', 1)[1].split('\n### ', 1)[0]
                phases.append(re.search(r'```bash\n(.*?)```', section, re.S)[1])
            script = '\n'.join(phases)
            result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            bundle = self.planning / owner / attempt
            a = vr.Attempt(bundle, owner, attempt)
            self.assertEqual('1' if conflict else '0', (bundle / 'merge-tree.status').read_text().strip())
            self.assertEqual('file' if conflict else '', (bundle / 'conflict-artifacts/files.txt').read_text().strip())
            if not conflict:
                self.assertEqual(b'', (bundle / 'residual.patch').read_bytes())
                self.assertIn(' = ', (bundle / 'range-diff.txt').read_text())
            # Generate the documented rollback template with shell-quoted literals.
            template = workflow.split('### 10. ', 1)[1]
            template = re.search(r'```bash\n(.*?)```', template, re.S)[1]
            values = {'<pinned-VR_HELPER>': str(HELPER), '<exact-BUNDLE>': str(bundle),
                      '<OWNER_ID>': owner, '<ATTEMPT_ID>': attempt}
            for key, value in values.items():
                template = template.replace(key, shlex.quote(value))
            (bundle / 'rollback.sh').write_text(template)
            (bundle / 'rollback.sh').chmod(0o700)
            a.finish('DIRTY-EXPLAINED' if conflict else 'CLEAN', 'COMPLETE')
            a.release()
            before_remote = git(repo, 'ls-remote', 'origin')
            rollback = subprocess.run([str(bundle / 'rollback.sh')], cwd=self.root, capture_output=True, text=True)
            self.assertEqual(0, rollback.returncode, rollback.stderr)
            self.assertEqual(a.owner['branch'], 'feature')
            self.assertEqual(before_remote, git(repo, 'ls-remote', 'origin'))
            self.assertFalse((repo / '.tmp').exists())

    def test_terminal_evidence_or_foreign_file_after_finish_blocks_release(self):
        for failure in ('evidence', 'foreign'):
            repo = make_repo(self.root, 'late-' + failure)
            a = self.attempt(repo)
            self.rebase(a)
            (a.bundle / 'summary.md').write_text('original')
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
    result = a.finish('CLEAN', 'COMPLETE')
    a.release()
    pipe.send(result['execution'])


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
