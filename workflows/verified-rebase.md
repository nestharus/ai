---
workflow:
  id: verified-rebase
workflow_dispatch_contract:
  orchestrator: jj-operator
  inputs:
  - BRANCH and TARGET refs for the rebase
  - optional SOURCE and PARENT_BUNDLE for scoped or stacked rebases
  - repo_root, external planning_dir, selected endpoint owner_invocation_id, and fresh attempt_id UUID
  expectations:
  - produces a deterministic bundle for rebase review
  - computes mechanical provenance from predicted tree, actual tree, conflicts, and range-diff output
  - does not push and does not resolve conflicts
  - selected endpoint directly owns all phases; no same-operation redispatch
  - atomic persistent substrate/Git common-dir/jj store reservation survives suspension and interruption
  - unknown ownership, intervening state, or partial records fail closed without cleanup
  outputs:
  - bundle under <planning_dir>/<owner_invocation_id>/<attempt_id>/
  - identity-bound result.json with separate mechanical verdict and execution terminal; no push eligibility
  - attempt-specific refs/pre-rebase/<attempt_id> anchor and owner-fenced rollback.sh
  non_goals:
  - does not provide a plain rebase fallback
  - does not decide whether the caller should push
  - does not judge semantic correctness of conflict resolutions
---
# Verified Rebase

## Declared roles

`orchestration`, `validator`, `parser`, `mapper`, `formatter`.

This file-local declaration is explicit per `~/ai/conventions/code-quality.md` § Declared roles. `orchestration` covers the ordered verified-rebase phases and direct execution by the selected `jj-operator` endpoint. `validator` covers preflight checks, stop conditions, mechanical verdict production, rollback preconditions, and gate ownership. `parser` covers jj/git command output, patch path sets, `refs.json`, `range-diff.txt`, conflict artifact records, and parent-bundle inputs. `mapper` covers ref-to-artifact, conflict-path-to-conflict-file, residual-path-to-conflict-path, and parent-bundle relationships. `formatter` covers bundle files, summary output, stdout verdicts, and rollback helper text.

## Intrinsic-surface declarations

These declarations are explicit per `~/ai/conventions/code-quality.md` § Intrinsic-surface declarations. The workflow's purpose is to predicate, filter, and select over jj CLI state, git CLI state, the verified-rebase bundle contract, and the workflow/operator/convention references that define that local rebase surface.

```yaml
intrinsic_surface_declarations:
  - component: workflows/verified-rebase.md
    role: intrinsic-surface
    Domain: verified_rebase_jj_cli
    Owns:
      - jj status
      - jj log
      - jj git fetch
      - jj op log
      - jj rebase
      - jj resolve --list
      - jj file show
      - jj op restore
  - component: workflows/verified-rebase.md
    role: intrinsic-surface
    Domain: verified_rebase_git_cli
    Owns:
      - git merge-base
      - git rev-parse
      - git update-ref
      - git merge-tree
      - git diff
      - git range-diff
      - git log
      - git push --force-with-lease
      - refs/pre-rebase/<attempt_id>
  - component: workflows/verified-rebase.md
    role: intrinsic-surface
    Domain: verified_rebase_bundle_artifact_contract
    Owns:
      - summary.md
      - refs.json
      - target-delta.patch
      - main-delta.patch
      - branch-intended.patch
      - branch-actual.patch
      - residual.patch
      - range-diff.txt
      - conflict-artifacts/files.txt
      - conflict-artifacts/<slug>.conflict
      - jj-pre-op-id.txt
      - rollback.sh
      - <planning_dir>/<owner_invocation_id>/<attempt_id>/
      - merge-tree.out
      - merge-tree.err
      - merge-tree.status
      - jj-op-log-before.txt
      - jj-op-log-after.txt
      - parent-delta.patch
      - summary.md.fragment
      - parent-pointer-check
      - result.json
      - owner.json
      - state.json
      - rollback-result.json
      - tools/verified_rebase.py
  - component: workflows/verified-rebase.md
    role: intrinsic-surface
    Domain: verified_rebase_workflow_convention_operator_refs
    Owns:
      - agents/jj-operator.md
      - models/roles.md
      - workflows/agents-cli.md
      - conventions/no-backwards-compatibility.md
      - conventions/no-operator-behavior-override-in-dispatch.md
      - conventions/gate-ownership.md
      - ../.build/VR-01-verified-rebase-proposal.md
      - agents/commit-hygiene-operator.md
      - agents/worktree-operator.md
  - component: workflows/verified-rebase.md
    role: intrinsic-surface
    Domain: verified_rebase_helper_commands
    Owns:
      - mkdir
      - jq
      - grep
      - head
      - tr
      - cp
      - chmod
      - cat
      - date
```

Standard POSIX-shell helpers used by the workflow's reference shell snippets.

Produce a deterministic artifact bundle for every rebase so a reviewer inspects O(residual) content instead of O(full-diff), with a cheap local rollback when the bundle shows unacceptable residuals.

This is the single rebase path. The plain `jj rebase` procedure is retired — see [`~/ai/agents/jj-operator.md`](../agents/jj-operator.md) `Procedure: Verified Rebase`.

Model assignments: [`~/ai/models/roles.md`](../models/roles.md). CLI: [`~/ai/workflows/agents-cli.md`](agents-cli.md). Conventions: [`~/ai/conventions/no-backwards-compatibility.md`](../conventions/no-backwards-compatibility.md).

## Workflow Dispatch Surface

### Orchestrator

jj-operator

### Inputs

- BRANCH and TARGET refs for the rebase
- optional SOURCE and PARENT_BUNDLE for scoped or stacked rebases
- repo_root, external planning_dir, selected endpoint owner_invocation_id, fresh attempt_id UUID

### Expectations

- selected endpoint directly owns all phases; no same-operation redispatch
- persistent substrate reservation survives suspension and interruption
- unknown/partial ownership and intervening state block without cleanup
- produces a deterministic bundle for rebase review
- computes mechanical provenance from predicted tree, actual tree, conflicts, and range-diff output
- does not push and does not resolve conflicts

### Outputs

- bundle under <planning_dir>/<owner_invocation_id>/<attempt_id>/
- identity-bound result.json: separate mechanical verdict and execution terminal; no push eligibility
- attempt-specific refs/pre-rebase/<attempt_id> anchor and owner-fenced rollback.sh

### Non-goals

- does not provide a plain rebase fallback
- does not decide whether the caller should push
- does not judge semantic correctness of conflict resolutions

## Inputs

- `repo_root`: explicit colocated Git/jj substrate, not inferred from launch cwd.
- `planning_dir`: existing external planning root, disjoint from any checkout or Git/jj metadata.
- `owner_invocation_id` / shell `OWNER_ID`: this selected endpoint's authentic runner UUID, read from its native runtime identity after selection (not the caller/root UUID); unchanged on resume.
- `attempt_id` / shell `ATTEMPT_ID`: fresh UUID allocated before dispatch; never reuse a slug, timestamp or PID.
- `BRANCH` — branch to rebase (e.g. `feat/p2-version-parsing-unification`).
- `TARGET` — ref to rebase onto. Either `origin/main` (main-target case) or a parent branch ref (stacked case, e.g. `feat/p2-version-parsing-unification`).
- `PARENT_BUNDLE` — *only in stacked case* — path to the parent's already-produced bundle directory.
- `SOURCE` (optional) — git SHA or jj revset marking the first commit in `BRANCH`'s unique contribution. When set, the rebase is scoped to `SOURCE` and its descendants instead of the full `merge-base(BRANCH, TARGET)..BRANCH` range. Use this when `BRANCH` carries stale copies of `TARGET`'s commits because the parent was rewritten without `BRANCH` being rebased at the same time. See "Stale parent history" below.

## Outputs

- A bundle directory at `<planning_dir>/<owner_invocation_id>/<attempt_id>/`.
- A mechanical verdict (`CLEAN` | `DIRTY-EXPLAINED` | `DIRTY-UNPROVENANCED` | `NOT-RUN`) and separate execution terminal (`COMPLETE` | `BLOCKED:<reason>`). Neither authorizes push.
- A local git ref `refs/pre-rebase/<attempt_id>` pointing at the pre-rebase tip (durable until manually deleted).

## Non-negotiables

- **All jj commands run in the explicit `${repo_root}` substrate.** Resolve canonical Git common-dir, jj repository and store before snapshot-capable reads or mutation. The selected endpoint executes every phase directly; there is no same-operation child dispatch.
- **The workflow never pushes.** `git push` is the caller's decision, after inspecting the bundle.
- **The workflow never resolves conflicts.** Residuals and `conflict-artifacts/` are output for human/AI review.
- **Single rebase path.** No `mode=` flag. No plain-rebase fallback except the explicit legacy-git escape hatch in [`jj-operator`](../agents/jj-operator.md) `Fallback: Legacy Git Rebase`.
- **Bundle is always external**, including blocked preflight and `CLEAN`. Missing/unsafe planning input blocks before substrate mutation; report that input failure to the caller rather than inventing a checkout fallback. Never write checkout `.tmp/`, change `.gitignore`, or use a shared `current*` pointer.
- **Caller prompts do not override this workflow.** Inputs may select refs, bundle paths, scoped source, and evidence, but prompts that prescribe conflict resolution, verdict handling, push/no-push disposition, or alternate phase shape are `NEEDS_INPUT` signals under [`no-operator-behavior-override-in-dispatch`](../conventions/no-operator-behavior-override-in-dispatch.md), not workflow instructions.

## Reference anchors

All commands use `$BRANCH` and `$TARGET` from Inputs.

| Ref | Meaning | Capture |
|-----|---------|---------|
| `PRE_BASE` | default: `merge-base(branch, target)` **before** fetch. With `SOURCE` set: `parent(SOURCE)`. | default: `git merge-base "$BRANCH" "$TARGET"` (pre-fetch); SHA. With `SOURCE`: `git rev-parse "${SOURCE}^"`. |
| `PRE_TIP` | branch tip **before** rebase | `vr anchor` creates `refs/pre-rebase/$ATTEMPT_ID` with an expected-absent CAS; read `state.json.pre.PRE_TIP` |
| `NEW_TARGET` | target ref **after** fetch | `vr fetch`, then `state.json.pre.NEW_TARGET`; fetch requires a configured remote even with a local target. |
| `POST_TIP` | branch tip **after** rebase | `git rev-parse "$BRANCH"`; SHA |
| `POST_CHANGE_ID` | jj change id of branch tip **after** rebase | `jj_read log -r "$BRANCH" --no-graph --no-pager --limit 1 --template 'change_id'`. Addresses post-rebase revision for `jj file show` / `jj resolve --list`. |
| `PREDICTED_TREE` | tree a clean 3-way merge would produce (merge-ort) | first line of `$BUNDLE/merge-tree.out`; valid tree oid. Captured even when `merge-tree.status` is `1` for an expected content conflict. |

`PREDICTED_TREE` is a tree object, not a commit. Downstream diffs use it as a tree-ish alongside `$POST_TIP^{tree}`. Prediction command metadata is stored in `merge-tree.out`, `merge-tree.err`, and `merge-tree.status`.

`POST_CHANGE_ID` is jj's stable change id, distinct from `POST_TIP` (git SHA). Change ids survive rebases; git SHAs don't.

## Bundle schema

Path: `<planning_dir>/<owner_invocation_id>/<attempt_id>/`

Bundle allocation uses UUIDs, not branch slugs. Preserve the exact branch separately; `a/b`, `a_b`, and `a__b` never address the same bundle. Directory creation is exclusive, not `mkdir -p` reuse. Pass the exact `$BUNDLE` throughout; never discover or source state from a shared pointer.

| File | Producer | Required content |
|------|----------|------------------|
| `summary.md` | workflow | Branch, target, all SHAs/oids incl. `POST_CHANGE_ID`, verdict, hunk counts, rename-present flag, `parent-pointer-check` line for stacked, one-liner rollback instruction |
| `refs.json` | workflow | `{branch, target, PRE_BASE, PRE_TIP, NEW_TARGET, POST_TIP, POST_CHANGE_ID, PREDICTED_TREE, timestamp, parent_bundle?, verdict}` |
| `target-delta.patch` (named `main-delta.patch` when `TARGET=origin/main`) | `git diff "$PRE_BASE" "$NEW_TARGET" --find-renames` | What the target introduced during the wait |
| `branch-intended.patch` | `git diff "$PRE_BASE" "$PRE_TIP" --find-renames` | What the branch intended to change |
| `branch-actual.patch` | `git diff "$NEW_TARGET" "$POST_TIP" --find-renames` | What the branch changes after rebase |
| `residual.patch` | `git diff "$PREDICTED_TREE" "$POST_TIP^{tree}" --find-renames` | **Provenance check.** See "Verdict" below. |
| `merge-tree.out` | `git merge-tree --write-tree --merge-base="$PRE_BASE" "$PRE_TIP" "$NEW_TARGET"` | Prediction stdout. First line is the accepted `PREDICTED_TREE` when the workflow continues; later lines may contain conflict descriptors. |
| `merge-tree.err` | `git merge-tree --write-tree --merge-base="$PRE_BASE" "$PRE_TIP" "$NEW_TARGET"` | Prediction stderr. |
| `merge-tree.status` | workflow | Decimal prediction command status, one line. `0` is success, `1` is expected content-conflict status when line 1 of `merge-tree.out` is a valid tree oid, and anything outside `{0, 1}` is `BLOCKED:merge-tree-failed`. |
| `range-diff.txt` | `git range-diff "$PRE_BASE..$PRE_TIP" "$NEW_TARGET..$POST_TIP"` | Per-commit correspondence; catches drops/reorders |
| `conflict-artifacts/files.txt` | Row-validation adapter over `conflict-artifacts/jj-resolve-list-raw.txt` | Row-validation adapter output. One validated bare conflicted repository path per non-empty line, produced from `conflict-artifacts/jj-resolve-list-raw.txt` per § 6. Empty if no conflicts. |
| `conflict-artifacts/jj-resolve-list-raw.txt` | `jj resolve --list -r "$POST_CHANGE_ID" --no-pager` | Raw `jj resolve --list -r "$POST_CHANGE_ID" --no-pager` stdout sidecar; preserved for diagnostics. May contain jj's human-rendered `path<TAB>N-sided conflict` rows. NOT consumed by verdict computation, `.conflict` artifact production, or operator inspection prose. |
| `conflict-artifacts/<slug>.conflict` | `jj file show -r "$POST_CHANGE_ID" "$path"` | jj's first-class conflict representation, per conflicted path |
| `jj-op-log-before.txt` | `jj_read op log --limit 20 --no-pager` pre-rebase | Audit trail |
| `jj-op-log-after.txt` | `jj_read op log --limit 20 --no-pager` post-rebase | Audit trail |
| `jj-pre-op-id.txt` | `state.json.pre.JJ_PRE_OP_ID` (captured post-fetch, pre-rebase) | Rollback target |
| `rollback.sh` | workflow (template below) | Pinned helper/path/owner/attempt invocation, no bare restore |
| `owner.json` | internal helper | Immutable invocation UUID, attempt UUID, exact branch/target/source, bundle, canonical path + device/inode substrate identities, helper hash and attempt anchor |
| `state.json` | internal helper | Durable operation checkpoint: full refs, HEAD, jj operation; completed labels and in-flight command intent; pre refs / post-fetch rollback operation |
| `result.json` | internal helper | Owner, checkpoint, pre/post identities, mechanical verdict, execution terminal, evidence hashes, no push eligibility, pending caller synchronization; topology validation is operator-owned |
| `rollback-result.json` | internal helper | Exact restored checkpoint; repeat is validated against current ownership/state, not a flag |
| `parent-delta.patch` *(stacked only)* | copy of `$PARENT_BUNDLE/branch-actual.patch` | Parent's shift — what the child inherits from its parent's rebase |

## Phases

Phases 1–11. All run in `${repo_root}`. `$BUNDLE` is the bundle directory created in phase 1.

### 1. Allocate, reserve, then preflight

Use the internal helper shipped beside this workflow. This is a local CLI, not an
agent dispatch. `$VR_HELPER` is its absolute path in the authoritative checkout;
keep that exact helper available (owner record pins its hash). All logs, prompts,
state and diagnostic bundles go under the externally supplied planning root.

```bash
set -euo pipefail
SOURCE_ARGS=()
if [ -n "${SOURCE:-}" ]; then SOURCE_ARGS=(--source "$SOURCE"); fi
BUNDLE=$(python3 "$VR_HELPER" allocate --repo "$repo_root" --planning "$planning_dir" \
  --owner-id "$OWNER_ID" --attempt-id "$ATTEMPT_ID" --branch "$BRANCH" --target "$TARGET" \
  "${SOURCE_ARGS[@]}" | jq -er .)
# In bash, define local command helpers once; never source generated shell state.
vr() { python3 "$VR_HELPER" "$1" --bundle "$BUNDLE" --owner-id "$OWNER_ID" --attempt-id "$ATTEMPT_ID" "${@:2}"; }
jj_read() { vr inspect >/dev/null && jj --ignore-working-copy --at-operation "$(jq -r .checkpoint.op "$BUNDLE/state.json")" --no-pager "$@"; }
cd "$repo_root"
vr check
```

Allocation uses nonblocking transition locks and persistent records in **all**
canonical Git common-dir / jj repository / jj store resources, independent of
branch name. The operation-wide reservation is not the short-lived OS lock:
process exit or suspension does not free it. A partial record, unknown owner,
live transition, or unavailable resource blocks before rebase or snapshot.
Owner/attempt path collisions never overwrite bytes. An allocation contender
writes only its own external `allocation-blocked.json`.

Preflight after reservation:
- Require clean tracked/index/untracked/ignored source inventory and an empty jj
  working-copy change. No stash, ignore repair, reset, or automatic cleanup.
- Verify `$BRANCH` and `$TARGET` exist; verify `$SOURCE` exists and is an ancestor
  of `$BRANCH` when supplied. Use `jj_read` for jj inspection.
- Preserve all foreign files. On unexpected state diagnose using Git no-optional-
  locks reads and pinned no-snapshot jj reads, never ordinary `jj status`.

On a preflight block, write the reason externally and use phase 10's `BLOCKED`
terminal path if current ownership/checkpoint still validates. Otherwise preserve
the reservation and partial evidence and return `BLOCKED:recovery-required`.
Missing planning inputs have no safe bundle destination: return the error without
writing to the substrate. Never take over by age or PID.

### 2. Capture PRE state

```bash
vr anchor
PRE_BASE=$(jq -er .pre.PRE_BASE "$BUNDLE/state.json")
PRE_TIP=$(jq -er .pre.PRE_TIP "$BUNDLE/state.json")
jj_read op log --limit 20 > "$BUNDLE/jj-op-log-before.txt"
```

The helper creates `refs/pre-rebase/$ATTEMPT_ID` with an expected-absent CAS.
It never overwrites another attempt's anchor, even for the same branch.

### 3. Fetch

```bash
vr fetch
NEW_TARGET=$(jq -er .pre.NEW_TARGET "$BUNDLE/state.json")
JJ_PRE_OP_ID=$(jq -er .pre.JJ_PRE_OP_ID "$BUNDLE/state.json")
printf '%s\n' "$JJ_PRE_OP_ID" > "$BUNDLE/jj-pre-op-id.txt"
```

Fetch is journaled under the reservation. Its exact post-fetch operation is the
rollback baseline. A failed/ambiguous command leaves an in-flight record and
reservation; no automatic replay. Missing origin is a real fetch failure, not a
successful local-target no-op.

Before each subsequent phase, run `vr check` (or `vr inspect` for blocked,
no-snapshot diagnostics). Never advance after a failed check. All mutations use
the helper, which journals intent before execution and readback afterward.

### 4. Predict

```bash
if git merge-tree --write-tree --merge-base="$PRE_BASE" "$PRE_TIP" "$NEW_TARGET" \
    > "$BUNDLE/merge-tree.out" \
    2> "$BUNDLE/merge-tree.err"; then
  MERGE_TREE_RC=0
else
  MERGE_TREE_RC=$?
fi
echo "$MERGE_TREE_RC" > "$BUNDLE/merge-tree.status"

PREDICTED_TREE=$(head -n 1 "$BUNDLE/merge-tree.out" | tr -d '[:space:]')
if ! echo "$PREDICTED_TREE" | grep -Eq '^[0-9a-f]{40}$|^[0-9a-f]{64}$'; then
  echo "BLOCKED:merge-tree-failed: empty or invalid PREDICTED_TREE on rc=$MERGE_TREE_RC" >&2
  exit 1
fi
if [ "$MERGE_TREE_RC" -ne 0 ] && [ "$MERGE_TREE_RC" -ne 1 ]; then
  echo "BLOCKED:merge-tree-failed: unexpected exit $MERGE_TREE_RC" >&2
  exit 1
fi
```

`merge-tree` metadata is captured before classification: stdout in `merge-tree.out`, stderr in `merge-tree.err`, and the decimal exit code in `merge-tree.status`. On the B1 success path, `merge-tree.status` is `0` and line 1 of `merge-tree.out` is a valid tree oid, so `PREDICTED_TREE` is set from that line and the workflow continues. On the B2 content-conflict path, `merge-tree.status` is `1` and line 1 is still a valid tree oid; Git emits the predicted tree oid on line 1 and conflict descriptors on subsequent lines, so `PREDICTED_TREE` is set and the workflow continues to rebase. On the B3 real-failure path, status is outside `{0, 1}` or line 1 is empty or not a valid 40-hex or 64-hex tree oid, so the workflow stops with `BLOCKED:merge-tree-failed`.

### 5. Rebase

The **same selected endpoint** performs the local step; it does not delegate to
itself, a wrapper, or a rebase child:

```bash
vr rebase
# If divergent revisions exist, select only a proven stale pre-rebase commit:
# vr abandon --revision <exact-old-commit-id>
```

The helper executes the existing `jj --ignore-working-copy --config
'revset-aliases."immutable_heads()"="none()"' rebase -s "$SOURCE" -d "$NEW_TARGET"`
or `rebase -b "$BRANCH" -d "$NEW_TARGET"` with the frozen inputs and target. A
completed label cannot run twice. Divergent cleanup is also journaled/fenced;
it must prove a current surviving revision with the same change ID and must not
abandon a current or foreign commit. Unprovable cleanup blocks, never falls back
to a naked command. No push or worktree synchronization runs here.

Stop: `BLOCKED:rebase-failed` (rare; jj accepts conflicts and stores them as first-class tree values).

### 6. Capture POST state

```bash
POST_TIP=$(git rev-parse "$BRANCH")
POST_CHANGE_ID=$(jj_read log -r "$BRANCH" --no-graph --no-pager --limit 1 --template 'change_id')
jj_read op log --limit 20 > "$BUNDLE/jj-op-log-after.txt"

mkdir -p "$BUNDLE/conflict-artifacts"
# Capture raw jj resolve --list stdout to a diagnostic sidecar first (ACR-260 precedent).
jj_read resolve --list -r "$POST_CHANGE_ID" \
  > "$BUNDLE/conflict-artifacts/jj-resolve-list-raw.txt" 2>/dev/null || true

# Row-validation adapter: validate each non-empty raw line and emit only validated bare paths
# into the canonical conflict-artifacts/files.txt. Reject unsupported rendering rows with a
# documented BLOCKED token rather than silently truncating.
: > "$BUNDLE/conflict-artifacts/files.txt"
while IFS= read -r RAW; do
  [ -z "$RAW" ] && continue
  # Strip the first whitespace-delimited field as the candidate path.
  CAND=${RAW%%[[:space:]]*}
  # Strict bare-path validation: no whitespace, no shell metacharacters, repository-path-shaped.
  if ! echo "$CAND" | grep -Eq '^[A-Za-z0-9._/-]+$'; then
    echo "BLOCKED:unsupported-jj-resolve-list-row: raw='$RAW'; candidate='$CAND'; see $BUNDLE/conflict-artifacts/jj-resolve-list-raw.txt" >&2
    exit 1
  fi
  printf '%s\n' "$CAND" >> "$BUNDLE/conflict-artifacts/files.txt"
done < "$BUNDLE/conflict-artifacts/jj-resolve-list-raw.txt"

# .conflict artifact production reads only validated paths from canonical files.txt.
while IFS= read -r P; do
  [ -z "$P" ] && continue
  SLUG=$(echo "$P" | tr '/' '__')
  jj_read file show -r "$POST_CHANGE_ID" "$P" \
    > "$BUNDLE/conflict-artifacts/${SLUG}.conflict"
done < "$BUNDLE/conflict-artifacts/files.txt"
```

Raw jj output is captured first in `conflict-artifacts/jj-resolve-list-raw.txt`, then the row-validation adapter publishes only validated bare paths to canonical `conflict-artifacts/files.txt`. If there are no conflicts, `files.txt` is empty and no `.conflict` files are written. Unsupported rows halt the workflow with `BLOCKED:unsupported-jj-resolve-list-row` rather than publishing truncated or raw display text.

### 7. Compute diffs

```bash
# target-delta (named main-delta.patch when TARGET is origin/main)
if [ "$TARGET" = "origin/main" ]; then DELTA=main-delta.patch; else DELTA=target-delta.patch; fi
git diff "$PRE_BASE" "$NEW_TARGET" --find-renames > "$BUNDLE/$DELTA"
git diff "$PRE_BASE" "$PRE_TIP"    --find-renames > "$BUNDLE/branch-intended.patch"
git diff "$NEW_TARGET" "$POST_TIP" --find-renames > "$BUNDLE/branch-actual.patch"
git diff "$PREDICTED_TREE" "$POST_TIP^{tree}" --find-renames > "$BUNDLE/residual.patch"
git range-diff "$PRE_BASE..$PRE_TIP" "$NEW_TARGET..$POST_TIP" > "$BUNDLE/range-diff.txt"
```

### 8. Compute verdict

Mechanical gate — purely syntactic, based on path-set membership and range-diff markers:

```
Let RP = {path : path appears in residual.patch}.
Let CF = {path : path appears in conflict-artifacts/files.txt}.
Let DC = {commit : range-diff.txt row prefix is '<' (dropped) or shows unexpected drift without a '=' match}.

Verdict:
  CLEAN                if RP is empty AND DC is empty
  DIRTY-EXPLAINED      if RP ⊆ CF     AND DC is empty
  DIRTY-UNPROVENANCED  if RP ⊄ CF     OR  DC is non-empty
```

`DIRTY-EXPLAINED` proves mechanical provenance: every residual hunk sits in a file that had a conflict. The reviewer still has to judge each resolution's correctness semantically — the gate doesn't claim the resolution was *right*, only that it had a provenance.

`DIRTY-UNPROVENANCED` is the blocking **mechanical** verdict. Execution ownership/cleanliness/currentness can independently block even a `CLEAN` mechanical result. It means either (a) content changed in a file that had no conflict, or (b) a commit was dropped/reordered without explanation. Both require human review.

In the stacked case where `PREDICTED_TREE` collapses (see §3.4 of [the proposal](../.build/VR-01-verified-rebase-proposal.md)), `residual.patch` is often trivially empty — the load for the child's content check is carried by `conflict-artifacts`, `range-diff.txt`, and the parent-pointer invariant (§9 below), not `residual.patch` alone.

### 9. Stacked cross-check (only when `$PARENT_BUNDLE` is set)

```bash
PARENT_POST_TIP=$(jq -r '.POST_TIP' "$PARENT_BUNDLE/refs.json")
if [ "$PARENT_POST_TIP" = "$NEW_TARGET" ]; then
  echo "parent-pointer-check: PASS" >> "$BUNDLE/summary.md.fragment"
else
  echo "parent-pointer-check: FAIL (expected $NEW_TARGET got $PARENT_POST_TIP)" >> "$BUNDLE/summary.md.fragment"
fi
cp "$PARENT_BUNDLE/branch-actual.patch" "$BUNDLE/parent-delta.patch"
```

The pointer invariant `parent.POST_TIP == child.NEW_TARGET` is the only cross-bundle invariant. FAIL means the child was rebased onto the wrong commit.

### 10. Freeze terminal evidence and release

Assemble `summary.md`, `refs.json`, all patches and diagnostics **before** terminal
publication. Include exact invocation/attempt/substrate/bundle, pre/post refs and
operations, mechanical verdict, execution status, and pending sync/review/push
obligations. Write `rollback.sh` as a pinned invocation of the same helper:

```bash
#!/bin/bash
set -euo pipefail
# Generator substitutes shell-quoted absolute literals, not caller cwd or current pointers:
exec python3 <pinned-VR_HELPER> rollback --bundle <exact-BUNDLE> \
  --owner-id <OWNER_ID> --attempt-id <ATTEMPT_ID>
```

Use a shell-quoting encoder (e.g. `shlex.quote`) for every substituted value,
then `chmod +x "$BUNDLE/rollback.sh"` before terminal evidence is frozen.
The helper validates its own hash, owner, attempt, canonical substrate identities,
all refs and jj operation, clean source, and the exact attempt anchor. Rollback
reacquires the same resources and refuses any intervening owner **even if that
owner finished without changing refs**. It refuses a later clean jj operation,
dirty source, replaced anchor, or incomplete journal. Current rollback restores
only the captured post-fetch operation and verifies restored topology refs/HEAD.
The exact pinned post-rebase `refs/jj/keep/*` GC roots are retained (not deleted
or broadly ignored); any other restore readback difference blocks. Repeat validates the new checkpoint and
owner before a no-op. No bare restore, age/operation-existence heuristic or
`rolled-back.flag` shortcut is permitted. It never pushes or synchronizes worktrees.

The operator must establish that it directly executed this operation with no
same-operation children still live. Preserve native invocation/subtree evidence
externally; the helper's `topology_validation: operator-owned` is **not** a process-
tree proof. A successful parent turn or helper exit alone cannot establish that.
Unresolved prior child or ambiguous termination means retain reservation and
report blocked, not release. After evidence is complete and all tool/child
activity terminal (not a claim that this still-running endpoint has exited):

```bash
vr finish --mechanical "$MECHANICAL" --execution "$EXECUTION" --reason "${REASON:-}"
vr release
```

`EXECUTION=COMPLETE` requires a completed rebase and final clean/current state.
`EXECUTION=BLOCKED` can retain `MECHANICAL=CLEAN` (for example, unexpected foreign
files after rebase) but always has `push_eligible=false`. A state/ownership mismatch
or in-flight command prevents finish/release: write a uniquely named external
diagnostic, preserve everything, and hand back `BLOCKED:recovery-required`.
Do not alter canonical evidence after `finish`; `release` checks its hashes.

Clean completion marks only this owner's records released; it does not delete
bundles, anchors, guards, worktrees or substrates. Released records remain as
lineage tombstones. Keep all owner-recorded evidence. Unknown/partial ownership
never authorizes cleanup. No recursive deletion or automatic lock stealing.

Suspension with a complete checkpoint resumes only the **same owner/attempt**
with fresh identity/state checks; skip recorded completed steps. Interruption
inside a command, partial reservation, or changed state requires explicit
operator recovery handoff and investigation; the helper intentionally offers no
force/unlock/reset option. Preserve the old evidence. Use a genuinely independent
substrate and new attempt ID for an independent rerun, not a renamed old path.

### 11. Return identity-bound disposition

Return the exact external bundle and `result.json`, mechanical verdict, execution
terminal and reservation disposition. Print `BLOCKED:<reason>` for a blocked or
unresolved execution, even when residuals are empty. For completed executions,
report `CLEAN`, `DIRTY-EXPLAINED`, or `DIRTY-UNPROVENANCED` as **mechanical only**.
After release, perform no further substrate mutation. The caller must join the
endpoint's authentic terminal/subtree readback with this result before reuse or
publication; the still-running endpoint cannot certify its own future runner exit.

Caller owns acceptance, worktree synchronization, required tests and review,
then separately authorized publication with an exact expected-old-OID lease and
remote readback. No verdict means “push freely”; neither a terminal record nor
an empty residual grants publication or rollback authority. Rollback requires
the caller's existing authorization and the fenced local helper above.

## Stacked branches

Bottom-up recursion, using the workflow inputs:

1. Run for the parent — `BRANCH=<parent>`, `TARGET=origin/main`, no `PARENT_BUNDLE`. Bundle A produced.
2. jj auto-rebases the child when the parent moves. Run for the child — `BRANCH=<child>`, `TARGET=<parent>`, `PARENT_BUNDLE=<path-to-A>`. Bundle B produced with `parent-pointer-check` recorded.

Each child attempt creates its own `refs/pre-rebase/<attempt_id>` anchor without overwriting the parent or a prior child. Complete/release the parent before acquiring the child on the same substrate; stacked order is sequential, not live same-operation recursion.

## Stale parent history

When a stack's parent is rewritten without the child being rebased at the same time, the child's local history retains stale copies of the parent's pre-rewrite commits. Running the workflow with default (`-b`) scope on such a child replays those stale commits onto the new parent and conflicts with the parent's current versions of the same files.

Symptoms:

- `DIRTY-UNPROVENANCED` verdict.
- `conflict-artifacts/files.txt` concentrates in paths that `target-delta.patch` edits.
- `range-diff.txt` shows many `<` (left-only) entries with subjects matching commits in `target-delta.patch` — the branch carries near-duplicate copies of the new `TARGET`'s commits.
- Residual hunk count is misleadingly large because jj wrote first-class conflict trees (`.jjconflict-base-N/`, `.jjconflict-side-N/`) into `POST_TIP^{tree}`, so `residual.patch` includes those entire side trees.

Recovery:

1. Run the bundle's `rollback.sh`.
2. Identify the first commit in `BRANCH`'s unique contribution. After fetch, `git log --oneline TARGET..BRANCH` lists `BRANCH`'s commits chronologically; the first one whose subject doesn't match any commit in `git log --oneline PRE_BASE..NEW_TARGET` is your `SOURCE`.
3. Re-run the workflow with `SOURCE=<that-commit>`. The bundle then verifies only the branch's actual unique contribution; `branch-intended.patch` reflects the branch's real intent rather than its full carried history, and `range-diff.txt` shows a clean `SOURCE..PRE_TIP ↔ NEW_TARGET..POST_TIP` correspondence.

This case is structurally distinct from a content conflict — recovery is mechanical (re-scope the rebase), not manual conflict resolution. Detection is intentionally not automated: the symptoms above are deterministic enough that diagnosis stays in caller territory, and a heuristic precondition would either over-block or miss edge cases.

## Tests (contract)

Runnable helper/procedure fixtures: `python3 -m unittest discover -s evals/verified-rebase-substrate-isolation -v`. See that directory's coverage limits; the table below remains the full mechanical contract, not a claim every row was executed.

| # | Scenario | Expected verdict / artifacts |
|---|----------|------------------------------|
| T1 | Conflict-free rebase; non-overlapping main changes | `CLEAN`. `residual.patch` empty. `range-diff.txt` shows `=` for every branch commit. |
| T2 | Text conflict on a line both sides edited | `DIRTY-EXPLAINED`. `residual.patch` touches only the conflicted file. `conflict-artifacts/<slug>.conflict` non-empty. |
| T3 | Stacked parent/child rebase | Two bundles. Bundle B's `summary.md` shows `parent-pointer-check: PASS`. |
| T4 | `rollback.sh` after a rebase | Branch ref back to `PRE_TIP`. `refs/pre-rebase/<attempt_id>` intact. `rollback-result.json` records the restored operation. Re-running is an owner/currentness-validated no-op. |
| T5 | Disposable production-shaped branches (never live production in regressions) | Bundles produced; no push; verdicts reported; fenced rollback available. |
| T6 | No-op rebase (branch already up-to-date with target) | `CLEAN`. `target-delta` empty. `branch-intended` == `branch-actual`. |
| T7 | Rename conflict (main renames a file the branch edited) | `DIRTY-EXPLAINED` with rename-present flag; OR `DIRTY-UNPROVENANCED` if ort/jj disagree (flagged as rename-detection divergence). |
| T8 | Delete conflict (main deletes, branch modifies) | `DIRTY-EXPLAINED`. `conflict-artifacts/<slug>.conflict` shows the deletion side. |
| T9 | Binary conflict | Content-conflict exit with a valid first-line predicted tree (`merge-tree.status=1`) continues into ordinary conflict accounting via `conflict-artifacts/files.txt` and `residual.patch`; real binary/unsupported prediction failure with no valid tree oid or status outside `{0, 1}` stops with `BLOCKED:merge-tree-failed`. |
| T10 | Rebase leaves unresolved conflicts | `DIRTY-EXPLAINED`. `conflict-artifacts/` has content. Caller resolves or rolls back. |
| T11 | Multi-parent basis collapse (one parent merged; child rebases onto main directly) | Single bundle at child level; no `parent-pointer-check` (basis was never pushed as target). |
| T12 | Branch carries stale copies of parent's commits (parent rewritten without child rebase) | With default scope: `DIRTY-UNPROVENANCED`. With `SOURCE=<first-unique-commit>`: `CLEAN`; `branch-intended.patch` reflects only the branch's unique work. |

## Anti-scope

- Not a merge-conflict auto-resolver.
- Not a replacement for [`commit-hygiene-operator`](../agents/commit-hygiene-operator.md).
- Not a PR-level tool — local branches only. No GitHub state.
- Does not decide whether to push. Always stops after bundle.
- Does not sync worktrees. Caller invokes [`worktree-operator`](../agents/worktree-operator.md) if needed.
- Does not judge resolution correctness. Mechanical provenance only (residual ⊆ conflict paths).
- Does not normalize diffs across refactors. If main's refactor moves code and jj ports the branch's edit successfully, that appears in `residual.patch` — the workflow surfaces it, not judges it.
- Does not support multi-target rebase.
- Does not handle `jj op` TTL recovery — `rollback.sh` fails loudly if the op was GC'd.

## Gate ownership

Per [`~/ai/conventions/gate-ownership.md`](../conventions/gate-ownership.md):

- Verdict production is **model-owned** (the mechanical gate in phase 8).
- Pushing or rolling back is **human-owned**. The workflow never does either.
