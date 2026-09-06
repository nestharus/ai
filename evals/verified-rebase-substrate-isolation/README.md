# Verified-rebase substrate isolation fixtures

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s evals/verified-rebase-substrate-isolation -v
```

Requires Linux/local-filesystem `flock`, Python 3.10+, Git with
`merge-tree --write-tree --merge-base`, jj colocated Git support and JSON
operation/bookmark templates, Bash and jq. The conflict serialization/CLI
adapter is exercised with jj 0.39.0 and Git 2.43.0. Unknown serialization,
unsupported path renderings or conflict modes fail closed, not via ignored paths.
Fixtures use independent system-temp repositories and local bare remotes;
no network remote, production substrate or agent is invoked. Fixture Git commits
disable signing only inside those disposable repositories. Pipes synchronize
real worker processes without sleeps or a simulated ownership model.

## Runnable surface

Tests load the same-checkout `tools/verified_rebase.py` and execute the checked-in
workflow shell blocks through terminal production and release. They inspect the
actual summary, refs, patches, conflict payloads/associations, correspondence,
raw storage and logical trees, parent bundle links and generated rollback script.
Mechanical labels in negative calls are assertions to reject, not producer input.

The fixtures cover:

- overlapping owners, different branches sharing a substrate, aliases, suspended
  ownership and successful process exit without release;
- exclusive UUID allocation, blocked preflight with no ignore repair, independent
  simultaneous attempts, partial records and interrupted commands;
- stale release/cleanup/rollback, current rollback/repeated validated no-op,
  unexpected foreign files preserved without snapshot, and late evidence changes;
- actual command-return/checkpoint barriers for anchor, fetch, rebase, rollback,
  and accepted divergent abandonment, with clean foreign jj operation/Git-ref
  interference and no-interference controls;
- normal and text-conflict full workflow, no-op, scoped and unscoped stale-parent
  history, stacked parent/child cross-bundle associations, multi-parent basis
  collapse, rename, deletion and binary conflicts;
- real failed ort prediction (invalid configuration), incomplete output sets,
  wrong labels, unexplained rename residuals, parent pointer mismatch and modified
  parent evidence; these cannot become accepted mechanics;
- `a/b`, `a_b`, `a__b` simultaneously conflicted, complete durable payload and
  source-path associations, empty/substituted payload controls, extra/unassociated
  artifacts, and unexplained serialized-storage paths;
- remote snapshots before allocation through terminal (including blocked and
  unprovenanced outcomes) and separately after rollback; intentional publication
  to a disposable bare remote fails the same equality oracle.

Git storage residuals and raw range rows are preserved, not filtered. Logical
residuals are decoded only with an exact commit-header/tree/operation proof.
Every pre/post change is accounted for by stable ID, authored metadata, parent
edges and per-change ort prediction (including clean virtual merge bases).
Unexplained correspondence, inherited unresolved conflicts, and ort/jj rename
mismatches remain blocked. This is mechanical provenance, not semantic resolution.

## Evidence retention and limits

Set `VR_TEST_ARTIFACT_ROOT` to retain raw command receipts and fixture copies.
Tests execute in system temporary directories and copy their exact bytes out
before cleanup. `fixture-origin.json` records original paths/test identity;
retained copies are evidence, never resumable live substrates. Without this
variable, temporary fixtures are removed on completion.

The helper enforces a cooperative Linux/local-filesystem protocol, not a sandbox
against arbitrary same-user writers. Unexpected mutations must block, not trigger
automatic cleanup or takeover. There is no unknown-owner recovery/deletion API.

No live agent invocation tree or RFQ adapter is exercised. The selected endpoint
and caller must establish native same-operation completion separately; a helper
exit or `topology_validation: operator-owned` is not that evidence. Source/config
variants outside these fixtures are not claimed tested. Prompt-override WRITE
evals remain specifications, not agent-tree experiments or semantic review.
