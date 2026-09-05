# Model Roles

Central rule for which model to reach for.
Workflow docs in `~/ai/workflows/` reference this file.
Do not restate the matrix there.

## The mental model

- **`gpt-high`** is the default worker: proposer, builder, researcher, implementer, checklist auditor, and external-facing prose author.
- **`gpt-xhigh`** is the deep-reasoning route: orchestrators, alignment, risk assessment, purpose-fit judgement, and high-stakes review gates.
- **`gpt-medium`** is the fast automation route for bounded, structured operator loops.
- Legacy provider-specific model ids are deprecated for shared routing. Do not add new provider-specific assignments to operational docs; update the operator frontmatter and this matrix instead.

## Matrix

| Model | Role | Use for |
|---|---|---|
| `gpt-high` | **Default.** Proposer/builder/auditor/writer. | RCA evidence gathering, research, most synthesis, proposals, hookpoint analysis, implementation, test writing, audit risk, behavior investigation, commit hygiene, test-audit gate, multi-concern PR review, justification PR review, ticket prose, PR prose, and roadmap ticket-file generation. Use it for work that gathers evidence, enumerates cases, builds artifacts, checks presence against a checklist, or writes external-facing prose unless a workflow/operator names a narrower exception. |
| `gpt-xhigh` | Orchestrators, deep-reasoning auditors, alignment, and risk-assessment work. | All `*-orchestrator` operators that route a workflow end-to-end; verification-plan review, scope risk, shortcut risk, supported-surface risk, coverage audit, risk assessor, philosophy/problem alignment, workflow reviewer, agent-design / workflow-design / workflow-process auditors, work-manager ticket-brief auditor, rebase-drift-checker; multi-file proposals spanning subsystems; research that needs deep reasoning across many sources before delegation; strategic synthesis where reasoning depth is the bottleneck. |
| `gpt-medium` | Fast, structured per-comment automation. | CodeRabbit operator + per-comment fixer driving the PR-mode review loop. |
| `gpt-luna-high` | Linear ticket operations. | `linear-operator` uses this registered model alias for its structured ticket operations. |

## Phase-by-phase assignment (implementation pipeline)

This table is the authoritative source for pipeline phase ownership.
`~/ai/workflows/implementation-pipeline.md` cites this section.

| Phase | Model | Why |
|---|---|---|
| RCA (bug fix) | `gpt-high` | Evidence gathering |
| Problem research | `gpt-high` | Facts, citations |
| Synthesis (integrate findings) | `gpt-high` | Construction, not judgement |
| Proposal | `gpt-high` | Propose |
| Audit risk | `gpt-high` | Presence/checklist: validations, tests, migrations, contracts |
| Scope risk | `gpt-xhigh` | Intent + estimate-delta reasoning: does this stay within the stated scope, including the >2x inherited estimate-delta signal? |
| Shortcut risk | `gpt-xhigh` | Intent: do the shortcuts compromise the underlying purpose? |
| Supported-surface risk | `gpt-xhigh` | Intent: does this still serve the supported surface? |
| Verification-plan review | `gpt-xhigh` | Deep pre-execution judgment of behavior-claim to experiment fit. This model reviews the plan and does not produce behavioral proof. |
| Hookpoint research | `gpt-high` | Analysis |
| Implementation | `gpt-high` | Build |
| Test writing (separate agent) | `gpt-high` | Enumerate cases from contract |
| CodeRabbit single review (operator + per-comment fixer) | `gpt-medium` | One structured review and per-comment application pass against the PR-mode driver. |
| Test-audit gate | `gpt-high` | Checklist against stated acceptance criteria |
| Commit-hygiene check | `gpt-high` | Checklist against small-testable-commit rules |
| Multi-concern PR review | `gpt-high` | Decide whether the PR should be split. |
| Justification PR review | `gpt-high` | Decide whether every change justifies its presence. |
| PR writing | `gpt-high` | External-reader writing quality. |
| Alignment gate (skill/ai-workflow) | `gpt-xhigh` | Direction check: is this going the right way? |
| Orchestrator (any `*-orchestrator`) | `gpt-xhigh` | Routes a workflow end-to-end; depth-of-reasoning is the bottleneck. |

## Coordinator / researcher split for large tasks

Use a split when the task needs both broad reasoning and detailed research.

- For research fanout, **coordinator** is `gpt-xhigh` by default (orchestrator-class work).
- For research fanout, **coordinator** may drop to `gpt-high` for narrow fanouts whose synthesis is mechanical aggregation rather than reasoning depth.
- For research fanout, **researcher** is `gpt-high`.

Coordinator responsibilities:

- Identify the questions that need answers.
- Write research prompts.
- Launch researchers.
- Synthesize researcher findings into the deliverable.

Researcher responsibilities:

- Receive a focused question.
- Investigate.
- Return findings.

Rules:

- The coordinator does **not** do deep research itself.
- The coordinator delegates research.
- For research fanout, the coordinator **does** synthesize.
- For research fanout, synthesis stays with the coordinator because synthesis is construction.
- This does not override workflow/operator-specific `gpt-xhigh` assignments for judgement-heavy gates.

A single agent that tries to do both deep research and synthesis across parallel findings produces shallow work.
Split the roles.

## When `gpt-xhigh` is NOT the right choice

Reach for `gpt-xhigh` when the question is:

- Does this route the whole workflow correctly?
- Do the shortcuts compromise the underlying purpose?
- Does this still serve the supported surface?
- Does this require deep alignment or risk reasoning across many inputs?

Do **not** reach for `gpt-xhigh` when the question is:

- Is the evidence present?
- Does this match a checklist?
- Build an internal artifact from these inputs.
- Integrate internal findings into a deliverable.
- Summarize this quickly.

Scoped routing summary:

- Evidence / checklist / presence checks: `gpt-high`
- Internal construction / integration / synthesis: `gpt-high`
- PR prose and ticket-system prose: `gpt-high`
- Quick summaries / fast passes: `gpt-medium`
- `gpt-xhigh` construction is exceptional and must be named by frontmatter or workflow dispatch.

## Invocation

All models are invoked through the `agents` CLI.
Workflow wrapper: `~/ai/workflows/agents-cli.md`
Full CLI reference: `/home/nes/projects/agent-runner/README.md`
