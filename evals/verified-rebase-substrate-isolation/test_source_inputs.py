"""Real input-boundary execution; all repositories/remotes are disposable."""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import unittest
import uuid

import test_ownership as ownership
from test_ownership import HELPER, capture, git, run, vr, make_stale_stack
from test_mechanics import workflow


def observation(repo):
    """Full ref/status/remote checkpoint, not just the selected branch tip."""
    result = {
        'refs': git(repo, 'for-each-ref', '--format=%(refname) %(objectname)'),
        'head': git(repo, 'rev-parse', 'HEAD'),
        'symbolic_head': git(repo, 'symbolic-ref', 'HEAD'),
        'status': git(repo, 'status', '--porcelain=v1', '--untracked-files=all'),
        'others': git(repo, 'ls-files', '--others', '-z'),
        'remote': git(repo, 'ls-remote', 'origin'),
    }
    if (Path(repo) / '.jj').exists():
        result['checkpoint'] = vr.snapshot(vr.substrate(repo))
    return result


def record(root, value):
    (root / (str(uuid.uuid4()) + '.json')).write_text(json.dumps(value, indent=2))


class SourceInputRegression(unittest.TestCase):
    setUp = ownership.OwnershipRegression.setUp
    preserve_and_clean = ownership.OwnershipRegression.preserve_and_clean
    attempt = ownership.OwnershipRegression.attempt
    assert_complete_bundle = ownership.OwnershipRegression.assert_complete_bundle

    def test_singleton_expressions_and_git_sources_on_stale_stack(self):
        for kind in ('change', 'intersection', 'git', 'short-git'):
            with self.subTest(kind=kind):
                root = self.root / str(uuid.uuid4())
                root.mkdir()
                repo = make_stale_stack(root)
                before = observation(repo)
                unique = git(repo, 'rev-parse', 'feature')
                parent = git(repo, 'rev-parse', unique + '^')
                op = before['checkpoint']['op']
                change = run(repo, 'jj', '--ignore-working-copy', '--at-operation', op,
                             'log', '-r', unique, '--no-graph', '-T', 'change_id')
                source = {'change': f'change_id({change})',
                          'intersection': 'feature & ~parent',
                          'git': unique, 'short-git': unique[:16]}[kind]
                record(root, {'source': source, 'before': before, 'unique': unique})
                a = workflow(repo, self.planning, target='parent', source=source)
                self.assert_complete_bundle(a, 'CLEAN')
                refs = vr.read(a.bundle / 'refs.json')
                self.assertEqual(unique, refs['SOURCE_COMMIT'])
                self.assertEqual(op, refs['SOURCE_OPERATION'])
                self.assertEqual(parent, refs['PRE_BASE'])
                receipt = vr.read(next(a.bundle.glob('source-resolution-*.json')))
                self.assertEqual(source, receipt['source'])
                self.assertEqual(op, receipt['checkpoint']['op'])
                self.assertEqual([unique], base64.b64decode(receipt['stdout_base64']).decode().splitlines())
                args = vr.read(a.bundle / 'rebase-command.json')['args']
                self.assertEqual(unique, args[args.index('-s') + 1])
                self.assertNotIn('parent-file', (a.bundle / 'branch-intended.patch').read_text())
                self.assertEqual('new', git(repo, 'show', 'feature:parent-file'))
                self.assertEqual(before['remote'], git(repo, 'ls-remote', 'origin'))
                record(root, {'after': observation(repo), 'bundle': str(a.bundle)})
                rollback = capture(root, [str(a.bundle / 'rollback.sh')], text=True)
                self.assertEqual(0, rollback.returncode, rollback.stderr)
                self.assertEqual(unique, git(repo, 'rev-parse', 'feature'))
                self.assertEqual(before['remote'], git(repo, 'ls-remote', 'origin'))

    def test_invalid_empty_multiple_and_nonancestor_source_refuse_before_anchor(self):
        for source, reason in (('feature | main', 'source-requires-single-commit'),
                               ('none()', 'source-requires-single-commit'),
                               ('change_id(', 'source-resolution-failed'),
                               ('main', 'command-failed')):
            with self.subTest(source=source):
                a = self.attempt(source=source)
                before = observation(self.repo)
                state = (a.bundle / 'state.json').read_bytes()
                record(self.root, {'source': source, 'before': before, 'bundle': str(a.bundle)})
                result = capture(self.repo, ['python3', str(HELPER), 'anchor', '--bundle', str(a.bundle),
                                 '--owner-id', a.owner['owner_id'], '--attempt-id', a.owner['attempt_id']], text=True)
                self.assertEqual(2, result.returncode)
                self.assertIn(reason, result.stderr)
                self.assertEqual(state, (a.bundle / 'state.json').read_bytes())
                self.assertEqual(before, observation(self.repo))
                self.assertFalse((a.bundle / 'anchor-command.json').exists())
                resolutions = list(a.bundle.glob('source-resolution-*.json'))
                self.assertEqual(1, len(resolutions))
                receipt = vr.read(resolutions[0])
                self.assertEqual(source, receipt['source'])
                self.assertIn('--at-operation', receipt['args'])
                # Refused repeated input appends diagnostics, never erases a failure.
                original = resolutions[0].read_bytes()
                again = capture(self.repo, ['python3', str(HELPER), 'anchor', '--bundle', str(a.bundle),
                                '--owner-id', a.owner['owner_id'], '--attempt-id', a.owner['attempt_id']], text=True)
                self.assertEqual(2, again.returncode)
                self.assertEqual(original, resolutions[0].read_bytes())
                self.assertEqual(2, len(list(a.bundle.glob('source-resolution-*.json'))))
                self.assertEqual(before, observation(self.repo))
                a.finish(execution='BLOCKED', reason=result.stderr.strip())
                a.release()
                terminal = vr.read(a.bundle / 'result.json')
                self.assertEqual('NOT-RUN', terminal['mechanical'])
                self.assertFalse(terminal['push_eligible'])
                self.assertEqual(before, observation(self.repo))
                record(self.root, {'after': observation(self.repo), 'bundle': str(a.bundle)})

    def test_source_resolution_does_not_adopt_foreign_operation(self):
        a = self.attempt(source='feature & ~main')
        state = (a.bundle / 'state.json').read_bytes()
        original = vr.invoke
        observed = []

        def intervene(repo, args, **kwargs):
            result = original(repo, args, **kwargs)
            if '-r' in args and args[args.index('-r') + 1] == a.owner['source'] and not observed:
                run(repo, 'jj', '--ignore-working-copy', 'describe', '-r', '@', '-m', 'separate operation')
                observed.append(observation(repo))
            return result

        vr.invoke = intervene
        try:
            with self.assertRaisesRegex(vr.Blocked, 'intervening-substrate-operation'):
                a.mutate('anchor')
        finally:
            vr.invoke = original
        self.assertEqual(1, len(observed))
        self.assertEqual(observed[0], observation(self.repo))
        self.assertEqual(state, (a.bundle / 'state.json').read_bytes())
        self.assertFalse((a.bundle / 'anchor-command.json').exists())
        self.assertEqual(1, len(list(a.bundle.glob('source-resolution-*.json'))))
        with self.assertRaisesRegex(vr.Blocked, 'intervening-substrate-operation'):
            a.finish(execution='BLOCKED', reason='intervening operation')
        record(self.root, {'after': observation(self.repo), 'foreign': observed, 'bundle': str(a.bundle)})

    def test_workflow_unavailable_jj_and_git_only_checkout_refuse(self):
        # PATH contains real tools, but genuinely has no jj executable; no fake jj.
        bin_dir = self.root / str(uuid.uuid4())
        bin_dir.mkdir()
        for tool in ('git', 'bash', 'python3', 'jq'):
            (bin_dir / tool).symlink_to(shutil.which(tool))
        bare = self.root / (str(uuid.uuid4()) + '.git')
        git(self.root, 'clone', '--bare', '--no-hardlinks', str(self.repo), str(bare))
        manual = self.root / str(uuid.uuid4())
        git(self.root, 'clone', '--no-hardlinks', str(bare), str(manual))
        git(manual, 'branch', 'feature', 'origin/feature')
        self.assertFalse((manual / '.jj').exists())
        for repo, path, reason in ((self.repo, str(bin_dir), 'jj-unavailable:no-rebase-fallback'),
                                  (manual, os.environ['PATH'], 'colocated-jj-required:no-manual-rebase')):
            with self.subTest(repo=str(repo)):
                owner, attempt = str(uuid.uuid4()), str(uuid.uuid4())
                before = observation(repo)
                text = (HELPER.parents[1] / 'workflows/verified-rebase.md').read_text()
                blocks = []
                for phase in range(1, 11):
                    section = text.split(f'### {phase}. ', 1)[1].split('\n### ', 1)[0]
                    block = re.search(r'```bash\n(.*?)```', section, re.S)
                    if block:
                        blocks.append(block[1])
                env = dict(os.environ, PATH=path, VR_HELPER=str(HELPER), repo_root=str(repo),
                           planning_dir=str(self.planning), OWNER_ID=owner, ATTEMPT_ID=attempt,
                           BRANCH='feature', TARGET='main', SOURCE='', PARENT_BUNDLE='')
                record(self.root, {'before': before, 'repo': str(repo), 'PATH': path,
                                   'owner_id': owner, 'attempt_id': attempt})
                result = capture(repo, ['bash', '-c', '\n'.join(blocks)], env=env, text=True)
                self.assertNotEqual(0, result.returncode)
                self.assertIn(reason, result.stderr)
                bundle = self.planning / owner / attempt
                refusal = vr.read(bundle / 'allocation-blocked.json')
                self.assertEqual(reason, refusal['reason'])
                self.assertIsNone(refusal['owner'])
                self.assertFalse(refusal['push_eligible'])
                self.assertFalse((bundle / 'owner.json').exists())
                self.assertFalse((bundle / 'state.json').exists())
                self.assertFalse((bundle / 'result.json').exists())
                self.assertFalse(list(repo.rglob('reservation.json')))
                self.assertEqual(before, observation(repo))
                record(self.root, {'after': observation(repo), 'bundle': str(bundle)})
        # Same previously refused supported substrate, restored real jj admission.
        remote = git(self.repo, 'ls-remote', 'origin')
        a = workflow(self.repo, self.planning)
        self.assert_complete_bundle(a, 'CLEAN')
        self.assertEqual(remote, git(self.repo, 'ls-remote', 'origin'))
