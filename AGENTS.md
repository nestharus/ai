# `~/ai/` Master Routing & Topology

Purpose: shared routing and workflow topology for any project that uses `~/ai/` as its workflow library.

Project `AGENTS.md` files should reference this file for the generic routing layer, then add only repo-specific overrides, operators, infrastructure, and exceptions.

Routing precedence and conflict resolution live in [`~/ai/conventions/workflow-routing.md`](conventions/workflow-routing.md). This file stays lean and pointer-heavy.

Dispatch terminology: in RCA and bug workflows, "reproduce" means create a deterministic failure signal only when the input is symptom-only. When a failing test command, node ID, CI log, red-phase report, or structured failure already exists, that signal is the reproduction; carry it forward and run the same failing signal with the candidate fix instead of dispatching redundant reproduction work.

## Mandatory General Landable-Change Lifecycle

This section overrides the generic workflow-routing convention and the legacy catalog links below for any general task that produces a landable change to code or to a behavior-authoritative artifact; either is a `protected change` below. An artifact is behavior-authoritative by causal capability, not extension: configuration, agent instructions or prompts, workflow or routing definitions, migrations, deployment artifacts, and similar sources qualify when they can alter implementation, review, correction, merge, deployment, or runtime behavior. Ordinary prose or documentation that cannot alter behavior is not a protected change merely because it is text. This lifecycle applies regardless of ticket count and includes features, bug fixes, behavioral changes, and behavior-preserving refactors. Trigger-specific discovery or operational workflows may still run when their own cues apply, but any resulting protected change enters this lifecycle.

Default implementation and correction for protected changes use directly dispatched ad-hoc agents in isolated worktrees. Do not route protected changes to `implementation-pipeline-orchestrator`, `feature-orchestrator`, or `refactoring-orchestrator`. Those orchestrators and their supporting workflow entries are non-routable legacy references unless the user explicitly requests one by name; explicit use does not replace or satisfy any gate in this section.

De-routing those orchestrators removes their default machinery, not applicable delivery outcomes. Before implementation, the root derives the purpose, environment, affected actors and delivery obligations from the request, ticket or brief, project policy and task-specific contracts. These may include ticket lifecycle/readback, estimates, dependency and integration order, bounded slicing, shim lifecycle, worktree isolation, PR state, external-mutation authority and final handoff. Own each applicable obligation or assign it to a direct ad-hoc agent; do not reconstruct a fixed legacy pipeline. Keep concise, useful context and decision notes rather than requiring immutable problem generations or custody packages for ordinary work.

Code Review Workflows owns observation, not this delivery loop. Read the current authoritative checkout under `/home/nes/projects/code-review-workflows`, particularly `README.md`, `AGENTS.md`, and `risk-axis-reviewers/{README.md,orchestration-order.md,semantic-review-contract.md,review-scope-adapter-contract.md,decision-semantics.md}`. It exclusively defines observational reviewer roles and investigative procedure. Do not copy its definitions or import historical corrective terminals. Route its investigative roles with opaque `gpt-xhigh`, without resolving or attesting underlying provider/model/effort settings.

The mandatory lifecycle is **observe → interpret against purpose/environment → decide across choices → correction/solution search → observe consequences**:

1. **Observe.** Supply material and the real question to read-only investigation. Collect source-grounded evidence, causal explanations, counterevidence, uncertainty and leads. Follow material relationships beyond starting files or ticket boundaries within actual access authority. Use distinct investigative dimensions and focused agents where useful and authorized, not a compulsory reviewer cohort, unchanged sweep or predetermined investigation budget. A review observation is not a recommendation, correction instruction or merge decision.
2. **Interpret.** The consuming workflow separately relates observations to the actual purpose, environment, actors and material consequences. Determine relevance rather than enforcing every incidental constraint: a constraint's violation may show that the constraint should be discarded. Preserve the observation and its evidence even when no change is warranted; do not narrow investigation to suppress inconvenient or apparently unrelated evidence.
3. **Decide.** Consider all identified decisions and their interactions, available choices, tradeoffs, rationale, accepted risks and user-owned questions together. This is NOT a specification or detailed solution plan. Explicitly distinguish accepted/no-action observations from unresolved consequential decisions. An irrelevant incidental-constraint observation can receive a reasoned no-action disposition; a consequential defect requires a decision on the affected outcome, not an automatic implementation mandate. Conflicting decisions must be reconciled or surfaced together. Unresolved user-owned consequential decisions pause affected work and prevent its completion; do not silently choose for the user. A non-actioned observation does not itself prevent completion.
4. **Correct / search for a solution.** Dispatch separate ad-hoc implementation agents in isolated worktrees with the decisions, relevant evidence and authority bounds. They search for and implement solutions satisfying the decisions rather than transcribing reviewer outputs into patches. If decisions conflict or prove infeasible, return to interpretation/decision instead of silently changing the goal. Review output alone grants no correction authority.
5. **Observe consequences.** Run applicable verification and examine the change and its effects. Retain useful source-bound evidence and uncertainty, including newly discovered consequences of correction; feed those back through interpretation and decision. The consumer decides what further observation is warranted by changed conditions and material unknowns, without compulsory unchanged sweeps or arbitrary count/time/depth limits. An interrupted investigation returns partial evidence and outstanding questions, not an inferred success. Neither static checks nor absence of observations proves universal safety or stochastic efficacy.
6. **Dispose / deliver.** The root owns verification, remaining decisions, delivery obligations and final disposition. Before merge, confirm that applicable checks and decisions still describe the content being delivered; revisit affected conclusions after changes. Complete only when consequential decisions are resolved, required verification and obligations are met, and accepted risks/no-action reasons and remaining uncertainty are visible. No universal reviewer `PASS` or zero-observation count supplies merge authority. External mutation requires the authority already granted by the task and environment.

Ordinary observation needs concise source/result references sufficient to understand what evidence supports, not a mandatory Git identity, immutable snapshot/hash manifest, custody pipeline, identity attestation, sandbox/file-lock or no-fetch rule. Normal configured Git acquisition does not by itself invalidate review of exact content. Preserve honest provenance and distinguish source reasoning from actual execution; never reattribute old results to changed content. Task-specific release/incident identity requirements, actual access/privacy restrictions and branch-work isolation remain binding. Do not build a duplicate delivery state machine to transport observations.

### Process refinements and transition authority

Process-only Markdown refinements do not by themselves select semantic product review or empirical evals. Changes to agent matching/recognition—what the agent recognizes, which role is selected, or which observations it can identify—warrant agent-design review even when written only in Markdown. Classify by changed capability, not extension; mixed changes retain the matching/recognition review requirement. Other protected changes still use this lifecycle. Explicitly selected empirical evaluations retain their own contracts; static document checks cannot establish agent efficacy.

This proposed consumer policy cannot govern its own acceptance. Until it and the prerequisite observation protocol are properly landed, the pre-change governing lifecycle still controls this patch: root owns the immutable problem, exact implementation identity, independent claim/evidence and full `unscoped corrective` gates, final checks and delivery obligations. Draft preparation against a concurrent CRW candidate is not compatibility approval; root must recheck the actual landed interface before integration. Active runs and historical results retain their selected policy, without retrospective relabeling or implicit bypass.

### Governed Emergency Disposition

The root may activate this disposition only when frozen evidence establishes an exact active incident and that waiting for the complete normal review would itself create material ongoing restoration harm. Urgency or a severity label alone cannot activate it, and neither a subordinate agent, CodeRabbit, nor a legacy pipeline can activate or satisfy it. It is a one-off evidence-triggered disposition, not a fixed emergency pipeline or an automatic bypass. Activation uses only merge and rollback mutation authority already granted by the task and environment; the disposition cannot manufacture missing authority.

Before merge, freeze an immutable emergency record identifying the restoration outcome and affected actors; one exact implementation identity and its bounded scope; the minimum incident-specific safety evidence; either one exact rollback action or explicitly bounded rollback identities; all remaining review debt; and exactly one named retrospective owner. Run and record every bounded test or check that can safely execute within the incident window. Record unavailable checks as explicit debt, never as inferred passes. The root retains the normal delivery-obligation ownership. Only the exact implementation identity in the record may merge as the emergency implementation. The same record governs rollback without an additional approval gate: rollback may execute only its exact recorded action or one of its bounded identities, including by merging a bounded rollback identity. If the authority already granted by the task and environment does not permit the merge or rollback, the disposition cannot execute that mutation.

At emergency merge, that identity has not completed the normal consumer-owned lifecycle and remains untrusted. Preserve its pre-merge record and evidence without silent revision. Immediately after restoration, the retrospective owner must take the exact merged identity and preserved evidence through observation, interpretation and decision under the normal lifecycle. Decided corrections must land as separately identified follow-ups completing that lifecycle before merge; they must not rewrite emergency evidence or imply pre-merge review completion.

CodeRabbit, reviewers or gates from the legacy implementation pipeline, and `~/ai/workflows/pr-review.md` are optional only when the user explicitly requests them. They never substitute for this consumer-owned lifecycle, establish delivery readiness by themselves, or activate the emergency disposition.

Previously merged changes supported only by legacy pipeline evidence must not be assumed trustworthy. Before extending or relying on them for release, inspect the relevant merged content and preserved evidence through this lifecycle, resolve consequential decisions and verify applicable claims. Preserve historical failures and limits; subsequent observation does not turn an earlier run into a pass.

## Declared roles

This file's classifications under `~/ai/conventions/code-quality.md` § Declared roles:

- `mapper` — Maps workflow triggers and operator entries to their routed agent, workflow, input, and model contracts.
- `orchestration` — Defines activation, topology, and strategy-selection flow for work across the shared `~/ai/` workflow library.
- `parser` — Specifies dispatch contract inputs and invocation fields that callers must supply to routed operators.

## Quick Activation: Work Manager Mode

When the user says **"you are work manager"** (or any equivalent designation), or otherwise places you in a long-running session managing a backlog of work units across multiple repos / dispatching orchestrators / surfacing frictions to the user — **operate as the Work Manager** per [`~/ai/agents/work-manager-operator.md`](agents/work-manager-operator.md). Read that file in full and follow its filing discipline, dispatch discipline, delegation patterns, and anti-scope. The default rule once activated: keep the user's context clean by delegating execution; do not perform multi-WU work inline.

When in Work Manager mode, load the file matching the declared flavor at session start: `manager-max` -> `~/ai/agents/work-manager-operator-max.md`, `manager-pragmatic` -> `~/ai/agents/work-manager-operator-pragmatic.md`, `manager-hackerman` -> `~/ai/agents/work-manager-operator-hackerman.md`. Default to `manager-max` when no flavor is declared; in short, default to manager-max. Also read `~/ai/agents/work-manager-operator.md` as the Work Manager overview for filing discipline, dispatch discipline, delegation patterns, ticket-backend pluggability, and anti-scope.

Strategy selection happens before dispatch. Any protected change, including one arising from multi-ticket work, user-facing or behavioral work, or an internal refactor, routes to the Mandatory General Landable-Change Lifecycle above and uses direct ad-hoc implementation and corrective agents rather than the three legacy delivery orchestrators. Continue to use roadmap, prototype, release, RCA, AGENTS maintenance, or another specialized route only when its specific trigger applies; any protected change still returns to the mandatory lifecycle. Manager flavor remains orthogonal: max/pragmatic/hackerman selects risk posture inside ad-hoc assignments and final disposition without replacing the required consumer-owned lifecycle.

## Project Setup Pattern

Projects organized for agent-driven workflows follow the umbrella layout `~/projects/<name>/{trunk,planning,worktrees}/`: the git repository sits at `trunk/`, machine-local planning artifacts live in `planning/<branch>/`, and per-WU worktrees live in `worktrees/<branch>/`.

- Full layout rule (single-repo and multi-repo umbrella variants): [`~/ai/conventions/project-layout.md`](conventions/project-layout.md).
- `worktree_path`, `scratch_dir`, `planning_dir` semantics for an orchestrator-driven WU: [`~/ai/agents/implementation-pipeline-orchestrator.md`](agents/implementation-pipeline-orchestrator.md) § Required Inputs.
- Machine-local planning artifacts live outside the worktree/repo diff; do not add new `.gitignore` rules for this WU's machine-local planning artifacts; upload durable outputs to the ticket when they need to survive.

## Mailbox Recovery

Agent-bash completion notifications are durable mailbox rows. If delivery repeats or floods, contain it with `oulipoly-agent-runner mailbox pause --session-id <id>`, then use `status`, `list`, `search`, and bounded `show --include-artifacts --max-bytes <n>` commands to review the queue.

After review, acknowledge only the intended inclusive range with `mailbox ack --session-id <id> --from-seq <first> --to-seq <last>`; newer rows remain pending. Use `mailbox resume --session-id <id>` when recovery is complete. Do not acknowledge unread rows, edit `pid-identity.db` directly, or rebuild/downgrade `state.db` as mailbox recovery.

## Operator Routing Table

Optimized contract sidecars live under `contracts/operators/` and `contracts/workflows/`. Dispatchers read those first and fall back to an operator `## Contract` block or workflow `workflow_dispatch_contract` frontmatter only when a sidecar is missing.

### AGENTS maintenance

- `agentsmd-curator` - Audit or edit `AGENTS.md` and the operator directory when routing, frontmatter, or topology may have drifted.
  File: [~/ai/agents/agentsmd-curator.md](agents/agentsmd-curator.md) | Inputs: `mode`, `repo_root`, `agents_md?`, `agents_dir?`, `findings_to_fix?`, `operator_file?`, `routing_entry?` | Model: `gpt-high`

- `agentsmd-maintenance-orchestrator` - Run the full AGENTS maintenance loop when the shared operator catalog or routing layer needs audit, triage, risk-gating, and verification.
  File: [~/ai/agents/agentsmd-maintenance-orchestrator.md](agents/agentsmd-maintenance-orchestrator.md) | Inputs: `repo_root`, `agents_md?`, `agents_dir?`, `triage_policy?`, `risk_gate_required?` | Model: `gpt-xhigh`

- `workflow-design-auditor` - Audit workflow document design against the shared design-pattern corpus; does not audit runtime execution.
  File: [~/ai/agents/workflow-design-auditor.md](agents/workflow-design-auditor.md) | Inputs: `workflow_file`, `repo_root`, `design_patterns_ref?`, `context_files?`, `audit_history_path?`, `report_path?`, `mode?` | Model: `gpt-xhigh`

- `agent-design-auditor` - Audit operator prompt design, operator-file-format conformance, and single-concern shape; does not maintain AGENTS routing.
  File: [~/ai/agents/agent-design-auditor.md](agents/agent-design-auditor.md) | Inputs: `operator_file`, `repo_root`, `operator_format_ref?`, `design_patterns_ref?`, `context_files?`, `audit_history_path?`, `report_path?`, `mode?` | Model: `gpt-xhigh`

- `workflow-reviewer` - Verify that a multi-step operator run actually followed its required procedure and produced the expected outputs.
  File: [~/ai/agents/workflow-reviewer.md](agents/workflow-reviewer.md) | Inputs: `operator_file`, `step_log`, `expected_outputs?`, `mode?` | Model: `gpt-xhigh`

- `process-tree-auditor` - Audit an `agents trace --json` process tree plus companion artifacts to verify root-delegated workflow execution.
  File: [~/ai/agents/process-tree-auditor.md](agents/process-tree-auditor.md) | Inputs: `operator_file`, `process_tree_path`, `root_invocation_uuid`, `subtree_root_uuid?`, `expected_process`, `companion_artifacts`, `audit_history_path?`, `mode?`, `report_path?` | Model: `gpt-high`

- `workflow-process-auditor` - Audit workflow run artifacts for procedure adherence; consumes process-tree reports as evidence but does not replace `process-tree-auditor`.
  File: [~/ai/agents/workflow-process-auditor.md](agents/workflow-process-auditor.md) | Inputs: `workflow_file`, `run_artifacts`, `repo_root`, `process_tree_report_path?`, `expected_process_path?`, `audit_history_path?`, `report_path?`, `mode?` | Model: `gpt-xhigh`

### Coverage / behavior / test authoring

- `coverage-analyzer` - Build a coverage inventory when you need covered vs. uncovered code, dead tests, or regression-baseline data.
  File: [~/ai/agents/coverage-analyzer.md](agents/coverage-analyzer.md) | Inputs: `task`, `worktree_path`, `scope?` | Model: `gpt-high`

- `coverage-auditor` - Judge test quality after coverage analysis or new test work, especially for captured behavior, dead tests, or low-value assertions.
  File: [~/ai/agents/coverage-auditor.md](agents/coverage-auditor.md) | Inputs: `task`, `worktree_path`, `test_files?`, `behavior_specs?` | Model: `gpt-xhigh`

- `coverage-expansion-operator` - Orchestrate coverage expansion from uncovered code through P0 selection, behavior investigation, test writing, strict xfails, and report artifacts.
  File: [~/ai/agents/coverage-expansion-operator.md](agents/coverage-expansion-operator.md) | Inputs: `repo_root`, `worktree_path`, `scratch_dir`, `planning_root?`, `spec_dir?`, `scope?`, `coverage_report?`, `agents_dir?`, `report_slug?` | Model: `gpt-high`

- `risk-assessor` - Rank uncovered code by outage potential, blast radius, and business value before choosing what to test first.
  File: [~/ai/agents/risk-assessor.md](agents/risk-assessor.md) | Inputs: `uncovered_areas`, `worktree_path`, `coverage_data?` | Model: `gpt-xhigh`

- `behavior-investigator` - Research intended behavior for suspicious or uncovered code before any test is written.
  File: [~/ai/agents/behavior-investigator.md](agents/behavior-investigator.md) | Inputs: `target`, `repo_root`, `planning_root?`, `context?` | Model: `gpt-high`

- `test-discovery` - Mechanically map changed product files to existing test files that mention them.
  File: [~/ai/agents/test-discovery.md](agents/test-discovery.md) | Inputs: `repo_root`, `scratch_dir`, `base_ref?`, `planning_root?`, `spec_dir?`, `product_globs?`, `test_roots?` | Model: `gpt-high`

- `test-audit-gate` - Produce a blocking `PASS | PARTIAL | FAIL` from existing spec, test, and locally-generated coverage evidence, with complete runner logs separated from canonical reports and an independently audited, production-validated three-child nested process proof.
  File: [~/ai/agents/test-audit-gate.md](agents/test-audit-gate.md) | Inputs: `mode`, `repo_root`, `scratch_dir`, `base_branch`, `base_ref?` (derived only from the caller-owned base branch), `base_sha?`, `head_branch?`, `head_ref?`, `head_sha?`, `planning_root?`, `spec_dir?`, `agents_dir?`, `repo?`, `local_coverage_command?`, `pr_number?` | Model: `gpt-high`

- `red-phase-gate` - Run newly authored tests against pre-implementation `HEAD` to confirm whether they are genuinely red.
  File: [~/ai/agents/red-phase-gate.md](agents/red-phase-gate.md) | Inputs: `project_dir`, `scratch_dir`, `base_ref?`, `new_test_nodeids?` | Model: `gpt-high`

- `green-phase-gate` - Re-run the red-phase node IDs after implementation to classify what turned green and what stayed blocked or red.
  File: [~/ai/agents/green-phase-gate.md](agents/green-phase-gate.md) | Inputs: `project_dir`, `scratch_dir`, `base_ref?`, `red_phase_report` | Model: `gpt-high`

- `test-writer` - Write tests only from verified intended behavior, never by snapshotting the current implementation.
  File: [~/ai/agents/test-writer.md](agents/test-writer.md) | Inputs: `behavior_spec`, `worktree_path`, `test_type`, `target` | Model: `gpt-high`

- `trace-recorder` - Capture Playwright traces and frame-by-frame workflow evidence when behavior is ambiguous and needs human review.
  File: [~/ai/agents/trace-recorder.md](agents/trace-recorder.md) | Inputs: `workflow`, `worktree_path`, `app_url`, `ambiguity`, `questions` | Model: `gpt-high`

- `adversarial-qa-driver` - Run the stage-only adversarial QA workflow for normal-regression and adversarial probing, then file complete evidence-backed bugs without absorbing prototype QA or RCA.
  Workflow: [~/ai/workflows/adversarial-qa-stage.md](workflows/adversarial-qa-stage.md) | File: [~/ai/agents/adversarial-qa-driver.md](agents/adversarial-qa-driver.md) | Inputs: `stage_url`, `health_check_url`, `use_case_dossier_path`, `run_id`, `planning_dir`, `ticket_system`, `${ticket_operator}` routing inputs, browser identity, credentials/roles, `feature_flags`, `local_log_paths?` | Model: `gpt-high`

- `push-pull-auditor` - Audit changed code-level and deployment-level pull sites for A1 push-vs-pull system coupling and report `uncontrolled-source coupler` findings with decoupling direction.
  File: [~/ai/agents/push-pull-auditor.md](agents/push-pull-auditor.md) | Inputs: `repo_root`, `diff_path`, `output_path`, `base_ref?`, `head_ref?`, `changed_files_path?`, `proposal_path?`, `problem_map_path?`, `risk_profile_path?`, `code_quality_ref?` | Model: `gpt-high`

- `verification-plan-reviewer` - Review proposal and RCA fix-decision verification plans for completeness, executability, expected observations, and direct claim-experiment fit without claiming that the experiment ran.
  File: [~/ai/agents/verification-plan-reviewer.md](agents/verification-plan-reviewer.md) | Inputs: `mode`, `proposal_path`, `report_path`, `worktree_path`, `contract_path?` | Model: `gpt-xhigh`

### Incident / RCA

- `rca-orchestrator` - Orchestrate the full RCA workflow from trigger classification through reproduction, split root-cause/fix/application dispatches, verify-or-return, and downstream incident lifecycle handoff.
  File: [~/ai/agents/rca-orchestrator.md](agents/rca-orchestrator.md) | Inputs: `incident_id?`, `failure_id`, `trigger_type`, `trigger_evidence_path`, `repo_root`, `worktree_path`, `scratch_dir`, `planning_dir`, `trigger_command?`, `ticket_system?` | Model: `gpt-xhigh`

- `incident-investigator` - Investigate an incident from a brief, evidence directory, and read-only repository, then write evidence-backed findings without mutating code or external systems.
  File: [~/ai/agents/incident-investigator.md](agents/incident-investigator.md) | Inputs: `incident_brief_path`, `evidence_dir`, `repo_root`, `findings_path?` | Model: `gpt-high`

- `post-mortem-author` — Synthesizes a post-mortem from incident-investigator findings and the incident brief, then writes one Markdown document
  File: [~/ai/agents/post-mortem-author.md](agents/post-mortem-author.md)
  Inputs: findings_path, incident_brief_path, output_path
  Model: gpt-high

- `prototype-rca-orchestrator` - Run the light two-agent prototype RCA loop for one failed behavior test or QA walkthrough observation, then hand back after targeted verification.
  File: [~/ai/agents/prototype-rca-orchestrator.md](agents/prototype-rca-orchestrator.md) | Inputs: `failure_id`, `trigger_type`, `trigger_evidence_path`, `repo_root`, `worktree_path`, `planning_dir`, `scratch_dir`, `handback_callback`, `trigger_command?`, `qa_use_case_id?` | Model: `gpt-xhigh`

### Regression Investigation

- `regression-investigator` — Orchestrate one regression-investigation run from incident artifact through commit-history analysis, A1 comparison, pattern audit, synthesis, and ticket handoff.
  File: [~/ai/agents/regression-investigator.md](agents/regression-investigator.md)
  Inputs: `incident_artifact_path`, `incident_id`, `repo_root`, `worktree_path`, `planning_dir`, `scratch_dir`, `ticket_system`, `surface_scope_path`, `investigation_window`, `linear_team_key`, `linear_project_id`, `jira_url`, `jira_project`, `jira_account_email`
  Model: `gpt-xhigh`

- `pattern-auditor` — Read-only per-file pattern auditor for regression-enabling code shapes.
  File: [~/ai/agents/pattern-auditor.md](agents/pattern-auditor.md)
  Inputs: `surface_path`, `surface_context`, `repo_root`, `planning_dir`, `incident_id`, `incident_artifact_path`, `output_path`
  Model: `gpt-high`

- `commit-history-analyzer` — Read-only commit-window analyzer for pressure, test accompaniment, review path, shortcut merges, and regression-introduction context.
  File: [~/ai/agents/commit-history-analyzer.md](agents/commit-history-analyzer.md)
  Inputs: `investigation_window`, `repo_root`, `planning_dir`, `surface_scope_path`, `regression_introduction_sha`, `fix_sha`, `output_path`
  Model: `gpt-high`

### PR review / justification

- `pr-writer` - Author the title and body of a draft pull request for an external reviewer who has no project context — enforces the audience and content rules (no internal jargon, no commit-history sections, no unverified closed-PR or planning-artifact references).
  File: [~/ai/agents/pr-writer.md](agents/pr-writer.md) | Inputs: `branch`, `base`, `base_ref`, `base_sha`, `head_ref`, `head_sha`, `repo_root`, `output_path`, `context_files?`, `stack_parent_pr?`, `merged_refs?`, `linear_issue_keys?` | Model: `gpt-high`

- `prototype-pr-writer` - Author an evidence-focused draft PR body for a shippable-prototype PR, centered on shipped use-cases, behavior-test evidence, QA screenshots, observed-vs-expected notes, and deliverable bring-up material; this PR writer does not replace `pr-writer` for production implementation PRs.
  File: [~/ai/agents/prototype-pr-writer.md](agents/prototype-pr-writer.md) | Inputs: `truth_branch_ref`, `proposal_path`, `behavior_tests_paths`, `test_results`, `qa_walkthrough_report_path`, `qa_screenshots_dir`, `deliverable_paths` | Model: `gpt-medium`

- `prototype-test-pr-writer` - Author fail-expected/pending prototype-test PR body files for production behavior-test contract review (NOT production implementation, NOT shippable-prototype experiment-evidence bundles).
  File: [~/ai/agents/prototype-test-pr-writer.md](agents/prototype-test-pr-writer.md) | Inputs: `prototype_test_branch_ref`, `base`, `repo_root`, `dossier_answer_path`, `prototype_evidence_review_path`, `spawned_tickets_path`, `test_manifest_path`, `pending_marker_convention_path`, `implementation_ticket_urls`, `output_path` | Model: `gpt-medium`

- `coderabbit-operator` - Run exactly one generated CodeRabbit review, continue each finding conversation independently until its thread resolves, require CodeRabbit approval on the exact final head, and reuse persisted completion on rerun.
  File: [~/ai/agents/coderabbit-operator.md](agents/coderabbit-operator.md) | Inputs: `repo`, `pr_num`, `worktree_path`, `trigger_mode?`, `initial_trigger?`, `fixer_agent?` | Model: `gpt-medium`

- `commit-hygiene-operator` - Audit or rewrite a branch's commits into small, testable, reviewable history without changing the cumulative diff.
  File: [~/ai/agents/commit-hygiene-operator.md](agents/commit-hygiene-operator.md) | Inputs: `branch`, `base`, `mode`, `target_commit_plan?`, `repo_root`, `worktrees_root?`, `worktree_path?`, `python_bin?` | Model: `gpt-high`

- `pr-review-operator` - Run the full rerunnable PR review pipeline in an exact PR/base/head/invocation-qualified immutable checkout and artifact root, with separate runner logs/canonical outputs, production-validated nested test-audit proof, independently audited initial/conditional fanouts, unchanged-state posting recheck, and explicit repository/PR mutation targets.
  File: [~/ai/agents/pr-review-operator.md](agents/pr-review-operator.md) | Inputs: `pr_number`, `repo_root`, `local_coverage_command`, `base_branch`, `base_ref`, `base_sha`, `head_branch`, `head_ref`, `head_sha`, `repo?`, `review_dir?`, `planning_root?`, `agents_dir?`, `audit_history_path?` | Model: `gpt-high`

- `pr-justification-gauntlet` - Orchestrate the multi-round justification loop across interrogator, researcher, value assessment, and adjudication.
  File: [~/ai/agents/pr-justification-gauntlet.md](agents/pr-justification-gauntlet.md) | Inputs: `pr_number`, `work_dir`, `repo_root`, `repo?`, `planning_root?`, `agents_dir?`, `pr_meta_path?`, `diff_path?`, `audit_history_path?` | Model: `gpt-high`

- `pr-justification-interrogator` - Read only the PR and open or press threads for any change that is not obviously justified in this PR.
  File: [~/ai/agents/pr-justification-interrogator.md](agents/pr-justification-interrogator.md) | Inputs: `pr metadata`, `diff`, `threads.json?`, `audit_history_path?` | Model: `gpt-high`

- `pr-justification-researcher` - Gather evidence from planning docs, Jira, related PRs, and git history for each open justification thread.
  File: [~/ai/agents/pr-justification-researcher.md](agents/pr-justification-researcher.md) | Inputs: `repo_root`, `planning_root?`, `jira_url`, `jira_project`, `jira_account_email`, `threads.json`, `prior_history?`, `audit_history_path?` | Model: `gpt-high`

- `pr-justification-value-assessor` - Score the benefit and cost of keeping each challenged change in the current PR.
  File: [~/ai/agents/pr-justification-value-assessor.md](agents/pr-justification-value-assessor.md) | Inputs: `threads.json`, `prior_history?`, `audit_history_path?` | Model: `gpt-xhigh`

- `pr-justification-adjudicator` - Decide when a justification thread is settled and cull it as `drop`, `backlog`, `keep`, or continue to another round.
  File: [~/ai/agents/pr-justification-adjudicator.md](agents/pr-justification-adjudicator.md) | Inputs: `threads.json`, `round history`, `audit_history_path?` | Model: `gpt-high`

- `decision-encoder` - Maintain canonical audit history after revise/review rounds by encoding findings, role determinations, watch signals, and summarization tail.
  File: [~/ai/agents/decision-encoder.md](agents/decision-encoder.md) | Inputs: `audit_history_path`, `round_number`, `artifact_under_review`, `round_artifacts`, `role_outputs`, `mode?` | Model: `gpt-high`

- `fastapi-review-operator` - Run the secondary FastAPI-specific PR review once the primary review pipeline has already passed its risk gate.
  File: [~/ai/agents/fastapi-review-operator.md](agents/fastapi-review-operator.md) | Inputs: `pr_number`, `repo_root`, `repo?`, `agents_dir?`, `reference_doc?` | Model: `gpt-high`

- `fastapi-best-practices` - Use as the FastAPI reviewer reference for architecture, contracts, state, and testing judgments in the secondary review.
  File: [~/ai/agents/fastapi-best-practices.md](agents/fastapi-best-practices.md) | Inputs: `reference doc only` | Model: `n/a`

### Legacy implementation pipeline orchestration

These entries are retained as non-routable catalog documentation. Do not dispatch them for a protected change unless the user explicitly requests the legacy implementation pipeline; even then, they cannot satisfy or bypass the Mandatory General Landable-Change Lifecycle, activate the Governed Emergency Disposition, or merge their output before that lifecycle passes outside that disposition.

- `apply-gate-set` - Own the active Phase 4/6/8 and RCA post-apply gate set, exact implementation identity transport, expected-process/trace audit, currentness joins, and stable hash-bound result envelope.
  File: [~/ai/agents/apply-gate-set.md](agents/apply-gate-set.md) | Inputs: `caller_mode`, repository/artifact roots, runtime cycle identity, exact base/head branch/ref/SHA for implementation modes, scope/runtime/contract/report hashes, mode-specific artifacts, output paths, and `local_coverage_command?` for Phase 8 | Model: `gpt-xhigh`

- `implementation-pipeline-orchestrator` - Orchestrate one Work Unit through Phase 9, acquiring one draft PR in Phase 7 and returning either a verified draft-PR or verified merged outcome. It refines inherited estimates in Phase 3 and resolves the authoritative ticket-operator contract to either verified estimate write-back or auditable `no_write_policy_disabled` evidence before Phase 4; missing, malformed, overridden, or failed-mutation policy never becomes no-write success. Phase 9 freezes caller-owned ticket/route/attempt/PR/reviewed expected context before dispatch, requires exact dispatched/result/provider base branch and fetched-ref names even when OIDs coincide, requires the producer-owned Jira/Linear comment-readback result to validate against it, and returns both path/hash pairs plus current Phase 4/6/8 process-proof path/hashes. There is no Phase 10; auto-merge preserves exact Phase 8 reviewed OPEN draft identity, restores draft state before any pre-merge replay, and permits no undo/replay after merge invocation.
  File: [~/ai/agents/implementation-pipeline-orchestrator.md](agents/implementation-pipeline-orchestrator.md) | Inputs: ticket source/backend inputs, optional existing-issue-only `wu_brief_context_path?`, `repo_root`, `worktree_path`, `scratch_dir`, `planning_dir`, required caller-owned `base_branch`, `branch_name?`, `local_coverage_command?`, `pipeline_entry_mode?`, complete review-first/plug-existing-review target, bundle, currentness, staleness, runtime-evidence, and proposer-fix inputs, `tickets_first_variant?` (migration-only no-op), `skip_problem_map_gate?`, `auto_merge_after_phase_9?` | Model: `gpt-xhigh`

- `wu-session-resumer` - Wake one merged Work Unit session only after independently proving exact merged PR/base/head/merge identity and refreshed-base containment, derive/validate supported manual-merge baseline evidence, run post-merge checks, cross-link the ticket, and close or prepare handoff.
  File: [~/ai/agents/wu-session-resumer.md](agents/wu-session-resumer.md) | Inputs: `pr_url`, `merge_sha`, `head_sha`, `base_branch`, `pre_merge_base_sha?`, `branch_name`, `ticket_id`, `session_manifest_path`, `test_command?`, `coverage_command?` | Model: `gpt-high`

### Feature orchestration

`feature-orchestrator` is retained as a non-routable legacy catalog reference. Do not dispatch it for general multi-ticket, user-facing, or behavioral work unless the user explicitly requests it by name, and do not treat its review or merge evidence as satisfying the mandatory consumer-owned lifecycle.

- `feature-orchestrator` - Coordinate one feature branch across backend-bound routed tickets using serialized attempts, route-discriminated direct operators/results, one exact-feature-branch common two-stage production process validator, closed hash-bound attempt-proof envelopes joined to the manifest/index/route result, caller-context-bound direct ticket evidence, verified refactoring merge identity, exact draft promotion, restoration-proved replay, route-specific merge ownership, and a verified final PR-open handoff.
  File: [~/ai/agents/feature-orchestrator.md](agents/feature-orchestrator.md) | Inputs: `feature_id`, `feature_scope_path`, `repo_root`, explicit `trunk_branch`, explicit `feature_branch`, `feature_worktree_path`, `child_worktrees_root`, `planning_dir`, `scratch_dir`, non-blank `local_coverage_command`, `scoped_ticket_list`, exactly one of `ticket_route_map?` or `successor_manifest_path?`, `ticket_system` plus matching backend configuration, `manager_flavor`, `acceptance_evidence_paths`, `post_merge_owner`, optional prototype/QA/evidence/audit-history context; runtime UUID is runner-derived | Model: `gpt-xhigh`

### Refactoring strategies

`refactoring-orchestrator` is retained as a non-routable legacy catalog reference. Internal reshaping does not select it by default; dispatch it only when the user explicitly requests it by name, and do not treat its review or merge evidence as satisfying the mandatory consumer-owned lifecycle. Other specialized refactoring catalog entries remain documented for their explicit triggers.

- `refactoring-orchestrator` - Coordinate one contract-bounded refactoring WU, validate and pass the exact normalized branch/ticket/context/roots plus reviewed integration base to exactly one implementation child with auto-merge disabled, require integration/dispatched/observed/nested implementation base branch and fetched-ref names to match exactly even when OIDs coincide, require caller-context-bound ticket evidence and current implementation/refactoring-owned process-proof hashes, restore exact draft state before any pre-merge replay, solely own its one non-replayable guarded ticket-PR merge attempt, and return current audited `VERIFIED_MERGED` evidence.
  File: [~/ai/agents/refactoring-orchestrator.md](agents/refactoring-orchestrator.md) | Inputs: exactly one of `jira_issue_key?` / `linear_issue_key?` / `wu_brief_path?`, optional existing-issue-only `wu_brief_context_path?`, required `ticket_system` plus matching backend configuration, `target_list`, `repo_root`, unique short `branch_name`, `worktree_path`, `planning_dir`, `scratch_dir`, required boolean `feature_routed`, feature-route-required `local_coverage_command?`, exact short `trunk_branch`, short GitHub `integration_branch_ref`, canonical `protected_branches` containing both, `slice_bounds`, optional shim parameters/evidence, `shim_registry_path?` (default `~/ai/conventions/active-shims.md`), `audit_history_path?` (default `${planning_dir}/refactoring-audit-history.md`), `manager_flavor?`; runtime UUID is runner-derived | Model: `gpt-xhigh`

- `refactoring-commit-history-orchestrator` - Strategic incremental refactoring by commit-history since last refactor milestone; `scope` freezes exact identities and fully executable package descriptors then stops, while `execute` validates descriptor/ref/path/dependency identity plus caller-owned existing-issue assignments before separate one-PR refactoring WUs.
  File: [~/ai/agents/refactoring-commit-history-orchestrator.md](agents/refactoring-commit-history-orchestrator.md) | Workflow: [~/ai/workflows/refactoring-commit-history.md](workflows/refactoring-commit-history.md) | Convention: [~/ai/conventions/refactoring-commit-history-scoping.md](conventions/refactoring-commit-history-scoping.md) | Inputs: required `mode=scope|execute`, `ticket_system`, repository/artifact roots, exact `trunk_branch`, canonical `protected_branches`, and `manager_flavor`; scope-only target/history/integration/degradation/package inputs; execute-only immutable `package_source_request`, caller-owned `package_ticket_source_map`, `current_identity_path`, and matching backend child configuration; performs no ticket automation | Model: `gpt-xhigh`

### Release management

- `release-orchestrator` - Orchestrate a staged release lifecycle across cut, freeze, hotfix, promote, tag, and reconcile phases.
  File: [~/ai/agents/release-orchestrator.md](agents/release-orchestrator.md) | Inputs: `repo_root`, `worktree_path`, `scratch_dir`, `planning_dir`, `release_id`, `develop_branch_name`, `main_branch_name`, `release_branch_name`, `tag_pattern`, `qa_lane_id`, `manifest_path?`, `release_manifest_path?`, `freeze_window`, `qa_evidence_path`, `required_checks_policy`, `settings_state_or_runbook_ticket`, `hotfix_policy`, `promotion_approval`, `reconcile_obligations`, `ticket_system`, `jira_url?`, `jira_project?`, `jira_account_email?`, `jira_issue_key?`, `jira_release_key?`, `linear_team_key?`, `linear_project_id?`, `linear_issue_key?`, `linear_release_key?`, `release_ticket_key?` | Model: `gpt-xhigh`

- `release-cut-operator` - Release branch cut mechanics. Wired in `~/ai/agents/release-orchestrator.md` § Phase 1 - cut.
  File: [~/ai/agents/release-cut-operator.md](agents/release-cut-operator.md) | Inputs: `repo_root`, `worktree_path`, `scratch_dir`, `release_id`, `develop_branch_name`, `release_branch_name`, `manifest_path?`, `release_manifest_path?`, `required_checks_policy`, `settings_state_or_runbook_ticket` | Model: `gpt-high`

- `release-hotfix-operator` - Release hotfix and cherry-pick mechanics. Wired in `~/ai/agents/release-orchestrator.md` § Phase 3 - hotfix-cherry-pick.
  File: [~/ai/agents/release-hotfix-operator.md](agents/release-hotfix-operator.md) | Inputs: `repo_root`, `worktree_path`, `scratch_dir`, `release_id`, `release_branch_name`, `hotfix_branch_name?`, `manifest_path?`, `release_manifest_path?`, `hotfix_policy`, `qa_evidence_path`, `promotion_approval` | Model: `gpt-high`

- `release-promote-operator` - Promotion and tag mechanics. Wired in `~/ai/agents/release-orchestrator.md` § Phase 4 - promote and § Phase 5 - tag.
  File: [~/ai/agents/release-promote-operator.md](agents/release-promote-operator.md) | Inputs: `repo_root`, `worktree_path`, `scratch_dir`, `release_id`, `release_branch_name`, `main_branch_name`, `tag_pattern`, `manifest_path?`, `release_manifest_path?`, `qa_evidence_path`, `promotion_approval` | Model: `gpt-high`

- `release-reconcile-operator` - Post-release reconciliation mechanics. Wired in `~/ai/agents/release-orchestrator.md` § Phase 6 - reconcile.
  File: [~/ai/agents/release-reconcile-operator.md](agents/release-reconcile-operator.md) | Inputs: `repo_root`, `worktree_path`, `scratch_dir`, `release_id`, `develop_branch_name`, `main_branch_name`, `release_branch_name`, `manifest_path?`, `release_manifest_path?`, `reconcile_obligations` | Model: `gpt-high`

### Strategic planning / proposal alignment cycle

The alignment cycle drives a project's `problem.md` ↔ `philosophy.md` ↔ `proposal.md` review loop. The orchestrator dispatches Stage 1 / 1b-classify / 1b-integrate / 2 / 2b-classify / 2b-integrate; the proposer is user-driven (the orchestrator does NOT run the proposer).

- `problem-bootstrap` - Create an initial product `problem.md` and standalone axis reference table from a fresh brief when the alignment cycle starts from an empty product-strategy state.
  File: [~/ai/agents/problem-bootstrap.md](agents/problem-bootstrap.md) | Inputs: `brief_path`, `project_root`, `problem_path`, `axis_table_path`, `scratch_dir` | Model: `gpt-high`

- `philosophy-bootstrap` - Create an initial product `philosophy.md` from a fresh brief plus an existing readable `problem.md` when the alignment cycle lacks philosophy seed content.
  File: [~/ai/agents/philosophy-bootstrap.md](agents/philosophy-bootstrap.md) | Inputs: `brief_path`, `problem_path`, `philosophy_path`, `scratch_dir` | Model: `gpt-high`

- `alignment-cycle-orchestrator` - Run the proposal alignment review cycle: Stage 1 problem-alignment, Stage 1b-classify + 1b-integrate (problem expansion), Stage 2 philosophy-alignment, Stage 2b-classify + 2b-integrate (philosophy expansion). Halts at 2b-classify if `philosophy-decisions.md` is written (user-input gate). Produces a run report.
  File: [~/ai/agents/alignment-cycle-orchestrator.md](agents/alignment-cycle-orchestrator.md) | Inputs: project paths to `problem.md`, `philosophy.md`, `proposal.md`, axis tables, scratch dir | Model: `gpt-xhigh`

- `proposer` - Write or update `proposal.md` as a system-design document grounded in `problem.md` + `philosophy.md`. Brownfield revisions consume `problem-review.md` + `philosophy-review.md`. Stack/build-order content is roadmap-/DECISIONS-layer concern, not proposal content.
  File: [~/ai/agents/proposer.md](agents/proposer.md) | Inputs: project paths to `problem.md`, `philosophy.md`, `proposal.md`, optional review files | Model: `gpt-high`

- `problem-alignment` - Stage 1 alignment review: read `problem.md` + `proposal.md` + project's axis reference table; produce `problem-review.md` (always) and `problem-surfaces.md` (when new surfaces are discovered).
  File: [~/ai/agents/problem-alignment.md](agents/problem-alignment.md) | Inputs: `problem.md`, `proposal.md`, project axis table | Model: `gpt-xhigh`

- `problem-expansion-classify` - Stage 1b-classify (judge): read `problem-surfaces.md` and judge each surface as `discard / already-covered`, `discard / proposal-specific`, `discard / out-of-scope`, `new-axis`, or `axis-expansion`. Writes `problem-classification.md`. Does NOT modify `problem.md`.
  File: [~/ai/agents/problem-expansion-classify.md](agents/problem-expansion-classify.md) | Inputs: `problem-surfaces.md`, `problem.md`, project axis table | Model: `gpt-xhigh`

- `problem-expansion-integrate` - Stage 1b-integrate (synthesis): read `problem-classification.md` and synthesize integrated text into `problem.md` + the axis reference table for `new-axis` and `axis-expansion` verdicts. Skips `discard` verdicts. Does NOT re-judge.
  File: [~/ai/agents/problem-expansion-integrate.md](agents/problem-expansion-integrate.md) | Inputs: `problem-classification.md`, `problem-surfaces.md`, `problem.md`, project axis table | Model: `gpt-high`

- `philosophy-alignment` - Stage 2 alignment review: read `philosophy.md` + `proposal.md` + `problem-review.md`; produce `philosophy-review.md` (always) and `philosophy-surfaces.md` (when new philosophical concerns are discovered).
  File: [~/ai/agents/philosophy-alignment.md](agents/philosophy-alignment.md) | Inputs: `philosophy.md`, `proposal.md`, `problem-review.md` | Model: `gpt-xhigh`

- `philosophy-expansion-classify` - Stage 2b-classify (judge): classify each concern as A absorbable, B compatible-addition, C tension, D new-axis, or E contradiction. Writes `philosophy-classification.md` (always) and `philosophy-decisions.md` (only when any C/D/E surface user-input concerns). Does NOT modify `philosophy.md`.
  File: [~/ai/agents/philosophy-expansion-classify.md](agents/philosophy-expansion-classify.md) | Inputs: `philosophy-surfaces.md`, `philosophy.md`, `philosophy-alignment.md` | Model: `gpt-xhigh`

- `philosophy-expansion-integrate` - Stage 2b-integrate (synthesis): apply absorbable clarifications (A) and provisional new principles (B) to `philosophy.md`. Skips C/D/E (those live in `philosophy-decisions.md` and are user-owned). Does NOT modify `philosophy-decisions.md`.
  File: [~/ai/agents/philosophy-expansion-integrate.md](agents/philosophy-expansion-integrate.md) | Inputs: `philosophy-classification.md`, `philosophy-surfaces.md`, `philosophy.md` | Model: `gpt-high`

### Roadmap cascade

The roadmap workflow cascades from market research (Layer 0) through ticket regeneration (Layer 4). Each layer has 3x risk gates (per-risk model assignment per `workflows/roadmap.md`, all-LOW required) before advancing.

- `roadmap-orchestrator` - Run the roadmap workflow cascade: Layer 1 executive-roadmap (3x risk), Layer 2 engineering-roadmap (3x risk), Layer 3 per-phase ai-roadmaps (3x risk per phase), Layer 4 ticket regeneration. Dispatches sub-proposers and risk operators via the agents CLI; surfaces NEEDS_INPUT new-value-questions to the root.
  File: [~/ai/agents/roadmap-orchestrator.md](agents/roadmap-orchestrator.md) | Inputs: project paths to `problem.md`, `philosophy.md`, `proposal.md`, `DECISIONS.md`, scratch dir | Model: `gpt-xhigh`

- `executive-roadmap-proposer` - Layer 1: write/update `executive-roadmap.md` from problem + philosophy + proposal + market research. Strategic ordering of value slices and milestones.
  File: [~/ai/agents/executive-roadmap-proposer.md](agents/executive-roadmap-proposer.md) | Inputs: `problem.md`, `philosophy.md`, `proposal.md`, `market-research.md`, optional risk reports | Model: `gpt-high`

- `engineering-roadmap-proposer` - Layer 2: write/update `engineering-roadmap.md` from approved executive-roadmap + DECISIONS.md + engineering-research. Names foundation-phase substrate and per-VS engineering effort.
  File: [~/ai/agents/engineering-roadmap-proposer.md](agents/engineering-roadmap-proposer.md) | Inputs: `executive-roadmap.md`, `DECISIONS.md`, `engineering-research.md`, optional risk reports | Model: `gpt-high`

- `ai-roadmap-proposer` - Layer 3: write/update `ai-roadmap-phase-N.md` from approved engineering-roadmap + per-phase scope. Decomposes a phase into AI-implementable Work Units with named contracts/schemas/parallelization.
  File: [~/ai/agents/ai-roadmap-proposer.md](agents/ai-roadmap-proposer.md) | Inputs: `engineering-roadmap.md`, phase scope, optional risk reports | Model: `gpt-high`

- `ticket-generation-agent` - Layer 4: generate phase ticket artifacts (`tickets/INDEX.md`, `tickets/INIT-NNN.md`, `tickets/SLICE-NNN.md`) from the approved `ai-roadmap-phase-N.md`, preserving named contracts/schemas/acceptance criteria/dependencies verbatim and including SLICE story-point estimate/source/rationale fields while INIT remains unsized.
  File: [~/ai/agents/ticket-generation-agent.md](agents/ticket-generation-agent.md) | Inputs: `ai-roadmap-phase-N.md`, phase id | Model: `gpt-high`

- `engineering-research-agent` - Layer 2 Stage 2a: survey the existing codebase + adjacent reference projects to produce `engineering-research.md`. Read-only against project files.
  File: [~/ai/agents/engineering-research-agent.md](agents/engineering-research-agent.md) | Inputs: `repo_root`, optional reference repos | Model: `gpt-high`

- `market-research-agent` - Layer 0: synthesize market research streams into `market-research.md`. Reads research streams from `research/`.
  File: [~/ai/agents/market-research-agent.md](agents/market-research-agent.md) | Inputs: `research/` directory, optional prior synthesis | Model: `gpt-high`

- `roadmap-risk-types` - Reference catalog of risk types per roadmap layer. Not a callable operator; the roadmap-orchestrator reads this to construct risk-assessment prompts.
  File: [~/ai/agents/roadmap-risk-types.md](agents/roadmap-risk-types.md) | Inputs: `reference doc only` | Model: `n/a`

### Worktree / branch execution

- `worktree-operator` - Create, list, sync, or remove git worktrees for feature branches.
  File: [~/ai/agents/worktree-operator.md](agents/worktree-operator.md) | Inputs: `task`, `name?`, `branch_name?`, `base_branch?`, `repo_root`, `worktrees_root?`, `branch_policy?` | Model: `gpt-high`

- `jj-operator` - Manage stacked-branch dependencies, rebases, squashes, integration branches, and cleanup with `jj`.
  File: [~/ai/agents/jj-operator.md](agents/jj-operator.md) | Inputs: `task`, `branch`, `target?`, `parents?`, `repo_root`, `worktrees_root?` | Model: `gpt-high`

- `pipeline-artifacts-operator` - Standardize scratch artifact naming and `.gitignore` handling inside a worktree so pipeline outputs do not collide.
  File: [~/ai/agents/pipeline-artifacts-operator.md](agents/pipeline-artifacts-operator.md) | Inputs: `worktree_path`, `mode`, `repo_root`, `worktrees_root?` | Model: `gpt-high`

### External integration

- `jira-operator` - Read, comment on, transition, search, create, or update-estimate Jira issues through the Atlassian REST API; `operation=comment-readback` emits the shared producer-owned ticket-operation result.
  File: [~/ai/agents/jira-operator.md](agents/jira-operator.md) | See `agents/jira-operator.md` `## Contract` for inputs/defaults/errors/delegation. | Model: `gpt-medium`

### Writing / document authoring

Imported verbatim from their source projects, then distributed into the existing `~/ai/` directories. Filenames preserved exactly (including spaces). The agent-runner CLI is not wired to these yet; they are reference assets that other operators or human authors can read.

Writing pipeline (from `~/projects/server-manager/product-strategy/`):

- Orchestrator: [`workflows/writing pipeline orchestrator.md`](workflows/writing%20pipeline%20orchestrator.md) — Phase A-J pipeline (content revision, skeleton + non-negotiable scan, mechanical ban fixes per category, story beats, flow and cohesion, adversarial robustness, editorial, restart check, quality gate, PDF render).
- Sub-agents: [`agents/writing content agent.md`](agents/writing%20content%20agent.md), [`agents/writing editorial agent.md`](agents/writing%20editorial%20agent.md), [`agents/writing quality gate agent.md`](agents/writing%20quality%20gate%20agent.md), [`agents/writing rubric agent.md`](agents/writing%20rubric%20agent.md), [`agents/writing rubric reviewer agent.md`](agents/writing%20rubric%20reviewer%20agent.md), [`agents/pitch deck agent.md`](agents/pitch%20deck%20agent.md).
- Craft reference: [`conventions/WRITING_SKILL_MASTER.md`](conventions/WRITING_SKILL_MASTER.md).
- Communication research: [`research/exec-roadmap-communication.md`](research/exec-roadmap-communication.md), [`research/pitch-deck-communication.md`](research/pitch-deck-communication.md).
- Renderer: [`tools/render-pitch-deck.py`](tools/render-pitch-deck.py).

Book authoring (from `~/projects/agent-implementation-skill/execution-philosophy/`):

- Master: [`workflows/book-authoring/AGENTS.md`](workflows/book-authoring/AGENTS.md) — 800-line orchestration doc with 4 core tenets, content authoring workflow, communication values V1-V7, quality workflows QW1-QW13, four visual creation tiers, and the model assignment matrix. Lives in its own subdir to avoid colliding with the master `~/ai/AGENTS.md`.
- Conventions: [`conventions/art-direction.md`](conventions/art-direction.md), [`conventions/structural-editing-guide.md`](conventions/structural-editing-guide.md).
- Tools: [`tools/md_to_pdf.py`](tools/md_to_pdf.py), [`tools/svg_to_png.py`](tools/svg_to_png.py), [`tools/review_svg.sh`](tools/review_svg.sh).
- Research reference: [`research/figure-best-practices.md`](research/figure-best-practices.md).

## Ecosystem Map

The `~/ai/` ecosystem composes operators, clients, tools, workflows, and conventions. The discoverability map:

- [`~/ai/VALUES.md`](VALUES.md) — ecosystem composition principles and lean-client posture.
- [`~/ai/clients/`](clients/) — first-party client libraries (currently the Linear GraphQL client).
- [`~/ai/tools/README.md`](tools/README.md) — ecosystem-wide tools (scheduler, PR-batch poller).
- [`~/ai/DECISIONS.md`](DECISIONS.md) — `~/ai/`-layer decisions, exceptions, and bootstrap context.
- [`~/ai/agents/linear-operator.md`](agents/linear-operator.md) — Linear ticket operator (Markdown-native).
- [`~/ai/agents/jira-operator.md`](agents/jira-operator.md) — Jira ticket operator (ADF).

Ecosystem-wide infrastructure (scheduler, PR-batch poller, ticket integration clients) lives in `~/ai/`, not in any application-layer project, per [`~/ai/VALUES.md`](VALUES.md) § Lean clients.

Source-of-truth repository: <https://github.com/nestharus/ai>.

## How to Invoke

Use the shared wrapper conventions in [`~/ai/workflows/agents-cli.md`](workflows/agents-cli.md).

Default shapes:

- Defined agent: `agents -a <agent.md> -p <worktree-path> -f <prompt-file> 2>&1 | tee <log-path>` — no `-m`; the agent file's `model:` frontmatter drives model selection.
- Ad-hoc / undefined agent: `agents -m <model> -p <worktree-path> -f <prompt-file> 2>&1 | tee <log-path>` — `-m` is required because there is no agent file to read frontmatter from.

Never combine `-m <model>` with `-a <agent.md>`: `-m` shadows the frontmatter and silently defeats any model rebalancing.

For long-running or parallel child dispatch, [`~/ai/workflows/agents-cli.md`](workflows/agents-cli.md) is also the canonical dispatch/wait rule: use one Bash-background tool invocation per child, not shell `&`, bundled wrapper scripts, shell `wait`, PID waits, or trace-polling loops.

### WAIT POLICY

Root agents never manually poll live workloads or jobs with repeated status, list, trace, or sleep calls. Use native background completion notifications when available. When only polling exists, launch exactly one bounded background waiter for the already-running job and rely on that waiter's completion notification. The waiter stops on terminal success, failure, cancellation, or timeout; it only observes the job and must not dispatch agents, wrap or launch an `agents` invocation, or create duplicate ownership. After notification, one terminal status or readback is allowed solely to verify the outcome.

The dispatch-shape prohibition below remains absolute: a waiter may observe an already-running job but may never wrap or launch an agent invocation.

### AGENT DISPATCH SHAPE

`~/ai/workflows/agents-cli.md` is the canonical positive-shape source. A child dispatch stays as one parent-visible bash invocation:

```bash
# Defined agent (no -m; frontmatter drives model):
agents -a <agent.md> -p <worktree-path> -f <prompt-file> 2>&1 | tee <log-path>

# Ad-hoc dispatch (no agent file; -m required):
agents -m <model> -p <worktree-path> -f <prompt-file> 2>&1 | tee <log-path>
```

Do not wrap `agents` calls in Python heredocs, shell scripts, or any composition that puts other commands between the parent shell and the `agents` invocation. Do not pipe live `agents` stdout through truncating filters such as `| head -N` or `| awk 'NR<=N'`; capture the full stream with `2>&1 | tee <log-path>` and parse the completed log afterward. Do not combine N independent dispatches into a single shell script; each dispatch is its own bash invocation, and ticket or setup commands run separately before or after it.

Wrong shapes:

```bash
# Wrong: -m combined with -a shadows the agent's frontmatter model.
agents -m gpt-xhigh -a ~/ai/agents/some-orchestrator.md -p /repo -f /tmp/prompt.md

# Wrong: composition between the parent shell and the agents invocation.
bash -c "python << EOF
print('ticket update or setup call here')
EOF
agents -a ~/ai/agents/some-orchestrator.md -p /repo -f /tmp/prompt.md | head -3"
```

Use [`/home/nes/projects/agent-runner/README.md`](/home/nes/projects/agent-runner/README.md) as the authoritative CLI reference for flags, named-agent resolution, config, and alternate invocation forms.

All branch work runs in an isolated git worktree. Central-checkout branch-tracking includes authorized clean, fast-forward-only deployment synchronization of its configured default branch, not feature work; dirty or divergent states stop without repair. See [`~/ai/conventions/worktree-isolation.md`](conventions/worktree-isolation.md).

## Workflow Topologies

These are discoverability links, not default dispatch authority. The first three are non-routable legacy workflows for protected changes and require an explicit user request; they cannot replace the Mandatory General Landable-Change Lifecycle.

- Legacy feature development (heterogeneous ticket routes and feature-branch integration): [`~/ai/workflows/feature-development.md`](workflows/feature-development.md)
- Legacy implementation pipeline (through Phase 9): [`~/ai/workflows/implementation-pipeline.md`](workflows/implementation-pipeline.md)
- Legacy refactoring (contract-bounded slices over an explicit integration branch): [`~/ai/workflows/refactoring.md`](workflows/refactoring.md)
- RCA workflow (full reproduction-first root-cause analysis with four-agent split, verify-or-return, and incident-to-close downstream lifecycle): [`~/ai/workflows/rca.md`](workflows/rca.md)
- Regression investigation (post-incident codebase-risk archaeology): [`~/ai/workflows/regression-investigation.md`](workflows/regression-investigation.md)
- Prototype RCA workflow (light two-agent root-cause/fix loop for one failed prototype trigger): [`~/ai/workflows/rca-prototype.md`](workflows/rca-prototype.md)
- Release management (staged cut/freeze/hotfix/promote/tag/reconcile lifecycle): [`~/ai/workflows/release-management.md`](workflows/release-management.md)
- Project bootstrap (project-specific operator wrapper open/closed path): [`~/ai/workflows/project-bootstrap.md`](workflows/project-bootstrap.md)
- Alignment cycle (problem ↔ philosophy ↔ proposal review loop with classify/integrate split): [`~/ai/workflows/alignment-cycle.md`](workflows/alignment-cycle.md)
- PR review gates (test-audit, multi-concern, justification, commit-hygiene): [`~/ai/workflows/pr-review.md`](workflows/pr-review.md)
- Audit sub-workflow (target-typed design/process/drift audit coordination): [`~/ai/workflows/audit.md`](workflows/audit.md)
- Research (single-agent, parallel-fanout, deep-reasoning escalation): [`~/ai/workflows/research.md`](workflows/research.md)
- Linter bootstrap (A1 linter coverage inventory, ecosystem research, and setup-PR proposal): [`~/ai/workflows/linter-bootstrap.md`](workflows/linter-bootstrap.md)
- Code quality (A1 composite auditor fanout and aggregate verdict): [`~/ai/workflows/code-quality.md`](workflows/code-quality.md)
- Roadmap (4-layer strategic pipeline): [`~/ai/workflows/roadmap.md`](workflows/roadmap.md)
- Tiered approval (3-tier action safety): [`~/ai/workflows/tiered-approval.md`](workflows/tiered-approval.md)
- Verified rebase (deterministic residual bundle + rollback; single rebase path): [`~/ai/workflows/verified-rebase.md`](workflows/verified-rebase.md)
- Writing pipeline (Phase A-J: orchestrator in [`workflows/writing pipeline orchestrator.md`](workflows/writing%20pipeline%20orchestrator.md))
- Book authoring (QW1-QW13 quality workflows + four visual creation tiers in [`workflows/book-authoring/AGENTS.md`](workflows/book-authoring/AGENTS.md))

## Conventions

- [`~/ai/conventions/code-quality.md`](conventions/code-quality.md) - shared code-quality rules for function classification, max nesting depth, inline mini-function extraction, duplicate responsibility handling, and push-vs-pull system coupling
- [`~/ai/conventions/design-patterns.md`](conventions/design-patterns.md) - shared design-pattern corpus consumed by workflow/agent design auditors
- [`~/ai/conventions/git.md`](conventions/git.md) - branches, GPG, draft PR routine, no-attribution
- [`~/ai/conventions/worktree-isolation.md`](conventions/worktree-isolation.md) - unconditional branch-work isolation and guarded central default-branch synchronization
- [`~/ai/conventions/no-backwards-compatibility.md`](conventions/no-backwards-compatibility.md)
- [`~/ai/conventions/no-deferred-stubs.md`](conventions/no-deferred-stubs.md)
- [`~/ai/conventions/behavioral-proof.md`](conventions/behavioral-proof.md) - expected-versus-observed experiment evidence and review authority boundaries
- [`~/ai/conventions/gate-ownership.md`](conventions/gate-ownership.md) - human vs. model gate owners
- [`~/ai/conventions/prototype-review.md`](conventions/prototype-review.md) - prototype review focus: executed experiment evidence, outcomes, and dossier verdict, not source code
- [`~/ai/conventions/prototype-pending-tests.md`](conventions/prototype-pending-tests.md) - prototype-pending marker reason and runner mapping for fail-expected prototype-test PRs
- [`~/ai/conventions/proposer-critic-pattern.md`](conventions/proposer-critic-pattern.md) - proposer/critic decomposition for risk-gated implementation
- [`~/ai/conventions/workflow-routing.md`](conventions/workflow-routing.md) - cue routing precedence
- [`~/ai/conventions/agent-questions-and-session-graph.md`](conventions/agent-questions-and-session-graph.md) - sub-agent question envelope, root surfacing, session graph, and resume/fallback convention
- [`~/ai/conventions/audit-history.md`](conventions/audit-history.md) - audit history schema, revise/review loop rules, decision-agent dispatch, and finding ID convention
- [`~/ai/conventions/workflow-execution-violations.md`](conventions/workflow-execution-violations.md) - process-review violation taxonomy and blocking/advisory defaults
- [`~/ai/conventions/review-convergence.md`](conventions/review-convergence.md) - non-converging review loops are a hard decomposition trigger; stop iterating and split the work
- [`~/ai/conventions/project-layout.md`](conventions/project-layout.md) - `~/projects/<name>/{trunk,planning,worktrees}/` umbrella layout for agent-driven projects
- [`~/ai/conventions/bootstrap-pattern.md`](conventions/bootstrap-pattern.md) - lifecycle for converting a general operator into a project-specific wrapper (open path / closed path / re-bootstrap triggers)
- [`~/ai/conventions/rebase-verification.md`](conventions/rebase-verification.md) - deterministic rebase verification, residual bundle, and rollback convention
- [`~/ai/conventions/wu-session-lifecycle.md`](conventions/wu-session-lifecycle.md) - WU spawn, run, merge, and post-merge wake lifecycle

## Model Roles

See [`~/ai/models/roles.md`](models/roles.md) for the authoritative matrix. Default is `gpt-high`; `gpt-xhigh` is for orchestration, alignment, and deep judgement gates.

## Operator File Format

See [`~/ai/agents/operator-file-format.md`](agents/operator-file-format.md) for frontmatter, optimized contract sidecars, `## Contract` fallback blocks, and body skeleton guidance.

## How Projects Extend This

A project's own `AGENTS.md` should reference this file for the generic routing layer, then add only project-local overrides and extensions.

Projects organized for agent-driven workflows use the
`~/projects/<name>/{trunk,planning,worktrees}/` umbrella layout per
[`~/ai/conventions/project-layout.md`](conventions/project-layout.md).
The git repository sits at `trunk/`; the project's own `AGENTS.md`
lives at `<project>/trunk/AGENTS.md`.

Project-specific operator wrappers live in `<project>/trunk/agents/`, reference `~/ai/agents/<name>.md` as their base procedure, and carry wrapper defaults in their optimized sidecar or `## Contract` block. See [`~/ai/conventions/bootstrap-pattern.md`](conventions/bootstrap-pattern.md) § Closed-path dispatch for the wrapper-first contract-surface read order.

### Per-Project Policy

A project's own `AGENTS.md` declares ticket-backend policy and, when explicitly requested, legacy implementation-pipeline knobs:

- `ticket_system`: `jira` or `linear` — selects the ticket backend for ticket-capable workflows. For an explicitly requested legacy implementation pipeline, see [`~/ai/agents/implementation-pipeline-orchestrator.md`](agents/implementation-pipeline-orchestrator.md) § Ticket System Pluggability.
- Linear projects declare `linear_team_key` (and optionally `linear_project_id`).
- Jira projects may declare project policy values, but category-local Jira execution defaults should live in the project wrapper contract when a wrapper exists.
- `skip_problem_map_gate` (legacy implementation pipeline only; boolean, default `false`) — see the orchestrator file's Optional Inputs. This setting never selects the pipeline or skips purpose and obligation framing above.
- `auto_merge_after_phase_9` (legacy implementation pipeline only; historical default `true`) — see the orchestrator file's Optional Inputs. This default is not merge authority for protected changes: an explicitly requested legacy pipeline that produces a protected change must set it to `false` and hand its output and evidence to the Mandatory General Landable-Change Lifecycle.

Semantics for each legacy knob live on the orchestrator's input contract; the project `AGENTS.md` only declares the chosen values. Declaring a legacy knob does not make the corresponding orchestrator routable.
