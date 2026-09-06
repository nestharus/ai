---
description: 'Create, list, sync, and manage git worktrees for feature branches.'
model: gpt-high
output_format: ''
---

# Worktree Operator

## Contract

When `contracts/operators/worktree-operator.yaml` is present, dispatchers use that sidecar as the optimized call interface and this embedded block only as its equivalent fallback. The full operator body remains the procedural authority.

```yaml
schema: operator-contract-v1
inputs:
  - name: task
    type: enum
    options: [create, list, sync, remove, bulk-cleanup, open-pr]
    required: true
    default_source: caller
    description: "task"
  - name: repo_root
    type: path
    required: true
    default_source: caller
    description: "repo root"
  - name: worktrees_root
    type: path
    required: false
    default_source: base
    description: "worktrees root"
  - name: name
    type: string
    required: false
    default_source: caller
    description: "Required for create, sync, remove, and open-pr; derives ${worktrees_root}/${name}. Must be one safe direct-child name without traversal, option-like values, or shell metacharacters."
  - name: branch_name
    type: string
    required: false
    default_source: caller | derived
    description: "Required or deterministically derived from name for create, sync, remove, and open-pr; must pass git check-ref-format --branch and the caller's branch policy."
  - name: base_branch
    type: string
    required: false
    default_source: base
    description: "Existing safe short branch required for create, remove, bulk-cleanup, and open-pr; resolved through the freshly fetched remote-tracking ref to an exact commit."
  - name: branch_policy
    type: string
    required: false
    default_source: caller
    description: "branch policy"
  - name: lock_acquire_seconds
    type: integer
    required: false
    default_source: base
    description: Positive integer seconds, at most 300, for acquiring the canonical worktree-operator.lock; expiry is BLOCKED:mutation-lock-timeout with no mutation.
  - name: lock_hold_seconds
    type: integer
    required: false
    default_source: base
    description: Positive integer seconds, at most 3600, for each synchronous mechanical critical section; never spans pr-writer.
  - name: lock_cleanup_seconds
    type: integer
    required: false
    default_source: base
    description: Positive integer seconds, at most 60, for TERM-to-KILL escalation and verified owned-tree retirement; must cover the installed runtime cancellation grace.
defaults:
  - name: worktrees_root
    value: ${repo_root}/worktrees
    source: base
  - name: base_branch
    value: main
    source: base
  - name: lock_acquire_seconds
    value: 30
    source: base
  - name: lock_hold_seconds
    value: 300
    source: base
  - name: lock_cleanup_seconds
    value: 10
    source: base
secrets:
  []
outputs:
  - task: create
    success_shape: "worktree-operation-result-v1 with task=create, canonical repo/worktree paths, branch, base branch/SHA, head SHA, and clean=true."
    wrote_lines: []
  - task: list
    success_shape: "worktree-operation-result-v1 with task=list and one canonical path/branch/head SHA/cleanliness/registration-status/reason row per registered worktree after per-worktree git status collection; unreadable or vanished rows retain every key and use null for unavailable fields; aggregate status is PASS for zero or all-readable rows, PARTIAL for mixed readable/BLOCKED rows, and BLOCKED for non-empty all-BLOCKED rows."
    wrote_lines: []
  - task: sync
    success_shape: "worktree-operation-result-v1 with task=sync, canonical path, branch, pre/post head SHA, and post-sync cleanliness."
    wrote_lines: []
  - task: remove
    success_shape: "worktree-operation-result-v1 with task=remove, pre-removal path/branch/base branch/base SHA/head SHA/cleanliness identity, and removed=true."
    wrote_lines: []
  - task: bulk-cleanup
    success_shape: "worktree-operation-result-v1 with task=bulk-cleanup and one worktree_path/branch/base branch/base SHA/head SHA/cleanliness/PR target repository/PR head repository/PR URL/number/state/removed/status/reason row per inspected target; skipped rows retain every key and use null for unavailable identity fields; aggregate status is PASS for zero or all-PASS rows, PARTIAL for mixed PASS/BLOCKED rows, and BLOCKED for non-empty all-BLOCKED rows."
    wrote_lines: []
  - task: open-pr
    success_shape: "worktree-operation-result-v1 with task=open-pr, status=PASS, provider_state=OPEN, exact target and head repository identities, PR URL/number, base/head branches, base SHA, head SHA, and draft=true."
    wrote_lines: []
errors:
  - class: BLOCKED
    cause: "Required inputs are missing, unreadable, contradictory, or unsafe for the selected task."
    recovery: "Supply corrected inputs or select the appropriate operator wrapper before rerun."
  - class: NEEDS_INPUT
    cause: "A user-owned value, scope, or trade-off question is required."
    recovery: "Answer the emitted question artifact and resume."
  - class: BLOCKED
    cause: Mutation lock acquisition, execution, cancellation, or retirement is unverified; use mutation-lock-timeout, mutation-lock-deadline, mutation-lock-interrupted, or mutation-lock-cleanup-unverified.
    recovery: Prove the exact prior attempt terminal before retry; unknown external outcomes require reconciliation.
side_effects:
  - git-fetch
  - git-worktree-create
  - git-worktree-remove
  - git-branch-create
  - git-reset-keep
  - git-push-validated-url
  - gh-pr-create
  - gh-pr-close-reconciliation
must_delegate:
  - worktree-mutation
may_direct:
  - worktree-list-read
forbidden_direct:
  - direct-worktree-mutation-without-branch-policy
  - recursive-worktree-operator-dispatch
  - unvalidated-worktree-mutation
  - unquoted-caller-controlled-git-arguments
  - worktree-target-outside-canonical-root
  - central-checkout-as-worktree-target
  - async-lock-holder-or-waiter
  - marker-or-sleep-lock-lifetime
  - unbounded-lock-acquisition
  - lock-across-pr-writer
  - unlock-before-owned-tree-retirement
  - unlink-or-replace-mutation-lock
```

You manage git worktrees for a repository that uses a dedicated worktree root at `${worktrees_root}`. The primary checkout at `${repo_root}` stays on `main` and is not used for feature implementation.

## Use When

- A new worktree needs to be created for a task
- Worktrees need to be listed or inspected
- A worktree needs to be synced after jj rebase
- A worktree needs to be removed/pruned
- Merged worktrees need provider-verified bulk cleanup
- A draft pull request needs exact creation or idempotent reuse

## Do Not Use When

- Rebasing or managing branch dependencies (use jj-operator)
- Running E2E tests in a worktree (use e2e-operator)
- Building releases (use release-operator)

## Execution Boundary

`must_delegate: worktree-mutation` is a caller boundary: callers delegate worktree mutations to this operator. Once selected, this operator performs the single requested task directly. It must never dispatch `worktree-operator.md`, another agent, or another workflow to perform the same request. Apply task-specific preconditions: `create` requires branch and path absence; `sync`, `remove`, and `open-pr` require one exact existing registered worktree, expected branch, and canonical containment; `bulk-cleanup` validates each discovered registered worktree independently. Every mutating task validates the repository, exact base where applicable, branch policy, and central-checkout protection, then returns task-specific identity and cleanliness evidence.

## Non-Negotiables

- **`${repo_root}` stays on `main`** — never commit directly there.
- **Branch naming follows the caller's `${branch_policy}`.** The examples below use `<branch-name>` placeholders rather than imposing one naming scheme.
- **Worktree location:** `${worktrees_root}/<name>/`.
- **Canonical containment:** resolve `${repo_root}`, `${worktrees_root}`, and every proposed or discovered worktree path before use. Every mutation target must differ from canonical `${repo_root}` and have canonical `${worktrees_root}` as its direct parent. `task=list` instead reports canonical `${repo_root}` as the explicit primary-checkout row and applies the direct-parent rule only to linked-worktree rows. `name` must be one safe path component matching `[A-Za-z0-9][A-Za-z0-9._-]*` and must not start with `-`. Apply the repository-path inequality to every mutation target even when the caller supplies a custom worktree root.
- **Argument safety:** pass caller-controlled paths and refs as individually quoted arguments, never through `eval`, `bash -c`, or an interpolated command string. Validate short branch names with `git check-ref-format --branch` and the caller's branch policy before use.

## Required Inputs

- `task`: One of: `create`, `list`, `sync`, `remove`, `bulk-cleanup`, `open-pr`
- `name` (for create/sync/remove/open-pr): Worktree name (e.g., `cost-estimation-e2e`) used to derive the exact direct-child worktree path.
- `branch_name` (for create/sync/remove/open-pr, optional): branch checked out in the worktree. If omitted, derive it deterministically from `name` using the caller's branch policy.
- `base_branch` (for create/remove/bulk-cleanup/open-pr, optional): Expected base branch. Defaults to `main`; fetch and resolve its exact remote-tracking SHA before mutation.

## Inputs

- `--input repo_root=<path>` (required) — target repository root.
- `--input worktrees_root=<path>` (optional, default `${repo_root}/worktrees`) — root directory containing git worktrees.
- `--input branch_policy=<pattern>` (optional, no default) — caller's branch naming convention for feature branches.

## Bounded Mutation Sections

All lock-using paths below use **one canonical exclusion domain**:
`realpath(git rev-parse --path-format=absolute --git-common-dir)/worktree-operator.lock`.
Never unlink, replace, or change the basename of that inode. `create` also uses
this section from final absence/base checks through post-create verification;
`bulk-cleanup` uses a separate section per target. `list` remains read-only.

Before starting, validate `lock_acquire_seconds` (default 30, range 1–300),
`lock_hold_seconds` (default 300, range 1–3600), and `lock_cleanup_seconds`
(default 10, range 1–60). All are positive integer seconds. The cleanup budget
must cover the installed runtime's documented cancellation grace plus terminal
readback. Missing runtime support or an insufficient cleanup budget is
`BLOCKED:mutation-lock-cleanup-unverified`, not permission to fall back to an
unleased command. Tests may use short fixture limits with an independent hard
teardown bound.

Prepare each complete mechanical section as a private, immutable shell script
outside the target worktree before acquisition. No agent turn, prompt, network
human wait, background job, `setsid`, `disown`, readiness/release marker, fixed
sleep holder, or detached helper belongs inside it. Execute foreground commands
sequentially; do not close the inherited flock descriptor or start commands that
shed it while leaving mutating descendants alive. A shell EXIT trap alone is
not owner-exit protection. No lock may span separate tool calls that perform its
protected work. The deadline bounds the work, not a sleep standing in for it.

### Canonical executable lock section

Save the following block as the attempt-private `lock-section.sh`; pass the
validated variables in its environment. `section_script` contains only the
mechanical operation, checks, and applicable reconciliation below. This is the
canonical command, not an illustrative alternative:

```bash
# worktree-lock-section-v1
set -euo pipefail
validate_lock_limit() {
  [[ "$1" =~ ^[1-9][0-9]{0,3}$ ]] && (( 10#$1 <= $2 ))
}
validate_lock_limit "$lock_acquire_seconds" 300 || exit 64
validate_lock_limit "$lock_hold_seconds" 3600 || exit 64
validate_lock_limit "$lock_cleanup_seconds" 60 || exit 64
common_dir=$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir)
common_dir=$(realpath -e -- "$common_dir")
exec flock --exclusive --no-fork --conflict-exit-code 75 \
  --wait "$lock_acquire_seconds" -- "$common_dir/worktree-operator.lock" \
  timeout --signal=TERM --kill-after="${lock_cleanup_seconds}s" \
  "${lock_hold_seconds}s" bash --noprofile --norc -euo pipefail "$section_script"
```

Use the existing installed matching agent-bash adapter/binary's synchronous,
exact-owner-cancellable ordinary-command path. Require **tree** completion, not
root-only completion or a readiness sentinel. The equivalent CLI admission is
below (`lock_owner_pid` is the live operator/caller ancestor, not a throwaway
shell; the runtime captures its PID/start-time/boot-ID identity). This is an
ordinary command, never an `agents` dispatch:

```bash
# worktree-lock-admission-v1
agent-bash run --delivery sync --completion-scope tree \
  --cancel-on-owner-exit --owner-pid "$lock_owner_pid" \
  -- bash --noprofile --norc "$lock_section_path"
```

Admission returns an attempt handle, **not completion**. Retain it and the
runtime's owner/workload identities; consume terminal completion through the
matching adapter or one bounded observer of this already-running handle.
Never detach it or switch delivery to async. All protected work is already in
that single synchronous-delivery lifetime; no later agent turn releases it.
Normal asynchronous agent/runtime behavior elsewhere is unchanged.

`flock` exit 75 means `BLOCKED:mutation-lock-timeout`, `mutation_state=none`:
no section command, including fetch, has run. Exit 124 or deadline escalation
137 means `BLOCKED:mutation-lock-deadline`. Cancellation, SIGINT/SIGTERM, or
owner exit means `BLOCKED:mutation-lock-interrupted`, never PASS even if a
command traps the signal and exits zero. Other nonzero exits preserve the
mechanical failure. Do not use 75/124/137 for a mechanical script's own
application errors. A killed attempt may have no final operator envelope;
its caller must retain the runtime non-pass and uncertainty instead.

On **every** success, validation/provider error, timeout, interruption, and owner
exit, require terminal tree retirement before accepting a result or replacing
the attempt. On deadline/cancellation the timeout and existing runtime terminate
owned work, escalate, and reap it; the inherited lock remains exclusion for any
still-live lock-bearing descendant. Never explicitly unlock underneath work.
Verify the exact attempt's tree is empty within `lock_cleanup_seconds`; a
surviving descendant or missing terminal evidence is
`BLOCKED:mutation-lock-cleanup-unverified`. Stop and hand back exact ownership
for investigation, never kill by PID alone, broad process matching, or an
unrelated holder. A different actor may immediately acquire the global lock;
retirement is an attempt-local assertion, not a perpetual global-lock probe.
A timeout/abort that may have crossed push/create/close remains
`mutation_state=unknown` until exact owned-resource reconciliation is proved;
local cleanup never changes it to `none`. Do not retry ambiguous publication.

## Procedure: Create Worktree

1. Resolve and validate the canonical repository and worktree roots, direct-child target, safe `name`, safe short `branch_name`, and safe short `base_branch`. Require the target path and local branch to be absent. Resolve `base_branch` to `base_sha` before mutation and reject any ambiguous or missing ref.
2. Create the worktree with argument-safe Git invocation:
   ```bash
   git -C "$repo_root" worktree add -b "$branch_name" "$worktree_path" "$base_sha"
   ```

3. Verify the exact branch, head, and clean state, then return the `create` result:
   ```bash
   git -C "$worktree_path" branch --show-current
   git -C "$worktree_path" rev-parse HEAD
   git -C "$worktree_path" status --porcelain
   ```

## Procedure: List Worktrees

```bash
git -C "$repo_root" worktree list --porcelain
```

For each registered worktree record, resolve its canonical path and run `git -C "$registered_worktree_path" status --porcelain` before returning the row. Every list row has `path`, `branch`, `head_sha`, `clean`, `registration_status`, and `reason`. The canonical `${repo_root}` record is a readable `REGISTERED_PRIMARY` row and is not tested as a linked mutation target. A readable linked direct child of `${worktrees_root}` is `REGISTERED_LINKED`. Both readable variants have all identity fields populated and `reason=null`. An unreadable, vanished, or invalid linked row has `registration_status=BLOCKED`, a precise `reason`, and `null` for each unavailable `branch`, `head_sha`, or `clean` field; never assume such a row is clean. Set aggregate `status=PASS` when there are zero rows or every row is readable, `status=PARTIAL` for mixed readable and `BLOCKED` rows, and `status=BLOCKED` for a non-empty result containing only `BLOCKED` rows.

## Procedure: Sync Worktree After Rebase

After jj updates branch refs in the shared `.git/`, each affected worktree needs to sync:

```bash
git -C "$worktree_path" reset --keep "$branch_name"
```

Run sync only when the caller explicitly selected `task=sync`. Use the bounded section above to acquire an exclusive advisory mutation lock under the canonical Git common directory and hold it from the final clean check through reset and post-reset verification. Under that lock, require the canonical target to be a registered direct child of `${worktrees_root}`, require its checked-out branch to equal the validated `branch_name`, and require `git status --porcelain` to be empty; a dirty worktree is `BLOCKED:dirty-worktree`. Record the pre-reset head, use `reset --keep` so a concurrent uncooperative writer causes refusal rather than deletion, do not perform an implicit bulk reset, then verify and return the post-reset head and cleanliness before releasing the lock.

## Procedure: Remove Worktree

Resolve the exact registered target and record its canonical path, checked-out branch, and head SHA. Fetch the validated `base_branch`, set `base_ref` to its exact remote-tracking ref, and resolve `base_sha` from that ref before removal. Acquire the same exclusive advisory mutation lock under the canonical Git common directory used by `sync`. While holding it, re-read the exact registration and require its canonical path, branch, head SHA, base identity, and empty `git status --porcelain` to match the recorded identity. Dirty or changed `remove` requests always return `BLOCKED`, and this operator has no force-removal input. Hold the lock through the removal and both post-removal checks. For the normal path:

```bash
git -C "$repo_root" worktree remove "$worktree_path"
```

Verify both that the filesystem path is absent and that no exact canonical path record remains in `git -C "$repo_root" worktree list --porcelain`; only then return the pre-removal identity with `removed: true`.

## Procedure: Bulk Cleanup Merged Worktrees

Remove worktrees whose PRs were merged. **Verify PR status before deleting**
— don't assume a missing remote branch means merged (could be local-only).

Read records with `git -C "$repo_root" worktree list --porcelain`. For each registered direct child of `${worktrees_root}`, skip detached heads and validate its exact branch, canonical containment, current head SHA, expected base branch, and repository identity. Require exactly one provider PR whose target/base repository and head repository both equal the canonical worktree `OWNER/REPO` identity, whose base branch, head branch, and head OID match the validated values, and whose state is `MERGED`; missing, ambiguous, or mismatched PR evidence blocks removal. Before removal, acquire the same exclusive advisory mutation lock under the canonical Git common directory used by `sync`. While holding it, re-read the exact registered worktree record and revalidate canonical path, branch, head SHA, base identity, and empty `git status --porcelain` against the provider-matched identity. Abort that target with `status=BLOCKED` if any identity or cleanliness changed. Hold the lock through `git worktree remove` and the post-removal filesystem and registration checks. Dirty worktrees are always skipped with `status=BLOCKED`, `reason=dirty-worktree`, and `removed=false`; this operator never force-removes them or deletes local branches. Every result row has `worktree_path`, `branch`, `base_branch`, `base_sha`, `head_sha`, `clean`, `pr_repo`, `pr_head_repo`, `pr_url`, `pr_number`, `pr_state`, `removed`, `status`, and `reason`. A removed row has all identity fields populated, both PR repository identities equal to the worktree repository, `pr_state=MERGED`, `removed=true`, `status=PASS`, and `reason=merged-pr`. A skipped detached or invalid row has `removed=false`, `status=BLOCKED`, its precise reason, and `null` for each worktree or PR identity or cleanliness field that could not be established. Return one result row for every inspected target. Set aggregate `status=PASS` when there are zero targets or every row is `PASS`, `status=PARTIAL` when `PASS` and `BLOCKED` rows are mixed, and `status=BLOCKED` when a non-empty result contains only `BLOCKED` rows.

While still holding the lock, re-query the exact captured PR with `gh pr view "$pr_number" --repo "$pr_repo" --json url,number,state,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner`. Require its URL/number, target and head repository identities, base branch/OID, head branch/OID, and `state=MERGED` to remain exactly equal to the provider evidence that authorized removal. Only after that exact re-query passes may the operator run `git worktree remove`; any query failure or drift returns that target as `status=BLOCKED` without removal.

```bash
git -C "$repo_root" worktree remove "$worktree_path"
```

Keep the mutation lock held through this command and the post-removal filesystem and registration checks.

**Never** delete a worktree just because `git ls-remote` can't find the branch
— local-only branches and branches not yet pushed would be lost.

## Procedure: Open PR

In this procedure, `push_url` is the exact validated push URL returned for `push_remote`; remote-head reads use this URL directly and never resolve the remote's potentially different fetch URL.

After creating a worktree and making commits, resolve and validate `repo_slug` as the exact `OWNER/REPO` identity of `${repo_root}`. Set `push_remote=origin`, read its push URL with `git -C "$repo_root" remote get-url --push "$push_remote"`, normalize only supported GitHub SSH/HTTPS URL forms to `OWNER/REPO`, and require that identity to equal `repo_slug`; otherwise return `BLOCKED:push-remote-repository-mismatch` before any fetch, push, or PR mutation. Acquire the same exclusive advisory mutation lock under the canonical Git common directory used by `sync` before resolving worktree or ref identities, and hold it through the exact open-PR decision only (section A). Use the canonical bounded command and retirement rules above for both sections. Release section A and prove its owned tree terminal before any writer dispatch. Section B will reacquire before push, remote-head verification, PR creation or reuse, provider verification, and any owned-PR reconciliation. While holding it, require the worktree's current branch to equal `branch_name`; fetch `base_branch`, set `base_ref` to the exact remote-tracking ref, resolve `base_sha`, set `head_ref` to the exact local branch ref, and resolve `head_sha`. Immediately before the provider query, re-read the current branch, `base_ref`, and `head_ref` and require exact equality with `branch_name`, `base_sha`, and `head_sha`; any change is `BLOCKED:stale-open-pr-worktree-identity`. Then, while still holding the lock and before any push, query open PRs with `gh pr list --repo "$repo_slug" --state open --head "$branch_name" --base "$base_branch" --json url,number,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner` and capture the exact target/head repository identities, base/head branch pair, URL, number, state, draft flag, and full OIDs. Require `headRepository.nameWithOwner` and the owner/name reconstructed from `headRepositoryOwner.login` plus `headRepository.name` to equal `repo_slug`. More than one match is `BLOCKED:ambiguous-open-pr`. If one PR exists and every required provider field matches the repository, local, and base identities, reuse it without invoking `pr-writer`, pushing, or creating another PR. If one PR exists and any required field differs, return `BLOCKED:non-exact-open-pr` with its observed identity; do not invoke `pr-writer`, push, or call `gh pr create`. Only zero open query results enter the creation path. In that path, freeze the complete publication tuple using the executable identity guard below, then release section A. With no owned lock holder or waiter, dispatch `pr-writer` and require successful, non-empty title and body output before the first push:

```bash
# Keep writer output outside the untrusted worktree and private to this invocation.
umask 077
writer_dir=$(mktemp -d)
# Keep this directory until the writer is terminal; cleanup is not lock release.
set -o pipefail
agents -a ~/ai/agents/pr-writer.md \
  -p "$worktree_path" \
  --input "branch=$branch_name" \
  --input "base=$base_branch" \
  --input "base_ref=$base_ref" \
  --input "base_sha=$base_sha" \
  --input "head_ref=$head_ref" \
  --input "head_sha=$head_sha" \
  --input "repo_root=$worktree_path" \
  --input "output_path=$writer_dir/pr-body.md" \
  2>&1 | tee "$writer_dir/pr-writer.log"
pipeline_status=("${PIPESTATUS[@]}")
writer_rc=${pipeline_status[0]}
writer_log_rc=${pipeline_status[1]}
  # Optional: --input context_files=<comma-separated paths the writer should read for intent>
  # Optional: --input stack_parent_pr=<num> if base is another open PR's head branch
  # Optional: --input linear_issue_keys=<KEY> when a Linear key is known.
```

If either pipeline status is nonzero, return the common `BLOCKED` envelope with `reason=pr-writer-failed`, `mutation_state=none`, and the observed pipeline statuses. Do not execute any later command in this procedure. Likewise, missing or empty title/body files return `reason=pr-writer-output-invalid` before any remote mutation.

### Section B: reacquire and revalidate

After writer completion and file validation, reacquire the **same** canonical
lock with fresh acquisition/execution budgets. Before any push/create, run the
identity guard in `revalidate` mode with the frozen section-A tuple. Re-resolve
canonical repository/root/target/common-dir and exact registration, require
cleanliness and the checked-out branch, ref names and full base/head OIDs,
re-read fetch/push URLs and normalized repository identity, refresh the base,
and query provider repository identity and open candidates again. Any tuple
drift invalidates the writer result: `BLOCKED:stale-open-pr-worktree-identity`
without publication. Never update the frozen tuple to make the writer fit.
A newly appeared exact PR is reused and verified without push/create;
non-exact or ambiguous candidates block. Only an unchanged tuple and zero
candidates authorize publication. Keep section B locked through all following
mechanical commands, verification and bounded owned-PR reconciliation. The
writer stays outside this script; do not redispatch it inside the lock.

### Executable publication identity guard

Save this block as an attempt-private `publication-identity.py`, outside both
the worktree and `writer_dir`. Run it **inside** section A with `capture`, and
inside section B with `revalidate`, passing the same arguments:
`MODE SNAPSHOT REPO_ROOT WORKTREES_ROOT NAME BRANCH BASE REPO_SLUG`.
`SNAPSHOT` is a new private file (never writable by the writer by contract).
Preserve its bytes/hash between sections. Nonzero means stop, not publish.
The JSON action `reuse` takes the existing exact-PR verification path;
`create` alone permits the section-B publication commands below. This guard
collects live Git/provider evidence; comparing caller-authored JSON is not a
substitute. Branch-policy validation remains a required precondition.

```python
# worktree-publication-identity-v1
import json
import pathlib
import re
import subprocess
import sys


def command(*args):
    # Preserve the inherited exclusion descriptor through Git/provider children.
    return subprocess.check_output(args, text=True, close_fds=False).rstrip("\n")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def github_slug(url):
    match = re.fullmatch(r"(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", url)
    require(match is not None, "push-remote-repository-mismatch")
    return match[1]


def registration(repo, target):
    records = command("git", "-C", repo, "worktree", "list", "--porcelain", "-z").split("\0\0")
    rows = [dict(field.split(" ", 1) if " " in field else (field, "")
                 for field in record.split("\0") if field) for record in records if record]
    matches = [row for row in rows if pathlib.Path(row["worktree"]).resolve() == target]
    require(len(matches) == 1, "stale-open-pr-worktree-identity")
    return matches[0]


def collect(repo_arg, root_arg, name, branch, base, slug):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name), "unsafe-name")
    repo = str(pathlib.Path(repo_arg).resolve(strict=True))
    root = pathlib.Path(root_arg).resolve(strict=True)
    target = (root / name).resolve(strict=True)
    require(target.parent == root and str(target) != repo, "unsafe-worktree-target")
    command("git", "check-ref-format", "--branch", branch)
    command("git", "check-ref-format", "--branch", base)
    common = command("git", "-C", repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    target_common = command("git", "-C", str(target), "rev-parse", "--path-format=absolute", "--git-common-dir")
    require(pathlib.Path(common).resolve() == pathlib.Path(target_common).resolve(), "stale-open-pr-worktree-identity")
    push_url = command("git", "-C", repo, "remote", "get-url", "--push", "origin")
    require(github_slug(push_url) == slug, "push-remote-repository-mismatch")
    fetch_url = command("git", "-C", repo, "remote", "get-url", "origin")
    base_ref, head_ref = "refs/remotes/origin/" + base, "refs/heads/" + branch
    command("git", "-C", repo, "fetch", "--no-tags", "origin", "+refs/heads/" + base + ":" + base_ref)
    row = registration(repo, target)
    require(command("git", "-C", str(target), "symbolic-ref", "--quiet", "HEAD") == head_ref, "stale-open-pr-worktree-identity")
    require(command("git", "-C", str(target), "status", "--porcelain=v1", "-z") == "", "dirty-worktree")
    base_sha = command("git", "-C", repo, "rev-parse", "--verify", base_ref + "^{commit}")
    head_sha = command("git", "-C", str(target), "rev-parse", "--verify", head_ref + "^{commit}")
    require(row.get("branch") == head_ref and row.get("HEAD") == head_sha, "stale-open-pr-worktree-identity")
    require(command("git", "-C", str(target), "rev-parse", "HEAD") == head_sha, "stale-open-pr-worktree-identity")
    provider = json.loads(command("gh", "repo", "view", slug, "--json", "id,nameWithOwner,url"))
    require(provider.get("nameWithOwner") == slug and provider.get("id") and provider.get("url"), "push-remote-repository-mismatch")
    return dict(repo_root=repo, worktrees_root=str(root), worktree_path=str(target),
                common_dir=str(pathlib.Path(common).resolve()), registration=row,
                branch=branch, base_branch=base, base_ref=base_ref, head_ref=head_ref,
                base_sha=base_sha, head_sha=head_sha, clean=True, push_remote="origin",
                push_url=push_url, fetch_url=fetch_url, repo_slug=slug, provider=provider)


def recheck_refs(identity):
    repo, target = identity["repo_root"], identity["worktree_path"]
    require(command("git", "-C", target, "symbolic-ref", "--quiet", "HEAD") == identity["head_ref"], "stale-open-pr-worktree-identity")
    require(command("git", "-C", repo, "rev-parse", "--verify", identity["base_ref"] + "^{commit}") == identity["base_sha"], "stale-open-pr-worktree-identity")
    require(command("git", "-C", target, "rev-parse", "--verify", identity["head_ref"] + "^{commit}") == identity["head_sha"], "stale-open-pr-worktree-identity")


def candidates(identity):
    recheck_refs(identity)
    fields = "url,number,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner"
    return json.loads(command("gh", "pr", "list", "--repo", identity["repo_slug"],
                              "--state", "open", "--head", identity["branch"],
                              "--base", identity["base_branch"], "--json", fields))


def decision(identity, rows):
    require(isinstance(rows, list), "non-exact-open-pr")
    require(len(rows) <= 1, "ambiguous-open-pr")
    if not rows:
        return dict(action="create", identity=identity, candidate=None)
    row, slug = rows[0], identity["repo_slug"]
    head = row.get("headRepository") or {}
    owner = row.get("headRepositoryOwner") or {}
    number = row.get("number")
    require(type(number) is int and number > 0, "non-exact-open-pr")
    expected = dict(url=f"https://github.com/{slug}/pull/{number}", state="OPEN", isDraft=True,
                    baseRefName=identity["base_branch"], baseRefOid=identity["base_sha"],
                    headRefName=identity["branch"], headRefOid=identity["head_sha"])
    require(row.get("isDraft") is True and all(row.get(key) == value for key, value in expected.items()), "non-exact-open-pr")
    require(head.get("nameWithOwner") == slug and
            owner.get("login", "") + "/" + head.get("name", "") == slug, "non-exact-open-pr")
    return dict(action="reuse", identity=identity, candidate=row)


def freeze_snapshot(path, identity):
    with open(path, "x") as output:
        json.dump(identity, output, sort_keys=True)


def main():
    mode, snapshot, *inputs = sys.argv[1:]
    require(mode in ("capture", "revalidate") and len(inputs) == 6, "invalid-publication-guard-input")
    current = collect(*inputs)
    if mode == "revalidate":
        require(json.loads(pathlib.Path(snapshot).read_text()) == current, "stale-open-pr-worktree-identity")
    result = decision(current, candidates(current))
    if mode == "capture" and result["action"] == "create":
        freeze_snapshot(snapshot, current)
    print(json.dumps(result, sort_keys=True))


try:
    main()
except (ValueError, OSError, subprocess.CalledProcessError) as error:
    print("BLOCKED:" + str(error), file=sys.stderr)
    sys.exit(1)
```

Use this executable check on the observed writer pipeline statuses and files
before admitting section B (and again at the start of section B):

```bash
# worktree-writer-output-v1
[[ "$writer_rc" == 0 && "$writer_log_rc" == 0 ]] || {
  echo 'BLOCKED:pr-writer-failed' >&2; exit 65;
}
for writer_file in "$writer_dir/pr-body.md" "$writer_dir/pr-body.md.title"; do
  [[ -f "$writer_file" && -s "$writer_file" && ! -L "$writer_file" ]] || {
    echo 'BLOCKED:pr-writer-output-invalid' >&2; exit 65;
  }
  [[ "$(dirname -- "$(realpath -e -- "$writer_file")")" == "$(realpath -e -- "$writer_dir")" ]] || exit 65
done
```

The section-B script defines `publish_new_pr` from the push/create/readback/
reconciliation commands below and `verify_reused_pr` from the exact captured
PR verification path. Load all mechanical identity arguments (including `worktree_path`, `push_url`,
`base_sha` and `head_sha`) only from `publication_decision.identity`, never from
unvalidated ambient shell variables. Both consume `publication_decision`; neither dispatches
an agent. Use this gate to select exactly one mechanical path without releasing
the lock or returning to the model between decision and mutation:

```bash
# worktree-publication-dispatch-v1
publication_decision=$(python3 "$publication_identity_script" revalidate "$snapshot" \
  "$repo_root" "$worktrees_root" "$name" "$branch_name" "$base_branch" "$repo_slug") || exit 76
publication_action=$(printf '%s' "$publication_decision" | python3 -c 'import json,sys; print(json.load(sys.stdin)["action"])') || exit 76
case "$publication_action" in
  create) publish_new_pr ;;
  reuse) verify_reused_pr ;;
  *) exit 76 ;;
esac
```

```bash
# Validate both writer files as non-empty before this first remote mutation.
git -C "$worktree_path" push "$push_url" \
  "refs/heads/$branch_name:refs/heads/$branch_name"
remote_head_record=$(git ls-remote --exit-code --refs "$push_url" "refs/heads/$branch_name")
# Require exactly one record whose ref is refs/heads/$branch_name and OID is head_sha.

set +e
created_pr_output=$(gh pr create --repo "$repo_slug" --draft \
  --head "$branch_name" \
  --base "$base_branch" \
  --title "$(cat "$writer_dir/pr-body.md.title")" \
  --body-file "$writer_dir/pr-body.md")
create_rc=$?
set -e
```

Include `--input linear_issue_keys=<KEY>` only when a Linear key is known to the manual operator. Omit when no key is known; no close footer will be emitted in that case.

Before the push, require the writer command to succeed and both `$writer_dir/pr-body.md.title` and `$writer_dir/pr-body.md` to exist, be non-empty regular files, not be symlinks, and have canonical `writer_dir` as their direct parent. A writer or file-validation failure returns the common `BLOCKED` envelope with `mutation_state=none`; it does not push. Never invoke `gh pr create` with missing/empty writer output or a hand-authored body. After the push, parse `remote_head_record`, require exactly one tab-delimited record whose ref is exactly `refs/heads/$branch_name` and whose OID equals `head_sha`, and return `BLOCKED:remote-head-unverified` with `mutation_state=unknown` before PR creation if `git ls-remote` fails, returns another shape, or reports another OID. Treat `created_pr_output` as a usable URL only when `create_rc=0` and it parses as exactly one PR URL in `repo_slug`; set `created_pr_url` to that exact URL and capture its number before postcondition verification. The writer's audience-and-content rules (`~/ai/agents/pr-writer.md`) exist because hand-written bodies routinely leak internal jargon ("wave N", "Slot B", work-unit ids, planning-artifact paths) that an external reviewer can't act on.

For a reused or newly created PR, query that exact captured URL/number from `repo_slug` and require `state=OPEN`, `draft=true`, the requested base/head branches, provider base OID equal to the captured `base_sha`, and provider head OID equal to the captured `head_sha`, then return that provider identity. If `create_rc` is nonzero or `created_pr_output` is empty, malformed, or not one usable URL, perform one bounded exact repository/base/head `--state all` requery for diagnostic evidence only. The requery cannot prove which actor created a discovered PR, even under the local mutation lock. Do not close any PR from that evidence; return `BLOCKED` with `mutation_state=unknown` and all observed candidates. Never report success from unusable create output.

If a newly created PR with a usable URL fails any postcondition, run `gh pr close "$created_pr_url" --repo "$repo_slug" --comment "Closed automatically after open-pr postcondition verification failed."` and re-query that exact PR. Use `mutation_state=reconciled` only when the close succeeds and the exact re-query succeeds with `state=CLOSED`; include a machine-readable `reconciliation` object containing the close result and closed provider identity. If close fails, re-query fails, or the exact PR remains open, return `BLOCKED` with `mutation_state=unknown` and the last observed identity. Never leave an identified unverified open PR or report success as though reconciliation completed. If a reused PR fails verification, leave it unchanged and return `BLOCKED` with `mutation_state=none` and its observed identity. A retry re-runs the exact open-PR query and reuses a valid exact match rather than creating another PR.

Cleanup `writer_dir` only after the writer is terminal and both section handles
(if admitted) are retired, on success and on every failure path. Writer failure
admits no section B and never leaves a lock waiter. Interrupted writer output
is not a publication candidate. Before replacement work, prove previous handles
terminal; Ctrl-C on an outer session is not proof.

## Result Contract

Return one `worktree-operation-result-v1` JSON object for every task. `list` includes one canonical path/branch/head SHA/observed-cleanliness/status row per registered worktree. `create` includes canonical repository/worktree paths, branch, base branch and SHA, head SHA, and `clean: true`. `sync` includes canonical path, branch, pre/post head SHA, and post-sync cleanliness. `remove` includes the pre-removal path, branch, base branch/SHA, head SHA, and cleanliness plus `removed: true`. `bulk-cleanup` includes one result row per inspected target with every declared key, explicit `removed`, `status`, and `reason`, and `null` only for skipped-row identity fields that could not be established; aggregate status follows the zero/all-pass, mixed, and all-blocked mapping below. `open-pr` includes `status: PASS`, `provider_state: OPEN`, exact repository and PR URL/number, base/head branches, base and head SHAs, and `draft: true`. Never report success from command text alone; verify the resulting filesystem, Git, and provider state first.

For each admitted critical section, include `lock_sections` evidence: canonical
lock path, script path/hash, acquire/hold/cleanup limits, exact handle and owner
identity, terminal runtime status/reason/exit code, and `owned_tree_retired`.
A mutating PASS (or PASS row) requires `owned_tree_retired=true` for every
admitted section; include an empty array when no section was admitted. Missing
or inconclusive retirement evidence cannot become PASS. Preserve the original
terminal records on interruption and handoff.

Every task that blocks outside a row-based partial result uses one common envelope: `schema=worktree-operation-result-v1`, the selected `task`, `status=BLOCKED`, a stable `reason`, and `mutation_state`. `mutation_state` is `none` when no side effect needs reconciliation, `reconciled` only when the result also includes machine-readable `reconciliation` evidence proving the side effect was undone or closed, and `unknown` only when an external mutation may have occurred but cannot be uniquely identified without risking an unrelated resource. Include any available `observed_identity`; unavailable identity fields are `null`, never omitted or invented. A `BLOCKED` envelope is terminal non-success even when reconciliation succeeded.

```yaml
schema: worktree-operation-result-v1
required: [schema, task, status]
variants:
  blocked:
    status: BLOCKED
    required: [reason, mutation_state, observed_identity]
    mutation_state: [none, reconciled, unknown]
    observed_identity: object | null
    reconciliation: object | null
    reconciliation_required_when: {mutation_state: reconciled}
  list:
    status: PASS | PARTIAL | BLOCKED
    required: [worktrees]
    aggregate_status: {zero_rows: PASS, all_rows_readable: PASS, mixed_readable_blocked: PARTIAL, nonempty_all_rows_blocked: BLOCKED}
    worktree_row_required: [path, branch, head_sha, clean, registration_status, reason]
    readable_row: {registration_status: REGISTERED_PRIMARY | REGISTERED_LINKED, reason: null, nullable: []}
    blocked_row: {registration_status: BLOCKED, nullable: [branch, head_sha, clean]}
  create:
    status: PASS
    required: [repo_root, worktree_path, branch, base_branch, base_sha, head_sha, clean]
  sync:
    status: PASS
    required: [worktree_path, branch, pre_head_sha, post_head_sha, clean]
  remove:
    status: PASS
    required: [worktree_path, branch, base_branch, base_sha, head_sha, clean, removed]
    fixed: {removed: true}
  bulk-cleanup:
    status: PASS | PARTIAL | BLOCKED
    required: [results]
    aggregate_status: {zero_targets: PASS, all_rows_pass: PASS, mixed_pass_blocked: PARTIAL, nonempty_all_rows_blocked: BLOCKED}
    result_row_required: [worktree_path, branch, base_branch, base_sha, head_sha, clean, pr_repo, pr_head_repo, pr_url, pr_number, pr_state, removed, status, reason]
    removed_row: {pr_state: MERGED, removed: true, status: PASS, reason: merged-pr, nullable: []}
    skipped_row: {removed: false, status: BLOCKED, nullable: [branch, base_branch, base_sha, head_sha, clean, pr_repo, pr_head_repo, pr_url, pr_number, pr_state]}
  open-pr:
    status: PASS
    required: [repo, head_repo, pr_url, pr_number, provider_state, draft, base_branch, base_sha, head_branch, head_sha]
    fixed: {provider_state: OPEN, draft: true}
```

## Stop Conditions

- Return `BLOCKED` if: worktree already exists with that name, branch already exists
- Return `NEEDS_INPUT` if: unclear which base branch to use
