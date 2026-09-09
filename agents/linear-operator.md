---
description: 'Read/comment/create/transition Linear issues via the ported Linear client at ~/ai/clients/linear/. Auth via $LINEAR_API_KEY env var.'
model: gpt-luna-high
output_format: ''
---

# Linear Operator

## Contract

When `contracts/operators/linear-operator.yaml` is present, dispatchers use that sidecar as the optimized call interface and this embedded block only as its equivalent fallback. The full operator body remains the procedural authority.

```yaml
schema: operator-contract-v1
estimate_mutation_enabled: false
inputs:
  - name: task
    type: enum
    required: true
    default_source: caller
    description: "task"
  - name: issue_key
    type: string
    required: false
    default_source: caller
    description: "issue key"
  - name: body
    type: string
    required: false
    default_source: caller
    description: "body"
  - name: operation
    type: enum
    options: [comment-readback]
    required: false
    default_source: caller
    description: "When supplied, must be comment-readback; omission selects ordinary comment behavior."
  - name: target_status
    type: string
    required: false
    default_source: caller
    description: "target status"
  - name: output_path
    type: path
    required: false
    default_source: caller
    description: "output path"
  - name: ticket_operation_context
    type: string
    required: false
    default_source: caller
    description: "Exact JSON ticket/route/attempt/PR/reviewed-ref context required for operation=comment-readback."
  - name: operation_result_path
    type: path
    required: false
    default_source: caller
    description: "Canonical ticket-operation-result-v1 path for comment-readback."
  - name: producer_log_path
    type: path
    required: false
    default_source: caller
    description: "Distinct producer-owned closed ticket-client operation log path."
  - name: producer_output_path
    type: path
    required: false
    default_source: caller
    description: "Distinct producer-owned exact remote readback output path."
  - name: brief_path
    type: path
    required: false
    default_source: caller
    description: "brief path"
  - name: summary
    type: string
    required: false
    default_source: caller
    description: "summary"
  - name: parent_key
    type: string
    required: false
    default_source: caller
    description: "parent key"
  - name: labels
    type: string
    required: false
    default_source: caller
    description: "labels"
  - name: estimate
    type: int
    required: false
    default_source: caller
    description: "estimate"
  - name: inherited_story_point_estimate
    type: int
    required: false
    default_source: caller
    description: "inherited story point estimate"
  - name: estimate_source
    type: string
    required: false
    default_source: caller
    description: "estimate source"
  - name: estimate_delta_rationale
    type: string
    required: false
    default_source: caller
    description: "estimate delta rationale"
  - name: estimate_delta_flag
    type: string
    required: false
    default_source: caller
    description: "estimate delta flag"
  - name: linear_team_key
    type: string
    required: false
    default_source: wrapper:<name> | caller | prompt
    description: "linear team key"
  - name: linear_project_id
    type: string
    required: false
    default_source: wrapper:<name> | caller | prompt
    description: "linear project id"
defaults:
  []
secrets:
  - LINEAR_API_KEY
outputs:
  - task: read
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
  - task: comment
    success_shape: "Ordinary comment confirmation, or producer-owned ticket-operation-result-v1 for caller-context validation after operation=comment-readback."
    wrote_lines: ["${operation_result_path} when operation=comment-readback", "${producer_log_path} when operation=comment-readback", "${producer_output_path} when operation=comment-readback"]
  - task: create
    success_shape: "Created or duplicate-reused issue key and URL after deterministic Markdown description readback returns MATCH."
    wrote_lines: []
  - task: update-estimate
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
  - task: transition
    success_shape: "Initial observation, requested status, resolved target, and acknowledged or already_matching outcome; no final-state claim. Explicitly required readback uses get-issue and reports a separate point-in-time match; mismatch, unverifiable state, or read error is BLOCKED with transition outcome retained."
    wrote_lines: []
  - task: search
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
  - task: list-issues
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
  - task: list-projects
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
  - task: list-labels
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
  - task: create-label
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
  - task: apply-labels
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
  - task: upsert-comment
    success_shape: "Task-specific stdout or durable artifact paths named by the procedure."
    wrote_lines: []
errors:
  - class: BLOCKED
    cause: "Required inputs are missing, unreadable, contradictory, or unsafe for the selected task."
    recovery: "Supply corrected inputs or select the appropriate operator wrapper before rerun."
  - class: NEEDS_INPUT
    cause: "A user-owned value, scope, or trade-off question is required."
    recovery: "Answer the emitted question artifact and resume."
side_effects:
  - linear-create
  - linear-comment
  - linear-transition
  - linear-update-estimate
  - linear-label-create
  - linear-label-apply
must_delegate:
  - linear-writes
may_direct:
  - linear-reads
forbidden_direct:
  - direct-linear-api-write-without-selected-contract
```

You read, comment on, create, and transition Linear issues using the ported Linear GraphQL client at `~/ai/clients/linear/`. Auth uses the `$LINEAR_API_KEY` environment variable. Linear descriptions and comments are markdown natively, so unlike `jira-operator` there is no ADF translation step.

## Use When

- The user references a Linear issue key (e.g., `AGE-34`) and wants info posted/read.
- A PR / initiative needs cross-linked from a Linear issue.
- A multi-PR campaign just landed and you need to log the PR list on the parent issue so the team can find it.
- The implementation-pipeline orchestrator dispatches Phase 0 read or cold-start create.

## Do Not Use When

- The user wants info posted to PRs (use `gh` CLI directly).
- The user wants Notion / Slack / email posts (different operators).

## Execution Boundary

`must_delegate: linear-writes` is a caller boundary: callers delegate Linear writes to this operator. Once selected, this operator is the terminal executor for the requested Linear operation. It must invoke the matching `clients.linear.cli` command directly (through the mandatory admission helper below for `update-estimate`) and must never dispatch `linear-operator.md`, another agent, or another workflow to perform the same operation. For `update-estimate`, a failed command ends this invocation through the terminal `BLOCKED` branch below; an asynchronous handle or "Dispatching" response is not completion.

These execution instructions apply to you in the current invocation, including when a selected project wrapper inherits this procedure: you are already its terminal executor, and reading the base procedure does not make you a caller requiring another dispatch.

The task mapping is closed: `read` uses `get-issue`; `comment` uses `create-comment`; `create` uses `search-issues` followed by at most one `create-issue`; `update-estimate` first applies the selected-contract admission in Procedure: Update Estimate, then uses `update-issue` and the documented comment path only when admitted; `transition` uses `transition-issue` (and `get-issue` only for explicitly required readback); `search` uses `search-issues`; `list-issues` uses `list-issues`; `list-projects` uses `list-projects`; `list-labels` uses `list-labels`; `create-label` uses `create-label`; `apply-labels` uses `apply-labels`; and `upsert-comment` uses `upsert-comment`. Return success only after the admitted direct operation and required readback are terminal.

## Required Inputs

- `task`: one of `read`, `comment`, `create`, `update-estimate`, `transition`, `search`, `list-issues`, `list-projects`, `list-labels`, `create-label`, `apply-labels`, `upsert-comment`; `task=read` is the Phase 0 bootstrap read path and `task=upsert-comment` is the idempotent comment path.
- `task=update-estimate`: backend-neutral estimate refinement write-back. Inputs: `issue_key`, `estimate`, `inherited_story_point_estimate`, `estimate_source`, `estimate_delta_rationale`, and `estimate_delta_flag`. Execute the numeric update and its durable Markdown note through Procedure: Update Estimate's mandatory admission helper, which guards the existing update/comment CLI operations. The note contains inherited estimate, refined estimate, source, and delta rationale. This task must not transition workflow status/state.
- `issue_key`: e.g., `AGE-34` or `${linear_team_key}-34` (required for known-issue-key `read`/`comment`, `transition`, and `apply-labels`).
- `target_status` (for `transition`): destination state name for the routine manager-owned path. The closed routine set is exactly `Todo`, `In Progress`, and `Done`, sourced from `clients.linear.client.ROUTINE_MANAGER_OWNED_STATES`; out-of-set values are out-of-contract and the operator returns `BLOCKED`.
- `body` (for `comment`): markdown body — Linear renders Markdown natively, no ADF.
- `operation` (for `comment`, optional): omit for an ordinary comment or pass exactly `comment-readback` for producer-authenticated evidence. Any other value is out-of-contract and returns `BLOCKED`; `comment-readback` requires `ticket_operation_context`, `operation_result_path`, `producer_log_path`, and `producer_output_path`.
- `output_path` (for `read`): destination file path the operator must write the rendered ticket to (used by orchestrator Phase 0 bootstrap).
- `brief_path` (for `create`): path to a markdown brief whose contents become the issue description verbatim. The orchestrator validates that the rendered description is non-empty; scope and boundaries are derived later in Phase 2.5 / Phase 3 / Step 6a, not pre-declared in the brief.
- `summary` (for `create`): one-line title for the issue.
- `parent_key` (for `create`, optional): parent Linear issue key when filing a child WU under an initiative.
- `labels` (for `create`/`search`/`list-issues`, optional): list of label names resolved in the selected team.
- `estimate=<int>` (for `create`, optional): story-point estimate; must be a fibonacci point value from `1, 2, 3, 5, 8, 13, 21, 40, 100`. Layer 4 ticket generation decides SLICE vs. INIT sizing; SLICE tickets may pass this value through, while INIT tickets remain unsized.
- Search filters (optional for `search`): `title_contains`, `title_starts_with`, `linear_project_id`, and `labels`; the client translates these to a GraphQL `filter:` clause.
- `linear_team_key` is required for `create`, `list-issues`, `list-projects` team scoping, `search`, `list-labels`, `create-label`, and `apply-labels`.
- `linear_team_key` is not required for known-issue-key `read` and `comment`; the issue identifier already carries the team prefix.

## Inputs

- `--input linear_team_key=<key>` (required for create, search, list-issues, list-projects, list-labels, create-label, and apply-labels) — Linear team key (e.g. `AST` or `NES`). Used to scope issue routing and the label namespace. Known-key read/comment operations do not need it because the issue identifier already carries the team prefix.
- `--input linear_project_id=<id-or-slugId>` (optional) — Linear project UUID or `slugId`; when supplied, created issues and issue queries are scoped to that existing project. Distinct from labels.

## AGENT DISPATCH SHAPE

`~/ai/workflows/agents-cli.md` is the canonical positive-shape source for any caller that updates Linear and then dispatches an agent. Linear client commands are ticket-client operations; they must finish as separate commands before or after the later `agents` dispatch.

Do not wrap `agents` calls in Python heredocs, shell scripts, or any composition that puts other commands between the parent shell and the `agents` invocation. Do not pipe live `agents` stdout through truncating filters such as `| head -N` or `| awk 'NR<=N'`; the later dispatch uses full `2>&1 | tee` capture from the canonical CLI convention. Do not combine N independent dispatches into a single shell script; Linear work and child dispatches remain sibling operations.

## Auth

```bash
if [[ -v LINEAR_API_KEY ]]; then
  printf '%s\n' 'LINEAR_API_KEY=present'
else
  printf '%s\n' 'BLOCKED:LINEAR_API_KEY=absent'
  exit 2
fi
```

Presence diagnostics must use a key-presence primitive such as `[[ -v NAME ]]` or `secret_safe_capture.py presence` against the resolved operator contract. Never use `env`, `printenv`, `set`, shell expansion, or another command that can emit the value.

`$LINEAR_API_KEY` is exported from `~/.bashrc`. The token is regenerated at <https://linear.app/settings/api> if rotated.

The client itself reads `LINEAR_API_KEY` from env on construction; you do not pass it explicitly. The CLI is invoked as `python3 -m clients.linear.cli` with `PYTHONPATH=$HOME/ai`.

## Procedure: Read

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli get-issue "AGE-34"
```

This returns a JSON envelope:

```json
{"ok": true, "data": {"id": "...uuid...", "identifier": "NES-34", "title": "...",
 "description": "<markdown>", "estimate": 5, "state": {"name": "..."}, "team": {"key": "NES"},
 "labels": [...], "project": {"id": "...", "slugId": "..."},
 "parent": {...}, "url": "https://linear.app/..."}}
```

For description-only:

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli get-issue-description "AGE-34"
```

### Read for orchestrator bootstrap (description as markdown)

When dispatched by `~/ai/agents/implementation-pipeline-orchestrator.md` at Phase 0, the prompt passes `output_path=${scratch_dir}/ticket.md`. Render the Linear issue to a markdown file with frontmatter:

```yaml
---
key: AGE-34
summary: <issue title>
status: <state name>
parent: <parent key or empty>
labels: [label1, label2]
url: <linear url>
story_point_estimate: <issue estimate or null>
estimate_source: <parsed source or missing>
estimate_rationale: <parsed rationale or null>
estimate_field: "estimate"
---
```

Then the markdown body is the issue description verbatim (Linear stores Markdown natively, no rendering step). Do not transform headings, lists, or code blocks. `story_point_estimate` comes from the Linear `estimate` field. `estimate_source` and `estimate_rationale` are parsed from description labels such as `Estimate Source` and `Estimate Rationale`; use `missing` and `null` when absent. `estimate_field: "estimate"` identifies the mutation target for later refinement. `labels:` must come from the real `get-issue` `labels` data, and project readback may include `project.slugId` and project teams. The orchestrator validates only that the rendered description is non-empty.

Implementation (the captured envelope is supplied on stdin; the destination is a real argv value):

```bash
if ISSUE_JSON=$(PYTHONPATH=$HOME/ai python3 -m clients.linear.cli get-issue "${issue_key}"); then
    printf '%s' "$ISSUE_JSON" | PYTHONPATH=$HOME/ai python3 -m clients.linear.ticket_bootstrap "${output_path}"
else
    printf '%s\n' 'BLOCKED:ticket-read: get-issue failed' >&2
    exit 2
fi
```

Require the renderer's exit status to be zero before using the artifact; on failure, return `BLOCKED` and never consume an earlier output file. The renderer serializes metadata with `yaml.safe_dump` and writes the description's exact UTF-8 bytes after the closing frontmatter delimiter. It recognizes plain or bold `Estimate Source:` / `Estimate Rationale:` lines, optionally list-prefixed, outside fenced code. Absent labels alone use `missing` / `null`. Identical repeated labels are accepted; empty/conflicting labels or a source outside `prototype-dossier`, `layer-2-magnitude`, `layer-3-slice`, `backstop-spike`, `missing` return `BLOCKED` with the encountered values. Retain the original readback and resolve that uncertainty before bootstrap continues; never replace unknown provenance with an invented baseline.

## Procedure: Update Estimate

Used by `~/ai/agents/implementation-pipeline-orchestrator.md` after Phase 3 artifact verification and before Phase 4 prompt composition. This admission also applies to every direct `task=update-estimate` invocation.

Required inputs: `issue_key`, `estimate`, `inherited_story_point_estimate`, `estimate_source`, `estimate_delta_rationale`, and `estimate_delta_flag`.

Before running the numeric update or writing its refinement note, resolve estimate policy from the selected operator contract:

1. Use the operator definition governing this invocation, including the current project wrapper's own contract when it inherits this base procedure. Keep the existing wrapper-first selection and inheritance from `~/ai/workflows/agents-cli.md` and `~/ai/conventions/bootstrap-pattern.md`; do not select a different wrapper to obtain permission. The governing definition supplies authority, not a caller/session claim about an operator path, contract path, or policy value.
2. Read that selected definition's optimized sidecar first; use its embedded `## Contract` only when the sidecar is absent. Bind the contract to the actual governing definition and its source path; validate `schema: operator-contract-v1`, any sidecar `source` metadata, and equivalence with the selected definition's embedded contract when both exist. If the selected source/contract cannot be established, is unreadable, no longer matches the governing definition, or has a source/path or wrapper-precedence mismatch, return `BLOCKED:estimate-mutation-policy-invalid` before either write. Never replace an invalid or unreadable selected sidecar with an embedded/base contract.
3. `estimate_mutation_enabled` is selected-contract policy, never an operator input or a default supplied by the caller. Reject caller/session overrides, non-boolean values, duplicate declarations, and conflicting declarations in the selected contract as `BLOCKED:estimate-mutation-policy-invalid`. A current selected wrapper's explicit policy takes precedence over the base policy; an enabled wrapper over a disabled base is not itself a conflict. Do not treat the inherited base procedure's embedded contract as the selected wrapper contract.
4. An exact boolean `false` returns `BLOCKED:estimate-mutation-policy-disabled` without a numeric update or refinement note. An exact boolean `true` admits the existing procedure below. If policy is absent, retain the existing `legacy_capability` admission only when the selected contract, with its normal capability inheritance, advertises both `task=update-estimate` in `outputs` and `linear-update-estimate` in `side_effects`; otherwise return `BLOCKED:estimate-mutation-policy-unresolved`. Never infer permission from the requested task, estimate value, prior dispatch, session state, or credential availability.

Execute admission and each protected operation together using `clients.linear.estimate_admission`. Set the internal `governing_definition` locator to the absolute source path of the definition already governing this invocation under step 1; it is not a new operator input, caller override, or permission source. The helper derives the sidecar from that definition, parses YAML with duplicate-key rejection, validates source binding and typed embedded/sidecar equivalence, and checks policy before calling the existing CLI. It reads the contract again for each protected operation.

The governing-definition selection remains this procedure's responsibility. The helper enforces admission on this path; it does not authenticate an arbitrary path against runner state, and independent raw `clients.linear.cli` calls do not inspect operator policy.

Run each guarded command synchronously. Before proceeding, inspect that command's own exit status and parse its JSON envelope; output capture must preserve the command's status. Apply these closed branches separately to the numeric update and the refinement note:

- **Failure:** Any nonzero exit, `ok: false`, missing or malformed envelope, or envelope without exact boolean `ok: true` ends this invocation as `BLOCKED`. Identify the failed stage and retain the underlying error code and message when available. For missing or malformed output, report that condition and the observed exit status without inventing a backend error. This applies to every error class, including unknown classes. Stop here: do not delegate, substitute a wrapper, or retry the operation through the guard, raw CLI, or another path.
- **Success:** Only exit zero with a valid success envelope permits the next step for that stage below. A command error does not establish whether a remote mutation occurred; report only the outcome supported by its result.

Run the numeric update through the guard and apply those branches to its result:

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.estimate_admission \
    --definition "${governing_definition}" -- \
    update-issue "${issue_key}" --estimate "${estimate}"
```

If the numeric update fails, return `BLOCKED` for the numeric stage and state that the refinement note was not attempted. Only after numeric success, retain that result and compose `refinement_note` with inherited estimate, refined estimate, source, and delta rationale; it may include the verbatim `estimate_delta_flag` for audit evidence. Write it through the same guard and apply the branches above to this command's own result:

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.estimate_admission \
    --definition "${governing_definition}" -- \
    create-comment "${issue_key}" --body "${refinement_note}"
```

When using the existing idempotent note path, the full `refinement_note` must start with `## Estimate refinement` followed by a newline and retain that first line on every update. Then replace only the command after `--` with `upsert-comment "${issue_key}" --title "Estimate refinement" --body "${refinement_note}"`; retain the same governing definition, guard, and result branches. If the note fails, return `BLOCKED` for the note stage and report the retained numeric success separately; do not claim rollback or a successful note. Return task success only after both stages succeed. This task does not transition status/state.

## Procedure: Comment

Linear comments are markdown. No ADF. No JSON document model.

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli create-comment \
    "AGE-34" \
    --body "$(cat <<'EOF'
PR #123 opened: https://github.com/owner/repo/pull/123

WU summary: <one-line>

Audit history: closed at LOW × 3.
EOF
)"
```

Returns `{"ok": true, "data": {"id": "<uuid>", "issueId": "<uuid>"}}`. Parse `id` to confirm.

For idempotent commenting (e.g., orchestrator Phase 9 cross-link, where re-running must not duplicate):

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli upsert-comment \
    "AGE-34" \
    --title "PR Cross-link" \
    --body $'## PR Cross-link\n\nPR #123 opened: https://github.com/owner/repo/pull/123'
```

`upsert-comment` compares `--title` with only the first body line, normalizing both by trimming surrounding whitespace, removing leading `#` characters, then trimming again. The full body must retain that matching first line on both creation and update; the client writes the supplied body unchanged and does not insert a title. This applies to every `task=upsert-comment`, including estimate refinement and calibration notes. Ordinary `create-comment` and exact-body `comment-readback` do not add this heading.
For `upsert-comment`: print the comment ID returned by the CLI JSON envelope so callers can record the durable reference.

### Producer-Authenticated Comment Readback

When `task=comment` and `operation=comment-readback`, require exact `ticket_operation_context`, `operation_result_path`, `producer_log_path`, and `producer_output_path`. The three paths are canonical, absolute, pairwise distinct, and written only by this invocation. Derive `producer_invocation_uuid` from runner provenance; never accept a caller-selected UUID.

Canonicalize the posted Markdown body once before any ticket-client request as its exact UTF-8 bytes and SHA-256 those bytes; do not trim, normalize line endings, or render Markdown before comparison.

Reconcile before any create request. Query the exact context ticket key with `get-issue` and the fully paginated `list-comments`, require both responses to agree on the exact issue identifier and UUID, and select only comments whose exact-body SHA-256 equals the posted-body SHA-256. Apply these closed outcomes:

- Zero matches: create once with `create-comment`; require its non-blank ID and returned issue UUID to equal the exact-ticket identity, then verify the posted-body hash through the mandatory post-create readback below.
- One match: do not create; reuse that comment's ID as the remote create identity only after its exact ticket and posted-body identities have passed the checks above.
- More than one match: return `BLOCKED: ambiguous comment-readback reconciliation` before create and write no PASS result artifacts.

After either zero-match creation or one-match reuse, query the same exact ticket with fully paginated `list-comments` again. Require exact issue identifier and UUID equality plus exactly one returned comment with the selected ID and exact posted-body SHA-256. Use the reconciled issue URL plus `#comment-<comment-id>` as the stable Linear remote comment URL and require it on both create and readback identities. Atomically write the canonical operation-identity projection defined below to `producer_log_path`, the exact readback projection to `producer_output_path`, and then the canonical result below to `operation_result_path`. The operator derives these closed projections from the client responses verified above.

The producer log contains the operation identity fields below; it contains no request/response sequence or outer runner transcript. The invoking workflow owns capture and retention of any underlying client responses or runner transcripts under its execution/evidence policy; this result schema neither carries those transcripts nor guarantees their capture. The feature route separately authenticates its implementation child through process lineage.

```yaml
schema: ticket-operation-result-v1
additional_properties: false
required_fields: [schema, backend, ticket_key, operation, status, owning_route, attempt_number, pr_url, pr_number, reviewed_base_branch, reviewed_base_ref, reviewed_base_sha, reviewed_head_branch, reviewed_head_ref, reviewed_head_sha, comment_body_sha256, remote_comment_id, remote_comment_url, readback_status, readback_ticket_key, readback_comment_id, readback_comment_url, readback_body_sha256, producer_operator, producer_invocation_uuid, producer_log_path, producer_log_sha256, producer_output_path, producer_output_sha256]
fixed_values:
  backend: linear
  operation: comment-readback
  status: PASS
  owning_route: implementation-pipeline
  readback_status: PASS
  producer_operator: agents/linear-operator.md
identity_rules:
  - readback_ticket_key-equals-ticket_key
  - readback_comment_id-and-url-equal-remote-comment-id-and-url
  - readback_body_sha256-equals-comment_body_sha256
  - producer-invocation-is-runtime-derived
  - producer-log-and-output-are-distinct-current-hash-bound-artifacts
producer_log_schema: ticket-operation-producer-log-v1
producer_output_schema: ticket-operation-readback-v1
caller_validator: tools/operational_contracts.py validate-ticket-operation-result --expected-context <caller-owned-path>
```

The producer log uses exactly `schema`, `backend`, `ticket_key`, `operation`, `status`, `producer_operator`, `producer_invocation_uuid`, `comment_body_sha256`, `remote_comment_id`, `remote_comment_url`, `readback_status`, `readback_ticket_key`, `readback_comment_id`, `readback_comment_url`, and `readback_body_sha256`. The readback output uses exactly `schema`, `backend`, `ticket_key`, `status`, `comment_id`, `comment_url`, and `body_sha256`. The caller runs the production validator with its immutable pre-dispatch `--expected-context` artifact before consuming the result. Unknown fields, failed/missing readback, a duplicate/missing comment, wrong issue/comment/body, malformed remote identity, stale producer support hash, or caller-context mismatch blocks consumption and never authorizes ticket/PR progression.

## Procedure: Create

Used by `~/ai/agents/implementation-pipeline-orchestrator.md` Phase 0 when cold-starting from a `brief_path`, and by any operator workflow that needs to file a new issue.

First complete duplicate reconciliation below. Only its zero-candidate outcome permits this single create invocation. Use its resolved `project_id` (or empty when no project was selected) as `resolved_project_id`:

```bash
create_args=(--team "${linear_team_key}" --title "${summary}" --description-file "${brief_path}")
if [[ -n "${resolved_project_id:-}" ]]; then create_args+=(--project "$resolved_project_id"); fi
if [[ -n "${labels:-}" ]]; then create_args+=(--label "$labels"); fi
# Optional story-point estimate and explicit missing-label creation.
if [[ -n "${estimate:-}" ]]; then create_args+=(--estimate "$estimate"); fi
if [[ "${create_missing_labels:-false}" == true ]]; then create_args+=(--create-missing-labels); fi
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli create-issue "${create_args[@]}"
```

For a concrete story-point value, the optional flag is `--estimate 5` (`--estimate <int>` in templates).

`--label` is singular and repeatable, and each occurrence may contain comma-separated label names (e.g. `--label "hardening,segmentation" --label prereq`). Labels resolve inside `${linear_team_key}`. A team label wins over a workspace label with the same name; a same-tier duplicate raises `AMBIGUOUS_LABEL`. When `--create-missing-labels` is supplied, any name without an existing label on the team is created on the fly with a default color; otherwise unknown names raise `LinearClientError("NOT_FOUND", ...)` and the issue is NOT created (so partial-label state is impossible).

`--project` accepts an existing project UUID or `slugId`, resolved against `${linear_team_key}` before create. Missing project tokens raise `NOT_FOUND`; duplicate `slugId` matches across distinct projects raise `AMBIGUOUS_PROJECT`. Project names and URLs are not accepted identifiers.

**Parent linking.** The CLI `create-issue` path does not expose a `--parent` flag. If parent linkage is required and the parent UUID is known, call the underlying Python client `update_issue(..., parent_id=<parent-uuid>)` after creation; if only an ambiguous parent key/reference is available, return `NEEDS_INPUT` with the requested parent reference rather than silently dropping it.

**Label conventions.** When creating tickets, apply project label conventions per `${linear_team_key}`'s setup:

- Risk-reduction / hardening tickets: label `hardening`. Check the project's `AGENTS.md` for the term it prefers (`hardening`, `risk-reduction`).
- Per-project labels (e.g. `~/ai`, `oulipoly`, `workflow`): from the project's routing rules. ~/ai itself uses the `~/ai` label.
- Per-initiative labels (e.g. `segmentation`, `workspace-split`): apply alongside the kind label.

Returns `{"ok": true, "data": {"id": "<uuid>", "identifier": "${linear_team_key}-NNN", "url": "..."}}`. Before reporting success for either a newly created or duplicate-reused issue, compare the stored description with the source brief:

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli verify-issue-description \
    "${issue_key}" --description-file "${brief_path}"
```

The comparison permits only Linear's observed Markdown canonicalization: unordered-list markers may change from `-` to `*` outside fenced code blocks, and one terminal newline may be removed. Changed headings, prose, links, code, list text or structure, interior whitespace, or additional trailing blank lines remain a mismatch. A mismatch is blocking after create/reuse and must never trigger another create attempt. Print the verified key + URL only after `status=MATCH` (the output contract).

**Description from a markdown brief.** The brief is sent without operator-authored transformation. Linear may canonicalize the two narrowly verified Markdown forms above; the operator does not synthesize scope or boundary sections from the brief.

**Duplicate reconciliation before create.** Resolve the selected team key and optional project UUID/slugId, search that same scope, then require one exact case-sensitive full title and matching issue/team/project readback before reuse. Use the internal read-only helper, which calls the existing client's team/project resolution, project-filtered search, and `get-issue` paths:

```bash
PYTHONPATH=$HOME/ai python3 - "${linear_team_key}" "${summary}" "${linear_project_id:-}" <<'PY'
import json, sys
from clients.linear.client import LinearClient, LinearClientError
from clients.linear.create_reconciliation import reconcile_create
try:
    result = reconcile_create(LinearClient(), sys.argv[1], sys.argv[2], sys.argv[3] or None)
except LinearClientError as error:
    print(json.dumps({"ok": False, "error": {"code": error.code, "message": str(error)}}))
    raise SystemExit(2)
print(json.dumps({"ok": True, "data": result}))
PY
```

Check exit zero and exact `ok: true` before proceeding. Keep the returned `team_id` and `project_id` for this operation. The search includes archived issues and requests 100 candidates; because the existing search has no continuation cursor, a full page returns `AMBIGUOUS_ISSUE` instead of claiming uniqueness. Missing/invalid scope, unreadable candidates, or multiple exact candidates block with no create and no successful reuse. Substring/case-only matches are not exact duplicates. When no project was selected, the selected team is the whole search scope; do not invent a project restriction.

- `data.issue` is null: create at most once in that resolved scope, then perform the required description verification.
- `data.issue` is one exact candidate: retain its identifier and URL, create nothing, and run the same required `verify-issue-description` against that identifier and the original brief. Report successful reuse only after `MATCH`.

A description mismatch or failed verification after either branch is `BLOCKED`; retain the candidate/created identity and do not make another create attempt. Reconciliation is a read-before-create check, not an atomic uniqueness guarantee against concurrent external creators.

## Procedure: List Projects

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli list-projects \
    --team "${linear_team_key}"
```

Returns the standard JSON envelope with projects under `data.projects[]`. Parse `id`, `slugId`, `name`, and `archivedAt` (when present) when selecting a project to pass as `linear_project_id`.

## Procedure: List Labels

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli list-labels --team "${linear_team_key}"
```

Returns workspace-level + team-scoped labels visible to the team. Use this when you need to verify a label exists before applying it, or when surfacing the full label inventory for a value-question to the user. Resolution uses team label precedence: team-owned label wins over a workspace label with the same name; duplicate same-tier labels are `AMBIGUOUS_LABEL`.

Use `create-label` when the task is label creation rather than applying labels to a specific issue:

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli create-label \
    --team "${linear_team_key}" \
    --name "hardening"
```

## Procedure: Apply Labels (post-create)

When the orchestrator's brief specifies labels but the issue was already created (e.g., the orchestrator filed a follow-up tracker without labels and now needs to retro-apply), use `apply-labels`:

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli apply-labels "AST-34" \
    --team "${linear_team_key}" \
    --labels "hardening,prereq" \
    --create-missing
```

Default behavior **merges** with the issue's current labels. Pass `--replace` to overwrite. Pass `--create-missing` to create labels on the fly.

The merge avoids the `update_issue` foot-gun where supplying `labelIds=[X]` would silently drop any other labels the issue already had — `apply-labels` queries the issue's current labels via direct GraphQL first and unions in the new ones. It also verifies the issue team before writing; an issue/team mismatch is `INVALID_INPUT` and must stop the operator before any label update.

ACR-126 immediate deferral uses this existing `task=apply-labels` surface as the Linear deferred-state contract: `labels=deferred-to-prototype`, `create_missing=true`, and `replace=false` unless the caller explicitly documents a later cleanup operation.

## Procedure: Transition

Use `task=transition` with required inputs `issue_key` and `target_status`. `target_status` must be one of `clients.linear.client.ROUTINE_MANAGER_OWNED_STATES`: `Todo`, `In Progress`, or `Done`.

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli transition-issue "ACR-130" --target-status "In Progress"
```

ACR-126 does not expand this routine transition contract; P4 original-ticket disposition may use only these same `Todo`, `In Progress`, or `Done` targets when the approved disposition requires a routine Linear status.

The CLI reads the issue, uses `issue.team.id`, lists that team's workflow states, exact-match checks `target_status`, and calls `issueUpdate` with `stateId` only if the initial state ID differs. Its `ok:true` means the routine operation succeeded, not that final state was verified. Report the returned evidence separately:

- `requestedStatus`: the normalized caller request.
- `resolvedTarget`: `{id, name}` from the owning team's state catalog, not an issue-state observation.
- `initialState`: `{id, name}` observed in the initial issue read (possibly null fields).
- `outcome=acknowledged`: the mutation returned literal `success:true`; no post-update state was read.
- `outcome=already_matching`: the initial state ID matched the target; no mutation was sent or acknowledged.

Print `KEY initial observation: NAME (ID); requested: STATUS; resolved target: NAME (ID); outcome: OUTCOME; post-read: not performed`. Never present the target as an observed after-state. Default operation requires no extra read. False or malformed acknowledgements remain errors, not success.

When the caller explicitly requires state readback, after successful transition run the existing `get-issue` command with the returned `issue_id` (not a potentially moved identifier). Report that read's `data.state.id` and `data.state.name` separately as a **point-in-time readback**, comparing the observed ID to `resolvedTarget.id`. Only an actual matching ID supports readback match; missing state/ID is unverifiable. On mismatch, missing state, or read failure, retain the transition outcome but return `BLOCKED` for the requested verified-readback task, disclosing the observed result or error. Do not infer the target, automatically retry, or overwrite concurrent changes. Even a matching read does not guarantee durable state. No readback is implied by acknowledgement or initial match.

Workflow states are per-team. Never hard-code state IDs or reuse a state ID observed on another team. If there is an unreadable issue, `$LINEAR_API_KEY` is missing, `target_status` is out-of-contract, or the target state is unknown or ambiguous, return `BLOCKED`.

## Procedure: Search

Linear search and listing use the live CLI and the same `(team, project?, labels[])` tuple filters. Use `search-issues --team-key` for filtered search and `list-issues --team` for list-style team discovery:

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli search-issues \
    --team-key "${linear_team_key}" \
    ${linear_project_id:+--project "${linear_project_id}"} \
    ${labels:+--label "${labels}"} \
    --title-contains "<first 8 words>"
```

```bash
PYTHONPATH=$HOME/ai python3 -m clients.linear.cli list-issues \
    --team "${linear_team_key}" \
    ${linear_project_id:+--project "${linear_project_id}"} \
    ${labels:+--label "${labels}"}
```

`--project` accepts UUID or `slugId`; `--label` is singular and repeatable. The client resolves project and label names before building `IssueFilter`, so raw project slugs and label names are not sent as filter identity.
Both CLI commands return the standard JSON envelope. Parse `identifier`, `title`, and `state.name` from `data[]`, then emit the operator's `search` output in the line-oriented form below.

## Output Contract

For `read`: write the rendered ticket to `output_path`; print the key, title, state, parent in a brief block.
For `comment`: when `operation` is omitted, print the new comment ID + a confirmation line; when `operation=comment-readback`, atomically write the producer log to `producer_log_path`, the readback projection to `producer_output_path`, and the `ticket-operation-result-v1` result to `operation_result_path`, then return that structured result.
For `create`: after description readback returns `MATCH`, print the created or duplicate-reused key + URL.
For `update-estimate`: after both stages succeed, print the issue key, refined estimate, and comment ID for the durable Markdown note. Otherwise return the terminal `BLOCKED` result from Procedure: Update Estimate, identifying the failed stage, observed error, and known outcome of each stage. An asynchronous handle or dispatch status is not a terminal task result.
For `list-projects`: print one line per result (`ID  state  name`, omitting blank state).
For `list-labels`: print one line per result (`ID  name`).
For `create-label`: print the new label ID + name.
For `apply-labels`: print the issue key + applied label names.
For `transition`: print the initial observation, requested status, resolved target and `acknowledged` or `already_matching` outcome per Procedure: Transition; disclose whether a post-read was performed. Explicit readback results are separate point-in-time observations, never target-derived after-status.
For `search`: print one line per result (`KEY  state  title`).

## Stop Conditions

- Return `BLOCKED` if `$LINEAR_API_KEY` is unset or returns 401 (likely rotated; ask the user to refresh at <https://linear.app/settings/api>).
- Return `BLOCKED` if the issue key doesn't resolve (typo or moved between teams; identifiers are not stable across team key changes).
- Return `BLOCKED` if `target_status` does not resolve to exactly one workflow state on the issue's owning team, if the target state is unknown or ambiguous, if `target_status` is out-of-contract, or if the issue is unreadable before mutation.
- Return `NEEDS_INPUT` if `create` requires a label or parent the caller did not supply and the project's labelling rules in `AGENTS.md` make the choice non-obvious.
- Return `BLOCKED` if `${linear_team_key}` does not match a real team (call `list-teams` to verify).
- Return `BLOCKED` on `AMBIGUOUS_LABEL`, `AMBIGUOUS_PROJECT`, or `INVALID_INPUT` issue/team mismatch; these indicate the caller must choose a label/project/team explicitly before mutation.

## Project Reference

| Project | Team key | URL pattern |
|---------|---------|-------------|
| Agents | `AGE` | `https://linear.app/<workspace>/issue/AGE-XX/...` |
| Agent Strategy | `AST` | `https://linear.app/<workspace>/issue/AST-XX/...` |

Known-key read/comment examples in this operator use issue keys such as `AGE-34` or `AST-34`; create/list/search examples use `${linear_team_key}` because those tasks are team-scoped.

## Notes vs. JIRA Operator

| Aspect | JIRA Operator | Linear Operator |
|---|---|---|
| Description format | ADF JSON | Markdown |
| Comment format | ADF JSON | Markdown |
| Auth | HTTP Basic (email + token) | Bearer-style header |
| Status transitions | `transition` task supported | `transition` task supported via `issueUpdate(stateId)` after resolving the issue team's workflow state |
| Hierarchy | Epic → Task with `parent: {key}` | Parent issue with `parent.id` (UUID) |
| Search | JQL | GraphQL `issueFilter` |
| Idempotent comment | Not natively (the operator searches first) | `upsert-comment` matches by leading title |

The Linear operator is intentionally narrower than `jira-operator`. Capabilities like rich-tableau ADF rendering, table cells, and layered marks are not needed because Linear renders Markdown directly.
