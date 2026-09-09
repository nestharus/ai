# Behavioral Proof

## Purpose

This convention is the repository authority for behavioral-proof vocabulary and
for the boundary between executing an experiment and reviewing its plan or
evidence.

## Ordinary observation boundary

Under the [shared delivery lifecycle](../AGENTS.md#mandatory-general-landable-change-lifecycle), ordinary CRW observation may use source locations, excerpts and existing result references without immutable execution records, custody packages or identity attestations. Report what those materials support and leave provenance gaps explicit; do not reject investigation merely because a record format is absent. The stricter experiment-proof requirements below apply when claiming behavioral proof, not as admission conditions on every observation. Source reasoning, proposed checks and static document checks do not establish runtime behavior or stochastic agent efficacy.

## Canonical Rule

Behavioral proof is the recorded comparison between the expected result of a
named experiment and the observed result produced when that experiment is
executed against the named target.

A plan, source review, diff review, model verdict, artifact path, evidence
bundle, or PR narrative is not behavioral proof. Those surfaces may propose,
assess, transport, or present experiment evidence, but they do not establish
that the named behavior occurred.

## Terminology

| Term | Meaning |
|---|---|
| Experiment | A deliberately executed command or action against a named target that can produce an observable result relevant to a behavior claim. Planning or reading is not execution. |
| Expected result | The observation declared before the experiment executes that would support the behavior claim at the experiment's stated scope. |
| Observed result | The status, output, artifact difference, runtime response, or application observation produced by executing the experiment. |
| Proof | The evidence record comparing the expected result with the observed result and stating the supported target and scope. |
| Review | Reading a plan, source, diff, log, artifact, or evidence record and assessing its completeness, relevance, integrity, or support. |
| Critique | Findings about defects, omissions, proxy substitution, contradictions, or unsupported claims in a plan or evidence set. |
| Hypothesis | A proposed explanation or predicted result that remains provisional until the relevant experiment is executed. |
| Verification-plan assessment | Pre-execution review of whether a behavior claim, experiment command or action, expected observation, and claim-experiment fit form a direct executable plan. |

## Experiment Classes

| Class | Minimum experiment record | Scope |
|---|---|---|
| Test execution | Exact test command or node, named target or revision, expected status or behavior, observed runner status, and relevant output. | Supports only the behavior and target exercised by the test. |
| Deterministic source or artifact inspection | Exact deterministic command or script, inspected source or artifact identity, expected match, difference, or status, observed output or diff, and exit status. | Establishes the inspected repository or artifact fact, not uncaptured runtime behavior. |
| Build and executable run | Build command and result, named built or runtime artifact, execution command or action, expected runtime observation, observed output or status, and target identity. | Build success alone cannot support a runtime claim when execution is required. |
| Recorded application interaction | User or QA action, environment and use-case identity, expected observation, actual observation, and retained report, screenshot, log, or equivalent record. | Supports only the exercised use case and environment. |

## Verification Plan

Every implementation proposal or RCA fix decision that claims behavior contains
one `## Verification plan` section with these exact fields:

| Field | Required content |
|---|---|
| `Behavior claim` | The behavior and scope to be established. |
| `Experiment command or action` | A concrete test, deterministic inspection, build and run, or application-use action that can be executed. |
| `Expected observation` | The result declared before execution that would support the claim at the stated scope. |
| `Claim-experiment fit` | Why the experiment directly exercises the claim, or an honest statement of the narrower scope when it is a proxy. |

The verification-plan reviewer may decide that this plan is complete, direct,
and suitable to execute. That assessment never means the expected observation
was produced. A proxy experiment is acceptable only when the behavior claim is
narrowed to what the proxy can establish.

## Authority Ordering

1. Executed experiment records are authoritative for whether the named behavior
   occurred at their stated target and scope.
2. This convention is authoritative for behavioral-proof vocabulary and
   evidence-role boundaries used by workflows, operators, contracts, and evals.
3. `agents/verification-plan-reviewer.md` is authoritative only for plan
   directness, completeness, executability, and proxy risk.
4. `agents/validation-integrity-auditor.md` is authoritative only for whether an
   actual diff or supplied evidence weakens, bypasses, or substitutes a required
   validation surface.
5. Validators, packagers, adapters, writers, model reviewers, and humans may
   validate, transport, present, or judge evidence. Their acceptance is not the
   experiment that produced it.
6. Workflow frontmatter is authoritative for generated workflow-index data;
   optimized sidecars are read-first mirrors and `workflows/index.json` is a
   deterministic projection.
7. Lifecycle `WRITE` eval specifications describe acceptance intent. They are
   not executable observations and cannot be cited as passing evidence.
8. Generic process proofs establish invocation topology, currentness, and
   artifact integrity only. They are not behavioral proof.

## Evidence Integrity

An experiment record retains enough identity to distinguish execution from a
prose assertion: command or action, target, expected result, observed result,
status, relevant output or retained observation, and provenance. Evidence paths
and bundles are references or transports; a path's existence alone does not
establish that its contents came from the claimed execution.

Provenance must resolve to producer-native evidence rather than a self-attested
summary. Command- or runner-based experiments cite a runner-emitted immutable
execution record with a stable invocation identity. Recorded application
interactions cite the native session or action-capture identity and retained
observation. In either class, the producer record must bind the expected result
before execution starts; an expected result added only to a later report cannot
validate the experiment.

Post-implementation passing claims cite the executed experiment record and its
observed result. Pending or fail-expected production tests remain future
behavior contracts and cannot be represented as passing production behavior.

## Declared Roles

`validator`, `mapper`

This convention validates behavioral-evidence claims and maps repository
surfaces to experiment producers, plan or evidence reviewers, and evidence
transport or presentation consumers.

## Anti-Scope

- Do not call model reading or reasoning an experiment.
- Do not substitute a favorable review outcome for an observed result.
- Do not broaden a proxy result beyond the scope it directly exercises.
- Do not weaken actual tests, deterministic inspections, build and runtime
  execution, application-use observations, or generic process-proof checks.
- Do not treat WRITE eval prose as executed evidence.
