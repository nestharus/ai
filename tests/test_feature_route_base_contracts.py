from __future__ import annotations

import json
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_ROUTE_SPEC = importlib.util.spec_from_file_location(
    "feature_route_manifest", REPO_ROOT / "tools/feature_route_manifest.py"
)
assert _ROUTE_SPEC and _ROUTE_SPEC.loader
_ROUTE_MODULE = importlib.util.module_from_spec(_ROUTE_SPEC)
_ROUTE_SPEC.loader.exec_module(_ROUTE_MODULE)
RouteManifestError = _ROUTE_MODULE.RouteManifestError
normalize_successor_manifest = _ROUTE_MODULE.normalize_successor_manifest
normalize_ticket_route_map = _ROUTE_MODULE.normalize_ticket_route_map
normalize_route_source = _ROUTE_MODULE.normalize_route_source
_CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "operational_contracts", REPO_ROOT / "tools/operational_contracts.py"
)
assert _CONTRACT_SPEC and _CONTRACT_SPEC.loader
_CONTRACT_MODULE = importlib.util.module_from_spec(_CONTRACT_SPEC)
_CONTRACT_SPEC.loader.exec_module(_CONTRACT_MODULE)
compute_plan_hash = _CONTRACT_MODULE.compute_plan_hash
cleanup_pr_review_worktree = _CONTRACT_MODULE.cleanup_pr_review_worktree
extract_provider_payload = _CONTRACT_MODULE.extract_provider_payload
initialize_pr_review_run = _CONTRACT_MODULE.initialize_pr_review_run
validate_package_execution = _CONTRACT_MODULE.validate_package_execution
require_pr_currentness = _CONTRACT_MODULE.require_pr_currentness
validate_pr_currentness = _CONTRACT_MODULE.validate_pr_currentness
validate_ready_state_restoration = _CONTRACT_MODULE.validate_ready_state_restoration
validate_refactoring_dispatch = _CONTRACT_MODULE.validate_refactoring_dispatch
validate_route_artifact_lineage = _CONTRACT_MODULE.validate_route_artifact_lineage
validate_route_attempt_proof = _CONTRACT_MODULE.validate_route_attempt_proof
validate_route_attempt_transition = _CONTRACT_MODULE.validate_route_attempt_transition
validate_route_process_proof = _CONTRACT_MODULE.validate_route_process_proof
render_process_tree_audit_report = _CONTRACT_MODULE.render_process_tree_audit_report
validate_ticket_operation_result = _CONTRACT_MODULE.validate_ticket_operation_result
validate_process_tree_audit_report = _CONTRACT_MODULE.validate_process_tree_audit_report
validate_test_audit_nested_proof = _CONTRACT_MODULE.validate_test_audit_nested_proof
validate_test_audit_result = _CONTRACT_MODULE.validate_test_audit_result
_route_attempt_names = _CONTRACT_MODULE._route_attempt_names

OPERATOR_NAMES = (
    "apply-gate-set",
    "feature-orchestrator",
    "implementation-pipeline-orchestrator",
    "jira-operator",
    "linear-operator",
    "pr-review-operator",
    "pr-writer",
    "process-tree-auditor",
    "refactoring-commit-history-orchestrator",
    "refactoring-orchestrator",
    "test-audit-gate",
    "wu-session-resumer",
)
WORKFLOW_NAMES = (
    "agents-cli",
    "apply-gate-set",
    "feature-development",
    "implementation-pipeline",
    "pr-review",
    "refactoring",
    "refactoring-commit-history",
    "wu-session-wake",
)
FEATURE_INPUT_NAMES = {
    "feature_id",
    "feature_scope_path",
    "repo_root",
    "trunk_branch",
    "feature_branch",
    "feature_worktree_path",
    "child_worktrees_root",
    "planning_dir",
    "scratch_dir",
    "local_coverage_command",
    "scoped_ticket_list",
    "ticket_route_map",
    "successor_manifest_path",
    "ticket_system",
    "jira_url",
    "jira_project",
    "jira_account_email",
    "linear_team_key",
    "linear_project_id",
    "manager_flavor",
    "acceptance_evidence_paths",
    "prototype_dossier_path",
    "qa_operator",
    "qa_target_descriptor",
    "evidence_pack_context",
    "post_merge_owner",
    "audit_history_path",
}
FEATURE_ARTIFACTS = {
    "${planning_dir}/route-manifest.json",
    "${scratch_dir}/route-dispatch-evidence.json",
    "${planning_dir}/ticket-pr-merge-index.json",
    "${planning_dir}/route-attempt-index.json",
    "${planning_dir}/feature-process-index.json",
    "${scratch_dir}/feature-process/prompts/<ticket_slug>-attempt-<NNNN>.prompt.md",
    "${scratch_dir}/feature-process/logs/<ticket_slug>-attempt-<NNNN>.log",
    "${scratch_dir}/feature-process/outputs/<ticket_slug>-attempt-<NNNN>.output.json",
    "${scratch_dir}/feature-process/expected/<ticket_slug>-attempt-<NNNN>.pre-audit.expected.json",
    "${scratch_dir}/feature-process/dispatch/<ticket_slug>-attempt-<NNNN>.pre-audit.dispatch.json",
    "${scratch_dir}/feature-process/traces/<ticket_slug>-attempt-<NNNN>.pre-audit.trace.json",
    "${scratch_dir}/feature-process/auditors/<ticket_slug>-attempt-<NNNN>.prompt.md",
    "${scratch_dir}/feature-process/auditors/<ticket_slug>-attempt-<NNNN>.log",
    "${scratch_dir}/feature-process/auditors/<ticket_slug>-attempt-<NNNN>.output.md",
    "${scratch_dir}/feature-process/expected/<ticket_slug>-attempt-<NNNN>.final.expected.json",
    "${scratch_dir}/feature-process/dispatch/<ticket_slug>-attempt-<NNNN>.final.dispatch.json",
    "${scratch_dir}/feature-process/traces/<ticket_slug>-attempt-<NNNN>.final.trace.json",
    "${planning_dir}/feature-process/<ticket_slug>-attempt-<NNNN>.audit.md",
    "${planning_dir}/feature-process/<ticket_slug>-attempt-<NNNN>.binding.json",
    "${planning_dir}/route-process-validation/<ticket_slug>-attempt-<NNNN>.json",
    "${planning_dir}/route-attempt-outcomes/<ticket_slug>-attempt-<NNNN>.json",
    "${planning_dir}/route-attempt-proofs/<ticket_slug>-attempt-<NNNN>.proof.json",
    "${scratch_dir}/feature-expected-process.json",
    "${scratch_dir}/feature-process-tree.json",
    "${planning_dir}/feature-process-tree-audit.md",
    "${planning_dir}/route-evidence/<ticket_slug>-attempt-<NNNN>.evidence.json",
    "${planning_dir}/route-acceptance/<ticket_slug>-attempt-<NNNN>.acceptance.json",
    "${planning_dir}/route-currentness/<ticket_slug>-attempt-<NNNN>-pre-ready.json",
    "${planning_dir}/route-currentness/<ticket_slug>-attempt-<NNNN>-post-ready.json",
    "${planning_dir}/route-ready-restoration/<ticket_slug>-attempt-<NNNN>.json",
    "${planning_dir}/route-authorization/<ticket_slug>-attempt-<NNNN>.json",
    "${planning_dir}/feature-evidence-index.json",
    "${planning_dir}/feature-integrated-review-input.json",
    "${planning_dir}/integrated-scope-verdict.md",
    "${planning_dir}/qa-verdict.md",
    "${planning_dir}/feature-final-evidence.json",
    "${planning_dir}/final-pr-handoff.json",
    "${planning_dir}/feature-outcome.json",
    "${audit_history_path} from review round two onward",
}
REFACTOR_INPUT_NAMES = {
    "jira_issue_key",
    "linear_issue_key",
    "wu_brief_path",
    "wu_brief_context_path",
    "ticket_system",
    "jira_url",
    "jira_project",
    "jira_account_email",
    "linear_team_key",
    "linear_project_id",
    "target_list",
    "repo_root",
    "branch_name",
    "worktree_path",
    "planning_dir",
    "scratch_dir",
    "local_coverage_command",
    "feature_routed",
    "trunk_branch",
    "protected_branches",
    "integration_branch_ref",
    "slice_bounds",
    "shim_placement_parameters",
    "prior_refactor_evidence_pointers",
    "shim_registry_path",
    "audit_history_path",
    "manager_flavor",
}
REFACTOR_ARTIFACTS = {
    "${planning_dir}/refactoring-route-result.json",
    "${planning_dir}/refactoring-auditor-index.json",
    "${planning_dir}/refactoring-currentness/<slice_identity>.json",
    "${planning_dir}/refactoring-ready-restoration/<slice_identity>.json",
    "${planning_dir}/refactoring-dispatch-validation.json",
    "${planning_dir}/refactoring-process-tree-audit-pre-merge.md",
    "${planning_dir}/refactoring-process-tree-audit.md",
    "${planning_dir}/refactoring-audit-history.md from revise/review round two onward",
    "${scratch_dir}/refactoring-dispatch-evidence-pre-merge.json",
    "${scratch_dir}/refactoring-dispatch-plan.json",
    "${scratch_dir}/refactoring-expected-process-pre-merge.json",
    "${scratch_dir}/refactoring-process-tree-pre-merge.json",
    "${scratch_dir}/refactoring-dispatch-evidence.json",
    "${scratch_dir}/refactoring-expected-process.json",
    "${scratch_dir}/refactoring-process-tree.json",
}
REFACTOR_AUDITORS = {
    "cohesion-auditor",
    "coupling-auditor",
    "function-classification-auditor",
    "push-pull-auditor",
    "validation-integrity-auditor",
}
REAL_AGE255_MANIFEST = Path(
    "/home/nes/projects/agent-runner/planning/"
    "hourly-suspicious-process-investigator-feature/age-255/decomposition/"
    "successor-manifest.json"
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _load_yaml(relative_path: str) -> dict[str, Any]:
    parsed = yaml.load(_read(relative_path), Loader=_UniqueKeyLoader)
    assert isinstance(parsed, dict), f"{relative_path} must parse as a YAML mapping"
    return parsed


def _operator_contract(name: str) -> dict[str, Any]:
    text = _read(f"agents/{name}.md")
    match = re.search(r"(?ms)^## Contract\s*$.*?^```yaml\s*$\n(.*?)^```\s*$", text)
    assert match, f"agents/{name}.md must contain a fenced YAML Contract"
    parsed = yaml.load(match.group(1), Loader=_UniqueKeyLoader)
    assert isinstance(parsed, dict)
    return parsed


def _workflow_dispatch_contract(name: str) -> dict[str, Any]:
    text = _read(f"workflows/{name}.md")
    assert text.startswith("---\n")
    closing = text.find("\n---\n", 4)
    assert closing > 0, f"workflows/{name}.md must close its YAML frontmatter"
    frontmatter = yaml.load(text[4:closing], Loader=_UniqueKeyLoader)
    assert isinstance(frontmatter, dict)
    contract = frontmatter.get("workflow_dispatch_contract")
    assert isinstance(contract, dict)
    return contract


def _section(relative_path: str, heading: str) -> str:
    text = _read(relative_path)
    marker = f"{heading}\n"
    assert text.count(marker) == 1, f"expected one {heading} in {relative_path}"
    start = text.index(marker) + len(marker)
    level = len(heading) - len(heading.lstrip("#"))
    match = re.search(rf"(?m)^#{{1,{level}}} (?!#)", text[start:])
    end = start + match.start() if match else len(text)
    return text[start:end]


def _between(relative_path: str, start_marker: str, end_marker: str) -> str:
    text = _read(relative_path)
    assert text.count(start_marker) == 1
    assert text.count(end_marker) == 1
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def _fenced_yaml_section(relative_path: str, heading: str) -> dict[str, Any]:
    section = _section(relative_path, heading)
    match = re.search(r"(?ms)^```yaml\s*$\n(.*?)^```\s*$", section)
    assert match, f"{heading} must contain one YAML fence"
    parsed = yaml.load(match.group(1), Loader=_UniqueKeyLoader)
    assert isinstance(parsed, dict)
    return parsed


def _input(contract: dict[str, Any], name: str) -> dict[str, Any]:
    inputs = contract.get("inputs")
    assert isinstance(inputs, list)
    matches = [item for item in inputs if isinstance(item, dict) and item.get("name") == name]
    assert len(matches) == 1, f"expected exactly one {name} input"
    return matches[0]


def _provider_bundle(
    *,
    base_sha: str = "a0" * 20,
    head_sha: str = "b0" * 20,
    base_name: str = "feature/hourly-suspicious-process-investigator",
    head_name: str = "route/age-260",
    state: str = "OPEN",
    is_draft: bool = True,
) -> dict[str, Any]:
    return {
        "pr_url": "https://github.com/example/repo/pull/260",
        "pr_number": 260,
        "state": state,
        "is_draft": is_draft,
        "base_ref_name": base_name,
        "base_ref_oid": base_sha,
        "head_ref_name": head_name,
        "head_ref_oid": head_sha,
    }


_RUNNER_UUID = "9e69e8cc-616d-4640-bf1d-96f5391b1a2e"
_SECOND_RUNNER_UUID = "1b54b457-50cb-4f14-a6d0-b2bdfd4322ab"
_LOCAL_COVERAGE_COMMAND = "coverage-tool --exact project configuration"
_LOCAL_COVERAGE_COMMAND_SHA256 = hashlib.sha256(
    _LOCAL_COVERAGE_COMMAND.encode("utf-8")
).hexdigest()


def _runner_envelope(
    payload: str,
    *,
    invocation_uuid: str = _RUNNER_UUID,
    result_uuid: str | None = None,
    status: str = "succeeded",
    success: bool = True,
    exit_code: int = 0,
) -> bytes:
    invocation = json.dumps(
        {"source": "fixture-provider", "id": invocation_uuid},
        separators=(",", ":"),
    )
    result = json.dumps(
        {
            "error_category": None,
            "exit_code": exit_code,
            "finished_at": "2026-07-18T00:00:00Z",
            "id": result_uuid or invocation_uuid,
            "status": status,
            "success": success,
            "terminal_reason": None,
        },
        separators=(",", ":"),
    )
    return (
        f"OULIPOLY_INVOCATION={invocation}\n"
        f"{payload}"
        f"OULIPOLY_RESULT={result}\n"
    ).encode()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _refactoring_dispatch_plan(**overrides: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "schema": "refactoring-dispatch-plan-v1",
        "ticket_pr_cardinality": "exactly-one",
        "branch_name": "route/age-260",
        "trunk_branch_name": "main",
        "integration_branch_name": "feature/integration",
        "feature_routed": True,
        "local_coverage_command": _LOCAL_COVERAGE_COMMAND,
        "protected_branches": ["main", "feature/integration"],
        "worktree_path": "/tmp/worktrees/age-260",
        "planning_dir": "/tmp/planning/age-260",
        "scratch_dir": "/tmp/scratch/age-260",
    }
    plan.update(overrides)
    plan.setdefault(
        "children",
        [
            {
                "branch_name": plan["branch_name"],
                "local_coverage_command": plan["local_coverage_command"],
                "worktree_path": plan["worktree_path"],
                "planning_dir": plan["planning_dir"],
                "scratch_dir": plan["scratch_dir"],
                "ticket_pr_cardinality": "exactly-one",
            }
        ],
    )
    return plan


def _package_source_request() -> dict[str, Any]:
    gates = [
        "implementation-pipeline-phase-4",
        "implementation-pipeline-phase-6",
        "implementation-pipeline-phase-7",
        "implementation-pipeline-phase-8",
    ]
    request: dict[str, Any] = {
        "schema": "refactoring-commit-history-package-source-request-v1",
        "ticket_system": "linear",
        "target": "tools/example.py",
        "target_identity_sha256": "1" * 64,
        "history_base_ref": "refs/tags/refactor-1",
        "history_base_sha": "2" * 40,
        "history_frontier_ref": "refs/heads/main",
        "history_frontier_sha": "3" * 40,
        "trunk_branch": "main",
        "integration_branch_ref": "refactor/integration",
        "integration_branch_sha": "4" * 40,
        "protected_branches": ["main", "refactor/integration"],
        "selected_package_ids": ["package-a", "package-b"],
        "package_plan": [
            {
                "package_id": "package-a",
                "target_list": '["src/a.py"]',
                "slice_bounds": '{"surface":"a"}',
                "refactor_intent": "no-intended-behavior-change",
                "milestone_evidence_ref": "/tmp/refactor/evidence/milestone.json",
                "degradation_evidence_ref": "/tmp/refactor/evidence/degradation.json",
                "inherited_gate_obligations": gates,
                "dependencies": [],
                "acceptance_criteria": ["preserves contract a"],
                "branch_name": "refactor/package-a",
                "worktree_path": "/tmp/refactor/worktrees/package-a",
                "planning_dir": "/tmp/refactor/planning/package-a",
                "scratch_dir": "/tmp/refactor/scratch/package-a",
                "route_result_path": "/tmp/refactor/planning/package-a/refactoring-route-result.json",
            },
            {
                "package_id": "package-b",
                "target_list": '["src/b.py"]',
                "slice_bounds": '{"surface":"b"}',
                "refactor_intent": "no-intended-behavior-change",
                "milestone_evidence_ref": "/tmp/refactor/evidence/milestone.json",
                "degradation_evidence_ref": "/tmp/refactor/evidence/degradation.json",
                "inherited_gate_obligations": gates,
                "dependencies": ["package-a"],
                "acceptance_criteria": ["preserves contract b"],
                "branch_name": "refactor/package-b",
                "worktree_path": "/tmp/refactor/worktrees/package-b",
                "planning_dir": "/tmp/refactor/planning/package-b",
                "scratch_dir": "/tmp/refactor/scratch/package-b",
                "route_result_path": "/tmp/refactor/planning/package-b/refactoring-route-result.json",
            },
        ],
        "source_hashes": {
            "milestone-evidence": "5" * 64,
            "degradation-inventory": "6" * 64,
        },
    }
    request["plan_hash"] = compute_plan_hash(request)
    return request


def _current_package_identity(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "refactoring-commit-history-current-identity-v1",
        **{
            field: request[field]
            for field in (
                "target",
                "target_identity_sha256",
                "history_base_ref",
                "history_base_sha",
                "history_frontier_ref",
                "history_frontier_sha",
                "trunk_branch",
                "integration_branch_ref",
                "integration_branch_sha",
                "protected_branches",
            )
        },
    }


def _package_ticket_map(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "refactoring-commit-history-package-ticket-source-v1",
        "plan_hash": request["plan_hash"],
        "ticket_system": "linear",
        "packages": [
            {
                "package_id": "package-a",
                "ticket_source": {"linear_issue_key": "AGE-301"},
            },
            {
                "package_id": "package-b",
                "ticket_source": {"linear_issue_key": "AGE-302"},
            },
        ],
    }


def _attempt_roots(tmp_path: Path) -> dict[str, str]:
    return {"proof_envelope_root": str(tmp_path / "planning" / "route-attempt-proofs")}


def _route_attempt(
    roots: dict[str, str],
    *,
    ticket_id: str,
    attempt_number: int,
    owning_route: str,
    dispatch_base_sha: str,
    reviewed_head_sha: str,
    state: str,
    transition_sha: str,
    dependency_proofs: list[dict[str, Any]] | None = None,
    pre_merge_head_sha: str | None = None,
    feature_branch: str = "feature/hourly-suspicious-process-investigator",
    local_coverage_command_sha256: str = _LOCAL_COVERAGE_COMMAND_SHA256,
) -> dict[str, Any]:
    slug, stem = _route_attempt_names(ticket_id, attempt_number)
    merged = state == "VERIFIED_MERGED"
    proof_root = Path(roots["proof_envelope_root"])
    proof_path = proof_root / f"{stem}.proof.json"
    _attempt_proof_fixture(
        proof_path,
        ticket_id=ticket_id,
        attempt_number=attempt_number,
        owning_route=owning_route,
        feature_branch=feature_branch,
        state=state,
        dispatch_base_sha=dispatch_base_sha,
        reviewed_head_sha=reviewed_head_sha,
        pre_merge_feature_sha=dispatch_base_sha if merged else transition_sha,
        pre_merge_head_sha=pre_merge_head_sha or reviewed_head_sha,
        merge_sha=transition_sha if merged else None,
        resulting_feature_sha=transition_sha if merged else None,
        local_coverage_command_sha256=local_coverage_command_sha256,
    )
    return {
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": owning_route,
        "dependency_proofs": dependency_proofs or [],
        "dispatch_base_sha": dispatch_base_sha,
        "reviewed_base_sha": dispatch_base_sha,
        "reviewed_head_sha": reviewed_head_sha,
        "pre_merge_feature_sha": dispatch_base_sha if merged else transition_sha,
        "pre_merge_head_sha": pre_merge_head_sha or reviewed_head_sha,
        "merge_sha": transition_sha if merged else None,
        "resulting_feature_sha": transition_sha if merged else None,
        "process_verdict": "PASS",
        "state": state,
        "proof_envelope_path": str(proof_path),
        "proof_envelope_sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest(),
    }


def _route_attempt_index(
    tmp_path: Path,
    manifest: dict[str, Any],
    attempts: list[dict[str, Any]],
    *,
    initial_feature_sha: str,
    current_feature_sha: str,
    complete: bool = True,
    accepted_attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if accepted_attempts is None:
        accepted_attempts = []
        for attempt in attempts:
            if attempt["state"] != "VERIFIED_MERGED":
                continue
            accepted_attempts.append(
                {
                    "ticket_id": attempt["ticket_id"],
                    "attempt_number": attempt["attempt_number"],
                    "merge_sha": attempt["merge_sha"],
                    "reachable_from_current_feature": True,
                }
            )
    return {
        "schema": "feature-route-attempt-index-v1",
        "state": "COMPLETE" if complete else "IN_PROGRESS",
        "feature_branch": manifest["feature_branch"],
        "initial_feature_sha": initial_feature_sha,
        "current_feature_sha": current_feature_sha,
        "artifact_roots": _attempt_roots(tmp_path),
        "attempts": attempts,
        "accepted_attempts": accepted_attempts,
    }


def _write_json_fixture(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _test_audit_result_fixture(tmp_path: Path) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root_uuid = _RUNNER_UUID
    base_sha = "a0" * 20
    head_sha = "b0" * 20
    node_specs = {
        "spec-alignment": (
            "ad-hoc-spec-alignment",
            "gpt-high",
            "SPEC",
            "10000000-0000-4000-8000-000000000001",
        ),
        "test-quality": (
            "coverage-auditor",
            "gpt-xhigh",
            "QUALITY",
            "10000000-0000-4000-8000-000000000002",
        ),
        "coverage-delta": (
            "coverage-analyzer",
            "gpt-high",
            "COVERAGE",
            "10000000-0000-4000-8000-000000000003",
        ),
    }
    expected_nodes: list[dict[str, Any]] = []
    child_artifacts: list[dict[str, Any]] = []
    for node_id, (operator, model, stem, invocation_uuid) in node_specs.items():
        prompt = tmp_path / f"TEST_AUDIT_{stem}.prompt.md"
        log = tmp_path / f"TEST_AUDIT_{stem}.log"
        output = tmp_path / f"TEST_AUDIT_{stem}.md"
        metadata_path = tmp_path / f"TEST_AUDIT_{stem}.extraction.json"
        prompt.write_text(f"# {node_id}\n", encoding="utf-8")
        log.write_bytes(
            _runner_envelope(
                f"Verdict: PASS\n\n# {node_id}\n",
                invocation_uuid=invocation_uuid,
            )
        )
        metadata = extract_provider_payload(log, output)
        _write_json_fixture(metadata_path, metadata)
        expected_nodes.append(
            {
                "id": node_id,
                "required": True,
                "operator_or_role": operator,
                "model": model,
                "parent": "root",
                "prompt_path": str(prompt),
                "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                "log_path": str(log),
                "log_sha256_join_field": "log_sha256",
                "canonical_output_path": str(output),
                "canonical_output_sha256_join_field": "canonical_output_sha256",
                "extraction_metadata_path": str(metadata_path),
                "extraction_metadata_sha256_join_field": "extraction_metadata_sha256",
                "provider_source_join_field": "provider_source",
                "output_mode": "stdout-extracted",
            }
        )
        child_artifacts.append(
            {
                "id": node_id,
                "invocation_uuid": invocation_uuid,
                "parent_invocation_uuid": root_uuid,
                "operator_or_role": operator,
                "model": model,
                "provider_source": metadata["provider_source"],
                "prompt_path": str(prompt),
                "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                "log_path": str(log),
                "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                "canonical_output_path": str(output),
                "canonical_output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "extraction_metadata_path": str(metadata_path),
                "extraction_metadata_sha256": hashlib.sha256(
                    metadata_path.read_bytes()
                ).hexdigest(),
                "output_mode": "stdout-extracted",
            }
        )

    expected_path = tmp_path / "TEST_AUDIT_EXPECTED_PROCESS.json"
    expected = {
        "schema": "test-audit-expected-process-v2",
        "test_audit_invocation_uuid": root_uuid,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "nodes": expected_nodes,
    }
    _write_json_fixture(expected_path, expected)
    dispatch_path = tmp_path / "TEST_AUDIT_DISPATCH_EVIDENCE.json"
    dispatch = {
        "schema": "test-audit-dispatch-evidence-v2",
        "test_audit_invocation_uuid": root_uuid,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "expected_process_path": str(expected_path),
        "expected_process_sha256": hashlib.sha256(expected_path.read_bytes()).hexdigest(),
        "nodes": child_artifacts,
    }
    _write_json_fixture(dispatch_path, dispatch)
    trace_path = tmp_path / "TEST_AUDIT_PROCESS_TREE.json"
    _write_json_fixture(
        trace_path,
        {
            "requested_id": root_uuid,
            "generated_at": "2026-07-18T00:00:00Z",
            "root": {
                "invocation": {
                    "row_id": 1,
                    "id": root_uuid,
                    "agent_runner_invocation_id": root_uuid,
                    "source": "fixture-provider",
                    "model_name": "gpt-high",
                    "parent_id": None,
                    "status": "running",
                    "success": None,
                    "exit_code": None,
                    "error_category": None,
                    "terminal_reason": None,
                    "started_at": "2026-07-18T00:00:00Z",
                    "finished_at": None,
                },
                "session": {},
                "warnings": [],
                "children": [
                    {
                        "invocation": {
                            "row_id": index + 2,
                            "id": child["invocation_uuid"],
                            "agent_runner_invocation_id": child["invocation_uuid"],
                            "source": child["provider_source"],
                            "model_name": child["model"],
                            "parent_id": root_uuid,
                            "status": "succeeded",
                            "success": True,
                            "exit_code": 0,
                            "error_category": None,
                            "terminal_reason": None,
                            "started_at": f"2026-07-18T00:00:0{index + 1}Z",
                            "finished_at": f"2026-07-18T00:00:1{index + 1}Z",
                        },
                        "session": {},
                        "warnings": [],
                        "children": [],
                    }
                    for index, child in enumerate(child_artifacts)
                ],
            },
        },
    )
    audit_prompt_path = tmp_path / "TEST_AUDIT_PROCESS_AUDIT.prompt.md"
    audit_prompt_path.write_text("# Audit nested test process\n", encoding="utf-8")
    audit_report_path = tmp_path / "TEST_AUDIT_PROCESS_AUDIT.md"
    companion_artifacts = [
        {
            "path": str(dispatch_path),
            "sha256": hashlib.sha256(dispatch_path.read_bytes()).hexdigest(),
        },
        {
            "path": str(audit_prompt_path),
            "sha256": hashlib.sha256(audit_prompt_path.read_bytes()).hexdigest(),
        },
    ]
    for child in child_artifacts:
        for stem in (
            "prompt",
            "log",
            "canonical_output",
            "extraction_metadata",
        ):
            companion_artifacts.append(
                {
                    "path": child[f"{stem}_path"],
                    "sha256": child[f"{stem}_sha256"],
                }
            )
    binding = {
        "schema": "process-tree-audit-binding-v1",
        "mode": "blocking",
        "report_identity": {
            "schema": "process-tree-audit-report-v1",
            "path": str(audit_report_path),
            "operator_file": str(REPO_ROOT / "agents/test-audit-gate.md"),
        },
        "operator_artifact": {
            "path": str(REPO_ROOT / "agents/test-audit-gate.md"),
            "sha256": hashlib.sha256(
                (REPO_ROOT / "agents/test-audit-gate.md").read_bytes()
            ).hexdigest(),
        },
        "audit_history": None,
        "root_invocation_uuid": root_uuid,
        "subtree_root_uuid": None,
        "expected_process": {
            "path": str(expected_path),
            "sha256": hashlib.sha256(expected_path.read_bytes()).hexdigest(),
        },
        "process_tree": {
            "path": str(trace_path),
            "sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
        },
        "companion_artifacts": sorted(
            companion_artifacts, key=lambda row: row["path"]
        ),
    }
    audit_report_path.write_text(
        render_process_tree_audit_report(
            binding,
            "PASS",
            body="## Tree Summary\n- Nodes inspected: 4",
        ),
        encoding="utf-8",
    )
    audit_log_path = tmp_path / "TEST_AUDIT_PROCESS_AUDIT.log"
    audit_log_path.write_bytes(
        _runner_envelope(
            "PASS\n", invocation_uuid="10000000-0000-4000-8000-000000000004"
        )
    )
    proof_path = tmp_path / "TEST_AUDIT_NESTED_PROOF.json"
    proof = {
        "schema": "test-audit-nested-proof-v1",
        "test_audit_invocation_uuid": root_uuid,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "expected_process_path": str(expected_path),
        "expected_process_sha256": hashlib.sha256(expected_path.read_bytes()).hexdigest(),
        "dispatch_evidence_path": str(dispatch_path),
        "dispatch_evidence_sha256": hashlib.sha256(dispatch_path.read_bytes()).hexdigest(),
        "process_tree_path": str(trace_path),
        "process_tree_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
        "process_tree_audit_prompt_path": str(audit_prompt_path),
        "process_tree_audit_prompt_sha256": hashlib.sha256(
            audit_prompt_path.read_bytes()
        ).hexdigest(),
        "process_tree_audit_path": str(audit_report_path),
        "process_tree_audit_sha256": hashlib.sha256(
            audit_report_path.read_bytes()
        ).hexdigest(),
        "process_tree_audit_log_path": str(audit_log_path),
        "process_tree_audit_log_sha256": hashlib.sha256(
            audit_log_path.read_bytes()
        ).hexdigest(),
        "child_artifacts": child_artifacts,
        "verdict": "PASS",
    }
    _write_json_fixture(proof_path, proof)
    validation_path = tmp_path / "TEST_AUDIT_NESTED_PROOF_VALIDATION.json"
    validation = validate_test_audit_nested_proof(proof, proof_path=proof_path)
    assert validation["status"] == "VALID", validation["errors"]
    _write_json_fixture(validation_path, validation)
    gate_path = tmp_path / "TEST_AUDIT_GATE.md"
    gate_path.write_text("Verdict: PASS\n\n# Test Audit Gate\n", encoding="utf-8")
    result_path = tmp_path / "TEST_AUDIT_RESULT.json"
    result = {
        "schema": "test-audit-result-v2",
        "status": "PASS",
        "mode": "pr-review",
        "test_audit_invocation_uuid": root_uuid,
        "base_branch": "main",
        "base_ref": "refs/pr-review/260/base",
        "base_sha": base_sha,
        "head_branch": "feature/age-260",
        "head_ref": "refs/pr-review/260/head",
        "head_sha": head_sha,
        "merge_base_sha": base_sha,
        "diff_sha256": "d" * 64,
        "local_coverage_command_sha256": "c" * 64,
        "gate_report_path": str(gate_path),
        "gate_report_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
        "nested_proof_path": str(proof_path),
        "nested_proof_sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest(),
        "nested_proof_validation_path": str(validation_path),
        "nested_proof_validation_sha256": hashlib.sha256(
            validation_path.read_bytes()
        ).hexdigest(),
        "nested_process_proof": proof,
    }
    _write_json_fixture(result_path, result)
    decision = validate_test_audit_result(
        result,
        expected_root_uuid=root_uuid,
        expected_base_sha=base_sha,
        expected_head_sha=head_sha,
    )
    assert decision["status"] == "VALID", decision["errors"]
    return {
        "result_path": result_path,
        "result": result,
        "proof_path": proof_path,
        "dispatch_path": dispatch_path,
        "trace_path": trace_path,
        "audit_prompt_path": audit_prompt_path,
        "audit_report_path": audit_report_path,
        "validation_path": validation_path,
        "child_output_path": Path(child_artifacts[0]["canonical_output_path"]),
        "root_uuid": root_uuid,
        "base_sha": base_sha,
        "head_sha": head_sha,
    }


def _refresh_test_audit_process_report(fixture: dict[str, Any]) -> dict[str, Any]:
    proof = json.loads(fixture["proof_path"].read_text(encoding="utf-8"))
    proof["expected_process_sha256"] = hashlib.sha256(
        Path(proof["expected_process_path"]).read_bytes()
    ).hexdigest()
    proof["dispatch_evidence_sha256"] = hashlib.sha256(
        Path(proof["dispatch_evidence_path"]).read_bytes()
    ).hexdigest()
    proof["process_tree_sha256"] = hashlib.sha256(
        Path(proof["process_tree_path"]).read_bytes()
    ).hexdigest()
    proof["process_tree_audit_prompt_sha256"] = hashlib.sha256(
        Path(proof["process_tree_audit_prompt_path"]).read_bytes()
    ).hexdigest()
    binding = {
        "schema": "process-tree-audit-binding-v1",
        "mode": "blocking",
        "report_identity": {
            "schema": "process-tree-audit-report-v1",
            "path": proof["process_tree_audit_path"],
            "operator_file": str(REPO_ROOT / "agents/test-audit-gate.md"),
        },
        "operator_artifact": {
            "path": str(REPO_ROOT / "agents/test-audit-gate.md"),
            "sha256": hashlib.sha256(
                (REPO_ROOT / "agents/test-audit-gate.md").read_bytes()
            ).hexdigest(),
        },
        "audit_history": None,
        "root_invocation_uuid": proof["test_audit_invocation_uuid"],
        "subtree_root_uuid": None,
        "expected_process": {
            "path": proof["expected_process_path"],
            "sha256": proof["expected_process_sha256"],
        },
        "process_tree": {
            "path": proof["process_tree_path"],
            "sha256": proof["process_tree_sha256"],
        },
        "companion_artifacts": _CONTRACT_MODULE._test_audit_bound_companions(
            proof, proof["child_artifacts"]
        ),
    }
    fixture["audit_report_path"].write_text(
        render_process_tree_audit_report(binding, "PASS"), encoding="utf-8"
    )
    proof["process_tree_audit_sha256"] = hashlib.sha256(
        fixture["audit_report_path"].read_bytes()
    ).hexdigest()
    _write_json_fixture(fixture["proof_path"], proof)
    return proof


def _mutate_json(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    _write_json_fixture(path, value)


def _refresh_acceptance_artifact_hash(paths: dict[str, Path], field: str) -> None:
    acceptance = json.loads(paths["acceptance"].read_text(encoding="utf-8"))
    acceptance[field]["sha256"] = hashlib.sha256(paths[field].read_bytes()).hexdigest()
    _write_json_fixture(paths["acceptance"], acceptance)


def _refresh_route_evidence_lineage(paths: dict[str, Path]) -> None:
    pre_dispatch = json.loads(
        paths["pre_audit_dispatch_snapshot"].read_text(encoding="utf-8")
    )
    pre_dispatch["expected_process_sha256"] = hashlib.sha256(
        paths["pre_audit_expected_process"].read_bytes()
    ).hexdigest()
    for node in pre_dispatch["nodes"]:
        node["prompt_sha256"] = hashlib.sha256(
            Path(node["prompt_path"]).read_bytes()
        ).hexdigest()
        node["log_sha256"] = hashlib.sha256(Path(node["log_path"]).read_bytes()).hexdigest()
        node["canonical_output_sha256"] = hashlib.sha256(
            Path(node["canonical_output_path"]).read_bytes()
        ).hexdigest()
    _write_json_fixture(paths["pre_audit_dispatch_snapshot"], pre_dispatch)

    lines = paths["process_report"].read_text(encoding="utf-8").splitlines()
    binding_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith(_CONTRACT_MODULE._PROCESS_TREE_AUDIT_BINDING_PREFIX)
    )
    binding = json.loads(
        lines[binding_index].removeprefix(
            _CONTRACT_MODULE._PROCESS_TREE_AUDIT_BINDING_PREFIX
        )
    )
    binding["expected_process"]["sha256"] = hashlib.sha256(
        Path(binding["expected_process"]["path"]).read_bytes()
    ).hexdigest()
    binding["process_tree"]["sha256"] = hashlib.sha256(
        Path(binding["process_tree"]["path"]).read_bytes()
    ).hexdigest()
    for row in binding["companion_artifacts"]:
        row["sha256"] = hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest()
    paths["process_report"].write_text(
        render_process_tree_audit_report(binding, "PASS"), encoding="utf-8"
    )
    final_dispatch = json.loads(
        paths["final_dispatch_snapshot"].read_text(encoding="utf-8")
    )
    auditor_node = final_dispatch["nodes"][1]
    paths["process_auditor_log"].write_bytes(
        _runner_envelope(
            paths["process_report"].read_text(encoding="utf-8"),
            invocation_uuid=auditor_node["invocation_uuid"],
        )
    )
    extract_provider_payload(paths["process_auditor_log"], paths["process_auditor_output"])
    final_dispatch["expected_process_sha256"] = hashlib.sha256(
        paths["final_expected_process"].read_bytes()
    ).hexdigest()
    for node in final_dispatch["nodes"]:
        node["prompt_sha256"] = hashlib.sha256(
            Path(node["prompt_path"]).read_bytes()
        ).hexdigest()
        node["log_sha256"] = hashlib.sha256(Path(node["log_path"]).read_bytes()).hexdigest()
        node["canonical_output_sha256"] = hashlib.sha256(
            Path(node["canonical_output_path"]).read_bytes()
        ).hexdigest()
    _write_json_fixture(paths["final_dispatch_snapshot"], final_dispatch)
    for field in _CONTRACT_MODULE._LINEAGE_ARTIFACT_FIELDS:
        _refresh_acceptance_artifact_hash(paths, field)


def _refresh_ticket_operation_lineage(paths: dict[str, Path]) -> None:
    ticket_hash = hashlib.sha256(paths["ticket_operation_result"].read_bytes()).hexdigest()
    route_output = json.loads(paths["route_output"].read_text(encoding="utf-8"))
    route_output["ticket_operation_result_sha256"] = ticket_hash
    _write_json_fixture(paths["route_output"], route_output)
    route_evidence = json.loads(paths["route_evidence"].read_text(encoding="utf-8"))
    route_evidence["ticket_operation_result"]["sha256"] = ticket_hash
    _write_json_fixture(paths["route_evidence"], route_evidence)
    _refresh_route_evidence_lineage(paths)


def _synchronize_ticket_operation_producer(paths: dict[str, Path]) -> None:
    result = json.loads(paths["ticket_operation_result"].read_text(encoding="utf-8"))
    producer_log = {
        "schema": "ticket-operation-producer-log-v1",
        "backend": result["backend"],
        "ticket_key": result["ticket_key"],
        "operation": result["operation"],
        "status": result["status"],
        "producer_operator": result["producer_operator"],
        "producer_invocation_uuid": result["producer_invocation_uuid"],
        "comment_body_sha256": result["comment_body_sha256"],
        "remote_comment_id": result["remote_comment_id"],
        "remote_comment_url": result["remote_comment_url"],
        "readback_status": result["readback_status"],
        "readback_ticket_key": result["readback_ticket_key"],
        "readback_comment_id": result["readback_comment_id"],
        "readback_comment_url": result["readback_comment_url"],
        "readback_body_sha256": result["readback_body_sha256"],
    }
    producer_output = {
        "schema": "ticket-operation-readback-v1",
        "backend": result["backend"],
        "ticket_key": result["readback_ticket_key"],
        "status": result["readback_status"],
        "comment_id": result["readback_comment_id"],
        "comment_url": result["readback_comment_url"],
        "body_sha256": result["readback_body_sha256"],
    }
    _write_json_fixture(paths["ticket_producer_log"], producer_log)
    _write_json_fixture(paths["ticket_producer_output"], producer_output)
    result["producer_log_sha256"] = hashlib.sha256(
        paths["ticket_producer_log"].read_bytes()
    ).hexdigest()
    result["producer_output_sha256"] = hashlib.sha256(
        paths["ticket_producer_output"].read_bytes()
    ).hexdigest()
    _write_json_fixture(paths["ticket_operation_result"], result)


def _route_lineage_fixture(
    tmp_path: Path,
    *,
    backend: str = "linear",
    ticket_id: str = "AGE-259",
    attempt_number: int = 1,
    reviewed: dict[str, Any] | None = None,
    feature_branch: str | None = None,
    local_coverage_command_sha256: str = _LOCAL_COVERAGE_COMMAND_SHA256,
) -> dict[str, Path]:
    _, stem = _route_attempt_names(ticket_id, attempt_number)
    reviewed = reviewed or _provider_bundle()
    feature_branch = feature_branch or reviewed["base_ref_name"]
    route_uuid = _SECOND_RUNNER_UUID
    auditor_uuid = "20000000-0000-4000-8000-000000000001"
    ticket_producer_uuid = "30000000-0000-4000-8000-000000000001"
    paths = {
        "route_evidence": tmp_path / "route-evidence" / f"{stem}.evidence.json",
        "ticket_operation_result": tmp_path
        / "ticket-evidence"
        / f"{stem}.ticket-operation.json",
        "ticket_expected_context": tmp_path
        / "ticket-evidence"
        / f"{stem}.expected-context.json",
        "ticket_producer_log": tmp_path
        / "ticket-evidence"
        / f"{stem}.producer-log.json",
        "ticket_producer_output": tmp_path
        / "ticket-evidence"
        / f"{stem}.readback.json",
        "route_prompt": tmp_path / "prompts" / f"{stem}.prompt.md",
        "route_log": tmp_path / "logs" / f"{stem}.log",
        "route_output": tmp_path / "outputs" / f"{stem}.output.json",
        "pre_audit_expected_process": tmp_path
        / "expected"
        / f"{stem}.pre-audit.expected.json",
        "pre_audit_dispatch_snapshot": tmp_path
        / "dispatch"
        / f"{stem}.pre-audit.dispatch.json",
        "pre_audit_trace": tmp_path / "traces" / f"{stem}.pre-audit.trace.json",
        "process_auditor_prompt": tmp_path / "auditor" / f"{stem}.prompt.md",
        "process_auditor_log": tmp_path / "auditor" / f"{stem}.log",
        "process_auditor_output": tmp_path / "auditor" / f"{stem}.output.md",
        "process_report": tmp_path / "process" / f"{stem}.audit.md",
        "process_report_binding": tmp_path / "process" / f"{stem}.binding.json",
        "common_process_validation": tmp_path
        / "process"
        / f"{stem}.common-validation.json",
        "final_expected_process": tmp_path
        / "expected"
        / f"{stem}.final.expected.json",
        "final_dispatch_snapshot": tmp_path
        / "dispatch"
        / f"{stem}.final.dispatch.json",
        "final_trace": tmp_path / "traces" / f"{stem}.final.trace.json",
        "pre_ready_currentness": tmp_path
        / "currentness"
        / f"{stem}-pre-ready.json",
        "acceptance": tmp_path / "acceptance" / f"{stem}.acceptance.json",
        "fresh_currentness": tmp_path
        / "currentness"
        / f"{stem}-post-ready.json",
    }
    for stage in ("phase-4", "phase-6", "phase-8"):
        for artifact in ("expected-process", "process-tree", "process-tree-audit"):
            paths[f"{stage}-{artifact}"] = (
                tmp_path / "child-process-proofs" / stage / f"{artifact}.json"
            )
    paths["route_prompt"].parent.mkdir(parents=True, exist_ok=True)
    paths["route_prompt"].write_text("# Run AGE-259\n", encoding="utf-8")
    paths["route_log"].parent.mkdir(parents=True, exist_ok=True)
    paths["route_log"].write_bytes(
        _runner_envelope(
            "implementation-pipeline: VERIFIED_DRAFT_PR\n",
            invocation_uuid=route_uuid,
        )
    )

    comment_body = (
        f"PR #{reviewed['pr_number']} opened: {reviewed['pr_url']}\n"
        f"base={reviewed['base_ref_oid']} head={reviewed['head_ref_oid']}\n"
    )
    body_sha256 = hashlib.sha256(comment_body.encode()).hexdigest()
    comment_id = (
        "40000000-0000-4000-8000-000000000001" if backend == "linear" else "1042"
    )
    comment_url = (
        f"https://linear.app/oulipoly/issue/{ticket_id}/test"
        f"#comment-{comment_id}"
        if backend == "linear"
        else f"https://example.atlassian.net/rest/api/3/issue/{ticket_id}/comment/{comment_id}"
    )
    ticket_site_url = (
        "https://linear.app" if backend == "linear" else "https://example.atlassian.net"
    )
    producer_operator = f"agents/{backend}-operator.md"
    producer_log = {
        "schema": "ticket-operation-producer-log-v1",
        "backend": backend,
        "ticket_key": ticket_id,
        "operation": "comment-readback",
        "status": "PASS",
        "producer_operator": producer_operator,
        "producer_invocation_uuid": ticket_producer_uuid,
        "comment_body_sha256": body_sha256,
        "remote_comment_id": comment_id,
        "remote_comment_url": comment_url,
        "readback_status": "PASS",
        "readback_ticket_key": ticket_id,
        "readback_comment_id": comment_id,
        "readback_comment_url": comment_url,
        "readback_body_sha256": body_sha256,
    }
    producer_output = {
        "schema": "ticket-operation-readback-v1",
        "backend": backend,
        "ticket_key": ticket_id,
        "status": "PASS",
        "comment_id": comment_id,
        "comment_url": comment_url,
        "body_sha256": body_sha256,
    }
    _write_json_fixture(paths["ticket_producer_log"], producer_log)
    _write_json_fixture(paths["ticket_producer_output"], producer_output)
    ticket_result = {
        "schema": "ticket-operation-result-v1",
        "backend": backend,
        "ticket_key": ticket_id,
        "operation": "comment-readback",
        "status": "PASS",
        "owning_route": "implementation-pipeline",
        "attempt_number": attempt_number,
        "pr_url": reviewed["pr_url"],
        "pr_number": reviewed["pr_number"],
        "reviewed_base_branch": reviewed["base_ref_name"],
        "reviewed_base_ref": f"refs/remotes/origin/{reviewed['base_ref_name']}",
        "reviewed_base_sha": reviewed["base_ref_oid"],
        "reviewed_head_branch": reviewed["head_ref_name"],
        "reviewed_head_ref": f"refs/heads/{reviewed['head_ref_name']}",
        "reviewed_head_sha": reviewed["head_ref_oid"],
        "comment_body_sha256": body_sha256,
        "remote_comment_id": comment_id,
        "remote_comment_url": comment_url,
        "readback_status": "PASS",
        "readback_ticket_key": ticket_id,
        "readback_comment_id": comment_id,
        "readback_comment_url": comment_url,
        "readback_body_sha256": body_sha256,
        "producer_operator": producer_operator,
        "producer_invocation_uuid": ticket_producer_uuid,
        "producer_log_path": str(paths["ticket_producer_log"]),
        "producer_log_sha256": hashlib.sha256(
            paths["ticket_producer_log"].read_bytes()
        ).hexdigest(),
        "producer_output_path": str(paths["ticket_producer_output"]),
        "producer_output_sha256": hashlib.sha256(
            paths["ticket_producer_output"].read_bytes()
        ).hexdigest(),
    }
    _write_json_fixture(
        paths["ticket_operation_result"],
        ticket_result,
    )
    expected_context = {
        "schema": "ticket-operation-expected-context-v1",
        "backend": backend,
        "ticket_site_url": ticket_site_url,
        "ticket_key": ticket_id,
        "operation": "comment-readback",
        "owning_route": "implementation-pipeline",
        "attempt_number": attempt_number,
        "pr_url": reviewed["pr_url"],
        "pr_number": reviewed["pr_number"],
        "reviewed_base_branch": reviewed["base_ref_name"],
        "reviewed_base_ref": ticket_result["reviewed_base_ref"],
        "reviewed_base_sha": reviewed["base_ref_oid"],
        "reviewed_head_branch": reviewed["head_ref_name"],
        "reviewed_head_ref": ticket_result["reviewed_head_ref"],
        "reviewed_head_sha": reviewed["head_ref_oid"],
    }
    _write_json_fixture(paths["ticket_expected_context"], expected_context)
    owned_process_proofs = []
    for stage in ("phase-4", "phase-6", "phase-8"):
        proof = {"owner": "implementation-pipeline", "stage": stage}
        for artifact in ("expected-process", "process-tree", "process-tree-audit"):
            path = paths[f"{stage}-{artifact}"]
            _write_json_fixture(
                path,
                {
                    "schema": f"implementation-{stage}-{artifact}-fixture-v1",
                    "status": "PASS",
                },
            )
            field = artifact.replace("-", "_")
            proof[f"{field}_path"] = str(path)
            proof[f"{field}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        owned_process_proofs.append(proof)
    route_output = {
        "schema": "implementation-pipeline-result-v1",
        "status": "VERIFIED_DRAFT_PR",
        "ticket_id": ticket_id,
        "ticket_system": backend,
        "owning_route": "implementation-pipeline",
        "route_attempt_number": attempt_number,
        "pr_url": reviewed["pr_url"],
        "pr_number": reviewed["pr_number"],
        "state": "OPEN",
        "is_draft": True,
        "phase_8_reviewed_is_draft": True,
        "base_branch": reviewed["base_ref_name"],
        "base_ref": ticket_result["reviewed_base_ref"],
        "head_branch": reviewed["head_ref_name"],
        "head_ref": ticket_result["reviewed_head_ref"],
        "phase_8_reviewed_base_sha": reviewed["base_ref_oid"],
        "phase_8_reviewed_head_sha": reviewed["head_ref_oid"],
        "phase_9_currentness_result": "PASS",
        "ticket_operation_expected_context_path": str(paths["ticket_expected_context"]),
        "ticket_operation_expected_context_sha256": hashlib.sha256(
            paths["ticket_expected_context"].read_bytes()
        ).hexdigest(),
        "ticket_operation_result_path": str(paths["ticket_operation_result"]),
        "ticket_operation_result_sha256": hashlib.sha256(
            paths["ticket_operation_result"].read_bytes()
        ).hexdigest(),
        "owned_process_proofs": owned_process_proofs,
        "merge_sha": None,
    }
    _write_json_fixture(paths["route_output"], route_output)
    _write_json_fixture(
        paths["route_evidence"],
        {
            "schema": "feature-route-evidence-v1",
            "ticket_id": ticket_id,
            "ticket_system": backend,
            "ticket_site_url": ticket_site_url,
            "attempt_number": attempt_number,
            "owning_route": "implementation-pipeline",
            "route_output": {
                "path": str(paths["route_output"]),
                "sha256": hashlib.sha256(paths["route_output"].read_bytes()).hexdigest(),
            },
            "ticket_operation_result": {
                "path": str(paths["ticket_operation_result"]),
                "sha256": hashlib.sha256(
                    paths["ticket_operation_result"].read_bytes()
                ).hexdigest(),
            },
            "provider_reviewed_identity": reviewed,
            "reviewed_base_sha": reviewed["base_ref_oid"],
            "reviewed_head_sha": reviewed["head_ref_oid"],
            "verdict": "PASS",
        },
    )

    route_expected_node = {
        "id": "route-child",
        "required": True,
        "operator_or_role": "implementation-pipeline-orchestrator",
        "model": "gpt-xhigh",
        "parent": "root",
        "prompt_path": str(paths["route_prompt"]),
        "prompt_sha256": hashlib.sha256(paths["route_prompt"].read_bytes()).hexdigest(),
        "log_path": str(paths["route_log"]),
        "log_sha256_join_field": "log_sha256",
        "canonical_output_path": str(paths["route_output"]),
        "canonical_output_sha256_join_field": "canonical_output_sha256",
        "output_mode": "file-produced",
    }
    route_dispatch_node = {
        "id": "route-child",
        "invocation_uuid": route_uuid,
        "parent_invocation_uuid": _RUNNER_UUID,
        "operator_or_role": "implementation-pipeline-orchestrator",
        "model": "gpt-xhigh",
        "provider_source": "fixture-provider",
        "prompt_path": str(paths["route_prompt"]),
        "prompt_sha256": route_expected_node["prompt_sha256"],
        "log_path": str(paths["route_log"]),
        "log_sha256": hashlib.sha256(paths["route_log"].read_bytes()).hexdigest(),
        "canonical_output_path": str(paths["route_output"]),
        "canonical_output_sha256": hashlib.sha256(
            paths["route_output"].read_bytes()
        ).hexdigest(),
        "output_mode": "file-produced",
    }

    def trace_child(
        invocation_uuid: str,
        model: str,
        *,
        row_id: int,
        parent_uuid: str,
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "invocation": {
                "row_id": row_id,
                "id": invocation_uuid,
                "agent_runner_invocation_id": invocation_uuid,
                "source": "fixture-provider",
                "model_name": model,
                "parent_id": parent_uuid,
                "status": "succeeded",
                "success": True,
                "exit_code": 0,
                "error_category": None,
                "terminal_reason": None,
                "started_at": "2026-07-18T00:00:01Z",
                "finished_at": "2026-07-18T00:00:02Z",
            },
            "session": {},
            "warnings": [],
            "children": children or [],
        }

    def trace(children: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "requested_id": _RUNNER_UUID,
            "generated_at": "2026-07-18T00:00:03Z",
            "root": {
                "invocation": {
                    "row_id": 1,
                    "id": _RUNNER_UUID,
                    "agent_runner_invocation_id": _RUNNER_UUID,
                    "source": "fixture-provider",
                    "model_name": "gpt-xhigh",
                    "parent_id": None,
                    "status": "running",
                    "success": None,
                    "exit_code": None,
                    "error_category": None,
                    "terminal_reason": None,
                    "started_at": "2026-07-18T00:00:00Z",
                    "finished_at": None,
                },
                "session": {},
                "warnings": [],
                "children": children,
            },
        }

    pre_expected = {
        "schema": "feature-route-expected-process-v1",
        "stage": "pre-audit",
        "feature_invocation_uuid": _RUNNER_UUID,
        "local_coverage_command_sha256": local_coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": "implementation-pipeline",
        "expected_direct_operator": "implementation-pipeline-orchestrator",
        "expected_direct_model": "gpt-xhigh",
        "child_result_schema": "implementation-pipeline-result-v1",
        "child_result_path": str(paths["route_output"]),
        "child_result_sha256_join_field": "child_result_sha256",
        "route_invocation_uuid_join_field": "route_invocation_uuid",
        "nodes": [route_expected_node],
    }
    _write_json_fixture(paths["pre_audit_expected_process"], pre_expected)
    pre_dispatch = {
        "schema": "feature-route-dispatch-evidence-v1",
        "stage": "pre-audit",
        "feature_invocation_uuid": _RUNNER_UUID,
        "local_coverage_command_sha256": local_coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": "implementation-pipeline",
        "expected_direct_operator": "implementation-pipeline-orchestrator",
        "expected_direct_model": "gpt-xhigh",
        "child_result_schema": "implementation-pipeline-result-v1",
        "child_result_path": str(paths["route_output"]),
        "child_result_sha256": hashlib.sha256(paths["route_output"].read_bytes()).hexdigest(),
        "route_invocation_uuid": route_uuid,
        "expected_process_path": str(paths["pre_audit_expected_process"]),
        "expected_process_sha256": hashlib.sha256(
            paths["pre_audit_expected_process"].read_bytes()
        ).hexdigest(),
        "nodes": [route_dispatch_node],
    }
    _write_json_fixture(paths["pre_audit_dispatch_snapshot"], pre_dispatch)
    implementation_descendants = [
        trace_child(
            "50000000-0000-4000-8000-000000000001",
            "gpt-medium",
            row_id=4,
            parent_uuid=route_uuid,
        ),
        trace_child(
            "50000000-0000-4000-8000-000000000002",
            "gpt-xhigh",
            row_id=5,
            parent_uuid=route_uuid,
        ),
    ]
    _write_json_fixture(
        paths["pre_audit_trace"],
        trace(
            [
                trace_child(
                    route_uuid,
                    "gpt-xhigh",
                    row_id=2,
                    parent_uuid=_RUNNER_UUID,
                    children=deepcopy(implementation_descendants),
                )
            ]
        ),
    )

    pre_ready = validate_pr_currentness(
        reviewed,
        reviewed,
        reviewed["base_ref_oid"],
        reviewed["head_ref_oid"],
        context="feature-direct-pre-ready",
        expected_draft=True,
    )
    assert pre_ready["status"] == "READY"
    _write_json_fixture(paths["pre_ready_currentness"], pre_ready)

    paths["process_auditor_prompt"].parent.mkdir(parents=True, exist_ok=True)
    paths["process_auditor_prompt"].write_text(
        "# Audit route process\nstdout_report_copy=true\n", encoding="utf-8"
    )
    paths["process_report"].parent.mkdir(parents=True, exist_ok=True)
    process_binding = {
        "schema": "process-tree-audit-binding-v1",
        "mode": "blocking",
        "report_identity": {
            "schema": "process-tree-audit-report-v1",
            "path": str(paths["process_report"]),
            "operator_file": str(REPO_ROOT / "agents/feature-orchestrator.md"),
        },
        "operator_artifact": {
            "path": str(REPO_ROOT / "agents/feature-orchestrator.md"),
            "sha256": hashlib.sha256(
                (REPO_ROOT / "agents/feature-orchestrator.md").read_bytes()
            ).hexdigest(),
        },
        "audit_history": None,
        "root_invocation_uuid": _RUNNER_UUID,
        "subtree_root_uuid": None,
        "expected_process": {
            "path": str(paths["pre_audit_expected_process"]),
            "sha256": hashlib.sha256(
                paths["pre_audit_expected_process"].read_bytes()
            ).hexdigest(),
        },
        "process_tree": {
            "path": str(paths["pre_audit_trace"]),
            "sha256": hashlib.sha256(
                paths["pre_audit_trace"].read_bytes()
            ).hexdigest(),
        },
        "companion_artifacts": sorted(
            [
                {
                    "path": str(paths[field]),
                    "sha256": hashlib.sha256(paths[field].read_bytes()).hexdigest(),
                }
                for field in (
                    "route_evidence",
                    "route_output",
                    "pre_audit_dispatch_snapshot",
                    "process_auditor_prompt",
                )
            ]
            + [
                {
                    "path": proof[f"{artifact.replace('-', '_')}_path"],
                    "sha256": proof[f"{artifact.replace('-', '_')}_sha256"],
                }
                for proof in owned_process_proofs
                for artifact in ("expected-process", "process-tree", "process-tree-audit")
            ],
            key=lambda row: row["path"],
        ),
    }
    paths["process_report"].write_text(
        render_process_tree_audit_report(process_binding, "PASS"),
        encoding="utf-8",
    )
    _write_json_fixture(paths["process_report_binding"], process_binding)
    paths["process_auditor_log"].write_bytes(
        _runner_envelope(
            paths["process_report"].read_text(encoding="utf-8"),
            invocation_uuid=auditor_uuid,
        )
    )
    extract_provider_payload(paths["process_auditor_log"], paths["process_auditor_output"])

    auditor_expected_node = {
        "id": "independent-process-auditor",
        "required": True,
        "operator_or_role": "process-tree-auditor",
        "model": "gpt-high",
        "parent": "root",
        "prompt_path": str(paths["process_auditor_prompt"]),
        "prompt_sha256": hashlib.sha256(
            paths["process_auditor_prompt"].read_bytes()
        ).hexdigest(),
        "log_path": str(paths["process_auditor_log"]),
        "log_sha256_join_field": "log_sha256",
        "canonical_output_path": str(paths["process_auditor_output"]),
        "canonical_output_sha256_join_field": "canonical_output_sha256",
        "output_mode": "stdout-extracted",
    }
    auditor_dispatch_node = {
        "id": "independent-process-auditor",
        "invocation_uuid": auditor_uuid,
        "parent_invocation_uuid": _RUNNER_UUID,
        "operator_or_role": "process-tree-auditor",
        "model": "gpt-high",
        "provider_source": "fixture-provider",
        "prompt_path": str(paths["process_auditor_prompt"]),
        "prompt_sha256": auditor_expected_node["prompt_sha256"],
        "log_path": str(paths["process_auditor_log"]),
        "log_sha256": hashlib.sha256(
            paths["process_auditor_log"].read_bytes()
        ).hexdigest(),
        "canonical_output_path": str(paths["process_auditor_output"]),
        "canonical_output_sha256": hashlib.sha256(
            paths["process_auditor_output"].read_bytes()
        ).hexdigest(),
        "output_mode": "stdout-extracted",
    }
    final_expected = {
        "schema": "feature-route-expected-process-v1",
        "stage": "final",
        "feature_invocation_uuid": _RUNNER_UUID,
        "local_coverage_command_sha256": local_coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": "implementation-pipeline",
        "expected_direct_operator": "implementation-pipeline-orchestrator",
        "expected_direct_model": "gpt-xhigh",
        "child_result_schema": "implementation-pipeline-result-v1",
        "child_result_path": str(paths["route_output"]),
        "child_result_sha256_join_field": "child_result_sha256",
        "route_invocation_uuid_join_field": "route_invocation_uuid",
        "nodes": [route_expected_node, auditor_expected_node],
    }
    _write_json_fixture(paths["final_expected_process"], final_expected)
    final_dispatch = {
        "schema": "feature-route-dispatch-evidence-v1",
        "stage": "final",
        "feature_invocation_uuid": _RUNNER_UUID,
        "local_coverage_command_sha256": local_coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": "implementation-pipeline",
        "expected_direct_operator": "implementation-pipeline-orchestrator",
        "expected_direct_model": "gpt-xhigh",
        "child_result_schema": "implementation-pipeline-result-v1",
        "child_result_path": str(paths["route_output"]),
        "child_result_sha256": hashlib.sha256(paths["route_output"].read_bytes()).hexdigest(),
        "route_invocation_uuid": route_uuid,
        "expected_process_path": str(paths["final_expected_process"]),
        "expected_process_sha256": hashlib.sha256(
            paths["final_expected_process"].read_bytes()
        ).hexdigest(),
        "nodes": [route_dispatch_node, auditor_dispatch_node],
    }
    _write_json_fixture(paths["final_dispatch_snapshot"], final_dispatch)
    _write_json_fixture(
        paths["final_trace"],
        trace(
            [
                trace_child(
                    route_uuid,
                    "gpt-xhigh",
                    row_id=2,
                    parent_uuid=_RUNNER_UUID,
                    children=deepcopy(implementation_descendants),
                ),
                trace_child(auditor_uuid, "gpt-high", row_id=3, parent_uuid=_RUNNER_UUID),
            ]
        ),
    )
    common_process_validation = validate_route_process_proof(
        owning_route="implementation-pipeline",
        feature_branch=feature_branch,
        ticket_id=ticket_id,
        attempt_number=attempt_number,
        route_evidence_path=paths["route_evidence"],
        pre_audit_expected_path=paths["pre_audit_expected_process"],
        pre_audit_dispatch_path=paths["pre_audit_dispatch_snapshot"],
        pre_audit_trace_path=paths["pre_audit_trace"],
        process_report_path=paths["process_report"],
        process_report_binding_path=paths["process_report_binding"],
        final_expected_path=paths["final_expected_process"],
        final_dispatch_path=paths["final_dispatch_snapshot"],
        final_trace_path=paths["final_trace"],
    )
    assert common_process_validation["status"] == "PASS", common_process_validation[
        "errors"
    ]
    _write_json_fixture(paths["common_process_validation"], common_process_validation)

    acceptance: dict[str, Any] = {
        "schema": "feature-route-attempt-acceptance-v1",
        "feature_branch": feature_branch,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": "implementation-pipeline",
        "construction_order": [
            "route-evidence",
            "pre-audit-process-proof",
            "independent-process-audit",
            "final-process-proof",
            "common-process-validation",
            "pre-ready-currentness",
            "attempt-acceptance",
        ],
        "provider_reviewed_identity": reviewed,
    }
    for field in (
        "route_evidence",
        "route_output",
        "pre_audit_expected_process",
        "pre_audit_dispatch_snapshot",
        "pre_audit_trace",
        "process_auditor_prompt",
        "process_auditor_log",
        "process_auditor_output",
        "process_report",
        "process_report_binding",
        "final_expected_process",
        "final_dispatch_snapshot",
        "final_trace",
        "common_process_validation",
    ):
        acceptance[field] = {
            "path": str(paths[field]),
            "sha256": hashlib.sha256(paths[field].read_bytes()).hexdigest(),
        }
    acceptance["pre_ready_currentness"] = {
        "path": str(paths["pre_ready_currentness"]),
        "sha256": hashlib.sha256(
            paths["pre_ready_currentness"].read_bytes()
        ).hexdigest(),
        "status": "READY",
        "final_equality_result": "PASS",
    }
    _write_json_fixture(paths["acceptance"], acceptance)

    immediate = {**reviewed, "is_draft": False}
    fresh = validate_pr_currentness(
        reviewed,
        immediate,
        reviewed["base_ref_oid"],
        reviewed["head_ref_oid"],
        context="feature-direct-post-ready",
        expected_draft=False,
    )
    assert fresh["status"] == "READY"
    _write_json_fixture(paths["fresh_currentness"], fresh)
    return paths


def _refactoring_route_process_fixture(
    tmp_path: Path,
    *,
    ticket_id: str,
    attempt_number: int,
    reviewed: dict[str, Any],
    merge_sha: str | None,
    resulting_feature_sha: str | None,
    feature_branch: str | None = None,
    nested_base_name: str | None = None,
    observed_base_name: str | None = None,
    local_coverage_command_sha256: str = _LOCAL_COVERAGE_COMMAND_SHA256,
) -> dict[str, Path]:
    assert merge_sha is not None and resulting_feature_sha == merge_sha
    feature_branch = feature_branch or reviewed["base_ref_name"]
    nested_reviewed = {
        **reviewed,
        "base_ref_name": nested_base_name or reviewed["base_ref_name"],
    }
    nested = _route_lineage_fixture(
        tmp_path / "nested-implementation",
        ticket_id=ticket_id,
        attempt_number=attempt_number,
        reviewed=nested_reviewed,
        local_coverage_command_sha256=local_coverage_command_sha256,
    )
    nested_result = json.loads(nested["route_output"].read_text(encoding="utf-8"))
    _, stem = _route_attempt_names(ticket_id, attempt_number)
    route_uuid = "21000000-0000-4000-8000-000000000001"
    auditor_uuid = "22000000-0000-4000-8000-000000000001"
    child_uuid = _SECOND_RUNNER_UUID
    paths = {
        "route_prompt": tmp_path / "prompts" / f"{stem}.prompt.md",
        "route_log": tmp_path / "logs" / f"{stem}.log",
        "route_output": tmp_path / "outputs" / f"{stem}.output.json",
        "route_evidence": tmp_path / "route-evidence" / f"{stem}.evidence.json",
        "pre_audit_expected_process": tmp_path / "expected" / f"{stem}.pre-audit.expected.json",
        "pre_audit_dispatch_snapshot": tmp_path / "dispatch" / f"{stem}.pre-audit.dispatch.json",
        "pre_audit_trace": tmp_path / "traces" / f"{stem}.pre-audit.trace.json",
        "process_auditor_prompt": tmp_path / "auditor" / f"{stem}.prompt.md",
        "process_auditor_log": tmp_path / "auditor" / f"{stem}.log",
        "process_auditor_output": tmp_path / "auditor" / f"{stem}.output.md",
        "process_report": tmp_path / "process" / f"{stem}.audit.md",
        "process_report_binding": tmp_path / "process" / f"{stem}.binding.json",
        "final_expected_process": tmp_path / "expected" / f"{stem}.final.expected.json",
        "final_dispatch_snapshot": tmp_path / "dispatch" / f"{stem}.final.dispatch.json",
        "final_trace": tmp_path / "traces" / f"{stem}.final.trace.json",
    }
    paths["route_prompt"].parent.mkdir(parents=True, exist_ok=True)
    paths["route_prompt"].write_text(f"# Refactor {ticket_id}\n", encoding="utf-8")

    owned_proofs: list[dict[str, Any]] = []
    ref_artifacts: dict[str, Path] = {}
    for stage in ("pre-merge", "final"):
        proof = {"owner": "refactoring-orchestrator", "stage": stage}
        for artifact in ("expected_process", "process_tree", "process_tree_audit"):
            path = tmp_path / "refactoring-owned" / stage / f"{artifact}.json"
            _write_json_fixture(
                path,
                {"schema": f"refactoring-{stage}-{artifact}-fixture-v1", "status": "PASS"},
            )
            proof[f"{artifact}_path"] = str(path)
            proof[f"{artifact}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            ref_artifacts[f"{stage}-{artifact}"] = path
        owned_proofs.append(proof)
    pre_dispatch = tmp_path / "refactoring-owned" / "pre-merge" / "dispatch.json"
    final_dispatch = tmp_path / "refactoring-owned" / "final" / "dispatch.json"
    auditor_index = tmp_path / "refactoring-owned" / "auditor-index.json"
    for path, schema in (
        (pre_dispatch, "refactoring-pre-merge-dispatch-fixture-v1"),
        (final_dispatch, "refactoring-final-dispatch-fixture-v1"),
    ):
        _write_json_fixture(path, {"schema": schema, "status": "PASS"})
    pre_merge_evidence = tmp_path / "refactoring-owned" / "pre-merge-evidence.json"
    child_pre_audit = tmp_path / "refactoring-owned" / "child-pre-merge-audit.json"
    child_final_audit = tmp_path / "refactoring-owned" / "child-final-audit.json"
    for path, schema in (
        (pre_merge_evidence, "refactoring-pre-merge-evidence-fixture-v1"),
        (child_pre_audit, "refactoring-child-pre-merge-audit-fixture-v1"),
        (child_final_audit, "refactoring-child-final-audit-fixture-v1"),
    ):
        _write_json_fixture(path, {"schema": schema, "status": "PASS"})
    pre_reports: list[dict[str, Any]] = []
    post_reports: list[dict[str, Any]] = []
    auditor_roles = _CONTRACT_MODULE._REFACTORING_AUDITOR_ROLES
    base_sha = reviewed["base_ref_oid"]
    head_sha = reviewed["head_ref_oid"]
    for stage, rows, current_head in (
        ("pre-merge", pre_reports, head_sha),
        ("post-merge", post_reports, resulting_feature_sha),
    ):
        for role in auditor_roles:
            path = tmp_path / "refactoring-owned" / "auditors" / f"{stage}-{role}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            verdict = "LOW" if role == "validation-integrity-auditor" else "Verdict: LOW"
            path.write_text(f"# {role}\n\n{verdict}\n", encoding="utf-8")
            rows.append(
                {
                    "role": role,
                    "stage": stage,
                    "report_path": str(path),
                    "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "verdict": "LOW",
                    "round": 1,
                    "baseline_sha": base_sha,
                    "current_head_sha": current_head,
                }
            )

    ticket_source = {"linear_issue_key": ticket_id}
    _write_json_fixture(
        auditor_index,
        {
            "schema": "refactoring-auditor-index-v1",
            "owning_route": "refactoring",
            "refactoring_invocation_uuid": route_uuid,
            "feature_branch": feature_branch,
            "ticket_id": ticket_id,
            "attempt_number": attempt_number,
            "auditor_baseline_sha": base_sha,
            "pre_merge_current_head": head_sha,
            "post_merge_current_head": resulting_feature_sha,
            "pre_merge_reports": pre_reports,
            "post_merge_reports": post_reports,
        },
    )
    child = {
        "ticket_source": ticket_source,
        "slice_identity": f"{ticket_id}-slice",
        "child_invocation_uuid": child_uuid,
        "child_session_id": f"session-{ticket_id.lower()}",
        "child_prompt_path": str(nested["route_prompt"]),
        "child_log_path": str(nested["route_log"]),
        "implementation_result_path": str(nested["route_output"]),
        "implementation_result_sha256": hashlib.sha256(nested["route_output"].read_bytes()).hexdigest(),
        "ticket_operation_expected_context_path": nested_result["ticket_operation_expected_context_path"],
        "ticket_operation_expected_context_sha256": nested_result["ticket_operation_expected_context_sha256"],
        "ticket_operation_result_path": nested_result["ticket_operation_result_path"],
        "ticket_operation_result_sha256": nested_result["ticket_operation_result_sha256"],
        "owned_process_proofs": nested_result["owned_process_proofs"],
        "declared_head_branch": reviewed["head_ref_name"],
        "declared_head_sha": head_sha,
        "dispatched_base_branch": reviewed["base_ref_name"],
        "dispatched_auto_merge_after_phase_9": False,
        "pr_url": reviewed["pr_url"],
        "pr_number": reviewed["pr_number"],
        "open_pr_state": "OPEN",
        "open_observed_is_draft": True,
        "open_observed_base_ref_name": observed_base_name or reviewed["base_ref_name"],
        "open_observed_base_sha": base_sha,
        "open_observed_head_ref_name": reviewed["head_ref_name"],
        "open_observed_head_sha": head_sha,
        "pre_merge_pr_state": "OPEN",
        "pre_merge_observed_is_draft": False,
        "pre_merge_observed_base_ref_name": reviewed["base_ref_name"],
        "pre_merge_observed_base_sha": base_sha,
        "pre_merge_observed_head_ref_name": reviewed["head_ref_name"],
        "pre_merge_observed_head_sha": head_sha,
        "pre_merge_base_sha": base_sha,
        "reviewed_base_sha": base_sha,
        "expected_head_guard_sha": head_sha,
        "merged_pr_state": "MERGED",
        "merged_observed_base_ref_name": reviewed["base_ref_name"],
        "merged_observed_base_sha": base_sha,
        "merged_observed_head_ref_name": reviewed["head_ref_name"],
        "merged_observed_head_sha": head_sha,
        "merged_observed_merge_sha": merge_sha,
        "pre_merge_evidence_verdict": "PASS",
        "pre_merge_evidence_path": str(pre_merge_evidence),
        "pre_merge_evidence_sha256": hashlib.sha256(pre_merge_evidence.read_bytes()).hexdigest(),
        "merge_owner": "refactoring-orchestrator",
        "merge_sha": merge_sha,
        "refreshed_integration_sha": resulting_feature_sha,
        "merge_first_parent_sha": base_sha,
        "ancestry_result": "PASS",
        "immediate_parent_result": "PASS",
        "auditor_baseline_sha": base_sha,
        "pre_merge_auditor_current_head": head_sha,
        "pre_merge_auditor_reports": pre_reports,
        "pre_merge_process_tree_audit_path": str(child_pre_audit),
        "pre_merge_process_tree_audit_sha256": hashlib.sha256(child_pre_audit.read_bytes()).hexdigest(),
        "post_merge_auditor_current_head": resulting_feature_sha,
        "post_merge_auditor_reports": post_reports,
        "auditor_verdict": "LOW",
        "process_tree_audit_path": str(child_final_audit),
        "process_tree_audit_sha256": hashlib.sha256(child_final_audit.read_bytes()).hexdigest(),
        "outcome": "VERIFIED_MERGED",
    }
    route_output = {
        "schema": "refactoring-route-result-v1",
        "refactoring_invocation_uuid": route_uuid,
        "ticket_source": ticket_source,
        "ticket_system": "linear",
        "integration_branch_name": reviewed["base_ref_name"],
        "final_integration_sha": resulting_feature_sha,
        "pre_merge_expected_process_path": str(ref_artifacts["pre-merge-expected_process"]),
        "pre_merge_expected_process_sha256": hashlib.sha256(ref_artifacts["pre-merge-expected_process"].read_bytes()).hexdigest(),
        "pre_merge_dispatch_evidence_path": str(pre_dispatch),
        "pre_merge_dispatch_evidence_sha256": hashlib.sha256(pre_dispatch.read_bytes()).hexdigest(),
        "pre_merge_process_tree_path": str(ref_artifacts["pre-merge-process_tree"]),
        "pre_merge_process_tree_sha256": hashlib.sha256(ref_artifacts["pre-merge-process_tree"].read_bytes()).hexdigest(),
        "pre_merge_process_tree_audit_path": str(ref_artifacts["pre-merge-process_tree_audit"]),
        "pre_merge_process_tree_audit_sha256": hashlib.sha256(ref_artifacts["pre-merge-process_tree_audit"].read_bytes()).hexdigest(),
        "expected_process_path": str(ref_artifacts["final-expected_process"]),
        "expected_process_sha256": hashlib.sha256(ref_artifacts["final-expected_process"].read_bytes()).hexdigest(),
        "dispatch_evidence_path": str(final_dispatch),
        "dispatch_evidence_sha256": hashlib.sha256(final_dispatch.read_bytes()).hexdigest(),
        "process_tree_path": str(ref_artifacts["final-process_tree"]),
        "process_tree_sha256": hashlib.sha256(ref_artifacts["final-process_tree"].read_bytes()).hexdigest(),
        "process_tree_audit_path": str(ref_artifacts["final-process_tree_audit"]),
        "process_tree_audit_sha256": hashlib.sha256(ref_artifacts["final-process_tree_audit"].read_bytes()).hexdigest(),
        "owned_process_proofs": owned_proofs,
        "auditor_index_path": str(auditor_index),
        "auditor_index_sha256": hashlib.sha256(auditor_index.read_bytes()).hexdigest(),
        "child": child,
        "state": "VERIFIED_MERGED",
    }
    _write_json_fixture(paths["route_output"], route_output)
    paths["route_log"].parent.mkdir(parents=True, exist_ok=True)
    paths["route_log"].write_bytes(
        _runner_envelope("refactoring: VERIFIED_MERGED\n", invocation_uuid=route_uuid)
    )
    _write_json_fixture(
        paths["route_evidence"],
        {
            "schema": "feature-route-evidence-v1",
            "ticket_id": ticket_id,
            "ticket_system": "linear",
            "ticket_site_url": "https://linear.app",
            "attempt_number": attempt_number,
            "owning_route": "refactoring",
            "route_output": {"path": str(paths["route_output"]), "sha256": hashlib.sha256(paths["route_output"].read_bytes()).hexdigest()},
            "ticket_operation_result": {"path": nested_result["ticket_operation_result_path"], "sha256": nested_result["ticket_operation_result_sha256"]},
            "provider_reviewed_identity": reviewed,
            "reviewed_base_sha": base_sha,
            "reviewed_head_sha": head_sha,
            "verdict": "PASS",
        },
    )
    route_expected_node = {
        "id": "route-child",
        "required": True,
        "operator_or_role": "refactoring-orchestrator",
        "model": "gpt-xhigh",
        "parent": "root",
        "prompt_path": str(paths["route_prompt"]),
        "prompt_sha256": hashlib.sha256(paths["route_prompt"].read_bytes()).hexdigest(),
        "log_path": str(paths["route_log"]),
        "log_sha256_join_field": "log_sha256",
        "canonical_output_path": str(paths["route_output"]),
        "canonical_output_sha256_join_field": "canonical_output_sha256",
        "output_mode": "file-produced",
    }
    route_dispatch_node = {
        "id": "route-child",
        "invocation_uuid": route_uuid,
        "parent_invocation_uuid": _RUNNER_UUID,
        "operator_or_role": "refactoring-orchestrator",
        "model": "gpt-xhigh",
        "provider_source": "fixture-provider",
        "prompt_path": str(paths["route_prompt"]),
        "prompt_sha256": route_expected_node["prompt_sha256"],
        "log_path": str(paths["route_log"]),
        "log_sha256": hashlib.sha256(paths["route_log"].read_bytes()).hexdigest(),
        "canonical_output_path": str(paths["route_output"]),
        "canonical_output_sha256": hashlib.sha256(paths["route_output"].read_bytes()).hexdigest(),
        "output_mode": "file-produced",
    }

    def trace_child(invocation_uuid: str, model: str, row_id: int, parent_uuid: str, children=None):
        return {
            "invocation": {
                "row_id": row_id,
                "id": invocation_uuid,
                "agent_runner_invocation_id": invocation_uuid,
                "source": "fixture-provider",
                "model_name": model,
                "parent_id": parent_uuid,
                "status": "succeeded",
                "success": True,
                "exit_code": 0,
                "error_category": None,
                "terminal_reason": None,
                "started_at": "2026-07-18T00:00:01Z",
                "finished_at": "2026-07-18T00:00:02Z",
            },
            "session": {},
            "warnings": [],
            "children": children or [],
        }

    def trace(children):
        return {
            "requested_id": _RUNNER_UUID,
            "generated_at": "2026-07-18T00:00:03Z",
            "root": {
                "invocation": {
                    "row_id": 1,
                    "id": _RUNNER_UUID,
                    "agent_runner_invocation_id": _RUNNER_UUID,
                    "source": "fixture-provider",
                    "model_name": "gpt-xhigh",
                    "parent_id": None,
                    "status": "running",
                    "success": None,
                    "exit_code": None,
                    "error_category": None,
                    "terminal_reason": None,
                    "started_at": "2026-07-18T00:00:00Z",
                    "finished_at": None,
                },
                "session": {},
                "warnings": [],
                "children": children,
            },
        }

    nested_descendants = [
        trace_child(
            child_uuid,
            "gpt-xhigh",
            4,
            route_uuid,
            [trace_child("23000000-0000-4000-8000-000000000001", "gpt-high", 5, child_uuid)],
        )
    ]
    expected_common = {
        "schema": "feature-route-expected-process-v1",
        "feature_invocation_uuid": _RUNNER_UUID,
        "local_coverage_command_sha256": local_coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": "refactoring",
        "expected_direct_operator": "refactoring-orchestrator",
        "expected_direct_model": "gpt-xhigh",
        "child_result_schema": "refactoring-route-result-v1",
        "child_result_path": str(paths["route_output"]),
        "child_result_sha256_join_field": "child_result_sha256",
        "route_invocation_uuid_join_field": "route_invocation_uuid",
    }
    dispatch_common = {
        "schema": "feature-route-dispatch-evidence-v1",
        "feature_invocation_uuid": _RUNNER_UUID,
        "local_coverage_command_sha256": local_coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": "refactoring",
        "expected_direct_operator": "refactoring-orchestrator",
        "expected_direct_model": "gpt-xhigh",
        "child_result_schema": "refactoring-route-result-v1",
        "child_result_path": str(paths["route_output"]),
        "child_result_sha256": hashlib.sha256(paths["route_output"].read_bytes()).hexdigest(),
        "route_invocation_uuid": route_uuid,
    }
    pre_expected = {**expected_common, "stage": "pre-audit", "nodes": [route_expected_node]}
    _write_json_fixture(paths["pre_audit_expected_process"], pre_expected)
    pre_dispatch_projection = {
        **dispatch_common,
        "stage": "pre-audit",
        "expected_process_path": str(paths["pre_audit_expected_process"]),
        "expected_process_sha256": hashlib.sha256(paths["pre_audit_expected_process"].read_bytes()).hexdigest(),
        "nodes": [route_dispatch_node],
    }
    _write_json_fixture(paths["pre_audit_dispatch_snapshot"], pre_dispatch_projection)
    _write_json_fixture(
        paths["pre_audit_trace"],
        trace([trace_child(route_uuid, "gpt-xhigh", 2, _RUNNER_UUID, deepcopy(nested_descendants))]),
    )
    paths["process_auditor_prompt"].parent.mkdir(parents=True, exist_ok=True)
    paths["process_auditor_prompt"].write_text("# Audit refactoring route\nstdout_report_copy=true\n", encoding="utf-8")
    companions = [
        {"path": str(paths[field]), "sha256": hashlib.sha256(paths[field].read_bytes()).hexdigest()}
        for field in ("route_evidence", "route_output", "pre_audit_dispatch_snapshot", "process_auditor_prompt")
    ]
    for proof in [*owned_proofs, *nested_result["owned_process_proofs"]]:
        for artifact in ("expected_process", "process_tree", "process_tree_audit"):
            companions.append({"path": proof[f"{artifact}_path"], "sha256": proof[f"{artifact}_sha256"]})
    process_binding = {
        "schema": "process-tree-audit-binding-v1",
        "mode": "blocking",
        "report_identity": {"schema": "process-tree-audit-report-v1", "path": str(paths["process_report"]), "operator_file": str(REPO_ROOT / "agents/feature-orchestrator.md")},
        "operator_artifact": {"path": str(REPO_ROOT / "agents/feature-orchestrator.md"), "sha256": hashlib.sha256((REPO_ROOT / "agents/feature-orchestrator.md").read_bytes()).hexdigest()},
        "audit_history": None,
        "root_invocation_uuid": _RUNNER_UUID,
        "subtree_root_uuid": None,
        "expected_process": {"path": str(paths["pre_audit_expected_process"]), "sha256": hashlib.sha256(paths["pre_audit_expected_process"].read_bytes()).hexdigest()},
        "process_tree": {"path": str(paths["pre_audit_trace"]), "sha256": hashlib.sha256(paths["pre_audit_trace"].read_bytes()).hexdigest()},
        "companion_artifacts": sorted(companions, key=lambda row: row["path"]),
    }
    paths["process_report"].parent.mkdir(parents=True, exist_ok=True)
    paths["process_report"].write_text(render_process_tree_audit_report(process_binding, "PASS"), encoding="utf-8")
    _write_json_fixture(paths["process_report_binding"], process_binding)
    paths["process_auditor_log"].write_bytes(
        _runner_envelope(paths["process_report"].read_text(encoding="utf-8"), invocation_uuid=auditor_uuid)
    )
    extract_provider_payload(paths["process_auditor_log"], paths["process_auditor_output"])
    auditor_expected_node = {
        "id": "independent-process-auditor",
        "required": True,
        "operator_or_role": "process-tree-auditor",
        "model": "gpt-high",
        "parent": "root",
        "prompt_path": str(paths["process_auditor_prompt"]),
        "prompt_sha256": hashlib.sha256(paths["process_auditor_prompt"].read_bytes()).hexdigest(),
        "log_path": str(paths["process_auditor_log"]),
        "log_sha256_join_field": "log_sha256",
        "canonical_output_path": str(paths["process_auditor_output"]),
        "canonical_output_sha256_join_field": "canonical_output_sha256",
        "output_mode": "stdout-extracted",
    }
    auditor_dispatch_node = {
        "id": "independent-process-auditor",
        "invocation_uuid": auditor_uuid,
        "parent_invocation_uuid": _RUNNER_UUID,
        "operator_or_role": "process-tree-auditor",
        "model": "gpt-high",
        "provider_source": "fixture-provider",
        "prompt_path": str(paths["process_auditor_prompt"]),
        "prompt_sha256": auditor_expected_node["prompt_sha256"],
        "log_path": str(paths["process_auditor_log"]),
        "log_sha256": hashlib.sha256(paths["process_auditor_log"].read_bytes()).hexdigest(),
        "canonical_output_path": str(paths["process_auditor_output"]),
        "canonical_output_sha256": hashlib.sha256(paths["process_auditor_output"].read_bytes()).hexdigest(),
        "output_mode": "stdout-extracted",
    }
    final_expected_projection = {**expected_common, "stage": "final", "nodes": [route_expected_node, auditor_expected_node]}
    _write_json_fixture(paths["final_expected_process"], final_expected_projection)
    final_dispatch_projection = {
        **dispatch_common,
        "stage": "final",
        "expected_process_path": str(paths["final_expected_process"]),
        "expected_process_sha256": hashlib.sha256(paths["final_expected_process"].read_bytes()).hexdigest(),
        "nodes": [route_dispatch_node, auditor_dispatch_node],
    }
    _write_json_fixture(paths["final_dispatch_snapshot"], final_dispatch_projection)
    _write_json_fixture(
        paths["final_trace"],
        trace(
            [
                trace_child(route_uuid, "gpt-xhigh", 2, _RUNNER_UUID, deepcopy(nested_descendants)),
                trace_child(auditor_uuid, "gpt-high", 3, _RUNNER_UUID),
            ]
        ),
    )
    return paths


def _validate_refactoring_process_fixture(paths: dict[str, Path]) -> dict[str, Any]:
    return validate_route_process_proof(
        owning_route="refactoring",
        feature_branch="feature/hourly-suspicious-process-investigator",
        ticket_id="AGE-257",
        attempt_number=1,
        route_evidence_path=paths["route_evidence"],
        pre_audit_expected_path=paths["pre_audit_expected_process"],
        pre_audit_dispatch_path=paths["pre_audit_dispatch_snapshot"],
        pre_audit_trace_path=paths["pre_audit_trace"],
        process_report_path=paths["process_report"],
        process_report_binding_path=paths["process_report_binding"],
        final_expected_path=paths["final_expected_process"],
        final_dispatch_path=paths["final_dispatch_snapshot"],
        final_trace_path=paths["final_trace"],
    )


def _attempt_proof_fixture(
    proof_path: Path,
    *,
    ticket_id: str,
    attempt_number: int,
    owning_route: str,
    feature_branch: str,
    state: str,
    dispatch_base_sha: str,
    reviewed_head_sha: str,
    pre_merge_feature_sha: str,
    pre_merge_head_sha: str,
    merge_sha: str | None,
    resulting_feature_sha: str | None,
    local_coverage_command_sha256: str = _LOCAL_COVERAGE_COMMAND_SHA256,
) -> None:
    slug, stem = _route_attempt_names(ticket_id, attempt_number)
    artifact_root = proof_path.parent / ".artifacts" / stem
    reviewed = _provider_bundle(
        base_sha=dispatch_base_sha,
        head_sha=reviewed_head_sha,
        base_name=feature_branch,
        head_name=f"route/{slug}-{attempt_number}",
    )
    if owning_route == "refactoring":
        paths = _refactoring_route_process_fixture(
            artifact_root,
            ticket_id=ticket_id,
            attempt_number=attempt_number,
            reviewed=reviewed,
            merge_sha=merge_sha,
            resulting_feature_sha=resulting_feature_sha,
            feature_branch=feature_branch,
            local_coverage_command_sha256=local_coverage_command_sha256,
        )
    else:
        paths = _route_lineage_fixture(
            artifact_root,
            ticket_id=ticket_id,
            attempt_number=attempt_number,
            reviewed=reviewed,
            feature_branch=feature_branch,
            local_coverage_command_sha256=local_coverage_command_sha256,
        )
    common = validate_route_process_proof(
        owning_route=owning_route,
        feature_branch=feature_branch,
        ticket_id=ticket_id,
        attempt_number=attempt_number,
        route_evidence_path=paths["route_evidence"],
        pre_audit_expected_path=paths["pre_audit_expected_process"],
        pre_audit_dispatch_path=paths["pre_audit_dispatch_snapshot"],
        pre_audit_trace_path=paths["pre_audit_trace"],
        process_report_path=paths["process_report"],
        process_report_binding_path=paths["process_report_binding"],
        final_expected_path=paths["final_expected_process"],
        final_dispatch_path=paths["final_dispatch_snapshot"],
        final_trace_path=paths["final_trace"],
    )
    assert common["status"] == "PASS", common["errors"]
    common_path = paths.get(
        "common_process_validation",
        artifact_root / "common-route-process-validation.json",
    )
    if common_path.exists():
        assert json.loads(common_path.read_text(encoding="utf-8")) == common
    else:
        _write_json_fixture(common_path, common)
    merge_authorization = None
    if state == "VERIFIED_MERGED" and owning_route == "implementation-pipeline":
        authorization = validate_route_artifact_lineage(
            paths["acceptance"], paths["fresh_currentness"]
        )
        assert authorization["status"] == "MERGE_AUTHORIZED", authorization["errors"]
        authorization_path = artifact_root / "merge-authorization.json"
        _write_json_fixture(authorization_path, authorization)
        merge_authorization = {
            "path": str(authorization_path),
            "sha256": hashlib.sha256(authorization_path.read_bytes()).hexdigest(),
        }
    outcome = {
        "schema": "feature-route-attempt-outcome-v1",
        "feature_branch": feature_branch,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": owning_route,
        "state": state,
        "dispatch_base_sha": dispatch_base_sha,
        "reviewed_base_sha": dispatch_base_sha,
        "reviewed_head_sha": reviewed_head_sha,
        "pre_merge_feature_sha": pre_merge_feature_sha,
        "pre_merge_head_sha": pre_merge_head_sha,
        "merge_sha": merge_sha,
        "resulting_feature_sha": resulting_feature_sha,
        "child_result": common["artifacts"]["child_result"],
        "merge_authorization": merge_authorization,
    }
    outcome_path = artifact_root / "route-specific-outcome.json"
    _write_json_fixture(outcome_path, outcome)
    proof = {
        "schema": "feature-route-attempt-proof-v1",
        "feature_branch": feature_branch,
        "local_coverage_command_sha256": local_coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": owning_route,
        **common["artifacts"],
        "child_owned_process_proofs": common["child_owned_process_proofs"],
        "common_validation_result": {
            "path": str(common_path),
            "sha256": hashlib.sha256(common_path.read_bytes()).hexdigest(),
        },
        "route_specific_evidence": {
            "path": str(outcome_path),
            "sha256": hashlib.sha256(outcome_path.read_bytes()).hexdigest(),
        },
    }
    _write_json_fixture(proof_path, proof)
    validation = validate_route_attempt_proof(proof_path)
    assert validation["status"] == "PASS", validation["errors"]


def _dependency_proof(
    ticket_id: str, attempt_number: int, merge_sha: str
) -> dict[str, Any]:
    return {
        "ticket_id": ticket_id,
        "accepted_attempt_number": attempt_number,
        "merge_sha": merge_sha,
        "reachable_from_dispatch_base": True,
    }


def _pr_review_posting_allowed(
    proof_schema: dict[str, Any],
    observed_nodes: dict[str, str],
    *,
    include_proposal: bool,
    include_domain: bool,
    provider_identity_unchanged: bool,
) -> bool:
    required = dict(proof_schema["initial_required_nodes"])
    if include_proposal:
        required.update(proof_schema["proposal_round_required_nodes"])
    if include_domain:
        required.update(proof_schema["domain_round_required_nodes"])
    return provider_identity_unchanged and all(
        observed_nodes.get(role) == model for role, model in required.items()
    )


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: yaml.Loader, node: yaml.Node, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _age255_manifest(tmp_path: Path, mutate=None) -> tuple[Path, list[str]]:
    source = json.loads(_read("tests/fixtures/age-255-successor-manifest.json"))
    manifest = deepcopy(source)
    brief_dir = tmp_path / "briefs"
    brief_dir.mkdir()
    for successor in manifest["successors"]:
        brief = brief_dir / Path(successor["brief_path"]).name
        brief.write_text(f"# {successor['successor_id']}\n", encoding="utf-8")
        successor["brief_path"] = str(brief)
    if mutate is not None:
        mutate(manifest)
    path = tmp_path / "successor-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, [row["ticket_key"] for row in manifest.get("successors", [])]


def _normalize_age255(
    tmp_path: Path,
    mutate=None,
    *,
    local_coverage_command: str = _LOCAL_COVERAGE_COMMAND,
) -> dict[str, Any]:
    path, tickets = _age255_manifest(tmp_path, mutate)
    scope = tmp_path / "feature-scope.md"
    scope.write_text("# Feature scope\n", encoding="utf-8")
    return normalize_successor_manifest(
        path,
        feature_id="AGE-255",
        feature_scope_path=scope,
        feature_branch="feature/hourly-suspicious-process-investigator",
        trunk_branch="main",
        manager_flavor="manager-max",
        ticket_system="linear",
        scoped_ticket_list=tickets,
        child_worktrees_root=tmp_path / "worktrees",
        planning_dir=tmp_path / "planning",
        scratch_dir=tmp_path / "scratch",
        local_coverage_command=local_coverage_command,
    )


def _inline_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {key: deepcopy(row[key]) for key in _ROUTE_MODULE.INLINE_RECORD_KEYS}
        for row in manifest["records"]
    ]


def _normalize_inline_age255(
    tmp_path: Path,
    mutate=None,
    *,
    feature_branch: str = "feature/hourly-suspicious-process-investigator",
    ticket_system: str = "linear",
    local_coverage_command: str = _LOCAL_COVERAGE_COMMAND,
) -> dict[str, Any]:
    successor = _normalize_age255(tmp_path)
    records = _inline_records(successor)
    if mutate is not None:
        mutate(records)
    return normalize_ticket_route_map(
        json.dumps(records, separators=(",", ":"), sort_keys=True),
        feature_id="AGE-255",
        feature_scope_path=tmp_path / "feature-scope.md",
        feature_branch=feature_branch,
        trunk_branch="main",
        manager_flavor="manager-max",
        ticket_system=ticket_system,
        scoped_ticket_list=[row["ticket_id"] for row in records if "ticket_id" in row],
        child_worktrees_root=tmp_path / "worktrees",
        planning_dir=tmp_path / "planning",
        scratch_dir=tmp_path / "scratch",
        local_coverage_command=local_coverage_command,
    )


def test_feature_route_manifest_resolves_remote_prefixes_once_per_normalization(
    tmp_path: Path, monkeypatch
):
    original_run = _ROUTE_MODULE.subprocess.run
    remote_calls = 0

    def counting_run(command, *args, **kwargs):
        nonlocal remote_calls
        if command == ["git", "remote"]:
            remote_calls += 1
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(_ROUTE_MODULE.subprocess, "run", counting_run)

    _normalize_age255(tmp_path)

    assert remote_calls == 1


def _route_cli_common(tmp_path: Path, output: Path, tickets: list[str]) -> list[str]:
    command = [
        sys.executable,
        str(REPO_ROOT / "tools/feature_route_manifest.py"),
        "--feature-id",
        "AGE-255",
        "--feature-scope-path",
        str(tmp_path / "feature-scope.md"),
        "--feature-branch",
        "feature/hourly-suspicious-process-investigator",
        "--trunk-branch",
        "main",
        "--manager-flavor",
        "manager-max",
        "--ticket-system",
        "linear",
        "--child-worktrees-root",
        str(tmp_path / "worktrees"),
        "--planning-dir",
        str(tmp_path / "planning"),
        "--scratch-dir",
        str(tmp_path / "scratch"),
        "--local-coverage-command",
        _LOCAL_COVERAGE_COMMAND,
        "--output",
        str(output),
    ]
    for ticket in tickets:
        command.extend(("--scoped-ticket", ticket))
    return command


@pytest.mark.parametrize("name", OPERATOR_NAMES)
def test_operator_contract_sidecar_matches_embedded_contract(name: str):
    embedded = _operator_contract(name)
    sidecar = _load_yaml(f"contracts/operators/{name}.yaml")
    projected = {
        key: value
        for key, value in sidecar.items()
        if key not in {"source", "model", "description"}
    }
    assert projected == embedded


def test_linear_contract_disables_estimate_mutation_globally():
    embedded = _operator_contract("linear-operator")
    sidecar = _load_yaml("contracts/operators/linear-operator.yaml")

    assert embedded["estimate_mutation_enabled"] is False
    assert sidecar["estimate_mutation_enabled"] is False

    implementation = _read("agents/implementation-pipeline-orchestrator.md")
    assert "a base-operator value applies to every project" in implementation
    assert "authoritative selected-contract policy" in implementation


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_workflow_sidecar_and_index_match_frontmatter(name: str):
    embedded = _workflow_dispatch_contract(name)
    sidecar = _load_yaml(f"contracts/workflows/{name}.yaml")
    projected = {
        key: value
        for key, value in sidecar.items()
        if key not in {"schema", "source", "workflow_id"}
    }
    assert projected == embedded

    index = json.loads(_read("workflows/index.json"))
    assert index["workflows"][name]["workflow_dispatch_contract"] == embedded


def test_feature_invocation_is_canonical_explicit_and_credential_free():
    contract = _operator_contract("feature-orchestrator")
    inputs = contract["inputs"]
    assert isinstance(inputs, list)
    assert {item["name"] for item in inputs} == FEATURE_INPUT_NAMES
    assert len(inputs) == len(FEATURE_INPUT_NAMES)
    assert _input(contract, "trunk_branch")["required"] is True
    assert _input(contract, "feature_branch")["required"] is True
    assert _input(contract, "feature_worktree_path")["required"] is True
    assert _input(contract, "child_worktrees_root")["required"] is True
    assert _input(contract, "scoped_ticket_list")["type"] == "string_list"
    assert _input(contract, "acceptance_evidence_paths")["type"] == "path_list"
    assert contract["defaults"] == [
        {
            "name": "audit_history_path",
            "value": "${planning_dir}/feature-audit-history.md",
            "source": "base",
        }
    ]
    assert contract["secrets"] == []
    assert "master" not in json.dumps(contract)
    assert "worktree_path" not in {item["name"] for item in inputs}

    workflow_inputs = "\n".join(_workflow_dispatch_contract("feature-development")["inputs"])
    for name in FEATURE_INPUT_NAMES:
        assert name in workflow_inputs
    assert "worktrees root" not in workflow_inputs
    assert "planning root" not in workflow_inputs


def test_feature_coverage_command_contract_and_exact_route_transport():
    feature_contract = _operator_contract("feature-orchestrator")
    coverage_input = _input(feature_contract, "local_coverage_command")
    assert coverage_input["required"] is True
    assert coverage_input["default_source"] == "caller"
    assert "passed unchanged" in coverage_input["description"]
    assert "before feature worktree creation" in coverage_input["description"]

    direct = _section(
        "agents/feature-orchestrator.md", "#### Direct implementation route"
    )
    refactoring = _section(
        "agents/feature-orchestrator.md", "#### Refactoring route"
    )
    for route in (direct, refactoring):
        assert "local_coverage_command=${local_coverage_command}" in route
    assert "auto_merge_after_phase_9=false" in direct

    refactoring_contract = _operator_contract("refactoring-orchestrator")
    nested_input = _input(refactoring_contract, "local_coverage_command")
    assert nested_input["required"] is False
    assert "Required for feature-routed calls" in nested_input["description"]
    child = _fenced_yaml_section(
        "agents/refactoring-orchestrator.md",
        "## Implementation Child Invocation Contract",
    )
    assert child["conditional_common_fields"]["local_coverage_command"] == {
        "required_when": "feature-routed",
        "mapping": "same-name-byte-for-byte",
    }


@pytest.mark.parametrize(
    ("owning_route", "coverage_command"),
    [
        ("implementation-pipeline", None),
        ("implementation-pipeline", " \t "),
        ("refactoring", None),
        ("refactoring", " \t "),
    ],
    ids=[
        "direct-missing",
        "direct-blank",
        "refactoring-missing",
        "refactoring-blank",
    ],
)
def test_feature_route_cli_rejects_missing_or_blank_coverage_before_output(
    tmp_path: Path, owning_route: str, coverage_command: str | None
):
    normalized = _normalize_age255(tmp_path)
    record = deepcopy(
        next(row for row in _inline_records(normalized) if row["owning_route"] == owning_route)
    )
    record["depends_on"] = []
    output = tmp_path / "must-not-exist" / f"{owning_route}.json"
    command = _route_cli_common(tmp_path, output, [record["ticket_id"]])
    coverage_index = command.index("--local-coverage-command")
    if coverage_command is None:
        del command[coverage_index : coverage_index + 2]
    else:
        command[coverage_index + 1] = coverage_command
    command.extend(
        (
            "--ticket-route-map-json",
            json.dumps([record], separators=(",", ":"), sort_keys=True),
        )
    )

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 2
    assert not output.exists()
    assert not output.parent.exists()
    assert completed.stdout == "BLOCKED:missing-local-coverage-command\n"
    assert completed.stderr == ""


@pytest.mark.parametrize(
    "owning_route", ["implementation-pipeline", "refactoring"]
)
def test_feature_route_command_hash_is_exact_and_changed_replay_fails_closed(
    tmp_path: Path, owning_route: str
):
    exact_command = "  coverage-tool --preserve exact bytes  "
    manifest = _normalize_age255(
        tmp_path, local_coverage_command=exact_command
    )
    exact_hash = hashlib.sha256(exact_command.encode("utf-8")).hexdigest()
    assert manifest["local_coverage_command_sha256"] == exact_hash
    assert all(
        "local_coverage_command" not in record["route_payload"]
        for record in manifest["records"]
    )

    record = deepcopy(
        next(record for record in manifest["records"] if record["owning_route"] == owning_route)
    )
    record["depends_on"] = []
    manifest["records"] = [record]
    roots = _attempt_roots(tmp_path)
    attempt = _route_attempt(
        roots,
        ticket_id=record["ticket_id"],
        attempt_number=1,
        owning_route=owning_route,
        dispatch_base_sha="a0" * 20,
        reviewed_head_sha="b0" * 20,
        state="VERIFIED_MERGED",
        transition_sha="c0" * 20,
        local_coverage_command_sha256=exact_hash,
    )
    index = _route_attempt_index(
        tmp_path,
        manifest,
        [attempt],
        initial_feature_sha="a0" * 20,
        current_feature_sha="c0" * 20,
    )
    current = validate_route_attempt_transition(manifest, index)
    assert current["status"] == "VALID", current["errors"]

    changed_manifest = deepcopy(manifest)
    changed_manifest["local_coverage_command_sha256"] = hashlib.sha256(
        b"different coverage command"
    ).hexdigest()
    decision = validate_route_attempt_transition(changed_manifest, index)

    assert decision["status"] == "INVALID"
    assert any("local coverage command mismatch" in error for error in decision["errors"])


def test_feature_workflow_has_one_exact_mirrored_dispatch_surface():
    workflow = _read("workflows/feature-development.md")
    assert workflow.count("## Workflow Dispatch Surface\n") == 1
    assert _fenced_yaml_section(
        "workflows/feature-development.md", "## Workflow Dispatch Surface"
    ) == _workflow_dispatch_contract("feature-development")


def test_route_record_schema_is_parsed_and_strict():
    schema = _fenced_yaml_section(
        "agents/feature-orchestrator.md", "## Route Record Schema"
    )
    assert schema["schema"] == "feature-route-source-v2"
    assert schema["source_cardinality"] == "exactly-one"
    inline = schema["ticket_route_map"]
    assert inline["source_schema"] == "feature-inline-route-map-v2"
    assert inline["additional_properties"] is False
    assert set(inline["required_keys"]) == set(inline["allowed_keys"]) == {
        "ticket_id",
        "successor_id",
        "title",
        "brief_path",
        "surfaces",
        "owning_route",
        "depends_on",
        "branch_name",
        "ticket_source",
        "route_payload",
    }
    assert inline["ticket_source"] == {
        "cardinality": "exactly-one",
        "allowed_keys": ["jira_issue_key", "linear_issue_key"],
        "backend_rule": "key-matches-ticket_system",
        "identity_rule": "issue-key-value-equals-ticket_id",
        "forbidden_keys": ["wu_brief_path"],
    }
    assert _ROUTE_MODULE.TICKET_SOURCE_KEYS == {"jira_issue_key", "linear_issue_key"}
    successor = schema["successor_manifest_path"]
    assert successor["top_level_type"] == "mapping"
    assert successor["dependency_namespace"] == "successor_id"
    assert successor["source_backend_binding"] == "linear"
    assert successor["successor"]["additional_properties"] is False
    assert set(successor["successor"]["required_keys"]) == {
        "successor_id",
        "title",
        "brief_path",
        "route",
        "depends_on",
        "surfaces",
        "ticket_key",
    }
    assert schema["normalized_output_schema"] == "feature-route-manifest-v2"
    assert schema["normalizer_cli_source_xor"] == [
        "--ticket-route-map-json",
        "--successor-manifest",
    ]


def test_pr_writer_closed_pr_rules_preserve_verified_merged_refs_only():
    reference_rules = _between(
        "agents/pr-writer.md", "### Reference rules\n", "### File-path references are fine\n"
    )
    assert "PRs merged to and reachable from" in reference_rules
    assert "supplied through `merged_refs` and verified merged" in reference_rules
    assert "Closed-rejected PRs" in reference_rules
    assert "❌ **Forbidden:** Closed PRs (whether" not in reference_rules

    sidecar = _load_yaml("contracts/operators/pr-writer.yaml")
    assert "must be reachable from base_sha" in _input(sidecar, "merged_refs")[
        "description"
    ]
    assert "no unverified closed-PR" in _read("AGENTS.md")


def test_route_attempt_fixture_names_use_the_production_rule():
    assert _route_attempt_names("AGE / 260", 7) == (
        "age-260",
        "age-260-attempt-0007",
    )


def test_route_parser_rejects_duplicate_keys_before_normalization():
    duplicate = '{"schema_version":1,"schema_version":1}'
    with pytest.raises(RouteManifestError, match="duplicate key: schema_version"):
        json.loads(duplicate, object_pairs_hook=_ROUTE_MODULE._unique_object)


def test_real_age255_manifest_normalizes_routes_dependencies_and_waves(tmp_path: Path):
    result = _normalize_age255(tmp_path)
    rows = {row["ticket_id"]: row for row in result["records"]}
    assert result["source_backend"] == result["ticket_system"] == "linear"
    assert result["topological_order"] == ["AGE-257", "AGE-256", "AGE-258", "AGE-259"]
    assert result["waves"] == [
        {"index": 0, "tickets": ["AGE-257", "AGE-256", "AGE-258"]},
        {"index": 1, "tickets": ["AGE-259"]},
    ]
    assert rows["AGE-259"]["depends_on"] == ["AGE-257", "AGE-256", "AGE-258"]
    assert rows["AGE-259"]["route_payload"] == {}
    target = json.loads(rows["AGE-257"]["route_payload"]["target_list"])
    bounds = json.loads(rows["AGE-257"]["route_payload"]["slice_bounds"])
    assert target["surfaces"] == ["S2", "S3", "S9"]
    assert Path(target["brief_path"]).name == "AGE255-S01-ATTEMPT-SEAMS.md"
    assert bounds == {
        "successor_id": "AGE255-S01-ATTEMPT-SEAMS",
        "surfaces": ["S2", "S3", "S9"],
        "title": "Extract balanced and resume attempt-execution seams",
    }


def test_feature_route_manifest_emits_exact_nested_route_identity_and_source_hash(
    tmp_path: Path,
):
    source_path, tickets = _age255_manifest(tmp_path)
    scope_path = tmp_path / "feature-scope.md"
    scope_path.write_text("# Feature scope\n", encoding="utf-8")

    result = normalize_successor_manifest(
        source_path,
        feature_id="AGE-255",
        feature_scope_path=scope_path,
        feature_branch="feature/hourly-suspicious-process-investigator",
        trunk_branch="main",
        manager_flavor="manager-max",
        ticket_system="linear",
        scoped_ticket_list=tickets,
        child_worktrees_root=tmp_path / "worktrees",
        planning_dir=tmp_path / "planning",
        scratch_dir=tmp_path / "scratch",
        local_coverage_command=_LOCAL_COVERAGE_COMMAND,
    )
    route = next(row for row in result["records"] if row["ticket_id"] == "AGE-259")

    assert set(result) == {
        "schema",
        "source_schema",
        "feature_id",
        "feature_scope_path",
        "local_coverage_command_sha256",
        "trunk_branch",
        "feature_branch",
        "ticket_system",
        "source_backend",
        "manager_flavor",
        "source_kind",
        "source_path",
        "source_sha256",
        "topological_order",
        "waves",
        "records",
    }
    assert {
        field: result[field]
        for field in (
            "schema",
            "source_schema",
            "source_kind",
            "source_path",
            "source_sha256",
            "source_backend",
            "local_coverage_command_sha256",
            "feature_branch",
            "trunk_branch",
            "ticket_system",
        )
    } == {
        "schema": "feature-route-manifest-v2",
        "source_schema": "feature-successor-envelope-v1",
        "source_kind": "successor_manifest_path",
        "source_path": str(source_path),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_backend": "linear",
        "local_coverage_command_sha256": _LOCAL_COVERAGE_COMMAND_SHA256,
        "feature_branch": "feature/hourly-suspicious-process-investigator",
        "trunk_branch": "main",
        "ticket_system": "linear",
    }
    assert set(route) == {
        "ticket_id",
        "successor_id",
        "title",
        "brief_path",
        "surfaces",
        "owning_route",
        "depends_on",
        "branch_name",
        "ticket_source",
        "route_payload",
        "route_worktree_path",
        "route_planning_dir",
        "route_scratch_dir",
    }
    assert route["branch_name"] == "route/age-259"
    assert route["route_worktree_path"] == str(tmp_path / "worktrees" / "age-259")
    assert route["route_planning_dir"] == str(
        tmp_path / "planning" / "routes" / "age-259"
    )
    assert route["route_scratch_dir"] == str(
        tmp_path / "scratch" / "routes" / "age-259"
    )


@pytest.mark.skipif(
    not REAL_AGE255_MANIFEST.is_file(),
    reason="external AGE-255 provenance source is unavailable",
)
def test_checked_in_age255_fixture_is_byte_identical_to_real_manifest():
    assert (REPO_ROOT / "tests/fixtures/age-255-successor-manifest.json").read_bytes() == (
        REAL_AGE255_MANIFEST.read_bytes()
    )


def test_byte_identical_age255_fixture_rejects_jira_without_output(tmp_path: Path):
    fixture = REPO_ROOT / "tests/fixtures/age-255-successor-manifest.json"
    scope = tmp_path / "feature-scope.md"
    scope.write_text("# Feature scope\n", encoding="utf-8")
    output = tmp_path / "normalized" / "route-manifest.json"
    manifest = json.loads(fixture.read_text(encoding="utf-8"))
    command = [
        sys.executable,
        str(REPO_ROOT / "tools/feature_route_manifest.py"),
        "--successor-manifest",
        str(fixture),
        "--feature-id",
        "AGE-255",
        "--feature-scope-path",
        str(scope),
        "--feature-branch",
        "feature/hourly-suspicious-process-investigator",
        "--trunk-branch",
        "main",
        "--manager-flavor",
        "manager-max",
        "--ticket-system",
        "jira",
        "--child-worktrees-root",
        str(tmp_path / "worktrees"),
        "--planning-dir",
        str(tmp_path / "planning"),
        "--scratch-dir",
        str(tmp_path / "scratch"),
        "--local-coverage-command",
        _LOCAL_COVERAGE_COMMAND,
        "--output",
        str(output),
    ]
    for successor in manifest["successors"]:
        command.extend(("--scoped-ticket", successor["ticket_key"]))

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 2
    assert "kind=age-255-estimate-clamp-successor-manifest requires ticket_system=linear" in (
        completed.stdout
    )
    assert "linear_readback requires ticket_system=linear" in completed.stdout
    assert "successors[0].ticket_url requires ticket_system=linear" in completed.stdout
    assert not output.exists()


@pytest.mark.parametrize(
    "ticket_url",
    [
        "https://example.atlassian.net/browse/AGE-257",
        "https://tickets.example.com/AGE-257",
    ],
    ids=["jira-host-on-linear-source", "unknown-ticket-host"],
)
def test_successor_ticket_url_host_must_match_selected_backend(
    tmp_path: Path, ticket_url: str
):
    with pytest.raises(RouteManifestError):
        _normalize_age255(
            tmp_path,
            lambda manifest: manifest["successors"][0].update(ticket_url=ticket_url),
        )


def test_feature_route_manifest_cli_writes_validated_output(tmp_path: Path):
    manifest_path, tickets = _age255_manifest(tmp_path)
    scope = tmp_path / "feature-scope.md"
    scope.write_text("# Feature scope\n", encoding="utf-8")
    output = tmp_path / "normalized" / "route-manifest.json"
    command = [
        sys.executable,
        str(REPO_ROOT / "tools/feature_route_manifest.py"),
        "--successor-manifest",
        str(manifest_path),
        "--feature-id",
        "AGE-255",
        "--feature-scope-path",
        str(scope),
        "--feature-branch",
        "feature/hourly-suspicious-process-investigator",
        "--trunk-branch",
        "main",
        "--manager-flavor",
        "manager-max",
        "--ticket-system",
        "linear",
        "--child-worktrees-root",
        str(tmp_path / "worktrees"),
        "--planning-dir",
        str(tmp_path / "planning"),
        "--scratch-dir",
        str(tmp_path / "scratch"),
        "--local-coverage-command",
        _LOCAL_COVERAGE_COMMAND,
        "--output",
        str(output),
    ]
    for ticket in tickets:
        command.extend(("--scoped-ticket", ticket))

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == f"feature-route-manifest: normalized; output={output}\n"
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["schema"] == "feature-route-manifest-v2"
    assert result["topological_order"] == ["AGE-257", "AGE-256", "AGE-258", "AGE-259"]


def test_feature_route_manifest_cli_blocks_on_output_io_error(monkeypatch, capsys):
    def fail_write(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(_ROUTE_MODULE, "normalize_route_source", lambda **_kwargs: {})
    monkeypatch.setattr(_ROUTE_MODULE, "write_manifest", fail_write)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "feature_route_manifest.py",
            "--ticket-route-map-json",
            "[]",
            "--feature-id",
            "AGE-255",
            "--feature-scope-path",
            "/scope.md",
            "--feature-branch",
            "feature/route",
            "--trunk-branch",
            "main",
            "--manager-flavor",
            "manager-max",
            "--ticket-system",
            "linear",
            "--scoped-ticket",
            "AGE-256",
            "--child-worktrees-root",
            "/worktrees",
            "--planning-dir",
            "/planning",
            "--scratch-dir",
            "/scratch",
            "--local-coverage-command",
            _LOCAL_COVERAGE_COMMAND,
            "--output",
            "/route-manifest.json",
        ],
    )

    assert _ROUTE_MODULE.main() == 2
    assert capsys.readouterr().out == (
        "BLOCKED:invalid-ticket-route-manifest: disk full\n"
    )


def test_inline_implementation_and_refactoring_records_share_successor_route_graph(
    tmp_path: Path,
):
    successor = _normalize_age255(tmp_path)
    inline = normalize_ticket_route_map(
        json.dumps(_inline_records(successor), separators=(",", ":"), sort_keys=True),
        feature_id="AGE-255",
        feature_scope_path=tmp_path / "feature-scope.md",
        feature_branch="feature/hourly-suspicious-process-investigator",
        trunk_branch="main",
        manager_flavor="manager-max",
        ticket_system="linear",
        scoped_ticket_list=successor["topological_order"],
        child_worktrees_root=tmp_path / "worktrees",
        planning_dir=tmp_path / "planning",
        scratch_dir=tmp_path / "scratch",
        local_coverage_command=_LOCAL_COVERAGE_COMMAND,
    )

    assert {row["owning_route"] for row in inline["records"]} == {
        "implementation-pipeline",
        "refactoring",
    }
    graph_fields = (
        "feature_id",
        "feature_scope_path",
        "trunk_branch",
        "feature_branch",
        "ticket_system",
        "source_backend",
        "manager_flavor",
        "topological_order",
        "waves",
        "records",
    )
    successor_graph = {key: successor[key] for key in graph_fields}
    inline_graph = {key: inline[key] for key in graph_fields}
    assert json.dumps(successor_graph, sort_keys=True, separators=(",", ":")).encode() == (
        json.dumps(inline_graph, sort_keys=True, separators=(",", ":")).encode()
    )
    assert set(inline["records"][0]) == set(successor["records"][0])
    assert inline["source_schema"] == "feature-inline-route-map-v2"
    assert inline["source_kind"] == "ticket_route_map"
    assert inline["source_path"] is None


@pytest.mark.parametrize(
    ("owning_route", "ticket_system", "ticket_id"),
    [
        ("implementation-pipeline", "linear", "AGE-701"),
        ("refactoring", "linear", "AGE-702"),
        ("implementation-pipeline", "jira", "OPS-701"),
        ("refactoring", "jira", "OPS-702"),
    ],
    ids=[
        "implementation-linear",
        "refactoring-linear",
        "implementation-jira",
        "refactoring-jira",
    ],
)
def test_inline_feature_routes_preserve_existing_provider_issue_identity(
    tmp_path: Path, owning_route: str, ticket_system: str, ticket_id: str
):
    successor = _normalize_age255(tmp_path)
    record = deepcopy(
        next(row for row in _inline_records(successor) if row["owning_route"] == owning_route)
    )
    issue_key_field = f"{ticket_system}_issue_key"
    record.update(
        ticket_id=ticket_id,
        branch_name=f"route/{ticket_id.lower()}",
        depends_on=[],
        ticket_source={issue_key_field: ticket_id},
    )

    result = normalize_ticket_route_map(
        json.dumps([record], separators=(",", ":"), sort_keys=True),
        feature_id="AGE-255",
        feature_scope_path=tmp_path / "feature-scope.md",
        feature_branch="feature/hourly-suspicious-process-investigator",
        trunk_branch="main",
        manager_flavor="manager-max",
        ticket_system=ticket_system,
        scoped_ticket_list=[ticket_id],
        child_worktrees_root=tmp_path / "positive-worktrees",
        planning_dir=tmp_path / "positive-planning",
        scratch_dir=tmp_path / "positive-scratch",
        local_coverage_command=_LOCAL_COVERAGE_COMMAND,
    )

    normalized = result["records"][0]
    assert normalized["owning_route"] == owning_route
    assert normalized["ticket_id"] == ticket_id
    assert normalized["ticket_source"] == {issue_key_field: ticket_id}


def test_inline_route_cli_writes_mixed_route_manifest(tmp_path: Path):
    successor = _normalize_age255(tmp_path)
    route_json = json.dumps(
        _inline_records(successor), separators=(",", ":"), sort_keys=True
    )
    output = tmp_path / "normalized" / "inline-route-manifest.json"
    command = _route_cli_common(tmp_path, output, successor["topological_order"])
    command.extend(("--ticket-route-map-json", route_json))

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["source_kind"] == "ticket_route_map"
    assert {row["owning_route"] for row in result["records"]} == {
        "implementation-pipeline",
        "refactoring",
    }


def test_inline_route_duplicate_json_keys_fail_before_normalization(tmp_path: Path):
    successor = _normalize_age255(tmp_path)
    route_json = json.dumps(
        _inline_records(successor), separators=(",", ":"), sort_keys=True
    ).replace('"ticket_id":"AGE-257"', '"ticket_id":"AGE-257","ticket_id":"AGE-257"', 1)

    with pytest.raises(RouteManifestError, match="duplicate key: ticket_id"):
        normalize_ticket_route_map(
            route_json,
            feature_id="AGE-255",
            feature_scope_path=tmp_path / "feature-scope.md",
            feature_branch="feature/hourly-suspicious-process-investigator",
            trunk_branch="main",
            manager_flavor="manager-max",
            ticket_system="linear",
            scoped_ticket_list=successor["topological_order"],
            child_worktrees_root=tmp_path / "worktrees",
            planning_dir=tmp_path / "planning",
            scratch_dir=tmp_path / "scratch",
            local_coverage_command=_LOCAL_COVERAGE_COMMAND,
        )


def test_inline_route_cli_rejects_duplicate_json_keys_without_output(tmp_path: Path):
    successor = _normalize_age255(tmp_path)
    route_json = json.dumps(
        _inline_records(successor), separators=(",", ":"), sort_keys=True
    ).replace('"ticket_id":"AGE-257"', '"ticket_id":"AGE-257","ticket_id":"AGE-257"', 1)
    output = tmp_path / "normalized" / "must-not-exist.json"
    command = _route_cli_common(tmp_path, output, successor["topological_order"])
    command.extend(("--ticket-route-map-json", route_json))

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 2
    assert "duplicate key: ticket_id" in completed.stdout
    assert not output.exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[0].update(unknown="value"),
        lambda rows: rows[0].pop("title"),
        lambda rows: rows[0].update(ticket_id=" AGE-257"),
        lambda rows: rows[0].update(ticket_source={"jira_issue_key": rows[0]["ticket_id"]}),
        lambda rows: rows[0].update(branch_name="bad..branch"),
        lambda rows: rows[1].update(branch_name=rows[0]["branch_name"]),
        lambda rows: rows[3].update(depends_on=["UNKNOWN"]),
        lambda rows: rows[3].update(depends_on=[rows[0]["ticket_id"], rows[0]["ticket_id"]]),
        lambda rows: (
            rows[0].update(depends_on=[rows[1]["ticket_id"]]),
            rows[1].update(depends_on=[rows[0]["ticket_id"]]),
        ),
    ],
    ids=[
        "unknown-field",
        "missing-field",
        "whitespace-ticket-identity",
        "backend-source-mismatch",
        "invalid-branch",
        "duplicate-branch",
        "unknown-dependency",
        "duplicate-dependency",
        "dependency-cycle",
    ],
)
def test_inline_route_closed_record_and_dependency_negatives(tmp_path: Path, mutate):
    with pytest.raises(RouteManifestError):
        _normalize_inline_age255(tmp_path, mutate)


def test_inline_route_rejects_protected_branch_identity(tmp_path: Path):
    with pytest.raises(RouteManifestError, match="protected route branch"):
        _normalize_inline_age255(
            tmp_path,
            feature_branch="route/age-257",
        )


def test_inline_route_rejects_colliding_slug_and_derived_paths(tmp_path: Path):
    def collide(rows):
        for row, ticket_id in zip(rows[:2], ("A B", "A?B"), strict=True):
            row["ticket_id"] = ticket_id
            row["ticket_source"] = {"linear_issue_key": ticket_id}
            row["branch_name"] = "route/a-b"

    with pytest.raises(RouteManifestError, match="route slugs collide"):
        _normalize_inline_age255(tmp_path, collide)


@pytest.mark.parametrize(
    "owning_route",
    ["implementation-pipeline", "refactoring"],
    ids=["implementation", "refactoring"],
)
def test_inline_feature_route_rejects_wu_brief_before_output_or_directories(
    tmp_path: Path, owning_route: str
):
    successor = _normalize_age255(tmp_path)
    record = deepcopy(
        next(row for row in _inline_records(successor) if row["owning_route"] == owning_route)
    )
    record["depends_on"] = []
    record["ticket_source"] = {"wu_brief_path": record["brief_path"]}
    output = tmp_path / "normalizer-output" / f"{owning_route}.json"
    command = _route_cli_common(tmp_path, output, [record["ticket_id"]])
    command.extend(
        (
            "--ticket-route-map-json",
            json.dumps([record], separators=(",", ":"), sort_keys=True),
        )
    )

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 2
    assert completed.stdout.startswith("BLOCKED:invalid-ticket-route-manifest:")
    assert "feature routes require an existing backend issue key" in completed.stdout
    assert "do not accept wu_brief_path" in completed.stdout
    assert not output.exists()
    assert not output.parent.exists()
    for root in ("worktrees", "planning", "scratch"):
        assert not (tmp_path / root).exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: next(row for row in rows if row["owning_route"] == "refactoring").update(
            route_payload=None
        ),
        lambda rows: next(row for row in rows if row["owning_route"] == "refactoring").update(
            route_payload={"target_list": "", "slice_bounds": "{}"}
        ),
        lambda rows: next(row for row in rows if row["owning_route"] == "refactoring").update(
            route_payload={"target_list": "{}", "slice_bounds": "{}", "unknown": "{}"}
        ),
        lambda rows: next(
            row for row in rows if row["owning_route"] == "implementation-pipeline"
        ).update(route_payload={"unknown": "{}"}),
        lambda rows: next(row for row in rows if row["owning_route"] == "refactoring").update(
            route_payload={"target_list": '{"b":1,"a":2}', "slice_bounds": "{}"}
        ),
        lambda rows: rows[0].update(owning_route="unknown-route"),
    ],
    ids=[
        "null-payload",
        "blank-payload-field",
        "unknown-refactoring-payload-field",
        "implementation-payload-field",
        "noncanonical-payload-json",
        "unknown-route",
    ],
)
def test_inline_route_payload_negatives(tmp_path: Path, mutate):
    with pytest.raises(RouteManifestError):
        _normalize_inline_age255(tmp_path, mutate)


@pytest.mark.parametrize("source_case", ["neither", "both"])
def test_route_cli_enforces_source_xor_before_parse_without_output(
    tmp_path: Path, source_case: str
):
    _normalize_age255(tmp_path)
    output = tmp_path / "normalized" / "must-not-exist.json"
    command = _route_cli_common(
        tmp_path, output, ["AGE-257", "AGE-256", "AGE-258", "AGE-259"]
    )
    if source_case == "both":
        command.extend(
            (
                "--successor-manifest",
                str(tmp_path / "does-not-exist.json"),
                "--ticket-route-map-json",
                "not-json",
            )
        )

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 2
    assert not output.exists()
    assert "not allowed with argument" in completed.stderr or "one of the arguments" in completed.stderr


def test_route_function_enforces_source_xor_before_parse(tmp_path: Path):
    common = {
        "feature_id": "AGE-255",
        "feature_scope_path": tmp_path / "unread-scope.md",
        "feature_branch": "feature/hourly-suspicious-process-investigator",
        "trunk_branch": "main",
        "manager_flavor": "manager-max",
        "ticket_system": "linear",
        "scoped_ticket_list": ["AGE-257"],
        "child_worktrees_root": tmp_path / "worktrees",
        "planning_dir": tmp_path / "planning",
        "scratch_dir": tmp_path / "scratch",
        "local_coverage_command": _LOCAL_COVERAGE_COMMAND,
    }
    with pytest.raises(RouteManifestError, match="exactly one"):
        normalize_route_source(**common)
    with pytest.raises(RouteManifestError, match="exactly one"):
        normalize_route_source(
            successor_manifest_path=tmp_path / "does-not-exist.json",
            ticket_route_map_json="not-json",
            **common,
        )


def test_route_cli_help_exposes_discriminated_sources():
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/feature_route_manifest.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "(--successor-manifest SUCCESSOR_MANIFEST | --ticket-route-map-json" in completed.stdout


@pytest.mark.parametrize(
    ("branch_flag", "bad_branch"),
    [
        ("--trunk-branch", "bad..branch"),
        ("--trunk-branch", "origin/main"),
        ("--trunk-branch", "@{-1}"),
        ("--feature-branch", "refs/heads/feature/unsafe"),
        ("--feature-branch", " feature/unsafe"),
    ],
    ids=[
        "invalid-trunk-syntax",
        "remote-tracking-trunk",
        "normalization-ambiguous-trunk",
        "full-ref-feature",
        "whitespace-feature",
    ],
)
def test_feature_route_manifest_cli_rejects_invalid_explicit_branches_before_output(
    tmp_path: Path, branch_flag: str, bad_branch: str
):
    manifest_path, tickets = _age255_manifest(tmp_path)
    scope = tmp_path / "feature-scope.md"
    scope.write_text("# Feature scope\n", encoding="utf-8")
    output = tmp_path / "normalized" / "route-manifest.json"
    values = {
        "--feature-branch": "feature/hourly-suspicious-process-investigator",
        "--trunk-branch": "main",
    }
    values[branch_flag] = bad_branch
    command = [
        sys.executable,
        str(REPO_ROOT / "tools/feature_route_manifest.py"),
        "--successor-manifest",
        str(manifest_path),
        "--feature-id",
        "AGE-255",
        "--feature-scope-path",
        str(scope),
        "--feature-branch",
        values["--feature-branch"],
        "--trunk-branch",
        values["--trunk-branch"],
        "--manager-flavor",
        "manager-max",
        "--ticket-system",
        "linear",
        "--child-worktrees-root",
        str(tmp_path / "worktrees"),
        "--planning-dir",
        str(tmp_path / "planning"),
        "--scratch-dir",
        str(tmp_path / "scratch"),
        "--local-coverage-command",
        _LOCAL_COVERAGE_COMMAND,
        "--output",
        str(output),
    ]
    for ticket in tickets:
        command.extend(("--scoped-ticket", ticket))

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 2
    assert completed.stdout.startswith("BLOCKED:invalid-ticket-route-manifest:")
    assert not output.exists()


def test_feature_route_manifest_rejects_protected_branch_equality(tmp_path: Path):
    manifest_path, tickets = _age255_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["feature_branch"] = "main"
    manifest["handoff"]["feature_branch"] = "main"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    scope = tmp_path / "feature-scope.md"
    scope.write_text("# Feature scope\n", encoding="utf-8")

    with pytest.raises(RouteManifestError, match="feature and trunk branches must differ"):
        normalize_successor_manifest(
            manifest_path,
            feature_id="AGE-255",
            feature_scope_path=scope,
            feature_branch="main",
            trunk_branch="main",
            manager_flavor="manager-max",
            ticket_system="linear",
            scoped_ticket_list=tickets,
            child_worktrees_root=tmp_path / "worktrees",
            planning_dir=tmp_path / "planning",
            scratch_dir=tmp_path / "scratch",
            local_coverage_command=_LOCAL_COVERAGE_COMMAND,
        )


def test_direct_prerequisite_can_form_an_earlier_ready_wave(tmp_path: Path):
    def mutate(manifest):
        manifest["successors"][0]["route"] = "implementation-pipeline"
        manifest["handoff"]["owning_routes"]["AGE255-S01-ATTEMPT-SEAMS"] = (
            "implementation-pipeline"
        )

    result = _normalize_age255(tmp_path, mutate)
    first = result["records"][0]
    assert first["owning_route"] == "implementation-pipeline"
    assert first["ticket_id"] in result["waves"][0]["tickets"]
    assert "AGE-259" in result["waves"][1]["tickets"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda manifest: manifest.update(successors=[]),
        lambda manifest: manifest["successors"][0].update(title=None),
        lambda manifest: manifest["successors"][0].update(unknown="value"),
        lambda manifest: manifest["successors"][3].update(depends_on=["UNKNOWN"]),
        lambda manifest: manifest["successors"][0].update(surfaces=[]),
        lambda manifest: manifest["handoff"].update(fresh_per_ticket_worktrees=False),
    ],
    ids=[
        "empty",
        "null",
        "unknown-key",
        "unknown-dependency",
        "empty-surfaces",
        "invalid-handoff",
    ],
)
def test_successor_manifest_malformed_payloads_fail_closed(tmp_path: Path, mutate):
    with pytest.raises(RouteManifestError):
        _normalize_age255(tmp_path, mutate)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda manifest: manifest["successors"][0].update(ticket_key=".."),
        lambda manifest: manifest["successors"][0].update(ticket_key="!!!"),
        lambda manifest: manifest["successors"][0].update(ticket_key=".invalid"),
        lambda manifest: (
            manifest["successors"][0].update(ticket_key="A B"),
            manifest["successors"][1].update(ticket_key="A?B"),
        ),
    ],
    ids=["traversal", "empty-slug", "invalid-branch", "slug-collision"],
)
def test_successor_manifest_unsafe_derived_identities_fail_closed(
    tmp_path: Path, mutate
):
    with pytest.raises(RouteManifestError):
        _normalize_age255(tmp_path, mutate)


@pytest.mark.parametrize("root_case", ["dotdot", "same-root", "symlink"])
def test_feature_route_manifest_rejects_noncanonical_or_aliased_roots(
    tmp_path: Path, root_case: str
):
    manifest_path, tickets = _age255_manifest(tmp_path)
    scope = tmp_path / "feature-scope.md"
    scope.write_text("# Feature scope\n", encoding="utf-8")
    worktrees = tmp_path / "worktrees"
    planning = tmp_path / "planning"
    scratch = tmp_path / "scratch"
    if root_case == "dotdot":
        planning = Path(f"{tmp_path}/planning/x/..")
    elif root_case == "same-root":
        planning = worktrees
    else:
        real = tmp_path / "real-worktrees"
        real.mkdir()
        alias = tmp_path / "worktrees-alias"
        alias.symlink_to(real, target_is_directory=True)
        worktrees = alias

    with pytest.raises(RouteManifestError):
        normalize_successor_manifest(
            manifest_path,
            feature_id="AGE-255",
            feature_scope_path=scope,
            feature_branch="feature/hourly-suspicious-process-investigator",
            trunk_branch="main",
            manager_flavor="manager-max",
            ticket_system="linear",
            scoped_ticket_list=tickets,
            child_worktrees_root=worktrees,
            planning_dir=planning,
            scratch_dir=scratch,
            local_coverage_command=_LOCAL_COVERAGE_COMMAND,
        )


def test_route_source_xor_and_validation_precede_normalization():
    route_section = _section("agents/feature-orchestrator.md", "## Route Record Schema")
    assert "exactly one non-empty top-level route source" in route_section
    assert "Both or neither returns `BLOCKED:invalid-ticket-route-manifest`" in route_section
    assert "The two source forms are discriminated, not aliases" in route_section
    assert "Validate the complete raw record set before normalization or dispatch" in route_section
    assert route_section.index("Duplicate keys are invalid") < route_section.index(
        "Validate the complete raw record set"
    )

    canonical = _section("agents/feature-orchestrator.md", "## Canonical Invocation")
    contract = _operator_contract("feature-orchestrator")
    for name in ("ticket_route_map", "successor_manifest_path"):
        assert "mutually exclusive" in _input(contract, name)["description"]
    workflow = _workflow_dispatch_contract("feature-development")
    assert "exactly one route source" in "\n".join(workflow["inputs"])
    assert "no `master`, `main`" in canonical
    assert "tools/feature_route_manifest.py" in route_section


@pytest.mark.parametrize(
    ("ticket_route_map", "successor_manifest_path"),
    [(None, None), ("inline-records", "/tmp/routes.yaml")],
    ids=["neither-route-source", "both-route-sources"],
)
def test_invalid_route_source_cardinality_is_fail_closed(
    ticket_route_map: str | None, successor_manifest_path: str | None
):
    selected = [
        value
        for value in (ticket_route_map, successor_manifest_path)
        if isinstance(value, str) and value
    ]
    assert len(selected) != 1
    route_section = _section("agents/feature-orchestrator.md", "## Route Record Schema")
    assert "BLOCKED:invalid-ticket-route-manifest" in route_section


def test_direct_dispatch_carries_exact_ticket_source_and_feature_owned_merge():
    direct = _section(
        "agents/feature-orchestrator.md", "#### Direct implementation route"
    )
    for value in (
        "jira_issue_key",
        "linear_issue_key",
        "feature route never dispatches `wu_brief_path`",
        "never enters Phase 0 ticket creation",
        "ticket_system",
        "matching backend configuration",
        "worktree_path=${route_worktree_path}",
        "planning_dir=${route_planning_dir}",
        "scratch_dir=${route_scratch_dir}",
        "branch_name",
        "base_branch=${feature_branch}",
        "auto_merge_after_phase_9=false",
        "status=VERIFIED_DRAFT_PR",
        "is_draft=true",
        "phase_8_reviewed_is_draft=true",
        "${planning_dir}/route-evidence/<ticket_slug>-attempt-<NNNN>.evidence.json",
        "no attempt process-report or acceptance hash",
        "validate-pr-currentness --expected-draft true",
        "route-acceptance/<ticket_slug>-attempt-<NNNN>.acceptance.json",
        'gh pr ready "${pr_url}" --repo "${repo}"',
        "Immediately after the command returns",
        "isDraft=false",
        "validate-pr-currentness --expected-draft false",
        "validate-route-artifact-lineage",
        "status=MERGE_AUTHORIZED",
        "state=STALE_CURRENTNESS",
        "REPLAY_REQUIRED",
        'gh pr ready --undo "${pr_url}" --repo "${repo}"',
        "validate-ready-state-restoration",
        "owner=feature-direct-merge",
        "BLOCKED:ready-state-restoration-failed",
        "BLOCKED:merge-attempt-started",
        "A sibling route merge or route-head movement immediately after ready",
        'gh pr merge --repo "${repo}" --squash "${pr_url}" --match-head-commit "${reviewed_head_oid}"',
        "state=MERGED",
        "mergeCommit.oid",
        "sole parent to equal `reviewed_base_sha`",
        "acceptance-envelope path/SHA-256",
    ):
        assert value in direct
    assert "auto_merge_after_phase_9=true" not in direct


def test_direct_verified_draft_ready_capture_guard_merge_order_is_current():
    direct = _section(
        "agents/feature-orchestrator.md", "#### Direct implementation route"
    )
    evidence = direct.index("Freeze `${planning_dir}/route-evidence")
    process_audit = direct.index("Then run the two-stage attempt process proof")
    pre_ready = direct.index("validate-pr-currentness --expected-draft true")
    acceptance = direct.index("Only after route evidence, the route-only pre-audit proof")
    ready = direct.index('gh pr ready "${pr_url}" --repo "${repo}"')
    post_ready_capture = direct.index("Immediately after the command returns")
    post_ready_guard = direct.index("validate-pr-currentness --expected-draft false")
    lineage = direct.index("validate-route-artifact-lineage")
    merge = direct.index('gh pr merge --repo "${repo}"')
    assert (
        evidence
        < process_audit
        < pre_ready
        < acceptance
        < ready
        < post_ready_capture
        < post_ready_guard
        < lineage
        < merge
    )

    reviewed_draft = _provider_bundle(is_draft=True)
    pre_ready_decision = validate_pr_currentness(
        reviewed_draft,
        reviewed_draft,
        reviewed_draft["base_ref_oid"],
        reviewed_draft["head_ref_oid"],
        context="feature-direct-pre-ready",
        expected_draft=True,
    )
    post_ready_decision = validate_pr_currentness(
        reviewed_draft,
        _provider_bundle(is_draft=False),
        reviewed_draft["base_ref_oid"],
        reviewed_draft["head_ref_oid"],
        context="feature-direct-post-ready",
        expected_draft=False,
    )
    assert pre_ready_decision["status"] == "READY"
    assert post_ready_decision["status"] == "READY"
    assert post_ready_decision["immediate"]["is_draft"] is False


def test_sibling_direct_merge_advancing_feature_base_refuses_stale_route_merge():
    reviewed = _provider_bundle(base_sha="f0" * 20)
    immediate = _provider_bundle(base_sha="f1" * 20)
    transition = validate_pr_currentness(
        reviewed,
        immediate,
        "f1" * 20,
        reviewed["head_ref_oid"],
        context="feature-direct-pre-merge",
    )
    assert transition["status"] == "STALE_CURRENTNESS"
    assert transition["final_equality_result"] == "FAIL"
    direct = _section(
        "agents/feature-orchestrator.md", "#### Direct implementation route"
    )
    assert "A sibling route merge or route-head movement immediately after ready" in direct
    assert 'gh pr ready --undo "${pr_url}" --repo "${repo}"' in direct
    assert "Only exact `REPLAY_REQUIRED`" in direct
    assert "Unchanged head alone cannot preserve acceptance" in direct


def test_two_direct_siblings_integrate_as_serial_accepted_attempts(tmp_path: Path):
    manifest = _normalize_age255(tmp_path)
    records = deepcopy(manifest["records"][:2])
    for record in records:
        record["owning_route"] = "implementation-pipeline"
        record["depends_on"] = []
    manifest["records"] = records
    roots = _attempt_roots(tmp_path)
    base_0, base_1, base_2 = "10" * 20, "11" * 20, "12" * 20
    attempts = [
        _route_attempt(
            roots,
            ticket_id=records[0]["ticket_id"],
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha=base_0,
            reviewed_head_sha="21" * 20,
            state="VERIFIED_MERGED",
            transition_sha=base_1,
        ),
        _route_attempt(
            roots,
            ticket_id=records[1]["ticket_id"],
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha=base_1,
            reviewed_head_sha="22" * 20,
            state="VERIFIED_MERGED",
            transition_sha=base_2,
        ),
    ]
    index = _route_attempt_index(
        tmp_path,
        manifest,
        attempts,
        initial_feature_sha=base_0,
        current_feature_sha=base_2,
    )

    decision = validate_route_attempt_transition(manifest, index)

    assert decision["status"] == "VALID"
    assert decision["accepted_attempts"] == {
        records[0]["ticket_id"]: 1,
        records[1]["ticket_id"]: 1,
    }
    stale_acceptance = deepcopy(index)
    stale_acceptance["accepted_attempts"][0]["acceptance_sha256"] = "0" * 64
    assert validate_route_attempt_transition(manifest, stale_acceptance)[
        "status"
    ] == "INVALID"

    reversed_attempts = [
        _route_attempt(
            roots,
            ticket_id=records[1]["ticket_id"],
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha=base_0,
            reviewed_head_sha="23" * 20,
            state="VERIFIED_MERGED",
            transition_sha=base_1,
        ),
        _route_attempt(
            roots,
            ticket_id=records[0]["ticket_id"],
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha=base_1,
            reviewed_head_sha="24" * 20,
            state="VERIFIED_MERGED",
            transition_sha=base_2,
        ),
    ]
    reversed_index = _route_attempt_index(
        tmp_path,
        manifest,
        reversed_attempts,
        initial_feature_sha=base_0,
        current_feature_sha=base_2,
    )
    assert validate_route_attempt_transition(manifest, reversed_index)[
        "status"
    ] == "INVALID"


def test_real_age255_refactoring_routes_integrate_serially_before_dependency_release(
    tmp_path: Path,
):
    manifest = _normalize_age255(tmp_path)
    rows = {row["ticket_id"]: row for row in manifest["records"]}
    roots = _attempt_roots(tmp_path)
    ticket_order = ["AGE-257", "AGE-256", "AGE-258"]
    feature_heads = ["30" * 20, "31" * 20, "32" * 20, "33" * 20]
    attempts: list[dict[str, Any]] = []
    for index, ticket_id in enumerate(ticket_order):
        assert rows[ticket_id]["owning_route"] == "refactoring"
        attempts.append(
            _route_attempt(
                roots,
                ticket_id=ticket_id,
                attempt_number=1,
                owning_route="refactoring",
                dispatch_base_sha=feature_heads[index],
                reviewed_head_sha=f"4{index}" * 20,
                state="VERIFIED_MERGED",
                transition_sha=feature_heads[index + 1],
                feature_branch=manifest["feature_branch"],
            )
        )
    final_sha = "34" * 20
    attempts.append(
        _route_attempt(
            roots,
            ticket_id="AGE-259",
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha=feature_heads[-1],
            reviewed_head_sha="44" * 20,
            state="VERIFIED_MERGED",
            transition_sha=final_sha,
            dependency_proofs=[
                _dependency_proof(ticket_id, 1, feature_heads[index + 1])
                for index, ticket_id in enumerate(ticket_order)
            ],
            feature_branch=manifest["feature_branch"],
        )
    )
    for attempt in attempts:
        proof = json.loads(Path(attempt["proof_envelope_path"]).read_text(encoding="utf-8"))
        assert proof["feature_branch"] == manifest["feature_branch"]
        route_result = json.loads(
            Path(proof["child_result"]["path"]).read_text(encoding="utf-8")
        )
        if attempt["owning_route"] == "implementation-pipeline":
            assert route_result["base_branch"] == manifest["feature_branch"]
            assert route_result["base_ref"] == (
                f"refs/remotes/origin/{manifest['feature_branch']}"
            )
        else:
            assert route_result["integration_branch_name"] == manifest["feature_branch"]
            child = route_result["child"]
            assert {
                child["dispatched_base_branch"],
                child["open_observed_base_ref_name"],
                child["pre_merge_observed_base_ref_name"],
                child["merged_observed_base_ref_name"],
            } == {manifest["feature_branch"]}
            nested = json.loads(
                Path(child["implementation_result_path"]).read_text(encoding="utf-8")
            )
            assert nested["base_branch"] == manifest["feature_branch"]
            assert nested["base_ref"] == (
                f"refs/remotes/origin/{manifest['feature_branch']}"
            )
    index = _route_attempt_index(
        tmp_path,
        manifest,
        attempts,
        initial_feature_sha=feature_heads[0],
        current_feature_sha=final_sha,
    )

    assert validate_route_attempt_transition(manifest, index)["status"] == "VALID"

    blocked = deepcopy(index)
    blocked["attempts"][-1]["dependency_proofs"][1][
        "reachable_from_dispatch_base"
    ] = False
    decision = validate_route_attempt_transition(manifest, blocked)
    assert decision["status"] == "INVALID"
    assert "attempts[3] dependency AGE-256 must be reachable" in decision["errors"]


def test_stale_route_attempt_replays_with_new_identity_and_selects_only_current_lineage(
    tmp_path: Path,
):
    manifest = _normalize_age255(tmp_path)
    manifest["records"] = [deepcopy(manifest["records"][0])]
    manifest["records"][0]["owning_route"] = "implementation-pipeline"
    ticket_id = manifest["records"][0]["ticket_id"]
    roots = _attempt_roots(tmp_path)
    base_0, external_base, merged = "50" * 20, "51" * 20, "52" * 20
    attempts = [
        _route_attempt(
            roots,
            ticket_id=ticket_id,
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha=base_0,
            reviewed_head_sha="61" * 20,
            state="STALE_CURRENTNESS",
            transition_sha=external_base,
        ),
        _route_attempt(
            roots,
            ticket_id=ticket_id,
            attempt_number=2,
            owning_route="implementation-pipeline",
            dispatch_base_sha=external_base,
            reviewed_head_sha="62" * 20,
            state="VERIFIED_MERGED",
            transition_sha=merged,
        ),
    ]
    index = _route_attempt_index(
        tmp_path,
        manifest,
        attempts,
        initial_feature_sha=base_0,
        current_feature_sha=merged,
    )

    decision = validate_route_attempt_transition(manifest, index)

    assert decision["status"] == "VALID"
    assert decision["accepted_attempts"] == {ticket_id: 2}
    assert attempts[0]["proof_envelope_path"] != attempts[1]["proof_envelope_path"]


def test_ready_failure_closes_direct_attempt_and_replays_without_merge(tmp_path: Path):
    manifest = _normalize_age255(tmp_path)
    manifest["records"] = [deepcopy(manifest["records"][-1])]
    manifest["records"][0]["depends_on"] = []
    ticket_id = manifest["records"][0]["ticket_id"]
    roots = _attempt_roots(tmp_path)
    feature_sha, merged_sha = "63" * 20, "64" * 20
    attempts = [
        _route_attempt(
            roots,
            ticket_id=ticket_id,
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha=feature_sha,
            reviewed_head_sha="65" * 20,
            state="REPLAY_REQUIRED",
            transition_sha=feature_sha,
        ),
        _route_attempt(
            roots,
            ticket_id=ticket_id,
            attempt_number=2,
            owning_route="implementation-pipeline",
            dispatch_base_sha=feature_sha,
            reviewed_head_sha="66" * 20,
            state="VERIFIED_MERGED",
            transition_sha=merged_sha,
        ),
    ]
    index = _route_attempt_index(
        tmp_path,
        manifest,
        attempts,
        initial_feature_sha=feature_sha,
        current_feature_sha=merged_sha,
    )

    decision = validate_route_attempt_transition(manifest, index)

    assert decision["status"] == "VALID"
    assert attempts[0]["merge_sha"] is None
    assert decision["accepted_attempts"] == {ticket_id: 2}


@pytest.mark.parametrize(
    "blocked_state",
    [
        "BLOCKED:ready-state-restoration-failed",
        "BLOCKED:merge-attempt-started",
    ],
)
def test_non_replayable_direct_attempt_blocks_later_attempts(
    tmp_path: Path, blocked_state: str
):
    manifest = _normalize_age255(tmp_path)
    manifest["records"] = [deepcopy(manifest["records"][-1])]
    manifest["records"][0]["depends_on"] = []
    ticket_id = manifest["records"][0]["ticket_id"]
    roots = _attempt_roots(tmp_path)
    feature_sha = "67" * 20
    blocked = _route_attempt(
        roots,
        ticket_id=ticket_id,
        attempt_number=1,
        owning_route="implementation-pipeline",
        dispatch_base_sha=feature_sha,
        reviewed_head_sha="68" * 20,
        state=blocked_state,
        transition_sha=feature_sha,
    )
    index = _route_attempt_index(
        tmp_path,
        manifest,
        [blocked],
        initial_feature_sha=feature_sha,
        current_feature_sha=feature_sha,
        complete=False,
    )

    assert validate_route_attempt_transition(manifest, index)["status"] == "VALID"

    later = _route_attempt(
        roots,
        ticket_id=ticket_id,
        attempt_number=2,
        owning_route="implementation-pipeline",
        dispatch_base_sha=feature_sha,
        reviewed_head_sha="69" * 20,
        state="REPLAY_REQUIRED",
        transition_sha=feature_sha,
    )
    index["attempts"].append(later)
    decision = validate_route_attempt_transition(manifest, index)
    assert decision["status"] == "INVALID"
    assert any("must not follow a non-replayable" in error for error in decision["errors"])


def test_route_attempt_validator_cli_writes_complete_accepted_lineage(tmp_path: Path):
    manifest = _normalize_age255(tmp_path)
    manifest["records"] = [deepcopy(manifest["records"][0])]
    ticket_id = manifest["records"][0]["ticket_id"]
    roots = _attempt_roots(tmp_path)
    attempt = _route_attempt(
        roots,
        ticket_id=ticket_id,
        attempt_number=1,
        owning_route="refactoring",
        dispatch_base_sha="80" * 20,
        reviewed_head_sha="81" * 20,
        state="VERIFIED_MERGED",
        transition_sha="82" * 20,
    )
    index = _route_attempt_index(
        tmp_path,
        manifest,
        [attempt],
        initial_feature_sha="80" * 20,
        current_feature_sha="82" * 20,
    )
    manifest_path = tmp_path / "route-manifest.json"
    index_path = tmp_path / "route-attempt-index.json"
    output_path = tmp_path / "route-attempt-validation.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    index_path.write_text(json.dumps(index), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-route-attempts",
            "--route-manifest",
            str(manifest_path),
            "--route-index",
            str(index_path),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output_path.read_text(encoding="utf-8"))[
        "accepted_attempts"
    ] == {ticket_id: 1}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda index: index["attempts"][1].update(attempt_number=1),
        lambda index: index["attempts"][1].update(
            proof_envelope_path=index["attempts"][0]["proof_envelope_path"]
        ),
        lambda index: index["accepted_attempts"][0].update(attempt_number=1),
    ],
    ids=["attempt-number-reuse", "path-reuse", "stale-attempt-selected"],
)
def test_route_attempt_identity_and_accepted_selection_fail_closed(
    tmp_path: Path, mutate
):
    manifest = _normalize_age255(tmp_path)
    manifest["records"] = [deepcopy(manifest["records"][0])]
    manifest["records"][0]["owning_route"] = "implementation-pipeline"
    ticket_id = manifest["records"][0]["ticket_id"]
    roots = _attempt_roots(tmp_path)
    attempts = [
        _route_attempt(
            roots,
            ticket_id=ticket_id,
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha="70" * 20,
            reviewed_head_sha="71" * 20,
            state="STALE_CURRENTNESS",
            transition_sha="72" * 20,
        ),
        _route_attempt(
            roots,
            ticket_id=ticket_id,
            attempt_number=2,
            owning_route="implementation-pipeline",
            dispatch_base_sha="72" * 20,
            reviewed_head_sha="73" * 20,
            state="VERIFIED_MERGED",
            transition_sha="74" * 20,
        ),
    ]
    index = _route_attempt_index(
        tmp_path,
        manifest,
        attempts,
        initial_feature_sha="70" * 20,
        current_feature_sha="74" * 20,
    )
    mutate(index)

    assert validate_route_attempt_transition(manifest, index)["status"] == "INVALID"


def test_real_age255_refactoring_route_passes_common_production_process_validator(
    tmp_path: Path,
):
    paths = _refactoring_route_process_fixture(
        tmp_path,
        ticket_id="AGE-257",
        attempt_number=1,
        reviewed=_provider_bundle(base_sha="90" * 20, head_sha="91" * 20),
        merge_sha="92" * 20,
        resulting_feature_sha="92" * 20,
    )

    decision = validate_route_process_proof(
        owning_route="refactoring",
        feature_branch="feature/hourly-suspicious-process-investigator",
        ticket_id="AGE-257",
        attempt_number=1,
        route_evidence_path=paths["route_evidence"],
        pre_audit_expected_path=paths["pre_audit_expected_process"],
        pre_audit_dispatch_path=paths["pre_audit_dispatch_snapshot"],
        pre_audit_trace_path=paths["pre_audit_trace"],
        process_report_path=paths["process_report"],
        process_report_binding_path=paths["process_report_binding"],
        final_expected_path=paths["final_expected_process"],
        final_dispatch_path=paths["final_dispatch_snapshot"],
        final_trace_path=paths["final_trace"],
    )

    assert decision["status"] == "PASS", decision["errors"]
    assert decision["expected_direct_operator"] == "refactoring-orchestrator"
    assert decision["child_result_schema"] == "refactoring-route-result-v1"
    assert {row["owner"] for row in decision["child_owned_process_proofs"]} == {
        "implementation-pipeline",
        "refactoring-orchestrator",
    }
    output_path = tmp_path / "route-process-validation.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-route-process-proof",
            "--owning-route",
            "refactoring",
            "--feature-branch",
            "feature/hourly-suspicious-process-investigator",
            "--ticket-id",
            "AGE-257",
            "--attempt-number",
            "1",
            "--route-evidence",
            str(paths["route_evidence"]),
            "--pre-audit-expected",
            str(paths["pre_audit_expected_process"]),
            "--pre-audit-dispatch",
            str(paths["pre_audit_dispatch_snapshot"]),
            "--pre-audit-trace",
            str(paths["pre_audit_trace"]),
            "--process-report",
            str(paths["process_report"]),
            "--process-report-binding",
            str(paths["process_report_binding"]),
            "--final-expected",
            str(paths["final_expected_process"]),
            "--final-dispatch",
            str(paths["final_dispatch_snapshot"]),
            "--final-trace",
            str(paths["final_trace"]),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(output_path.read_text(encoding="utf-8")) == decision


def test_route_process_binding_artifact_is_loaded_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = _route_lineage_fixture(tmp_path)
    binding_path = paths["process_report_binding"].resolve()
    original_load_json = _CONTRACT_MODULE._load_json
    binding_loads: list[Path] = []

    def tracking_load_json(path: Path) -> dict[str, Any]:
        if path.resolve() == binding_path:
            binding_loads.append(path.resolve())
        return original_load_json(path)

    monkeypatch.setattr(_CONTRACT_MODULE, "_load_json", tracking_load_json)
    decision = validate_route_process_proof(
        owning_route="implementation-pipeline",
        feature_branch="feature/hourly-suspicious-process-investigator",
        ticket_id="AGE-259",
        attempt_number=1,
        route_evidence_path=paths["route_evidence"],
        pre_audit_expected_path=paths["pre_audit_expected_process"],
        pre_audit_dispatch_path=paths["pre_audit_dispatch_snapshot"],
        pre_audit_trace_path=paths["pre_audit_trace"],
        process_report_path=paths["process_report"],
        process_report_binding_path=paths["process_report_binding"],
        final_expected_path=paths["final_expected_process"],
        final_dispatch_path=paths["final_dispatch_snapshot"],
        final_trace_path=paths["final_trace"],
    )

    assert decision["status"] == "PASS", decision["errors"]
    assert binding_loads == [binding_path]


@pytest.mark.parametrize("owning_route", ["implementation-pipeline", "refactoring"])
def test_common_route_process_rejects_wrong_base_name_at_same_oid(
    tmp_path: Path, owning_route: str
):
    expected_branch = "feature/hourly-suspicious-process-investigator"
    wrong_branch = "feature/same-oid-alias"
    shared_base_sha = "90" * 20
    reviewed = _provider_bundle(
        base_sha=shared_base_sha,
        head_sha="91" * 20,
        base_name=wrong_branch,
    )
    expected_base = _provider_bundle(
        base_sha=shared_base_sha,
        head_sha="91" * 20,
        base_name=expected_branch,
    )
    if owning_route == "implementation-pipeline":
        paths = _route_lineage_fixture(tmp_path, reviewed=reviewed)
    else:
        paths = _refactoring_route_process_fixture(
            tmp_path,
            ticket_id="AGE-257",
            attempt_number=1,
            reviewed=reviewed,
            merge_sha="92" * 20,
            resulting_feature_sha="92" * 20,
        )

    decision = validate_route_process_proof(
        owning_route=owning_route,
        feature_branch=expected_branch,
        ticket_id="AGE-259" if owning_route == "implementation-pipeline" else "AGE-257",
        attempt_number=1,
        route_evidence_path=paths["route_evidence"],
        pre_audit_expected_path=paths["pre_audit_expected_process"],
        pre_audit_dispatch_path=paths["pre_audit_dispatch_snapshot"],
        pre_audit_trace_path=paths["pre_audit_trace"],
        process_report_path=paths["process_report"],
        process_report_binding_path=paths["process_report_binding"],
        final_expected_path=paths["final_expected_process"],
        final_dispatch_path=paths["final_dispatch_snapshot"],
        final_trace_path=paths["final_trace"],
    )

    assert reviewed["base_ref_name"] != expected_base["base_ref_name"]
    assert reviewed["base_ref_oid"] == expected_base["base_ref_oid"] == shared_base_sha
    assert decision["status"] == "INVALID"
    assert any("feature_branch" in error for error in decision["errors"])


@pytest.mark.parametrize(
    ("fixture_overrides", "expected_error"),
    [
        (
            {"nested_base_name": "feature/same-oid-nested"},
            "refactoring implementation result base_branch mismatch",
        ),
        (
            {"observed_base_name": "feature/same-oid-provider"},
            "refactoring route child open_observed_base_ref_name must equal feature_branch",
        ),
    ],
    ids=["nested-implementation-base", "provider-base-name"],
)
def test_refactoring_route_rejects_nested_child_or_provider_base_name_mismatch(
    tmp_path: Path, fixture_overrides: dict[str, str], expected_error: str
):
    feature_branch = "feature/hourly-suspicious-process-investigator"
    shared_base_sha = "93" * 20
    paths = _refactoring_route_process_fixture(
        tmp_path,
        ticket_id="AGE-257",
        attempt_number=1,
        reviewed=_provider_bundle(
            base_sha=shared_base_sha,
            head_sha="94" * 20,
            base_name=feature_branch,
        ),
        merge_sha="95" * 20,
        resulting_feature_sha="95" * 20,
        **fixture_overrides,
    )

    decision = validate_route_process_proof(
        owning_route="refactoring",
        feature_branch=feature_branch,
        ticket_id="AGE-257",
        attempt_number=1,
        route_evidence_path=paths["route_evidence"],
        pre_audit_expected_path=paths["pre_audit_expected_process"],
        pre_audit_dispatch_path=paths["pre_audit_dispatch_snapshot"],
        pre_audit_trace_path=paths["pre_audit_trace"],
        process_report_path=paths["process_report"],
        process_report_binding_path=paths["process_report_binding"],
        final_expected_path=paths["final_expected_process"],
        final_dispatch_path=paths["final_dispatch_snapshot"],
        final_trace_path=paths["final_trace"],
    )

    assert decision["status"] == "INVALID"
    assert expected_error in decision["errors"]


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        (
            "same-oid-wrong-child-head-name",
            "refactoring route child declared_head_branch mismatch nested implementation reviewed identity",
        ),
        (
            "wrong-pr-url-number",
            "refactoring route child pr_url mismatch nested implementation reviewed identity",
        ),
        (
            "unrelated-merged-base",
            "refactoring route child merged_observed_base_sha must equal nested reviewed base",
        ),
        (
            "wrong-expected-head-guard",
            "refactoring route child expected_head_guard_sha must equal nested reviewed head",
        ),
    ],
)
def test_refactoring_route_rejects_wrong_nested_pr_head_or_merged_base_identity(
    tmp_path: Path, case: str, expected_error: str
):
    paths = _refactoring_route_process_fixture(
        tmp_path,
        ticket_id="AGE-257",
        attempt_number=1,
        reviewed=_provider_bundle(base_sha="a1" * 20, head_sha="a2" * 20),
        merge_sha="a3" * 20,
        resulting_feature_sha="a3" * 20,
    )

    def mutate(route_output: dict[str, Any]) -> None:
        child = route_output["child"]
        if case == "same-oid-wrong-child-head-name":
            for field in (
                "declared_head_branch",
                "open_observed_head_ref_name",
                "pre_merge_observed_head_ref_name",
                "merged_observed_head_ref_name",
            ):
                child[field] = "route/same-oid-wrong-head"
        elif case == "wrong-pr-url-number":
            child["pr_url"] = "https://github.com/other/repo/pull/999"
            child["pr_number"] = 999
        elif case == "unrelated-merged-base":
            child["merged_observed_base_sha"] = "a4" * 20
        else:
            child["expected_head_guard_sha"] = "a4" * 20

    _mutate_json(paths["route_output"], mutate)

    decision = _validate_refactoring_process_fixture(paths)

    assert decision["status"] == "INVALID"
    assert any(expected_error in error for error in decision["errors"])


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        (
            "report-collection-wrong-type",
            "refactoring route child pre_merge_auditor_reports must be an array",
        ),
        (
            "missing-required-role",
            "refactoring auditor index pre_merge_reports must contain exactly 5 reports",
        ),
        (
            "duplicate-required-role",
            "refactoring auditor index pre_merge_reports must contain the exact canonical auditor role order",
        ),
        (
            "unknown-report-key",
            "refactoring auditor index pre_merge_reports[0] fields are invalid",
        ),
        (
            "missing-report-key",
            "refactoring auditor index pre_merge_reports[0] fields are invalid",
        ),
        (
            "unknown-index-key",
            "refactoring auditor index fields must exactly equal:",
        ),
        (
            "stale-report-hash",
            "refactoring auditor index pre_merge_reports[0] report hash mismatch",
        ),
        (
            "report-index-mismatch",
            "refactoring route child pre_merge_reports must equal auditor index",
        ),
        (
            "non-low-report",
            "refactoring auditor index pre_merge_reports[0] report must contain exactly one canonical Verdict: LOW line",
        ),
        (
            "validation-non-low-report",
            "refactoring auditor index pre_merge_reports[4] report must end with exactly one canonical validation-integrity LOW token",
        ),
        (
            "validation-mixed-verdict-report",
            "refactoring auditor index pre_merge_reports[4] report must end with exactly one canonical validation-integrity LOW token",
        ),
        (
            "wrong-pre-merge-head",
            "refactoring route child pre_merge_auditor_current_head must equal nested reviewed head",
        ),
        (
            "wrong-post-merge-head",
            "refactoring route child post_merge_auditor_current_head must equal final integration SHA",
        ),
    ],
)
def test_refactoring_route_rejects_unclosed_or_stale_auditor_evidence(
    tmp_path: Path, case: str, expected_error: str
):
    paths = _refactoring_route_process_fixture(
        tmp_path,
        ticket_id="AGE-257",
        attempt_number=1,
        reviewed=_provider_bundle(base_sha="b1" * 20, head_sha="b2" * 20),
        merge_sha="b3" * 20,
        resulting_feature_sha="b3" * 20,
    )
    route_output = json.loads(paths["route_output"].read_text(encoding="utf-8"))
    child = route_output["child"]
    auditor_index_path = Path(route_output["auditor_index_path"])
    auditor_index = json.loads(auditor_index_path.read_text(encoding="utf-8"))

    if case == "report-collection-wrong-type":
        child["pre_merge_auditor_reports"] = "not-a-report-list"
    elif case == "missing-required-role":
        auditor_index["pre_merge_reports"].pop()
        child["pre_merge_auditor_reports"] = deepcopy(
            auditor_index["pre_merge_reports"]
        )
    elif case == "duplicate-required-role":
        auditor_index["pre_merge_reports"][1]["role"] = auditor_index[
            "pre_merge_reports"
        ][0]["role"]
        child["pre_merge_auditor_reports"] = deepcopy(
            auditor_index["pre_merge_reports"]
        )
    elif case == "unknown-report-key":
        auditor_index["pre_merge_reports"][0]["unexpected"] = True
        child["pre_merge_auditor_reports"] = deepcopy(
            auditor_index["pre_merge_reports"]
        )
    elif case == "missing-report-key":
        auditor_index["pre_merge_reports"][0].pop("round")
        child["pre_merge_auditor_reports"] = deepcopy(
            auditor_index["pre_merge_reports"]
        )
    elif case == "unknown-index-key":
        auditor_index["unexpected"] = True
    elif case == "stale-report-hash":
        report_path = Path(auditor_index["pre_merge_reports"][0]["report_path"])
        report_path.write_text("# Stale report\n\nVerdict: LOW\n", encoding="utf-8")
    elif case == "report-index-mismatch":
        child["pre_merge_auditor_reports"][0]["round"] = 2
    elif case == "non-low-report":
        report = auditor_index["pre_merge_reports"][0]
        report_path = Path(report["report_path"])
        report_path.write_text("# Current report\n\nVerdict: HIGH\n", encoding="utf-8")
        report["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
        child["pre_merge_auditor_reports"] = deepcopy(
            auditor_index["pre_merge_reports"]
        )
    elif case == "validation-non-low-report":
        report = auditor_index["pre_merge_reports"][4]
        report_path = Path(report["report_path"])
        report_path.write_text("# Validation integrity\n\nHIGH\n", encoding="utf-8")
        report["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
        child["pre_merge_auditor_reports"] = deepcopy(
            auditor_index["pre_merge_reports"]
        )
    elif case == "validation-mixed-verdict-report":
        report = auditor_index["pre_merge_reports"][4]
        report_path = Path(report["report_path"])
        report_path.write_text(
            "# Validation integrity\n\nVerdict: HIGH\nLOW\n", encoding="utf-8"
        )
        report["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
        child["pre_merge_auditor_reports"] = deepcopy(
            auditor_index["pre_merge_reports"]
        )
    elif case == "wrong-pre-merge-head":
        wrong_head = "b4" * 20
        child["pre_merge_auditor_current_head"] = wrong_head
        auditor_index["pre_merge_current_head"] = wrong_head
        for report in auditor_index["pre_merge_reports"]:
            report["current_head_sha"] = wrong_head
        child["pre_merge_auditor_reports"] = deepcopy(
            auditor_index["pre_merge_reports"]
        )
    else:
        wrong_head = "b4" * 20
        child["post_merge_auditor_current_head"] = wrong_head
        auditor_index["post_merge_current_head"] = wrong_head
        for report in auditor_index["post_merge_reports"]:
            report["current_head_sha"] = wrong_head
        child["post_merge_auditor_reports"] = deepcopy(
            auditor_index["post_merge_reports"]
        )

    if case not in {"report-collection-wrong-type", "report-index-mismatch", "stale-report-hash"}:
        _write_json_fixture(auditor_index_path, auditor_index)
        route_output["auditor_index_sha256"] = hashlib.sha256(
            auditor_index_path.read_bytes()
        ).hexdigest()
    _write_json_fixture(paths["route_output"], route_output)

    decision = _validate_refactoring_process_fixture(paths)

    assert decision["status"] == "INVALID"
    assert any(expected_error in error for error in decision["errors"])


def test_refactoring_route_accepts_trailing_blank_after_validation_verdict(
    tmp_path: Path,
):
    report_path = tmp_path / "validation-integrity.md"
    report_path.write_text("# Validation integrity\n\nLOW\n\n", encoding="utf-8")
    errors: list[str] = []

    _CONTRACT_MODULE._validate_refactoring_auditor_report_verdict(
        report_path,
        role="validation-integrity-auditor",
        label="validation report",
        errors=errors,
    )

    assert errors == []


def test_route_attempt_rejects_proof_envelope_feature_branch_mismatch(
    tmp_path: Path,
):
    manifest = _normalize_age255(tmp_path)
    manifest["records"] = [deepcopy(manifest["records"][0])]
    attempt = _route_attempt(
        _attempt_roots(tmp_path),
        ticket_id=manifest["records"][0]["ticket_id"],
        attempt_number=1,
        owning_route="refactoring",
        dispatch_base_sha="96" * 20,
        reviewed_head_sha="97" * 20,
        state="VERIFIED_MERGED",
        transition_sha="98" * 20,
        feature_branch="feature/same-oid-alias",
    )
    index = _route_attempt_index(
        tmp_path,
        manifest,
        [attempt],
        initial_feature_sha="96" * 20,
        current_feature_sha="98" * 20,
    )

    decision = validate_route_attempt_transition(manifest, index)

    assert decision["status"] == "INVALID"
    assert "attempts[0] route attempt proof feature_branch mismatch" in decision["errors"]


def test_route_attempt_rejects_route_result_feature_branch_mismatch(
    tmp_path: Path,
):
    manifest = _normalize_age255(tmp_path)
    manifest["records"] = [deepcopy(manifest["records"][0])]
    attempt = _route_attempt(
        _attempt_roots(tmp_path),
        ticket_id=manifest["records"][0]["ticket_id"],
        attempt_number=1,
        owning_route="refactoring",
        dispatch_base_sha="99" * 20,
        reviewed_head_sha="9a" * 20,
        state="VERIFIED_MERGED",
        transition_sha="9b" * 20,
        feature_branch="feature/same-oid-alias",
    )
    proof_path = Path(attempt["proof_envelope_path"])
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    proof["feature_branch"] = manifest["feature_branch"]
    _write_json_fixture(proof_path, proof)
    attempt["proof_envelope_sha256"] = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    index = _route_attempt_index(
        tmp_path,
        manifest,
        [attempt],
        initial_feature_sha="99" * 20,
        current_feature_sha="9b" * 20,
    )

    decision = validate_route_attempt_transition(manifest, index)

    assert decision["status"] == "INVALID"
    assert any("integration branch must equal feature_branch" in error for error in decision["errors"])


@pytest.mark.parametrize(
    "case",
    [
        "wrong-route",
        "wrong-operator",
        "wrong-result-schema",
        "empty-process",
        "invalid-child-owned-proof",
        "undeclared-direct-sibling",
    ],
)
def test_common_refactoring_route_process_proof_rejects_invalid_evidence(
    tmp_path: Path, case: str
):
    paths = _refactoring_route_process_fixture(
        tmp_path,
        ticket_id="AGE-257",
        attempt_number=1,
        reviewed=_provider_bundle(base_sha="93" * 20, head_sha="94" * 20),
        merge_sha="95" * 20,
        resulting_feature_sha="95" * 20,
    )
    owning_route = "refactoring"
    if case == "wrong-route":
        owning_route = "implementation-pipeline"
    elif case == "wrong-operator":
        _mutate_json(
            paths["pre_audit_expected_process"],
            lambda value: value["nodes"][0].update(
                operator_or_role="implementation-pipeline-orchestrator"
            ),
        )
    elif case == "wrong-result-schema":
        _mutate_json(
            paths["route_output"],
            lambda value: value.update(schema="implementation-pipeline-result-v1"),
        )
    elif case == "empty-process":
        _mutate_json(
            paths["pre_audit_trace"],
            lambda value: value["root"].update(children=[]),
        )
    elif case == "invalid-child-owned-proof":
        route_output = json.loads(paths["route_output"].read_text(encoding="utf-8"))
        Path(route_output["owned_process_proofs"][0]["expected_process_path"]).write_text(
            "stale\n", encoding="utf-8"
        )
    else:
        def add_sibling(value: dict[str, Any]) -> None:
            sibling = deepcopy(value["root"]["children"][1])
            sibling["invocation"]["id"] = "24000000-0000-4000-8000-000000000001"
            sibling["invocation"]["agent_runner_invocation_id"] = sibling["invocation"]["id"]
            value["root"]["children"].append(sibling)

        _mutate_json(paths["final_trace"], add_sibling)

    decision = validate_route_process_proof(
        owning_route=owning_route,
        feature_branch="feature/hourly-suspicious-process-investigator",
        ticket_id="AGE-257",
        attempt_number=1,
        route_evidence_path=paths["route_evidence"],
        pre_audit_expected_path=paths["pre_audit_expected_process"],
        pre_audit_dispatch_path=paths["pre_audit_dispatch_snapshot"],
        pre_audit_trace_path=paths["pre_audit_trace"],
        process_report_path=paths["process_report"],
        process_report_binding_path=paths["process_report_binding"],
        final_expected_path=paths["final_expected_process"],
        final_dispatch_path=paths["final_dispatch_snapshot"],
        final_trace_path=paths["final_trace"],
    )

    assert decision["status"] == "INVALID"
    assert decision["errors"]


@pytest.mark.parametrize(
    "case",
    ["absent-artifact", "hash-mismatch", "nonexistent-path", "literal-only-common-pass"],
)
def test_route_attempt_transition_rejects_untruthful_proof_envelopes(
    tmp_path: Path, case: str
):
    manifest = _normalize_age255(tmp_path)
    manifest["records"] = [deepcopy(manifest["records"][0])]
    roots = _attempt_roots(tmp_path)
    attempt = _route_attempt(
        roots,
        ticket_id="AGE-257",
        attempt_number=1,
        owning_route="refactoring",
        dispatch_base_sha="96" * 20,
        reviewed_head_sha="97" * 20,
        state="VERIFIED_MERGED",
        transition_sha="98" * 20,
    )
    proof_path = Path(attempt["proof_envelope_path"])
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    if case == "absent-artifact":
        Path(proof["process_report_binding"]["path"]).unlink()
    elif case == "hash-mismatch":
        Path(proof["route_log"]["path"]).write_bytes(b"stale\n")
    elif case == "nonexistent-path":
        proof["child_result"] = {
            "path": str(tmp_path / "does-not-exist.json"),
            "sha256": "0" * 64,
        }
        _write_json_fixture(proof_path, proof)
        attempt["proof_envelope_sha256"] = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    else:
        common_path = Path(proof["common_validation_result"]["path"])
        _write_json_fixture(
            common_path,
            {"schema": "feature-route-process-proof-validation-v1", "status": "PASS"},
        )
        proof["common_validation_result"]["sha256"] = hashlib.sha256(
            common_path.read_bytes()
        ).hexdigest()
        _write_json_fixture(proof_path, proof)
        attempt["proof_envelope_sha256"] = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    index = _route_attempt_index(
        tmp_path,
        manifest,
        [attempt],
        initial_feature_sha="96" * 20,
        current_feature_sha="98" * 20,
    )

    decision = validate_route_attempt_transition(manifest, index)

    assert decision["status"] == "INVALID"
    assert decision["errors"]


def test_age259_dependency_release_rejects_refactoring_row_without_common_proof(
    tmp_path: Path,
):
    manifest = _normalize_age255(tmp_path)
    refactoring = deepcopy(manifest["records"][0])
    dependent = deepcopy(manifest["records"][-1])
    dependent["depends_on"] = [refactoring["ticket_id"]]
    manifest["records"] = [refactoring, dependent]
    roots = _attempt_roots(tmp_path)
    ref_merge = "a1" * 20
    final_merge = "a2" * 20
    attempts = [
        _route_attempt(
            roots,
            ticket_id=refactoring["ticket_id"],
            attempt_number=1,
            owning_route="refactoring",
            dispatch_base_sha="a0" * 20,
            reviewed_head_sha="b1" * 20,
            state="VERIFIED_MERGED",
            transition_sha=ref_merge,
        ),
        _route_attempt(
            roots,
            ticket_id=dependent["ticket_id"],
            attempt_number=1,
            owning_route="implementation-pipeline",
            dispatch_base_sha=ref_merge,
            reviewed_head_sha="b2" * 20,
            state="VERIFIED_MERGED",
            transition_sha=final_merge,
            dependency_proofs=[
                _dependency_proof(refactoring["ticket_id"], 1, ref_merge)
            ],
        ),
    ]
    proof_path = Path(attempts[0]["proof_envelope_path"])
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    proof["common_validation_result"] = {
        "path": str(tmp_path / "missing-common-validation.json"),
        "sha256": "0" * 64,
    }
    _write_json_fixture(proof_path, proof)
    attempts[0]["proof_envelope_sha256"] = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    index = _route_attempt_index(
        tmp_path,
        manifest,
        attempts,
        initial_feature_sha="a0" * 20,
        current_feature_sha=final_merge,
    )

    decision = validate_route_attempt_transition(manifest, index)

    assert decision["status"] == "INVALID"
    assert any("common" in error for error in decision["errors"])


def test_refactoring_adapter_and_merge_owner_are_complete():
    feature_route = _section("agents/feature-orchestrator.md", "#### Refactoring route")
    for value in (
        "same-named sole existing-issue ticket-source field",
        "matching backend configuration",
        "target_list",
        "slice_bounds",
        "integration_branch_ref=${feature_branch}",
        "already-normalized `branch_name`",
        "Do not put a child invocation UUID in the prompt",
        "base_branch=${feature_branch}",
        "auto_merge_after_phase_9=false",
        "sole owner of that child PR merge",
        "state=VERIFIED_MERGED",
        "singular complete `child`",
        "exactly one ticket PR",
        "distinct immutable pre-merge process evidence",
        "full post-merge auditor/process PASS evidence with artifact hashes",
        "must not open, merge, or re-merge",
    ):
        assert value in feature_route

    ticket_map = _fenced_yaml_section(
        "agents/feature-orchestrator.md", "#### Refactoring route"
    )
    assert ticket_map == {
        "ticket_source_to_refactoring_input": {
            "jira_issue_key": "jira_issue_key",
            "linear_issue_key": "linear_issue_key",
        },
        "cardinality": "exactly-one",
    }
    assert "cannot enter Phase 0 ticket creation" in feature_route

    refactor_contract = _operator_contract("refactoring-orchestrator")
    refactor_inputs = {item["name"] for item in refactor_contract["inputs"]}
    assert refactor_inputs == REFACTOR_INPUT_NAMES
    assert _input(refactor_contract, "ticket_system")["required"] is True
    assert _input(refactor_contract, "branch_name")["required"] is True
    assert "non-protected short branch" in _input(
        refactor_contract, "branch_name"
    )["description"]
    assert "root_invocation_uuid" not in refactor_inputs
    output = refactor_contract["outputs"][0]
    assert set(output["wrote_lines"]) == REFACTOR_ARTIFACTS
    assert "VERIFIED_MERGED" in output["success_shape"]

    refactor_procedure = _section("agents/refactoring-orchestrator.md", "## Procedure")
    assert "base_branch=${integration_branch_ref}" in refactor_procedure
    assert "auto_merge_after_phase_9=false" in refactor_procedure
    assert "sole merge owner" in refactor_procedure
    assert "ticket-scoped pre-merge evidence to be PASS" in refactor_procedure
    assert "prove ancestry" in refactor_procedure
    canonical = _section("agents/refactoring-orchestrator.md", "## Canonical Invocation")
    assert "OULIPOLY_PARENT_INVOCATION" in canonical
    assert "Never accept a caller-selected substitute" in canonical


def test_refactoring_optional_inputs_and_defaults_have_full_contract_parity():
    contract = _operator_contract("refactoring-orchestrator")
    defaults = {item["name"]: item for item in contract["defaults"]}
    assert defaults == {
        "shim_registry_path": {
            "name": "shim_registry_path",
            "value": "~/ai/conventions/active-shims.md",
            "source": "base",
        },
        "audit_history_path": {
            "name": "audit_history_path",
            "value": "${planning_dir}/refactoring-audit-history.md",
            "source": "base",
        },
    }
    optional = _section("agents/refactoring-orchestrator.md", "## Optional Inputs")
    for name in (
        "shim_placement_parameters",
        "prior_refactor_evidence_pointers",
        "shim_registry_path",
        "audit_history_path",
    ):
        assert f"`{name}`" in optional
        assert _input(contract, name)["required"] is False


def test_refactoring_child_invocation_contract_is_complete_and_fixed():
    child = _fenced_yaml_section(
        "agents/refactoring-orchestrator.md",
        "## Implementation Child Invocation Contract",
    )
    assert child == {
        "schema": "refactoring-child-dispatch-v1",
        "cardinality": "exactly-one",
        "ticket_pr_cardinality": "exactly-one",
        "ticket_source": {
            "accepted_fields": [
                "jira_issue_key",
                "linear_issue_key",
                "wu_brief_path",
            ],
            "cardinality": "exactly-one",
            "mapping": "same-name-pass-through",
        },
        "ticket_context": {
            "field": "wu_brief_context_path",
            "mapping": "same-name-pass-through",
            "requires_existing_issue_key": True,
            "authorizes_ticket_creation": False,
        },
        "backend": {
            "selector": "ticket_system",
            "jira_fields": ["jira_url", "jira_project", "jira_account_email"],
            "linear_fields": ["linear_team_key", "linear_project_id"],
        },
        "required_common_fields": [
            "repo_root",
            "worktree_path",
            "scratch_dir",
            "planning_dir",
            "branch_name",
            "base_branch",
            "auto_merge_after_phase_9",
        ],
        "conditional_common_fields": {
            "local_coverage_command": {
                "required_when": "feature-routed",
                "mapping": "same-name-byte-for-byte",
            }
        },
        "fixed_values": {
            "branch_name": "${branch_name}",
            "worktree_path": "${worktree_path}",
            "scratch_dir": "${scratch_dir}",
            "planning_dir": "${planning_dir}",
            "base_branch": "${integration_branch_ref}",
            "auto_merge_after_phase_9": False,
        },
    }
    body = _section(
        "agents/refactoring-orchestrator.md",
        "## Implementation Child Invocation Contract",
    )
    assert "fully composed prompt and its resolved input row before dispatch" in body


def test_refactoring_dispatch_validator_enforces_one_child_and_exact_branch_projection():
    valid = _refactoring_dispatch_plan()
    valid_decision = validate_refactoring_dispatch(valid)
    assert valid_decision["status"] == "VALID"
    assert valid_decision["local_coverage_command_sha256"] == (
        _LOCAL_COVERAGE_COMMAND_SHA256
    )

    second_child = deepcopy(valid["children"][0])
    second_child["branch_name"] = "route/age-261"
    multiple = deepcopy(valid)
    multiple["children"].append(second_child)
    decision = validate_refactoring_dispatch(multiple)
    assert decision["status"] == "INVALID"
    assert "children must contain exactly one implementation child" in decision["errors"]

    mismatched = _refactoring_dispatch_plan()
    mismatched["children"][0]["branch_name"] = "route/other"
    decision = validate_refactoring_dispatch(mismatched)
    assert decision["status"] == "INVALID"
    assert "child branch_name must equal the route projection" in decision["errors"]

    protected = _refactoring_dispatch_plan(branch_name="feature/integration")
    decision = validate_refactoring_dispatch(protected)
    assert decision["status"] == "INVALID"
    assert "branch_name must not be protected" in decision["errors"]

    changed_command = _refactoring_dispatch_plan()
    changed_command["children"][0]["local_coverage_command"] += " --changed"
    decision = validate_refactoring_dispatch(changed_command)
    assert decision["status"] == "INVALID"
    assert (
        "child local_coverage_command must equal the route projection"
        in decision["errors"]
    )

    missing_command = _refactoring_dispatch_plan()
    missing_command.pop("local_coverage_command")
    missing_command["children"][0].pop("local_coverage_command")
    decision = validate_refactoring_dispatch(missing_command)
    assert decision["status"] == "INVALID"
    assert (
        "feature-routed dispatch plan must supply local_coverage_command"
        in decision["errors"]
    )

    direct_without_command = deepcopy(missing_command)
    direct_without_command["feature_routed"] = False
    assert validate_refactoring_dispatch(direct_without_command)["status"] == "VALID"

    invalid_route_origin = _refactoring_dispatch_plan(feature_routed="true")
    decision = validate_refactoring_dispatch(invalid_route_origin)
    assert decision["status"] == "INVALID"
    assert "feature_routed must be a boolean" in decision["errors"]

    blank_command = _refactoring_dispatch_plan(local_coverage_command=" \t ")
    blank_command["children"][0]["local_coverage_command"] = " \t "
    decision = validate_refactoring_dispatch(blank_command)
    assert decision["status"] == "INVALID"
    assert "local_coverage_command must be a non-blank string" in decision["errors"]


@pytest.mark.parametrize(
    "protected_branches",
    [
        ["refs/heads/main", "feature/integration"],
        ["origin/main", "feature/integration"],
        ["main", "main", "feature/integration"],
    ],
    ids=["full-ref", "remote-tracking", "duplicate"],
)
def test_refactoring_dispatch_rejects_invalid_protected_entries_before_membership(
    protected_branches: list[str],
):
    plan = _refactoring_dispatch_plan(
        branch_name="main", protected_branches=protected_branches
    )

    decision = validate_refactoring_dispatch(plan)

    assert decision["status"] == "INVALID"
    assert any("protected_branches" in error for error in decision["errors"])


@pytest.mark.parametrize("path_case", ["dotdot", "same-root", "symlink"])
def test_refactoring_dispatch_rejects_noncanonical_and_cross_root_aliases(
    tmp_path: Path, path_case: str
):
    worktree = tmp_path / "worktree"
    planning = tmp_path / "planning"
    scratch = tmp_path / "scratch"
    if path_case == "dotdot":
        planning = Path(f"{tmp_path}/planning/x/..")
    elif path_case == "same-root":
        planning = worktree
    else:
        real = tmp_path / "real-worktree"
        real.mkdir()
        alias = tmp_path / "worktree-alias"
        alias.symlink_to(real, target_is_directory=True)
        worktree = alias
    plan = _refactoring_dispatch_plan(
        worktree_path=str(worktree),
        planning_dir=str(planning),
        scratch_dir=str(scratch),
    )
    plan["children"] = [
        {
            "branch_name": plan["branch_name"],
            "worktree_path": plan["worktree_path"],
            "planning_dir": plan["planning_dir"],
            "scratch_dir": plan["scratch_dir"],
            "ticket_pr_cardinality": "exactly-one",
        }
    ]

    assert validate_refactoring_dispatch(plan)["status"] == "INVALID"


def test_commit_history_has_strict_scope_and_execute_contracts():
    contract = _operator_contract("refactoring-commit-history-orchestrator")
    assert _input(contract, "mode")["required"] is True
    assert "scope or execute" in _input(contract, "mode")["description"]
    assert _input(contract, "trunk_branch")["required"] is True
    assert _input(contract, "protected_branches")["required"] is True
    assert "scope and execute" in _input(contract, "protected_branches")["description"]
    request = _input(contract, "package_source_request")
    source_map = _input(contract, "package_ticket_source_map")
    current_identity = _input(contract, "current_identity_path")
    assert request["required"] is False
    assert source_map["required"] is False
    assert current_identity["required"] is False
    assert source_map["type"] == "path"
    assert "plan_hash" in source_map["description"]

    request_schema = _fenced_yaml_section(
        "agents/refactoring-commit-history-orchestrator.md",
        "## Package Source Request Schema",
    )
    assert request_schema["schema"] == (
        "refactoring-commit-history-package-source-request-v1"
    )
    assert "plan_hash" in request_schema["required_top_level_fields"]
    assert "trunk_branch" in request_schema["required_top_level_fields"]
    assert "protected_branches" in request_schema["required_top_level_fields"]
    assert request_schema["scope_stop"] == "PACKAGE_SOURCE_REQUEST_READY"
    assert request_schema["plan_hash"]["excludes"] == ["plan_hash"]
    assert request_schema["package_additional_properties"] is False
    assert set(request_schema["package_required_fields"]) == set(
        request_schema["package_field_contracts"]
    )
    assert set(request_schema["inherited_gate_obligations"]["required"]) == {
        "implementation-pipeline-phase-4",
        "implementation-pipeline-phase-6",
        "implementation-pipeline-phase-7",
        "implementation-pipeline-phase-8",
    }
    assert request_schema["dependency_graph"] == "package-local-and-acyclic"
    assert request_schema["protected_branches"]["required_members"] == [
        "trunk_branch",
        "integration_branch_ref",
    ]

    assignment = _fenced_yaml_section(
        "agents/refactoring-commit-history-orchestrator.md",
        "## Execute Assignment Schema",
    )
    source_schema = assignment
    assert source_schema["schema"] == (
        "refactoring-commit-history-package-ticket-source-v1"
    )
    assert source_schema["failure"] == (
        "BLOCKED:invalid-package-ticket-source-map-before-dispatch"
    )
    assert "exact plan_hash equality with package_source_request" in source_schema[
        "rules"
    ]
    assert "no wu_brief_path ticket source" in source_schema["rules"]

    procedure = _section(
        "agents/refactoring-commit-history-orchestrator.md", "## Procedure"
    )
    scope = procedure.index("### Scope mode")
    scope_stop = procedure.index("PACKAGE_SOURCE_REQUEST_READY", scope)
    execute = procedure.index("### Execute mode")
    validate = procedure.index("validate-package-execute", execute)
    dispatch = procedure.index("dispatch `agents/refactoring-orchestrator.md`", execute)
    assert scope < scope_stop < execute
    assert validate < dispatch
    for value in (
        "Traverse the immutable acyclic dependency graph in topological order",
        "every package ID in its `dependencies` has produced a complete hashed `VERIFIED_MERGED` outcome",
        "blocks all of its transitive dependents from dispatch",
        "existing `jira_issue_key` or `linear_issue_key` as the sole ticket source",
        "`wu_brief_context_path` under that exact context-only name",
        "implementation Phase 0 reads the issue and cannot cold-create",
        "performs no ticket operation",
    ):
        assert value in procedure


def test_commit_history_execute_rejects_plan_hash_and_package_set_mismatch():
    request = _package_source_request()
    current = _current_package_identity(request)
    accepted = validate_package_execution(request, _package_ticket_map(request), current)
    assert accepted["status"] == "VALID"
    assert accepted["identity_equal"] is True
    assert accepted["package_set_equal"] is True

    tampered_request = deepcopy(request)
    tampered_request["package_plan"][0]["target_list"] = ["changed-after-scope"]
    decision = validate_package_execution(
        tampered_request, _package_ticket_map(request), current
    )
    assert decision["status"] == "INVALID"
    assert "request plan_hash does not match canonical request content" in decision[
        "errors"
    ]

    stale_hash_map = _package_ticket_map(request)
    stale_hash_map["plan_hash"] = "f" * 64
    decision = validate_package_execution(request, stale_hash_map, current)
    assert decision["status"] == "INVALID"
    assert "ticket source map plan_hash must equal request plan_hash" in decision["errors"]

    incomplete_map = _package_ticket_map(request)
    incomplete_map["packages"].pop()
    decision = validate_package_execution(request, incomplete_map, current)
    assert decision["status"] == "INVALID"
    assert decision["package_set_equal"] is False
    assert (
        "ticket source map package set must exactly equal selected package set"
        in decision["errors"]
    )

    moved_identity = _current_package_identity(request)
    moved_identity["integration_branch_sha"] = "9" * 40
    decision = validate_package_execution(
        request, _package_ticket_map(request), moved_identity
    )
    assert decision["status"] == "INVALID"
    assert "current identity mismatch: integration_branch_sha" in decision["errors"]


@pytest.mark.parametrize(
    ("trunk_branch", "package_branch"),
    [
        ("main", "main"),
        ("release/trunk", "release/trunk"),
        ("main", "refactor/integration"),
    ],
    ids=["main", "explicit-non-main-trunk", "integration"],
)
def test_commit_history_execute_rejects_every_protected_package_branch(
    trunk_branch: str, package_branch: str
):
    request = _package_source_request()
    request["trunk_branch"] = trunk_branch
    request["protected_branches"] = [trunk_branch, request["integration_branch_ref"]]
    request["package_plan"][0]["branch_name"] = package_branch
    request["plan_hash"] = compute_plan_hash(request)

    decision = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )

    assert decision["status"] == "INVALID"
    assert "package_plan[0].branch_name must not be protected" in decision["errors"]


@pytest.mark.parametrize(
    "protected_branches",
    [
        ["refs/heads/main", "refactor/integration"],
        ["origin/main", "refactor/integration"],
        ["bad branch", "refactor/integration"],
        ["main", "main", "refactor/integration"],
    ],
    ids=["full-ref", "remote-ref", "malformed", "duplicate"],
)
def test_commit_history_execute_rejects_invalid_protected_branch_sets(
    protected_branches: list[str],
):
    request = _package_source_request()
    request["protected_branches"] = protected_branches
    request["plan_hash"] = compute_plan_hash(request)

    decision = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )

    assert decision["status"] == "INVALID"
    assert any("protected_branches" in error for error in decision["errors"])


def test_commit_history_execute_rejects_protected_set_drift_after_scope():
    request = _package_source_request()
    current = _current_package_identity(request)
    current["protected_branches"] = [
        "main",
        "refactor/integration",
        "release/protected",
    ]

    decision = validate_package_execution(
        request, _package_ticket_map(request), current
    )

    assert decision["status"] == "INVALID"
    assert "current identity mismatch: protected_branches" in decision["errors"]


def test_commit_history_transports_exact_protected_set_to_refactoring_dispatch():
    request = _package_source_request()
    package = request["package_plan"][0]
    plan = _refactoring_dispatch_plan(
        feature_routed=False,
        branch_name=package["branch_name"],
        trunk_branch_name=request["trunk_branch"],
        integration_branch_name=request["integration_branch_ref"],
        protected_branches=request["protected_branches"],
        worktree_path=package["worktree_path"],
        planning_dir=package["planning_dir"],
        scratch_dir=package["scratch_dir"],
    )

    decision = validate_refactoring_dispatch(plan)

    assert decision["status"] == "VALID", decision["errors"]


@pytest.mark.parametrize(
    "missing_field",
    [
        "package_id",
        "target_list",
        "slice_bounds",
        "refactor_intent",
        "milestone_evidence_ref",
        "degradation_evidence_ref",
        "inherited_gate_obligations",
        "dependencies",
        "acceptance_criteria",
        "branch_name",
        "worktree_path",
        "planning_dir",
        "scratch_dir",
        "route_result_path",
    ],
)
def test_commit_history_package_descriptor_rejects_every_omitted_field(
    missing_field: str,
):
    request = _package_source_request()
    request["package_plan"][0].pop(missing_field)
    request["plan_hash"] = compute_plan_hash(request)

    decision = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )

    assert decision["status"] == "INVALID"
    assert any("fields must exactly equal" in error for error in decision["errors"])


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("package_id", " "),
        ("target_list", []),
        ("slice_bounds", {}),
        ("refactor_intent", "ship-behavior"),
        ("milestone_evidence_ref", "relative/milestone.json"),
        ("degradation_evidence_ref", "/tmp/evidence/x/../degradation.json"),
        ("inherited_gate_obligations", ["implementation-pipeline-phase-4"]),
        ("dependencies", "package-a"),
        ("acceptance_criteria", []),
        ("branch_name", "refs/heads/refactor/package-a"),
        ("worktree_path", "relative/worktree"),
        ("planning_dir", "/tmp/refactor/planning/x/../package-a"),
        ("scratch_dir", ""),
        ("route_result_path", "/tmp/refactor/planning/package-a/other.json"),
    ],
)
def test_commit_history_package_descriptor_rejects_invalid_field_classes(
    field: str, bad_value: Any
):
    request = _package_source_request()
    request["package_plan"][0][field] = bad_value
    request["plan_hash"] = compute_plan_hash(request)

    decision = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )

    assert decision["status"] == "INVALID"


def test_commit_history_package_descriptor_rejects_unknown_field_and_invalid_integration_ref():
    request = _package_source_request()
    request["package_plan"][0]["unknown"] = "value"
    request["integration_branch_ref"] = "origin/refactor/integration"
    request["plan_hash"] = compute_plan_hash(request)

    decision = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )

    assert decision["status"] == "INVALID"
    assert any("fields must exactly equal" in error for error in decision["errors"])
    assert any("integration_branch_ref" in error for error in decision["errors"])


@pytest.mark.parametrize(
    "duplicate_field",
    [
        "package_id",
        "branch_name",
        "worktree_path",
        "planning_dir",
        "scratch_dir",
        "route_result_path",
    ],
)
def test_commit_history_package_descriptor_rejects_duplicate_identities(
    duplicate_field: str,
):
    request = _package_source_request()
    request["package_plan"][1][duplicate_field] = request["package_plan"][0][
        duplicate_field
    ]
    if duplicate_field == "package_id":
        request["selected_package_ids"][1] = request["selected_package_ids"][0]
    if duplicate_field == "planning_dir":
        request["package_plan"][1]["route_result_path"] = request["package_plan"][0][
            "route_result_path"
        ]
    request["plan_hash"] = compute_plan_hash(request)

    decision = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )

    assert decision["status"] == "INVALID"


@pytest.mark.parametrize("dependency_case", ["unknown", "self", "cycle"])
def test_commit_history_package_descriptor_rejects_dependency_errors(
    dependency_case: str,
):
    request = _package_source_request()
    if dependency_case == "unknown":
        request["package_plan"][1]["dependencies"] = ["package-missing"]
    elif dependency_case == "self":
        request["package_plan"][0]["dependencies"] = ["package-a"]
    else:
        request["package_plan"][0]["dependencies"] = ["package-b"]
        request["package_plan"][1]["dependencies"] = ["package-a"]
    request["plan_hash"] = compute_plan_hash(request)

    decision = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )

    assert decision["status"] == "INVALID"


def test_commit_history_package_descriptor_rejects_result_escape_and_symlink_alias(
    tmp_path: Path,
):
    request = _package_source_request()
    request["package_plan"][0]["route_result_path"] = (
        "/tmp/refactor/planning/package-b/refactoring-route-result.json"
    )
    request["plan_hash"] = compute_plan_hash(request)
    escaped = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )
    assert escaped["status"] == "INVALID"

    request = _package_source_request()
    real = tmp_path / "real-worktree"
    real.mkdir()
    alias = tmp_path / "worktree-alias"
    alias.symlink_to(real, target_is_directory=True)
    request["package_plan"][0]["worktree_path"] = str(alias)
    request["plan_hash"] = compute_plan_hash(request)
    symlinked = validate_package_execution(
        request, _package_ticket_map(request), _current_package_identity(request)
    )
    assert symlinked["status"] == "INVALID"


def test_existing_issue_and_context_composition_cannot_enter_phase0_ticket_create():
    refactor_child = _fenced_yaml_section(
        "agents/refactoring-orchestrator.md", "## Implementation Child Invocation Contract"
    )
    assert refactor_child["ticket_context"]["requires_existing_issue_key"] is True
    assert refactor_child["ticket_context"]["authorizes_ticket_creation"] is False

    implementation = _operator_contract("implementation-pipeline-orchestrator")
    context_input = _input(implementation, "wu_brief_context_path")
    assert context_input["required"] is False
    assert "never authorizes Phase 0 ticket creation" in context_input["description"]
    phase_0 = _section(
        "agents/implementation-pipeline-orchestrator.md", "### Phase 0 — Bootstrap"
    )
    assert "require exactly one existing issue key" in phase_0
    assert "BLOCKED:invalid-wu-brief-context" in phase_0
    create_step = phase_0[
        phase_0.index("3. **Draft the ticket if cold-starting.**") : phase_0.index(
            "4. **Read the ticket from the ticket system.**"
        )
    ]
    assert "When `ticket_id` is unset" in create_step
    assert "wu_brief_context_path" not in create_step


def test_refactoring_workflow_has_one_exact_mirrored_dispatch_surface():
    workflow = _read("workflows/refactoring.md")
    assert workflow.count("## Workflow Dispatch Surface\n") == 1
    embedded = _workflow_dispatch_contract("refactoring")
    assert _fenced_yaml_section(
        "workflows/refactoring.md", "## Workflow Dispatch Surface"
    ) == embedded
    joined_inputs = "\n".join(embedded["inputs"])
    for name in REFACTOR_INPUT_NAMES:
        assert name in joined_inputs
    joined_outputs = "\n".join(embedded["outputs"])
    for path in REFACTOR_ARTIFACTS:
        assert Path(path).name in joined_outputs


def test_refactoring_route_result_schema_is_complete_and_post_merge_only():
    schema = _fenced_yaml_section(
        "agents/refactoring-orchestrator.md", "## Route Result Schema"
    )
    assert schema["schema"] == "refactoring-route-result-v1"
    assert schema["state"] == "VERIFIED_MERGED"
    assert set(schema["required_top_level_fields"]) == {
        "schema",
        "refactoring_invocation_uuid",
        "ticket_source",
        "ticket_system",
        "integration_branch_name",
        "final_integration_sha",
        "pre_merge_expected_process_path",
        "pre_merge_expected_process_sha256",
        "pre_merge_dispatch_evidence_path",
        "pre_merge_dispatch_evidence_sha256",
        "pre_merge_process_tree_path",
        "pre_merge_process_tree_sha256",
        "pre_merge_process_tree_audit_path",
        "pre_merge_process_tree_audit_sha256",
        "expected_process_path",
        "expected_process_sha256",
        "dispatch_evidence_path",
        "dispatch_evidence_sha256",
        "process_tree_path",
        "process_tree_sha256",
        "process_tree_audit_path",
        "process_tree_audit_sha256",
        "owned_process_proofs",
        "auditor_index_path",
        "auditor_index_sha256",
        "child",
        "state",
    }
    assert set(schema["child_required_fields"]) == {
        "ticket_source",
        "slice_identity",
        "child_invocation_uuid",
        "child_session_id",
        "child_prompt_path",
        "child_log_path",
        "implementation_result_path",
        "implementation_result_sha256",
        "ticket_operation_expected_context_path",
        "ticket_operation_expected_context_sha256",
        "ticket_operation_result_path",
        "ticket_operation_result_sha256",
        "owned_process_proofs",
        "declared_head_branch",
        "declared_head_sha",
        "dispatched_base_branch",
        "dispatched_auto_merge_after_phase_9",
        "pr_url",
        "pr_number",
        "open_pr_state",
        "open_observed_is_draft",
        "open_observed_base_ref_name",
        "open_observed_base_sha",
        "open_observed_head_ref_name",
        "open_observed_head_sha",
        "pre_merge_pr_state",
        "pre_merge_observed_is_draft",
        "pre_merge_observed_base_ref_name",
        "pre_merge_observed_base_sha",
        "pre_merge_observed_head_ref_name",
        "pre_merge_observed_head_sha",
        "pre_merge_base_sha",
        "reviewed_base_sha",
        "expected_head_guard_sha",
        "merged_pr_state",
        "merged_observed_base_ref_name",
        "merged_observed_base_sha",
        "merged_observed_head_ref_name",
        "merged_observed_head_sha",
        "merged_observed_merge_sha",
        "pre_merge_evidence_verdict",
        "pre_merge_evidence_path",
        "pre_merge_evidence_sha256",
        "merge_owner",
        "merge_sha",
        "refreshed_integration_sha",
        "merge_first_parent_sha",
        "ancestry_result",
        "immediate_parent_result",
        "auditor_baseline_sha",
        "pre_merge_auditor_current_head",
        "pre_merge_auditor_reports",
        "pre_merge_process_tree_audit_path",
        "pre_merge_process_tree_audit_sha256",
        "post_merge_auditor_current_head",
        "post_merge_auditor_reports",
        "auditor_verdict",
        "process_tree_audit_path",
        "process_tree_audit_sha256",
        "outcome",
    }
    assert schema["success_values"] == {
        "dispatched_auto_merge_after_phase_9": False,
        "open_pr_state": "OPEN",
        "open_observed_is_draft": True,
        "pre_merge_pr_state": "OPEN",
        "pre_merge_observed_is_draft": False,
        "merged_pr_state": "MERGED",
        "merge_owner": "refactoring-orchestrator",
        "ancestry_result": "PASS",
        "immediate_parent_result": "PASS",
        "auditor_verdict": "LOW",
        "outcome": "VERIFIED_MERGED",
    }
    assert set(schema["owned_process_proof_row_required_fields"]) == (
        _CONTRACT_MODULE._OWNED_PROCESS_PROOF_FIELDS
    )
    assert schema["top_level_owned_process_proofs"] == {
        "owner": "refactoring-orchestrator",
        "exact_stage_order": ["pre-merge", "final"],
    }
    assert schema["child_owned_process_proofs"] == {
        "owner": "implementation-pipeline",
        "exact_stage_order": ["phase-4", "phase-6", "phase-8"],
    }
    assert set(schema["auditor_index_schema"]["required_fields"]) == (
        _CONTRACT_MODULE._REFACTORING_AUDITOR_INDEX_FIELDS
    )
    assert tuple(schema["auditor_index_schema"]["exact_role_order"]) == (
        _CONTRACT_MODULE._REFACTORING_AUDITOR_ROLES
    )
    assert schema["auditor_index_schema"]["exact_stages"] == [
        "pre-merge",
        "post-merge",
    ]
    assert schema["auditor_index_schema"]["reports_per_stage"] == 5
    assert set(schema["auditor_index_schema"]["report_row_required_fields"]) == (
        _CONTRACT_MODULE._REFACTORING_AUDITOR_REPORT_FIELDS
    )
    assert schema["auditor_index_schema"]["additional_properties"] is False
    assert set(schema["exact_nested_pr_head_join"]["pr_fields"]) == {
        "child.pr_url",
        "child.pr_number",
        "child.implementation_result.pr_url",
        "child.implementation_result.pr_number",
    }
    assert "child.expected_head_guard_sha" in schema["exact_nested_pr_head_join"][
        "head_sha_fields"
    ]
    assert "child.merged_observed_base_sha" in schema["exact_nested_pr_head_join"][
        "base_sha_fields"
    ]
    schema_body = _section("agents/refactoring-orchestrator.md", "## Route Result Schema")
    assert "complete and non-null" in schema_body
    assert "open-only PR" in schema_body
    assert "never a successful route result" in schema_body


def test_refactoring_expected_process_covers_child_inputs_and_every_auditor_rerun():
    process = _section(
        "agents/refactoring-orchestrator.md", "## Expected Process And Join"
    )
    for value in (
        "refactoring-expected-process-pre-merge.json",
        "stable-id nodes",
        "no post-merge node",
        "no unknowable child UUID",
        "refactoring-dispatch-evidence-pre-merge.json",
        "agents trace --json ${refactoring_invocation_uuid}",
        "refactoring-process-tree-pre-merge.json",
        "independent `process-tree-auditor`",
        "blocking mode",
        "refactoring-process-tree-audit-pre-merge.md",
        "refactoring-expected-process.json",
        "refactoring-dispatch-evidence.json",
        "retains every pre-merge declaration unchanged",
        "adds post-merge-auditor nodes",
        "current hash-bound PASS report",
        "Both projections complement and never duplicate",
    ):
        assert value in process
    for copied_pipeline_internal in ("Phase 2.5", "Phase 6b", "Phase 8"):
        assert copied_pipeline_internal not in process


def test_refactoring_auditor_gate_is_exact_current_and_round_aware():
    auditor = _section(
        "agents/refactoring-orchestrator.md", "## Refactoring Auditor Contract"
    )
    for name in REFACTOR_AUDITORS:
        assert f"`{name}`" in auditor
    assert "`verification-plan-reviewer` is not route-level applicable" in auditor
    for value in (
        "auditor_baseline_sha",
        "pre_merge_current_sha",
        "post_merge_current_sha",
        "full five-auditor set",
        "all five reports present, current to one named head, and `LOW`",
        "no finding or metric worse than the baseline",
        "substantive correction invalidates every prior pre-merge accept",
        "same implementation-pipeline owner",
        "rerun all affected implementation-child gates",
        "Before a second revise/review round starts",
        "decision-encoder",
        "audit_history_path",
    ):
        assert value in auditor


def test_refactoring_post_merge_success_and_fail_closed_results_are_explicit():
    procedure = _section("agents/refactoring-orchestrator.md", "## Procedure")
    phase_4 = procedure.index("5. Phase 4")
    phase_5 = procedure.index("6. Phase 5")
    assert procedure.index("state=OPEN", phase_4, phase_5) >= phase_4
    for value in (
        "baseRefName == ${integration_branch_name}",
        "headRefName",
        "declared child head SHA",
        "BLOCKED:refactor-pr-base-mismatch",
        "BLOCKED:refactor-pr-head-mismatch",
        "BLOCKED:refactor-pr-evidence-not-ready",
    ):
        assert value in procedure[phase_4:phase_5]
    post_merge = procedure[phase_5:]
    for value in (
        '--match-head-commit "${pre_merge_observed_head_sha}"',
        "state=MERGED",
        "unchanged identities",
        "non-null `mergeCommit.oid == merge_sha`",
        'gh pr ready --undo "${pr_url}" --repo "${repo}"',
        "validate-ready-state-restoration",
        "owner=refactoring-owner-merge",
        "BLOCKED:ready-state-restoration-failed",
        "BLOCKED:merge-attempt-started",
        "replay_permitted=false",
        "state=VERIFIED_MERGED",
    ):
        assert value in post_merge
    stops = _section("agents/refactoring-orchestrator.md", "## Stop Conditions")
    assert "PR-open alone" not in stops
    assert "Once the merge command starts" in stops


def test_external_integration_base_advancement_invalidates_refactoring_acceptance():
    reviewed = _provider_bundle(base_sha="a0" * 20)
    immediate = _provider_bundle(base_sha="a1" * 20)
    transition = validate_pr_currentness(
        reviewed,
        immediate,
        "a1" * 20,
        reviewed["head_ref_oid"],
        context="refactoring-pre-merge",
    )
    assert transition["status"] == "STALE_CURRENTNESS"
    procedure = _section("agents/refactoring-orchestrator.md", "## Procedure")
    phase_5 = procedure[procedure.index("6. Phase 5") :]
    assert "pre_merge_base_sha == reviewed_base_sha == baseRefOid" in phase_5
    assert "state=STALE_CURRENTNESS" in phase_5
    assert "restore-draft-then-refresh-rebase-and-rerun-parent-sensitive-gates" in phase_5
    assert "BLOCKED:ready-state-restoration-failed" in phase_5
    assert phase_5.index("state=STALE_CURRENTNESS") < phase_5.index(
        "Only the exact-equality path may invoke"
    )


def test_refactoring_rejects_full_or_remote_integration_refs_before_comparison():
    canonical = _section("agents/refactoring-orchestrator.md", "## Canonical Invocation")
    for value in (
        "git check-ref-format --branch",
        "refs/heads/*",
        "refs/remotes/*",
        "origin/*",
        "BLOCKED:unsupported-integration-branch-ref",
        "integration_branch_name=${integration_branch_ref}",
        "Do not strip or otherwise normalize unsupported full or remote refs",
    ):
        assert value in canonical
    assert canonical.index("BLOCKED:unsupported-integration-branch-ref") < _read(
        "agents/refactoring-orchestrator.md"
    ).index("baseRefName == ${integration_branch_name}")


def test_dependency_completion_requires_verified_merged_ancestral_route_result():
    ownership = _section(
        "agents/feature-orchestrator.md", "### Route dispatch and merge ownership"
    )
    assert "verified merged route result" in ownership
    assert "base equals `feature_branch`" in ownership
    assert "merge commit is an ancestor of the refreshed feature head" in ownership
    assert "BLOCKED:feature-dependency-not-merged" in ownership


def test_feature_artifacts_are_stable_and_mirrored():
    contract = _operator_contract("feature-orchestrator")
    output = contract["outputs"][0]
    assert set(output["wrote_lines"]) == FEATURE_ARTIFACTS
    assert "FINAL_PR_OPEN_HANDOFF" in output["success_shape"]

    artifact_section = _section("agents/feature-orchestrator.md", "## Artifact Schemas")
    workflow_outputs = "\n".join(
        _workflow_dispatch_contract("feature-development")["outputs"]
    )
    for path in FEATURE_ARTIFACTS:
        assert path in _read("agents/feature-orchestrator.md")
        if not path.startswith("${audit_history_path}"):
            assert Path(path).name in artifact_section
        if path.startswith("${audit_history_path}"):
            assert "feature-audit-history.md when review reaches round two" in workflow_outputs
        else:
            assert Path(path).name in workflow_outputs


def test_feature_process_tree_join_is_independent_attempt_scoped_and_cumulative():
    process = _section("agents/feature-orchestrator.md", "### Feature process-tree join")
    for value in (
        "feature-expected-process.json",
        "route-dispatch-evidence.json",
        "contains no guessed child UUID",
        "route-only pre-audit",
        "independent-process-auditor",
        "blocking mode",
        "stdout_report_copy=true",
        "extracted bytes to equal the consumed canonical report bytes exactly",
        "route child plus the independent auditor direct child",
        "preventing circular hashes",
        "complete attempt union",
        "one cumulative independent join",
    ):
        assert value in process
    for copied_child_internal in ("Phase 2.5", "Phase 6b", "Phase 8"):
        assert copied_child_internal not in process

    expected_schema = _section("agents/feature-orchestrator.md", "## Artifact Schemas")
    assert "final cumulative one-row-per-attempt snapshot" in expected_schema
    assert "child-internal invocations are not rows" in expected_schema
    ownership = _section(
        "agents/feature-orchestrator.md", "### Route dispatch and merge ownership"
    )
    assert "one accepted route result and one or more immutable attempts" in ownership


def test_route_artifact_lineage_constructs_directionally_and_authorizes_merge(
    tmp_path: Path,
):
    paths = _route_lineage_fixture(tmp_path)

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "MERGE_AUTHORIZED"
    assert decision["errors"] == []
    assert decision["acceptance_sha256"] == hashlib.sha256(
        paths["acceptance"].read_bytes()
    ).hexdigest()
    assert paths["process_report"].read_bytes() == paths["process_auditor_output"].read_bytes()
    pre_trace = json.loads(paths["pre_audit_trace"].read_text())
    assert len(pre_trace["root"]["children"]) == 1
    assert len(pre_trace["root"]["children"][0]["children"]) == 2
    assert {
        child["invocation"]["model_name"]
        for child in pre_trace["root"]["children"][0]["children"]
    } == {"gpt-medium", "gpt-xhigh"}
    assert len(json.loads(paths["final_trace"].read_text())["root"]["children"]) == 2
    output = tmp_path / "route-authorization.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-route-artifact-lineage",
            "--acceptance",
            str(paths["acceptance"]),
            "--fresh-currentness",
            str(paths["fresh_currentness"]),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == (
        "MERGE_AUTHORIZED"
    )


def test_route_artifact_lineage_rejects_legacy_currentness_without_fetched_head(
    tmp_path: Path,
):
    paths = _route_lineage_fixture(tmp_path)
    currentness = json.loads(paths["fresh_currentness"].read_text(encoding="utf-8"))
    currentness.pop("fetched_head_sha")
    _write_json_fixture(paths["fresh_currentness"], currentness)

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert (
        "fresh currentness must use the exact pr-currentness-validation-v1 key set"
        in decision["errors"]
    )


def test_route_artifact_lineage_rejects_stale_child_owned_process_proof(tmp_path: Path):
    paths = _route_lineage_fixture(tmp_path)
    paths["phase-4-process-tree"].write_text(
        paths["phase-4-process-tree"].read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert "implementation route phase-4 process_tree hash mismatch" in decision["errors"]


def test_feature_route_evidence_schema_matches_production_validator():
    schema = _fenced_yaml_section(
        "agents/feature-orchestrator.md", "### Route Evidence Schema"
    )
    assert schema["schema"] == "feature-route-evidence-v1"
    assert set(schema["required_fields"]) == _CONTRACT_MODULE._ROUTE_EVIDENCE_FIELDS
    assert set(schema["ticket_operation_result"]["required_fields"]) == (
        _CONTRACT_MODULE._TICKET_OPERATION_RESULT_REF_FIELDS
    )
    assert schema["ticket_operation_result"]["producer_schema"] == (
        "ticket-operation-result-v1"
    )
    assert schema["process_verdict_rule"] == (
        "exactly-one-canonical-Verdict-line-with-whole-value-PASS"
    )


@pytest.mark.parametrize("backend", ["jira", "linear"])
def test_ticket_operator_result_producer_to_consumer_positive(
    tmp_path: Path, backend: str
):
    paths = _route_lineage_fixture(tmp_path, backend=backend)
    result = json.loads(paths["ticket_operation_result"].read_text(encoding="utf-8"))
    expected_context = json.loads(
        paths["ticket_expected_context"].read_text(encoding="utf-8")
    )

    decision = validate_ticket_operation_result(
        result,
        expected_context,
        result_path=paths["ticket_operation_result"],
        expected_context_path=paths["ticket_expected_context"],
    )

    assert decision["status"] == "VALID", decision["errors"]
    assert decision["producer_invocation_uuid"] == (
        "30000000-0000-4000-8000-000000000001"
    )
    validation_path = tmp_path / f"{backend}-ticket-operation-validation.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-ticket-operation-result",
            "--result",
            str(paths["ticket_operation_result"]),
            "--expected-context",
            str(paths["ticket_expected_context"]),
            "--output",
            str(validation_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(validation_path.read_text(encoding="utf-8"))["status"] == "VALID"


def test_ticket_operation_validator_cli_rejects_omitted_expected_context(tmp_path: Path):
    paths = _route_lineage_fixture(tmp_path)
    validation_path = tmp_path / "missing-expected-context-validation.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-ticket-operation-result",
            "--result",
            str(paths["ticket_operation_result"]),
            "--output",
            str(validation_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "--expected-context" in completed.stderr
    assert not validation_path.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticket_key", "WRONG-999"),
        ("backend", "jira"),
        ("attempt_number", 2),
        ("pr_url", "https://github.com/other/repo/pull/42"),
        ("pr_number", 99),
        ("reviewed_base_branch", "wrong-base"),
        ("reviewed_base_ref", "refs/remotes/origin/wrong-base"),
        ("reviewed_base_sha", "c0" * 20),
        ("reviewed_head_branch", "wrong-head"),
        ("reviewed_head_ref", "refs/heads/wrong-head"),
        ("reviewed_head_sha", "d0" * 20),
        ("operation", "comment"),
    ],
)
def test_ticket_operation_validator_cli_rejects_wrong_caller_context_with_current_producer(
    tmp_path: Path, field: str, value: Any
):
    paths = _route_lineage_fixture(tmp_path)
    result = json.loads(paths["ticket_operation_result"].read_text(encoding="utf-8"))
    result[field] = value
    if field == "ticket_key":
        result["readback_ticket_key"] = value
        result["remote_comment_url"] = result["remote_comment_url"].replace(
            "AGE-259", str(value)
        )
        result["readback_comment_url"] = result["remote_comment_url"]
    elif field == "backend":
        result["producer_operator"] = "agents/jira-operator.md"
    elif field == "pr_number":
        result["pr_url"] = f"https://github.com/example/repo/pull/{value}"
    _write_json_fixture(paths["ticket_operation_result"], result)
    _synchronize_ticket_operation_producer(paths)
    validation_path = tmp_path / f"wrong-{field}-validation.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-ticket-operation-result",
            "--result",
            str(paths["ticket_operation_result"]),
            "--expected-context",
            str(paths["ticket_expected_context"]),
            "--output",
            str(validation_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    decision = json.loads(validation_path.read_text(encoding="utf-8"))
    assert completed.returncode == 2
    assert decision["status"] == "INVALID"
    assert any(
        f"ticket operation result {field} mismatch" in error
        for error in decision["errors"]
    )


@pytest.mark.parametrize("backend", ["jira", "linear"])
@pytest.mark.parametrize("mismatch", ["site", "ticket"])
def test_ticket_operation_validator_cli_rejects_mismatched_encoded_remote_url(
    tmp_path: Path, backend: str, mismatch: str
):
    paths = _route_lineage_fixture(tmp_path, backend=backend)
    result = json.loads(paths["ticket_operation_result"].read_text(encoding="utf-8"))
    if mismatch == "site":
        replacement = "wrong.example.com"
        result["remote_comment_url"] = re.sub(
            r"(?<=https://)[^/]+", replacement, result["remote_comment_url"], count=1
        )
    else:
        result["remote_comment_url"] = result["remote_comment_url"].replace(
            "AGE-259", "WRONG-999"
        )
    result["readback_comment_url"] = result["remote_comment_url"]
    _write_json_fixture(paths["ticket_operation_result"], result)
    _synchronize_ticket_operation_producer(paths)
    validation_path = tmp_path / f"{backend}-{mismatch}-remote-url-validation.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-ticket-operation-result",
            "--result",
            str(paths["ticket_operation_result"]),
            "--expected-context",
            str(paths["ticket_expected_context"]),
            "--output",
            str(validation_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    decision = json.loads(validation_path.read_text(encoding="utf-8"))
    assert completed.returncode == 2
    assert decision["status"] == "INVALID"
    assert "ticket operation result remote comment identity is invalid" in decision["errors"]


def test_ticket_operators_share_closed_comment_readback_schema_and_contract_inputs():
    schemas = {
        backend: _fenced_yaml_section(
            f"agents/{backend}-operator.md", "### Producer-Authenticated Comment Readback"
        )
        for backend in ("jira", "linear")
    }
    for backend, schema in schemas.items():
        assert schema["schema"] == "ticket-operation-result-v1"
        assert schema["additional_properties"] is False
        assert set(schema["required_fields"]) == _CONTRACT_MODULE._TICKET_OPERATION_RESULT_FIELDS
        assert schema["fixed_values"]["backend"] == backend
        assert schema["fixed_values"]["operation"] == "comment-readback"
        assert schema["fixed_values"]["status"] == "PASS"
        assert schema["producer_log_schema"] == "ticket-operation-producer-log-v1"
        assert schema["producer_output_schema"] == "ticket-operation-readback-v1"
        assert "validate-ticket-operation-result --expected-context" in schema[
            "caller_validator"
        ]
        contract = _operator_contract(f"{backend}-operator")
        input_names = {item["name"] for item in contract["inputs"]}
        assert {
            "operation",
            "ticket_operation_context",
            "operation_result_path",
            "producer_log_path",
            "producer_output_path",
        } <= input_names
        comment_output = next(
            output for output in contract["outputs"] if output["task"] == "comment"
        )
        assert "ticket-operation-result-v1" in comment_output["success_shape"]

    for backend in ("jira", "linear"):
        contract = _operator_contract(f"{backend}-operator")
        operation_input = next(
            item for item in contract["inputs"] if item["name"] == "operation"
        )
        assert operation_input["type"] == "enum"
        assert operation_input["options"] == ["comment-readback"]
        assert operation_input["required"] is False
        assert "must be comment-readback" in operation_input["description"]
        required_inputs = _section(
            f"agents/{backend}-operator.md", "## Required Inputs"
        )
        assert "Any other value is out-of-contract and returns `BLOCKED`" in required_inputs


@pytest.mark.parametrize("backend", ["jira", "linear"])
def test_ticket_operator_comment_readback_reconciles_exact_ticket_and_body_before_create(
    backend: str,
):
    readback = _section(
        f"agents/{backend}-operator.md", "### Producer-Authenticated Comment Readback"
    )

    reconciliation = readback.index("Reconcile before any create request.")
    zero = readback.index("Zero matches:")
    one = readback.index("One match:")
    multiple = readback.index("More than one match:")
    zero_match = readback[zero:one]
    assert reconciliation < zero < one < multiple
    assert "exact context ticket key" in readback
    assert "posted-body SHA-256" in readback
    assert "create once" in zero_match
    assert "do not" in readback[one:multiple]
    assert "before POST" in readback[multiple:] or "before create" in readback[multiple:]
    assert "write no PASS result artifacts" in readback[multiple:]
    if backend == "jira":
        assert "Read every page" in readback
        assert "canonicalize each returned ADF body by the same rule" in readback
    else:
        comment_procedure = _section("agents/linear-operator.md", "## Procedure: Comment")
        assert (
            'Returns `{"ok": true, "data": {"id": "<uuid>", "issueId": "<uuid>"}}`.'
            in comment_procedure
        )
        assert "returned body hash" not in zero_match
        assert "non-blank ID and returned issue UUID" in zero_match
        assert "verify the posted-body hash through the mandatory post-create readback" in zero_match
        assert "fully paginated `list-comments`" in readback
        assert "exact UTF-8 bytes" in readback
        assert "do not trim, normalize line endings, or render Markdown" in readback


def test_jira_authenticated_readback_is_v3_adf_only_without_changing_ordinary_fallback():
    comment_procedure = _section("agents/jira-operator.md", "## Procedure: Comment")
    endpoint_contract = _between(
        "agents/jira-operator.md",
        "**Endpoint contract:**\n",
        "For simple plain-text comments:\n",
    )
    readback = _section(
        "agents/jira-operator.md", "### Producer-Authenticated Comment Readback"
    )

    assert "v2 fallback applies only to ordinary comments" in endpoint_contract
    assert "operation=comment-readback` path below is v3-only" in endpoint_contract
    assert "v3-only" in readback
    assert "sorted object keys" in readback
    assert "no insignificant whitespace" in readback
    assert "without a v2 fallback" in readback
    assert "/rest/api/2/" not in readback
    assert "/rest/api/2/issue/{issueIdOrKey}/comment" in comment_procedure


def test_phase_9_named_ticket_dispatch_validates_and_transports_producer_result():
    phase_9 = _section(
        "agents/implementation-pipeline-orchestrator.md",
        "### Phase 9 — Verified PR Outcome",
    )
    for value in (
        "operation=comment-readback",
        "route_attempt_number",
        "agents -a ${ticket_operator}",
        "never override its frontmatter model",
        "validate-ticket-operation-result",
        "--expected-context",
        "ticket-operation-expected-context-v1",
        "ticket_operation_expected_context_path",
        "ticket_operation_expected_context_sha256",
        "ticket_operation_result_path",
        "ticket_operation_result_sha256",
        "owned_process_proofs",
        "implementation-pipeline-result-v1",
    ):
        assert value in phase_9
    assert "agents -m gpt-xhigh" not in phase_9


def test_phase_9_expected_context_and_owned_process_schemas_match_validator():
    expected_context = _fenced_yaml_section(
        "agents/implementation-pipeline-orchestrator.md",
        "### Ticket Operation Expected Context Schema",
    )
    assert expected_context["schema"] == "ticket-operation-expected-context-v1"
    assert expected_context["additional_properties"] is False
    assert set(expected_context["required_fields"]) == (
        _CONTRACT_MODULE._TICKET_OPERATION_EXPECTED_CONTEXT_FIELDS
    )
    assert expected_context["write_order"] == "write-and-hash-before-ticket-dispatch"
    assert "--expected-context" in expected_context["validator"]

    process_proofs = _fenced_yaml_section(
        "agents/implementation-pipeline-orchestrator.md",
        "### Implementation-Owned Process Proof Schema",
    )
    assert process_proofs["field"] == "owned_process_proofs"
    assert process_proofs["owner"] == "implementation-pipeline"
    assert process_proofs["exact_stage_order"] == ["phase-4", "phase-6", "phase-8"]
    assert set(process_proofs["row_required_fields"]) == (
        _CONTRACT_MODULE._OWNED_PROCESS_PROOF_FIELDS
    )


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda evidence, _paths: evidence.pop("ticket_operation_result"),
            "route evidence fields must exactly equal",
        ),
        (
            lambda evidence, _paths: evidence["ticket_operation_result"].update(
                unknown="value"
            ),
            "ticket_operation_result fields must exactly equal",
        ),
        (
            lambda evidence, _paths: evidence.update(ticket_operation_result="PASS"),
            "ticket_operation_result fields must exactly equal",
        ),
        (
            lambda evidence, paths: paths["ticket_operation_result"].write_text(
                paths["ticket_operation_result"].read_text(encoding="utf-8") + " ",
                encoding="utf-8",
            ),
            "ticket operation result hash mismatch",
        ),
    ],
    ids=["absent", "unknown", "malformed", "stale"],
)
def test_route_artifact_lineage_rejects_invalid_ticket_result_reference(
    tmp_path: Path, mutation, expected_error: str
):
    paths = _route_lineage_fixture(tmp_path)
    route_evidence = json.loads(paths["route_evidence"].read_text(encoding="utf-8"))
    mutation(route_evidence, paths)
    _write_json_fixture(paths["route_evidence"], route_evidence)
    _refresh_route_evidence_lineage(paths)

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert any(expected_error in error for error in decision["errors"])


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("ticket_key", "WRONG-1", "ticket operation result ticket_key mismatch"),
        ("backend", "jira", "ticket operation result backend mismatch"),
        ("operation", "comment", "operation must equal comment-readback"),
        ("status", "FAIL", "status must equal PASS"),
        ("owning_route", "refactoring", "owning_route must equal implementation-pipeline"),
        ("attempt_number", 2, "attempt_number mismatch"),
        ("pr_url", "https://github.com/example/repo/pull/999", "pr_url mismatch"),
        ("pr_number", 999, "PR URL/number identity is invalid"),
        ("reviewed_base_branch", "wrong-base", "reviewed_base_branch mismatch"),
        ("reviewed_base_ref", "refs/remotes/origin/wrong-base", "reviewed_base_ref mismatch"),
        ("reviewed_base_sha", "c0" * 20, "reviewed_base_sha mismatch"),
        ("reviewed_head_branch", "wrong-head", "reviewed_head_branch mismatch"),
        ("reviewed_head_ref", "refs/heads/wrong-head", "reviewed_head_ref mismatch"),
        ("reviewed_head_sha", "d0" * 20, "reviewed_head_sha mismatch"),
        ("remote_comment_id", "", "remote comment identity is invalid"),
        ("remote_comment_url", "not-a-url", "remote comment identity is invalid"),
        ("readback_status", "FAIL", "readback_status must equal PASS"),
        ("readback_ticket_key", "WRONG-1", "readback ticket identity mismatch"),
        ("producer_operator", "agents/jira-operator.md", "producer operator/backend mismatch"),
        ("producer_invocation_uuid", "not-a-uuid", "producer_invocation_uuid"),
        ("schema", "ticket-operation-result-v2", "schema must equal ticket-operation-result-v1"),
    ],
)
def test_route_artifact_lineage_rejects_hash_consistent_ticket_semantic_falsehoods(
    tmp_path: Path, field: str, value: Any, expected_error: str
):
    paths = _route_lineage_fixture(tmp_path)
    _mutate_json(paths["ticket_operation_result"], lambda result: result.update({field: value}))
    _refresh_ticket_operation_lineage(paths)

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert any(expected_error in error for error in decision["errors"]), decision["errors"]


@pytest.mark.parametrize("corruption", ["unknown-key", "missing-readback", "stale-producer"])
def test_route_artifact_lineage_rejects_malformed_or_stale_ticket_producer_evidence(
    tmp_path: Path, corruption: str
):
    paths = _route_lineage_fixture(tmp_path)
    if corruption == "unknown-key":
        _mutate_json(
            paths["ticket_operation_result"],
            lambda result: result.update(unknown="value"),
        )
        _refresh_ticket_operation_lineage(paths)
        expected_error = "ticket operation result fields must exactly equal"
    elif corruption == "missing-readback":
        _mutate_json(
            paths["ticket_operation_result"],
            lambda result: result.pop("readback_comment_id"),
        )
        _refresh_ticket_operation_lineage(paths)
        expected_error = "ticket operation result fields must exactly equal"
    else:
        paths["ticket_producer_output"].write_text("{}\n", encoding="utf-8")
        expected_error = "ticket operation producer output hash mismatch"

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert any(expected_error in error for error in decision["errors"]), decision["errors"]


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("empty", "exactly the declared route child"),
        ("missing", "cannot hash pre_audit_trace.path"),
        ("duplicate", "invocation UUIDs must be unique"),
        ("unexpected-root-sibling", "undeclared direct root children"),
        ("reparented-nested", "undeclared direct root children"),
        ("wrong-identity", "invocation UUID must occur exactly once"),
        ("wrong-parent", "actual parent"),
        ("wrong-model", "actual model"),
        ("wrong-operator", "operator"),
        ("failed", "status must equal succeeded"),
        ("non-terminal", "terminal with finished_at"),
    ],
)
def test_route_artifact_lineage_rejects_invalid_pre_audit_route_topology(
    tmp_path: Path, corruption: str, expected_error: str
):
    paths = _route_lineage_fixture(tmp_path)
    if corruption == "missing":
        paths["pre_audit_trace"].unlink()
    elif corruption == "wrong-operator":
        _mutate_json(
            paths["pre_audit_expected_process"],
            lambda expected: expected["nodes"][0].update(operator_or_role="wrong-operator"),
        )
        _mutate_json(
            paths["pre_audit_dispatch_snapshot"],
            lambda dispatch: dispatch["nodes"][0].update(operator_or_role="wrong-operator"),
        )
        _refresh_route_evidence_lineage(paths)
    else:
        trace = json.loads(paths["pre_audit_trace"].read_text(encoding="utf-8"))
        children = trace["root"]["children"]
        if corruption == "empty":
            children.clear()
        elif corruption == "duplicate":
            children.append(deepcopy(children[0]))
        elif corruption == "unexpected-root-sibling":
            unexpected = deepcopy(children[0]["children"][0])
            unexpected["invocation"].update(
                id="60000000-0000-4000-8000-000000000001",
                agent_runner_invocation_id="60000000-0000-4000-8000-000000000001",
                parent_id=_RUNNER_UUID,
            )
            children.append(unexpected)
        elif corruption == "reparented-nested":
            reparented = children[0]["children"].pop(0)
            reparented["invocation"]["parent_id"] = _RUNNER_UUID
            children.append(reparented)
        elif corruption == "wrong-identity":
            children[0]["invocation"].update(
                id="60000000-0000-4000-8000-000000000002",
                agent_runner_invocation_id="60000000-0000-4000-8000-000000000002",
            )
        elif corruption == "wrong-parent":
            children[0]["invocation"]["parent_id"] = _SECOND_RUNNER_UUID
        elif corruption == "wrong-model":
            children[0]["invocation"]["model_name"] = "gpt-high"
        elif corruption == "non-terminal":
            children[0]["invocation"]["finished_at"] = None
        else:
            children[0]["invocation"].update(status="failed", success=False, exit_code=1)
        _write_json_fixture(paths["pre_audit_trace"], trace)
        _refresh_route_evidence_lineage(paths)

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert any(expected_error in error for error in decision["errors"]), decision["errors"]


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("empty", "route child and independent auditor child"),
        ("missing-auditor", "route child and independent auditor child"),
        ("duplicate-auditor", "invocation UUIDs must be unique"),
        ("wrong-parent", "actual parent"),
        ("wrong-model", "actual model"),
        ("wrong-operator", "operator"),
        ("failed", "status must equal succeeded"),
        ("stale-auditor", "process_auditor_output hash mismatch"),
    ],
)
def test_route_artifact_lineage_rejects_invalid_final_auditor_topology(
    tmp_path: Path, corruption: str, expected_error: str
):
    paths = _route_lineage_fixture(tmp_path)
    if corruption == "stale-auditor":
        paths["process_auditor_output"].write_text("stale\n", encoding="utf-8")
    elif corruption == "wrong-operator":
        _mutate_json(
            paths["final_expected_process"],
            lambda expected: expected["nodes"][1].update(operator_or_role="wrong-operator"),
        )
        _mutate_json(
            paths["final_dispatch_snapshot"],
            lambda dispatch: dispatch["nodes"][1].update(operator_or_role="wrong-operator"),
        )
        _refresh_acceptance_artifact_hash(paths, "final_expected_process")
        final_dispatch = json.loads(
            paths["final_dispatch_snapshot"].read_text(encoding="utf-8")
        )
        final_dispatch["expected_process_sha256"] = hashlib.sha256(
            paths["final_expected_process"].read_bytes()
        ).hexdigest()
        _write_json_fixture(paths["final_dispatch_snapshot"], final_dispatch)
        _refresh_acceptance_artifact_hash(paths, "final_dispatch_snapshot")
    else:
        trace = json.loads(paths["final_trace"].read_text(encoding="utf-8"))
        children = trace["root"]["children"]
        if corruption == "empty":
            children.clear()
        elif corruption == "missing-auditor":
            children.pop()
        elif corruption == "duplicate-auditor":
            children.append(deepcopy(children[1]))
        elif corruption == "wrong-parent":
            children[1]["invocation"]["parent_id"] = _SECOND_RUNNER_UUID
        elif corruption == "wrong-model":
            children[1]["invocation"]["model_name"] = "gpt-xhigh"
        else:
            children[1]["invocation"].update(status="failed", success=False, exit_code=1)
        _write_json_fixture(paths["final_trace"], trace)
        _refresh_acceptance_artifact_hash(paths, "final_trace")

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert any(expected_error in error for error in decision["errors"]), decision["errors"]


@pytest.mark.parametrize(
    "verdict_text",
    [
        "",
        "Verdict: FAIL",
        "Verdict: NEEDS_INPUT",
        "Verdict: BLOCKED",
        "Verdict: PASS\nVerdict: PASS",
        "Verdict: FAIL\nVerdict: PASS",
        "Verdict: PASS or FAIL",
        "Verdict: PASS | FAIL | NEEDS_INPUT",
    ],
    ids=[
        "missing",
        "fail",
        "needs-input",
        "blocked",
        "duplicate",
        "conflicting",
        "ambiguous",
        "template",
    ],
)
def test_route_artifact_lineage_rejects_every_noncanonical_process_verdict(
    tmp_path: Path, verdict_text: str
):
    paths = _route_lineage_fixture(tmp_path)
    report = paths["process_report"].read_text(encoding="utf-8")
    paths["process_report"].write_text(
        report.replace("Verdict: PASS", verdict_text), encoding="utf-8"
    )
    _refresh_acceptance_artifact_hash(paths, "process_report")

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert any("canonical Verdict" in error or "canonical verdict" in error for error in decision["errors"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda paths: paths["route_evidence"].write_text(
            paths["route_evidence"].read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        ),
        lambda paths: paths["process_report"].write_text(
            paths["process_report"].read_text(encoding="utf-8") + "\nmutated\n",
            encoding="utf-8",
        ),
        lambda paths: _mutate_json(
            paths["acceptance"],
            lambda value: value["provider_reviewed_identity"].update(pr_number=999),
        ),
    ],
    ids=["stale-route-evidence", "stale-process-audit", "mutated-acceptance"],
)
def test_route_artifact_lineage_rejects_stale_or_mutated_artifacts(
    tmp_path: Path, mutate
):
    paths = _route_lineage_fixture(tmp_path)
    mutate(paths)

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert decision["errors"]


def test_route_evidence_and_process_report_cannot_reference_future_acceptance(
    tmp_path: Path,
):
    paths = _route_lineage_fixture(tmp_path)
    _mutate_json(
        paths["route_evidence"],
        lambda value: value.update(attempt_process_report_sha256="f" * 64),
    )
    acceptance = json.loads(paths["acceptance"].read_text(encoding="utf-8"))
    acceptance["route_evidence"]["sha256"] = hashlib.sha256(
        paths["route_evidence"].read_bytes()
    ).hexdigest()
    _write_json_fixture(paths["acceptance"], acceptance)

    decision = validate_route_artifact_lineage(
        paths["acceptance"], paths["fresh_currentness"]
    )

    assert decision["status"] == "INVALID"
    assert any("route evidence contains future hash fields" in error for error in decision["errors"])


def test_route_attempt_index_schema_matches_production_transition_validator():
    schema = _fenced_yaml_section(
        "agents/feature-orchestrator.md", "### Route Attempt Index Schema"
    )
    assert schema["schema"] == "feature-route-attempt-index-v1"
    assert schema["state_values"] == ["IN_PROGRESS", "COMPLETE"]
    assert schema["artifact_roots"]["required_fields"] == ["proof_envelope_root"]
    assert schema["attempt"]["identity"] == ["ticket_id", "attempt_number"]
    assert schema["attempt"]["terminal_states"] == [
        "STALE_CURRENTNESS",
        "REPLAY_REQUIRED",
        "BLOCKED:ready-state-restoration-failed",
        "BLOCKED:merge-attempt-started",
        "VERIFIED_MERGED",
    ]
    assert "proof_envelope_path" in schema["attempt"]["required_fields"]
    assert "proof_envelope_sha256" in schema["attempt"]["required_fields"]
    assert schema["validators"]["attempt_index"] == (
        "tools/operational_contracts.py validate-route-attempts"
    )
    assert schema["validators"]["direct_merge_lineage"] == (
        "tools/operational_contracts.py validate-route-artifact-lineage"
    )
    assert schema["validators"]["common_route_process"] == (
        "tools/operational_contracts.py validate-route-process-proof"
    )


def test_route_attempt_proof_schema_matches_production_validator():
    schema = _fenced_yaml_section(
        "agents/feature-orchestrator.md", "### Route Attempt Proof Envelope Schema"
    )
    assert schema["schema"] == "feature-route-attempt-proof-v1"
    assert schema["identity_fields"] == [
        "feature_branch",
        "local_coverage_command_sha256",
        "ticket_id",
        "attempt_number",
        "owning_route",
    ]
    assert schema["feature_branch_rule"] == (
        "exact-manifest-and-attempt-index-short-branch-name"
    )
    assert set(schema["artifact_reference_fields"]) == set(
        _CONTRACT_MODULE._ROUTE_PROOF_ARTIFACT_FIELDS
    ) | {"common_validation_result", "route_specific_evidence"}
    assert schema["child_owned_process_proofs"]["row_required_fields"] == [
        "owner",
        "stage",
        "artifact",
        "path",
        "sha256",
    ]
    assert schema["validator"] == "tools/operational_contracts.py validate-route-attempts"


def test_attempt_acceptance_schema_is_acyclic_and_merge_authorizing():
    schema = _fenced_yaml_section(
        "agents/feature-orchestrator.md", "### Attempt Acceptance Envelope Schema"
    )
    assert schema["schema"] == "feature-route-attempt-acceptance-v1"
    assert schema["construction_order"] == [
        "route-evidence",
        "pre-audit-process-proof",
        "independent-process-audit",
        "final-process-proof",
        "common-process-validation",
        "pre-ready-currentness",
        "attempt-acceptance",
    ]
    assert set(schema["required_fields"]) == _CONTRACT_MODULE._ACCEPTANCE_FIELDS
    assert schema["process_topology"] == (
        "exact-feature-root-direct-children-only-pre-audit-route-then-final-route-plus-independent-auditor"
    )
    assert schema["route_descendants"] == "permitted-and-owned-by-route-orchestrator"
    assert schema["child_process_companions"] == (
        "current-route-returned-implementation-and-refactoring-path-hashes-without-feature-level-reaudit"
    )
    assert schema["auditor_output_rule"] == (
        "provider-only-extracted-output-bytes-equal-consumed-report-bytes"
    )
    assert set(schema["forbidden_fields"]) >= {
        "self_sha256",
        "acceptance_sha256",
        "attempt_process_audit_sha256",
        "attempt_process_report_sha256",
        "post_ready_currentness",
    }
    assert "validate-route-artifact-lineage" in schema["merge_authorization"]


def test_integrated_scope_gate_is_current_model_owned_and_round_aware():
    gate = _section(
        "agents/feature-orchestrator.md", "### Evidence, QA, and integrated-scope gate"
    )
    for value in (
        "${trunk_branch}...${feature_branch}",
        "mechanically dispatchable ad-hoc `gpt-xhigh` child",
        "${planning_dir}/feature-evidence-index.json",
        "${planning_dir}/feature-integrated-review-input.json",
        "integrated_review_input_sha256",
        "current immutable input hash and current feature head",
        "Any substantive feature-branch or trunk-parent change invalidates the input",
        "Before review round two",
        "decision-encoder",
        "${audit_history_path}",
        "Never carry forward an earlier PASS",
    ):
        assert value in gate
    full_text = _read("agents/feature-orchestrator.md")
    assert full_text.index("current integrated-scope PASS") < full_text.index(
        "call `pr-writer`"
    )


def test_integrated_review_inputs_are_created_in_executable_order_and_non_self_referential():
    gate = _section(
        "agents/feature-orchestrator.md", "### Evidence, QA, and integrated-scope gate"
    )
    qa = gate.index("1. Route-scoped evidence")
    pinned_diff = gate.index("2. Freshly fetch and pin trunk and feature refs")
    evidence_index = gate.index(
        "3. Assemble and freeze `${planning_dir}/feature-evidence-index.json`"
    )
    review_input = gate.index(
        "assemble and freeze separately named `${planning_dir}/feature-integrated-review-input.json`"
    )
    reviewer = gate.index("4. Dispatch the reviewer")
    final_evidence = gate.index(
        "5. After PASS, write `${planning_dir}/feature-final-evidence.json`"
    )
    assert qa < pinned_diff < evidence_index < review_input < reviewer < final_evidence

    schema = _fenced_yaml_section(
        "agents/feature-orchestrator.md", "### Integrated Review Input Schema"
    )
    assert schema["schema"] == "feature-integrated-review-input-v1"
    assert schema["path"] == "${planning_dir}/feature-integrated-review-input.json"
    assert {"diff_sha256", "evidence_index_sha256", "qa_sha256", "hashed_inputs"} <= set(
        schema["required_fields"]
    )
    assert set(schema["forbidden_fields"]) == {
        "integrated_scope_verdict",
        "final_evidence",
        "final_pr",
        "self_sha256",
    }
    assert set(schema["binding_consumers"]) == {
        "integrated-scope-reviewer",
        "integrated-scope-verdict",
        "feature-final-evidence",
        "final-pr-handoff",
        "feature-outcome",
    }


def test_terminal_state_is_verified_final_pr_open_handoff_only():
    handoff = _section("agents/feature-orchestrator.md", "### Final PR-open handoff")
    for value in (
        "baseRefName == ${trunk_branch}",
        "headRefName == ${feature_branch}",
        "headRefOid` equal the reviewed feature SHA",
        "FINAL_PR_OPEN_HANDOFF",
        "post_merge_owner",
        "does not wait for or perform the final feature PR merge",
        "close tickets",
        "post-merge outcome",
    ):
        assert value in handoff
    assert "On final PR merge" not in _read("agents/feature-orchestrator.md")
    assert "Succeed only at `FINAL_PR_OPEN_HANDOFF`" in _section(
        "agents/feature-orchestrator.md", "## Stop Conditions"
    )


def test_feature_capabilities_expose_specialist_owners_and_merge_boundaries():
    contract = _operator_contract("feature-orchestrator")
    assert set(contract["must_delegate"]) >= {
        "feature-worktree-management:worktree-operator",
        "ticket-route-execution:implementation-pipeline-orchestrator|refactoring-orchestrator",
        "feature-process-review:process-tree-auditor",
        "final-integrated-scope-review:ad-hoc-gpt-xhigh",
        "second-round-history-encoding:decision-encoder",
        "final-pr-body-authoring:pr-writer",
        "qa-execution:qa_operator",
        "ticket-system-writes:selected-ticket-operator",
    }
    assert "direct-route-pr-verification-and-merge" in contract["may_direct"]
    assert "refactoring-merged-result-consumption-without-pr-merge" in contract["may_direct"]
    assert "feature-owner-merge-of-refactoring-owned-pr" in contract["forbidden_direct"]
    assert "implementation-child-auto-merge" in contract["forbidden_direct"]
    assert "coordinator-direct-ticket-api-write" in contract["forbidden_direct"]
    assert "direct-route-pr-merges-into-feature-branch" in contract["side_effects"]
    assert "final-feature-pr-body-authoring-creation-and-verification" in contract[
        "side_effects"
    ]


def test_implementation_base_is_explicit_for_every_caller():
    contract = _operator_contract("implementation-pipeline-orchestrator")
    base_input = _input(contract, "base_branch")
    assert base_input["required"] is True
    assert base_input["default_source"] == "caller"
    defaults = contract["defaults"]
    assert isinstance(defaults, list)
    assert not any(item["name"] == "base_branch" for item in defaults)

    text = _read("agents/implementation-pipeline-orchestrator.md")
    assert "BLOCKED:invalid-base-branch" in text
    assert "do not derive or fall back to `main`" in text
    assert "required caller-owned WU parent" in text


def test_feature_issue_only_boundary_preserves_standalone_cold_start_contracts():
    implementation = _operator_contract("implementation-pipeline-orchestrator")
    refactoring = _operator_contract("refactoring-orchestrator")
    assert _input(implementation, "wu_brief_path")["required"] is False
    assert _input(refactoring, "wu_brief_path")["required"] is False
    assert "used to create a ticket" in _input(implementation, "wu_brief_path")[
        "description"
    ]
    assert "Canonical WU brief path" in _input(refactoring, "wu_brief_path")[
        "description"
    ]
    feature_schema = _section("agents/feature-orchestrator.md", "## Route Record Schema")
    assert "standalone implementation-pipeline and refactoring callers retain" in feature_schema


def test_implementation_contract_covers_every_entry_mode_input_and_default():
    contract = _operator_contract("implementation-pipeline-orchestrator")
    input_names = {item["name"] for item in contract["inputs"]}
    assert input_names == {
        "jira_issue_key",
        "linear_issue_key",
        "wu_brief_path",
        "wu_brief_context_path",
        "ticket_system",
        "jira_url",
        "jira_project",
        "jira_account_email",
        "linear_team_key",
        "linear_project_id",
        "repo_root",
        "worktree_path",
        "scratch_dir",
        "planning_dir",
        "audit_history_path",
        "pipeline_entry_mode",
        "audit_workflow_path",
        "audit_target_type",
        "audit_target_paths",
        "audit_target_manifest",
        "audit_target_ref",
        "design_patterns_ref",
        "operator_format_ref",
        "audit_slug",
        "audit_report_bundle_path",
        "existing_review_bundle_path",
        "existing_review_bundle_schema",
        "reviewed_target_paths",
        "reviewed_target_ref",
        "current_target_ref",
        "review_staleness_policy",
        "review_staleness_fallback",
        "proposer_fix_scope",
        "workflow_file",
        "run_artifacts",
        "runtime_artifacts_path",
        "process_tree_report_path",
        "expected_process_path",
        "root_invocation_uuid",
        "generated_report_timestamp",
        "tickets_first_variant",
        "branch_name",
        "base_branch",
        "predecessor_session_manifest_path",
        "models_dir",
        "skip_problem_map_gate",
        "auto_merge_after_phase_9",
        "route_attempt_number",
        "local_coverage_command",
    }
    default_names = {item["name"] for item in contract["defaults"]}
    assert default_names <= input_names
    assert {
        "audit_workflow_path",
        "existing_review_bundle_schema",
        "review_staleness_policy",
        "review_staleness_fallback",
        "operator_format_ref",
        "design_patterns_ref",
    } <= default_names
    optional_table = _section(
        "agents/implementation-pipeline-orchestrator.md", "## Optional Inputs"
    )
    for name in (
        "reviewed_target_paths",
        "reviewed_target_ref",
        "current_target_ref",
        "proposer_fix_scope",
        "workflow_file",
        "run_artifacts",
        "runtime_artifacts_path",
        "process_tree_report_path",
        "expected_process_path",
        "root_invocation_uuid",
        "generated_report_timestamp",
    ):
        assert f"`{name}`" in optional_table

    coverage_command = _input(contract, "local_coverage_command")
    assert coverage_command["required"] is False
    assert "blocks before Phase 8 fanout" in coverage_command["description"]
    assert "BLOCKED:missing-local-coverage-command" in coverage_command["description"]


def test_tickets_first_variant_is_contractual_migration_noop():
    contract = _operator_contract("implementation-pipeline-orchestrator")
    description = _input(contract, "tickets_first_variant")["description"]
    assert "Migration-only no-op" in description
    assert "does not add a Phase 8.5 gate" in description
    body = _section(
        "agents/implementation-pipeline-orchestrator.md", "## Optional Inputs"
    )
    assert "removed/no-op migration-compatible boolean" in body
    assert "never inserts a Phase 8.5 gate" in body


def test_implementation_contract_declares_destructive_effects_and_outcomes():
    contract = _operator_contract("implementation-pipeline-orchestrator")
    assert {
        "git-worktree-create",
        "git-worktree-delete",
        "git-hard-reset-wu-branch",
        "git-force-push-with-lease-wu-branch",
        "git-local-branch-delete",
        "git-remote-branch-delete",
        "git-push-origin",
        "gh-pr-create",
        "gh-pr-ready-when-auto-merge-enabled",
        "gh-pr-squash-merge-when-auto-merge-enabled",
    } <= set(contract["side_effects"])
    success = contract["outputs"][0]["success_shape"]
    for value in (
        "VERIFIED_DRAFT_PR",
        "VERIFIED_MERGED",
        "ticket-operation-expected-context-v1 path/hash",
        "ticket-operation-result-v1 path/hash",
        "Phase 4/6/8 process-proof paths/hashes",
        "boolean is_draft",
        "phase_8_reviewed_is_draft",
        "phase_8_reviewed_base_sha",
        "phase_8_reviewed_head_sha",
        "final Phase 9 equality result",
        "pr_open_base_sha",
        "pre_merge_base_sha equal to the Phase 8 reviewed base when captured",
        "merge_sha",
        "refreshed remote base SHA",
        "merge reachability proof",
    ):
        assert value in success


def test_phase_7_acquires_one_verified_pr_before_coderabbit():
    phase_7 = _section(
        "agents/implementation-pipeline-orchestrator.md",
        "#### Draft PR acquisition and single CodeRabbit review",
    )
    for value in (
        "agents -a pr-writer",
        "gh pr create --draft --base ${base_branch} --head ${branch_name}",
        "${scratch_dir}/pr-url.txt",
        "${scratch_dir}/pr-number.txt",
        "URL/number/state/isDraft/baseRefName/baseRefOid/headRefName/headRefOid",
        "Require OPEN draft state",
        "exact branch names",
        "baseRefOid == base_sha",
        "headRefOid == head_sha",
        "pr_open_base_sha=base_sha",
        "pre_merge_base_sha=null",
        "coderabbit_review_driver.py is-enabled",
    ):
        assert value in phase_7
    assert phase_7.index("agents -a pr-writer") < phase_7.index(
        "coderabbit_review_driver.py is-enabled"
    )
    assert phase_7.index("${scratch_dir}/pr-number.txt") < phase_7.index(
        "coderabbit_review_driver.py review-loop"
    )
    for value in (
        "exactly one CodeRabbit review",
        "single_review_completion",
        "must not request a follow-up review",
    ):
        assert value in phase_7
    assert "starts incremental follow-up generations" not in phase_7
    assert "unchanged-head re-triggers" not in phase_7
    pr_writer = _section("agents/pr-writer.md", "## Procedure")
    assert "merge-base --is-ancestor <sha> ${base_sha}" in pr_writer
    assert "merge-base --is-ancestor <sha> origin/main" not in pr_writer


def test_phase_0_records_real_branch_out_provenance():
    phase_0 = _section(
        "agents/implementation-pipeline-orchestrator.md", "### Phase 0 — Bootstrap"
    )
    fetch = "fetch origin refs/heads/${base_branch}:refs/remotes/origin/${base_branch}"
    assert phase_0.index(fetch) < phase_0.index("resolved_base_sha_at_spawn")
    assert phase_0.index("resolved_base_sha_at_spawn") < phase_0.index(
        "worktree add ${worktree_path}"
    )
    assert "git merge-base --fork-point ${verified_remote_base_ref} HEAD" in phase_0
    assert "git merge-base --all ${verified_remote_base_ref} HEAD" in phase_0
    assert "Require exactly one commit that is an ancestor of both" in phase_0
    assert "BLOCKED:ambiguous-worktree-provenance" in phase_0
    assert "never record the current base tip as an existing worktree's branch-out SHA" in phase_0


def test_non_main_rebase_drift_requires_target_delta():
    gate = _section(
        "agents/implementation-pipeline-orchestrator.md", "## Rebase Verification Gate"
    )
    drift_start = gate.index("5. Check #4, drift check:")
    drift_end = gate.index("6. Write `${planning_dir}", drift_start)
    drift = gate[drift_start:drift_end]
    assert "When `${base_branch}` resolves to any non-`main` target" in drift
    assert "choose `${bundle}/target-delta.patch`" in drift
    assert "`${bundle}/main-delta.patch` is not a presence-based fallback" in drift
    assert "target SHA equal to the resolved base commit" in drift
    assert "BLOCKED:rebase-delta-target-mismatch" in drift
    assert "main-delta.patch` when present, otherwise" not in drift


def test_phase_9_captures_true_pre_merge_base_and_refreshes_remote():
    phase_9 = _section(
        "agents/implementation-pipeline-orchestrator.md",
        "### Phase 9 — Verified PR Outcome",
    )
    assert "Phase 9 must not call `gh pr create`" in phase_9
    assert "never copy `pr_open_base_sha`" in phase_9
    fetch = "git fetch origin refs/heads/${base_branch}:refs/remotes/origin/${base_branch}"
    capture = "freshly_fetched_base_sha=$(git rev-parse refs/remotes/origin/${base_branch}^{commit})"
    reread = "perform one provider capture of the exact PR URL/number"
    validate = "--context implementation-phase-9-pre-merge"
    persist = "assign `pre_merge_base_sha=${freshly_fetched_base_sha}`"
    merge = 'gh pr merge --repo "${repo}" --squash "${pr_url}"'
    assert phase_9.index(fetch) < phase_9.index(capture)
    assert phase_9.index(capture) < phase_9.index(reread)
    assert phase_9.index(reread) < phase_9.index(validate)
    assert phase_9.index(validate) < phase_9.index(persist)
    assert phase_9.index(persist) < phase_9.index(merge)
    assert phase_9.count(fetch) >= 2
    for value in (
        "phase_8_reviewed_base_sha",
        "phase_8_reviewed_head_sha",
        "phase_8_reviewed_is_draft=true",
        "baseRefOid == freshly_fetched_base_sha == phase_8_reviewed_base_sha",
        "headRefOid == freshly_fetched_head_sha == phase_8_reviewed_head_sha",
        "leaves `pre_merge_base_sha=null`",
        "reruns every parent-sensitive Phase 8 gate",
        "BLOCKED:ready-state-restoration-failed",
        "BLOCKED:merge-attempt-started",
    ):
        assert value in phase_9
    assert "post_merge_base_sha" in phase_9
    assert "git merge-base --is-ancestor ${merge_sha}" in phase_9
    assert "first parent equals the persisted `pre_merge_base_sha`" in phase_9


@pytest.mark.parametrize(
    (
        "immediate",
        "fetched_base_sha",
        "fetched_head_sha",
        "expected_status",
        "failed_check",
    ),
    [
        (
            _provider_bundle(base_sha="a1" * 20),
            "a1" * 20,
            "b0" * 20,
            "STALE_CURRENTNESS",
            "fetched_base_equals_reviewed",
        ),
        (
            _provider_bundle(base_name="retargeted/base"),
            "a0" * 20,
            "b0" * 20,
            "STALE_CURRENTNESS",
            "base_name_equal",
        ),
        (
            _provider_bundle(),
            "a0" * 20,
            "b0" * 20,
            "READY",
            None,
        ),
    ],
    ids=["post-ready-base-advance", "provider-retarget-same-head", "exact-unchanged"],
)
def test_production_phase_9_currentness_validator_rejects_movement(
    immediate: dict[str, Any],
    fetched_base_sha: str,
    fetched_head_sha: str,
    expected_status: str,
    failed_check: str | None,
):
    decision = validate_pr_currentness(
        _provider_bundle(),
        immediate,
        fetched_base_sha,
        fetched_head_sha,
        context="implementation-phase-9-pre-merge",
    )
    assert decision["status"] == expected_status
    assert decision["final_equality_result"] == (
        "PASS" if expected_status == "READY" else "FAIL"
    )
    if failed_check is not None:
        assert decision["equality"][failed_check] is False
        assert decision["required_action"] == (
            "perform-no-ready-or-merge-side-effect-and-rerun-parent-sensitive-gates"
        )


def test_currentness_result_schema_and_required_wrapper_record_fetched_head():
    reviewed = _provider_bundle()
    decision = require_pr_currentness(
        reviewed,
        reviewed,
        reviewed["base_ref_oid"],
        reviewed["head_ref_oid"],
        context="implementation-phase-9-entry",
        expected_draft=True,
    )

    assert set(decision) == {
        "schema",
        "context",
        "expected_draft",
        "status",
        "final_equality_result",
        "reviewed",
        "immediate",
        "fetched_base_sha",
        "fetched_head_sha",
        "equality",
        "errors",
        "required_action",
    }
    assert decision["schema"] == "pr-currentness-validation-v1"
    assert decision["fetched_head_sha"] == reviewed["head_ref_oid"]
    assert decision["equality"]["provider_head_equals_fetched"] is True
    assert decision["equality"]["fetched_head_equals_reviewed"] is True


def test_every_merge_owner_supplies_fresh_base_and_head_to_currentness():
    feature = _section(
        "agents/feature-orchestrator.md", "#### Direct implementation route"
    )
    implementation = _section(
        "agents/implementation-pipeline-orchestrator.md",
        "### Phase 9 — Verified PR Outcome",
    )
    refactoring = _section("agents/refactoring-orchestrator.md", "## Procedure")

    for text, expected_calls in ((feature, 2), (implementation, 3), (refactoring, 1)):
        assert text.count("validate-pr-currentness") == expected_calls
        assert text.count("--fetched-base-sha") == expected_calls
        assert text.count("--fetched-head-sha") == expected_calls
    assert '--match-head-commit "${reviewed_head_oid}"' in feature
    assert '--match-head-commit "${phase_8_reviewed_head_sha}"' in implementation
    assert '--match-head-commit "${pre_merge_observed_head_sha}"' in refactoring


_MERGE_CURRENTNESS_CONTEXTS = (
    "feature-direct-post-ready",
    "refactoring-pre-merge",
    "implementation-phase-9-pre-merge",
)


@pytest.mark.parametrize("context", _MERGE_CURRENTNESS_CONTEXTS)
@pytest.mark.parametrize(
    ("immediate", "fetched_base_sha", "fetched_head_sha", "failed_checks"),
    [
        (
            _provider_bundle(is_draft=False),
            "a0" * 20,
            "b1" * 20,
            {"provider_head_equals_fetched", "fetched_head_equals_reviewed"},
        ),
        (
            _provider_bundle(head_sha="b1" * 20, is_draft=False),
            "a0" * 20,
            "b0" * 20,
            {"provider_head_equals_fetched"},
        ),
        (
            _provider_bundle(is_draft=False),
            "b0" * 20,
            "a0" * 20,
            {
                "provider_base_equals_fetched",
                "fetched_base_equals_reviewed",
                "provider_head_equals_fetched",
                "fetched_head_equals_reviewed",
            },
        ),
    ],
    ids=[
        "provider-reviewed-equal-fetched-head-moved",
        "provider-head-moved",
        "fetched-base-head-cross-associated",
    ],
)
def test_merge_owner_currentness_rejects_every_head_fetch_inequality(
    context: str,
    immediate: dict[str, Any],
    fetched_base_sha: str,
    fetched_head_sha: str,
    failed_checks: set[str],
):
    decision = validate_pr_currentness(
        _provider_bundle(),
        immediate,
        fetched_base_sha,
        fetched_head_sha,
        context=context,
        expected_draft=False,
    )

    assert decision["status"] == "STALE_CURRENTNESS"
    assert decision["final_equality_result"] == "FAIL"
    assert decision["fetched_base_sha"] == fetched_base_sha
    assert decision["fetched_head_sha"] == fetched_head_sha
    assert failed_checks <= {
        key for key, value in decision["equality"].items() if value is False
    }


@pytest.mark.parametrize("context", _MERGE_CURRENTNESS_CONTEXTS)
def test_merge_owner_currentness_cli_rejects_fetched_head_movement(
    tmp_path: Path, context: str
):
    reviewed = _provider_bundle()
    immediate = _provider_bundle(is_draft=False)
    reviewed_path = tmp_path / f"{context}-reviewed.json"
    immediate_path = tmp_path / f"{context}-immediate.json"
    output_path = tmp_path / f"{context}-currentness.json"
    _write_json_fixture(reviewed_path, reviewed)
    _write_json_fixture(immediate_path, immediate)

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-pr-currentness",
            "--reviewed",
            str(reviewed_path),
            "--immediate",
            str(immediate_path),
            "--fetched-base-sha",
            reviewed["base_ref_oid"],
            "--fetched-head-sha",
            "b1" * 20,
            "--context",
            context,
            "--expected-draft",
            "false",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    decision = json.loads(output_path.read_text(encoding="utf-8"))
    assert decision["status"] == "STALE_CURRENTNESS"
    assert decision["fetched_head_sha"] == "b1" * 20
    assert decision["equality"]["provider_head_equals_fetched"] is False
    assert decision["equality"]["fetched_head_equals_reviewed"] is False


def test_phase_8_declared_provider_keys_pass_the_phase_9_consumer(tmp_path: Path):
    phase_8_schema = _fenced_yaml_section(
        "agents/implementation-pipeline-orchestrator.md",
        "### Phase 8 — apply-gate-set PR-review Gates + Process-tree Audit #3",
    )
    fields = phase_8_schema["phase_8_reviewed_pr_fields"]
    required_values = phase_8_schema["phase_8_reviewed_pr_required_values"]
    provider_capture = _provider_bundle(is_draft=True)
    reviewed_artifact = {field: provider_capture[field] for field in fields}

    assert fields == [
        "pr_url",
        "pr_number",
        "state",
        "is_draft",
        "base_ref_name",
        "base_ref_oid",
        "head_ref_name",
        "head_ref_oid",
    ]
    assert required_values == {"state": "OPEN", "is_draft": True}
    assert reviewed_artifact["is_draft"] is True
    reviewed_path = tmp_path / "phase-8-reviewed-pr.json"
    immediate_path = tmp_path / "phase-9-provider.json"
    output_path = tmp_path / "phase-9-currentness.json"
    _write_json_fixture(reviewed_path, reviewed_artifact)
    _write_json_fixture(immediate_path, reviewed_artifact)
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-pr-currentness",
            "--reviewed",
            str(reviewed_path),
            "--immediate",
            str(immediate_path),
            "--fetched-base-sha",
            reviewed_artifact["base_ref_oid"],
            "--fetched-head-sha",
            reviewed_artifact["head_ref_oid"],
            "--context",
            "implementation-phase-9-entry",
            "--expected-draft",
            "true",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    decision = json.loads(output_path.read_text(encoding="utf-8"))
    assert decision["status"] == "READY"
    assert decision["final_equality_result"] == "PASS"

    non_draft_reviewed = deepcopy(reviewed_artifact)
    non_draft_reviewed["is_draft"] = False
    rejected = validate_pr_currentness(
        non_draft_reviewed,
        non_draft_reviewed,
        non_draft_reviewed["base_ref_oid"],
        non_draft_reviewed["head_ref_oid"],
        context="implementation-phase-9-entry",
        expected_draft=False,
    )
    assert rejected["status"] == "STALE_CURRENTNESS"
    assert rejected["equality"]["reviewed_draft_snapshot"] is False


_READY_STATE_OWNER_OUTCOMES = (
    ("feature-direct-merge", "REPLAY_REQUIRED"),
    ("implementation-auto-merge", "RETURN_TO_PHASE_8"),
    ("refactoring-owner-merge", "RETURN_TO_PHASE_8"),
)


@pytest.mark.parametrize(("owner", "expected_status"), _READY_STATE_OWNER_OUTCOMES)
def test_post_ready_base_and_head_movement_restores_draft_for_replay(
    owner: str, expected_status: str
):
    promoted = _provider_bundle(base_sha="c0" * 20, head_sha="d0" * 20, is_draft=False)
    restored = deepcopy(promoted)
    restored["is_draft"] = True

    decision = validate_ready_state_restoration(
        promoted,
        restored,
        promoted["base_ref_oid"],
        promoted["head_ref_oid"],
        owner=owner,
        undo_attempted=True,
        undo_exit_code=0,
        requery_succeeded=True,
        merge_attempt_started=False,
    )

    assert decision["status"] == expected_status
    assert decision["replay_permitted"] is True
    assert decision["identity_equal"] is True
    assert decision["restored"]["is_draft"] is True


@pytest.mark.parametrize(("owner", "_"), _READY_STATE_OWNER_OUTCOMES)
def test_post_ready_restoration_rejects_wrong_identity(owner: str, _: str):
    promoted = _provider_bundle(is_draft=False)
    restored = _provider_bundle(is_draft=True)
    restored["pr_number"] = 261

    decision = validate_ready_state_restoration(
        promoted,
        restored,
        restored["base_ref_oid"],
        restored["head_ref_oid"],
        owner=owner,
        undo_attempted=True,
        undo_exit_code=0,
        requery_succeeded=True,
        merge_attempt_started=False,
    )

    assert decision["status"] == "BLOCKED:ready-state-restoration-failed"
    assert decision["replay_permitted"] is False
    assert decision["identity_equal"] is False


@pytest.mark.parametrize(("owner", "_"), _READY_STATE_OWNER_OUTCOMES)
def test_post_ready_restoration_rejects_undo_failure(owner: str, _: str):
    promoted = _provider_bundle(is_draft=False)

    decision = validate_ready_state_restoration(
        promoted,
        None,
        None,
        None,
        owner=owner,
        undo_attempted=True,
        undo_exit_code=1,
        requery_succeeded=False,
        merge_attempt_started=False,
    )

    assert decision["status"] == "BLOCKED:ready-state-restoration-failed"
    assert decision["replay_permitted"] is False
    assert any("ready undo must exit zero" in error for error in decision["errors"])


@pytest.mark.parametrize(("owner", "_"), _READY_STATE_OWNER_OUTCOMES)
def test_merge_attempt_started_is_explicitly_non_replayable(owner: str, _: str):
    decision = validate_ready_state_restoration(
        _provider_bundle(is_draft=False),
        None,
        None,
        None,
        owner=owner,
        undo_attempted=False,
        undo_exit_code=None,
        requery_succeeded=False,
        merge_attempt_started=True,
    )

    assert decision["status"] == "BLOCKED:merge-attempt-started"
    assert decision["undo_permitted"] is False
    assert decision["replay_permitted"] is False


@pytest.mark.parametrize(
    ("relative_path", "heading", "owner"),
    [
        (
            "agents/feature-orchestrator.md",
            "#### Direct implementation route",
            "feature-direct-merge",
        ),
        (
            "agents/implementation-pipeline-orchestrator.md",
            "### Phase 9 — Verified PR Outcome",
            "implementation-auto-merge",
        ),
        (
            "agents/refactoring-orchestrator.md",
            "## Procedure",
            "refactoring-owner-merge",
        ),
    ],
)
def test_all_merge_owners_declare_restore_before_replay_and_no_undo_after_merge(
    relative_path: str, heading: str, owner: str
):
    section = _section(relative_path, heading)
    for value in (
        "gh pr ready --undo",
        "freshly fetch both exact",
        "freshly re-query",
        "validate-ready-state-restoration",
        f"owner={owner}",
        "merge_attempt_started=false",
        "BLOCKED:ready-state-restoration-failed",
        "BLOCKED:merge-attempt-started",
        "replay_permitted=false",
    ):
        assert value in section
    assert "no `gh pr ready --undo` is permitted" in section


def test_phase_9_terminal_outcomes_replace_phase_10():
    workflow = _read("workflows/implementation-pipeline.md")
    assert "## Phase 10" not in workflow
    phase_map = _section("workflows/implementation-pipeline.md", "## Phase Map")
    assert "Phase 8 -> Phase 9`" in phase_map
    assert "Phase 9 -> Phase 10" not in phase_map
    phase_9 = _section(
        "workflows/implementation-pipeline.md", "## Phase 9 - Verified PR Outcome"
    )
    for value in (
        "pre_merge_base_sha",
        "pr_open_base_sha",
        "tiered-approval.md",
    ):
        assert value in phase_9
    workflow_contract = _workflow_dispatch_contract("implementation-pipeline")
    workflow_outcomes = "\n".join(workflow_contract["outputs"])
    assert "VERIFIED_DRAFT_PR" in workflow_outcomes
    assert "VERIFIED_MERGED" in workflow_outcomes
    ownership = _section("conventions/gate-ownership.md", "## Gate-owner table")
    assert "Phase 9 verified PR outcome" in ownership
    assert "there is no Phase 10" in ownership


def test_test_audit_validates_and_uses_explicit_base_ref_everywhere():
    contract = _operator_contract("test-audit-gate")
    base_input = _input(contract, "base_ref")
    assert base_input["required"] is False
    assert base_input["default_source"] == "derived"
    assert "required caller-owned base branch" in base_input["description"]
    base_branch_input = _input(contract, "base_branch")
    assert base_branch_input["required"] is True
    assert base_branch_input["default_source"] == "caller"
    assert not any(item["name"] == "base_ref" for item in contract["defaults"])
    prepare = _section("agents/test-audit-gate.md", "### 1. Prepare Diff Inputs")
    coverage = _between(
        "agents/test-audit-gate.md",
        "### 6. Generate Coverage Locally in `pr-review` Mode Only\n",
        "### 7. Launch Three Parallel Sub-Agent Invocations\n",
    )
    for section in (prepare, coverage):
        assert 'git rev-parse --verify "${base_ref}^{commit}"' in section
        assert "BLOCKED:invalid-base-ref" in section
        assert 'git merge-base "$resolved_head_ref" "$resolved_base_ref"' in section
        assert "BLOCKED:pinned-review-identity-mismatch" in section
        assert "origin/main" not in section
    assert '${base_branch+x}' in prepare
    assert 'derived_base_ref="refs/remotes/origin/${base_branch}"' in prepare
    assert "BLOCKED:invalid-base-branch" in prepare
    assert 'if [ "$mode" = "pr-review" ]' in prepare
    assert '${head_ref//[[:space:]]/}' in prepare
    assert "BLOCKED:missing-pinned-head-ref" in prepare
    assert prepare.index("BLOCKED:missing-pinned-head-ref") < prepare.index(
        'git rev-parse --verify "${head_ref:-HEAD}^{commit}"'
    )
    assert 'git worktree add --detach "$base_worktree" "$merge_base_sha"' in coverage
    assert "base-coverage-summary.json" in coverage
    assert "main-coverage-summary.json" not in coverage
    assert "BLOCKED:coverage-worktree-path-exists" in coverage
    assert 'git worktree add --detach "$head_worktree" "$head_sha" || {' in coverage
    assert (
        'git worktree add --detach "$base_worktree" "$merge_base_sha" || {'
        in coverage
    )
    assert "BLOCKED:head-local-coverage-command-failed" in coverage
    assert "BLOCKED:base-local-coverage-command-failed" in coverage
    assert "BLOCKED:head-coverage-summary-copy-failed" in coverage
    assert "BLOCKED:head-lcov-copy-failed" in coverage
    assert "BLOCKED:base-coverage-summary-copy-failed" in coverage
    assert "BLOCKED:base-lcov-copy-failed" in coverage


def test_test_audit_process_prompt_and_binding_use_the_same_absolute_operator():
    process = _section(
        "agents/test-audit-gate.md",
        "### 7. Launch Three Parallel Sub-Agent Invocations",
    )
    operator_path = "${repo_root}/agents/test-audit-gate.md"
    assert f"operator_file={operator_path}" in process
    assert f"`report_identity` names `{operator_path}`" in process
    assert "`operator_artifact.path` names that same canonical absolute operator path" in process
    assert "`mode` equals exact `blocking`" in process
    assert "operator_file=agents/test-audit-gate.md" not in process


def test_test_audit_coverage_command_hash_is_mode_conditional(tmp_path: Path):
    fixture = _test_audit_result_fixture(tmp_path)

    implementation = deepcopy(fixture["result"])
    implementation["mode"] = "implementation"
    implementation.pop("local_coverage_command_sha256")
    accepted = validate_test_audit_result(
        implementation,
        expected_root_uuid=fixture["root_uuid"],
        expected_base_sha=fixture["base_sha"],
        expected_head_sha=fixture["head_sha"],
    )
    assert accepted["status"] == "VALID", accepted["errors"]

    missing_pr_review_hash = deepcopy(fixture["result"])
    missing_pr_review_hash.pop("local_coverage_command_sha256")
    missing = validate_test_audit_result(missing_pr_review_hash)
    assert missing["status"] == "INVALID"
    assert any("selected mode" in error for error in missing["errors"])

    invented_null_hash = deepcopy(implementation)
    invented_null_hash["local_coverage_command_sha256"] = None
    invented = validate_test_audit_result(invented_null_hash)
    assert invented["status"] == "INVALID"
    assert any("local_coverage_command_sha256" in error for error in invented["errors"])

    schema = _section("agents/test-audit-gate.md", "### 8a. Test Audit Result Schema")
    assert "implementation: optional-lowercase-sha256-only-when-command-was-supplied" in schema
    assert "local_coverage_command_sha256" not in schema.split("conditional_fields:", 1)[0]


def test_apply_gate_process_tree_report_is_required_end_to_end():
    contract = _operator_contract("apply-gate-set")
    report_input = _input(contract, "process_tree_report_path")
    assert report_input["required"] is True
    assert report_input["default_source"] == "caller"
    output = contract["outputs"][0]
    assert "${process_tree_report_path}" in output["wrote_lines"]
    assert "${audit_history_path}" in output["wrote_lines"]
    assert "required process_tree_report_path" in output["success_shape"]

    output_contract = _section("agents/apply-gate-set.md", "## Output contract")
    assert "`process_tree_report_path`\n" in output_contract
    assert "explicit not-applicable reason" not in output_contract
    assert "the process-tree report is PASS" in output_contract
    workflow = _read("workflows/apply-gate-set.md")
    assert "- Required independent process-tree report." in workflow


def test_pr_review_requires_all_six_caller_identity_fields_before_provider_verification():
    contract = _operator_contract("pr-review-operator")
    identity_fields = (
        "base_branch",
        "base_ref",
        "base_sha",
        "head_branch",
        "head_ref",
        "head_sha",
    )
    for name in identity_fields:
        field = _input(contract, name)
        assert field["required"] is True
        assert field["default_source"] == "caller"

    phase_0 = _between(
        "agents/pr-review-operator.md",
        "### Phase 0: Fetch the PR\n",
        "### Phase 1: Risk Assessment (3x parallel)\n",
    )
    blocker = "BLOCKED:missing-pr-review-caller-identity"
    assert blocker in phase_0
    assert phase_0.index(blocker) < phase_0.index("gh pr view")
    for name in identity_fields:
        assert f"${{{name}+x}}" in phase_0
        assert f"${{{name}//[[:space:]]/}}" in phase_0
    required_inputs = _section("agents/pr-review-operator.md", "## Required Inputs")
    assert "provider data verifies every value" in required_inputs
    assert "never supplies or replaces a missing caller field" in required_inputs


def test_pr_review_requires_non_blank_coverage_command_before_provider_verification():
    phase_0 = _between(
        "agents/pr-review-operator.md",
        "### Phase 0: Fetch the PR\n",
        "### Phase 1: Risk Assessment (3x parallel)\n",
    )
    blocker = "BLOCKED:missing-local-coverage-command"
    assert blocker in phase_0
    assert phase_0.index(blocker) < phase_0.index("gh pr view")
    assert "${local_coverage_command+x}" in phase_0
    assert "${local_coverage_command//[[:space:]]/}" in phase_0


def test_pr_review_rejects_invalid_runtime_identity_before_provider_access():
    phase_0 = _between(
        "agents/pr-review-operator.md",
        "### Phase 0: Fetch the PR\n",
        "### Phase 1: Risk Assessment (3x parallel)\n",
    )
    blocker = "BLOCKED:runtime-invocation-identity-unavailable"
    assert blocker in phase_0
    assert phase_0.index(blocker) < phase_0.index("gh pr view")
    assert phase_0.index(blocker) < phase_0.index("init-pr-review-run")
    assert "object_pairs_hook=unique_object" in phase_0
    assert "str(uuid.UUID(invocation_uuid)) != invocation_uuid" in phase_0


def test_pr_review_rejects_non_open_pr_before_run_allocation():
    phase_0 = _between(
        "agents/pr-review-operator.md",
        "### Phase 0: Fetch the PR\n",
        "### Phase 1: Risk Assessment (3x parallel)\n",
    )
    state_check = 'if [ "$PR_STATE" != "OPEN" ]; then'
    assert 'jq -r .state' in phase_0
    assert state_check in phase_0
    assert "BLOCKED:pr-not-reviewable" in phase_0
    assert phase_0.index(state_check) < phase_0.index("init-pr-review-run")


def test_phase_8_transports_base_through_mandatory_test_audit_providers():
    phase_8 = _section(
        "agents/implementation-pipeline-orchestrator.md",
        "### Phase 8 — apply-gate-set PR-review Gates + Process-tree Audit #3",
    )
    for value in (
        "root_invocation_uuid=${implementation_invocation_uuid}",
        "base_branch",
        "base_ref",
        "base_sha",
        "head_branch=${branch_name}",
        "head_ref",
        "head_sha",
        "local_coverage_command",
    ):
        assert value in phase_8
    assert "test-audit" in phase_8

    apply_gate = _section("agents/apply-gate-set.md", "## Procedure")
    assert "`pr-review-operator` and `test-audit-gate` prompts include the complete exact base/head branch/ref/SHA bundle" in apply_gate
    assert "`local_coverage_command`" in apply_gate

    pr_review = _between(
        "agents/pr-review-operator.md",
        "### Phase 3: Test-Audit Gate\n",
        "### Phase 4: PR Decomposition Review (2x parallel)\n",
    )
    for value in (
        "- base_branch: $BASE_BRANCH",
        "- base_ref: $BASE_REF",
        "- base_sha: $BASE_SHA",
        "- head_branch: $HEAD_BRANCH",
        "- head_ref: $HEAD_REF",
        "- head_sha: $HEAD_SHA",
        "- local_coverage_command: ${local_coverage_command}",
    ):
        assert value in pr_review
    pr_fetch = _between(
        "agents/pr-review-operator.md",
        "### Phase 0: Fetch the PR\n",
        "### Phase 1: Risk Assessment (3x parallel)\n",
    )
    assert "baseRefName" in pr_fetch
    assert "init-pr-review-run" in pr_fetch
    assert 'BASE_REF=$(jq -r .base_ref "$RUN_MANIFEST")' in pr_fetch
    assert 'HEAD_REF=$(jq -r .head_ref "$RUN_MANIFEST")' in pr_fetch
    assert 'git -C "$SOURCE_REPO_ROOT" fetch --force origin' in pr_fetch
    assert 'rev-parse "${BASE_REF}^{commit}"' in pr_fetch
    assert 'rev-parse "${HEAD_REF}^{commit}"' in pr_fetch
    assert 'rev-parse HEAD)" = "$HEAD_SHA"' in pr_fetch
    implementation = _read("agents/implementation-pipeline-orchestrator.md")
    assert "OULIPOLY_PARENT_INVOCATION" in implementation
    assert "external runtime-audit target" in implementation


def test_runner_envelope_extraction_writes_only_canonical_provider_payload(
    tmp_path: Path,
):
    log_path = tmp_path / "risk-audit.log"
    output_path = tmp_path / "risk-audit.md"
    payload = "Verdict: PASS\n\n# Canonical provider report\n"
    log_path.write_bytes(
        (REPO_ROOT / "tests/fixtures/runner-success-with-session.txt").read_bytes()
    )

    extraction = extract_provider_payload(log_path, output_path)

    assert output_path.read_text(encoding="utf-8") == payload
    assert output_path.read_text(encoding="utf-8").splitlines()[0] == "Verdict: PASS"
    assert "OULIPOLY_" not in output_path.read_text(encoding="utf-8")
    assert extraction["invocation_uuid"] == _RUNNER_UUID
    assert extraction["log_path"] != extraction["output_path"]
    assert extraction["log_sha256"] == hashlib.sha256(log_path.read_bytes()).hexdigest()
    assert extraction["output_sha256"] == hashlib.sha256(payload.encode()).hexdigest()
    assert extraction["session"]["agent_runner_invocation_id"] == _RUNNER_UUID


def test_agents_cli_declares_production_runner_order_and_optional_session_contract():
    separation = _section(
        "workflows/agents-cli.md", "## Runner Log And Canonical Output Separation"
    )
    invocation = separation.index("exactly one valid invocation marker")
    session = separation.index("at most one optional session marker")
    result = separation.index("exactly one ordered terminal successful result sentinel")
    for value in (
        "immediately after invocation and before payload",
        "agent_runner_invocation_id",
        "duplicate, malformed, misplaced, post-payload",
        "excludes the session marker",
        "OULIPOLY_SESSION",
    ):
        assert value in separation
    assert invocation < session < result
    assert (
        "production runner emits none when session resolution/capture returns `emitted=false`"
        in _read("workflows/agents-cli.md")
    )


def test_runner_envelope_extraction_keeps_declared_marker_free_compatibility(
    tmp_path: Path,
):
    log_path = REPO_ROOT / "tests/fixtures/runner-success-without-session.txt"
    output_path = tmp_path / "canonical.md"

    extraction = extract_provider_payload(log_path, output_path)

    assert output_path.read_text(encoding="utf-8") == (
        "Verdict: PASS\n\n# Canonical provider report\n"
    )
    assert extraction["session"] is None


@pytest.mark.parametrize(
    "fixture_name",
    [
        "runner-session-malformed.txt",
        "runner-session-duplicate.txt",
        "runner-session-identity-mismatch.txt",
        "runner-session-misplaced.txt",
        "runner-session-post-payload.txt",
    ],
    ids=["malformed", "duplicate", "identity-mismatch", "misplaced", "post-payload"],
)
def test_runner_envelope_extraction_rejects_invalid_session_markers(
    tmp_path: Path, fixture_name: str
):
    output_path = tmp_path / "canonical.md"
    output_path.write_text("preserved canonical output\n", encoding="utf-8")

    with pytest.raises(_CONTRACT_MODULE.ContractValidationError):
        extract_provider_payload(REPO_ROOT / "tests/fixtures" / fixture_name, output_path)

    assert output_path.read_text(encoding="utf-8") == "preserved canonical output\n"


@pytest.mark.parametrize(
    "stream",
    [
        _runner_envelope("Verdict: PASS\n").split(b"\n", 1)[1],
        _runner_envelope("Verdict: PASS\n")
        + _runner_envelope("Verdict: PASS\n"),
        _runner_envelope("Verdict: PASS\n").rsplit(b"OULIPOLY_RESULT=", 1)[0],
        b"OULIPOLY_INVOCATION={not-json}\nVerdict: PASS\n"
        b'OULIPOLY_RESULT={"id":"9e69e8cc-616d-4640-bf1d-96f5391b1a2e"}\n',
        b'OULIPOLY_INVOCATION={"source":"fixture-provider","id":"'
        + _RUNNER_UUID.encode()
        + b'"}\nVerdict: PASS\nOULIPOLY_RESULT={not-json}\n',
        _runner_envelope("Verdict: PASS\n").splitlines(keepends=True)[-1]
        + _runner_envelope("Verdict: PASS\n").splitlines(keepends=True)[0]
        + b"Verdict: PASS\n",
        _runner_envelope("Verdict: PASS\n") + b"trailing output\n",
        _runner_envelope("Verdict: PASS\n").replace(
            b"OULIPOLY_RESULT=", b"OULIPOLY_FAILURE="
        ),
        _runner_envelope(
            "Verdict: PASS\n", result_uuid=_SECOND_RUNNER_UUID
        ),
        _runner_envelope(
            "Verdict: PASS\n", status="failed", success=False, exit_code=1
        ),
    ],
    ids=[
        "missing-invocation",
        "duplicate-envelope",
        "missing-result",
        "malformed-invocation",
        "malformed-result",
        "out-of-order",
        "non-terminal-result",
        "failure-sentinel",
        "identity-mismatch",
        "failed-result",
    ],
)
def test_runner_envelope_extraction_rejects_malformed_stream_without_overwrite(
    tmp_path: Path, stream: bytes
):
    log_path = tmp_path / "child.log"
    output_path = tmp_path / "child.md"
    log_path.write_bytes(stream)
    output_path.write_text("preserved canonical output\n", encoding="utf-8")

    with pytest.raises(_CONTRACT_MODULE.ContractValidationError):
        extract_provider_payload(log_path, output_path)

    assert output_path.read_text(encoding="utf-8") == "preserved canonical output\n"


def test_runner_envelope_extraction_rejects_log_output_alias(tmp_path: Path):
    log_path = tmp_path / "child.log"
    stream = _runner_envelope("Verdict: PASS\n")
    log_path.write_bytes(stream)

    with pytest.raises(_CONTRACT_MODULE.ContractValidationError):
        extract_provider_payload(log_path, log_path)

    assert log_path.read_bytes() == stream


def test_test_audit_nested_proof_validator_accepts_exact_independent_fanout(
    tmp_path: Path,
):
    fixture = _test_audit_result_fixture(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-test-audit-result",
            "--result",
            str(fixture["result_path"]),
            "--expected-root-uuid",
            fixture["root_uuid"],
            "--expected-base-sha",
            fixture["base_sha"],
            "--expected-head-sha",
            fixture["head_sha"],
            "--output",
            str(tmp_path / "PR_REVALIDATION.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    decision = json.loads((tmp_path / "PR_REVALIDATION.json").read_text())
    assert decision["status"] == "VALID"
    assert decision["test_audit_invocation_uuid"] == fixture["root_uuid"]
    assert len(fixture["result"]["nested_process_proof"]["child_artifacts"]) == 3


def test_canonical_process_audit_producer_report_interoperates_with_consumers(
    tmp_path: Path,
):
    fixture = _test_audit_result_fixture(tmp_path)
    lines = fixture["audit_report_path"].read_text(encoding="utf-8").splitlines()

    assert lines[0] == "# Process Tree Audit"
    assert lines.index(f"Root invocation UUID: {fixture['root_uuid']}") < lines.index(
        "Verdict: PASS"
    )
    assert len([line for line in lines if line.startswith("Verdict:")]) == 1
    report_validation = validate_process_tree_audit_report(
        fixture["audit_report_path"]
    )
    assert report_validation["status"] == "VALID", report_validation["errors"]
    assert report_validation["verdict"] == "PASS"
    cli_output = tmp_path / "PROCESS_AUDIT_VALIDATION.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-process-tree-audit-report",
            "--report",
            str(fixture["audit_report_path"]),
            "--output",
            str(cli_output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(cli_output.read_text(encoding="utf-8")) == report_validation
    binding = report_validation["binding"]
    assert binding["schema"] == "process-tree-audit-binding-v1"
    assert binding["mode"] == "blocking"
    assert binding["report_identity"] == {
        "schema": "process-tree-audit-report-v1",
        "path": str(fixture["audit_report_path"]),
        "operator_file": str(REPO_ROOT / "agents/test-audit-gate.md"),
    }
    assert "sha256" not in binding["report_identity"]
    nested_validation = validate_test_audit_nested_proof(
        fixture["result"]["nested_process_proof"],
        proof_path=fixture["proof_path"],
    )
    assert nested_validation["status"] == "VALID", nested_validation["errors"]


def test_process_tree_binding_resolves_named_operator_before_comparison(tmp_path: Path):
    fixture = _test_audit_result_fixture(tmp_path)
    report_path = fixture["audit_report_path"]
    binding = validate_process_tree_audit_report(report_path)["binding"]
    operator_alias = REPO_ROOT / "agents" / ".." / "agents" / "test-audit-gate.md"
    assert str(operator_alias) != str(operator_alias.resolve())
    binding["report_identity"]["operator_file"] = str(operator_alias)
    report_path.write_text(
        render_process_tree_audit_report(binding, "PASS"), encoding="utf-8"
    )

    decision = validate_process_tree_audit_report(report_path)

    assert decision["status"] == "VALID", decision["errors"]


def test_process_tree_binding_mode_is_required_and_exact_for_nested_pass(tmp_path: Path):
    missing_fixture = _test_audit_result_fixture(tmp_path / "missing")
    missing_report = missing_fixture["audit_report_path"]
    missing_binding = validate_process_tree_audit_report(missing_report)["binding"]
    missing_binding.pop("mode")
    missing_report.write_text(
        render_process_tree_audit_report(missing_binding, "PASS"), encoding="utf-8"
    )
    missing = validate_process_tree_audit_report(missing_report)
    assert missing["status"] == "INVALID"
    assert any("mode" in error for error in missing["errors"])

    advisory_fixture = _test_audit_result_fixture(tmp_path / "advisory")
    advisory_report = advisory_fixture["audit_report_path"]
    advisory_binding = validate_process_tree_audit_report(advisory_report)["binding"]
    advisory_binding["mode"] = "advisory"
    advisory_report.write_text(
        render_process_tree_audit_report(advisory_binding, "PASS"), encoding="utf-8"
    )
    proof = deepcopy(advisory_fixture["result"]["nested_process_proof"])
    proof["process_tree_audit_sha256"] = hashlib.sha256(
        advisory_report.read_bytes()
    ).hexdigest()
    advisory = validate_test_audit_nested_proof(proof)
    assert advisory["status"] == "INVALID"
    assert "process audit report producer-owned binding mismatch" in advisory["errors"]


def test_process_tree_audit_binding_rejects_changed_decision_inputs(tmp_path: Path):
    fixture = _test_audit_result_fixture(tmp_path)
    report_path = fixture["audit_report_path"]
    binding = validate_process_tree_audit_report(report_path)["binding"]
    history_path = tmp_path / "audit-history.md"
    history_path.write_text("# Audit History\n", encoding="utf-8")
    binding["audit_history"] = {
        "path": str(history_path),
        "sha256": hashlib.sha256(history_path.read_bytes()).hexdigest(),
    }
    report_path.write_text(
        render_process_tree_audit_report(binding, "PASS"), encoding="utf-8"
    )
    assert validate_process_tree_audit_report(report_path)["status"] == "VALID"

    history_path.write_text("# Replaced Audit History\n", encoding="utf-8")
    history_result = validate_process_tree_audit_report(report_path)
    assert history_result["status"] == "INVALID"
    assert "process audit history hash mismatch" in history_result["errors"]

    binding["audit_history"]["sha256"] = hashlib.sha256(
        history_path.read_bytes()
    ).hexdigest()
    binding["operator_artifact"]["sha256"] = "0" * 64
    report_path.write_text(
        render_process_tree_audit_report(binding, "PASS"), encoding="utf-8"
    )
    operator_result = validate_process_tree_audit_report(report_path)
    assert operator_result["status"] == "INVALID"
    assert "process audit operator artifact hash mismatch" in operator_result["errors"]


def test_process_tree_auditor_declares_one_canonical_report_and_binding_schema():
    output = _between(
        "agents/process-tree-auditor.md", "## Output Format\n", "Final stdout:\n"
    )
    header = output.index("# Process Tree Audit")
    identities = [
        output.index("Operator/workflow: <operator_file>"),
        output.index("Root invocation UUID: <uuid>"),
        output.index("Subtree root UUID: <uuid|none>"),
        output.index("Trace JSON: <process_tree_path>"),
        output.index("Expected process: <expected_process>"),
    ]
    verdict = output.index("Verdict: <PASS|FAIL|NEEDS_INPUT>")
    binding = output.index("PROCESS_TREE_AUDIT_BINDING_JSON=<canonical-json")
    assert header < identities[0] < identities[1] < identities[2]
    assert identities[2] < identities[3] < identities[4] < verdict < binding

    machine_binding = _between(
        "agents/process-tree-auditor.md",
        "## Canonical Machine Binding\n",
        "## Non-Negotiables\n",
    )
    for field in (
        '"mode"',
        '"report_identity"',
        '"operator_artifact"',
        '"audit_history"',
        '"root_invocation_uuid"',
        '"subtree_root_uuid"',
        '"expected_process"',
        '"process_tree"',
        '"companion_artifacts"',
    ):
        assert field in machine_binding
    assert "deliberately has no report hash" in machine_binding
    load_inputs = _section("agents/process-tree-auditor.md", "### Step 1: Load Inputs")
    assert "BLOCKED:self-referential-companion-artifact" in load_inputs
    assert "if any companion identity equals the report identity" in load_inputs
    sidecar = _load_yaml("contracts/operators/process-tree-auditor.yaml")
    companion_input = _input(sidecar, "companion_artifacts")
    assert "canonical report path is forbidden" in companion_input["description"]
    assert "Header-first # Process Tree Audit report" in sidecar["outputs"][0][
        "success_shape"
    ]
    contract = _operator_contract("process-tree-auditor")
    inputs = contract["inputs"]
    expected_types = {
        "operator_file": "path",
        "process_tree_path": "path",
        "root_invocation_uuid": "string",
        "subtree_root_uuid": "string",
        "expected_process": "path",
        "companion_artifacts": "path_list",
        "audit_history_path": "path",
        "mode": "enum",
        "report_path": "path",
        "stdout_report_copy": "bool",
    }
    assert {item["name"]: item["type"] for item in inputs} == expected_types
    assert contract["defaults"] == [
        {"name": "mode", "value": "blocking", "source": "base"},
        {
            "name": "report_path",
            "value": "PROCESS_TREE_AUDIT.report.md",
            "source": "base",
        },
        {"name": "stdout_report_copy", "value": False, "source": "base"},
    ]


def test_named_process_audit_consumers_use_canonical_producer_binding():
    consumers = {
        "test-audit": _section(
            "agents/test-audit-gate.md",
            "### 7. Launch Three Parallel Sub-Agent Invocations",
        ),
        "pr-review": _section(
            "agents/pr-review-operator.md",
            "### Phase 4e: Initial Independent Process-Tree Join",
        ),
        "feature": _section(
            "agents/feature-orchestrator.md", "### Feature process-tree join"
        ),
        "refactoring": _section(
            "agents/refactoring-orchestrator.md", "## Expected Process And Join"
        ),
        "wake": _section(
            "workflows/wu-session-wake.md", "## Process-Tree Relationship"
        ),
    }
    for name, consumer in consumers.items():
        normalized = consumer.lower()
        assert "header-first" in normalized, name
        assert "producer-owned" in normalized, name
        assert "binding" in normalized, name
        assert "blocking" in normalized, name
    assert "TEST_AUDIT_PROCESS_PROOF_JSON" not in _read("agents/test-audit-gate.md")
    assert "ATTEMPT_LINEAGE_JSON" not in _read("agents/feature-orchestrator.md")


@pytest.mark.parametrize("corruption", ["verdict-first", "duplicate-verdict"])
def test_canonical_process_audit_parser_rejects_noncanonical_verdict_envelopes(
    tmp_path: Path, corruption: str
):
    fixture = _test_audit_result_fixture(tmp_path)
    report = fixture["audit_report_path"].read_text(encoding="utf-8")
    if corruption == "verdict-first":
        report = "Verdict: PASS\n\n" + report.replace("Verdict: PASS\n", "", 1)
    else:
        report += "Verdict: PASS\n"
    fixture["audit_report_path"].write_text(report, encoding="utf-8")

    decision = validate_process_tree_audit_report(fixture["audit_report_path"])

    assert decision["status"] == "INVALID"
    assert decision["errors"]


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("requested-root", "requested_id"),
        ("root-id", "root invocation id"),
        ("empty", "exactly the three declared child nodes"),
        ("missing", "must occur exactly once"),
        ("duplicate", "invocation UUIDs must be unique"),
        ("unexpected-required-role", "extra nested nodes"),
        ("wrong-parent", "actual parent"),
        ("wrong-model", "actual model"),
        ("wrong-source", "authoritative source"),
        ("failed", "status must equal succeeded"),
        ("non-terminal", "status must equal succeeded"),
        ("extra-nested", "extra nested nodes"),
    ],
)
def test_test_audit_nested_proof_rejects_actual_trace_topology_mutations(
    tmp_path: Path, corruption: str, expected_error: str
):
    fixture = _test_audit_result_fixture(tmp_path)
    trace = json.loads(fixture["trace_path"].read_text(encoding="utf-8"))
    children = trace["root"]["children"]
    if corruption == "requested-root":
        trace["requested_id"] = _SECOND_RUNNER_UUID
    elif corruption == "root-id":
        trace["root"]["invocation"]["id"] = _SECOND_RUNNER_UUID
    elif corruption == "empty":
        children.clear()
    elif corruption == "missing":
        children.pop()
    elif corruption == "duplicate":
        children.append(deepcopy(children[0]))
    elif corruption == "unexpected-required-role":
        replacement_uuid = "20000000-0000-4000-8000-000000000004"
        children[2]["invocation"]["id"] = replacement_uuid
        children[2]["invocation"]["agent_runner_invocation_id"] = replacement_uuid
    elif corruption == "wrong-parent":
        children[1]["invocation"]["parent_id"] = _SECOND_RUNNER_UUID
    elif corruption == "wrong-model":
        children[1]["invocation"]["model_name"] = "gpt-high"
    elif corruption == "wrong-source":
        children[1]["invocation"]["source"] = "different-provider"
    elif corruption == "failed":
        children[1]["invocation"].update(
            status="failed", success=False, exit_code=1
        )
    elif corruption == "non-terminal":
        children[1]["invocation"].update(
            status="running", success=None, exit_code=None, finished_at=None
        )
    else:
        nested = deepcopy(children[0])
        nested_uuid = "20000000-0000-4000-8000-000000000005"
        nested["invocation"].update(
            id=nested_uuid,
            agent_runner_invocation_id=nested_uuid,
            parent_id=children[0]["invocation"]["id"],
        )
        children[0]["children"].append(nested)
    _write_json_fixture(fixture["trace_path"], trace)
    proof = _refresh_test_audit_process_report(fixture)

    decision = validate_test_audit_nested_proof(
        proof, proof_path=fixture["proof_path"]
    )

    assert decision["status"] == "INVALID"
    assert any(expected_error in error for error in decision["errors"]), decision[
        "errors"
    ]


def test_test_audit_nested_proof_rejects_wrong_declared_operator_for_trace_node(
    tmp_path: Path,
):
    fixture = _test_audit_result_fixture(tmp_path)
    dispatch = json.loads(fixture["dispatch_path"].read_text(encoding="utf-8"))
    dispatch["nodes"][1]["operator_or_role"] = "coverage-analyzer"
    _write_json_fixture(fixture["dispatch_path"], dispatch)
    proof = json.loads(fixture["proof_path"].read_text(encoding="utf-8"))
    proof["child_artifacts"] = dispatch["nodes"]
    _write_json_fixture(fixture["proof_path"], proof)
    proof = _refresh_test_audit_process_report(fixture)

    decision = validate_test_audit_nested_proof(
        proof, proof_path=fixture["proof_path"]
    )

    assert decision["status"] == "INVALID"
    assert any("operator mismatch" in error for error in decision["errors"])


def test_test_audit_consumer_rejects_incomplete_producer_owned_binding(
    tmp_path: Path,
):
    fixture = _test_audit_result_fixture(tmp_path)
    report_decision = validate_process_tree_audit_report(fixture["audit_report_path"])
    binding = report_decision["binding"]
    binding["companion_artifacts"].pop()
    fixture["audit_report_path"].write_text(
        render_process_tree_audit_report(binding, "PASS"), encoding="utf-8"
    )
    proof = json.loads(fixture["proof_path"].read_text(encoding="utf-8"))
    proof["process_tree_audit_sha256"] = hashlib.sha256(
        fixture["audit_report_path"].read_bytes()
    ).hexdigest()
    _write_json_fixture(fixture["proof_path"], proof)

    decision = validate_test_audit_nested_proof(
        proof, proof_path=fixture["proof_path"]
    )

    assert decision["status"] == "INVALID"
    assert "process audit report producer-owned binding mismatch" in decision["errors"]


@pytest.mark.parametrize(
    "corruption",
    [
        "missing-child",
        "wrong-model",
        "wrong-parent",
        "stale-output",
        "missing-audit-report",
        "missing-nested-proof-hash",
    ],
)
def test_pr_review_production_validator_blocks_invalid_nested_test_audit_proof(
    tmp_path: Path, corruption: str
):
    fixture = _test_audit_result_fixture(tmp_path)
    result_path = fixture["result_path"]
    if corruption == "stale-output":
        fixture["child_output_path"].write_text(
            "Verdict: PASS\n\nstale replacement\n", encoding="utf-8"
        )
    elif corruption == "missing-audit-report":
        fixture["audit_report_path"].unlink()
    elif corruption == "missing-nested-proof-hash":
        result = json.loads(result_path.read_text())
        result.pop("nested_proof_sha256")
        _write_json_fixture(result_path, result)
    else:
        dispatch = json.loads(fixture["dispatch_path"].read_text())
        proof = json.loads(fixture["proof_path"].read_text())
        if corruption == "missing-child":
            dispatch["nodes"].pop()
            proof["child_artifacts"].pop()
        elif corruption == "wrong-model":
            dispatch["nodes"][1]["model"] = "gpt-high"
            proof["child_artifacts"][1]["model"] = "gpt-high"
        else:
            dispatch["nodes"][1]["parent_invocation_uuid"] = _SECOND_RUNNER_UUID
            proof["child_artifacts"][1]["parent_invocation_uuid"] = _SECOND_RUNNER_UUID
        _write_json_fixture(fixture["dispatch_path"], dispatch)
        _write_json_fixture(fixture["proof_path"], proof)

    output = tmp_path / "PR_REVALIDATION.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/operational_contracts.py"),
            "validate-test-audit-result",
            "--result",
            str(result_path),
            "--expected-root-uuid",
            fixture["root_uuid"],
            "--expected-base-sha",
            fixture["base_sha"],
            "--expected-head-sha",
            fixture["head_sha"],
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    decision = json.loads(output.read_text())
    assert decision["status"] == "INVALID"
    assert decision["errors"]


def test_pr_review_detached_posting_targets_exact_pr_and_repo_with_fake_gh(
    tmp_path: Path,
):
    phase_8 = _section(
        "agents/pr-review-operator.md",
        "### Phase 8: Final Provider Recheck, Post, and Stable Envelope",
    )
    assert 'gh pr review "$PR" --repo "$REPO"' in phase_8
    assert 'gh pr comment "$PR" --repo "$REPO"' in phase_8
    assert 'gh api --method GET "repos/${REPO}/pulls/${PR}/reviews"' in phase_8
    assert 'gh api --method GET "repos/${REPO}/issues/${PR}/comments"' in phase_8
    assert "gh pr review --" not in phase_8
    assert "gh pr comment --" not in phase_8
    assert "Reuse exactly one matching review ID and URL" in phase_8
    assert "Reuse exactly one matching comment ID and URL" in phase_8
    assert "BLOCKED:duplicate-pr-review-posting-identity" in phase_8
    assert "BLOCKED:duplicate-pr-comment-posting-identity" in phase_8

    repo = tmp_path / "detached"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@example.com")
    _git(repo, "config", "user.name", "Contract Tests")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "fixture")
    _git(repo, "checkout", "--detach")
    assert _git(repo, "branch", "--show-current") == ""

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "gh-calls.txt"
    fake_gh = bin_dir / "gh"
    fake_gh.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$GH_CALLS\"\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    body = tmp_path / "body.md"
    body.write_text("review body\n", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GH_CALLS": str(calls),
    }
    commands = [
        ["gh", "api", "--method", "GET", "repos/octo/example/pulls/260/reviews"],
        [
            "gh",
            "pr",
            "review",
            "260",
            "--repo",
            "octo/example",
            "--body-file",
            str(body),
            "--comment",
        ],
        ["gh", "api", "--method", "GET", "repos/octo/example/issues/260/comments"],
        [
            "gh",
            "pr",
            "comment",
            "260",
            "--repo",
            "octo/example",
            "--body-file",
            str(body),
        ],
    ]
    for command in commands:
        subprocess.run(command, cwd=repo, env=env, check=True)

    observed = calls.read_text(encoding="utf-8").splitlines()
    assert observed[0] == "api --method GET repos/octo/example/pulls/260/reviews"
    assert observed[1].startswith("pr review 260 --repo octo/example --body-file ")
    assert observed[1].endswith(" --comment")
    assert observed[2] == "api --method GET repos/octo/example/issues/260/comments"
    assert observed[3].startswith("pr comment 260 --repo octo/example --body-file ")


def test_all_pr_review_process_nodes_have_distinct_executable_log_output_pairs(
    tmp_path: Path,
):
    schema = _fenced_yaml_section(
        "agents/pr-review-operator.md", "## Process Proof Schema"
    )
    assert schema["node_path_invariant"] == (
        "dedicated-log-distinct-from-canonical-output"
    )
    assert set(schema["node_artifact_required_fields"]) >= {
        "log_path",
        "log_sha256_join_field",
        "canonical_output_path",
        "canonical_output_sha256_join_field",
        "output_mode",
    }
    initial = schema["initial_required_nodes"]
    proposal = schema["proposal_round_required_nodes"]
    domain = schema["domain_round_required_nodes"]
    expected_direct = set(initial) | set(proposal) | set(domain)
    test_audit_schema = _fenced_yaml_section(
        "agents/test-audit-gate.md", "### 7a. Test Audit Process Artifact Schema"
    )
    assert test_audit_schema["schema"] == "test-audit-process-artifacts-v2"
    assert test_audit_schema["root_identity_source"] == "OULIPOLY_PARENT_INVOCATION"
    assert test_audit_schema["required_nodes"] == {
        "spec-alignment": {
            "operator_or_role": "ad-hoc-spec-alignment",
            "model": "gpt-high",
            "parent": "root",
        },
        "test-quality": {
            "operator_or_role": "coverage-auditor",
            "model": "gpt-xhigh",
            "parent": "root",
        },
        "coverage-delta": {
            "operator_or_role": "coverage-analyzer",
            "model": "gpt-high",
            "parent": "root",
        },
    }
    assert test_audit_schema["node_path_invariant"] == (
        "dedicated-log-distinct-from-canonical-output"
    )
    assert test_audit_schema["identity_source"] == "complete-log-only"
    assert test_audit_schema["verdict_source"] == "canonical-output-only"
    assert "provider_source_join_field" in test_audit_schema["node_required_fields"]
    assert test_audit_schema["proof_acceptance"] == (
        "canonical-header-first-unique-report-PASS-producer-binding-current-"
        "final-stdout-PASS-and-production-validator-VALID"
    )
    file_nodes = {
        "test-audit",
        "justification-gauntlet",
        "commit-hygiene",
        "initial-process-auditor",
        "proposal-process-auditor",
        "domain-process-auditor",
    }
    nested_test_nodes = {
        f"test-audit-{node}" for node in test_audit_schema["required_nodes"]
    }
    stdout_nodes = expected_direct - file_nodes | nested_test_nodes
    all_nodes = stdout_nodes | file_nodes
    assert expected_direct <= all_nodes

    records: list[dict[str, str]] = []
    for node in sorted(all_nodes):
        node_root = tmp_path / node
        node_root.mkdir()
        log_path = node_root / f"{node}.log"
        output_path = node_root / f"{node}.md"
        payload = f"Verdict: PASS\n\n# {node}\n"
        log_path.write_bytes(_runner_envelope(payload))
        if node in stdout_nodes:
            extract_provider_payload(log_path, output_path)
            output_mode = "stdout-extracted"
        else:
            output_path.write_text(payload, encoding="utf-8")
            output_mode = "file-produced"
        records.append(
            {
                "node_id": node,
                "log_path": str(log_path),
                "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                "canonical_output_path": str(output_path),
                "canonical_output_sha256": hashlib.sha256(
                    output_path.read_bytes()
                ).hexdigest(),
                "output_mode": output_mode,
            }
        )

    assert {record["node_id"] for record in records} == all_nodes
    assert all(
        record["log_path"] != record["canonical_output_path"]
        and record["log_path"].endswith(".log")
        and record["canonical_output_path"].endswith(".md")
        for record in records
    )
    assert len({record["log_path"] for record in records}) == len(records)
    assert len({record["canonical_output_path"] for record in records}) == len(
        records
    )

    test_audit = _section(
        "agents/test-audit-gate.md",
        "### 7. Launch Three Parallel Sub-Agent Invocations",
    )
    for stem in ("SPEC", "QUALITY", "COVERAGE"):
        assert f'TEST_AUDIT_{stem}.log"' in test_audit
        assert f'--output "$scratch_dir/TEST_AUDIT_{stem}.md"' in test_audit
    pr_review = _read("agents/pr-review-operator.md")
    assert 'tee "$WORK_DIR/TEST_AUDIT_GATE.log"' in pr_review
    assert 'tee "$WORK_DIR/TEST_AUDIT_GATE.md"' not in pr_review
    violations = _read("conventions/workflow-execution-violations.md")
    assert "distinct complete-log and canonical-output paths/hashes" in violations
    assert "UUID evidence is parsed from a report" in violations


def test_pr_review_two_non_fast_forward_runs_preserve_lineage_and_current_evidence(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    review_root = tmp_path / "review-lineage"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@example.com")
    _git(repo, "config", "user.name", "Contract Tests")
    surface = repo / "surface.txt"
    surface.write_text("base\n", encoding="utf-8")
    _git(repo, "add", "surface.txt")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    surface.write_text("first head\n", encoding="utf-8")
    _git(repo, "commit", "-am", "first head")
    first_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "-c", "rewritten-head", base_sha)
    surface.write_text("rewritten head\n", encoding="utf-8")
    _git(repo, "commit", "-am", "rewritten head")
    second_head = _git(repo, "rev-parse", "HEAD")
    ancestry = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", first_head, second_head],
        check=False,
    )
    assert ancestry.returncode == 1

    first = initialize_pr_review_run(
        review_root, repo, 260, base_sha, first_head, _RUNNER_UUID
    )
    second = initialize_pr_review_run(
        review_root, repo, 260, base_sha, second_head, _SECOND_RUNNER_UUID
    )
    assert first["run_root"] != second["run_root"]
    assert first["worktree_path"] != second["worktree_path"]
    assert first["base_ref"] != second["base_ref"]
    assert first["head_ref"] != second["head_ref"]
    for run in (first, second):
        manifest_lines = (
            (Path(run["run_root"]) / "pr-review-run.json")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert manifest_lines[0] == "{"
        assert manifest_lines[1].strip().startswith('"schema":')

    for run in (first, second):
        _git(repo, "update-ref", run["base_ref"], base_sha)
        _git(repo, "update-ref", run["head_ref"], run["head_sha"])
        _git(repo, "worktree", "add", "--detach", run["worktree_path"], run["head_ref"])
        assert _git(Path(run["worktree_path"]), "rev-parse", "HEAD") == run["head_sha"]
        result_path = Path(run["run_root"]) / "PR_REVIEW_RESULT.json"
        result_path.write_text(
            json.dumps(
                {
                    "schema": "pr-review-result-v2",
                    "run_id": run["run_id"],
                    "run_root": run["run_root"],
                    "pr_number": run["pr_number"],
                    "base_sha": run["base_sha"],
                    "head_sha": run["head_sha"],
                    "pr_review_invocation_uuid": run["invocation_uuid"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    first_result = Path(first["run_root"]) / "PR_REVIEW_RESULT.json"
    first_cleanup = cleanup_pr_review_worktree(first, first_result)
    assert first_cleanup["status"] == "REMOVED"
    assert not Path(first["worktree_path"]).exists()
    assert first_result.exists()
    assert _git(repo, "rev-parse", first["head_ref"]) == first_head

    foreign_manifest = deepcopy(second)
    foreign_manifest["worktree_path"] = first["worktree_path"]
    with pytest.raises(_CONTRACT_MODULE.ContractValidationError):
        cleanup_pr_review_worktree(
            foreign_manifest, Path(second["run_root"]) / "PR_REVIEW_RESULT.json"
        )
    assert Path(second["worktree_path"]).exists()

    second_result = Path(second["run_root"]) / "PR_REVIEW_RESULT.json"
    current = json.loads(second_result.read_text(encoding="utf-8"))
    assert current["run_id"] == second["run_id"]
    assert current["base_sha"] == base_sha
    assert current["head_sha"] == second_head
    assert current["pr_review_invocation_uuid"] == _SECOND_RUNNER_UUID
    assert _git(repo, "rev-parse", second["head_ref"]) == second_head
    second_cleanup = cleanup_pr_review_worktree(second, second_result)
    assert second_cleanup["status"] == "REMOVED"
    assert not Path(second["worktree_path"]).exists()
    assert first_result.exists()
    assert second_result.exists()


def test_pr_review_initial_and_conditional_process_proof_schema_is_complete():
    schema = _fenced_yaml_section(
        "agents/pr-review-operator.md", "## Process Proof Schema"
    )
    assert schema["schema"] == "pr-review-process-proof-v1"
    assert schema["initial_required_nodes"] == {
        "risk-audit": "gpt-xhigh",
        "risk-scope": "gpt-xhigh",
        "risk-shortcut": "gpt-xhigh",
        "research": "gpt-high",
        "test-audit": "gpt-high",
        "multi-concern": "gpt-xhigh",
        "justification-gauntlet": "gpt-high",
        "supported-surface": "gpt-xhigh",
        "commit-hygiene": "gpt-high",
    }
    assert schema["proposal_round_required_nodes"] == {
        "proposal-writer": "gpt-high",
        "proposal-risk-audit": "gpt-xhigh",
        "proposal-risk-scope": "gpt-xhigh",
        "proposal-risk-shortcut": "gpt-xhigh",
    }
    assert schema["domain_round_required_nodes"] == {
        "domain-research": "gpt-high"
    }
    assert schema["proof_acceptance"] == (
        "canonical-header-first-unique-report-PASS-producer-binding-exact-blocking-"
        "mode-current-and-final-stdout-PASS"
    )
    assert schema["posting_currentness"] == (
        "exact-same-OPEN-pr-base-head-oids-as-phase-0"
    )
    assert schema["nested_test_audit_companion"] == (
        "production-validator-VALID-bound-to-outer-child-uuid-base-sha-head-sha"
    )

    gauntlet = _between(
        "agents/pr-review-operator.md",
        "#### 4b. Justification Gauntlet (`pr-justification-gauntlet.md`)\n",
        "### Phase 4c: Supported-Surface Verification (`gpt-xhigh`)\n",
    )
    dispatch = (
        "agents -a ${agents_dir}/pr-justification-gauntlet.md "
        '-p "$PROJECT_DIR" -f "$WORK_DIR/gauntlet-kickoff.md" '
        '2>&1 | tee "$WORK_DIR/result-justification.log"'
    )
    assert dispatch in gauntlet
    assert "agents -m" not in gauntlet


@pytest.mark.parametrize(
    ("mutation", "provider_identity_unchanged"),
    [
        (lambda nodes: nodes.pop("proposal-risk-shortcut"), True),
        (lambda nodes: nodes.update({"domain-research": "gpt-xhigh"}), True),
        (lambda nodes: None, False),
    ],
    ids=[
        "omitted-conditional-child",
        "wrong-model-conditional-child",
        "stale-provider-state",
    ],
)
def test_pr_review_rejects_incomplete_wrong_model_or_stale_conditional_results(
    mutation, provider_identity_unchanged: bool
):
    schema = _fenced_yaml_section(
        "agents/pr-review-operator.md", "## Process Proof Schema"
    )
    nodes = {
        **schema["initial_required_nodes"],
        **schema["proposal_round_required_nodes"],
        **schema["domain_round_required_nodes"],
    }
    mutation(nodes)
    assert not _pr_review_posting_allowed(
        schema,
        nodes,
        include_proposal=True,
        include_domain=True,
        provider_identity_unchanged=provider_identity_unchanged,
    )

    operator = _read("agents/pr-review-operator.md")
    assert "proposal-round-<NN>-v1" in operator
    assert "domain-<slug>-v1" in operator
    assert "an earlier PASS never certifies a later round" in operator
    assert "BLOCKED:pr-review-stale-provider-state" in operator


def test_pr_review_terminal_envelope_returns_every_versioned_process_proof_hash():
    schema = _fenced_yaml_section(
        "agents/pr-review-operator.md", "## Terminal Result Schema"
    )
    assert schema["schema"] == "pr-review-result-v2"
    assert {
        "run_id",
        "run_root",
        "run_manifest_path",
        "run_manifest_sha256",
        "pr_review_invocation_uuid",
        "final_provider_identity_path",
        "final_provider_identity_sha256",
        "child_artifacts",
        "nested_test_audit_proof",
    } <= set(schema["required_fields"])
    assert schema["child_artifact_path_invariant"] == (
        "log_path-must-differ-from-canonical_output_path"
    )
    assert set(schema["process_proof_required_fields"]) == {
        "kind",
        "version",
        "expected_process_path",
        "expected_process_sha256",
        "dispatch_evidence_path",
        "dispatch_evidence_sha256",
        "process_tree_path",
        "process_tree_sha256",
        "process_tree_audit_path",
        "process_tree_audit_sha256",
        "process_tree_audit_log_path",
        "process_tree_audit_log_sha256",
        "verdict",
    }
    assert schema["process_proof_kinds"] == [
        "initial",
        "proposal-round",
        "domain-research",
    ]
    assert schema["nested_test_audit_acceptance"] == (
        "production-validator-VALID-bound-to-outer-node-and-pinned-provider-identity"
    )
    phase_8 = _section(
        "agents/pr-review-operator.md",
        "### Phase 8: Final Provider Recheck, Post, and Stable Envelope",
    )
    assert "After every applicable initial, proposal-round, and domain process proof" in phase_8
    assert "Require the same `state=OPEN`" in phase_8
    assert phase_8.index("re-query the exact PR") < phase_8.index(
        "Only then post the prepared review"
    )


def test_manual_merge_baseline_is_derived_at_wake_not_guessed():
    wake = _section("workflows/wu-session-wake.md", "## Procedure")
    assert "`pre_merge_base_sha` is optional" in wake
    assert "`base_ref_oid` is current PR/base status evidence and is not `pre_merge_base_sha`" in wake
    assert "omit/null means the resumer must derive it from trusted merge evidence" in wake
    assert "derive the poller's `<owner>/<repo>#<number>` identifier" in wake
    assert "without replacing the stored URL" in wake

    resumer_contract = _load_yaml("contracts/operators/wu-session-resumer.yaml")
    assert _input(resumer_contract, "pre_merge_base_sha")["required"] is False
    resumer = _section("agents/wu-session-resumer.md", "## Procedure")
    assert "two-parent merge commit uses parent one" in resumer
    assert "one-parent squash commit" in resumer
    assert "BLOCKED:ambiguous-pre-merge-base" in resumer
    assert "Never use manifest `pr_open_base_sha` or poller `base_ref_oid`" in resumer

    poller = _section("tools/pr-batch-poller/README.md", "## Resumer-handoff shape")
    assert "`base_ref_name`" in poller
    assert "optional `pre_merge_base_sha`" in poller
    assert "`base_ref_oid` is current base-status evidence, not `pre_merge_base_sha`" in poller
    assert "pre_merge_main_sha" not in poller


def test_resumer_contract_declares_high_risk_outputs_delegation_and_effects():
    contract = _operator_contract("wu-session-resumer")
    assert _input(contract, "session_manifest_path")["type"] == "path"
    assert set(contract["outputs"][0]["wrote_lines"]) == {
        "session_manifest_path",
        "${planning_dir}/../sessions.active-wake.json exact-row removal after verified close or handoff",
        "${scratch_dir}/session-writes/resumer-update.json",
        "${scratch_dir}/session-writes/resumer-close.json",
        "manifest audit_history_path or ${planning_dir}/audit-history.md",
        "${planning_dir}/reports/post-merge-test-rerun.md",
        "${planning_dir}/reports/post-merge-coverage.md",
        "${planning_dir}/reports/post-merge-contracts.md",
        "${planning_dir}/reports/post-merge-drift.md",
        "${scratch_dir}/questions/q-<uuidv4>.question.json when input is required",
        "${scratch_dir}/ticket-comments/${ticket_id}-post-merge.json when a ticket write cannot complete",
        "successor_session_brief when a successor handoff is declared",
    }
    assert set(contract["must_delegate"]) == {
        "semantic-drift-review-to-rebase-drift-checker",
        "linear-ticket-write-to-linear-operator",
        "jira-ticket-write-to-jira-operator",
    }
    assert {
        "session-manifest-write",
        "session-audit-history-write",
        "post-merge-report-writes",
        "ticket-cross-link-comment",
        "executable-resumer-update-and-resumer-close-closed-schema-requests",
    } <= set(contract["side_effects"])
    success = contract["outputs"][0]["success_shape"]
    assert "wu-session-resumer: closed; manifest=<path>" in success
    assert "wu-session-resumer: handoff-prepared; manifest=<path>; brief=<path>" in success


def test_resumer_revalidates_exact_pr_identity_and_containment_before_mutation():
    procedure = _section("agents/wu-session-resumer.md", "## Procedure")
    trusted_query = "query exactly the PR identified by `pr_url`"
    fetch = "freshly fetch `refs/heads/${base_branch}`"
    containment = "git merge-base --is-ancestor ${merge_sha}"
    mutation = "Only after all gates pass"
    assert procedure.index(trusted_query) < procedure.index(fetch)
    assert procedure.index(fetch) < procedure.index(containment)
    assert procedure.index(containment) < procedure.index(mutation)
    for value in (
        "returned URL exactly equals `pr_url`",
        "`state == MERGED`",
        "full `headRefOid == head_sha == draft_pr_head_sha`",
        "`baseRefName == base_branch`",
        "full `mergeCommit.oid == merge_sha`",
        "BLOCKED:pr-url-mismatch",
        "BLOCKED:pr-not-merged",
        "BLOCKED:pr-head-oid-mismatch",
        "BLOCKED:pr-base-ref-mismatch",
        "BLOCKED:pr-merge-oid-mismatch",
        "BLOCKED:merge-not-contained",
    ):
        assert value in procedure
    assert "provider-supported `MERGE` reports exactly two parents" in procedure
    assert "provider-supported `SQUASH` reports exactly one parent" in procedure
    assert "`REBASE`" in procedure


def test_wake_dispatch_surface_report_and_process_tree_are_exact():
    workflow = _read("workflows/wu-session-wake.md")
    assert workflow.count("## Workflow Dispatch Surface\n") == 1
    assert _fenced_yaml_section(
        "workflows/wu-session-wake.md", "## Workflow Dispatch Surface"
    ) == _workflow_dispatch_contract("wu-session-wake")
    contract = _workflow_dispatch_contract("wu-session-wake")
    assert contract["orchestrator"] == "root wu-session-wake invocation (scheduler-triggered or manual)"
    joined_inputs = "\n".join(contract["inputs"])
    assert "caller-owned unique run_id" in joined_inputs
    assert "OULIPOLY_PARENT_INVOCATION" in joined_inputs
    assert "sessions.active-wake.json path" in joined_inputs
    assert "sessions.index.json path" not in joined_inputs
    assert "root_invocation_uuid" not in joined_inputs
    assert "verifies the multi-row expected process and process tree before aggregate completion" in contract[
        "expectations"
    ]
    outputs = set(contract["outputs"])
    assert {
        "${planning_root}/wake-runs/${run_id}/composition-report.json",
        "${planning_root}/wake-runs/${run_id}/expected-process.json",
        "${planning_root}/wake-runs/${run_id}/dispatch-evidence.json",
        "${planning_root}/wake-runs/${run_id}/process-tree.json",
        "${planning_root}/wake-runs/${run_id}/process-tree-audit.md",
        "${planning_root}/wake-runs/${run_id}/process-tree-audit.log",
    } <= outputs
    report = _section("workflows/wu-session-wake.md", "## Composition Report")
    for value in (
        '"status": "joined | skipped | blocked"',
        '"session_manifest_path"',
        '"successor_brief_path"',
        '"prompt_path"',
        '"log_path"',
        '"expected_node_id"',
        '"row_identity_sha256"',
        '"child_invocation_uuid"',
        '"child_sentinel"',
        '"aggregate": "success | partial | blocked"',
    ):
        assert value in report
    process = _section("workflows/wu-session-wake.md", "## Process-Tree Relationship")
    assert "exactly one direct resumer child per expected row" in process
    assert "no child for skipped/blocked rows" in process
    assert "process-tree-auditor" in process
    assert "derived `wake_invocation_uuid`" in process
    assert "exact `Verdict: PASS`" in process
    assert "auditor log's final exact `PASS`" in process


def test_wake_validates_safe_tokens_contains_paths_and_quotes_dispatch_paths():
    procedure = _section("workflows/wu-session-wake.md", "## Procedure")
    safe_token = "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
    assert procedure.count(safe_token) == 2
    assert "BLOCKED:unsafe-wake-path" in procedure
    assert 'realpath -m -- "${wake_run_root}"' in procedure
    assert 'realpath -- "${planning_root}"' in procedure
    assert "generated prompt path, and generated log path" in procedure
    assert "remain strictly below the canonical `planning_root`" in procedure
    assert (
        'agents -a wu-session-resumer -p "${worktree_path}" '
        '-f "${planning_dir}/prompts/${ticket_id}-wu-session-resume-${run_id}.md" '
        '2>&1 | tee "${planning_dir}/logs/${ticket_id}-wu-session-resume-${run_id}.log"'
        in procedure
    )


def test_wake_skipped_only_batch_is_successful_audited_noop():
    procedure = _section("workflows/wu-session-wake.md", "## Procedure")
    stop = _section("workflows/wu-session-wake.md", "## Stop Conditions")
    assert "zero merged rows, and no blocked inputs is a successful no-op" in procedure
    assert "empty expected-process/dispatch/trace audit with zero resumer nodes" in procedure
    assert "legitimately skipped non-merged rows" in stop
    assert "successful audited no-op with zero resumer nodes" in stop
    assert "The legitimate skipped-only no-op is not blocked" in stop


def test_wake_pre_merge_base_is_active_index_sourced_and_manifest_mismatch_blocks():
    procedure = _section("workflows/wu-session-wake.md", "## Procedure")
    assert "active-index `pre_merge_base_sha`" in procedure
    assert "including null equality" in procedure
    assert "BLOCKED:pre-merge-base-source-mismatch" in procedure
    assert "The active index is the sole source passed to the resumer" in procedure
    assert "from the session index or manifest" not in procedure
    assert (
        "from the active index after exact manifest equality validation" in procedure
    )


def test_wake_expected_nodes_match_canonical_auditor_schema_and_marker_join():
    schema = _fenced_yaml_section(
        "workflows/wu-session-wake.md", "## Expected Process Schema"
    )
    assert schema["schema"] == "wu-session-wake-expected-process-v1"
    assert set(schema["node_required_fields"]) == {
        "id",
        "required",
        "operator_or_role",
        "model",
        "parent",
        "prompt",
        "log",
        "expected_outputs",
        "questions_allowed",
        "question_artifacts",
        "answer_artifacts",
        "continuation_evidence",
        "blocking_if_missing",
        "notes",
        "row_identity",
        "row_identity_sha256",
        "prompt_sha256",
    }
    assert schema["fixed_node_values"] == {
        "required": True,
        "operator_or_role": "wu-session-resumer",
        "model": "gpt-high",
        "parent": "root",
        "questions_allowed": True,
        "blocking_if_missing": True,
    }
    assert schema["post_dispatch_identity_source"] == (
        "dispatch-evidence.json OULIPOLY_INVOCATION marker only"
    )
    procedure = _section("workflows/wu-session-wake.md", "## Procedure")
    assert "Do not accept a caller-provided current invocation UUID" in procedure
    assert "set `wake_invocation_uuid`" in procedure
    assert "parse exactly one valid `OULIPOLY_INVOCATION` marker" in procedure
    assert "never rewrite the expected manifest to add UUIDs" in procedure
    assert "Reject `FAIL:*`, `NEEDS_INPUT:*`, `BLOCKED:*`, `compliant`" in procedure


def test_wake_requires_current_exact_resumer_sentinel_and_row_identity():
    procedure = _section("workflows/wu-session-wake.md", "## Procedure")
    assert "Parse only the same current log's final sentinel" in procedure
    assert "wu-session-resumer: closed; manifest=<path>" in procedure
    assert "wu-session-resumer: handoff-prepared; manifest=<path>; brief=<path>" in procedure
    assert "returned manifest equals the joined row's exact `session_manifest_path`" in procedure
    stop = _section("workflows/wu-session-wake.md", "## Stop Conditions")
    for sentinel in (
        "wu-session-wake: success; report=<absolute-path>",
        "wu-session-wake: partial; report=<absolute-path>",
        "wu-session-wake: blocked; report=<absolute-path>",
    ):
        assert sentinel in stop
    assert "accepted-breakage classification present in the active index blocks" in stop
    assert "canonical OPEN row that currently polls non-merged may remain pending" in stop


def test_poller_handoff_exposes_exact_merge_base_and_full_head_identity():
    readme = _section("tools/pr-batch-poller/README.md", "## Resumer-handoff shape")
    implementation = _read("tools/pr-batch-poller/pr_batch_poller.py")
    for field in (
        "pr_url",
        "state",
        "merged",
        "merge_sha",
        "head_sha",
        "head_ref_name",
        "base_ref_name",
        "base_ref_oid",
        "merged_at",
    ):
        assert f"`{field}`" in readme
        assert f'"{field}"' in implementation
    assert "full `merge_sha`" in readme
    assert "full `head_sha`" in readme
    assert "current base OID observed when the poll ran" in readme
    assert "not automatically the historical immediate pre-merge SHA" in readme
    assert "pre_merge_main_sha" not in readme


def test_scheduler_and_tools_route_only_through_wake_composition_root():
    tools = _read("tools/README.md")
    scheduler = _read("tools/scheduler/README.md")
    poller = _read("tools/pr-batch-poller/README.md")
    resumer = _read("agents/wu-session-resumer.md")
    assert "scheduler/manual root  ──>  wu-session-wake" in tools
    assert "one exact joined row" in tools
    assert "invokes the `wu-session-wake` workflow root" in scheduler
    assert "scheduler or manual caller invokes `wu-session-wake`" in poller
    assert "The poller is status-only and never dispatches a resumer" in poller
    assert "one exact joined row from that root" in resumer
    assert "scheduler  ──(every 10 min)──>  pr-batch-poller" not in tools


def test_active_wake_handoff_has_no_retired_field_names():
    active_paths = (
        "agents/wu-session-resumer.md",
        "contracts/operators/wu-session-resumer.yaml",
        "workflows/wu-session-wake.md",
        "contracts/workflows/wu-session-wake.yaml",
        "tools/pr-batch-poller/README.md",
        "agents/implementation-pipeline-orchestrator.md",
        "workflows/implementation-pipeline.md",
    )
    for path in active_paths:
        assert "pre_merge_main_sha" not in _read(path), path


def test_migration_tool_documents_executable_runtime_writer_and_cutover_safety():
    readme = _read("tools/wu-session-migration/README.md")
    implementation = _read("tools/wu-session-migration/wu_session_migration.py")
    for value in (
        "Dry run never writes a session manifest or index",
        "306 manifests, seven `sessions.index.json` files, 152 source rows, and 42 unique cohort manifests",
        "Accepted-breakage manifests remain untouched",
        "not observer-atomic",
        "sessions.active-wake.json",
        "CLOUD-259-session-store-scoped-acquisition",
    ):
        assert value in readme
    assert 'PLAN_SCHEMA = "wu-session-migration-plan-v1"' in implementation
    assert "stale source identity" in implementation
    assert "recover_incomplete_transaction" in implementation
    assert "cutover.lock" in implementation
    assert "os.replace" in implementation
    for operation in (
        "phase0-init",
        "phase7-upsert",
        "phase9-update",
        "resumer-update",
        "resumer-close",
    ):
        assert f"python3 tools/wu-session-migration {operation} --request" in readme
    assert 'RUNTIME_REQUEST_SCHEMA = "wu-session-runtime-write-v1"' in implementation
    assert "O_DIRECTORY" in implementation
    assert "src_dir_fd" in implementation
    assert "dst_dir_fd" in implementation
    assert "malformed or substituted recovery journal" in implementation


def test_pipeline_and_resumer_invoke_exact_runtime_writer_commands():
    pipeline = _read("agents/implementation-pipeline-orchestrator.md")
    resumer = _read("agents/wu-session-resumer.md")
    workflow = _read("workflows/implementation-pipeline.md")
    for operation in ("phase0-init", "phase7-upsert", "phase9-update"):
        command = f"python3 ~/ai/tools/wu-session-migration {operation} --request"
        assert command in pipeline
        assert command in workflow
    for operation in ("resumer-update", "resumer-close"):
        assert f"python3 ~/ai/tools/wu-session-migration {operation} --request" in resumer
    assert "do not write either target directly" in pipeline
    assert "do not write either target directly" in resumer


def test_direct_and_feature_session_owner_contracts_are_synchronized():
    pipeline = _read("agents/implementation-pipeline-orchestrator.md")
    workflow = _read("workflows/implementation-pipeline.md")
    lifecycle = _read("conventions/wu-session-lifecycle.md")
    runtime_readme = _read("tools/wu-session-migration/README.md")
    feature = _read("agents/feature-orchestrator.md")
    refactoring = _read("agents/refactoring-orchestrator.md")
    wake = _read("workflows/wu-session-wake.md")
    resumer = _read("agents/wu-session-resumer.md")

    assert "R=${planning_dir}/.." in pipeline
    assert "R=${planning_dir}/.." in workflow
    assert "R=${planning_dir}/.." in lifecycle
    documents = {
        "agents/implementation-pipeline-orchestrator.md": pipeline,
        "workflows/implementation-pipeline.md": workflow,
        "conventions/wu-session-lifecycle.md": lifecycle,
        "tools/wu-session-migration/README.md": runtime_readme,
    }
    for name, text in documents.items():
        assert "F/routes" in text, name
        assert "sessions.active-wake.json" in text, name
    assert "route_planning_dir.parent" in feature
    assert "planning_root=F/routes" in feature
    assert "planning_dir.parent" in refactoring
    assert "selects that `F/routes` root explicitly" in refactoring
    assert "direct callers pass P and feature callers pass F/routes" in wake
    assert "Never scan ancestors or descendants" in wake
    assert "Never search ancestors, descendants, or another active index" in resumer
    assert "exact same-owner `R/sessions.active-wake.json`" in resumer


def test_agents_routing_summary_matches_canonical_feature_contract():
    feature_row = _section("AGENTS.md", "### Feature orchestration")
    for value in (
        "`feature_scope_path`",
        "explicit `trunk_branch`",
        "explicit `feature_branch`",
        "`feature_worktree_path`",
        "`child_worktrees_root`",
        "exactly one of `ticket_route_map?` or `successor_manifest_path?`",
        "`ticket_system` plus matching backend configuration",
        "`acceptance_evidence_paths`",
        "`post_merge_owner`",
        "runtime UUID is runner-derived",
    ):
        assert value in feature_row
    assert "`trunk_branch?`" not in feature_row
    assert "`feature_branch?`" not in feature_row
    assert "`worktree_path`" not in feature_row
    assert "`root_invocation_uuid`" not in feature_row


def test_agents_routing_summary_matches_refactoring_contract_and_defaults():
    row = _section("AGENTS.md", "### Refactoring strategies")
    for value in (
        "exactly one of `jira_issue_key?` / `linear_issue_key?` / `wu_brief_path?`",
        "required `ticket_system` plus matching backend configuration",
        "short GitHub `integration_branch_ref`",
        "`shim_registry_path?` (default `~/ai/conventions/active-shims.md`)",
        "`audit_history_path?` (default `${planning_dir}/refactoring-audit-history.md`)",
        "current audited `VERIFIED_MERGED` evidence",
        "runtime UUID is runner-derived",
    ):
        assert value in row
    assert "`root_invocation_uuid`" not in row


def test_step6c_workflow_declares_sidecar_first_contract_resolution():
    workflow = (REPO_ROOT / "workflows/step6c-consumption-side-file.md").read_text()
    sidecar = yaml.safe_load(
        (REPO_ROOT / "contracts/workflows/step6c-consumption-side-file.yaml").read_text()
    )
    rule = sidecar["expectations"][0]

    assert "authoritative dispatch contract" in rule
    assert "frontmatter only when the sidecar is absent" in rule
    workflow_rule = rule.replace(
        "this sidecar", "`contracts/workflows/step6c-consumption-side-file.yaml`"
    )
    assert workflow_rule in workflow


def test_worktree_operator_sidecar_closes_mutation_boundary_and_results():
    sidecar = yaml.safe_load(
        (REPO_ROOT / "contracts/operators/worktree-operator.yaml").read_text()
    )
    task = next(row for row in sidecar["inputs"] if row["name"] == "task")
    name = next(row for row in sidecar["inputs"] if row["name"] == "name")
    outputs = {
        row["task"]: row["success_shape"] for row in sidecar["outputs"]
    }
    operator = (REPO_ROOT / "agents/worktree-operator.md").read_text()
    result_contract = _fenced_yaml_section(
        "agents/worktree-operator.md", "## Result Contract"
    )
    variants = result_contract["variants"]

    assert task["options"] == [
        "create",
        "list",
        "sync",
        "remove",
        "bulk-cleanup",
        "open-pr",
    ]
    assert "pre/post head SHA" in outputs["sync"]
    assert "task=list" in outputs["list"]
    assert "per-worktree git status collection" in outputs["list"]
    for list_rule in (
        "unreadable or vanished rows retain every key",
        "PASS for zero or all-readable rows",
        "PARTIAL for mixed readable/BLOCKED rows",
        "BLOCKED for non-empty all-BLOCKED rows",
    ):
        assert list_rule in outputs["list"]
    assert "open-pr" in name["description"]
    assert "base branch/base SHA" in outputs["remove"]
    assert "pre-removal" in outputs["remove"]
    assert "one worktree_path/branch" in outputs["bulk-cleanup"]
    for bulk_field in (
        "base branch",
        "base SHA",
        "head SHA",
        "cleanliness",
        "PR target repository",
        "PR head repository",
        "PR URL/number/state",
        "removed",
    ):
        assert bulk_field in outputs["bulk-cleanup"]
    for value in (
        "status=PASS",
        "provider_state=OPEN",
        "exact target and head repository identities",
        "PR URL/number",
        "base/head branches",
        "base SHA",
        "head SHA",
        "draft=true",
    ):
        assert value in outputs["open-pr"]
    assert "skipped rows retain every key" in outputs["bulk-cleanup"]
    assert "null for unavailable identity fields" in outputs["bulk-cleanup"]
    for aggregate_rule in (
        "PASS for zero or all-PASS rows",
        "PARTIAL for mixed PASS/BLOCKED rows",
        "BLOCKED for non-empty all-BLOCKED rows",
    ):
        assert aggregate_rule in outputs["bulk-cleanup"]
    assert "status/reason" in outputs["bulk-cleanup"]
    assert "recursive-worktree-operator-dispatch" in sidecar["forbidden_direct"]
    assert "unquoted-caller-controlled-git-arguments" in sidecar["forbidden_direct"]
    assert "central-checkout-as-worktree-target" in sidecar["forbidden_direct"]
    assert "git-fetch" in sidecar["side_effects"]
    assert "git-reset-keep" in sidecar["side_effects"]
    assert "git-push-validated-url" in sidecar["side_effects"]
    assert "BLOCKED:dirty-worktree" in operator
    assert 'reset --keep "$branch_name"' in operator
    assert "exclusive advisory mutation lock" in operator
    assert "Hold the lock through `git worktree remove`" in operator
    assert "revalidate canonical path, branch, head SHA, base identity" in operator
    assert "Hold the lock through the removal and both post-removal checks" in operator
    assert "this operator has no force-removal input" in operator
    assert "Require exactly one provider PR" in operator
    assert 'writer_dir=$(mktemp -d)' in operator
    assert "Cleanup `writer_dir` only after the writer is terminal" in operator
    assert 'tee "$writer_dir/pr-writer.log"' in operator
    assert "$worktree_path/.tmp" not in operator
    assert "not be symlinks" in operator
    assert "canonical `writer_dir` as their direct parent" in operator
    assert 'pipeline_status=("${PIPESTATUS[@]}")' in operator
    assert "to exist, be non-empty regular files" in operator
    assert "worktree's current branch to equal `branch_name`" in operator
    for pinned_input in ("base_ref", "base_sha", "head_ref", "head_sha"):
        assert f'--input "{pinned_input}=${pinned_input}"' in operator
    assert "no exact canonical path record remains" in operator
    assert "worktree_row_required" in operator
    assert "result_row_required" in operator
    assert "removed_row: {pr_state: MERGED, removed: true, status: PASS" in operator
    assert "skipped_row: {removed: false, status: BLOCKED" in operator
    assert "nullable: [branch, base_branch, base_sha, head_sha, clean, pr_repo" in operator
    assert "provider_state: OPEN" in operator
    assert 'gh pr list --repo "$repo_slug" --state open' in operator
    assert "BLOCKED:non-exact-open-pr" in operator
    assert "Only zero open query results enter the creation path" in operator
    assert "successful, non-empty title and body output before the first push" in operator
    assert "reason=pr-writer-failed" in operator
    assert "reason=pr-writer-output-invalid" in operator
    assert "Do not execute any later command in this procedure" in operator
    assert 'self.command("gh", "pr", "create"' in operator
    assert "perform one bounded exact repository/base/head" in operator
    assert "for diagnostic evidence only" in operator
    assert "Do not close any PR from that evidence" in operator
    assert "mutation_state=unknown" in operator
    assert 'self.command("git", "ls-remote", "--exit-code", "--refs", identity["push_url"]' in operator
    assert "BLOCKED:remote-head-unverified" in operator
    assert "whose OID equals `head_sha`" in operator
    assert "hold it through the exact open-PR decision only (section A)" in operator
    assert "Release section A and prove its owned tree terminal" in operator
    assert "### Section B: reacquire and revalidate" in operator
    assert "Only an unchanged tuple and zero" in operator
    for limit, value in (("lock_acquire_seconds", 30), ("lock_hold_seconds", 300), ("lock_cleanup_seconds", 10)):
        assert next(row["value"] for row in sidecar["defaults"] if row["name"] == limit) == value
    for forbidden in ("async-lock-holder-or-waiter", "marker-or-sleep-lock-lifetime", "unbounded-lock-acquisition", "lock-across-pr-writer", "unlock-before-owned-tree-retirement"):
        assert forbidden in sidecar["forbidden_direct"]
    embedded = _fenced_yaml_section("agents/worktree-operator.md", "## Contract")
    for field in ("inputs", "defaults", "outputs", "errors", "forbidden_direct"):
        assert embedded[field] == sidecar[field]
    assert "before resolving worktree or ref identities" in operator
    assert "BLOCKED:stale-open-pr-worktree-identity" in operator
    assert "REGISTERED_PRIMARY" in operator
    assert "REGISTERED_LINKED" in operator
    assert "not tested as a linked mutation target" in operator
    assert 'remote get-url --push "$push_remote"' in operator
    assert "BLOCKED:push-remote-repository-mismatch" in operator
    assert "headRepository.nameWithOwner" in operator
    assert "headRepositoryOwner.login" in operator
    assert "target/base repository and head repository both equal" in operator
    assert "pr_head_repo" in operator
    bulk_cleanup_section = operator.split(
        "## Procedure: Bulk Cleanup Merged Worktrees", 1
    )[1].split("## Procedure: Open PR", 1)[0]
    provider_recheck_index = bulk_cleanup_section.index(
        'gh pr view "$pr_number" --repo "$pr_repo"'
    )
    removal_index = bulk_cleanup_section.index(
        'git -C "$repo_root" worktree remove "$worktree_path"'
    )
    assert provider_recheck_index < removal_index
    assert "state=MERGED" in bulk_cleanup_section
    assert "Merged worktrees need provider-verified bulk cleanup" in operator
    assert "A draft pull request needs exact creation or idempotent reuse" in operator
    assert 'gh pr close "$created_pr_url" --repo "$repo_slug"' in operator
    assert "BLOCKED:ambiguous-open-pr" in operator
    assert "re-query that exact PR" in operator
    assert "exact re-query succeeds with `state=CLOSED`" in operator
    assert "mutation_state=reconciled" in operator
    assert "Use `mutation_state=reconciled` only when the close succeeds" in operator
    assert "the exact PR remains open" in operator
    assert "A retry re-runs the exact open-PR query" in operator
    assert result_contract["variants"]["blocked"] == {
        "status": "BLOCKED",
        "required": ["reason", "mutation_state", "observed_identity"],
        "mutation_state": ["none", "reconciled", "unknown"],
        "observed_identity": "object | null",
        "reconciliation": "object | null",
        "reconciliation_required_when": {"mutation_state": "reconciled"},
    }
    assert variants["list"]["worktree_row_required"] == [
        "path",
        "branch",
        "head_sha",
        "clean",
        "registration_status",
        "reason",
    ]
    assert variants["list"]["aggregate_status"] == {
        "zero_rows": "PASS",
        "all_rows_readable": "PASS",
        "mixed_readable_blocked": "PARTIAL",
        "nonempty_all_rows_blocked": "BLOCKED",
    }
    assert variants["list"]["blocked_row"] == {
        "registration_status": "BLOCKED",
        "nullable": ["branch", "head_sha", "clean"],
    }
    assert variants["create"]["required"] == [
        "repo_root",
        "worktree_path",
        "branch",
        "base_branch",
        "base_sha",
        "head_sha",
        "clean",
    ]
    assert variants["sync"]["required"] == [
        "worktree_path",
        "branch",
        "pre_head_sha",
        "post_head_sha",
        "clean",
    ]
    assert variants["remove"]["required"] == [
        "worktree_path",
        "branch",
        "base_branch",
        "base_sha",
        "head_sha",
        "clean",
        "removed",
    ]
    assert variants["bulk-cleanup"]["result_row_required"] == [
        "worktree_path",
        "branch",
        "base_branch",
        "base_sha",
        "head_sha",
        "clean",
        "pr_repo",
        "pr_head_repo",
        "pr_url",
        "pr_number",
        "pr_state",
        "removed",
        "status",
        "reason",
    ]
    assert variants["open-pr"] == {
        "status": "PASS",
        "required": [
            "repo",
            "head_repo",
            "pr_url",
            "pr_number",
            "provider_state",
            "draft",
            "base_branch",
            "base_sha",
            "head_branch",
            "head_sha",
        ],
        "fixed": {"provider_state": "OPEN", "draft": True},
    }
    open_pr_section = operator.split("## Procedure: Open PR", 1)[1].split(
        "## Result Contract", 1
    )[0]
    lock_index = open_pr_section.index("Acquire the same exclusive advisory mutation lock")
    resolve_index = open_pr_section.index("resolve `base_sha`")
    query_index = open_pr_section.index(
        'gh pr list --repo "$repo_slug" --state open'
    )
    non_exact_index = open_pr_section.index("BLOCKED:non-exact-open-pr")
    writer_index = open_pr_section.index("agents -a ~/ai/agents/pr-writer.md")
    push_index = open_pr_section.index(
        'self.command("git", "-C", identity["worktree_path"], "push", identity["push_url"]'
    )
    remote_head_index = open_pr_section.index(
        'self.command("git", "ls-remote", "--exit-code", "--refs", identity["push_url"]'
    )
    stale_identity_index = open_pr_section.index(
        "BLOCKED:stale-open-pr-worktree-identity"
    )
    create_index = open_pr_section.index('self.command("gh", "pr", "create"')
    assert lock_index < resolve_index < query_index < non_exact_index < writer_index
    assert stale_identity_index < push_index < create_index
    revalidate_index = open_pr_section.index("# worktree-publication-dispatch-v1")
    assert writer_index < revalidate_index < push_index < remote_head_index < create_index
    assert variants["bulk-cleanup"]["aggregate_status"] == {
        "zero_targets": "PASS",
        "all_rows_pass": "PASS",
        "mixed_pass_blocked": "PARTIAL",
        "nonempty_all_rows_blocked": "BLOCKED",
    }


def test_build_prototype_indexes_complete_test_carry_forward_schema():
    fields = (
        "prototype_test_pr_url",
        "prototype_test_branch",
        "test_paths_or_node_ids",
        "marker_reason",
        "ticket_mapping",
        "implementation_acceptance_criterion",
    )
    workflow = (REPO_ROOT / "workflows/build-prototype.md").read_text()
    sidecar = yaml.safe_load(
        (REPO_ROOT / "contracts/workflows/build-prototype.yaml").read_text()
    )
    index = json.loads((REPO_ROOT / "workflows/index.json").read_text())
    indexed_outputs = index["workflows"]["build-prototype"][
        "workflow_dispatch_contract"
    ]["outputs"]

    for field in fields:
        assert field in workflow
        assert any(field in output for output in sidecar["outputs"])
        assert any(field in output for output in indexed_outputs)


def test_project_bootstrap_indexes_canonical_wrapper_location_and_base():
    workflow = (REPO_ROOT / "workflows/project-bootstrap.md").read_text()
    sidecar = yaml.safe_load(
        (REPO_ROOT / "contracts/workflows/project-bootstrap.yaml").read_text()
    )

    for value in ("<project>/trunk/agents/", "~/ai/agents/<name>.md"):
        assert value in workflow
        assert any(value in item for item in sidecar["expectations"])
        assert any(value in item for item in sidecar["outputs"])
    assert "<project>/agents/" not in workflow
    precedence = next(
        item
        for item in sidecar["expectations"]
        if "contracts/workflows/project-bootstrap.yaml" in item
    )
    assert "authoritative dispatch contract" in precedence
    assert "frontmatter only when the sidecar is absent" in precedence
    assert precedence.replace(
        "contracts/workflows/project-bootstrap.yaml",
        "`contracts/workflows/project-bootstrap.yaml`",
    ) in workflow


def test_pr_review_rechecks_provider_identity_before_each_post_or_reuse():
    operator = (REPO_ROOT / "agents/pr-review-operator.md").read_text()
    phase8 = operator.split(
        "### Phase 8: Final Provider Recheck, Post, and Stable Envelope", 1
    )[1].split("## Terminal Result Schema", 1)[0]

    query_fields = (
        "url,number,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid"
    )
    for clause in (
        'gh pr view "$PR" --repo "$REPO"',
        f"--json {query_fields}",
        '"$WORK_DIR/final-provider-identity.json"',
        "state=OPEN",
        "exact Phase 0 draft flag",
        "baseRefName=$BASE_BRANCH",
        "baseRefOid=$BASE_SHA",
        "headRefName=$HEAD_BRANCH",
        "headRefOid=$HEAD_SHA",
        "Immediately before each existing-post identity reuse",
        "immediately before each review/comment mutation",
        "as the final preceding operation",
        "exact field equality",
        "BLOCKED:pr-review-stale-provider-state",
        "next reuse or mutation requires a fresh recheck",
    ):
        assert clause in phase8
    posting_index = phase8.index(
        "Only then post the prepared review and comment payloads"
    )
    assert phase8.index('gh pr view "$PR" --repo "$REPO"') < posting_index
    assert (
        phase8.index("Immediately before each existing-post identity reuse")
        < posting_index
    )
    assert phase8.index("as the final preceding operation") < posting_index


def test_rca_requires_failing_test_trigger_command_before_routing():
    sidecar = yaml.safe_load(
        (REPO_ROOT / "contracts/operators/rca-orchestrator.yaml").read_text()
    )
    trigger_command = next(
        row for row in sidecar["inputs"] if row["name"] == "trigger_command"
    )
    operator = (REPO_ROOT / "agents/rca-orchestrator.md").read_text()

    assert trigger_command["required"] is False
    assert "required for `trigger_type=failing_test`" in trigger_command["description"]
    assert "require a non-empty `trigger_command` before routing" in operator
    assert "BLOCKED:missing-trigger-command" in operator
