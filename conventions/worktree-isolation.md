# Worktree Isolation

**Unconditional rule**: every branch's work happens in its own git worktree, regardless of concurrency. The central checkout is for inspection and branch-tracking only, including the guarded default-branch deployment synchronization below—not authoring or feature work.

## Why

The central checkout is the directory the user ran `git clone` into or otherwise treats as the primary repository checkout. Examples include `/home/nes/ai`, `/home/nes/projects/agent-runner/trunk`, and a project's `trunk/` directory in the `~/projects/<name>/{trunk,planning,worktrees}/` layout.

Keeping branch work out of the central checkout protects the stable branch-tracking point and makes every working branch explicit. The rule is unconditional because a single writer can still leave hidden state behind, switch the primary checkout away from the expected branch, or blur which working tree owns a change.

Worktree isolation gives each branch a clean, disjoint working directory backed by a dedicated branch. Merging or stacking branches is the join step.

## Setup

Use worktree-creation tooling or the direct Git command when a branch needs a working directory:

```bash
# From the main repository checkout:
git worktree add worktrees/<branch-name> -b <branch-name> <base-branch>

# Point the agent at it:
agents -m <model> -p worktrees/<branch-name> -f <prompt>.md
```

Convention for worktree location: `worktrees/<branch-name>/` inside the repo root.

## Central Checkout Use

### Allowed in the central checkout (read-state only)

The central checkout may be inspected and kept aware of remote branch state. These operations must not edit tracked files or move the checkout onto feature work:

1. `git status`
2. `git log`
3. `git show`
4. `git diff` for inspection only
5. `git branch --show-current`
6. `git branch --list`
7. `git worktree list`
8. `git remote -v`
9. `git fetch`
10. `gh pr view`
11. `gh pr list`
12. `gh run view`
13. `gh run list`
14. File reads and searches that do not edit tracked files

### Default-branch deployment synchronization

When task authority permits deployment synchronization, a clean central checkout already on its configured default branch may run `git pull --ff-only <remote> <default-branch>` from that branch's configured remote. This advances the local branch and working tree to already merged remote default-branch content; it is branch-tracking/deployment synchronization, not authoring or feature mutation. Fetch alone updates remote-tracking state but does not deploy instructions into the local checkout.

Before pulling, verify the repository's actual default branch, current branch, configured remote and upstream; the upstream must match that remote's default branch. Do not assume `main` (for example, ai uses `master`, while CRW uses `main`). Stop if any identity is missing, mismatched or uncertain; do not switch branches or reconfigure tracking to make the check pass. Verify a clean index and working tree, including no untracked work, and no operation in progress. Fetch and confirm that the local head is equal to or an ancestor of the remote default-branch head; local-only or divergent history stops synchronization.

Use fast-forward-only behavior with rebasing and autostashing disabled, regardless of local Git configuration (for example, `git -c pull.rebase=false -c rebase.autoStash=false -c merge.autoStash=false pull --ff-only <remote> <default-branch>`). Dirty state, a non-fast-forward result, or any other failure stops the operation without automatic repair. Do not stash, reset, force, rebase, merge divergent history, resolve conflicts, or edit files in the central checkout. Afterward, read back the branch, head, upstream and clean status to confirm the intended synchronization; report any mismatch rather than repairing it. This exception grants no merge/review bypass or additional task authority.

### Disallowed in the central checkout (authoring and other state mutation)

Except for the guarded default-branch synchronization above and recognized topology carve-outs below, state-mutating work belongs in a git worktree. Do not use the central checkout for:

1. `git checkout <branch>` or any feature-branch checkout
2. `git switch <branch>`
3. `git reset`, including `git reset --hard`
4. `git commit`
5. `git merge`
6. `git rebase`
7. `git cherry-pick`
8. `git push`
9. `git pull` except the guarded default-branch deployment synchronization above
10. `git stash` used to manage central-checkout work
11. `git add` or other staging operations
12. Authored edits to tracked files or generated-file updates (not updates delivered by the guarded synchronization above)
13. Branch construction, feature implementation, experiments, fixes, or review revisions

## Recognized Carve-outs

These are narrow topology exceptions. They do not permit ordinary branch work in the central checkout.

### jj substrate maintenance

[`jj-operator`](../agents/jj-operator.md) owns jj substrate maintenance. Its commands intentionally operate on the repository substrate from `${repo_root}`; treat that as topology maintenance, not feature implementation in the central checkout.

### Worktree administration

[`worktree-operator`](../agents/worktree-operator.md) owns worktree administration, including worktree creation, listing, removal, and sync. Creating or synchronizing worktrees from the repository root is allowed when it is topology administration for the branch worktree fleet.

### Outside-repo scratch for read-only investigations

[`pipeline-artifacts-operator`](../agents/pipeline-artifacts-operator.md) defines `Tasks Without a Worktree`. That outside-repo scratch carve-out is for read-only investigations and ad-hoc non-tracked artifacts only; it must not write tracked files or perform central-checkout branch work.

## Cleanup

After the agent branch has been merged:

```bash
git worktree remove worktrees/<branch-name>
# If the branch is still wanted elsewhere, keep it; otherwise:
git branch -d <branch-name>
```
