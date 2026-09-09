---
workflow:
  id: agents-cli
workflow_dispatch_contract:
  orchestrator: "root orchestrator or workflow operator invoking agents CLI"
  inputs:
    - "model name, worktree path, prompt file, dedicated runner log path, and distinct canonical output path for an agent dispatch"
    - "sub-agent delegation, question-handling, or parallel-writer context"
  expectations:
    - "standardizes agents CLI invocation and tee-based log capture for pipeline work"
    - "keeps complete invocation, optional session, provider payload, and result streams separate from canonical provider results and child-owned reports"
    - "routes delegated user questions through the root-owned question artifact convention"
    - "requires branch work and authored tracked-file mutation to run from git worktrees; central branch-tracking permits only the guarded default-branch synchronization in conventions/worktree-isolation.md"
  outputs:
    - "consistent agents command shape for prompts, complete logs, distinct canonical outputs, and long-running background work"
    - "stable prompt and log naming conventions for post-run review"
  non_goals:
    - "does not replace the agent-runner README as the authoritative CLI reference"
    - "does not define model role selection beyond pointing to the model-role matrix"
---
# `agents` CLI — Workflow Conventions

## Declared roles

`orchestration`, `validator`, `formatter`.

This file-local declaration reflects this workflow's ownership of dispatch sequencing, pre-dispatch contract validation, and canonical prompt/log command formatting.

CLI reference: `/home/nes/projects/agent-runner/README.md`.
That is the authoritative source for flags, options, named-agent resolution, TOML model config, and invocation shapes. This doc only covers the conventions layered on top for pipeline work.

## Workflow Dispatch Surface

### Orchestrator

root orchestrator or workflow operator invoking agents CLI

### Inputs

- model name, worktree path, prompt file, dedicated runner log path, and distinct canonical output path for an agent dispatch
- sub-agent delegation, question-handling, or parallel-writer context

### Expectations

- standardizes agents CLI invocation and tee-based log capture for pipeline work
- keeps complete invocation, optional session, provider payload, and result streams separate from canonical provider results and child-owned reports
- routes delegated user questions through the root-owned question artifact convention
- requires branch work and authored tracked-file mutation to run from git worktrees; central branch-tracking permits only the guarded default-branch synchronization in conventions/worktree-isolation.md

### Outputs

- consistent agents command shape for prompts, complete logs, distinct canonical outputs, and long-running background work
- stable prompt and log naming conventions for post-run review

### Non-goals

- does not replace the agent-runner README as the authoritative CLI reference
- does not define model role selection beyond pointing to the model-role matrix

## Pre-dispatch contract resolution

1. Resolve the selected operator path: use the project wrapper when execution is in project scope and the wrapper is current; otherwise use the base operator.
2. Read the operator contract sidecar when present at `contracts/operators/<operator-name>.yaml`; otherwise read the operator's `## Contract` block. Parse the YAML and validate `schema: operator-contract-v1`.
3. Apply `defaults:` to the input set and verify all required inputs are present from defaults or caller-supplied values.
4. At the caller boundary, honor `must_delegate:` by selecting the operator as the execution endpoint and honor `forbidden_direct:` by refusing prohibited direct work. Do not inline procedure that belongs to the operator or copy `must_delegate:` into the prompt as an instruction for the selected endpoint to redispatch itself.
5. Inspect the validated contract's `secrets:` list before dispatch. When it is empty, invoke `agents -a <agent.md> -p <worktree-path> -f <prompt-file> 2>&1 | tee <log>` per the canonical command shape. When it is non-empty, replace only the capture sink with `python3 ~/ai/tools/secret_safe_capture.py capture --contract <resolved-contract> --log <log>` as shown below. The agent file's `model:` frontmatter drives model selection; do not pass `-m` alongside `-a`.

Once the selected operator invocation begins, its own `must_delegate:` declaration is satisfied for that operation. The endpoint executes its bounded procedure directly and never dispatches the same operator for the same operation. Valid child delegation remains allowed only for a different concern explicitly owned by the endpoint procedure; it uses the canonical invocation and capture shape so the caller-to-endpoint and endpoint-to-child edges remain visible in process-tree evidence.

The workflow sidecar at `contracts/workflows/<workflow-id>.yaml`, when present, is the optimized workflow dispatch surface. Otherwise use the `workflow_dispatch_contract` frontmatter. The operator contract sidecar is the analogous optimized surface for operator dispatch.

## Standard invocation shape

The `agents` invocation core has two shapes, selected by whether you are dispatching a defined agent or an ad-hoc prompt. The resolved contract then selects raw `tee` or declared-secret capture as the sink:

```bash
# Defined agent: frontmatter drives the model. No -m.
agents -a <agent.md> -p <worktree-path> -f <prompt-file> 2>&1 | tee <log-path>

# Ad-hoc / undefined agent: no agent file to read frontmatter from, so -m is required.
agents -m <model> -p <worktree-path> -f <prompt-file> 2>&1 | tee <log-path>

# Selected operator declares one or more secrets: preserve the agents invocation core.
agents -a <agent.md> -p <worktree-path> -f <prompt-file> 2>&1 | python3 ~/ai/tools/secret_safe_capture.py capture --contract <resolved-contract> --log <log-path>
```

- `-a <agent.md>`: path or named-agent reference; the `model:` value in the agent's frontmatter selects the model. **Do not** combine with `-m` — `-m` shadows the frontmatter and silently defeats any model rebalancing.
- `-m <model>`: one of `gpt-high`, `gpt-xhigh`, `gpt-medium`, or another configured model id. Only used when there is no `-a`. See `~/ai/models/roles.md` for selection guidance.
- `-p <worktree-path>`: the agent's working directory; for branch work or authored tracked-file mutation, this MUST be a git worktree per `~/ai/conventions/worktree-isolation.md`.
- `-f <prompt-file>`: the prompt as a Markdown file, usually in `.tmp/` or `.build/`.
- `2>&1 | tee <log-path>`: capture the complete merged runner envelope into a dedicated `.log` file. A successful stream contains exactly one `OULIPOLY_INVOCATION`, exactly one optional `OULIPOLY_SESSION` immediately after it, provider payload, then exactly one terminal `OULIPOLY_RESULT`; it is never a canonical provider result/report path. The session envelope is optional because the production runner emits none when session resolution/capture returns `emitted=false`.
- `2>&1 | secret_safe_capture.py capture ...`: the required capture form when the selected contract declares secrets. The helper validates `schema` and `secrets` before opening the log, replaces every non-empty declared environment value before writing to stdout or disk, and otherwise preserves the complete byte stream. Missing, blank, malformed, wrong-schema, non-list, duplicate, or invalid-name contract data is blocking and creates no new log.

Use the README for other invocation forms. In `~/ai/`, the patterns above are the default pipeline entry point.

## Log Capture And Consumption

The canonical `2>&1 | tee <log-path>` shape is a producer-side capture rule. It prevents live dispatch filters from hiding invocation markers or terminal evidence; it does not require an auditor to load the complete resulting log into model context.

The declared-secret capture form is the only non-`tee` producer sink. It is not a truncating or summarizing filter: non-secret output, runner markers, provider payload extraction, and process-evidence parsing remain byte-complete. Callers must pass the exact already-resolved operator contract rather than hard-code credential names. For auth diagnostics, run `python3 ~/ai/tools/secret_safe_capture.py presence --contract <resolved-contract>`; its output contains only each declared environment name and `present` or `absent`, never a value.

Consumers inspect completed logs programmatically with targeted search, bounded line ranges, or bounded tails. They MUST NOT add arbitrary maximum log-byte acceptance thresholds to proposals, expected-process manifests, audit history, or gate logic. Runtime retention, rotation, or truncation markers are context for evidence availability, not failures by themselves; use `~/ai/conventions/workflow-execution-violations.md` when a specific required fact is genuinely unavailable.

## Prompt / log file conventions

- Prompts live in the project's `.tmp/` directory.
- Prompts for `~/ai/` authoring work live in `~/ai/.build/`.
- Name prompts by phase: `<task>-<phase>.md`.
- Example: `slice-007-research.md`, `slice-007-proposal.md`, `slice-007-risk-audit.md`.
- Logs pair one-to-one with prompts: `<task>-<phase>.log`.
- For revisions, suffix by round: `slice-007-proposal-revise.md`, `slice-007-proposal-revise2.md`.
- For parallel risk rounds, log per round: `slice-007-risk-audit.log`, `slice-007-risk-audit2.log`, `slice-007-risk-audit3.log`.

## Runner Log And Canonical Output Separation

- Every `agents` invocation has one complete `.log` sink and a different canonical output path. No command may use the same path for `tee` and a child-owned or extracted `.md`/`.json` result.
- For an ad-hoc or other stdout-producing child, run `python3 ~/ai/tools/operational_contracts.py extract-provider-payload --log <log> --output <result> --metadata <extraction.json>` only after the invocation completes. The helper requires exactly one valid invocation marker, at most one optional session marker immediately after invocation and before payload, exactly one ordered terminal successful result sentinel, matching invocation/result UUIDs, session `agent_runner_invocation_id` equality when present, and no duplicate, malformed, misplaced, post-payload, or failure envelope; it atomically writes only the provider payload and excludes the session marker.
- For a file-producing child, retain the complete `.log`, require the child-owned canonical output at the distinct prompted path, and hash/validate that file independently. Do not overwrite it with the runner stream or reconstruct it from the log.
- Process evidence parses invocation UUIDs only from complete `.log` files and verdict/schema content only from canonical outputs. Expected-process nodes name both distinct paths and the post-dispatch log/output hash fields; dispatch evidence freezes the actual hashes.
- Canonical Markdown begins with its own required verdict/schema header. Canonical JSON begins with its own schema object/key. Neither may begin with `OULIPOLY_INVOCATION`, `OULIPOLY_SESSION`, `OULIPOLY_RESULT`, or `OULIPOLY_FAILURE`.

## Sub-agent delegation

All sub-agent invocation goes through the `agents` CLI.

- Pipeline docs should describe model choice, prompt shape, working directory, and log capture.
- CLI reference details stay in `/home/nes/projects/agent-runner/README.md`, not in `~/ai/`.

## Sub-agent questions

Sub-agents do not talk to the user directly. When a sub-agent needs user input, it writes a question artifact under `~/ai/conventions/agent-questions-and-session-graph.md`, returns `NEEDS_INPUT:<question_artifact_path>`, and stops.

The root orchestrator reads the artifact, presents the question and structured options to the user, writes the paired answer artifact, and continues the originating work through the feature-detected resume path or the session-files fallback from that convention. Downstream workflow steps that depend on the answer are blocked until continuation evidence exists.

## Worktree Isolation

Every branch-work or authored-tracked-file-mutating agent runs in a worktree, regardless of concurrency. Read-state operations may inspect the central checkout; single-writer branch work must not use the main checkout.

- Use one worktree per branch-work or authored-tracked-file-mutating agent.
- Read-state agents can inspect the central checkout without tracked-file edits. Authorized default-branch deployment synchronization is a separate branch-tracking operation, allowed only under the guarded exception in the isolation convention; it is not authoring or feature work.
- See `~/ai/conventions/worktree-isolation.md` for the rule, central-checkout limits, and setup.

## Long-running agents

For agents expected to run longer than about 30 seconds:

- Dispatch with the orchestrator's background-execution mode, one Bash tool call per child.
- Canonical long-running shape (defined agent; frontmatter drives model):
  ```python
  Bash(
      command="agents -a <agent.md> -p <worktree-path> -f <prompt-file> 2>&1 | tee <log-path>",
      run_in_background=True,
      description="Run <child role>"
  )
  ```
  When the selected operator contract declares secrets, preserve the same `agents` arguments and replace only `tee` with the declared-secret capture sink from `## Standard invocation shape`.
  Use `-m <model>` instead of `-a <agent.md>` only when the dispatch has no agent file (ad-hoc prompt). Never combine `-m` with `-a`.
- Do not use shell job control or custom watcher machinery for `agents` dispatches. Forbidden patterns: trailing shell `&`, `disown`, bundled wrapper scripts around multiple `agents` calls, shell `wait` after `agents` fanout, PID-capture plus PID waits around `agents` invocations, trace polling loops as the waiting primitive, and piping live `agents` stdout through truncating filters such as `head -N` or `grep -m1`.
- The forbidden trace-loop class includes repeated `agents trace --json` inspection used to decide when a child is complete.
- Do not poll continuously; use the Bash task completion notification.
- Capture the Bash tool task id so the output can be retrieved afterward; do not capture shell `$!` PIDs around `agents` invocations.
- Keep the `tee` log path stable so post-mortem inspection does not depend on terminal scrollback.
- `agents trace --json` is for post-run inspection, audit evidence, session topology, and eval input. It is not the active completion-wait primitive for a running child.

For parallel risk gates, dispatch all rounds as separate Bash-background tool calls, then collect outputs sequentially after their task notifications arrive.

## Long-running / parallel agents on opencode runtimes (agent-bash spooler — DO NOT POLL)

On opencode (gpt-*) runtimes, the bash tool is the **agent-bash spooler**: every command runs detached in the
background automatically (no opencode bash timeout applies) and the completion is **delivered back to you** by
agent-runner — you do not poll and you do not manage the child.

- **Dispatch exactly the canonical shape** through the bash tool. For `secrets: []`, use
  `agents -a <agent.md> -p <worktree> -f <prompt> 2>&1 | tee <log>`; for declared secrets, preserve that invocation core and use the secret-safe sink from `## Standard invocation shape`. The spooler returns quickly: short commands
  return their output in-call; long ones return a `handle` and keep running detached.
- **Delivery is push, not poll.** When the child completes, agent-runner resolves your session and delivers an
  `[OULIPOLY NOTIFICATIONS]` envelope: headless sessions are **resumed** with it at the next turn; live interactive
  (PTY) sessions receive it **injected as input**. Continue other work after dispatching; the result arrives.
- A returned `handle` may be checked once opportunistically (call bash with `{handle}`), but DO NOT loop-poll —
  the wake is the completion mechanism.
- **Deprecated:** `agents-bg`, `agents-bg-poll`, `agents-bg-wait` (the old tmux stopgap). Do not use them and do not
  poll their logs. Do NOT use raw `&`/`nohup` (session-tied, orphans the child).

The "do not poll / no wrapper script / no shell `&`/`disown`/`wait` / no trace-loop" prohibitions above now apply on
ALL runtimes: Claude harness runtimes use `run_in_background=True` + the Bash completion notification; opencode
runtimes use the agent-bash spooler + agent-runner wake. Parallel fan-out on opencode: dispatch each child as its own
bash call (each returns fast), continue working, and handle each completion envelope as it is delivered.
