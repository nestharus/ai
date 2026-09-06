# Verified-rebase substrate isolation fixtures

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s evals/verified-rebase-substrate-isolation -v
```

Requires Linux/local-filesystem `flock`, Python 3.10+, Git with
`merge-tree --write-tree --merge-base`, jj colocated Git support, Bash and jq.
The fixtures create independent temporary repositories and local bare remotes;
no network remote, incident substrate, production branch or agent is invoked.
Pipes synchronize real worker processes; no timing sleeps or mocked lock model.
Fixture Git commits disable signing only inside those disposable repositories.

## Executed surface

Tests call the actual `tools/verified_rebase.py` implementation. One test extracts
and executes the **checked-in** workflow phase 1–7 shell blocks and generates the
phase 10 rollback template with quoted literals. Thus it exercises the real
allocation/CLI wiring, ort capture, jj rebase, raw conflict-row adapter, diffs and
fenced rollback, not a second implementation of those snippets.

The named assertions cover:

- overlap, different branches sharing a substrate, canonical path aliases,
  suspended owner and successful process exit without reservation release;
- exclusive owner/attempt bundle creation (no branch-slug collision), blocked
  preflight without a `.gitignore` repair or checkout artifact;
- simultaneously rebasing independent substrates, and live independent attempts
  for `a/b`, `a_b`, `a__b`;
- partial reservation/state, interruption after actual rebase before receipt,
  completed-rebase resume with no replay, and terminal-before-release ownership;
- stale cleanup/release/rollback against a successor, including a successor that
  changed no refs; current/foreign commit cleanup rejection;
- rollback after a later clean jj operation or anchor replacement versus current
  rollback/repeated validated no-op; unrelated cwd and unchanged remote refs;
- eight incident-shaped foreign paths preserved byte-for-byte and not jj-
  snapshotted; `mechanical=CLEAN` remains `execution=BLOCKED`, never push-eligible;
- late evidence/source changes preventing release after terminal recording;
- conflict-free tree/range correspondence, no-op, unresolved text conflict,
  stacked child parent-tip equality and scoped stale-parent-history rebase.

## Honest coverage limits

The helper enforces a **cooperative local protocol**, not a sandbox against an
arbitrary writer with the same filesystem privileges. Persistent ownership
survives worker death; a non-cooperating writer can still modify files/metadata,
which must block currentness/cleanliness checks rather than trigger cleanup.
There is intentionally no automatic unknown-owner recovery or deletion API.

No live agent invocation tree or RFQ wrapper is exercised: same-operation
self-dispatch prohibition and native endpoint/subtree completion validation are
operator obligations, not facts inferred from a helper exit. The helper records
`topology_validation: operator-owned`, never a fictitious process-tree pass.
The implementation agent cannot run that agent exercise under its no-delegation
assignment; the separately blocked RFQ adapter and caller own that follow-up.

Mechanical verdict **selection** remains the workflow's existing model-owned
algebra, not a new algorithm in the helper. Tests supply mechanical labels when
exercising the ownership/terminal API; they do not certify every conflict verdict
or semantic resolution. Workflow T1/T3/T4/T6/T10 and T12's scoped path have direct
fixture coverage; T2 executes text-conflict production but not semantic verdict
selection. T7 rename, T8 delete, T9 binary, T11 multi-parent collapse, unscoped T12
verdict classification and a successful divergent-abandon case remain contract
scenarios, not claimed passing experiments. ACR-260/261 and the prompt-override
WRITE evals are specifications, not executable suites or agent-tree proof.
