# `wu-session-migration` - one-time persisted WU cutover

Status: implemented for reviewed capture/dry-run followed by explicit apply, plus the strict persisted-session runtime writer operations. It does not apply a live migration by itself.

## One concern

Convert the exact reviewed AGE-260 live cohort to the strict wake contract without rewriting historical source indexes or inventing identity evidence. Dry run validates and reconciles all 306 manifests, seven `sessions.index.json` files, 152 source rows, and 42 unique cohort manifests before it emits a deterministic plan. Apply creates seven dedicated `sessions.active-wake.json` files and updates eligible live manifests through a durable, interruption-recoverable transaction.

Each `os.replace` is atomic for one file. The cross-file transaction is not observer-atomic: wake dispatch must remain disabled during cutover and recovery. Safety comes from one exclusive lock, a durable pre-mutation journal, retained original backups and staged replacements, parent-directory fsync after every replace, and deterministic recovery on every later invocation. Recovery reports whether it restored the preimage or retained an already committed replacement; committed cleanup recovery is never labeled rollback.

## Commands

```text
python3 tools/wu-session-migration capture-evidence \
  --inventory <age-260-session-migration-inventory.json> \
  --reviewed-inventory-sha256 <full-reviewed-sha256> \
  --output <trusted-pr-evidence.json>

python3 tools/wu-session-migration dry-run \
  --inventory <age-260-session-migration-inventory.json> \
  --reviewed-inventory-sha256 <full-reviewed-sha256> \
  --pr-evidence <trusted-pr-evidence.json> \
  --dispositions <cutover-dispositions.json> \
  [--conflict-resolutions <manager-conflict-resolutions.json>] \
  --plan <migration-plan.json>

python3 tools/wu-session-migration apply --plan <migration-plan.json>

python3 tools/wu-session-migration phase0-init --request <runtime-write-request.json>
python3 tools/wu-session-migration phase0-reresolve --request <runtime-write-request.json>
python3 tools/wu-session-migration cold-start-disposition-bind --request <runtime-write-request.json>
python3 tools/wu-session-migration phase3-bind --request <runtime-write-request.json>
python3 tools/wu-session-migration phase3-rebind --request <runtime-write-request.json>
python3 tools/wu-session-migration phase7-upsert --request <runtime-write-request.json>
python3 tools/wu-session-migration phase9-update --request <runtime-write-request.json>
python3 tools/wu-session-migration resumer-update --request <runtime-write-request.json>
python3 tools/wu-session-migration resumer-close --request <runtime-write-request.json>
```

Dry run never writes a session manifest or index. It may write only `--plan`, which must be outside every managed planning tree and must not normalize to, resolve to, or inode-alias any inventory, evidence, disposition, conflict-resolution, manifest, or source-index path. Plan-output I/O errors are concise schema/input failures without a traceback. Apply refuses an ineligible plan, changed input digest, changed device/inode or content identity, new path collision, symlink, path escape, malformed replacement, or incomplete recovery.

The reviewed AGE-260 inventory SHA-256 is supplied explicitly rather than inferred from a path. The plan records that digest, every other input digest, a combined input-set digest, deterministic row verdicts, exact original device/inode/content identity, and replacement digests. Apply re-hashes every input and validates the plan's own payload digest.

## Complete inventory gate

The production gate requires schema `age-260-session-migration-inventory-v1` and the reviewed aggregate counts exactly: 306 manifests, seven source indexes, 152 source rows, 42 cohort manifests, 25 persisted/derived base branches, 30 distinct indexed cohort manifests, three explicit refusals, two fully persisted candidates, 32 cohort source rows, and 37 non-refusal trusted-query candidates.

Validation rejects truncated or added arrays, classification-count drift, duplicate manifest paths, duplicate normalized paths or device/inode aliases, duplicate PR/branch joins, duplicate or omitted row locators, malformed rows, source row-count drift, field drift from the reviewed inventory, paths outside a declared planning root, unexpected basenames, symlinks, and unresolved locator links. Every `existing_index_rows` entry resolves its exact keyed or list locator in the exact declared source index.

All managed manifests are `session.json` below a planning root enumerated by the reviewed inventory. Source indexes are named `sessions.index.json`; active outputs are named `sessions.active-wake.json` in the same directory as each source index. Existing source indexes remain byte-for-byte historical inventory and are never migration write targets.

## Trusted PR and git evidence

`capture-evidence` performs one exact provider query per unique PR URL and records the raw provider payload, command, RFC3339 capture time, and canonical payload SHA-256. It validates dynamic Git OID operands as hexadecimal before invocation. For merged PRs it records `git show -s '--format=%H %P' --end-of-options <merge-sha>` output and digest from the named repository. For every `branch_out_sha`, including an already-full OID, it records the exact named manifest repository, requested OID, full `git rev-parse --verify --end-of-options <oid>^{commit}` result, command, time, and digest.

Dry run trusts no separately asserted normalized state. It recomputes URL, state, branch, head, base, merge identity/time, parent list, merge shape, and branch-out expansion from the hash-bound raw captures. It compares candidate, manifest, every exact source row, and provider evidence for manifest path, ticket/backend, branch, PR URL, head, and base identity. Persisted and derived pre-merge baselines must agree with the verified immediate parent.

State schemas are exclusive:

- `OPEN` has no merge SHA, merge time, or merge-commit capture.
- `CLOSED` has no merge SHA, merge time, or merge-commit capture and is excluded without manifest mutation.
- `MERGED` is the provider's raw exclusive state and requires full merge SHA, merge time, and captured exact commit parents. A two-parent merge remains valid only when parent two equals the PR head. A one-parent commit is valid only with a separate closed `github-merge-operation-response` capture of the successful provider merge operation: its digest-bound command must be exactly `gh api --method PUT repos/<owner>/<repo>/pulls/<number>/merge -f merge_method=squash -f sha=<full-head-sha>` (field order may be reversed), and its raw response must bind `merged=true` and the exact merge SHA. The sole parent must equal every persisted candidate/manifest pre-merge baseline that exists, and `merge_sha` must differ from the PR head. Missing or unknown method evidence, `REBASE`, parent/head contradictions, octopus history, and every other one-parent shape are refused. `capture-evidence` leaves this historical merge-operation record null when the standard PR query cannot provide it; it must come from the retained provider operation capture and is never inferred from topology.

## Conflicts and accepted breakage

Source-row conflict is not normalization. A conflicting locator is refused unless a separate `wu-session-conflict-resolutions-v1` record is manager-owned, identifies the exact index path and locator, hashes the discarded source row, and supplies the complete intended retained identity. `accepted_breakage` means only that loss of wake automation is accepted for an otherwise unprovable inventory refusal; it is not conflict resolution. Consequently `s11-m2c-resume-fix` and `CLOUD-259-session-store-scoped-acquisition` cannot be silently normalized.

Accepted-breakage manifests remain untouched as source history and do not enter an active index. A disposition is valid only for one exact inventory row already carrying `explicit_refusal_reasons`, with `owner=manager`, `accepted_breakage=true`, and a non-empty reason.

## Active wake indexes

Each deterministic `wu-sessions-active-wake-v1` index contains only globally validated OPEN or MERGED cohort rows assigned to that exact source-index location. It contains no closed history, accepted breakage, pre-PR rows, malformed placeholders, or unresolved conflicts. Duplicate source aliases consolidate into one canonical active row. Unindexed accepted live manifests enter the nearest containing reviewed index location. Wake must block if an excluded classification is present; only a valid canonical OPEN row that currently polls non-merged may remain pending.

`wu-session-wake` consumes only `sessions.active-wake.json`. New implementation sessions enter it only after exact Phase 7 PR acquisition. `wu-session-resumer` removes the exact row only after verified close or successor-handoff completion.

## Lock and recovery protocol

Migration, implementation-pipeline session writers, and the resumer use the exclusive flock at:

```text
~/.local/state/ai/wu-session-migration/cutover.lock
```

The transaction journal is `transaction.json` in that directory. One closed schema binds transaction id, operation, `staging | prepared | committing | committed` phase/progress, exact plan/request path and file/payload/input-set digests, canonical planning roots, and an ordered target projection containing exact target/artifact names, parent device/inode, original device/inode/mode/content, and backup/replacement hashes and modes. The closed `staging` journal is durable before the first backup or replacement is created and is rewritten/fsynced after each artifact becomes durable. Recovery validates every key and type before target access, reopens and hashes the bound plan/request, requires its exact target projection, and repeats basename, containment, normalized-path, no-symlink, duplicate-path, duplicate-inode, and transaction-name checks. Staging recovery removes an inode-bound artifact only when its exact journaled identity still matches. If an artifact's identity is not yet bound, recovery removes it only when its digest and exact regular-file mode match the already-journaled planned artifact contract; mismatching foreign or partial files are preserved and keep the journal actionable. Cleanup is descriptor-relative, fsyncs every changed reachable parent, and removes the journal only after every target is recovered and cleanup completes. Malformed, torn, redirected, or substituted journals are concise recovery failures and remain on disk.

Every command and supported imported apply, readback, or recovery entry point constructs its own immutable acting state from the current passwd home's canonical `~/.local/state/ai/wu-session-migration` root, takes that one lock, and recovers an incomplete transaction before accepting new work. No command, environment variable, public parameter, or mutable module selector can choose another production lock or journal namespace. Already-held execution primitives accept state only as a private dependency; the behavioral-test harness uses that boundary for isolated files without redirecting a supported production entry point. The transaction opens every target parent with `O_DIRECTORY|O_NOFOLLOW`, records and rechecks parent device/inode, and performs source reads, staging, replace, unlink, and directory fsync relative to held descriptors. After the committing journal is durable it rechecks every target's held-parent entry, device, inode, bound mode, and content hash; it repeats that check for the current target immediately before each descriptor-relative replacement. A mismatch preserves the unexpected content, safely rolls back any earlier replacement, never reports success, and retains an actionable journal if complete rollback cannot finish. Recovery reopens each recorded parent and requires that exact identity before any operation. After journal-wide schema and plan/request binding validation, parent-open, parent-identity, target/artifact, replace, unlink, and fsync failures are collected by canonical parent or target while every independently safe target is attempted. Recovery recognizes only original or planned replacement hashes, aggregates all failures into one recovery error, and retains the journal on any failure. Unknown third-party content is never overwritten. A recovered rollback can change file inodes, so a previously reviewed plan/request may become stale and must be regenerated.

Runtime operations consume the closed `wu-session-runtime-write-v1` schema. Every request requires `manifest_path.name=session.json`, manifest `planning_dir == manifest_path.parent`, declared live runtime root `R == planning_dir.parent`, and `index_path == R/sessions.active-wake.json`. Direct mode requires `R` to equal the top-level project planning tree `P`; feature direct/refactoring mode requires canonical `R=F/routes`, where `R == P/features/<feature>/routes`. Every active row points to one session directory immediately below its exact `R`, and no runtime operation searches for, aggregates, or falls back to another index. The separately normalized manifest scratch directory may be outside `R` but must remain strictly below `P`; `phase0-init` validates that relationship before creating the manifest. Each normalized path is no-symlink, contained, and descriptor-validated. The complete source and replacement active indexes must have unique PR/branch wake joins, manifest paths, and ticket/branch identities. `phase0-init` initializes the manifest while preserving or creating the empty canonical active index and adds no pre-PR row. `cold-start-disposition-bind` requires an existing open pre-PR implementation session, `row_identity=null`, one confirmed answer artifact under the declared scratch directory, three null source bindings, and exactly one changed manifest key: `cold_start_disposition_ref`. `phase3-bind` requires the same open/no-row state, null estimate bindings, the exact estimate artifact and every currentness source identity it names, a preserved cold-start reference, and exactly the estimate ref/hash plus one canonical `{"phase":"3","status":"complete","ts":"<UTC-Z>"}` history append. Unknown, partial, mixed, duplicate, diverted-route, stale, malformed-history, or semantic-replay requests fail closed. For both pre-PR operations the write target is only `session.json`; the complete active index and artifact set are journaled, repeatedly checked read-only guards whose bytes/device/inode/mode and row order cannot change. `phase7-upsert` permits exact PR-acquisition fields and one unambiguous new canonical active row; `phase9-update` and `resumer-update` permit only their declared manifest fields and replace one exact active row; `resumer-close` requires final closure and removes exactly one full-identity row. Historical `sessions.index.json` remains read-only inventory. Unknown request keys, forbidden field changes, partial identities, stale sources, cross-root rows, duplicate joins, or non-exact projections fail before mutation.

`phase3-rebind` advances only Phase 3 binding attempt 1 to 2 or 2 to 3. It admits only prior and revised estimate dispositions of `no_write_policy_disabled`; `write_verified` is outside this operation and fails before mutation. Admission consumes the existing complete `apply-gate-set-result-v1` for `caller_mode=implementation-phase-4`, including exact ticket/cycle/attempt context, blocking gate rows and process proof, terminal decision and repair route, currentness summary, returned output paths, and the producer's authority-bearing artifact hashes. It does not attest runner or defined-agent identity and performs no provider mutation, dispatch, retry, or remote readback.

The gate producer appends the canonical `${planning_dir}/audit-history.md`. Each rebind therefore requires an attempt-scoped `phase-4-attempt-<N>-audit-history.snapshot.md` guard whose bytes and digest exactly match the canonical audit named by the producer result at admission. The immutable snapshot, not the appendable canonical path, enters revision lineage. The complete canonical audit, snapshot, producer result and outputs, prior estimate/proposal, and retained lineage remain read-only guards. The writer requires byte-distinct attempt-versioned proposal and estimate artifacts and changes exactly five manifest keys: the estimate ref/hash, binding attempt, revision history, and phase history. Replay, skip, reorder, diversion, stale evidence, malformed or wrong-context producer results, incomplete lineage, and attempt 4 fail closed.

`phase0-reresolve` is the pre-PR policy-drift transaction for an existing session. It is valid only before Phase 3 and Phase 7, requires fresh contract-resolution and ticket producer identities, joins policy/operator/contract/ticket/topology fields to five read-only artifacts, preserves cold-start disposition and phase history, writes only `session.json`, and never creates an active-index row.

For `phase3-bind` only, the persisted resolved operator and optimized contract are producer-time identities. Their digests normally match regular tracked blobs at the manifest's exact full `branch_out_sha` commit and canonical repository-contained paths. When an authenticated `phase0-reresolve` changed those identities after branch-out, Phase 3 instead requires the canonical `phase0-reresolve.readback.json` as an additional read-only guard and machine-validates that closed readback against the unchanged pre-Phase-3 manifest before accepting the migrated identities. These two roles are exempt from the record-to-estimate live digest match, so their current files may drift after ordinary production; every other request artifact retains its live filesystem identity guard. Unknown or non-commit branch-out objects, missing or non-blob paths, symlinks, gitlinks, and digest mismatches without the authenticated re-resolution readback fail before mutation. A malformed producer identity exits `2`; a failed Git interrogation of the declared repository exits `3`.

Post-write evidence for `phase0-reresolve`, `cold-start-disposition-bind`, `phase3-bind`, and `phase3-rebind` uses the closed `wu-session-pre-pr-write-readback-v1` schema. `validate-pre-pr-readback --readback <path>` binds that evidence to the immutable writer request and independently verifies the before/after manifest projection, operation-specific changed keys and Phase 3 history transition, current and retained artifact identities, unchanged active-index identity and rows, absence of a synthesized row, and absence of a retained journal. A literal `verdict=PASS` does not bypass these checks.

`phase3-rebind` itself creates the attempt-scoped readback below `${scratch_dir}/session-writes/`, reruns the complete lineage and producer-result join, and returns or prints terminal `PASS` only after that readback validates. If the manifest commit succeeds but readback publication or validation fails, the operation returns `committed-awaiting-readback` with the expected readback path, never `PASS` and never rollback; rerunning the same immutable request reconstructs its source projection and publishes or validates that readback without repeating the manifest write. Internal transaction primitives do not authorize completion independently.

## Exit codes

- `0`: evidence capture completed, dry-run plan is eligible, migration apply completed, or a runtime writer operation completed.
- `1`: dry run completed complete reconciliation but has one or more deterministic row refusals. The refusal plan is still written.
- `2`: malformed arguments, schema, inventory, evidence, dispositions, conflict resolutions, or plan; also plan-output I/O failure.
- `3`: provider/git capture failure, stale apply input/source identity, transaction failure, recovery failure, or committed Phase 3 write awaiting a valid closed readback.

## Used by

- `conventions/wu-session-lifecycle.md` defines the one-time cutover and shared writer protocol.
- `workflows/wu-session-wake.md` consumes only dedicated canonical active indexes.
- `agents/implementation-pipeline-orchestrator.md` inserts and updates canonical active rows.
- `agents/wu-session-resumer.md` removes an exact active row after verified completion.
