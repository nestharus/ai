"""Complete durable workflow and mechanical populations in disposable repositories."""
import json
import os
import re
from pathlib import Path
import unittest
import uuid
import test_ownership as ownership

from test_ownership import (HELPER, CTX, capture, git, run, vr,
                            make_repo, make_stale_stack, command_boundary_worker)


def workflow(repo, planning, branch='feature', target='main', source=None, parent=None, expect_failure=False):
    owner, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    text = (HELPER.parents[1] / 'workflows/verified-rebase.md').read_text()
    blocks = []
    for phase in range(1, 11):
        section = text.split(f'### {phase}. ', 1)[1].split('\n### ', 1)[0]
        block = re.search(r'```bash\n(.*?)```', section, re.S)
        if block:
            blocks.append(block[1])
    env = dict(os.environ, VR_HELPER=str(HELPER), repo_root=str(repo), planning_dir=str(planning),
               OWNER_ID=owner, ATTEMPT_ID=attempt, BRANCH=branch, TARGET=target,
               SOURCE=source or '', PARENT_BUNDLE=str(parent) if parent else '')
    result = capture(repo, ['bash', '-c', '\n'.join(blocks)], env=env, text=True)
    if bool(result.returncode) != expect_failure:
        raise AssertionError(f'rc={result.returncode}: {result.stderr}')
    return vr.Attempt(planning / owner / attempt, owner, attempt)


def make_file_case(root, kind):
    repo = root / kind
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    git(repo, 'config', 'user.name', 'Fixture')
    git(repo, 'config', 'commit.gpgsign', 'false')
    base = b'base\x00\xff\x00\n' if kind == 'binary' else b''.join(f'line {i}\n'.encode() for i in range(30))
    (repo / 'file').write_bytes(base)
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'base')
    git(repo, 'checkout', '-b', 'feature')
    (repo / 'file').write_bytes(b'feature\x00\xff\n' if kind == 'binary' else base.replace(b'line 3\n', b'feature\n'))
    git(repo, 'commit', '-am', 'feature')
    git(repo, 'checkout', 'main')
    if kind == 'rename':
        git(repo, 'mv', 'file', 'renamed')
    elif kind == 'delete':
        git(repo, 'rm', 'file')
    else:
        (repo / 'file').write_bytes(b'target\x00\xfe\n')
    git(repo, 'commit', '-am', 'target')
    git(repo, 'clone', '--bare', '--no-hardlinks', str(repo), str(root / (kind + '-origin.git')))
    git(repo, 'remote', 'add', 'origin', str(root / (kind + '-origin.git')))
    run(repo, 'jj', 'git', 'init', '--colocate')
    return repo


def make_divergent(root, name):
    repo = make_repo(root, name)
    op = vr.snapshot(vr.substrate(repo))['op']
    run(repo, 'jj', '--ignore-working-copy', 'describe', '-r', 'feature', '-m', 'first version')
    first = git(repo, 'rev-parse', 'feature')
    run(repo, 'jj', '--ignore-working-copy', '--at-operation', op, 'describe', '-r', 'feature', '-m', 'second version')
    run(repo, 'jj', '--ignore-working-copy', 'log')  # reconcile setup operations before ownership
    change = vr.jj(repo, 'log', '-r', first, '--no-graph', '-T', 'change_id')
    versions = vr.jj(repo, 'log', '-r', f'change_id({change})', '--no-graph', '-T', 'commit_id ++ "\\n"').splitlines()
    stale = next(oid for oid in versions if oid != first and git(repo, 'show', '-s', '--format=%s', oid) == 'second version')
    run(repo, 'jj', '--ignore-working-copy', 'bookmark', 'set', 'feature', '-r', first)
    return repo, stale


class MechanicalRegression(unittest.TestCase):
    setUp = ownership.OwnershipRegression.setUp
    preserve_and_clean = ownership.OwnershipRegression.preserve_and_clean
    attempt = ownership.OwnershipRegression.attempt
    rebase = ownership.OwnershipRegression.rebase
    assemble = ownership.OwnershipRegression.assemble
    assert_complete_bundle = ownership.OwnershipRegression.assert_complete_bundle
    assert_conflict_payloads = ownership.OwnershipRegression.assert_conflict_payloads

    def test_rename_delete_binary_full_workflow(self):
        for kind in ('rename', 'delete', 'binary'):
            with self.subTest(kind=kind):
                repo = make_file_case(self.root, kind)
                remote = git(repo, 'ls-remote', 'origin')
                a = workflow(repo, self.planning)
                result = vr.read(a.bundle / 'result.json')
                verdict = result['mechanical']
                self.assert_complete_bundle(a, verdict)
                if kind == 'rename':
                    self.assertIn(verdict, ('DIRTY-EXPLAINED', 'DIRTY-UNPROVENANCED'))
                    self.assertIn('rename-present: true', (a.bundle / 'summary.md').read_text())
                else:
                    self.assertEqual('DIRTY-EXPLAINED', verdict)
                    post = result['POST_TIP']
                    expected = capture(repo, ['jj', '--ignore-working-copy', '--no-pager', '--color=never',
                        '--at-operation', result['checkpoint']['op'], 'file', 'show', '-r', post, '--', 'file']).stdout
                    self.assert_conflict_payloads(a.bundle, {'file': expected})
                    self.assertTrue(expected)
                    self.assertEqual('1', (a.bundle / 'merge-tree.status').read_text().strip())
                self.assertEqual('BLOCKED' if verdict == 'DIRTY-UNPROVENANCED' else 'COMPLETE', result['execution'])
                self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))
                rollback = capture(self.root, [str(a.bundle / 'rollback.sh')], text=True)
                self.assertEqual(0, rollback.returncode, rollback.stderr)
                self.assertEqual(result['pre']['PRE_TIP'], git(repo, 'rev-parse', 'feature'))
                self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))

    def test_stale_parent_unscoped_blocked_and_scoped_complete(self):
        repo = make_stale_stack(self.root)
        remote = git(repo, 'ls-remote', 'origin')
        unique = git(repo, 'rev-parse', 'feature')
        a = workflow(repo, self.planning, target='parent')
        self.assert_complete_bundle(a, 'DIRTY-UNPROVENANCED')
        self.assertEqual('BLOCKED', vr.read(a.bundle / 'result.json')['execution'])
        self.assertTrue(vr.read(a.bundle / 'correspondence.json')['problems'])
        self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))
        a.rollback()
        self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))
        b = workflow(repo, self.planning, target='parent', source=unique)
        self.assert_complete_bundle(b, 'CLEAN')
        self.assertNotIn('parent-file', (b.bundle / 'branch-intended.patch').read_text())
        self.assertEqual('new', git(repo, 'show', 'feature:parent-file'))
        self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))

    def test_stacked_bundles_and_noop_complete_cross_associations(self):
        git(self.repo, 'checkout', '-b', 'child', 'feature')
        (self.repo / 'child-file').write_text('child\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'child')
        git(self.repo, 'checkout', 'main')
        run(self.repo, 'jj', 'git', 'import')
        git(self.repo, 'fetch', 'origin')
        run(self.repo, 'jj', 'git', 'import')
        remote = git(self.repo, 'ls-remote', 'origin')
        parent = workflow(self.repo, self.planning, target='origin/main')
        child = workflow(self.repo, self.planning, branch='child', target='feature', parent=parent.bundle)
        for a in (parent, child):
            self.assert_complete_bundle(a, 'CLEAN')
        self.assertTrue((parent.bundle / 'main-delta.patch').exists())
        self.assertEqual((parent.bundle / 'branch-actual.patch').read_bytes(), (child.bundle / 'parent-delta.patch').read_bytes())
        self.assertIn('parent-pointer-check: PASS', (child.bundle / 'summary.md').read_text())
        self.assertEqual(vr.read(parent.bundle / 'refs.json')['POST_TIP'], vr.read(child.bundle / 'refs.json')['NEW_TARGET'])
        self.assertEqual((child.bundle / 'branch-intended.patch').read_bytes(), (child.bundle / 'branch-actual.patch').read_bytes())
        self.assertEqual(b'', (child.bundle / 'target-delta.patch').read_bytes())
        self.assertEqual(remote, git(self.repo, 'ls-remote', 'origin'))
        child.rollback()
        self.assertEqual(remote, git(self.repo, 'ls-remote', 'origin'))

    def test_terminal_refuses_unassembled_wrong_label_and_omitted_outputs(self):
        for missing in ('summary.md', 'refs.json', 'residual.patch', 'correspondence.json'):
            repo = make_repo(self.root, 'omitted-' + missing)
            remote = git(repo, 'ls-remote', 'origin')
            a = self.attempt(repo)
            self.rebase(a)
            with self.assertRaisesRegex(vr.Blocked, 'complete-mechanical-bundle-required'):
                a.finish('CLEAN', 'COMPLETE')
            self.assemble(a)
            with self.assertRaisesRegex(vr.Blocked, 'mechanical-label-mismatch'):
                a.finish('DIRTY-EXPLAINED', 'COMPLETE')
            (a.bundle / missing).rename(self.root / ('removed-' + missing))
            with self.assertRaisesRegex(vr.Blocked, 'assembled-evidence-changed'):
                a.finish('CLEAN', 'COMPLETE')
            self.assertFalse((a.bundle / 'result.json').exists())
            self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))
        repo = make_stale_stack(self.root)
        a = self.attempt(repo, target='parent')
        self.rebase(a)
        self.assemble(a)
        with self.assertRaisesRegex(vr.Blocked, 'mechanical-label-mismatch'):
            a.finish('CLEAN', 'COMPLETE')
        with self.assertRaisesRegex(vr.Blocked, 'unprovenanced-mechanics-blocked'):
            a.finish('DIRTY-UNPROVENANCED', 'COMPLETE')
        a.finish()
        a.release()

    def test_divergent_abandon_return_boundary_and_interference(self):
        for mutation in ('none', 'operation', 'ref'):
            repo, stale = make_divergent(self.root, 'divergent-' + mutation)
            remote = git(repo, 'ls-remote', 'origin')
            a = self.attempt(repo)
            refs = self.rebase(a)
            self.assertIn(stale, vr.read(a.bundle / 'state.json')['pre']['CLEANUP_CANDIDATES'])
            checkpoint = vr.read(a.bundle / 'state.json')['checkpoint']
            parent, child = CTX.Pipe()
            process = CTX.Process(target=command_boundary_worker, args=(a, 'abandon', child, stale))
            process.start()
            self.addCleanup(lambda p=process: p.kill() if p.is_alive() else None)
            self.assertTrue(parent.poll(20))
            self.assertEqual('command-returned', parent.recv())
            if mutation == 'operation':
                run(repo, 'jj', '--ignore-working-copy', 'bookmark', 'create', 'foreign', '-r', 'main')
            elif mutation == 'ref':
                git(repo, 'update-ref', 'refs/heads/foreign', 'main')
            observed = vr.snapshot(a.identity)
            parent.send('readback')
            self.assertTrue(parent.poll(20))
            outcome = parent.recv()
            process.join(10)
            self.assertEqual(0, process.exitcode)
            if mutation == 'none':
                self.assertEqual('accepted', outcome)
                self.assertIn('abandon-' + stale, vr.read(a.bundle / 'state.json')['completed'])
                self.assertEqual(refs['post'], git(repo, 'rev-parse', 'feature'))
                self.assemble(a)
                a.finish()
                a.release()
                self.assert_complete_bundle(a, 'CLEAN')
                a.rollback()
            else:
                self.assertIn('blocked', outcome)
                self.assertEqual(checkpoint, vr.read(a.bundle / 'state.json')['checkpoint'])
                self.assertIsNotNone(vr.read(a.bundle / 'state.json')['inflight'])
                for operation in (a.check, a.release, a.rollback, lambda: a.finish()):
                    with self.assertRaises(vr.Blocked):
                        operation()
                self.assertEqual(observed, vr.snapshot(a.identity))
            self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))

    def test_unexplained_rename_residual_cannot_be_labeled_clean(self):
        repo = make_file_case(self.root, 'rename')
        remote = git(repo, 'ls-remote', 'origin')
        a = self.attempt(repo)
        self.rebase(a)
        decision = self.assemble(a)
        self.assertEqual('DIRTY-UNPROVENANCED', decision['verdict'])
        self.assertIn('renamed', set(decision['residual_paths']) - set(decision['conflict_paths']))
        with self.assertRaisesRegex(vr.Blocked, 'mechanical-label-mismatch'):
            a.finish('CLEAN', 'COMPLETE')
        with self.assertRaisesRegex(vr.Blocked, 'unprovenanced-mechanics-blocked'):
            a.finish('DIRTY-UNPROVENANCED', 'COMPLETE')
        a.finish()
        a.release()
        self.assert_complete_bundle(a, 'DIRTY-UNPROVENANCED')
        self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))
        a.rollback()
        self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))

    def test_parent_pointer_mismatch_and_changed_parent_evidence(self):
        parent = workflow(self.repo, self.planning)
        original_hashes = vr.evidence_hashes(parent.bundle)
        # Same source repository, deliberately wrong target relative to this
        # parent's tip: content cleanliness alone cannot satisfy the pointer.
        child = self.attempt(branch='feature', target='main')
        self.rebase(child)
        decision = self.assemble(child, parent.bundle)
        self.assertFalse(decision['parent']['pointer_matches'])
        self.assertEqual('DIRTY-UNPROVENANCED', decision['verdict'])
        child.finish()
        child.release()
        self.assertIn('parent-pointer-check: FAIL', (child.bundle / 'summary.md').read_text())
        self.assertEqual(original_hashes, vr.evidence_hashes(parent.bundle))
        (parent.bundle / 'branch-actual.patch').rename(self.root / 'parent-original-actual.patch')
        (parent.bundle / 'branch-actual.patch').write_bytes(b'substituted')
        another = self.attempt()
        self.rebase(another)
        another.capture_conflicts()
        with self.assertRaisesRegex(vr.Blocked, 'parent-evidence-changed'):
            another.assemble(parent.bundle)
        self.assertFalse((another.bundle / 'result.json').exists())

    def test_real_prediction_failure_retains_partial_bundle_and_remote(self):
        git(self.repo, 'config', 'merge.renames', 'invalid-boolean')
        remote = git(self.repo, 'ls-remote', 'origin')
        pre_tip = git(self.repo, 'rev-parse', 'feature')
        a = workflow(self.repo, self.planning, expect_failure=True)
        self.assertNotIn((a.bundle / 'merge-tree.status').read_text().strip(), ('0', '1'))
        self.assertFalse((a.bundle / 'result.json').exists())
        self.assertNotIn('rebase', vr.read(a.bundle / 'state.json')['completed'])
        a.finish('NOT-RUN', 'BLOCKED', 'merge-tree-failed')
        a.release()
        self.assertEqual(pre_tip, git(self.repo, 'rev-parse', 'feature'))
        self.assertEqual(remote, git(self.repo, 'ls-remote', 'origin'))

    def test_decoder_refuses_unexplained_storage_path(self):
        repo = make_repo(self.root, 'storage', conflict=True)
        a = self.attempt(repo)
        self.rebase(a)
        evidence = vr.MechanicalEvidence(a, a.inspect())
        post = git(repo, 'rev-parse', 'feature')
        raw = evidence.git('cat-file', 'commit', post)
        entries = evidence.tree_map(post)
        entries['.jjconflict-unrelated/file'] = entries['file']
        tree = evidence.make_tree(entries)
        altered = b'tree ' + tree.encode() + b'\n' + raw.split(b'\n', 1)[1]
        oid = evidence.git('hash-object', '-t', 'commit', '-w', '--stdin', input=altered).decode().strip()
        with self.assertRaisesRegex(vr.Blocked, 'unexplained-conflict-storage'):
            evidence.decode(oid)
        self.assertFalse((a.bundle / 'result.json').exists())

    def test_conflict_capture_tampering_refuses_terminal_assembly(self):
        for corruption in ('payload', 'association', 'extra'):
            repo = make_repo(self.root, 'capture-' + corruption, conflict=True)
            a = self.attempt(repo)
            self.rebase(a)
            a.capture_conflicts()
            directory = a.bundle / 'conflict-artifacts'
            if corruption == 'payload':
                (directory / '0.conflict').rename(self.root / 'original-payload')
                (directory / '0.conflict').write_bytes(b'not the actual conflict')
            elif corruption == 'association':
                (directory / 'files.txt').rename(self.root / 'original-path-list')
                (directory / 'files.txt').write_text('other\n')
            else:
                (directory / 'unassociated.conflict').write_text('foreign artifact')
            with self.assertRaises(vr.Blocked):
                a.assemble()
            self.assertFalse((a.bundle / 'result.json').exists())
            with self.assertRaisesRegex(vr.Blocked, 'complete-mechanical-bundle-required'):
                a.finish('DIRTY-EXPLAINED', 'COMPLETE')

    def test_multi_parent_basis_collapse_complete_bundle(self):
        repo = self.repo
        base = git(repo, 'rev-parse', 'main~1')
        git(repo, 'checkout', '-b', 'second', base)
        (repo / 'second').write_text('second\n')
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'second parent')
        git(repo, 'checkout', '-b', 'basis', 'feature')
        git(repo, 'merge', '--no-ff', 'second', '-m', 'basis')
        git(repo, 'checkout', '-b', 'child')
        (repo / 'child').write_text('child\n')
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'child')
        git(repo, 'checkout', 'main')
        git(repo, 'merge', '--no-ff', 'feature', '-m', 'land first parent')
        run(repo, 'jj', 'git', 'import')
        remote = git(repo, 'ls-remote', 'origin')
        a = workflow(repo, self.planning, branch='child')
        self.assert_complete_bundle(a, 'CLEAN')
        self.assertNotIn('parent-pointer-check', (a.bundle / 'summary.md').read_text())
        self.assertFalse((a.bundle / 'parent-delta.patch').exists())
        self.assertEqual('child', git(repo, 'show', 'child:child'))
        self.assertEqual('second', git(repo, 'show', 'child:second'))
        self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))
        a.rollback()
        self.assertEqual(remote, git(repo, 'ls-remote', 'origin'))
