from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import copy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


TOOL_DIR = Path(__file__).resolve().parents[1] / "tools" / "wu-session-migration"
SPEC = importlib.util.spec_from_file_location(
    "wu_session_migration", TOOL_DIR / "wu_session_migration.py"
)
assert SPEC is not None and SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)
ApplyError = MIGRATION.ApplyError
InputError = MIGRATION.InputError
apply_plan = MIGRATION.apply_plan
build_plan = MIGRATION.build_plan


A = "a" * 40
B = "b" * 40
C = "c" * 40
D = "d" * 40
E = "e" * 40
REAL_INVENTORY = Path(
    os.environ.get(
        "AGE_260_REVIEWED_INVENTORY",
        "/home/nes/projects/agent-runner/planning/"
        "hourly-suspicious-process-investigator-feature/.scratch/"
        "age-260-session-migration-inventory.json",
    )
)
REAL_INVENTORY_SHA256 = "f48f87265635fb362a37294071cef7f8d016c5ad502a4cda27491a835f262622"
FROZEN_REAL_SQUASH_EVIDENCE = (
    Path(__file__).resolve().parent / "fixtures" / "age-260-merged-squash-evidence.json"
)
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


@pytest.fixture(autouse=True)
def isolated_transaction_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WU_SESSION_MIGRATION_STATE_DIR", str(tmp_path / "transaction-state"))
    setattr(MIGRATION, "FAULT_HOOK", None)
    yield
    setattr(MIGRATION, "FAULT_HOOK", None)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _capture(command: list[str], payload: object) -> dict[str, object]:
    return {
        "command": command,
        "captured_at": "2026-07-19T00:00:00+00:00",
        "payload": payload,
        "payload_sha256": _digest(_canonical_bytes(payload)),
    }


@pytest.mark.parametrize("helper_name", ["_run_text_command", "_run_bytes_command"])
def test_trusted_command_timeout_is_bounded_and_translated(
    helper_name: str, monkeypatch: pytest.MonkeyPatch
):
    observed_timeout = None

    def timeout(command: list[str], **kwargs: Any):
        nonlocal observed_timeout
        observed_timeout = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(command, observed_timeout)

    monkeypatch.setattr(MIGRATION.subprocess, "run", timeout)

    with pytest.raises(ApplyError, match="trusted evidence capture failed"):
        getattr(MIGRATION, helper_name)(["git", "status"])

    assert observed_timeout == MIGRATION.TRUSTED_COMMAND_TIMEOUT_SECONDS


@pytest.mark.parametrize("helper_name", ["_run_text_command", "_run_bytes_command"])
def test_trusted_commands_sanitize_inherited_git_environment(
    helper_name: str, monkeypatch: pytest.MonkeyPatch
):
    observed_environment = None

    def capture_environment(command: list[str], **kwargs: Any):
        nonlocal observed_environment
        observed_environment = kwargs.get("env")
        stdout = b"" if helper_name == "_run_bytes_command" else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout)

    monkeypatch.setenv("GIT_DIR", "/untrusted/repository/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/untrusted/worktree")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setattr(MIGRATION.subprocess, "run", capture_environment)

    getattr(MIGRATION, helper_name)(["git", "status"])

    assert observed_environment is not None
    assert "GIT_DIR" not in observed_environment
    assert "GIT_WORK_TREE" not in observed_environment
    assert "GIT_CONFIG_COUNT" not in observed_environment
    assert observed_environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert observed_environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert observed_environment["GIT_TERMINAL_PROMPT"] == "0"


def _merge_method_capture(
    pr_url: str,
    head_sha: str,
    merge_sha: str,
    method: str,
    command: list[str] | None = None,
) -> dict[str, object]:
    if command is None:
        parsed = pr_url.removeprefix("https://github.com/").split("/")
        command = [
            "gh",
            "api",
            "--method",
            "PUT",
            f"repos/{parsed[0]}/{parsed[1]}/pulls/{parsed[3]}/merge",
            "-f",
            f"merge_method={method.lower()}",
            "-f",
            f"sha={head_sha}",
        ]
    return {
        "source": "github-merge-operation-response",
        **_capture(
            command,
            {
                "sha": merge_sha,
                "merged": True,
                "message": "Pull Request successfully merged",
            },
        ),
    }


def _evidence(
    pr_url: str,
    branch: str,
    base: str,
    *,
    state: str = "OPEN",
    head: str = B,
    merge_sha: str | None = None,
    merged_at: str | None = None,
    parents: list[str] | None = None,
    merge_method: str | None = None,
    merge_method_command: list[str] | None = None,
    branch_out: tuple[str, str, Path] | None = None,
) -> dict[str, object]:
    payload = {
        "url": pr_url,
        "state": state,
        "headRefName": branch,
        "headRefOid": head,
        "baseRefName": base,
        "baseRefOid": C,
        "mergeCommit": {"oid": merge_sha} if merge_sha else None,
        "mergedAt": merged_at,
    }
    record: dict[str, object] = {
        "provider": _capture(
            ["gh", "pr", "view", "--json", MIGRATION.PR_PROVIDER_JSON_SELECTOR, "--", pr_url], payload
        ),
        "merge_commit": None,
        "merge_method": None,
        "branch_out": None,
    }
    if merge_sha:
        repository = branch_out[2] if branch_out else Path("/trusted/repo")
        text = " ".join([merge_sha, *(parents or [])])
        record["merge_commit"] = _capture(
            ["git", "-C", str(repository), "show", "-s", "--format=%H %P", merge_sha],
            text,
        )
        if merge_method is not None:
            record["merge_method"] = _merge_method_capture(
                pr_url,
                head,
                merge_sha,
                merge_method,
                merge_method_command,
            )
    if branch_out:
        requested, resolved, repository = branch_out
        record["branch_out"] = _capture(
            ["git", "-C", str(repository), "rev-parse", "--verify", f"{requested}^{{commit}}"],
            {
                "repository": str(repository),
                "requested_oid": requested,
                "resolved_oid": resolved,
            },
        )
    return record


def _complete_fixture(tmp_path: Path) -> dict[str, Any]:
    projects = [tmp_path / f"project-{index}" for index in range(7)]
    planning_roots = [project / "planning" for project in projects]
    index_paths = [root / "sessions.index.json" for root in planning_roots]
    index_documents: dict[Path, dict[str, Any]] = {
        path: {"sessions": []} for path in index_paths
    }
    manifests: list[dict[str, Any]] = []
    manifest_documents: dict[Path, dict[str, Any] | None] = {}
    cohort: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {
        "schema": MIGRATION.PR_EVIDENCE_SCHEMA,
        "prs": {},
    }

    for index in range(42):
        planning = planning_roots[index % 7]
        path = planning / f"session-{index:03d}" / "session.json"
        branch = "age-1" if index == 0 else f"branch-{index:03d}"
        ticket = "AGE-1" if index == 0 else f"AGE-{index + 1}"
        pr_url = (
            "https://github.com/example/repo/pull/1"
            if index == 0
            else f"https://github.com/example/repo/pull/{index + 1}"
        )
        base = f"base-{index:03d}"
        is_refusal = index >= 39
        is_merged = 36 <= index <= 38
        persisted_base = base if index < 25 else None
        document: dict[str, Any] = {
            "session_id": f"session-{index:03d}",
            "ticket_id": None if is_refusal else ticket,
            "ticket_system": "none" if is_refusal else "linear",
            "branch": branch,
            "branch_out_sha": A,
            "draft_pr_url": pr_url,
            "draft_pr_head_sha": B,
            "worktree_path": str(projects[index % 7] / "worktrees" / branch),
            "planning_dir": str(path.parent),
            "scratch_dir": str(path.parent / ".scratch"),
            "closed_at": None,
        }
        if persisted_base is not None:
            document["base_branch"] = persisted_base
        if is_merged:
            document["merge_sha"] = E
        manifest_documents[path] = document
        classification = (
            "merged but wake incomplete" if is_merged else "draft/open dormant and wakeable"
        )
        manifests.append(
            {
                "path": str(path),
                "readable": True,
                "classification": classification,
                "fields": dict(document),
            }
        )
        candidate: dict[str, Any] = {
            "manifest_path": str(path),
            "derived_session_manifest_path": str(path),
            "classification": classification,
            "ticket_id": None if is_refusal else ticket,
            "ticket_system": "none" if is_refusal else "linear",
            "branch": branch,
            "branch_out_sha": A,
            "persisted_head_sha": B,
            "persisted_or_derived_base_branch": persisted_base,
            "persisted_or_derived_pre_merge_base_sha": C if index in {36, 37} else None,
            "pr_url": pr_url,
            "merge_sha": E if is_merged else None,
            "existing_index_rows": [],
            "explicit_refusal_reasons": ["unprovable identity"] if is_refusal else [],
            "fully_derivable_from_persisted_evidence": index in {36, 37},
            "later_trusted_pr_query_requirements": ["trusted provider status"]
            if index < 36 or index == 38
            else [],
        }
        cohort.append(candidate)
        if not is_refusal:
            if is_merged:
                evidence["prs"][pr_url] = _evidence(
                    pr_url,
                    branch,
                    persisted_base or base,
                    state="MERGED",
                    merge_sha=E,
                    merged_at="2026-07-18T12:00:00Z",
                    parents=[C, B],
                    branch_out=(A, A, projects[index % 7]),
                )
            else:
                evidence["prs"][pr_url] = _evidence(
                    pr_url,
                    branch,
                    persisted_base or base,
                    branch_out=(A, A, projects[index % 7]),
                )

    # Exactly 30 distinct cohort manifests are indexed with two duplicate aliases.
    for index in range(30):
        candidate = cohort[index]
        index_path = index_paths[index % 7]
        row = {
            "ticket_id": candidate["ticket_id"],
            "ticket_system": candidate["ticket_system"],
            "branch": candidate["branch"],
            "draft_pr_url": candidate["pr_url"],
            "draft_pr_head_sha": B,
            "manifest_path": candidate["manifest_path"],
        }
        if candidate["persisted_or_derived_base_branch"] is not None:
            row["base_branch"] = candidate["persisted_or_derived_base_branch"]
        copies = 2 if index in {0, 1} else 1
        for _ in range(copies):
            locator_index = len(index_documents[index_path]["sessions"])
            index_documents[index_path]["sessions"].append(dict(row))
            locator = f"sessions[{locator_index}]"
            candidate["existing_index_rows"].append(
                {"index_path": str(index_path), "row_locator": locator}
            )
            index_rows.append(
                {
                    "index_path": str(index_path),
                    "row_locator": locator,
                    "classification": "draft/open dormant and wakeable",
                    "linked_manifest_path": candidate["manifest_path"],
                    "fields": dict(row),
                }
            )

    noncohort_specs = [
        (179, "already closed/post-merge complete", 76),
        (82, "pre-PR/incomplete", 40),
        (2, "abandoned/ambiguous", 1),
        (1, "malformed/unreadable", 3),
    ]
    next_manifest = 42
    for manifest_count, classification, row_count in noncohort_specs:
        category_paths: list[Path] = []
        for _ in range(manifest_count):
            planning = planning_roots[next_manifest % 7]
            path = planning / f"history-{next_manifest:03d}" / "session.json"
            if classification == "malformed/unreadable":
                manifest_documents[path] = None
                fields: dict[str, Any] = {}
                readable = False
            else:
                document = {
                    "session_id": f"history-{next_manifest:03d}",
                    "branch": f"history-{next_manifest:03d}",
                    "closed_at": "2026-07-01T00:00:00Z"
                    if classification == "already closed/post-merge complete"
                    else None,
                }
                manifest_documents[path] = document
                fields = dict(document)
                readable = True
            manifests.append(
                {
                    "path": str(path),
                    "readable": readable,
                    "classification": classification,
                    "fields": fields,
                }
            )
            category_paths.append(path)
            next_manifest += 1
        for row_index in range(row_count):
            index_path = index_paths[(len(index_rows) + row_index) % 7]
            row: dict[str, Any] = {
                "ticket_id": f"HIST-{classification[:2]}-{row_index}",
                "branch": f"history-row-{classification[:2]}-{row_index}",
            }
            linked: str | None = None
            if classification != "malformed/unreadable":
                linked = str(category_paths[row_index % len(category_paths)])
                row["manifest_path"] = linked
            locator_index = len(index_documents[index_path]["sessions"])
            index_documents[index_path]["sessions"].append(row)
            index_rows.append(
                {
                    "index_path": str(index_path),
                    "row_locator": f"sessions[{locator_index}]",
                    "classification": classification,
                    "linked_manifest_path": linked,
                    "fields": dict(row),
                }
            )

    assert len(manifests) == 306
    assert len(index_rows) == 152
    index_files = [
        {"path": str(path), "row_count": len(index_documents[path]["sessions"])}
        for path in index_paths
    ]
    inventory = {
        "schema": MIGRATION.INVENTORY_SCHEMA,
        "scope": "fixture",
        "counts": {
            **MIGRATION.EXPECTED_COUNTS,
            "manifest_classifications": {
                "already closed/post-merge complete": 179,
                "draft/open dormant and wakeable": 39,
                "merged but wake incomplete": 3,
                "pre-PR/incomplete": 82,
                "abandoned/ambiguous": 2,
                "malformed/unreadable": 1,
            },
            "index_row_classifications": {
                "already closed/post-merge complete": 76,
                "draft/open dormant and wakeable": 32,
                "pre-PR/incomplete": 40,
                "abandoned/ambiguous": 1,
                "malformed/unreadable": 3,
            },
        },
        "manifests": manifests,
        "index_files": index_files,
        "index_rows": index_rows,
        "migration_cohort": cohort,
    }
    dispositions = {
        "schema": MIGRATION.DISPOSITION_SCHEMA,
        "dispositions": [
            {
                "manifest_path": cohort[index]["manifest_path"],
                "reason": "Manager accepts loss of wake automation for unprovable identity.",
                "accepted_breakage": True,
                "owner": "manager",
            }
            for index in range(39, 42)
        ],
    }
    resolutions = {
        "schema": MIGRATION.CONFLICT_RESOLUTION_SCHEMA,
        "resolutions": [],
    }
    fixture = {
        "inventory_path": tmp_path / "inventory.json",
        "evidence_path": tmp_path / "evidence.json",
        "dispositions_path": tmp_path / "dispositions.json",
        "resolutions_path": tmp_path / "resolutions.json",
        "plan_path": tmp_path / "plan.json",
        "inventory": inventory,
        "evidence": evidence,
        "dispositions": dispositions,
        "resolutions": resolutions,
        "manifest_documents": manifest_documents,
        "index_documents": index_documents,
        "manifest_paths": [Path(row["path"]) for row in manifests],
        "index_paths": index_paths,
        "cohort": cohort,
    }
    _persist(fixture)
    return fixture


def _persist(fixture: dict[str, Any]) -> str:
    for path, document in fixture["manifest_documents"].items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if document is None:
            path.write_text("{ malformed\n", encoding="utf-8")
        else:
            _write_json(path, document)
    for path, document in fixture["index_documents"].items():
        _write_json(path, document)
    _write_json(fixture["inventory_path"], fixture["inventory"])
    digest = _digest(fixture["inventory_path"].read_bytes())
    fixture["evidence"]["reviewed_inventory_sha256"] = digest
    _write_json(fixture["evidence_path"], fixture["evidence"])
    _write_json(fixture["dispositions_path"], fixture["dispositions"])
    _write_json(fixture["resolutions_path"], fixture["resolutions"])
    fixture["reviewed_digest"] = digest
    return digest


def _plan(fixture: dict[str, Any], *, plan_path: Path | None = None) -> dict[str, Any]:
    return build_plan(
        fixture["inventory_path"],
        fixture["evidence_path"],
        fixture["dispositions_path"],
        fixture["reviewed_digest"],
        fixture["resolutions_path"],
        plan_path,
    )


def _write_plan(fixture: dict[str, Any], plan: dict[str, Any]) -> Path:
    _write_json(fixture["plan_path"], plan)
    return fixture["plan_path"]


def _target(fixture: dict[str, Any], index: int = 0) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    candidate = fixture["cohort"][index]
    path = Path(candidate["manifest_path"])
    document = fixture["manifest_documents"][path]
    assert isinstance(document, dict)
    return candidate, path, document


def _refresh_manifest_inventory(fixture: dict[str, Any], path: Path) -> None:
    row = next(item for item in fixture["inventory"]["manifests"] if item["path"] == str(path))
    document = fixture["manifest_documents"][path]
    assert isinstance(document, dict)
    row["fields"] = dict(document)


def _refresh_index_inventory(fixture: dict[str, Any], key: tuple[str, str]) -> None:
    index_path = Path(key[0])
    locator = key[1]
    position = int(locator.removeprefix("sessions[").removesuffix("]"))
    row = fixture["index_documents"][index_path]["sessions"][position]
    inventory_row = next(
        item
        for item in fixture["inventory"]["index_rows"]
        if (item["index_path"], item["row_locator"]) == key
    )
    inventory_row["fields"] = dict(row)


def _runtime_manifest(planning_root: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = planning_root / "AGE-260" / "session.json"
    manifest_path.parent.mkdir(parents=True)
    return manifest_path, {
        "session_id": "runtime-session",
        "ticket_id": "AGE-260",
        "ticket_system": "linear",
        "branch": "age-260-runtime",
        "base_branch": "main",
        "branch_out_sha": A,
        "repo_root": str(planning_root.parent / "trunk"),
        "worktree_path": str(planning_root.parent / "worktrees" / "age-260-runtime"),
        "planning_dir": str(manifest_path.parent),
        "scratch_dir": str(manifest_path.parent / ".scratch"),
        "session_manifest_path": str(manifest_path),
        "cold_start_disposition_ref": None,
        "phase_3_estimate_writeback_ref": None,
        "phase_3_estimate_writeback_sha256": None,
        "phase_history": [
            {
                "phase": "2.5",
                "status": "complete",
                "ts": "2026-07-18T00:00:00Z",
            }
        ],
        "draft_pr_url": None,
        "draft_pr_number": None,
        "draft_pr_head_sha": None,
        "pr_open_base_sha": None,
        "pre_merge_base_sha": None,
        "merge_sha": None,
        "post_merge_base_sha": None,
        "merged_at": None,
        "post_merge": {},
        "successor_session_brief": None,
        "closed_at": None,
    }


def _active_row(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    return MIGRATION._canonical_index_row(manifest, manifest_path)


def _row_identity(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in MIGRATION.ROW_IDENTITY_KEYS}


def _write_runtime_request(
    request_path: Path,
    operation: str,
    planning_root: Path,
    manifest_path: Path,
    index_path: Path,
    replacement_manifest: dict[str, Any],
    replacement_index: dict[str, Any],
    row_identity: dict[str, Any] | None,
    artifacts: dict[str, Path] | None = None,
) -> Path:
    sources: dict[str, Any] = {
        "manifest": MIGRATION.runtime_source_identity(manifest_path),
        "index": MIGRATION.runtime_source_identity(index_path),
    }
    if operation in MIGRATION.PRE_PR_BIND_OPERATIONS:
        sources["artifacts"] = [
            {
                "role": role,
                "path": str(path),
                **{
                    key: value
                    for key, value in MIGRATION.runtime_source_identity(path).items()
                    if key != "exists"
                },
            }
            for role, path in sorted((artifacts or {}).items())
        ]
    request = {
        "schema": MIGRATION.RUNTIME_REQUEST_SCHEMA,
        "operation": operation,
        "planning_root": str(planning_root),
        "manifest_path": str(manifest_path),
        "index_path": str(index_path),
        "row_identity": row_identity,
        "sources": sources,
        "replacement_manifest": replacement_manifest,
        "replacement_index": replacement_index,
        "input_set_sha256": "",
        "payload_sha256": "",
    }
    request["input_set_sha256"], request["payload_sha256"] = MIGRATION.runtime_request_digests(request)
    _write_json(request_path, request)
    return request_path


def _runtime_case(
    tmp_path: Path, target_operation: str, *, feature: bool = False
) -> dict[str, Any]:
    project_planning_root = tmp_path / "project" / "planning"
    request_dir = tmp_path / "requests" / ("feature" if feature else "direct")
    planning_root = (
        project_planning_root / "features" / "acr-337" / "routes"
        if feature
        else project_planning_root
    )
    planning_root.mkdir(parents=True)
    manifest_path, initial_manifest = _runtime_manifest(planning_root)
    active_path = planning_root / "sessions.active-wake.json"
    direct_index_path = project_planning_root / "sessions.active-wake.json"
    if feature:
        initial_manifest.update(
            {
                "repo_root": str(project_planning_root.parent / "trunk"),
                "worktree_path": str(
                    project_planning_root.parent / "worktrees" / "age-260-runtime"
                ),
                "scratch_dir": str(
                    project_planning_root
                    / "features"
                    / "acr-337-scratch"
                    / "routes"
                    / "age-260"
                ),
            }
        )
        if not direct_index_path.exists():
            _write_json(
                direct_index_path,
                {"schema": MIGRATION.ACTIVE_INDEX_SCHEMA, "sessions": []},
            )
    scratch_dir = Path(initial_manifest["scratch_dir"])
    scratch_dir.mkdir(parents=True)
    repo_root = Path(initial_manifest["repo_root"])
    repo_root.mkdir(parents=True, exist_ok=True)
    ticket_snapshot = scratch_dir / "ticket.md"
    ticket_snapshot.write_text("# AGE-260\n")
    operator_path = repo_root / "agents" / "linear-operator.md"
    operator_path.parent.mkdir(parents=True, exist_ok=True)
    operator_path.write_text("# linear operator\n")
    contract_path = repo_root / "contracts" / "linear-operator.yaml"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(
        "source: linear-operator\nestimate_mutation_enabled: false\n"
    )
    subprocess.run(["git", "init", "-q", str(repo_root)], check=True, env=GIT_ENV)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "add",
            "--",
            "agents/linear-operator.md",
            "contracts/linear-operator.yaml",
        ],
        check=True,
        env=GIT_ENV,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "-c",
            "user.name=Session Test",
            "-c",
            "user.email=session-test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "fixture producer identities",
        ],
        check=True,
        env=GIT_ENV,
    )
    initial_manifest["branch_out_sha"] = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
        env=GIT_ENV,
    ).stdout.strip()
    proposal_path = manifest_path.parent / "proposals" / "age-260-AGE-260.md"
    proposal_path.parent.mkdir(parents=True)
    proposal_path.write_text("# Proposal\n")
    cold_start_path = scratch_dir / "questions" / "cold-start.answer.json"
    _write_json(
        cold_start_path,
        {
            "schema_version": 1,
            "kind": "agent_answer",
            "question_id": "age-260-cold-start",
            "answer": {
                "selected_option_ids": ["proceed-without-baseline-estimate"],
                "confirmed": True,
            },
        },
    )
    verification_path = scratch_dir / "ticket-operations" / "estimate-readback.json"
    _write_json(verification_path, {"status": "PASS", "estimate": 8})
    initial_manifest.update(
        {
            "contract_resolution_path": str(
                scratch_dir / "phase0-contract-resolution.json"
            ),
            "contract_resolution_producing_invocation_uuid": (
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
            ),
            "contract_resolution_sha256": "0" * 64,
            "estimate_capability_evidence": {
                "output_task": "update-estimate",
                "side_effect": "linear-update-estimate",
            },
            "estimate_field": "estimate",
            "estimate_mutation_policy": {
                "resolution": "legacy_capability",
                "source": "legacy_capability",
                "value": None,
            },
            "estimate_writeback_disposition": "update_estimate_required",
            "resolved_defaults_source": {"linear_team_key": "caller"},
            "ticket_snapshot_path": str(ticket_snapshot),
            "ticket_snapshot_sha256": _digest(ticket_snapshot.read_bytes()),
            "ticket_snapshot_producing_invocation_uuid": (
                "11111111-1111-4111-8111-111111111111"
            ),
            "resolved_operator_path": str(operator_path),
            "resolved_operator_sha256": _digest(operator_path.read_bytes()),
            "resolved_operator_contract_path": str(contract_path),
            "resolved_contract_path": str(contract_path),
            "resolved_contract_sha256": _digest(contract_path.read_bytes()),
            "topology_revalidation_path": str(
                scratch_dir / "phase0-topology-revalidation.json"
            ),
            "topology_revalidation_sha256": "5" * 64,
        }
    )
    topology_path = Path(initial_manifest["topology_revalidation_path"])
    _write_json(topology_path, {"schema": "phase0-topology-revalidation-v1"})
    initial_manifest["topology_revalidation_sha256"] = _digest(
        topology_path.read_bytes()
    )
    resolution_path = Path(initial_manifest["contract_resolution_path"])
    _write_json(
        resolution_path,
        {
            "estimate_capability_evidence": {
                "output_task": "update-estimate",
                "side_effect": "linear-update-estimate",
            },
            "estimate_field": "estimate",
            "estimate_mutation_policy": {
                "resolution": "legacy_capability",
                "source": "legacy_capability",
                "value": None,
            },
            "estimate_writeback_disposition": "update_estimate_required",
            "linear_team_key_source": "caller",
            "resolved_contract_path": str(contract_path),
            "resolved_contract_sha256": _digest(contract_path.read_bytes()),
            "resolved_operator_path": str(operator_path),
            "resolved_operator_sha256": _digest(operator_path.read_bytes()),
            "schema": "implementation-phase0-contract-resolution-v1",
            "ticket_system": "linear",
        },
    )
    initial_manifest["contract_resolution_sha256"] = _digest(
        resolution_path.read_bytes()
    )
    estimate_path = (
        manifest_path.parent / "risk" / "age-260-phase-3-estimate-writeback.json"
    )
    estimate = {
        "schema_version": "phase-3-estimate-writeback-v1",
        "ticket_id": "AGE-260",
        "ticket_system": "linear",
        "disposition": "write_verified",
        "estimate_field": "estimate",
        "cold_start_disposition_ref": str(cold_start_path),
        "phase_0_ticket_snapshot_path": str(ticket_snapshot),
        "phase_0_ticket_snapshot_sha256": _digest(ticket_snapshot.read_bytes()),
        "phase_0_ticket_snapshot_producing_invocation_uuid": (
            "22222222-2222-4222-8222-222222222222"
        ),
        "phase_3_proposal_path": str(proposal_path),
        "phase_3_proposal_sha256": _digest(proposal_path.read_bytes()),
        "resolved_operator_path": str(operator_path),
        "resolved_operator_sha256": _digest(operator_path.read_bytes()),
        "resolved_operator_contract_path": str(contract_path),
        "resolved_contract_sha256": _digest(contract_path.read_bytes()),
        "update_estimate_dispatch_expected": True,
        "update_estimate_dispatch_executed": True,
        "write_verification_evidence": {
            "status": "PASS",
            "path": str(verification_path),
            "sha256": _digest(verification_path.read_bytes()),
        },
        "currentness": {
            "cold_start_disposition_sha256": _digest(cold_start_path.read_bytes()),
            "phase_0_ticket_snapshot_sha256": _digest(ticket_snapshot.read_bytes()),
            "phase_3_proposal_sha256": _digest(proposal_path.read_bytes()),
            "resolved_operator_sha256": _digest(operator_path.read_bytes()),
            "resolved_contract_sha256": _digest(contract_path.read_bytes()),
            "write_verification_sha256": _digest(verification_path.read_bytes()),
        },
    }
    _write_json(estimate_path, estimate)
    phase3_artifacts = {
        "cold-start-disposition": cold_start_path,
        "phase-0-ticket-snapshot": ticket_snapshot,
        "phase-3-estimate-writeback": estimate_path,
        "phase-3-proposal": proposal_path,
        "resolved-ticket-contract": contract_path,
        "resolved-ticket-operator": operator_path,
        "write-verification-evidence": verification_path,
    }
    operations = [
        "phase0-init",
        "phase0-reresolve",
        "cold-start-disposition-bind",
        "phase3-bind",
        "phase3-rebind",
        "phase7-upsert",
        "phase9-update",
        "resumer-update",
        "resumer-close",
    ]

    for operation in operations:
        if operation == "phase0-init":
            replacement_manifest = copy.deepcopy(initial_manifest)
            replacement_index = {"schema": MIGRATION.ACTIVE_INDEX_SCHEMA, "sessions": []}
            index_path = active_path
            identity = None
            artifacts = None
        else:
            current_manifest = json.loads(manifest_path.read_text())
            replacement_manifest = copy.deepcopy(current_manifest)
            index_path = active_path
            if operation == "phase0-reresolve":
                _write_json(
                    resolution_path,
                    {
                        "estimate_capability_evidence": None,
                        "estimate_field": "estimate",
                        "estimate_mutation_policy": {
                            "resolution": "explicit_contract_policy",
                            "source": str(contract_path),
                            "value": False,
                        },
                        "estimate_writeback_disposition": (
                            "no_write_policy_disabled"
                        ),
                        "linear_team_key_source": "caller",
                        "resolved_contract_path": str(contract_path),
                        "resolved_contract_sha256": _digest(
                            contract_path.read_bytes()
                        ),
                        "resolved_operator_path": str(operator_path),
                        "resolved_operator_sha256": _digest(
                            operator_path.read_bytes()
                        ),
                        "schema": "implementation-phase0-contract-resolution-v1",
                        "ticket_system": "linear",
                    },
                )
                replacement_manifest.update(
                    {
                        "contract_resolution_producing_invocation_uuid": (
                            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
                        ),
                        "contract_resolution_sha256": _digest(
                            resolution_path.read_bytes()
                        ),
                        "estimate_capability_evidence": None,
                        "estimate_mutation_policy": {
                            "resolution": "explicit_contract_policy",
                            "source": str(contract_path),
                            "value": False,
                        },
                        "estimate_writeback_disposition": (
                            "no_write_policy_disabled"
                        ),
                        "ticket_snapshot_producing_invocation_uuid": (
                            "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
                        ),
                    }
                )
                replacement_index = json.loads(active_path.read_text())
                identity = None
                artifacts = {
                    "phase-0-contract-resolution": resolution_path,
                    "phase-0-ticket-snapshot": ticket_snapshot,
                    "phase-0-topology-revalidation": topology_path,
                    "resolved-ticket-contract": contract_path,
                    "resolved-ticket-operator": operator_path,
                }
            elif operation == "cold-start-disposition-bind":
                replacement_manifest["cold_start_disposition_ref"] = str(cold_start_path)
                replacement_index = json.loads(active_path.read_text())
                identity = None
                artifacts = {"cold-start-disposition": cold_start_path}
            elif operation == "phase3-bind":
                if target_operation == "phase3-rebind":
                    estimate.update(
                        {
                            "disposition": "no_write_policy_disabled",
                            "estimate_mutation_policy": current_manifest[
                                "estimate_mutation_policy"
                            ],
                            "update_estimate_dispatch_expected": False,
                            "update_estimate_dispatch_executed": False,
                            "update_estimate_prompt_path": None,
                            "update_estimate_prompt_sha256": None,
                            "update_estimate_log_path": None,
                            "update_estimate_log_sha256": None,
                            "update_estimate_invocation_uuid": None,
                            "write_verification_evidence": None,
                        }
                    )
                    estimate["currentness"]["disposition"] = (
                        "no_write_policy_disabled"
                    )
                    estimate["currentness"]["estimate_mutation_policy"] = (
                        current_manifest["estimate_mutation_policy"]
                    )
                    estimate["currentness"]["write_verification_sha256"] = None
                    _write_json(estimate_path, estimate)
                    phase3_artifacts = dict(phase3_artifacts)
                    phase3_artifacts.pop("write-verification-evidence")
                replacement_manifest.update(
                    {
                        "phase_3_estimate_writeback_ref": str(estimate_path),
                        "phase_3_estimate_writeback_sha256": _digest(
                            estimate_path.read_bytes()
                        ),
                        "phase_history": replacement_manifest["phase_history"] + [
                            {
                                "phase": "3",
                                "status": "complete",
                                "ts": "2026-07-19T00:00:00Z",
                            }
                        ],
                    }
                )
                replacement_index = json.loads(active_path.read_text())
                identity = None
                artifacts = phase3_artifacts
            elif operation == "phase3-rebind":
                if target_operation != "phase3-rebind":
                    continue
                return _next_phase3_rebind_case(
                    {
                        "operation": operation,
                        "request_dir": request_dir,
                        "project_planning_root": project_planning_root,
                        "planning_root": planning_root,
                        "manifest_path": manifest_path,
                        "index_path": index_path,
                        "direct_index_path": direct_index_path,
                        "repo_root": repo_root,
                    }
                )
            elif operation == "phase7-upsert":
                replacement_manifest.update(
                    {
                        "draft_pr_url": "https://github.com/example/repo/pull/260",
                        "draft_pr_number": 260,
                        "draft_pr_head_sha": B,
                        "pr_open_base_sha": C,
                        "phase_history": replacement_manifest["phase_history"]
                        + [{"phase": "7", "status": "complete", "ts": "2026-07-19T00:10:00Z"}],
                    }
                )
            elif operation == "phase9-update":
                replacement_manifest.update(
                    {
                        "phase_8_reviewed_is_draft": True,
                        "phase_8_reviewed_base_sha": C,
                        "phase_8_reviewed_head_sha": B,
                        "phase_9_currentness_result": "PASS",
                        "phase_history": replacement_manifest["phase_history"]
                        + [{"phase": "9", "status": "complete", "ts": "2026-07-19T00:20:00Z"}],
                    }
                )
            elif operation == "resumer-update":
                replacement_manifest.update(
                    {
                        "pre_merge_base_sha": C,
                        "merge_sha": E,
                        "merged_at": "2026-07-19T00:00:00Z",
                        "phase_history": replacement_manifest["phase_history"]
                        + [{"phase": "wake", "status": "complete", "ts": "2026-07-19T00:30:00Z"}],
                    }
                )
            else:
                replacement_manifest.update(
                    {
                        "closed_at": "2026-07-19T01:00:00Z",
                        "post_merge": {"tests": "PASS"},
                        "phase_history": replacement_manifest["phase_history"]
                        + [{"phase": "closed", "status": "complete", "ts": "2026-07-19T01:00:00Z"}],
                    }
                )
            if operation not in MIGRATION.PRE_PR_BIND_OPERATIONS:
                artifacts = None
                row = _active_row(replacement_manifest, manifest_path)
                identity = _row_identity(row)
                if operation == "phase7-upsert":
                    replacement_index = {
                        "schema": MIGRATION.ACTIVE_INDEX_SCHEMA,
                        "sessions": [row],
                    }
                else:
                    replacement_index = json.loads(active_path.read_text())
                    if operation == "resumer-close":
                        replacement_index["sessions"] = []
                    else:
                        replacement_index["sessions"] = [row]
        request_path = _write_runtime_request(
            request_dir / f"{operation}.json",
            operation,
            planning_root,
            manifest_path,
            index_path,
            replacement_manifest,
            replacement_index,
            identity,
            artifacts,
        )
        if operation == target_operation:
            return {
                "operation": operation,
                "request_path": request_path,
                "project_planning_root": project_planning_root,
                "planning_root": planning_root,
                "manifest_path": manifest_path,
                "index_path": index_path,
                "direct_index_path": direct_index_path,
                "repo_root": repo_root,
                "replacement_manifest": replacement_manifest,
                "replacement_index": replacement_index,
                "artifacts": artifacts,
            }
        MIGRATION.apply_runtime_request(request_path, operation)
    raise AssertionError(target_operation)


def _next_phase3_rebind_case(case: dict[str, Any]) -> dict[str, Any]:
    manifest_path = case["manifest_path"]
    index_path = case["index_path"]
    source_manifest = json.loads(manifest_path.read_text())
    current_attempt = source_manifest.get("phase_3_binding_attempt", 1)
    next_attempt = current_attempt + 1
    ticket_id = source_manifest["ticket_id"]
    planning_dir = manifest_path.parent
    risk_dir = planning_dir / "risk"
    proposal_dir = planning_dir / "proposals"
    prior_estimate_path = Path(source_manifest["phase_3_estimate_writeback_ref"])
    prior_estimate = json.loads(prior_estimate_path.read_text())
    prior_proposal_path = Path(prior_estimate["phase_3_proposal_path"])

    audit_path = risk_dir / f"phase-4-attempt-{current_attempt}-audit-history.md"
    audit_path.write_text(f"attempt: {current_attempt}\ndecision: return_to_phase_3\n")
    return_path = risk_dir / f"phase-4-attempt-{current_attempt}-return-decision.json"
    _write_json(
        return_path,
        {
            "schema": "apply-gate-set-result-v1",
            "ticket_id": ticket_id,
            "status": "BLOCKED",
            "terminal_decision": "return_to_phase_3_proposal_revision",
            "phase_5_authorized": False,
            "estimate_disposition": {
                "path": str(prior_estimate_path),
                "sha256": _digest(prior_estimate_path.read_bytes()),
            },
            "phase_3_proposal": {
                "path": str(prior_proposal_path),
                "sha256": _digest(prior_proposal_path.read_bytes()),
            },
            "audit_history_path": str(audit_path),
            "artifact_sha256": {
                str(prior_proposal_path): _digest(prior_proposal_path.read_bytes()),
                str(audit_path): _digest(audit_path.read_bytes()),
            },
        },
    )

    revised_proposal_path = (
        proposal_dir / f"{ticket_id.lower()}-{ticket_id}-attempt-{next_attempt}.md"
    )
    revised_proposal_path.write_text(
        f"# Proposal attempt {next_attempt}\n\nSubstantive revision {next_attempt}.\n"
    )
    revised_estimate_path = (
        risk_dir
        / f"{ticket_id.lower()}-phase-3-estimate-writeback-attempt-{next_attempt}.json"
    )
    revised_estimate = copy.deepcopy(prior_estimate)
    revised_estimate.update(
        {
            "phase_3_binding_attempt": next_attempt,
            "prior_phase_3_estimate_writeback_ref": str(prior_estimate_path),
            "prior_phase_3_estimate_writeback_sha256": _digest(
                prior_estimate_path.read_bytes()
            ),
            "phase_4_return_to_phase_3_ref": str(return_path),
            "phase_4_return_to_phase_3_sha256": _digest(return_path.read_bytes()),
            "phase_4_return_audit_ref": str(audit_path),
            "phase_4_return_audit_sha256": _digest(audit_path.read_bytes()),
            "phase_3_proposal_path": str(revised_proposal_path),
            "phase_3_proposal_sha256": _digest(revised_proposal_path.read_bytes()),
            "phase_3_proposal_producing_invocation_uuid": (
                f"30000000-0000-4000-8000-{next_attempt:012d}"
            ),
        }
    )
    revised_estimate["currentness"].update(
        {
            "phase_3_binding_attempt": next_attempt,
            "phase_3_proposal_sha256": _digest(revised_proposal_path.read_bytes()),
            "prior_phase_3_estimate_writeback_sha256": _digest(
                prior_estimate_path.read_bytes()
            ),
            "phase_4_return_to_phase_3_sha256": _digest(return_path.read_bytes()),
            "phase_4_return_audit_sha256": _digest(audit_path.read_bytes()),
        }
    )
    revised_verification_path: Path | None = None
    if revised_estimate["disposition"] == "write_verified":
        revised_verification_path = (
            Path(source_manifest["scratch_dir"])
            / "ticket-operations"
            / f"estimate-readback-attempt-{next_attempt}.json"
        )
        _write_json(
            revised_verification_path,
            {"status": "PASS", "estimate": 8, "attempt": next_attempt},
        )
        revised_estimate["write_verification_evidence"] = {
            "status": "PASS",
            "path": str(revised_verification_path),
            "sha256": _digest(revised_verification_path.read_bytes()),
        }
        revised_estimate["currentness"]["write_verification_sha256"] = _digest(
            revised_verification_path.read_bytes()
        )
    _write_json(revised_estimate_path, revised_estimate)

    artifacts = {
        "phase-0-ticket-snapshot": Path(revised_estimate["phase_0_ticket_snapshot_path"]),
        "phase-3-estimate-writeback": revised_estimate_path,
        "phase-3-proposal": revised_proposal_path,
        "phase-4-return-audit": audit_path,
        "phase-4-return-decision": return_path,
        "prior-phase-3-estimate-writeback": prior_estimate_path,
        "prior-phase-3-proposal": prior_proposal_path,
        "resolved-ticket-contract": Path(
            revised_estimate["resolved_operator_contract_path"]
        ),
        "resolved-ticket-operator": Path(revised_estimate["resolved_operator_path"]),
    }
    cold_start_ref = revised_estimate.get("cold_start_disposition_ref")
    if cold_start_ref is not None:
        artifacts["cold-start-disposition"] = Path(cold_start_ref)
    prior_verification = prior_estimate.get("write_verification_evidence")
    if isinstance(prior_verification, dict):
        artifacts["prior-write-verification-evidence"] = Path(
            prior_verification["path"]
        )
    if revised_verification_path is not None:
        artifacts["write-verification-evidence"] = revised_verification_path
    reresolve_readback = (
        Path(source_manifest["scratch_dir"])
        / "session-writes"
        / "phase0-reresolve.readback.json"
    )
    if reresolve_readback.is_file():
        artifacts["phase-0-reresolve-readback"] = reresolve_readback
    for entry in source_manifest.get("phase_3_revision_history", []):
        attempt = entry["attempt"]
        artifacts.update(
            {
                f"lineage-estimate-writeback-attempt-{attempt}": Path(
                    entry["estimate_writeback_ref"]
                ),
                f"lineage-phase-3-proposal-attempt-{attempt}": Path(
                    entry["phase_3_proposal_path"]
                ),
                f"lineage-return-audit-attempt-{attempt}": Path(
                    entry["return_to_phase_3_audit_ref"]
                ),
                f"lineage-return-decision-attempt-{attempt}": Path(
                    entry["return_to_phase_3_ref"]
                ),
            }
        )

    replacement_manifest = copy.deepcopy(source_manifest)
    replacement_manifest.update(
        {
            "phase_3_estimate_writeback_ref": str(revised_estimate_path),
            "phase_3_estimate_writeback_sha256": _digest(
                revised_estimate_path.read_bytes()
            ),
            "phase_3_binding_attempt": next_attempt,
            "phase_3_revision_history": source_manifest.get(
                "phase_3_revision_history", []
            )
            + [
                {
                    "attempt": current_attempt,
                    "estimate_writeback_ref": str(prior_estimate_path),
                    "estimate_writeback_sha256": _digest(
                        prior_estimate_path.read_bytes()
                    ),
                    "phase_3_proposal_path": str(prior_proposal_path),
                    "phase_3_proposal_sha256": _digest(
                        prior_proposal_path.read_bytes()
                    ),
                    "return_to_phase_3_ref": str(return_path),
                    "return_to_phase_3_sha256": _digest(return_path.read_bytes()),
                    "return_to_phase_3_audit_ref": str(audit_path),
                    "return_to_phase_3_audit_sha256": _digest(
                        audit_path.read_bytes()
                    ),
                }
            ],
            "phase_history": source_manifest["phase_history"]
            + [
                {
                    "attempt": next_attempt,
                    "phase": "3",
                    "status": "rebound",
                    "ts": f"2026-07-{19 + next_attempt:02d}T00:00:00Z",
                }
            ],
        }
    )
    replacement_index = json.loads(index_path.read_text())
    request_path = _write_runtime_request(
        case["request_dir"] / f"phase3-rebind-attempt-{next_attempt}.json",
        "phase3-rebind",
        case["planning_root"],
        manifest_path,
        index_path,
        replacement_manifest,
        replacement_index,
        None,
        artifacts,
    )
    return {
        **case,
        "operation": "phase3-rebind",
        "request_path": request_path,
        "replacement_manifest": replacement_manifest,
        "replacement_index": replacement_index,
        "artifacts": artifacts,
    }


def _rewrite_phase3_request(
    case: dict[str, Any],
    name: str,
    *,
    producer_role: str | None = None,
    producer_path: Path | None = None,
    producer_digest: str | None = None,
    repo_root: Path | None = None,
    branch_out_sha: str | None = None,
) -> Path:
    source_manifest = json.loads(case["manifest_path"].read_text())
    estimate_path = case["artifacts"]["phase-3-estimate-writeback"]
    estimate = json.loads(estimate_path.read_text())
    artifacts = dict(case["artifacts"])
    if producer_role is not None:
        fields = {
            "resolved-ticket-operator": (
                "resolved_operator_path",
                "resolved_operator_sha256",
            ),
            "resolved-ticket-contract": (
                "resolved_operator_contract_path",
                "resolved_contract_sha256",
            ),
        }
        path_key, digest_key = fields[producer_role]
        if producer_path is not None:
            source_manifest[path_key] = str(producer_path)
            estimate[path_key] = str(producer_path)
            artifacts[producer_role] = producer_path
            if producer_role == "resolved-ticket-contract":
                source_manifest["resolved_contract_path"] = str(producer_path)
        if producer_digest is not None:
            source_manifest[digest_key] = producer_digest
            estimate[digest_key] = producer_digest
            estimate["currentness"][digest_key] = producer_digest
    if repo_root is not None:
        source_manifest["repo_root"] = str(repo_root)
    if branch_out_sha is not None:
        source_manifest["branch_out_sha"] = branch_out_sha
    _write_json(case["manifest_path"], source_manifest)
    _write_json(estimate_path, estimate)
    replacement = copy.deepcopy(source_manifest)
    replacement.update(
        {
            "phase_3_estimate_writeback_ref": str(estimate_path),
            "phase_3_estimate_writeback_sha256": _digest(estimate_path.read_bytes()),
            "phase_history": source_manifest["phase_history"]
            + [case["replacement_manifest"]["phase_history"][-1]],
        }
    )
    return _write_runtime_request(
        case["request_path"].with_name(f"phase3-{name}.json"),
        "phase3-bind",
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        replacement,
        case["replacement_index"],
        None,
        artifacts,
    )


def _commit_fixture_repo(repo_root: Path, message: str) -> str:
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "-c",
            "user.name=Session Test",
            "-c",
            "user.email=session-test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            message,
        ],
        check=True,
        env=GIT_ENV,
    )
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
        env=GIT_ENV,
    ).stdout.strip()


def _production_runtime_manifest(planning_root: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path, manifest = _runtime_manifest(planning_root)
    scratch_dir = manifest_path.parent / ".scratch"
    manifest.update(
        {
            "session_id": "62df1deb-d32e-4de3-8007-41129d47cd54",
            "implementation_invocation_uuid": "62df1deb-d32e-4de3-8007-41129d47cd54",
            "auto_merge_after_phase_9": False,
            "cold_start_disposition_ref": None,
            "contract_resolution_path": str(scratch_dir / "phase0-contract-resolution.json"),
            "contract_resolution_producing_invocation_uuid": "654884b3-5ae9-4508-94e1-a142dffeacc8",
            "contract_resolution_sha256": "1" * 64,
            "estimate_capability_evidence": {
                "output_task": "update-estimate",
                "side_effect": "linear-update-estimate",
            },
            "estimate_field": "estimate",
            "estimate_mutation_policy": {
                "resolution": "legacy_capability",
                "source": "legacy_capability",
                "value": None,
            },
            "estimate_writeback_disposition": "update_estimate_required",
            "local_coverage_command": "coverage run -m pytest -q",
            "phase_3_estimate_writeback_ref": None,
            "phase_3_estimate_writeback_sha256": None,
            "phase_8_reviewed_artifact_path": None,
            "phase_8_reviewed_artifact_sha256": None,
            "phase_8_reviewed_base_sha": None,
            "phase_8_reviewed_head_sha": None,
            "phase_8_reviewed_is_draft": None,
            "phase_9_currentness_path": None,
            "phase_9_currentness_result": None,
            "phase_9_currentness_sha256": None,
            "predecessor_session_manifest_path": None,
            "resolved_contract_path": str(scratch_dir / "linear-operator.yaml"),
            "resolved_contract_sha256": "2" * 64,
            "resolved_defaults_source": {"linear_team_key": "caller"},
            "resolved_operator_contract_path": str(scratch_dir / "linear-operator.yaml"),
            "resolved_operator_path": str(scratch_dir / "linear-operator.md"),
            "resolved_operator_sha256": "3" * 64,
            "route_attempt_number": 1,
            "spawned_at": "2026-08-08T04:01:03.610682795Z",
            "ticket_snapshot_path": str(scratch_dir / "ticket.md"),
            "ticket_snapshot_producing_invocation_uuid": "cfeb1847-219b-4f0a-9a56-72cab7770e85",
            "ticket_snapshot_sha256": "4" * 64,
            "topology_revalidation_path": str(scratch_dir / "phase0-topology-revalidation.json"),
            "topology_revalidation_sha256": "5" * 64,
            "wu_brief_context_path": str(scratch_dir / "wu-brief-context.md"),
            "wu_brief_context_sha256": "6" * 64,
            "wu_brief_context_source_path": str(scratch_dir / "current-route-assessment.md"),
            "wu_brief_context_source_sha256": "6" * 64,
        }
    )
    return manifest_path, manifest


def _expected_active_row(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    return {
        "ticket_id": manifest["ticket_id"],
        "ticket_system": manifest["ticket_system"],
        "branch": manifest["branch"],
        "base_branch": manifest["base_branch"],
        "branch_out_sha": manifest["branch_out_sha"],
        "draft_pr_url": manifest["draft_pr_url"],
        "draft_pr_number": manifest["draft_pr_number"],
        "draft_pr_head_sha": manifest["draft_pr_head_sha"],
        "pr_open_base_sha": manifest["pr_open_base_sha"],
        "pre_merge_base_sha": manifest["pre_merge_base_sha"],
        "merge_sha": manifest["merge_sha"],
        "merged_at": manifest["merged_at"],
        "session_manifest_path": str(manifest_path),
        "worktree_path": manifest["worktree_path"],
        "planning_dir": manifest["planning_dir"],
    }


def _run_production_runtime_lifecycle(
    tmp_path: Path, *, reviewed_index: bool = False
) -> dict[str, Any]:
    planning_root = tmp_path / "project" / "planning"
    planning_root.mkdir(parents=True)
    manifest_path, initial_manifest = _production_runtime_manifest(planning_root)
    Path(initial_manifest["scratch_dir"]).mkdir()
    index_path = planning_root / "sessions.active-wake.json"
    source_index_path = planning_root / "sessions.index.json"
    initial_index: dict[str, Any] = {
        "schema": MIGRATION.ACTIVE_INDEX_SCHEMA,
        "sessions": [],
    }
    source_index_before: bytes | None = None
    if reviewed_index:
        _write_json(source_index_path, {"sessions": [{"historical": True}]})
        source_index_before = source_index_path.read_bytes()
        initial_index.update(
            {
                "reviewed_inventory_sha256": "7" * 64,
                "source_index_path": str(source_index_path),
            }
        )
        _write_json(index_path, initial_index)

    snapshots: dict[str, dict[str, Any]] = {}
    for operation in (
        "phase0-init",
        "phase7-upsert",
        "phase9-update",
        "resumer-update",
        "resumer-close",
    ):
        if operation == "phase0-init":
            replacement_manifest = copy.deepcopy(initial_manifest)
            replacement_index = copy.deepcopy(initial_index)
            row_identity = None
        else:
            replacement_manifest = json.loads(manifest_path.read_text())
            if operation == "phase7-upsert":
                replacement_manifest.update(
                    {
                        "draft_pr_url": "https://github.com/example/repo/pull/260",
                        "draft_pr_number": 260,
                        "draft_pr_head_sha": B,
                        "pr_open_base_sha": C,
                        "phase_history": ["phase7"],
                    }
                )
            elif operation == "phase9-update":
                replacement_manifest.update(
                    {
                        "phase_8_reviewed_is_draft": True,
                        "phase_8_reviewed_base_sha": C,
                        "phase_8_reviewed_head_sha": B,
                        "phase_8_reviewed_artifact_path": str(
                            manifest_path.parent / "phase-8-reviewed.json"
                        ),
                        "phase_8_reviewed_artifact_sha256": "8" * 64,
                        "phase_9_currentness_result": "PASS",
                        "phase_9_currentness_path": str(
                            manifest_path.parent / "phase-9-currentness.json"
                        ),
                        "phase_9_currentness_sha256": "9" * 64,
                        "phase_history": ["phase7", "phase9"],
                    }
                )
            elif operation == "resumer-update":
                replacement_manifest.update(
                    {
                        "pre_merge_base_sha": C,
                        "merge_sha": E,
                        "merged_at": "2026-08-08T05:00:00Z",
                        "phase_history": ["phase7", "phase9", "wake"],
                    }
                )
            else:
                replacement_manifest.update(
                    {
                        "closed_at": "2026-08-08T06:00:00Z",
                        "post_merge": {"tests": "PASS", "coverage": "PASS"},
                        "phase_history": ["phase7", "phase9", "wake", "closed"],
                    }
                )

            row = _expected_active_row(replacement_manifest, manifest_path)
            row_identity = _row_identity(row)
            replacement_index = json.loads(index_path.read_text())
            if operation == "phase7-upsert":
                replacement_index["sessions"] = [row]
            elif operation == "resumer-close":
                replacement_index["sessions"] = []
            else:
                replacement_index["sessions"] = [row]

        request_path = _write_runtime_request(
            tmp_path / "requests" / f"{operation}.json",
            operation,
            planning_root,
            manifest_path,
            index_path,
            replacement_manifest,
            replacement_index,
            row_identity,
        )
        MIGRATION.apply_runtime_request(request_path, operation)
        snapshots[operation] = {
            "manifest": json.loads(manifest_path.read_text()),
            "index": json.loads(index_path.read_text()),
        }

    return {
        "planning_root": planning_root,
        "manifest_path": manifest_path,
        "index_path": index_path,
        "source_index_path": source_index_path,
        "source_index_before": source_index_before,
        "initial_manifest": initial_manifest,
        "snapshots": snapshots,
    }


def _transaction_artifacts(paths: list[Path]) -> list[Path]:
    artifacts: list[Path] = []
    for path in paths:
        artifacts.extend(path.parent.glob(f".{path.name}.*.backup"))
        artifacts.extend(path.parent.glob(f".{path.name}.*.replacement"))
    return artifacts


def test_open_dry_run_is_deterministic_no_write_and_builds_seven_active_indexes(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    before = {path: path.read_bytes() for path in fixture["manifest_paths"] + fixture["index_paths"]}

    first = _plan(fixture, plan_path=fixture["plan_path"])
    second = _plan(fixture, plan_path=fixture["plan_path"])

    assert first == second
    assert first["eligible"] is True
    assert first["rows"][0]["verdict"] == "migrated-open"
    assert first["rows"][0]["pre_merge_base_sha"] is None
    assert len(first["active_index_paths"]) == 7
    assert {path: path.read_bytes() for path in before} == before
    assert not any(Path(path).exists() for path in first["active_index_paths"])


def test_apply_writes_canonical_manifest_and_active_index_but_preserves_source_index(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    _, manifest_path, _ = _target(fixture)
    source_indexes = {path: path.read_bytes() for path in fixture["index_paths"]}
    plan = _plan(fixture)

    apply_plan(_write_plan(fixture, plan))

    manifest = json.loads(manifest_path.read_text())
    active_path = fixture["index_paths"][0].with_name("sessions.active-wake.json")
    active = json.loads(active_path.read_text())
    assert active["schema"] == MIGRATION.ACTIVE_INDEX_SCHEMA
    row = next(item for item in active["sessions"] if item["session_manifest_path"] == str(manifest_path))
    assert row["draft_pr_head_sha"] == B
    assert manifest["pre_merge_base_sha"] is None
    assert manifest["session_manifest_path"] == str(manifest_path)
    assert not MIGRATION.RETIRED_KEYS & set(manifest)
    assert {path: path.read_bytes() for path in source_indexes} == source_indexes
    assert not MIGRATION._journal_path().exists()


def test_active_indexes_exclude_history_placeholders_and_accepted_breakage(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    plan = _plan(fixture)
    apply_plan(_write_plan(fixture, plan))

    active_rows = []
    for source in fixture["index_paths"]:
        active = json.loads(source.with_name("sessions.active-wake.json").read_text())
        active_rows.extend(active["sessions"])
    assert len(active_rows) == 39
    assert all(row["ticket_id"] is not None for row in active_rows)
    assert all("history-row" not in row["branch"] for row in active_rows)
    assert all(Path(row["session_manifest_path"]).name == "session.json" for row in active_rows)


@pytest.mark.parametrize(
    ("state", "merge_sha", "merged_at", "merge_capture"),
    [
        ("OPEN", E, None, None),
        ("CLOSED", None, "2026-07-18T12:00:00Z", None),
        ("OPEN", None, None, _capture(["git", "show"], f"{E} {C}")),
    ],
)
def test_unmerged_state_rejects_any_merge_evidence(
    tmp_path: Path,
    state: str,
    merge_sha: str | None,
    merged_at: str | None,
    merge_capture: dict[str, object] | None,
):
    fixture = _complete_fixture(tmp_path)
    candidate, _, _ = _target(fixture)
    record = fixture["evidence"]["prs"][candidate["pr_url"]]
    payload = record["provider"]["payload"]
    payload["state"] = state
    payload["mergeCommit"] = {"oid": merge_sha} if merge_sha else None
    payload["mergedAt"] = merged_at
    record["provider"]["payload_sha256"] = _digest(_canonical_bytes(payload))
    record["merge_commit"] = merge_capture
    _persist(fixture)

    plan = _plan(fixture)

    assert plan["eligible"] is False
    assert plan["rows"][0]["reason"] == "contradictory-pr-state-evidence"


@pytest.mark.parametrize(
    ("parents", "head", "merge_sha", "merge_method", "reason"),
    [
        ([C, B], B, E, None, None),
        ([C], B, E, "SQUASH", None),
        ([C], B, E, None, "missing-or-malformed-merge-method-capture"),
        ([C], B, E, "REBASE", "ambiguous-pre-merge-base"),
        ([C], B, E, "MERGE", "ambiguous-pre-merge-base"),
        ([C], E, E, "SQUASH", "ambiguous-pre-merge-base"),
        ([C, D, B], B, E, None, "ambiguous-pre-merge-base"),
        ([C, D], B, E, None, "ambiguous-pre-merge-base"),
    ],
)
def test_merged_state_accepts_only_evidence_backed_merge_or_squash_shape(
    tmp_path: Path,
    parents: list[str],
    head: str,
    merge_sha: str,
    merge_method: str | None,
    reason: str | None,
):
    fixture = _complete_fixture(tmp_path)
    candidate, path, manifest = _target(fixture)
    candidate["classification"] = "merged but wake incomplete"
    candidate["merge_sha"] = merge_sha
    manifest["merge_sha"] = merge_sha
    _refresh_manifest_inventory(fixture, path)
    fixture["evidence"]["prs"][candidate["pr_url"]] = _evidence(
        candidate["pr_url"], candidate["branch"], candidate["persisted_or_derived_base_branch"],
        state="MERGED",
        head=head,
        merge_sha=merge_sha,
        merged_at="2026-07-18T12:00:00Z",
        parents=parents,
        merge_method=merge_method,
        branch_out=(A, A, path.parents[2]),
    )
    _persist(fixture)

    plan = _plan(fixture)

    if reason:
        assert plan["eligible"] is False
        assert plan["rows"][0]["reason"] == reason
    else:
        assert plan["rows"][0]["verdict"] == "migrated-merged"
        assert plan["rows"][0]["pre_merge_base_sha"] == C


def test_persisted_pre_merge_baseline_conflict_is_refused(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    candidate, path, manifest = _target(fixture, 36)
    candidate["persisted_or_derived_pre_merge_base_sha"] = D
    manifest["pre_merge_base_sha"] = D
    _refresh_manifest_inventory(fixture, path)
    _persist(fixture)

    plan = _plan(fixture)

    row = next(item for item in plan["rows"] if item["manifest_path"] == str(path))
    assert row["reason"] == "persisted-pre-merge-base-conflict"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("extra", "missing-or-malformed-merge-method-capture"),
        ("digest", "merge-method-capture-digest-mismatch"),
        ("source", "unsupported-merge-method-capture-source"),
    ],
)
def test_one_parent_merge_method_capture_is_closed_and_hash_bound(
    mutation: str, reason: str, tmp_path: Path
):
    fixture = _complete_fixture(tmp_path)
    candidate, path, manifest = _target(fixture)
    candidate["classification"] = "merged but wake incomplete"
    candidate["merge_sha"] = E
    manifest["merge_sha"] = E
    _refresh_manifest_inventory(fixture, path)
    record = _evidence(
        candidate["pr_url"],
        candidate["branch"],
        candidate["persisted_or_derived_base_branch"],
        state="MERGED",
        merge_sha=E,
        merged_at="2026-07-18T12:00:00Z",
        parents=[C],
        merge_method="SQUASH",
        branch_out=(A, A, path.parents[2]),
    )
    capture = record["merge_method"]
    assert isinstance(capture, dict)
    if mutation == "extra":
        capture["extra"] = True
    elif mutation == "digest":
        capture["payload"]["message"] = "tampered"
    else:
        capture["source"] = "local-topology-inference"
    fixture["evidence"]["prs"][candidate["pr_url"]] = record
    _persist(fixture)

    assert _plan(fixture)["rows"][0]["reason"] == reason


def test_abbreviated_branch_out_requires_hash_bound_repository_resolution(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    candidate, path, manifest = _target(fixture)
    candidate["branch_out_sha"] = "aaaaaaa"
    manifest["branch_out_sha"] = "aaaaaaa"
    _refresh_manifest_inventory(fixture, path)
    _persist(fixture)
    refused = _plan(fixture)
    assert refused["rows"][0]["reason"] == "branch-out-requires-trusted-repository-resolution"

    record = fixture["evidence"]["prs"][candidate["pr_url"]]
    record["branch_out"] = _capture(
        ["git", "-C", str(path.parents[2]), "rev-parse", "--verify", "aaaaaaa^{commit}"],
        {"repository": str(path.parents[2]), "requested_oid": "aaaaaaa", "resolved_oid": A},
    )
    _persist(fixture)
    accepted = _plan(fixture)
    assert accepted["rows"][0]["verdict"] == "migrated-open"


def test_exact_locator_head_conflict_refuses_even_with_accepted_breakage(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    candidate, _, _ = _target(fixture)
    locator = candidate["existing_index_rows"][0]
    key = (locator["index_path"], locator["row_locator"])
    index = int(key[1].removeprefix("sessions[").removesuffix("]"))
    fixture["index_documents"][Path(key[0])]["sessions"][index]["draft_pr_head_sha"] = D
    _refresh_index_inventory(fixture, key)
    candidate["explicit_refusal_reasons"] = ["head conflict"]
    fixture["dispositions"]["dispositions"].append(
        {
            "manifest_path": candidate["manifest_path"],
            "reason": "Accepted loss is not a conflict resolution.",
            "accepted_breakage": True,
            "owner": "manager",
        }
    )
    # Preserve the reviewed aggregate of three explicit refusals by moving one old refusal out.
    old = fixture["cohort"][39]
    old["explicit_refusal_reasons"] = []
    old["later_trusted_pr_query_requirements"] = ["trusted provider status"]
    fixture["dispositions"]["dispositions"] = [
        row for row in fixture["dispositions"]["dispositions"] if row["manifest_path"] != old["manifest_path"]
    ]
    fixture["evidence"]["prs"][old["pr_url"]] = _evidence(
        old["pr_url"], old["branch"], f"base-{39:03d}"
    )
    _persist(fixture)

    plan = _plan(fixture)

    assert plan["rows"][0]["verdict"] == "refused"
    assert "source-identity-conflict" in plan["rows"][0]["reason"]


def test_manager_conflict_resolution_must_hash_discarded_row_and_retained_identity(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    candidate, _, _ = _target(fixture)
    locator = candidate["existing_index_rows"][0]
    key = (locator["index_path"], locator["row_locator"])
    position = int(key[1].removeprefix("sessions[").removesuffix("]"))
    source_row = fixture["index_documents"][Path(key[0])]["sessions"][position]
    source_row["draft_pr_head_sha"] = D
    _refresh_index_inventory(fixture, key)
    fixture["resolutions"]["resolutions"] = [
        {
            "index_path": key[0],
            "row_locator": key[1],
            "owner": "manager",
            "conflict_resolution": True,
            "reason": "Retain manifest/provider attempt after independent review.",
            "discarded_row_sha256": _digest(_canonical_bytes(source_row)),
            "retained_identity": {
                "manifest_path": candidate["manifest_path"],
                "ticket_id": candidate["ticket_id"],
                "ticket_system": candidate["ticket_system"],
                "branch": candidate["branch"],
                "pr_url": candidate["pr_url"],
                "head_sha": candidate["persisted_head_sha"],
                "base_branch": candidate["persisted_or_derived_base_branch"],
            },
        }
    ]
    _persist(fixture)

    plan = _plan(fixture)

    assert plan["rows"][0]["verdict"] == "migrated-open"


@pytest.mark.parametrize("mutation", ["truncate-manifests", "add-cohort", "bad-count", "duplicate-locator"])
def test_complete_inventory_reconciliation_rejects_truncation_additions_and_duplicates(
    tmp_path: Path, mutation: str
):
    fixture = _complete_fixture(tmp_path)
    inventory = fixture["inventory"]
    if mutation == "truncate-manifests":
        inventory["manifests"].pop()
    elif mutation == "add-cohort":
        inventory["migration_cohort"].append(dict(inventory["migration_cohort"][0]))
    elif mutation == "bad-count":
        inventory["counts"]["index_rows"] = 151
    else:
        inventory["index_rows"][1]["index_path"] = inventory["index_rows"][0]["index_path"]
        inventory["index_rows"][1]["row_locator"] = inventory["index_rows"][0]["row_locator"]
    _write_json(fixture["inventory_path"], inventory)
    digest = _digest(fixture["inventory_path"].read_bytes())

    with pytest.raises(InputError):
        build_plan(
            fixture["inventory_path"], fixture["evidence_path"], fixture["dispositions_path"],
            digest, fixture["resolutions_path"], fixture["plan_path"]
        )


def test_reviewed_inventory_digest_is_mandatory_and_exact(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    with pytest.raises(InputError, match="reviewed inventory SHA-256 mismatch"):
        build_plan(
            fixture["inventory_path"], fixture["evidence_path"], fixture["dispositions_path"],
            "0" * 64, fixture["resolutions_path"], fixture["plan_path"]
        )


@pytest.mark.parametrize("collision", ["manifest", "index", "inventory", "inside-planning"])
def test_plan_destination_rejects_source_aliases_and_managed_tree(collision: str, tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    if collision == "manifest":
        plan_path = fixture["manifest_paths"][0]
    elif collision == "index":
        plan_path = fixture["index_paths"][0]
    elif collision == "inventory":
        plan_path = fixture["inventory_path"]
    else:
        plan_path = fixture["index_paths"][0].parent / "scratch" / "plan.json"
        plan_path.parent.mkdir()
    with pytest.raises(InputError):
        _plan(fixture, plan_path=plan_path)


def test_plan_destination_rejects_existing_inode_alias(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    alias = tmp_path / "plan-hardlink.json"
    os.link(fixture["inventory_path"], alias)
    with pytest.raises(InputError, match="inode aliases"):
        _plan(fixture, plan_path=alias)


def test_symlink_source_and_path_escape_are_refused(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    source = fixture["manifest_paths"][0]
    real = source.with_name("real-session.json")
    source.rename(real)
    source.symlink_to(real)
    with pytest.raises(InputError, match="symlink"):
        _plan(fixture)

    fixture = _complete_fixture(tmp_path / "escape-case")
    fixture["inventory"]["migration_cohort"][0]["manifest_path"] = str(tmp_path / "outside" / "session.json")
    _write_json(fixture["inventory_path"], fixture["inventory"])
    fixture["reviewed_digest"] = _digest(fixture["inventory_path"].read_bytes())
    with pytest.raises(InputError, match="does not reconcile"):
        _plan(fixture)


def test_duplicate_inode_alias_is_refused(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    first, second = fixture["manifest_paths"][:2]
    second.unlink()
    os.link(first, second)
    with pytest.raises(InputError, match="device/inode"):
        _plan(fixture)


def test_second_identity_check_prevents_overwriting_concurrent_writer(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    plan = _plan(fixture)
    source_write = next(write for write in plan["writes"] if write["source_exists"])
    path = Path(source_write["path"])
    concurrent = b'{"concurrent": true}\n'

    def race(point: str, index: int) -> None:
        if point == "stage" and index == 1:
            path.write_bytes(concurrent)

    setattr(MIGRATION, "FAULT_HOOK", race)
    with pytest.raises(ApplyError, match="stale source identity"):
        apply_plan(_write_plan(fixture, plan))
    assert path.read_bytes() == concurrent
    assert not MIGRATION._journal_path().exists()


def test_post_journal_source_mutation_is_preserved_and_never_replaced(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase9-update")
    path = case["manifest_path"]
    concurrent = b'{"post_journal": true}\n'

    def race(point: str, index: int) -> None:
        if (point, index) == ("journal-transition", 0):
            path.write_bytes(concurrent)

    setattr(MIGRATION, "FAULT_HOOK", race)
    with pytest.raises(ApplyError, match="recovery remains pending"):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])

    assert path.read_bytes() == concurrent
    assert MIGRATION._journal_path().exists()


def test_later_pre_replacement_mutation_rolls_back_earlier_target_and_is_preserved(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase9-update")
    manifest_before = case["manifest_path"].read_bytes()
    index_path = case["index_path"]
    concurrent = b'{"later_target": true}\n'

    def race(point: str, index: int) -> None:
        if (point, index) == ("replacement", 1):
            index_path.write_bytes(concurrent)

    setattr(MIGRATION, "FAULT_HOOK", race)
    with pytest.raises(ApplyError, match="recovery remains pending"):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])

    assert case["manifest_path"].read_bytes() == manifest_before
    assert index_path.read_bytes() == concurrent
    assert MIGRATION._journal_path().exists()


@pytest.mark.parametrize(
    ("point", "index"),
    [
        ("stage", 0),
        ("stage", 1),
        ("replace", 0),
        ("replace", 1),
        ("directory-fsync", 0),
        ("directory-fsync", 1),
        ("journal", 0),
        ("journal", 1),
    ],
)
def test_fault_injection_rolls_back_every_target(point: str, index: int, tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    plan = _plan(fixture)
    before = {
        Path(write["path"]): Path(write["path"]).read_bytes() if Path(write["path"]).exists() else None
        for write in plan["writes"]
    }

    def fail(actual_point: str, actual_index: int) -> None:
        if (actual_point, actual_index) == (point, index):
            raise OSError(f"fault {point}:{index}")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError):
        apply_plan(_write_plan(fixture, plan))
    for path, original in before.items():
        assert path.read_bytes() == original if original is not None else not path.exists()


def test_rollback_failure_is_aggregated_and_later_recovery_completes(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    plan = _plan(fixture)
    plan_path = _write_plan(fixture, plan)
    original = Path(plan["writes"][0]["path"]).read_bytes()

    def fail(point: str, index: int) -> None:
        if (point, index) in {("directory-fsync", 1), ("rollback", 0)}:
            raise OSError(f"fault {point}:{index}")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError, match="recovery remains pending"):
        apply_plan(plan_path)
    assert MIGRATION._journal_path().exists()

    setattr(MIGRATION, "FAULT_HOOK", None)
    MIGRATION.recover_incomplete_transaction()
    assert Path(plan["writes"][0]["path"]).read_bytes() == original
    assert not MIGRATION._journal_path().exists()


def test_subprocess_interruption_is_recovered_before_next_apply(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    plan = _plan(fixture)
    plan_path = _write_plan(fixture, plan)
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "directory-fsync:0"
    command = [sys.executable, str(TOOL_DIR), "apply", "--plan", str(plan_path)]

    interrupted = subprocess.run(command, env=env, text=True, capture_output=True)
    assert interrupted.returncode == 97
    assert MIGRATION._journal_path().exists()

    env.pop("WU_SESSION_MIGRATION_INTERRUPT")
    dry_run_command = [
        sys.executable,
        str(TOOL_DIR),
        "dry-run",
        "--inventory",
        str(fixture["inventory_path"]),
        "--reviewed-inventory-sha256",
        fixture["reviewed_digest"],
        "--pr-evidence",
        str(fixture["evidence_path"]),
        "--dispositions",
        str(fixture["dispositions_path"]),
        "--conflict-resolutions",
        str(fixture["resolutions_path"]),
        "--plan",
        str(plan_path),
    ]
    recovered = subprocess.run(dry_run_command, env=env, text=True, capture_output=True)
    assert recovered.returncode == 0, recovered.stderr
    applied = subprocess.run(command, env=env, text=True, capture_output=True)
    assert applied.returncode == 0, applied.stderr
    assert not MIGRATION._journal_path().exists()
    assert all(Path(path).exists() for path in plan["active_index_paths"])


def test_multi_parent_recovery_rolls_back_reachable_target_before_later_completion(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase9-update")
    paths = [case["manifest_path"], case["index_path"]]
    before = {path: path.read_bytes() for path in paths}
    command = [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(case["request_path"])]
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "journal-transition:2"

    interrupted = subprocess.run(command, env=env, text=True, capture_output=True)
    assert interrupted.returncode == 97
    assert case["manifest_path"].read_bytes() == _json_bytes(case["replacement_manifest"])
    assert case["index_path"].read_bytes() == _json_bytes(case["replacement_index"])

    parent = case["manifest_path"].parent
    unavailable_parent = parent.with_name(f"{parent.name}-unavailable")
    parent.rename(unavailable_parent)
    env.pop("WU_SESSION_MIGRATION_INTERRUPT")
    try:
        recovered = subprocess.run(command, env=env, text=True, capture_output=True)

        assert recovered.returncode == 3
        assert "Traceback" not in recovered.stderr
        assert str(case["manifest_path"]) in recovered.stderr
        assert (unavailable_parent / "session.json").read_bytes() == _json_bytes(
            case["replacement_manifest"]
        )
        assert case["index_path"].read_bytes() == before[case["index_path"]]
        assert MIGRATION._journal_path().exists()
    finally:
        unavailable_parent.rename(parent)

    completed = subprocess.run(command, env=env, text=True, capture_output=True)
    assert completed.returncode == 3
    assert "Traceback" not in completed.stderr
    assert {path: path.read_bytes() for path in paths} == before
    assert not MIGRATION._journal_path().exists()


def test_cli_exit_classes_and_plan_output_io_are_concise(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    malformed = tmp_path / "malformed-plan.json"
    malformed.write_text("{", encoding="utf-8")
    assert MIGRATION.main(["apply", "--plan", str(malformed)]) == 2
    assert "Traceback" not in capsys.readouterr().err

    fixture = _complete_fixture(tmp_path / "fixture")
    bad_output = tmp_path / "missing-parent" / "plan.json"
    code = MIGRATION.main(
        [
            "dry-run", "--inventory", str(fixture["inventory_path"]),
            "--reviewed-inventory-sha256", fixture["reviewed_digest"],
            "--pr-evidence", str(fixture["evidence_path"]),
            "--dispositions", str(fixture["dispositions_path"]),
            "--conflict-resolutions", str(fixture["resolutions_path"]),
            "--plan", str(bad_output),
        ]
    )
    assert code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_cli_returns_one_for_refusal_and_three_for_stale_apply(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    candidate, manifest_path, _ = _target(fixture)
    del fixture["evidence"]["prs"][candidate["pr_url"]]
    _persist(fixture)
    args = [
        "dry-run", "--inventory", str(fixture["inventory_path"]),
        "--reviewed-inventory-sha256", fixture["reviewed_digest"],
        "--pr-evidence", str(fixture["evidence_path"]),
        "--dispositions", str(fixture["dispositions_path"]),
        "--conflict-resolutions", str(fixture["resolutions_path"]),
        "--plan", str(fixture["plan_path"]),
    ]
    assert MIGRATION.main(args) == 1

    fixture = _complete_fixture(tmp_path / "stale")
    plan = _plan(fixture)
    _write_plan(fixture, plan)
    manifest_path = Path(fixture["cohort"][0]["manifest_path"])
    manifest_path.write_text("{}\n", encoding="utf-8")
    assert MIGRATION.main(["apply", "--plan", str(fixture["plan_path"])]) == 3


def test_dry_run_recomputes_raw_capture_digest_and_command(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    candidate, _, _ = _target(fixture)
    record = fixture["evidence"]["prs"][candidate["pr_url"]]
    record["provider"]["payload"]["headRefOid"] = D
    _persist(fixture)
    digest_refusal = _plan(fixture)
    assert digest_refusal["rows"][0]["reason"] == "provider-capture-digest-mismatch"

    fixture = _complete_fixture(tmp_path / "command")
    candidate, _, _ = _target(fixture)
    record = fixture["evidence"]["prs"][candidate["pr_url"]]
    record["provider"]["command"] = ["printf", "fake"]
    _persist(fixture)
    command_refusal = _plan(fixture)
    assert command_refusal["rows"][0]["reason"] == "provider-capture-command-mismatch"

    fixture = _complete_fixture(tmp_path / "selector")
    candidate, _, _ = _target(fixture)
    record = fixture["evidence"]["prs"][candidate["pr_url"]]
    record["provider"]["command"][4] = "url,state,headRefName"
    _persist(fixture)
    selector_refusal = _plan(fixture)
    assert selector_refusal["rows"][0]["reason"] == "provider-capture-command-mismatch"


def test_raw_merged_state_and_full_branch_out_resolution_are_required(tmp_path: Path):
    fixture = _complete_fixture(tmp_path)
    candidate, _, _ = _target(fixture, 36)
    record = fixture["evidence"]["prs"][candidate["pr_url"]]
    assert record["provider"]["payload"]["state"] == "MERGED"
    accepted = next(
        row for row in _plan(fixture)["rows"] if row["manifest_path"] == candidate["manifest_path"]
    )
    assert accepted["verdict"] == "migrated-merged"

    record["branch_out"] = None
    _persist(fixture)
    refused = _plan(fixture)
    row = next(item for item in refused["rows"] if item["manifest_path"] == candidate["manifest_path"])
    assert row["reason"] == "branch-out-requires-trusted-repository-resolution"


def test_capture_evidence_guards_dynamic_git_oid_operands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixture = _complete_fixture(tmp_path)
    merged_candidate = fixture["cohort"][0]
    commands: list[list[str]] = []

    def provider(command: list[str]) -> dict[str, Any]:
        candidate = next(
            row for row in fixture["cohort"] if row["pr_url"] == command[-1]
        )
        merged = candidate is merged_candidate
        return {
            "url": candidate["pr_url"],
            "state": "MERGED" if merged else "OPEN",
            "headRefName": candidate["branch"],
            "headRefOid": B,
            "baseRefName": candidate["persisted_or_derived_base_branch"]
            or "provider-base",
            "baseRefOid": C,
            "mergeCommit": {"oid": E} if merged else None,
            "mergedAt": "2026-07-18T12:00:00Z" if merged else None,
        }

    def git(command: list[str]) -> str:
        commands.append(command)
        if "show" in command:
            return f"{E} {C} {B}\n"
        return f"{A}\n"

    monkeypatch.setattr(MIGRATION, "_run_json_command", provider)
    monkeypatch.setattr(MIGRATION, "_run_text_command", git)
    output_path = tmp_path / "captured-evidence.json"

    MIGRATION.capture_evidence(
        fixture["inventory_path"], fixture["reviewed_digest"], output_path
    )

    assert output_path.is_file()
    assert any("show" in command for command in commands)
    assert all(command[-2] == "--end-of-options" for command in commands)


@pytest.mark.parametrize("malformed_source", ["merge", "branch-out"])
def test_capture_evidence_rejects_malformed_git_oid_before_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformed_source: str,
):
    fixture = _complete_fixture(tmp_path)
    target = fixture["cohort"][0]
    if malformed_source == "branch-out":
        target["branch_out_sha"] = "--help"
        _persist(fixture)

    def provider(command: list[str]) -> dict[str, Any]:
        candidate = next(
            row for row in fixture["cohort"] if row["pr_url"] == command[-1]
        )
        malformed_merge = malformed_source == "merge" and candidate is target
        return {
            "url": candidate["pr_url"],
            "state": "MERGED" if malformed_merge else "OPEN",
            "headRefName": candidate["branch"],
            "headRefOid": B,
            "baseRefName": candidate["persisted_or_derived_base_branch"]
            or "provider-base",
            "baseRefOid": C,
            "mergeCommit": {"oid": "--help"} if malformed_merge else None,
            "mergedAt": "2026-07-18T12:00:00Z" if malformed_merge else None,
        }

    def unexpected_git(_: list[str]) -> str:
        raise AssertionError("malformed OID reached Git")

    monkeypatch.setattr(MIGRATION, "_run_json_command", provider)
    monkeypatch.setattr(MIGRATION, "_run_text_command", unexpected_git)

    with pytest.raises(InputError, match="invalid dynamic Git"):
        MIGRATION.capture_evidence(
            fixture["inventory_path"],
            fixture["reviewed_digest"],
            tmp_path / "rejected-evidence.json",
        )


def test_phase3_bind_maps_canonical_snapshot_keys_and_preserves_source_and_index(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase3-bind")
    source_manifest = json.loads(case["manifest_path"].read_text())
    estimate = json.loads(
        case["artifacts"]["phase-3-estimate-writeback"].read_text()
    )
    original_index_bytes = case["index_path"].read_bytes()
    original_index_stat = case["index_path"].stat()
    manifest_snapshot_aliases = {
        "phase_0_ticket_snapshot_path",
        "phase_0_ticket_snapshot_sha256",
        "phase_0_ticket_snapshot_producing_invocation_uuid",
    }
    estimate_snapshot_aliases = {
        "ticket_snapshot_path",
        "ticket_snapshot_sha256",
        "ticket_snapshot_producing_invocation_uuid",
    }

    assert manifest_snapshot_aliases.isdisjoint(source_manifest)
    assert estimate_snapshot_aliases.isdisjoint(estimate)
    assert source_manifest["ticket_snapshot_path"] == estimate[
        "phase_0_ticket_snapshot_path"
    ]
    assert source_manifest["ticket_snapshot_sha256"] == estimate[
        "phase_0_ticket_snapshot_sha256"
    ]
    assert source_manifest["ticket_snapshot_producing_invocation_uuid"] != estimate[
        "phase_0_ticket_snapshot_producing_invocation_uuid"
    ]

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL_DIR),
            "phase3-bind",
            "--request",
            str(case["request_path"]),
        ],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    updated_manifest = json.loads(case["manifest_path"].read_text())
    changed_fields = {
        key
        for key in set(source_manifest) | set(updated_manifest)
        if source_manifest.get(key) != updated_manifest.get(key)
    }
    assert changed_fields == {
        "phase_3_estimate_writeback_ref",
        "phase_3_estimate_writeback_sha256",
        "phase_history",
    }
    assert updated_manifest == case["replacement_manifest"]
    assert manifest_snapshot_aliases.isdisjoint(updated_manifest)
    assert updated_manifest["ticket_snapshot_producing_invocation_uuid"] == source_manifest[
        "ticket_snapshot_producing_invocation_uuid"
    ]
    assert updated_manifest["cold_start_disposition_ref"] == source_manifest[
        "cold_start_disposition_ref"
    ]
    assert updated_manifest["phase_history"] == source_manifest["phase_history"] + [
        {"phase": "3", "status": "complete", "ts": "2026-07-19T00:00:00Z"}
    ]
    assert all(
        updated_manifest[key] == value
        for key, value in source_manifest.items()
        if key not in changed_fields
    )
    assert case["index_path"].read_bytes() == original_index_bytes
    updated_index_stat = case["index_path"].stat()
    assert (updated_index_stat.st_dev, updated_index_stat.st_ino, updated_index_stat.st_mode) == (
        original_index_stat.st_dev,
        original_index_stat.st_ino,
        original_index_stat.st_mode,
    )
    assert not MIGRATION._journal_path().exists()

    readback_path = tmp_path / "phase3-bind.readback.json"
    _write_json(readback_path, _pre_pr_readback(case, source_manifest))
    assert MIGRATION.validate_pre_pr_readback(readback_path) is None


@pytest.mark.parametrize(
    ("mismatch", "expected_field"),
    [("path", "ticket_snapshot_path"), ("digest", "ticket_snapshot_sha256")],
)
def test_phase3_bind_rejects_manifest_snapshot_identity_mismatch(
    mismatch: str, expected_field: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase3-bind")
    source_manifest = json.loads(case["manifest_path"].read_text())
    if mismatch == "path":
        source_manifest["ticket_snapshot_path"] = str(
            Path(source_manifest["scratch_dir"]) / "other-ticket.md"
        )
    else:
        source_manifest["ticket_snapshot_sha256"] = "0" * 64
    _write_json(case["manifest_path"], source_manifest)
    replacement = copy.deepcopy(source_manifest)
    replacement.update(
        {
            "phase_3_estimate_writeback_ref": case["replacement_manifest"][
                "phase_3_estimate_writeback_ref"
            ],
            "phase_3_estimate_writeback_sha256": case["replacement_manifest"][
                "phase_3_estimate_writeback_sha256"
            ],
            "phase_history": case["replacement_manifest"]["phase_history"],
        }
    )
    request_path = _write_runtime_request(
        tmp_path / "requests" / f"phase3-snapshot-{mismatch}-mismatch.json",
        "phase3-bind",
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        replacement,
        case["replacement_index"],
        None,
        case["artifacts"],
    )
    original_manifest_bytes = case["manifest_path"].read_bytes()
    original_index_bytes = case["index_path"].read_bytes()
    original_index_stat = case["index_path"].stat()
    assert not MIGRATION._journal_path().exists()

    with pytest.raises(
        InputError,
        match=rf"does not match manifest {expected_field}",
    ):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")

    assert case["manifest_path"].read_bytes() == original_manifest_bytes
    assert case["index_path"].read_bytes() == original_index_bytes
    updated_index_stat = case["index_path"].stat()
    assert (updated_index_stat.st_dev, updated_index_stat.st_ino, updated_index_stat.st_mode) == (
        original_index_stat.st_dev,
        original_index_stat.st_ino,
        original_index_stat.st_mode,
    )
    assert not MIGRATION._journal_path().exists()


def _pre_pr_readback(case: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    request_path = case["request_path"]
    request = json.loads(request_path.read_text())
    manifest_path = case["manifest_path"]
    index_path = case["index_path"]
    current_manifest = json.loads(manifest_path.read_text())
    return {
        "schema": MIGRATION.PRE_PR_READBACK_SCHEMA,
        "operation": case["operation"],
        "request_path": str(request_path),
        "request_sha256": _digest(request_path.read_bytes()),
        "source_manifest": source_manifest,
        "manifest_identity": MIGRATION.runtime_source_identity(manifest_path),
        "changed_keys": sorted(
            key
            for key in set(source_manifest) | set(current_manifest)
            if source_manifest.get(key) != current_manifest.get(key)
        ),
        "artifact_identities": [
            {**record, **MIGRATION.runtime_source_identity(Path(record["path"]))}
            for record in request["sources"]["artifacts"]
        ],
        "active_index_identity": MIGRATION.runtime_source_identity(index_path),
        "active_index_rows": json.loads(index_path.read_text())["sessions"],
        "synthesized_row": False,
        "journal_retained": False,
        "verdict": "PASS",
    }


def test_phase3_rebind_attempt_one_to_two_changes_exact_keys_and_passes_readback(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase3-rebind")
    source_manifest = json.loads(case["manifest_path"].read_text())
    index_bytes = case["index_path"].read_bytes()
    index_stat = case["index_path"].stat()
    retained_paths = [
        case["artifacts"][role]
        for role in (
            "prior-phase-3-estimate-writeback",
            "prior-phase-3-proposal",
            "phase-4-return-decision",
            "phase-4-return-audit",
        )
    ]
    retained_before = {
        path: (path.read_bytes(), path.stat().st_ino) for path in retained_paths
    }
    extra_phase4 = case["manifest_path"].parent / "risk" / "retained-phase-4-row.md"
    extra_phase4.write_text("PHASE4_ROW: HIGH\n")
    extra_before = (extra_phase4.read_bytes(), extra_phase4.stat().st_ino)

    MIGRATION.apply_runtime_request(case["request_path"], case["operation"])

    current = json.loads(case["manifest_path"].read_text())
    changed = {
        key
        for key in set(source_manifest) | set(current)
        if source_manifest.get(key) != current.get(key)
    }
    assert changed == MIGRATION.RUNTIME_ALLOWED_MANIFEST_CHANGES["phase3-rebind"]
    assert current["phase_3_binding_attempt"] == 2
    assert current["phase_3_revision_history"] == [
        {
            "attempt": 1,
            "estimate_writeback_ref": str(
                case["artifacts"]["prior-phase-3-estimate-writeback"]
            ),
            "estimate_writeback_sha256": _digest(
                case["artifacts"]["prior-phase-3-estimate-writeback"].read_bytes()
            ),
            "phase_3_proposal_path": str(
                case["artifacts"]["prior-phase-3-proposal"]
            ),
            "phase_3_proposal_sha256": _digest(
                case["artifacts"]["prior-phase-3-proposal"].read_bytes()
            ),
            "return_to_phase_3_ref": str(
                case["artifacts"]["phase-4-return-decision"]
            ),
            "return_to_phase_3_sha256": _digest(
                case["artifacts"]["phase-4-return-decision"].read_bytes()
            ),
            "return_to_phase_3_audit_ref": str(
                case["artifacts"]["phase-4-return-audit"]
            ),
            "return_to_phase_3_audit_sha256": _digest(
                case["artifacts"]["phase-4-return-audit"].read_bytes()
            ),
        }
    ]
    assert all(
        current[key] == value
        for key, value in source_manifest.items()
        if key not in changed
    )
    assert {
        path: (path.read_bytes(), path.stat().st_ino) for path in retained_paths
    } == retained_before
    assert (extra_phase4.read_bytes(), extra_phase4.stat().st_ino) == extra_before
    assert case["index_path"].read_bytes() == index_bytes
    current_index_stat = case["index_path"].stat()
    assert (
        current_index_stat.st_dev,
        current_index_stat.st_ino,
        current_index_stat.st_mode,
    ) == (index_stat.st_dev, index_stat.st_ino, index_stat.st_mode)
    readback_path = tmp_path / "phase3-rebind-attempt-2.readback.json"
    _write_json(readback_path, _pre_pr_readback(case, source_manifest))
    MIGRATION.validate_pre_pr_readback(readback_path)
    assert not MIGRATION._journal_path().exists()


def test_phase3_rebind_attempt_two_to_three_preserves_lineage_and_enforces_cap(
    tmp_path: Path,
):
    attempt_two = _runtime_case(tmp_path, "phase3-rebind")
    source_one = json.loads(attempt_two["manifest_path"].read_text())
    MIGRATION.apply_runtime_request(attempt_two["request_path"], "phase3-rebind")
    attempt_three = _next_phase3_rebind_case(attempt_two)
    source_two = json.loads(attempt_three["manifest_path"].read_text())
    index_before = attempt_three["index_path"].read_bytes()
    retained_before = {
        path: path.read_bytes()
        for path in attempt_three["artifacts"].values()
        if "phase-3-estimate-writeback-attempt-3" not in path.name
        and not path.name.endswith("attempt-3.md")
    }

    MIGRATION.apply_runtime_request(attempt_three["request_path"], "phase3-rebind")

    current = json.loads(attempt_three["manifest_path"].read_text())
    assert current["phase_3_binding_attempt"] == 3
    assert [entry["attempt"] for entry in current["phase_3_revision_history"]] == [
        1,
        2,
    ]
    assert current["phase_3_revision_history"][:-1] == source_two[
        "phase_3_revision_history"
    ]
    assert source_two["phase_3_revision_history"][0]["estimate_writeback_ref"] == (
        source_one["phase_3_estimate_writeback_ref"]
    )
    assert attempt_three["index_path"].read_bytes() == index_before
    assert all(path.read_bytes() == payload for path, payload in retained_before.items())
    readback_path = tmp_path / "phase3-rebind-attempt-3.readback.json"
    _write_json(readback_path, _pre_pr_readback(attempt_three, source_two))
    MIGRATION.validate_pre_pr_readback(readback_path)

    capped = _next_phase3_rebind_case(attempt_three)
    before_cap = capped["manifest_path"].read_bytes()
    with pytest.raises(InputError, match="three-attempt cap"):
        MIGRATION.apply_runtime_request(capped["request_path"], "phase3-rebind")
    assert capped["manifest_path"].read_bytes() == before_cap
    assert not MIGRATION._journal_path().exists()


@pytest.mark.parametrize(
    ("mutation", "error_type", "message"),
    [
        ("replay", InputError, "exact revision projection"),
        ("skip", InputError, "revision lineage length"),
        ("stale-source", ApplyError, "stale runtime manifest"),
        ("stale-artifact", ApplyError, "stale runtime artifact"),
        ("extra-key", InputError, "exact revision projection"),
        ("changed-index", InputError, "cannot change the active index"),
        ("malformed-history", InputError, "history attempts are not ordered"),
        ("missing-prior", InputError, "path is missing"),
        ("aliased-prior", InputError, "duplicate device/inode alias"),
    ],
)
def test_phase3_rebind_refusal_matrix_is_non_mutating(
    mutation: str,
    error_type: type[Exception],
    message: str,
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase3-rebind")
    request = json.loads(case["request_path"].read_text())
    if mutation == "replay":
        current = json.loads(case["manifest_path"].read_text())
        request_path = _write_runtime_request(
            tmp_path / "requests" / "phase3-rebind-replay.json",
            "phase3-rebind",
            case["planning_root"],
            case["manifest_path"],
            case["index_path"],
            current,
            json.loads(case["index_path"].read_text()),
            None,
            case["artifacts"],
        )
    else:
        request_path = case["request_path"]
        if mutation == "skip":
            request["replacement_manifest"]["phase_3_binding_attempt"] = 3
        elif mutation == "stale-source":
            request["sources"]["manifest"]["sha256"] = "0" * 64
        elif mutation == "stale-artifact":
            request["sources"]["artifacts"][0]["sha256"] = "0" * 64
        elif mutation == "extra-key":
            request["replacement_manifest"]["unexpected"] = True
        elif mutation == "changed-index":
            request["replacement_index"]["reviewed_inventory_sha256"] = "0" * 64
        elif mutation == "malformed-history":
            request["replacement_manifest"]["phase_3_revision_history"][-1][
                "attempt"
            ] = 2
        elif mutation == "missing-prior":
            case["artifacts"]["prior-phase-3-proposal"].unlink()
        else:
            original = case["artifacts"]["prior-phase-3-proposal"]
            alias = original.with_name("prior-proposal-alias.md")
            os.link(original, alias)
            request["sources"]["artifacts"].append(
                {
                    "role": "retained-prior-proposal-alias",
                    "path": str(alias),
                    **{
                        key: value
                        for key, value in MIGRATION.runtime_source_identity(alias).items()
                        if key != "exists"
                    },
                }
            )
            request["sources"]["artifacts"].sort(
                key=lambda record: (record["role"], record["path"])
            )
        _resign_runtime_request(request_path, request)
    manifest_before = case["manifest_path"].read_bytes()
    index_before = case["index_path"].read_bytes()

    with pytest.raises(error_type, match=message):
        MIGRATION.apply_runtime_request(request_path, "phase3-rebind")

    assert case["manifest_path"].read_bytes() == manifest_before
    assert case["index_path"].read_bytes() == index_before
    assert not MIGRATION._journal_path().exists()


def test_phase3_rebind_rejects_lifecycle_diversion(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-rebind")
    source = json.loads(case["manifest_path"].read_text())
    source["draft_pr_url"] = "https://github.com/example/repo/pull/260"
    _write_json(case["manifest_path"], source)
    diverted = _next_phase3_rebind_case(case)
    before = diverted["manifest_path"].read_bytes()

    with pytest.raises(InputError, match="bound lifecycle field"):
        MIGRATION.apply_runtime_request(diverted["request_path"], "phase3-rebind")

    assert diverted["manifest_path"].read_bytes() == before
    assert not MIGRATION._journal_path().exists()


def test_phase3_rebind_transaction_fault_restores_manifest_and_guards(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-rebind")
    manifest_before = case["manifest_path"].read_bytes()
    index_before = case["index_path"].read_bytes()
    artifacts_before = {
        path: path.read_bytes() for path in case["artifacts"].values()
    }

    def fail(point: str, index: int) -> None:
        if (point, index) == ("commit-parent-fsync", 0):
            raise OSError("phase3-rebind transaction fault")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError, match="rolled back"):
        MIGRATION.apply_runtime_request(case["request_path"], "phase3-rebind")
    setattr(MIGRATION, "FAULT_HOOK", None)

    assert case["manifest_path"].read_bytes() == manifest_before
    assert case["index_path"].read_bytes() == index_before
    assert all(path.read_bytes() == payload for path, payload in artifacts_before.items())
    assert not MIGRATION._journal_path().exists()


def test_phase0_reresolve_applies_policy_and_passes_closed_readback(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase0-reresolve")
    source_manifest = json.loads(case["manifest_path"].read_text())
    original_index = case["index_path"].read_bytes()

    MIGRATION.apply_runtime_request(case["request_path"], case["operation"])
    current = json.loads(case["manifest_path"].read_text())

    assert current["estimate_mutation_policy"]["value"] is False
    assert current["estimate_writeback_disposition"] == "no_write_policy_disabled"
    assert current["cold_start_disposition_ref"] == source_manifest[
        "cold_start_disposition_ref"
    ]
    assert current["phase_history"] == source_manifest["phase_history"]
    assert case["index_path"].read_bytes() == original_index

    readback_path = tmp_path / "phase0-reresolve.readback.json"
    _write_json(readback_path, _pre_pr_readback(case, source_manifest))
    MIGRATION.validate_pre_pr_readback(readback_path)


def test_phase0_reresolve_rejects_missing_new_producer(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase0-reresolve")
    request = json.loads(case["request_path"].read_text())
    source = json.loads(case["manifest_path"].read_text())
    request["replacement_manifest"]["ticket_snapshot_producing_invocation_uuid"] = (
        source["ticket_snapshot_producing_invocation_uuid"]
    )
    _resign_runtime_request(case["request_path"], request)

    with pytest.raises(InputError, match="must include"):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])


def test_phase0_reresolve_rejects_post_phase3_session(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase0-reresolve")
    source = json.loads(case["manifest_path"].read_text())
    source["phase_3_estimate_writeback_ref"] = str(tmp_path / "phase3.json")
    source["phase_3_estimate_writeback_sha256"] = "d" * 64
    _write_json(case["manifest_path"], source)
    request = json.loads(case["request_path"].read_text())
    request["sources"]["manifest"] = MIGRATION.runtime_source_identity(
        case["manifest_path"]
    )
    request["replacement_manifest"] = copy.deepcopy(source)
    request["replacement_manifest"].update(
        {
            key: value
            for key, value in case["replacement_manifest"].items()
            if key in MIGRATION.RUNTIME_ALLOWED_MANIFEST_CHANGES["phase0-reresolve"]
        }
    )
    _resign_runtime_request(case["request_path"], request)

    with pytest.raises(InputError, match="pre-PR, pre-Phase-3"):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])


def test_phase0_reresolve_policy_drift_composes_with_phase3_bind_and_readback(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase3-bind")
    manifest_path = case["manifest_path"]
    index_path = case["index_path"]
    scratch_dir = Path(json.loads(manifest_path.read_text())["scratch_dir"])
    operator_path = case["artifacts"]["resolved-ticket-operator"]
    contract_path = case["artifacts"]["resolved-ticket-contract"]
    resolution_path = scratch_dir / "phase0-contract-resolution.json"

    operator_path.write_text("# linear operator after policy re-resolution\n")
    contract_path.write_text(
        "source: linear-operator\nestimate_mutation_enabled: false\n"
        "# authenticated after branch-out\n"
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(case["repo_root"]),
            "add",
            "--",
            "agents/linear-operator.md",
            "contracts/linear-operator.yaml",
        ],
        check=True,
        env=GIT_ENV,
    )
    _commit_fixture_repo(case["repo_root"], "policy re-resolution")

    resolution = json.loads(resolution_path.read_text())
    resolution["resolved_operator_sha256"] = _digest(operator_path.read_bytes())
    resolution["resolved_contract_sha256"] = _digest(contract_path.read_bytes())
    _write_json(resolution_path, resolution)

    source_manifest = json.loads(manifest_path.read_text())
    reresolved_manifest = copy.deepcopy(source_manifest)
    reresolved_manifest.update(
        {
            "contract_resolution_producing_invocation_uuid": (
                "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
            ),
            "contract_resolution_sha256": _digest(resolution_path.read_bytes()),
            "resolved_contract_sha256": _digest(contract_path.read_bytes()),
            "resolved_operator_sha256": _digest(operator_path.read_bytes()),
            "ticket_snapshot_producing_invocation_uuid": (
                "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
            ),
        }
    )
    reresolve_artifacts = {
        "phase-0-contract-resolution": resolution_path,
        "phase-0-ticket-snapshot": case["artifacts"]["phase-0-ticket-snapshot"],
        "phase-0-topology-revalidation": (
            scratch_dir / "phase0-topology-revalidation.json"
        ),
        "resolved-ticket-contract": contract_path,
        "resolved-ticket-operator": operator_path,
    }
    reresolve_request = _write_runtime_request(
        scratch_dir / "session-writes" / "phase0-reresolve.json",
        "phase0-reresolve",
        case["planning_root"],
        manifest_path,
        index_path,
        reresolved_manifest,
        json.loads(index_path.read_text()),
        None,
        reresolve_artifacts,
    )
    reresolve_case = {
        "operation": "phase0-reresolve",
        "request_path": reresolve_request,
        "manifest_path": manifest_path,
        "index_path": index_path,
    }
    MIGRATION.apply_runtime_request(reresolve_request, "phase0-reresolve")
    reresolve_readback = (
        scratch_dir / "session-writes" / "phase0-reresolve.readback.json"
    )
    _write_json(reresolve_readback, _pre_pr_readback(reresolve_case, source_manifest))
    MIGRATION.validate_pre_pr_readback(reresolve_readback)

    estimate_path = case["artifacts"]["phase-3-estimate-writeback"]
    estimate = json.loads(estimate_path.read_text())
    estimate["resolved_operator_sha256"] = _digest(operator_path.read_bytes())
    estimate["resolved_contract_sha256"] = _digest(contract_path.read_bytes())
    estimate["currentness"]["resolved_operator_sha256"] = estimate[
        "resolved_operator_sha256"
    ]
    estimate["currentness"]["resolved_contract_sha256"] = estimate[
        "resolved_contract_sha256"
    ]
    _write_json(estimate_path, estimate)

    phase3_source = json.loads(manifest_path.read_text())
    phase3_replacement = copy.deepcopy(phase3_source)
    phase3_replacement.update(
        {
            "phase_3_estimate_writeback_ref": str(estimate_path),
            "phase_3_estimate_writeback_sha256": _digest(estimate_path.read_bytes()),
            "phase_history": phase3_source["phase_history"]
            + [
                {
                    "phase": "3",
                    "status": "complete",
                    "ts": "2026-07-19T00:00:00Z",
                }
            ],
        }
    )
    phase3_artifacts = dict(case["artifacts"])
    phase3_artifacts["phase-0-reresolve-readback"] = reresolve_readback
    phase3_request = _write_runtime_request(
        scratch_dir / "session-writes" / "phase3-bind.json",
        "phase3-bind",
        case["planning_root"],
        manifest_path,
        index_path,
        phase3_replacement,
        json.loads(index_path.read_text()),
        None,
        phase3_artifacts,
    )
    phase3_case = {
        "operation": "phase3-bind",
        "request_path": phase3_request,
        "manifest_path": manifest_path,
        "index_path": index_path,
    }
    MIGRATION.apply_runtime_request(phase3_request, "phase3-bind")
    phase3_readback = scratch_dir / "session-writes" / "phase3-bind.readback.json"
    _write_json(phase3_readback, _pre_pr_readback(phase3_case, phase3_source))
    MIGRATION.validate_pre_pr_readback(phase3_readback)

    current = json.loads(manifest_path.read_text())
    assert current["phase_3_estimate_writeback_ref"] == str(estimate_path)
    assert current["estimate_writeback_disposition"] == "no_write_policy_disabled"
    assert json.loads(index_path.read_text())["sessions"] == []


def test_phase3_bind_rejects_non_reresolve_readback_for_migrated_producers(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase3-bind")
    source_manifest = json.loads(case["manifest_path"].read_text())
    source_manifest["resolved_operator_sha256"] = "0" * 64
    _write_json(case["manifest_path"], source_manifest)

    estimate_path = case["artifacts"]["phase-3-estimate-writeback"]
    estimate = json.loads(estimate_path.read_text())
    estimate["resolved_operator_sha256"] = "0" * 64
    estimate["currentness"]["resolved_operator_sha256"] = "0" * 64
    _write_json(estimate_path, estimate)

    replacement_manifest = copy.deepcopy(source_manifest)
    replacement_manifest.update(
        {
            "phase_3_estimate_writeback_ref": str(estimate_path),
            "phase_3_estimate_writeback_sha256": _digest(estimate_path.read_bytes()),
            "phase_history": source_manifest["phase_history"]
            + [
                {
                    "phase": "3",
                    "status": "complete",
                    "ts": "2026-07-19T00:00:00Z",
                }
            ],
        }
    )
    scratch_dir = Path(source_manifest["scratch_dir"])
    readback_path = scratch_dir / "session-writes" / "phase0-reresolve.readback.json"
    _write_json(readback_path, {"operation": "cold-start-disposition-bind"})
    artifacts = dict(case["artifacts"])
    artifacts["phase-0-reresolve-readback"] = readback_path
    request_path = _write_runtime_request(
        scratch_dir / "session-writes" / "phase3-bind.json",
        "phase3-bind",
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        replacement_manifest,
        case["replacement_index"],
        None,
        artifacts,
    )

    with pytest.raises(InputError, match="producer readback operation mismatch"):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")


def test_validate_pre_pr_readback_machine_validates_phase3_pass(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    source_manifest = json.loads(case["manifest_path"].read_text())
    assert source_manifest["phase_history"]
    assert case["replacement_manifest"]["phase_history"][:-1] == source_manifest[
        "phase_history"
    ]
    assert case["replacement_manifest"]["phase_history"][-1] == {
        "phase": "3",
        "status": "complete",
        "ts": "2026-07-19T00:00:00Z",
    }
    MIGRATION.apply_runtime_request(case["request_path"], case["operation"])
    readback_path = tmp_path / "phase3-bind.readback.json"
    _write_json(readback_path, _pre_pr_readback(case, source_manifest))

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL_DIR),
            "validate-pre-pr-readback",
            "--readback",
            str(readback_path),
        ],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "WU-SESSION-PRE-PR-READBACK: PASS" in result.stdout


def test_validate_pre_pr_readback_recovers_committed_transaction(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    source_manifest = json.loads(case["manifest_path"].read_text())

    def fail(point: str, index: int) -> None:
        if (point, index) == ("cleanup-unlink", 0):
            raise OSError("cleanup fault")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError, match="recovery remains pending"):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])
    setattr(MIGRATION, "FAULT_HOOK", None)
    assert MIGRATION._journal_path().exists()

    readback_path = tmp_path / "phase3-bind.readback.json"
    _write_json(readback_path, _pre_pr_readback(case, source_manifest))
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL_DIR),
            "validate-pre-pr-readback",
            "--readback",
            str(readback_path),
        ],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "WU-SESSION-PRE-PR-READBACK: PASS" in result.stdout
    assert not MIGRATION._journal_path().exists()


def test_validate_pre_pr_readback_rejects_self_asserted_pass(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    source_manifest = json.loads(case["manifest_path"].read_text())
    MIGRATION.apply_runtime_request(case["request_path"], case["operation"])
    readback = _pre_pr_readback(case, source_manifest)
    readback["changed_keys"] = ["phase_history"]
    readback_path = tmp_path / "phase3-bind.readback.json"
    _write_json(readback_path, readback)

    with pytest.raises(InputError, match="changed keys mismatch"):
        MIGRATION.validate_pre_pr_readback(readback_path)


def test_cold_start_disposition_bind_updates_only_disposition_ref(tmp_path: Path):
    case = _runtime_case(tmp_path, "cold-start-disposition-bind")
    source_manifest = json.loads(case["manifest_path"].read_text())
    original_index = case["index_path"].read_bytes()
    original_index_stat = case["index_path"].stat()

    MIGRATION.apply_runtime_request(case["request_path"], case["operation"])

    updated = json.loads(case["manifest_path"].read_text())
    changed = {
        key
        for key in set(source_manifest) | set(updated)
        if source_manifest.get(key) != updated.get(key)
    }
    assert changed == {"cold_start_disposition_ref"}
    assert updated["phase_3_estimate_writeback_ref"] is None
    assert updated["phase_3_estimate_writeback_sha256"] is None
    assert updated["phase_history"] == source_manifest["phase_history"]
    assert case["index_path"].read_bytes() == original_index
    updated_index_stat = case["index_path"].stat()
    assert (updated_index_stat.st_dev, updated_index_stat.st_ino, updated_index_stat.st_mode) == (
        original_index_stat.st_dev,
        original_index_stat.st_ino,
        original_index_stat.st_mode,
    )


@pytest.mark.parametrize("operation", sorted(MIGRATION.RUNTIME_OPERATIONS))
def test_runtime_writer_operations_execute_nominally(operation: str, tmp_path: Path):
    case = _runtime_case(tmp_path, operation)

    code = MIGRATION.main([operation, "--request", str(case["request_path"])])

    assert code == 0
    assert json.loads(case["manifest_path"].read_text()) == case["replacement_manifest"]
    assert json.loads(case["index_path"].read_text()) == case["replacement_index"]
    assert not MIGRATION._journal_path().exists()


def test_direct_runtime_preserves_full_session_identity_across_all_operations(
    tmp_path: Path,
):
    lifecycle = _run_production_runtime_lifecycle(tmp_path)
    initial = lifecycle["initial_manifest"]
    identity_fields = (
        "session_id",
        "implementation_invocation_uuid",
        "ticket_id",
        "ticket_system",
        "branch",
        "base_branch",
        "branch_out_sha",
        "repo_root",
        "worktree_path",
        "planning_dir",
        "scratch_dir",
        "session_manifest_path",
        "route_attempt_number",
        "resolved_operator_path",
        "resolved_operator_sha256",
        "resolved_contract_path",
        "resolved_contract_sha256",
        "resolved_operator_contract_path",
        "resolved_defaults_source",
        "contract_resolution_path",
        "contract_resolution_sha256",
        "contract_resolution_producing_invocation_uuid",
        "ticket_snapshot_path",
        "ticket_snapshot_sha256",
        "ticket_snapshot_producing_invocation_uuid",
        "estimate_mutation_policy",
        "estimate_field",
        "estimate_writeback_disposition",
        "spawned_at",
        "auto_merge_after_phase_9",
        "topology_revalidation_path",
        "topology_revalidation_sha256",
        "wu_brief_context_path",
        "wu_brief_context_sha256",
        "wu_brief_context_source_path",
        "wu_brief_context_source_sha256",
    )
    expected_identity = {field: initial[field] for field in identity_fields}

    assert list(lifecycle["snapshots"]) == [
        "phase0-init",
        "phase7-upsert",
        "phase9-update",
        "resumer-update",
        "resumer-close",
    ]
    for snapshot in lifecycle["snapshots"].values():
        persisted = snapshot["manifest"]
        assert {field: persisted[field] for field in identity_fields} == expected_identity
    assert lifecycle["snapshots"]["phase0-init"]["index"]["sessions"] == []
    assert len(lifecycle["snapshots"]["phase7-upsert"]["index"]["sessions"]) == 1
    assert lifecycle["snapshots"]["resumer-close"]["index"]["sessions"] == []


def test_direct_runtime_preserves_reviewed_active_index_metadata(tmp_path: Path):
    lifecycle = _run_production_runtime_lifecycle(tmp_path, reviewed_index=True)
    expected_metadata = {
        "schema": MIGRATION.ACTIVE_INDEX_SCHEMA,
        "reviewed_inventory_sha256": "7" * 64,
        "source_index_path": str(lifecycle["planning_root"] / "sessions.index.json"),
    }

    for snapshot in lifecycle["snapshots"].values():
        index = snapshot["index"]
        assert {field: index[field] for field in expected_metadata} == expected_metadata
        assert set(index) == {*expected_metadata, "sessions"}
    assert lifecycle["source_index_path"].read_bytes() == lifecycle["source_index_before"]
    assert Path(expected_metadata["source_index_path"]).parent == lifecycle["planning_root"]
    assert not MIGRATION._journal_path().exists()


def test_feature_runtime_phase0_uses_route_index_and_same_project_scratch(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase0-init", feature=True)
    direct_before = case["direct_index_path"].read_bytes()
    direct_stat = case["direct_index_path"].stat()

    MIGRATION.apply_runtime_request(case["request_path"], case["operation"])

    manifest = json.loads(case["manifest_path"].read_text())
    assert Path(manifest["planning_dir"]).parent == case["planning_root"]
    assert Path(manifest["scratch_dir"]).is_relative_to(case["project_planning_root"])
    assert not Path(manifest["scratch_dir"]).is_relative_to(case["planning_root"])
    assert json.loads(case["index_path"].read_text())["sessions"] == []
    assert case["direct_index_path"].read_bytes() == direct_before
    current_direct_stat = case["direct_index_path"].stat()
    assert (
        current_direct_stat.st_dev,
        current_direct_stat.st_ino,
        current_direct_stat.st_mode,
    ) == (direct_stat.st_dev, direct_stat.st_ino, direct_stat.st_mode)
    assert not MIGRATION._journal_path().exists()


@pytest.mark.parametrize(
    ("operation", "changed_keys"),
    [
        ("cold-start-disposition-bind", {"cold_start_disposition_ref"}),
        (
            "phase3-bind",
            {
                "phase_3_estimate_writeback_ref",
                "phase_3_estimate_writeback_sha256",
                "phase_history",
            },
        ),
    ],
)
def test_feature_pre_pr_binds_preserve_route_index_and_pass_closed_readback(
    operation: str, changed_keys: set[str], tmp_path: Path
):
    case = _runtime_case(tmp_path, operation, feature=True)
    source_manifest = json.loads(case["manifest_path"].read_text())
    feature_index_before = case["index_path"].read_bytes()
    feature_index_stat = case["index_path"].stat()
    direct_index_before = case["direct_index_path"].read_bytes()

    MIGRATION.apply_runtime_request(case["request_path"], operation)
    readback_path = tmp_path / f"{operation}.readback.json"
    _write_json(readback_path, _pre_pr_readback(case, source_manifest))

    assert MIGRATION.validate_pre_pr_readback(readback_path) is None
    current_manifest = json.loads(case["manifest_path"].read_text())
    assert {
        key
        for key in set(source_manifest) | set(current_manifest)
        if source_manifest.get(key) != current_manifest.get(key)
    } == changed_keys
    assert case["index_path"].read_bytes() == feature_index_before
    current_feature_stat = case["index_path"].stat()
    assert (
        current_feature_stat.st_dev,
        current_feature_stat.st_ino,
        current_feature_stat.st_mode,
    ) == (
        feature_index_stat.st_dev,
        feature_index_stat.st_ino,
        feature_index_stat.st_mode,
    )
    assert case["direct_index_path"].read_bytes() == direct_index_before
    assert not MIGRATION._journal_path().exists()


@pytest.mark.parametrize(
    ("operation", "expected_rows"),
    [
        ("phase7-upsert", 1),
        ("phase9-update", 1),
        ("resumer-update", 1),
        ("resumer-close", 0),
    ],
)
def test_feature_active_lifecycle_mutates_only_the_route_index(
    operation: str, expected_rows: int, tmp_path: Path
):
    case = _runtime_case(tmp_path, operation, feature=True)
    direct_before = case["direct_index_path"].read_bytes()

    MIGRATION.apply_runtime_request(case["request_path"], operation)

    rows = json.loads(case["index_path"].read_text())["sessions"]
    assert len(rows) == expected_rows
    assert all(row["session_manifest_path"] == str(case["manifest_path"]) for row in rows)
    assert case["direct_index_path"].read_bytes() == direct_before
    assert not MIGRATION._journal_path().exists()


def test_direct_and_feature_sessions_coexist_in_separate_owner_indexes(tmp_path: Path):
    direct = _runtime_case(tmp_path, "phase7-upsert")
    MIGRATION.apply_runtime_request(direct["request_path"], direct["operation"])
    feature = _runtime_case(tmp_path, "phase7-upsert", feature=True)
    direct_before_feature_upsert = direct["index_path"].read_bytes()

    MIGRATION.apply_runtime_request(feature["request_path"], feature["operation"])

    direct_rows = json.loads(direct["index_path"].read_text())["sessions"]
    feature_rows = json.loads(feature["index_path"].read_text())["sessions"]
    assert len(direct_rows) == 1
    assert len(feature_rows) == 1
    assert direct["index_path"].read_bytes() == direct_before_feature_upsert
    assert direct_rows[0]["session_manifest_path"] == str(direct["manifest_path"])
    assert feature_rows[0]["session_manifest_path"] == str(feature["manifest_path"])
    assert direct_rows[0]["session_manifest_path"] != feature_rows[0][
        "session_manifest_path"
    ]
    assert not MIGRATION._journal_path().exists()


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            "unsupported-owner",
            "runtime planning root is not a supported session owner",
        ),
        (
            "sibling-routes",
            "runtime planning root is not a supported session owner",
        ),
        (
            "nested-routes",
            "runtime planning root is not a supported session owner",
        ),
        ("wrong-index", "runtime active index path does not match planning_root"),
        (
            "nested-session",
            "runtime planning_dir must be a direct child of planning_root",
        ),
        (
            "cross-tree-scratch",
            "pre-PR manifest scratch_dir is noncanonical or cross-root",
        ),
    ],
)
def test_feature_runtime_rejects_noncanonical_owner_relationships_before_mutation(
    mutation: str,
    expected_error: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    case = _runtime_case(tmp_path, "phase0-init", feature=True)
    request = json.loads(case["request_path"].read_text())
    if mutation == "unsupported-owner":
        request["planning_root"] = str(
            case["project_planning_root"] / "features" / "acr-337" / "runtime"
        )
    elif mutation in {"sibling-routes", "nested-routes"}:
        planning_root = (
            case["project_planning_root"] / "other" / "routes"
            if mutation == "sibling-routes"
            else case["planning_root"].parent / "nested" / "routes"
        )
        manifest_path = (
            planning_root / case["manifest_path"].parent.name / "session.json"
        )
        request.update(
            {
                "planning_root": str(planning_root),
                "manifest_path": str(manifest_path),
                "index_path": str(planning_root / "sessions.active-wake.json"),
            }
        )
        request["replacement_manifest"]["planning_dir"] = str(manifest_path.parent)
        request["replacement_manifest"]["session_manifest_path"] = str(manifest_path)
    elif mutation == "wrong-index":
        request["index_path"] = str(case["direct_index_path"])
        request["sources"]["index"] = MIGRATION.runtime_source_identity(
            case["direct_index_path"]
        )
    elif mutation == "nested-session":
        manifest_path = case["planning_root"] / "nested" / "AGE-260" / "session.json"
        request["manifest_path"] = str(manifest_path)
        request["replacement_manifest"]["planning_dir"] = str(manifest_path.parent)
        request["replacement_manifest"]["session_manifest_path"] = str(manifest_path)
    else:
        foreign_scratch = tmp_path / "foreign" / "planning" / "scratch"
        foreign_scratch.mkdir(parents=True)
        request["replacement_manifest"]["scratch_dir"] = str(foreign_scratch)
    _resign_runtime_request(case["request_path"], request)
    targets = [case["manifest_path"], case["index_path"], case["direct_index_path"]]
    before = {path: path.read_bytes() if path.exists() else None for path in targets}

    assert MIGRATION.main(
        [case["operation"], "--request", str(case["request_path"])]
    ) == 2

    assert expected_error in capsys.readouterr().err
    assert {path: path.read_bytes() if path.exists() else None for path in targets} == before
    assert not MIGRATION._journal_path().exists()
    assert not _transaction_artifacts(targets)


def test_feature_runtime_rejects_symlinked_route_owner_before_mutation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    case = _runtime_case(tmp_path, "phase0-init", feature=True)
    request = json.loads(case["request_path"].read_text())
    feature_dir = case["planning_root"].parent
    alias_dir = feature_dir.parent / "acr-337-link"
    alias_dir.symlink_to(feature_dir, target_is_directory=True)
    alias_root = alias_dir / "routes"
    alias_manifest = alias_root / case["manifest_path"].parent.name / "session.json"
    request.update(
        {
            "planning_root": str(alias_root),
            "manifest_path": str(alias_manifest),
            "index_path": str(alias_root / "sessions.active-wake.json"),
        }
    )
    request["replacement_manifest"]["planning_dir"] = str(alias_manifest.parent)
    request["replacement_manifest"]["session_manifest_path"] = str(alias_manifest)
    _resign_runtime_request(case["request_path"], request)
    targets = [case["manifest_path"], case["index_path"], case["direct_index_path"]]
    before = {path: path.read_bytes() if path.exists() else None for path in targets}

    assert MIGRATION.main(
        [case["operation"], "--request", str(case["request_path"])]
    ) == 2

    assert "symlink path component is forbidden" in capsys.readouterr().err
    assert {path: path.read_bytes() if path.exists() else None for path in targets} == before
    assert not MIGRATION._journal_path().exists()


def test_feature_runtime_recovers_interrupted_route_index_transaction(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase7-upsert", feature=True)
    command = [
        sys.executable,
        str(TOOL_DIR),
        case["operation"],
        "--request",
        str(case["request_path"]),
    ]
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "commit-parent-fsync:0"

    assert subprocess.run(command, env=env, capture_output=True).returncode == 97
    assert MIGRATION._journal_path().exists()
    env.pop("WU_SESSION_MIGRATION_INTERRUPT")
    stale = subprocess.run(command, env=env, text=True, capture_output=True)
    assert stale.returncode == 3
    assert not MIGRATION._journal_path().exists()

    refreshed = _write_runtime_request(
        case["request_path"],
        case["operation"],
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        case["replacement_manifest"],
        case["replacement_index"],
        _row_identity(_active_row(case["replacement_manifest"], case["manifest_path"])),
    )
    completed = subprocess.run(
        [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(refreshed)],
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert len(json.loads(case["index_path"].read_text())["sessions"]) == 1
    assert json.loads(case["direct_index_path"].read_text())["sessions"] == []


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            "lexical-alias",
            "runtime request manifest_path must be normalized and absolute",
        ),
        ("symlink", "symlink path component is forbidden"),
        (
            "path-escape",
            "runtime manifest path is outside a planning tree",
        ),
    ],
    ids=["lexical-alias", "symlink", "path-escape"],
)
def test_runtime_request_path_aliases_and_symlinks_fail_before_mutation(
    mutation: str,
    expected_error: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    case = _runtime_case(tmp_path / mutation, "phase7-upsert")
    request = json.loads(case["request_path"].read_text())
    extra_targets: list[Path] = []
    if mutation == "lexical-alias":
        request["manifest_path"] = str(
            case["manifest_path"].parent
            / ".."
            / case["manifest_path"].parent.name
            / "session.json"
        )
    elif mutation == "symlink":
        alias_project = tmp_path / mutation / "project-link"
        alias_project.symlink_to(case["planning_root"].parent, target_is_directory=True)
        alias_root = alias_project / "planning"
        request["planning_root"] = str(alias_root)
        request["manifest_path"] = str(
            alias_root / case["manifest_path"].parent.name / "session.json"
        )
        request["index_path"] = str(alias_root / "sessions.active-wake.json")
    else:
        escaped_manifest = tmp_path / mutation / "outside" / "session.json"
        escaped_manifest.parent.mkdir()
        request["manifest_path"] = str(escaped_manifest)
        extra_targets.append(escaped_manifest)
    _resign_runtime_request(case["request_path"], request)

    addressed_targets = [Path(request["manifest_path"]), Path(request["index_path"])]
    watched_targets = [
        case["manifest_path"],
        case["index_path"],
        *addressed_targets,
        *extra_targets,
    ]
    before = {
        path: path.read_bytes() if path.exists() else None for path in watched_targets
    }

    assert MIGRATION.main(
        [case["operation"], "--request", str(case["request_path"])]
    ) == 2
    assert expected_error in capsys.readouterr().err
    assert {
        path: path.read_bytes() if path.exists() else None for path in watched_targets
    } == before
    assert not MIGRATION._journal_path().exists()
    assert not _transaction_artifacts(watched_targets)


@pytest.mark.parametrize(
    ("mutation", "operation", "expected_error"),
    [
        ("input-digest", "phase7-upsert", "runtime request input-set digest mismatch"),
        ("payload-digest", "phase7-upsert", "runtime request payload digest mismatch"),
        (
            "forbidden-field",
            "phase9-update",
            "phase9-update changes forbidden manifest fields",
        ),
        (
            "missing-row",
            "phase9-update",
            "runtime active-row identity is missing or duplicated",
        ),
        (
            "missing-row",
            "resumer-update",
            "runtime active-row identity is missing or duplicated",
        ),
        ("missing-row", "resumer-close", "resumer-close requires one exact active row"),
    ],
    ids=[
        "input-digest",
        "payload-digest",
        "forbidden-field",
        "missing-row-phase9-update",
        "missing-row-resumer-update",
        "missing-row-resumer-close",
    ],
)
def test_runtime_request_digests_allowlists_and_exact_row_requirements_fail_before_mutation(
    mutation: str,
    operation: str,
    expected_error: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    case = _runtime_case(tmp_path / f"{mutation}-{operation}", operation)
    request = json.loads(case["request_path"].read_text())
    if mutation == "input-digest":
        request["input_set_sha256"] = "0" * 64
        _write_json(case["request_path"], request)
    elif mutation == "payload-digest":
        request["payload_sha256"] = "0" * 64
        _write_json(case["request_path"], request)
    elif mutation == "forbidden-field":
        request["replacement_manifest"]["ticket_id"] = "AGE-OTHER"
        _resign_runtime_request(case["request_path"], request)
    else:
        empty_index = {"schema": MIGRATION.ACTIVE_INDEX_SCHEMA, "sessions": []}
        _write_json(case["index_path"], empty_index)
        replacement_index = (
            empty_index if operation == "resumer-close" else case["replacement_index"]
        )
        _write_runtime_request(
            case["request_path"],
            operation,
            case["planning_root"],
            case["manifest_path"],
            case["index_path"],
            case["replacement_manifest"],
            replacement_index,
            _row_identity(
                _expected_active_row(
                    case["replacement_manifest"], case["manifest_path"]
                )
            ),
        )

    targets = [case["manifest_path"], case["index_path"]]
    before = {path: path.read_bytes() if path.exists() else None for path in targets}

    assert MIGRATION.main(
        [case["operation"], "--request", str(case["request_path"])]
    ) == 2
    assert expected_error in capsys.readouterr().err
    assert {
        path: path.read_bytes() if path.exists() else None for path in targets
    } == before
    assert not MIGRATION._journal_path().exists()
    assert not _transaction_artifacts(targets)


@pytest.mark.parametrize("operation", sorted(MIGRATION.RUNTIME_OPERATIONS))
def test_runtime_writer_operations_roll_back_cross_file_failure(operation: str, tmp_path: Path):
    case = _runtime_case(tmp_path, operation)
    paths = [case["manifest_path"], case["index_path"]]
    before = {path: path.read_bytes() if path.exists() else None for path in paths}

    def fail(point: str, index: int) -> None:
        if (point, index) == ("commit-parent-fsync", 0):
            raise OSError("runtime commit fault")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError):
        MIGRATION.apply_runtime_request(case["request_path"], operation)
    setattr(MIGRATION, "FAULT_HOOK", None)

    assert {path: path.read_bytes() if path.exists() else None for path in paths} == before
    assert not MIGRATION._journal_path().exists()


@pytest.mark.parametrize("operation", sorted(MIGRATION.RUNTIME_OPERATIONS))
def test_runtime_writer_operations_recover_subprocess_interruption(operation: str, tmp_path: Path):
    case = _runtime_case(tmp_path, operation)
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "commit-parent-fsync:0"
    command = [sys.executable, str(TOOL_DIR), operation, "--request", str(case["request_path"])]

    interrupted = subprocess.run(command, env=env, text=True, capture_output=True)
    assert interrupted.returncode == 97
    assert MIGRATION._journal_path().exists()

    env.pop("WU_SESSION_MIGRATION_INTERRUPT")
    recovered_stale = subprocess.run(command, env=env, text=True, capture_output=True)
    assert recovered_stale.returncode == (0 if operation == "phase0-init" else 3)
    assert "Traceback" not in recovered_stale.stderr
    assert not MIGRATION._journal_path().exists()
    if recovered_stale.returncode == 0:
        return
    refreshed = _write_runtime_request(
        case["request_path"],
        operation,
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        case["replacement_manifest"],
        case["replacement_index"],
        None
        if operation == "phase0-init" or operation in MIGRATION.PRE_PR_BIND_OPERATIONS
        else _row_identity(_active_row(case["replacement_manifest"], case["manifest_path"])),
        case.get("artifacts"),
    )
    completed = subprocess.run(
        [sys.executable, str(TOOL_DIR), operation, "--request", str(refreshed)],
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    ("point", "index"),
    [
        ("backup-create", 0),
        ("backup-file-fsync", 0),
        ("backup-parent-fsync", 0),
        ("replacement-create", 0),
        ("replacement-file-fsync", 0),
        ("replacement-parent-fsync", 0),
        ("journal-create", 0),
        ("journal-write", 0),
        ("journal-file-fsync", 0),
        ("journal-replace", 0),
        ("journal-parent-fsync", 0),
        ("journal-transition", 0),
        ("replacement", 0),
        ("commit-parent-fsync", 0),
    ],
)
def test_shared_transaction_fault_stages_restore_sources(point: str, index: int, tmp_path: Path):
    case = _runtime_case(tmp_path, "phase9-update")
    paths = [case["manifest_path"], case["index_path"]]
    before = {path: path.read_bytes() for path in paths}

    def fail(actual_point: str, actual_index: int) -> None:
        if (actual_point, actual_index) == (point, index):
            raise OSError(f"fault {point}:{index}")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])
    setattr(MIGRATION, "FAULT_HOOK", None)
    if MIGRATION._journal_path().exists():
        MIGRATION.recover_incomplete_transaction()
    assert {path: path.read_bytes() for path in paths} == before


@pytest.mark.parametrize(
    ("point", "artifact"),
    [("backup-write", "backup"), ("replacement-write", "replacement")],
)
def test_partial_identity_unbound_transaction_artifact_is_preserved(
    point: str, artifact: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase9-update")
    paths = [case["manifest_path"], case["index_path"]]
    before = {path: path.read_bytes() for path in paths}

    def fail(actual_point: str, actual_index: int) -> None:
        if (actual_point, actual_index) == (point, 0):
            raise OSError(f"fault {point}:0")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError, match="recovery remains pending"):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])
    setattr(MIGRATION, "FAULT_HOOK", None)
    journal = json.loads(MIGRATION._journal_path().read_text())
    artifact_path = Path(journal["ordered_targets"][0][f"{artifact}_path"])

    assert artifact_path.exists()
    with pytest.raises(ApplyError, match="identity-unbound transaction artifact"):
        MIGRATION.recover_incomplete_transaction()
    assert artifact_path.exists()
    assert MIGRATION._journal_path().exists()
    assert {path: path.read_bytes() for path in paths} == before


@pytest.mark.parametrize(
    ("operation", "rollback_point"),
    [("phase0-init", "rollback-unlink"), ("phase9-update", "rollback-replace"), ("phase9-update", "rollback-parent-fsync")],
)
def test_rollback_stage_failures_retain_journal_and_recover(
    operation: str, rollback_point: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, operation)
    paths = [case["manifest_path"], case["index_path"]]
    before = {path: path.read_bytes() if path.exists() else None for path in paths}

    def fail(point: str, index: int) -> None:
        if (point, index) in {("commit-parent-fsync", 0), (rollback_point, 0)}:
            raise OSError(f"fault {point}:{index}")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError, match="recovery remains pending"):
        MIGRATION.apply_runtime_request(case["request_path"], operation)
    assert MIGRATION._journal_path().exists()
    setattr(MIGRATION, "FAULT_HOOK", None)
    MIGRATION.recover_incomplete_transaction()
    assert {path: path.read_bytes() if path.exists() else None for path in paths} == before


def test_committed_cleanup_failure_retains_recoverable_journal(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase9-update")

    def fail(point: str, index: int) -> None:
        if (point, index) == ("cleanup-unlink", 0):
            raise OSError("cleanup fault")

    setattr(MIGRATION, "FAULT_HOOK", fail)
    with pytest.raises(ApplyError, match="recovery remains pending"):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])
    assert MIGRATION._journal_path().exists()
    setattr(MIGRATION, "FAULT_HOOK", None)
    MIGRATION.recover_incomplete_transaction()
    assert json.loads(case["manifest_path"].read_text()) == case["replacement_manifest"]
    assert not MIGRATION._journal_path().exists()


def test_recovery_subprocess_interruption_is_retried_without_target_mutation(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase9-update")
    command = [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(case["request_path"])]
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "commit-parent-fsync:0"
    assert subprocess.run(command, env=env, capture_output=True).returncode == 97
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "recovery:1"
    assert subprocess.run(command, env=env, capture_output=True).returncode == 97
    assert MIGRATION._journal_path().exists()
    env.pop("WU_SESSION_MIGRATION_INTERRUPT")
    recovered = subprocess.run(command, env=env, text=True, capture_output=True)
    assert recovered.returncode == 3
    assert "Traceback" not in recovered.stderr
    assert not MIGRATION._journal_path().exists()


@pytest.mark.parametrize(
    ("interrupt", "retry_code"),
    [
        ("backup-create:0", 0),
        ("backup-file-fsync:0", 0),
        ("backup-parent-fsync:0", 0),
        ("replacement-create:0", 0),
        ("replacement-file-fsync:0", 0),
        ("replacement-parent-fsync:0", 0),
        ("journal-transition:0", 0),
        ("journal-transition:1", 3),
        ("journal-transition:2", 3),
        ("journal-transition:3", 3),
        ("cleanup-unlink:0", 3),
    ],
)
def test_subprocess_interruptions_cover_staging_commit_progress_and_committed_cleanup(
    interrupt: str, retry_code: int, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase9-update")
    command = [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(case["request_path"])]
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = interrupt

    interrupted = subprocess.run(command, env=env, text=True, capture_output=True)
    assert interrupted.returncode == 97
    assert MIGRATION._journal_path().exists()
    env.pop("WU_SESSION_MIGRATION_INTERRUPT")

    retried = subprocess.run(command, env=env, text=True, capture_output=True)
    assert retried.returncode == retry_code
    assert "Traceback" not in retried.stderr
    assert not MIGRATION._journal_path().exists()
    assert not _transaction_artifacts([case["manifest_path"], case["index_path"]])


@pytest.mark.parametrize(
    ("artifact", "interrupt"),
    [
        ("backup", "backup-file-fsync:0"),
        ("replacement", "replacement-file-fsync:0"),
    ],
)
def test_matching_identity_unbound_transaction_artifact_is_cleaned(
    artifact: str, interrupt: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase9-update")
    command = [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(case["request_path"])]
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = interrupt

    interrupted = subprocess.run(command, env=env, text=True, capture_output=True)
    assert interrupted.returncode == 97
    journal = json.loads(MIGRATION._journal_path().read_text())
    target = journal["ordered_targets"][0]
    assert target[f"{artifact}_device"] is None
    assert Path(target[f"{artifact}_path"]).exists()

    env.pop("WU_SESSION_MIGRATION_INTERRUPT")
    recovered = subprocess.run(command, env=env, text=True, capture_output=True)
    assert recovered.returncode == 0, recovered.stderr
    assert not MIGRATION._journal_path().exists()
    assert not _transaction_artifacts([case["manifest_path"], case["index_path"]])


@pytest.mark.parametrize("artifact", ["backup", "replacement"])
def test_foreign_identity_unbound_staging_artifact_is_preserved(
    artifact: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase9-update")
    command = [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(case["request_path"])]
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "stage:0"
    interrupted = subprocess.run(command, env=env, text=True, capture_output=True)
    assert interrupted.returncode == 97
    journal = json.loads(MIGRATION._journal_path().read_text())
    target = journal["ordered_targets"][0]
    artifact_path = Path(target[f"{artifact}_path"])
    foreign = b"foreign identity-unbound artifact\n"
    artifact_path.write_bytes(foreign)
    assert target[f"{artifact}_device"] is None

    env.pop("WU_SESSION_MIGRATION_INTERRUPT")
    refused = subprocess.run(command, env=env, text=True, capture_output=True)

    assert refused.returncode == 3
    assert "Traceback" not in refused.stderr
    assert "recovery failures" in refused.stderr
    assert str(artifact_path) in refused.stderr
    assert artifact_path.read_bytes() == foreign
    assert MIGRATION._journal_path().exists()


def test_runtime_request_closed_schema_rejects_unknown_keys_without_mutation(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase7-upsert")
    request = json.loads(case["request_path"].read_text())
    request["extra"] = True
    _write_json(case["request_path"], request)
    before = case["manifest_path"].read_bytes()

    result = subprocess.run(
        [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(case["request_path"])],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert case["manifest_path"].read_bytes() == before


@pytest.mark.parametrize("mutation", ["nested-manifest", "alternate-index", "manifest-planning-dir"])
def test_runtime_request_rejects_noncanonical_manifest_root_index_relationship(
    mutation: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase7-upsert")
    manifest_path = case["manifest_path"]
    index_path = case["index_path"]
    replacement_manifest = copy.deepcopy(case["replacement_manifest"])
    if mutation == "nested-manifest":
        manifest_path = case["planning_root"] / "nested" / "AGE-260" / "session.json"
        manifest_path.parent.mkdir(parents=True)
        replacement_manifest["planning_dir"] = str(manifest_path.parent)
        replacement_manifest["session_manifest_path"] = str(manifest_path)
    elif mutation == "alternate-index":
        index_path = case["planning_root"] / "nested" / "sessions.active-wake.json"
        index_path.parent.mkdir()
    else:
        other_planning = case["planning_root"] / "OTHER"
        other_planning.mkdir()
        replacement_manifest["planning_dir"] = str(other_planning)
    request_path = _write_runtime_request(
        tmp_path / f"{mutation}.json",
        case["operation"],
        case["planning_root"],
        manifest_path,
        index_path,
        replacement_manifest,
        case["replacement_index"],
        _row_identity(_active_row(replacement_manifest, manifest_path)),
    )
    before = case["manifest_path"].read_bytes()

    result = MIGRATION.main([case["operation"], "--request", str(request_path)])

    assert result == 2
    assert case["manifest_path"].read_bytes() == before


def _other_runtime_row(
    case: dict[str, Any], tmp_path: Path, *, cross_root: bool = False
) -> dict[str, Any]:
    planning_root = (
        tmp_path / "other-project" / "planning" if cross_root else case["planning_root"]
    )
    planning_dir = planning_root / "OTHER"
    planning_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = planning_dir / "session.json"
    manifest = copy.deepcopy(case["replacement_manifest"])
    manifest.update(
        {
            "ticket_id": "AGE-OTHER",
            "branch": "age-other",
            "draft_pr_url": "https://github.com/example/repo/pull/999",
            "planning_dir": str(planning_dir),
            "session_manifest_path": str(manifest_path),
        }
    )
    _write_json(manifest_path, manifest)
    return _active_row(manifest, manifest_path)


@pytest.mark.parametrize("duplicate", ["wake", "manifest", "ticket-branch"])
def test_runtime_request_rejects_duplicate_active_index_joins(
    duplicate: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase9-update")
    source_index = json.loads(case["index_path"].read_text())
    first = source_index["sessions"][0]
    second = _other_runtime_row(case, tmp_path)
    if duplicate == "wake":
        second["draft_pr_url"] = first["draft_pr_url"]
        second["branch"] = first["branch"]
    elif duplicate == "manifest":
        second["session_manifest_path"] = first["session_manifest_path"]
        second["planning_dir"] = first["planning_dir"]
    else:
        second["ticket_id"] = first["ticket_id"]
        second["branch"] = first["branch"]
    source_index["sessions"].append(second)
    _write_json(case["index_path"], source_index)
    request_path = _write_runtime_request(
        tmp_path / f"duplicate-{duplicate}.json",
        case["operation"],
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        case["replacement_manifest"],
        source_index,
        _row_identity(_active_row(case["replacement_manifest"], case["manifest_path"])),
    )

    assert MIGRATION.main([case["operation"], "--request", str(request_path)]) == 2


def test_runtime_request_rejects_cross_root_active_row_path(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase9-update")
    source_index = json.loads(case["index_path"].read_text())
    source_index["sessions"].append(_other_runtime_row(case, tmp_path, cross_root=True))
    _write_json(case["index_path"], source_index)
    request_path = _write_runtime_request(
        tmp_path / "cross-root.json",
        case["operation"],
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        case["replacement_manifest"],
        source_index,
        _row_identity(_active_row(case["replacement_manifest"], case["manifest_path"])),
    )

    assert MIGRATION.main([case["operation"], "--request", str(request_path)]) == 2


@pytest.mark.parametrize("collision", ["wake", "manifest", "ticket-branch"])
def test_phase7_upsert_rejects_any_existing_join_collision(
    collision: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase7-upsert")
    replacement_row = _active_row(case["replacement_manifest"], case["manifest_path"])
    existing = _other_runtime_row(case, tmp_path)
    if collision == "wake":
        existing["draft_pr_url"] = replacement_row["draft_pr_url"]
        existing["branch"] = replacement_row["branch"]
    elif collision == "manifest":
        existing["session_manifest_path"] = replacement_row["session_manifest_path"]
        existing["planning_dir"] = replacement_row["planning_dir"]
    else:
        existing["ticket_id"] = replacement_row["ticket_id"]
        existing["branch"] = replacement_row["branch"]
    source_index = {"schema": MIGRATION.ACTIVE_INDEX_SCHEMA, "sessions": [existing]}
    _write_json(case["index_path"], source_index)
    requested_index = {
        "schema": MIGRATION.ACTIVE_INDEX_SCHEMA,
        "sessions": [existing, replacement_row],
    }
    request_path = _write_runtime_request(
        tmp_path / f"collision-{collision}.json",
        case["operation"],
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        case["replacement_manifest"],
        requested_index,
        _row_identity(replacement_row),
    )

    assert MIGRATION.main([case["operation"], "--request", str(request_path)]) == 2


def _resign_runtime_request(path: Path, request: dict[str, Any]) -> None:
    request["input_set_sha256"], request["payload_sha256"] = (
        MIGRATION.runtime_request_digests(request)
    )
    _write_json(path, request)


@pytest.mark.parametrize(
    ("operation", "mutation"),
    [
        ("cold-start-disposition-bind", "history"),
        ("cold-start-disposition-bind", "index"),
        ("cold-start-disposition-bind", "row-identity"),
        ("phase0-reresolve", "history"),
        ("phase0-reresolve", "index"),
        ("phase0-reresolve", "row-identity"),
        ("phase3-bind", "cold-start"),
        ("phase3-bind", "index"),
        ("phase3-bind", "row-identity"),
    ],
)
def test_pre_pr_bind_operations_reject_mixed_fields_index_changes_and_row_identity(
    operation: str, mutation: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, operation)
    request = json.loads(case["request_path"].read_text())
    if mutation == "history":
        request["replacement_manifest"]["phase_history"] = request[
            "replacement_manifest"
        ]["phase_history"] + [
            {"phase": "2.6", "status": "complete", "ts": "2026-07-18T01:00:00Z"}
        ]
    elif mutation == "cold-start":
        request["replacement_manifest"]["cold_start_disposition_ref"] = None
    elif mutation == "index":
        request["replacement_index"]["reviewed_inventory_sha256"] = "f" * 64
    else:
        request["row_identity"] = {
            "ticket_id": "AGE-260",
            "branch": "age-260-runtime",
            "draft_pr_url": "https://github.com/example/repo/pull/260",
            "session_manifest_path": str(case["manifest_path"]),
        }
    _resign_runtime_request(case["request_path"], request)
    before_manifest = case["manifest_path"].read_bytes()
    before_index = case["index_path"].read_bytes()

    assert MIGRATION.main([operation, "--request", str(case["request_path"])]) == 2
    assert case["manifest_path"].read_bytes() == before_manifest
    assert case["index_path"].read_bytes() == before_index


@pytest.mark.parametrize(
    "operation", ["cold-start-disposition-bind", "phase0-reresolve", "phase3-bind"]
)
def test_pre_pr_bind_operations_refuse_semantic_replay(
    operation: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, operation)
    MIGRATION.apply_runtime_request(case["request_path"], operation)
    replay = _write_runtime_request(
        tmp_path / "requests" / f"{operation}-replay.json",
        operation,
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        case["replacement_manifest"],
        case["replacement_index"],
        None,
        case["artifacts"],
    )

    assert MIGRATION.main([operation, "--request", str(replay)]) == 2


@pytest.mark.parametrize(
    ("operation", "expected_roles"),
    [
        (
            "cold-start-disposition-bind",
            ["active-index", "cold-start-disposition"],
        ),
        (
            "phase0-reresolve",
            [
                "active-index",
                "phase-0-contract-resolution",
                "phase-0-ticket-snapshot",
                "phase-0-topology-revalidation",
                "resolved-ticket-contract",
                "resolved-ticket-operator",
            ],
        ),
        (
            "phase3-bind",
            [
                "active-index",
                "cold-start-disposition",
                "phase-0-ticket-snapshot",
                "phase-3-estimate-writeback",
                "phase-3-proposal",
                "resolved-ticket-contract",
                "resolved-ticket-operator",
                "write-verification-evidence",
            ],
        ),
    ],
)
def test_pre_pr_bind_operations_journal_one_target_and_read_only_guards(
    operation: str, expected_roles: list[str], tmp_path: Path
):
    case = _runtime_case(tmp_path, operation)
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "journal-transition:0"
    command = [
        sys.executable,
        str(TOOL_DIR),
        operation,
        "--request",
        str(case["request_path"]),
    ]

    assert subprocess.run(command, env=env, capture_output=True).returncode == 97
    journal = json.loads(MIGRATION._journal_path().read_text())
    assert [target["path"] for target in journal["ordered_targets"]] == [
        str(case["manifest_path"])
    ]
    assert [guard["role"] for guard in journal["read_only_guards"]] == expected_roles
    assert str(case["index_path"]) not in {
        target["path"] for target in journal["ordered_targets"]
    }
    MIGRATION.recover_incomplete_transaction()
    assert not MIGRATION._journal_path().exists()


def test_pre_pr_bind_guard_race_rolls_back_manifest_without_rewriting_index(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase3-bind")
    manifest_before = case["manifest_path"].read_bytes()
    raced_index = b'{"schema":"wu-sessions-active-wake-v1","sessions":[]}\n'

    def mutate_index(point: str, index: int) -> None:
        if (point, index) == ("after-replace-before-guard-check", 0):
            case["index_path"].write_bytes(raced_index)

    setattr(MIGRATION, "FAULT_HOOK", mutate_index)
    with pytest.raises(ApplyError):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])
    setattr(MIGRATION, "FAULT_HOOK", None)

    assert case["manifest_path"].read_bytes() == manifest_before
    assert case["index_path"].read_bytes() == raced_index
    assert not MIGRATION._journal_path().exists()


def test_phase3_bind_accepts_policy_disabled_no_write(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    estimate_path = case["artifacts"]["phase-3-estimate-writeback"]
    estimate = json.loads(estimate_path.read_text())
    estimate.update(
        {
            "disposition": "no_write_policy_disabled",
            "estimate_mutation_policy": {"value": False},
            "update_estimate_dispatch_expected": False,
            "update_estimate_dispatch_executed": False,
            "update_estimate_prompt_path": None,
            "update_estimate_prompt_sha256": None,
            "update_estimate_log_path": None,
            "update_estimate_log_sha256": None,
            "update_estimate_invocation_uuid": None,
            "write_verification_evidence": None,
        }
    )
    estimate["currentness"].pop("write_verification_sha256")
    _write_json(estimate_path, estimate)
    artifacts = dict(case["artifacts"])
    artifacts.pop("write-verification-evidence")
    replacement = copy.deepcopy(case["replacement_manifest"])
    replacement["phase_3_estimate_writeback_sha256"] = _digest(
        estimate_path.read_bytes()
    )
    request_path = _write_runtime_request(
        tmp_path / "requests" / "phase3-no-write.json",
        "phase3-bind",
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        replacement,
        case["replacement_index"],
        None,
        artifacts,
    )

    MIGRATION.apply_runtime_request(request_path, "phase3-bind")

    assert json.loads(case["manifest_path"].read_text()) == replacement


def test_phase3_bind_accepts_trusted_estimate_with_null_cold_start(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    source = json.loads(case["manifest_path"].read_text())
    source["cold_start_disposition_ref"] = None
    _write_json(case["manifest_path"], source)
    estimate_path = case["artifacts"]["phase-3-estimate-writeback"]
    estimate = json.loads(estimate_path.read_text())
    estimate["cold_start_disposition_ref"] = None
    estimate["currentness"].pop("cold_start_disposition_sha256")
    _write_json(estimate_path, estimate)
    artifacts = dict(case["artifacts"])
    artifacts.pop("cold-start-disposition")
    replacement = copy.deepcopy(case["replacement_manifest"])
    replacement["cold_start_disposition_ref"] = None
    replacement["phase_3_estimate_writeback_sha256"] = _digest(
        estimate_path.read_bytes()
    )
    request_path = _write_runtime_request(
        tmp_path / "requests" / "phase3-trusted-estimate.json",
        "phase3-bind",
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        replacement,
        case["replacement_index"],
        None,
        artifacts,
    )

    MIGRATION.apply_runtime_request(request_path, "phase3-bind")

    assert json.loads(case["manifest_path"].read_text()) == replacement


@pytest.mark.parametrize("confirmed", [True, False])
def test_cold_start_bind_validates_agent_answer_confirmation(
    confirmed: bool, tmp_path: Path
):
    case = _runtime_case(tmp_path, "cold-start-disposition-bind")
    answer_path = case["artifacts"]["cold-start-disposition"]
    _write_json(
        answer_path,
        {
            "schema_version": 1,
            "kind": "agent_answer",
            "answer": {"confirmed": confirmed, "selected_option_ids": ["A"]},
        },
    )
    request_path = _write_runtime_request(
        tmp_path / "requests" / f"cold-start-confirmed-{confirmed}.json",
        case["operation"],
        case["planning_root"],
        case["manifest_path"],
        case["index_path"],
        case["replacement_manifest"],
        case["replacement_index"],
        None,
        case["artifacts"],
    )

    result = MIGRATION.main([case["operation"], "--request", str(request_path)])

    assert result == (0 if confirmed else 2)


@pytest.mark.parametrize(
    "history",
    [
        [{"phase": "3", "status": "complete", "ts": "2026-07-19T00:00:00+00:00"}],
        [{"phase": "3", "status": "complete", "ts": "2026-07-19T00:00:00Z", "extra": True}],
        ["phase3"],
    ],
)
def test_phase3_bind_rejects_malformed_history_append(
    history: list[Any], tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase3-bind")
    request = json.loads(case["request_path"].read_text())
    request["replacement_manifest"]["phase_history"] = history
    _resign_runtime_request(case["request_path"], request)

    assert MIGRATION.main([case["operation"], "--request", str(case["request_path"])]) == 2


def test_phase3_bind_accepts_historical_producer_identities_after_live_file_drift(
    tmp_path: Path,
):
    case = _runtime_case(tmp_path, "phase3-bind")
    drifted = {
        role: path.read_bytes() + f"# live drift for {role}\n".encode()
        for role, path in case["artifacts"].items()
        if role in {"resolved-ticket-operator", "resolved-ticket-contract"}
    }
    for role, payload in drifted.items():
        case["artifacts"][role].write_bytes(payload)
    request_path = _rewrite_phase3_request(case, "live-producer-drift")

    MIGRATION.apply_runtime_request(request_path, "phase3-bind")

    assert json.loads(case["manifest_path"].read_text())[
        "phase_3_estimate_writeback_ref"
    ] == str(case["artifacts"]["phase-3-estimate-writeback"])
    assert all(
        case["artifacts"][role].read_bytes() == payload
        for role, payload in drifted.items()
    )


@pytest.mark.parametrize(
    "role", ["resolved-ticket-operator", "resolved-ticket-contract"]
)
def test_phase3_bind_rejects_wrong_historical_producer_hash(
    role: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase3-bind")
    request_path = _rewrite_phase3_request(
        case,
        f"wrong-{role}-hash",
        producer_role=role,
        producer_digest="0" * 64,
    )

    with pytest.raises(InputError, match=rf"{role} historical blob digest mismatch"):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")


def test_phase3_bind_rejects_uncommitted_only_producer_path(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    untracked_operator = case["repo_root"] / "agents" / "untracked-operator.md"
    untracked_operator.write_text("# untracked operator\n")
    request_path = _rewrite_phase3_request(
        case,
        "untracked-operator",
        producer_role="resolved-ticket-operator",
        producer_path=untracked_operator,
    )

    with pytest.raises(InputError, match="historical path is missing or ambiguous"):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")


def test_phase3_bind_rejects_valid_but_wrong_historical_commit(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    operator_path = case["artifacts"]["resolved-ticket-operator"]
    operator_path.write_text("# operator from the wrong commit\n")
    subprocess.run(
        ["git", "-C", str(case["repo_root"]), "add", "--", "agents/linear-operator.md"],
        check=True,
        env=GIT_ENV,
    )
    wrong_commit = _commit_fixture_repo(case["repo_root"], "wrong producer commit")
    request_path = _rewrite_phase3_request(
        case, "wrong-commit", branch_out_sha=wrong_commit
    )

    with pytest.raises(InputError, match="historical blob digest mismatch"):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")


@pytest.mark.parametrize("ref_kind", ["unknown", "blob"])
def test_phase3_bind_rejects_unknown_or_noncommit_branch_out(
    ref_kind: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase3-bind")
    if ref_kind == "unknown":
        branch_out_sha = "f" * 40
    else:
        branch_out_sha = subprocess.run(
            [
                "git",
                "-C",
                str(case["repo_root"]),
                "rev-parse",
                "HEAD:agents/linear-operator.md",
            ],
            check=True,
            text=True,
            capture_output=True,
            env=GIT_ENV,
        ).stdout.strip()
    request_path = _rewrite_phase3_request(
        case, f"{ref_kind}-branch-out", branch_out_sha=branch_out_sha
    )

    with pytest.raises(InputError, match="branch_out_sha is not an exact commit"):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")


@pytest.mark.parametrize("invalid_input", ["non-repository", "path-escape"])
def test_phase3_bind_rejects_nonrepository_and_escaped_producer_paths(
    invalid_input: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase3-bind")
    if invalid_input == "non-repository":
        non_repository = tmp_path / "not-a-repository"
        non_repository.mkdir()
        request_path = _rewrite_phase3_request(
            case, invalid_input, repo_root=non_repository
        )
        expected_error = ApplyError
        expected_message = "trusted evidence capture failed"
    else:
        escaped_path = tmp_path / "escaped-operator.md"
        escaped_path.write_text("# escaped operator\n")
        request_path = _rewrite_phase3_request(
            case,
            invalid_input,
            producer_role="resolved-ticket-operator",
            producer_path=escaped_path,
        )
        expected_error = InputError
        expected_message = "outside the declared repository"

    with pytest.raises(expected_error, match=expected_message):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")


@pytest.mark.parametrize("object_form", ["symlink", "gitlink"])
def test_phase3_bind_rejects_unsupported_historical_git_object_form(
    object_form: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase3-bind")
    repo_root = case["repo_root"]
    operator_path = case["artifacts"]["resolved-ticket-operator"]
    if object_form == "symlink":
        operator_path.unlink()
        operator_path.symlink_to("producer-target.md")
        subprocess.run(
            ["git", "-C", str(repo_root), "add", "--", "agents/linear-operator.md"],
            check=True,
            env=GIT_ENV,
        )
    else:
        target_commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
            env=GIT_ENV,
        ).stdout.strip()
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{target_commit},agents/linear-operator.md",
            ],
            check=True,
            env=GIT_ENV,
        )
    unsupported_commit = _commit_fixture_repo(
        repo_root, f"unsupported {object_form} producer identity"
    )
    if operator_path.is_symlink():
        operator_path.unlink()
        operator_path.write_text("# current regular operator\n")
    request_path = _rewrite_phase3_request(
        case, f"unsupported-{object_form}", branch_out_sha=unsupported_commit
    )

    with pytest.raises(InputError, match="historical object is not a regular blob"):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")


def test_phase3_bind_rejects_manifest_estimate_producer_disagreement(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    source_manifest = json.loads(case["manifest_path"].read_text())
    source_manifest["resolved_operator_sha256"] = "0" * 64
    _write_json(case["manifest_path"], source_manifest)
    request_path = _rewrite_phase3_request(case, "manifest-estimate-disagreement")

    with pytest.raises(InputError, match="does not match manifest resolved_operator_sha256"):
        MIGRATION.apply_runtime_request(request_path, "phase3-bind")


@pytest.mark.parametrize("role", ["phase-0-ticket-snapshot", "phase-3-proposal"])
def test_phase3_bind_keeps_current_source_validation_strict(role: str, tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    current_source = case["artifacts"][role]
    current_source.write_bytes(current_source.read_bytes() + b"stale\n")

    with pytest.raises(ApplyError, match="stale runtime artifact source identity"):
        MIGRATION.apply_runtime_request(case["request_path"], "phase3-bind")


def test_pre_pr_bind_rejects_stale_artifact_identity(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    estimate_path = case["artifacts"]["phase-3-estimate-writeback"]
    estimate_path.write_bytes(estimate_path.read_bytes() + b" ")

    assert MIGRATION.main(
        [case["operation"], "--request", str(case["request_path"])]
    ) == 3


def test_pre_pr_bind_recovery_rejects_substituted_guard_projection(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase3-bind")
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "journal-transition:0"
    command = [
        sys.executable,
        str(TOOL_DIR),
        case["operation"],
        "--request",
        str(case["request_path"]),
    ]
    assert subprocess.run(command, env=env, capture_output=True).returncode == 97
    journal = json.loads(MIGRATION._journal_path().read_text())
    journal["read_only_guards"][0]["source_sha256"] = "0" * 64
    _write_json(MIGRATION._journal_path(), journal)

    with pytest.raises(ApplyError, match="guard projection mismatch"):
        MIGRATION.recover_incomplete_transaction()
    assert MIGRATION._journal_path().exists()


def test_lifecycle_tool_readmes_and_operator_contract_name_both_pre_pr_operations():
    root = Path(__file__).resolve().parents[1]
    relative_paths = [
        "agents/implementation-pipeline-orchestrator.md",
        "contracts/operators/implementation-pipeline-orchestrator.yaml",
        "workflows/implementation-pipeline.md",
        "conventions/wu-session-lifecycle.md",
        "tools/wu-session-migration/README.md",
        "tools/README.md",
    ]
    contents = {path: (root / path).read_text() for path in relative_paths}

    for path, content in contents.items():
        assert "cold-start-disposition-bind" in content, path
        assert "phase3-bind" in content, path

    orchestrator = contents["agents/implementation-pipeline-orchestrator.md"]
    assert "before the separate terrain/risk/defer gate" in orchestrator
    assert "before Phase 4" in orchestrator
    assert "row_identity=null" in contents["conventions/wu-session-lifecycle.md"]
    assert "read-only guard" in contents["tools/wu-session-migration/README.md"]


def test_malformed_committed_recovery_journal_is_concise_and_retained(tmp_path: Path):
    state_root = MIGRATION._state_root()
    state_root.mkdir(parents=True)
    _write_json(
        MIGRATION._journal_path(),
        {"schema": MIGRATION.JOURNAL_SCHEMA, "phase": "committed", "ordered_targets": [{}]},
    )
    missing_plan = tmp_path / "missing-plan.json"

    result = subprocess.run(
        [sys.executable, str(TOOL_DIR), "apply", "--plan", str(missing_plan)],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 3
    assert "Traceback" not in result.stderr
    assert "recovery journal" in result.stderr
    assert MIGRATION._journal_path().exists()


@pytest.mark.parametrize("redirect", ["path", "backup_path", "replacement_path"])
def test_recovery_journal_redirected_paths_are_refused_and_retained(
    redirect: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase9-update")
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "journal-transition:0"
    command = [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(case["request_path"])]
    interrupted = subprocess.run(command, env=env, text=True, capture_output=True)
    assert interrupted.returncode == 97
    journal = json.loads(MIGRATION._journal_path().read_text())
    journal["ordered_targets"][0][redirect] = str(tmp_path / "redirected" / "session.json")
    _write_json(MIGRATION._journal_path(), journal)
    env.pop("WU_SESSION_MIGRATION_INTERRUPT")

    refused = subprocess.run(command, env=env, text=True, capture_output=True)

    assert refused.returncode == 3
    assert "Traceback" not in refused.stderr
    assert "projection mismatch" in refused.stderr
    assert MIGRATION._journal_path().exists()


@pytest.mark.parametrize("mutation", ["unknown-target-key", "duplicate-target", "substituted-plan"])
def test_recovery_journal_unknown_duplicate_and_substituted_bindings_are_refused(
    mutation: str, tmp_path: Path
):
    case = _runtime_case(tmp_path, "phase9-update")
    env = os.environ.copy()
    env["WU_SESSION_MIGRATION_INTERRUPT"] = "journal-transition:0"
    command = [sys.executable, str(TOOL_DIR), case["operation"], "--request", str(case["request_path"])]
    assert subprocess.run(command, env=env, capture_output=True).returncode == 97
    if mutation == "substituted-plan":
        request = json.loads(case["request_path"].read_text())
        request["replacement_manifest"]["phase_history"].append("substituted")
        _write_json(case["request_path"], request)
    else:
        journal = json.loads(MIGRATION._journal_path().read_text())
        if mutation == "unknown-target-key":
            journal["ordered_targets"][0]["extra"] = True
        else:
            journal["ordered_targets"].append(copy.deepcopy(journal["ordered_targets"][0]))
        _write_json(MIGRATION._journal_path(), journal)
    env.pop("WU_SESSION_MIGRATION_INTERRUPT")

    refused = subprocess.run(command, env=env, text=True, capture_output=True)

    assert refused.returncode == 3
    assert "Traceback" not in refused.stderr
    assert MIGRATION._journal_path().exists()


def test_held_parent_retarget_after_final_source_check_changes_no_substitute_path(tmp_path: Path):
    case = _runtime_case(tmp_path, "phase0-init")
    original_parent = case["manifest_path"].parent
    held_parent = original_parent.with_name("AGE-260-held")
    substitute_payload = b'{"substitute": true}\n'

    def retarget(point: str, index: int) -> None:
        if (point, index) != ("after-final-source-check", 0):
            return
        original_parent.rename(held_parent)
        original_parent.mkdir()
        (original_parent / "session.json").write_bytes(substitute_payload)

    setattr(MIGRATION, "FAULT_HOOK", retarget)
    with pytest.raises(ApplyError, match="held parent identity changed"):
        MIGRATION.apply_runtime_request(case["request_path"], case["operation"])

    assert (original_parent / "session.json").read_bytes() == substitute_payload
    assert not (held_parent / "session.json").exists()
    assert MIGRATION._journal_path().exists()


def _full_test_oid(value: str) -> str:
    return value if len(value) in {40, 64} else value + ("0" * (40 - len(value)))


def _frozen_real_squash_cases() -> list[dict[str, Any]]:
    document = json.loads(FROZEN_REAL_SQUASH_EVIDENCE.read_text())
    assert document["schema"] == "age-260-frozen-squash-evidence-v1"
    return document["cases"]


def _frozen_real_squash_record(case: dict[str, Any]) -> dict[str, object]:
    return _evidence(
        case["pr_url"],
        case["branch"],
        case["base_ref_name"],
        state="MERGED",
        head=case["head_sha"],
        merge_sha=case["merge_sha"],
        merged_at=case["merged_at"],
        parents=[case["parent_sha"]],
        merge_method=case["merge_method"],
        merge_method_command=case["merge_method_command"],
        branch_out=(case["branch_out_sha"], case["branch_out_sha"], Path(case["repo_root"])),
    )


@pytest.mark.parametrize("case", _frozen_real_squash_cases(), ids=lambda row: row["branch"])
def test_frozen_real_one_parent_squash_evidence_is_accepted(case: dict[str, Any]):
    evidence = MIGRATION._derive_and_validate_evidence(_frozen_real_squash_record(case))

    assert evidence["state"] == "MERGED"
    assert evidence["merge_shape"] == "SQUASH"
    assert evidence["merge_sha"] == case["merge_sha"]
    assert evidence["merge_parents"] == [case["parent_sha"]]
    assert evidence["merge_sha"] != evidence["head_sha"]


def _real_evidence_document(inventory: dict[str, Any]) -> dict[str, Any]:
    frozen = {case["pr_url"]: case for case in _frozen_real_squash_cases()}
    records: dict[str, Any] = {}
    for candidate in inventory["migration_cohort"]:
        if candidate["explicit_refusal_reasons"]:
            continue
        if candidate["pr_url"] in frozen:
            records[candidate["pr_url"]] = _frozen_real_squash_record(frozen[candidate["pr_url"]])
            continue
        manifest_path = Path(candidate["manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        repo_root = Path(manifest.get("repo_root") or MIGRATION._manifest_repo_root(manifest_path))
        head = _full_test_oid(candidate["persisted_head_sha"])
        branch_out = candidate["branch_out_sha"]
        base = (
            candidate.get("persisted_or_derived_base_branch")
            or manifest.get("base_branch")
            or "main"
        )
        records[candidate["pr_url"]] = _evidence(
            candidate["pr_url"],
            candidate["branch"],
            base,
            head=head,
            branch_out=(branch_out, _full_test_oid(branch_out), repo_root),
        )
    return {
        "schema": MIGRATION.PR_EVIDENCE_SCHEMA,
        "reviewed_inventory_sha256": REAL_INVENTORY_SHA256,
        "prs": records,
    }


def _real_conflict_resolutions(
    inventory: dict[str, Any], evidence_document: dict[str, Any]
) -> dict[str, Any]:
    context = MIGRATION._validate_inventory(inventory, REAL_INVENTORY)
    resolutions: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in inventory["migration_cohort"]:
        manifest = context["documents"][Path(candidate["manifest_path"])]
        locator_rows = MIGRATION._resolve_candidate_locators(
            candidate,
            context["documents"],
            context["inventory_rows"],
        )
        conflicts = MIGRATION._identity_conflicts(candidate, manifest, locator_rows, None)
        record = evidence_document["prs"].get(candidate["pr_url"])
        if record is not None:
            evidence = MIGRATION._derive_and_validate_evidence(record)
            conflicts.extend(
                MIGRATION._identity_conflicts(candidate, manifest, locator_rows, evidence)
            )
        rows = dict(locator_rows)
        for locator, _field in conflicts:
            if locator is None or locator in resolutions:
                continue
            source_row = rows[locator]
            resolutions[locator] = {
                "index_path": locator[0],
                "row_locator": locator[1],
                "conflict_resolution": True,
                "owner": "manager",
                "reason": "Frozen read-only integration fixture resolves the reviewed source conflict.",
                "discarded_row_sha256": _digest(_canonical_bytes(source_row)),
                "retained_identity": {
                    "manifest_path": candidate.get("manifest_path"),
                    "ticket_id": candidate.get("ticket_id"),
                    "ticket_system": candidate.get("ticket_system"),
                    "branch": candidate.get("branch"),
                    "pr_url": candidate.get("pr_url"),
                    "head_sha": candidate.get("persisted_head_sha"),
                    "base_branch": candidate.get("persisted_or_derived_base_branch"),
                },
            }
    return {
        "schema": MIGRATION.CONFLICT_RESOLUTION_SCHEMA,
        "resolutions": list(resolutions.values()),
    }


@pytest.mark.skipif(not REAL_INVENTORY.is_file(), reason="reviewed AGE-260 inventory unavailable")
def test_real_inventory_supports_evidence_complete_active_cohort_and_is_read_only(
    tmp_path: Path,
):
    inventory = json.loads(REAL_INVENTORY.read_text())
    evidence_path = tmp_path / "real-evidence.json"
    dispositions_path = tmp_path / "real-dispositions.json"
    resolutions_path = tmp_path / "real-resolutions.json"
    evidence_document = _real_evidence_document(inventory)
    _write_json(evidence_path, evidence_document)
    refusal_paths = [
        row["manifest_path"]
        for row in inventory["migration_cohort"]
        if row["explicit_refusal_reasons"]
    ]
    _write_json(
        dispositions_path,
        {
            "schema": MIGRATION.DISPOSITION_SCHEMA,
            "dispositions": [
                {
                    "manifest_path": path,
                    "reason": "Read-only integration fixture accepted-breakage proof.",
                    "accepted_breakage": True,
                    "owner": "manager",
                }
                for path in refusal_paths
            ],
        },
    )
    resolutions_document = _real_conflict_resolutions(inventory, evidence_document)
    _write_json(resolutions_path, resolutions_document)
    source_paths = [Path(row["path"]) for row in inventory["manifests"]] + [
        Path(row["path"]) for row in inventory["index_files"]
    ]
    before = {path: (_digest(path.read_bytes()), path.stat().st_ino) for path in source_paths}

    first = build_plan(
        REAL_INVENTORY, evidence_path, dispositions_path, REAL_INVENTORY_SHA256, resolutions_path,
        tmp_path / "real-plan.json"
    )
    second = build_plan(
        REAL_INVENTORY, evidence_path, dispositions_path, REAL_INVENTORY_SHA256, resolutions_path,
        tmp_path / "real-plan.json"
    )

    assert first == second
    assert first["validated_counts"] == MIGRATION.EXPECTED_COUNTS
    assert len(first["rows"]) == 42
    assert len(first["source_index_paths"]) == 7
    cloud = next(row for row in first["rows"] if row["branch"] == "CLOUD-259-session-store-scoped-acquisition")
    assert cloud["verdict"] == "migrated-open"
    resume_fix = next(row for row in first["rows"] if row["branch"] == "s11-m2c-resume-fix")
    assert resume_fix["verdict"] == "excluded-accepted-breakage"
    assert first["eligible"] is True
    merged = {row["branch"]: row for row in first["rows"] if row["verdict"] == "migrated-merged"}
    assert set(merged) == {case["branch"] for case in _frozen_real_squash_cases()}
    assert {
        branch: row["pre_merge_base_sha"] for branch, row in merged.items()
    } == {case["branch"]: case["parent_sha"] for case in _frozen_real_squash_cases()}
    proposed_active = [
        write["replacement"] for write in first["writes"] if write["path"].endswith("sessions.active-wake.json")
    ]
    assert len(proposed_active) == 7
    assert sum(len(index["sessions"]) for index in proposed_active) == 39
    assert {row["verdict"] for row in first["rows"]} == {
        "migrated-open",
        "migrated-merged",
        "excluded-accepted-breakage",
    }
    assert {path: (_digest(path.read_bytes()), path.stat().st_ino) for path in source_paths} == before
