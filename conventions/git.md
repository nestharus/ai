# Git Conventions

## Branches

- All work happens on branches, never directly on `main`.
- All branch work happens in a git worktree; the primary default-branch checkout is for inspection and branch-tracking only, including guarded clean fast-forward-only deployment synchronization under `~/ai/conventions/worktree-isolation.md`.
- The primary `main` checkout stays clean.

### Naming

Choose one naming scheme based on the project's tracker:

- **`<TICKET-ID>-<short-description>`** is **required** when the project uses a tracker (Linear, Jira, GitHub Issues with ticket-style IDs). Match the ticket ID casing exactly so the tracker auto-links. Every branch must reference an open ticket — if there isn't one yet, file it first, *then* cut the branch.
- **`feat/<short-description>`** is permitted only when the project has no tracker, or has explicitly declared in its `AGENTS.md` that ticket-linked branches are not required.
- Keep branch names short enough to stay legible in the GitHub UI. Cap total length at about 50 characters.
- Use lowercase hyphenated descriptions after the prefix or ticket ID.
- The `fix/` and `feat/` *kind prefixes* are redundant once a ticket prefix is present and should be dropped — the ticket already conveys the work type.

Examples:

- `ENG-4321-add-caching-layer` (ticket-tracked project — required form)
- `feat/add-caching-layer` (no-tracker project only)

### Topology for Multi-PR Initiatives

When one initiative ships as multiple stacked PRs, use explicit supporting branches:

- **`basis/<name>`** is a shared base branch when several child PRs depend on one common delta.
- **`integration/<name>`** is a temporary branch that merges multiple child PRs for cross-PR or end-to-end testing before any of them land on `main`.
- Child feature branches still use the normal naming schemes above.

Track the stack in the initiative's planning doc with a short table:

```markdown
| PR | Branch | Depends on | Merge order | Status |
|----|--------|------------|-------------|--------|
| #123 | feat/caching-repository | main | 1 | ready |
| #124 | feat/caching-service | #123 | 2 | draft |
| #125 | feat/caching-endpoint | #124 | 3 | draft |
| — | integration/caching-rollup | #123, #124, #125 | test only | testing |
```

- Merge order follows the dependency chain.
- If a branch depends on another PR, it stays stacked on that parent until the parent lands.

## Commits

- **GPG-sign every commit.** Configure signing globally:

```bash
git config --global user.signingkey <your-key-id>
git config --global commit.gpgsign true
```

- Store the signing key under `~/.gnupg/`.
- Use an RSA 4096-bit key unless the repository documents a different standard.
- Upload the public key to GitHub so signatures show as verified in the UI.
- **Prefer new commits over amends.** Amend only when the previous commit has not been pushed, or while applying findings from the single CodeRabbit review described in `~/ai/agents/coderabbit-operator.md`.
- Never amend a pushed commit outside that narrow loop.
- **No agent authorship attribution.** Agents do not add `Co-Authored-By:`, `Generated-By:`, provider-specific "wrote this" notes, "Generated with ...", or similar trailers.
- The commit author is the human operator who ran the pipeline; agents are tools.
- Prefer small, testable commits. Each commit should build, pass tests, and represent one concern.
- **Reference the ticket in every commit message** when the project uses a tracker. Use a leading scope, e.g. `INFA-118: surface script error in download status` — the tracker auto-links the commit and the change history stays navigable from the ticket. The same form is acceptable as a trailing `Refs: INFA-118` line for fixup-style commits where the leading scope would distort readability. Multiple tickets are listed comma-separated (`INFA-118, INFA-117: ...`).
- Branches that span several commits must reference the ticket on at least the head commit; per-commit references are preferred so individual cherries stay traceable when reorganizing.

## Pull Requests

- Open PRs in draft mode first.
- **Draft PR creation is routine.** Opening a draft PR is a normal pipeline step and is not treated as a special approval-gated action.
- **Promotion is human.** Moving a draft PR to ready-for-review requires an explicit human decision.
- Keep one concern per PR. For multi-concern split rules, see `~/ai/workflows/pr-review.md`.
- A large deletion is its own PR unless the repo documents a stronger exception.
- Dependency order matters. If PR B depends on PR A, PR A merges first and PR B remains stacked until that happens.

## Public Visibility

When a repository's PR list is visible to a public audience beyond the internal team:

- Draft PRs still remain routine.
- Promoting a draft to ready-for-review is Tier-3.
- Opening a new non-draft PR is also Tier-3.
- See `~/ai/workflows/tiered-approval.md` for the approval model.

## Summary Rules

- Work on branches, not `main`.
- All branch work happens in a git worktree; the primary default-branch checkout is for inspection and branch-tracking only, including guarded clean fast-forward-only deployment synchronization under `~/ai/conventions/worktree-isolation.md`.
- Keep `main` clean.
- Sign commits with GPG.
- Do not add agent authorship trailers.
- Use `feat/...` or exact-case ticket branches.
- Use `basis/...` and `integration/...` only when the branch topology needs them.
- Open draft PRs routinely; humans decide when review visibility changes.
