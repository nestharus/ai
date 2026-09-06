#!/usr/bin/env python3
"""Executable validators for merge and refactoring orchestration contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


_REPO_ROOT = Path(__file__).resolve().parents[1]


class ContractValidationError(ValueError):
    """Raised when an operational contract cannot authorize its next action."""

    def __init__(self, decision: dict[str, Any]):
        super().__init__("; ".join(decision.get("errors", [])) or "contract rejected")
        self.decision = decision


_FULL_OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_FIELDS = (
    "pr_url",
    "pr_number",
    "state",
    "is_draft",
    "base_ref_name",
    "base_ref_oid",
    "head_ref_name",
    "head_ref_oid",
)
_IDENTITY_FIELDS = (
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
_PACKAGE_FIELDS = {
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
}
_REQUIRED_PACKAGE_GATES = {
    "implementation-pipeline-phase-4",
    "implementation-pipeline-phase-6",
    "implementation-pipeline-phase-7",
    "implementation-pipeline-phase-8",
}
_ATTEMPT_PROOF_ROOT_FIELD = "proof_envelope_root"
_ATTEMPT_PROOF_SUFFIX = ".proof.json"
_ATTEMPT_FIELDS = {
    "ticket_id",
    "attempt_number",
    "owning_route",
    "dependency_proofs",
    "dispatch_base_sha",
    "reviewed_base_sha",
    "reviewed_head_sha",
    "pre_merge_feature_sha",
    "pre_merge_head_sha",
    "merge_sha",
    "resulting_feature_sha",
    "process_verdict",
    "state",
    "proof_envelope_path",
    "proof_envelope_sha256",
}
_ACCEPTED_ATTEMPT_BASE_FIELDS = {
    "ticket_id",
    "attempt_number",
    "merge_sha",
    "reachable_from_current_feature",
}
_LINEAGE_ARTIFACT_FIELDS = (
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
)
_LINEAGE_CONSTRUCTION_ORDER = [
    "route-evidence",
    "pre-audit-process-proof",
    "independent-process-audit",
    "final-process-proof",
    "common-process-validation",
    "pre-ready-currentness",
    "attempt-acceptance",
]
_PROCESS_TREE_AUDIT_BINDING_PREFIX = "PROCESS_TREE_AUDIT_BINDING_JSON="
_PROCESS_TREE_AUDIT_BINDING_FIELDS = {
    "schema",
    "mode",
    "report_identity",
    "operator_artifact",
    "audit_history",
    "root_invocation_uuid",
    "subtree_root_uuid",
    "expected_process",
    "process_tree",
    "companion_artifacts",
}
_PROCESS_TREE_AUDIT_REPORT_IDENTITY_FIELDS = {"schema", "path", "operator_file"}
_PROCESS_TREE_AUDIT_ARTIFACT_FIELDS = {"path", "sha256"}
_ROUTE_EVIDENCE_FIELDS = {
    "schema",
    "ticket_id",
    "ticket_system",
    "ticket_site_url",
    "attempt_number",
    "owning_route",
    "route_output",
    "ticket_operation_result",
    "provider_reviewed_identity",
    "reviewed_base_sha",
    "reviewed_head_sha",
    "verdict",
}
_TICKET_OPERATION_RESULT_REF_FIELDS = {"path", "sha256"}
_TICKET_OPERATION_EXPECTED_CONTEXT_FIELDS = {
    "schema",
    "backend",
    "ticket_site_url",
    "ticket_key",
    "operation",
    "owning_route",
    "attempt_number",
    "pr_url",
    "pr_number",
    "reviewed_base_branch",
    "reviewed_base_ref",
    "reviewed_base_sha",
    "reviewed_head_branch",
    "reviewed_head_ref",
    "reviewed_head_sha",
}
_TICKET_OPERATION_EXPECTED_RESULT_FIELDS = (
    "backend",
    "ticket_key",
    "operation",
    "owning_route",
    "attempt_number",
    "pr_url",
    "pr_number",
    "reviewed_base_branch",
    "reviewed_base_ref",
    "reviewed_base_sha",
    "reviewed_head_branch",
    "reviewed_head_ref",
    "reviewed_head_sha",
)
_TICKET_OPERATION_RESULT_FIELDS = {
    "schema",
    "backend",
    "ticket_key",
    "operation",
    "status",
    "owning_route",
    "attempt_number",
    "pr_url",
    "pr_number",
    "reviewed_base_branch",
    "reviewed_base_ref",
    "reviewed_base_sha",
    "reviewed_head_branch",
    "reviewed_head_ref",
    "reviewed_head_sha",
    "comment_body_sha256",
    "remote_comment_id",
    "remote_comment_url",
    "readback_status",
    "readback_ticket_key",
    "readback_comment_id",
    "readback_comment_url",
    "readback_body_sha256",
    "producer_operator",
    "producer_invocation_uuid",
    "producer_log_path",
    "producer_log_sha256",
    "producer_output_path",
    "producer_output_sha256",
}
_TICKET_OPERATION_PRODUCER_LOG_FIELDS = {
    "schema",
    "backend",
    "ticket_key",
    "operation",
    "status",
    "producer_operator",
    "producer_invocation_uuid",
    "comment_body_sha256",
    "remote_comment_id",
    "remote_comment_url",
    "readback_status",
    "readback_ticket_key",
    "readback_comment_id",
    "readback_comment_url",
    "readback_body_sha256",
}
_TICKET_OPERATION_PRODUCER_OUTPUT_FIELDS = {
    "schema",
    "backend",
    "ticket_key",
    "status",
    "comment_id",
    "comment_url",
    "body_sha256",
}
_IMPLEMENTATION_ROUTE_OUTPUT_REQUIRED_FIELDS = {
    "schema",
    "status",
    "ticket_id",
    "ticket_system",
    "owning_route",
    "route_attempt_number",
    "pr_url",
    "pr_number",
    "state",
    "is_draft",
    "phase_8_reviewed_is_draft",
    "base_branch",
    "base_ref",
    "head_branch",
    "head_ref",
    "phase_8_reviewed_base_sha",
    "phase_8_reviewed_head_sha",
    "phase_9_currentness_result",
    "ticket_operation_expected_context_path",
    "ticket_operation_expected_context_sha256",
    "ticket_operation_result_path",
    "ticket_operation_result_sha256",
    "owned_process_proofs",
}
_OWNED_PROCESS_PROOF_FIELDS = {
    "owner",
    "stage",
    "expected_process_path",
    "expected_process_sha256",
    "process_tree_path",
    "process_tree_sha256",
    "process_tree_audit_path",
    "process_tree_audit_sha256",
}
_IMPLEMENTATION_PROCESS_PROOF_STAGES = ("phase-4", "phase-6", "phase-8")
_ROUTE_PROCESS_EXPECTED_FIELDS = {
    "schema",
    "stage",
    "feature_invocation_uuid",
    "local_coverage_command_sha256",
    "ticket_id",
    "attempt_number",
    "owning_route",
    "expected_direct_operator",
    "expected_direct_model",
    "child_result_schema",
    "child_result_path",
    "child_result_sha256_join_field",
    "route_invocation_uuid_join_field",
    "nodes",
}
_ROUTE_PROCESS_DISPATCH_FIELDS = {
    "schema",
    "stage",
    "feature_invocation_uuid",
    "local_coverage_command_sha256",
    "ticket_id",
    "attempt_number",
    "owning_route",
    "expected_direct_operator",
    "expected_direct_model",
    "child_result_schema",
    "child_result_path",
    "child_result_sha256",
    "route_invocation_uuid",
    "expected_process_path",
    "expected_process_sha256",
    "nodes",
}
_ROUTE_PROCESS_EXPECTED_NODE_FIELDS = {
    "id",
    "required",
    "operator_or_role",
    "model",
    "parent",
    "prompt_path",
    "prompt_sha256",
    "log_path",
    "log_sha256_join_field",
    "canonical_output_path",
    "canonical_output_sha256_join_field",
    "output_mode",
}
_ROUTE_PROCESS_DISPATCH_NODE_FIELDS = {
    "id",
    "invocation_uuid",
    "parent_invocation_uuid",
    "operator_or_role",
    "model",
    "provider_source",
    "prompt_path",
    "prompt_sha256",
    "log_path",
    "log_sha256",
    "canonical_output_path",
    "canonical_output_sha256",
    "output_mode",
}
_ROUTE_KIND_SPECS = {
    "implementation-pipeline": {
        "operator": "implementation-pipeline-orchestrator",
        "model": "gpt-xhigh",
        "result_schema": "implementation-pipeline-result-v1",
    },
    "refactoring": {
        "operator": "refactoring-orchestrator",
        "model": "gpt-xhigh",
        "result_schema": "refactoring-route-result-v1",
    },
}
_ROUTE_PROCESS_STAGE_NODES = {
    "pre-audit": ("route-child",),
    "final": ("route-child", "independent-process-auditor"),
}
_ROUTE_PROOF_ARTIFACT_FIELDS = (
    "route_prompt",
    "route_log",
    "child_result",
    "route_evidence",
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
)
_ROUTE_ATTEMPT_PROOF_FIELDS = {
    "schema",
    "feature_branch",
    "local_coverage_command_sha256",
    "ticket_id",
    "attempt_number",
    "owning_route",
    *_ROUTE_PROOF_ARTIFACT_FIELDS,
    "child_owned_process_proofs",
    "common_validation_result",
    "route_specific_evidence",
}
_CHILD_PROCESS_PROOF_REF_FIELDS = {"owner", "stage", "artifact", "path", "sha256"}
_ROUTE_OUTCOME_EVIDENCE_FIELDS = {
    "schema",
    "feature_branch",
    "ticket_id",
    "attempt_number",
    "owning_route",
    "state",
    "dispatch_base_sha",
    "reviewed_base_sha",
    "reviewed_head_sha",
    "pre_merge_feature_sha",
    "pre_merge_head_sha",
    "merge_sha",
    "resulting_feature_sha",
    "child_result",
    "merge_authorization",
}
_REFACTORING_ROUTE_RESULT_FIELDS = {
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
_REFACTORING_ROUTE_CHILD_FIELDS = {
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
_REFACTORING_AUDITOR_ROLES = (
    "cohesion-auditor",
    "coupling-auditor",
    "function-classification-auditor",
    "push-pull-auditor",
    "validation-integrity-auditor",
)
_REFACTORING_AUDITOR_INDEX_FIELDS = {
    "schema",
    "owning_route",
    "refactoring_invocation_uuid",
    "feature_branch",
    "ticket_id",
    "attempt_number",
    "auditor_baseline_sha",
    "pre_merge_current_head",
    "post_merge_current_head",
    "pre_merge_reports",
    "post_merge_reports",
}
_REFACTORING_AUDITOR_REPORT_FIELDS = {
    "role",
    "stage",
    "report_path",
    "report_sha256",
    "verdict",
    "round",
    "baseline_sha",
    "current_head_sha",
}
_ACCEPTANCE_FIELDS = {
    "schema",
    "feature_branch",
    "ticket_id",
    "attempt_number",
    "owning_route",
    "construction_order",
    *_LINEAGE_ARTIFACT_FIELDS,
    "provider_reviewed_identity",
    "pre_ready_currentness",
}
_FORBIDDEN_FUTURE_HASH_FIELDS = {
    "acceptance_sha256",
    "acceptance_envelope_sha256",
    "attempt_process_audit_sha256",
    "attempt_process_report_sha256",
    "self_sha256",
}
_INVOCATION_PREFIX = b"OULIPOLY_INVOCATION="
_SESSION_PREFIX = b"OULIPOLY_SESSION="
_RESULT_PREFIX = b"OULIPOLY_RESULT="
_FAILURE_PREFIX = b"OULIPOLY_FAILURE="
_READY_STATE_OWNERS = {
    "feature-direct-merge": "REPLAY_REQUIRED",
    "implementation-auto-merge": "RETURN_TO_PHASE_8",
    "refactoring-owner-merge": "RETURN_TO_PHASE_8",
}
_PR_REVIEW_RUN_FIELDS = {
    "schema",
    "run_id",
    "pr_number",
    "invocation_uuid",
    "source_repo_root",
    "review_root",
    "run_root",
    "worktree_path",
    "worktree_ownership_path",
    "base_ref",
    "head_ref",
    "base_sha",
    "head_sha",
}
_PR_REVIEW_OWNERSHIP_FIELDS = {
    "schema",
    "run_id",
    "invocation_uuid",
    "source_repo_root",
    "run_root",
    "worktree_path",
    "head_sha",
}
_TEST_AUDIT_NODE_SPECS = {
    "spec-alignment": ("ad-hoc-spec-alignment", "gpt-high"),
    "test-quality": ("coverage-auditor", "gpt-xhigh"),
    "coverage-delta": ("coverage-analyzer", "gpt-high"),
}
_TEST_AUDIT_NODE_FIELDS = {
    "id",
    "required",
    "operator_or_role",
    "model",
    "parent",
    "prompt_path",
    "prompt_sha256",
    "log_path",
    "log_sha256_join_field",
    "canonical_output_path",
    "canonical_output_sha256_join_field",
    "extraction_metadata_path",
    "extraction_metadata_sha256_join_field",
    "provider_source_join_field",
    "output_mode",
}
_TEST_AUDIT_CHILD_FIELDS = {
    "id",
    "invocation_uuid",
    "parent_invocation_uuid",
    "operator_or_role",
    "model",
    "provider_source",
    "prompt_path",
    "prompt_sha256",
    "log_path",
    "log_sha256",
    "canonical_output_path",
    "canonical_output_sha256",
    "extraction_metadata_path",
    "extraction_metadata_sha256",
    "output_mode",
}
_TEST_AUDIT_PROOF_FIELDS = {
    "schema",
    "test_audit_invocation_uuid",
    "base_sha",
    "head_sha",
    "expected_process_path",
    "expected_process_sha256",
    "dispatch_evidence_path",
    "dispatch_evidence_sha256",
    "process_tree_path",
    "process_tree_sha256",
    "process_tree_audit_prompt_path",
    "process_tree_audit_prompt_sha256",
    "process_tree_audit_path",
    "process_tree_audit_sha256",
    "process_tree_audit_log_path",
    "process_tree_audit_log_sha256",
    "child_artifacts",
    "verdict",
}
_TEST_AUDIT_RESULT_FIELDS = {
    "schema",
    "status",
    "mode",
    "test_audit_invocation_uuid",
    "base_branch",
    "base_ref",
    "base_sha",
    "head_branch",
    "head_ref",
    "head_sha",
    "merge_base_sha",
    "diff_sha256",
    "gate_report_path",
    "gate_report_sha256",
    "nested_proof_path",
    "nested_proof_sha256",
    "nested_proof_validation_path",
    "nested_proof_validation_sha256",
    "nested_process_proof",
}
def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractValidationError(
                {"status": "INVALID", "errors": [f"duplicate JSON key: {key}"]}
            )
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(
            {"status": "INVALID", "errors": [f"cannot read JSON {path}: {exc}"]}
        ) from exc
    if not isinstance(value, dict):
        raise ContractValidationError(
            {"status": "INVALID", "errors": [f"JSON root must be an object: {path}"]}
        )
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = (
        {
            "schema": value["schema"],
            **{key: value[key] for key in sorted(value) if key != "schema"},
        }
        if "schema" in value
        else {key: value[key] for key in sorted(value)}
    )
    payload = json.dumps(ordered, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_uuid(value: Any, label: str) -> str:
    if not _nonblank(value):
        raise ContractValidationError(
            {"status": "INVALID", "errors": [f"{label} must be a canonical UUID"]}
        )
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ContractValidationError(
            {"status": "INVALID", "errors": [f"{label} must be a canonical UUID"]}
        ) from exc
    if str(parsed) != value:
        raise ContractValidationError(
            {"status": "INVALID", "errors": [f"{label} must be a canonical UUID"]}
        )
    return value


def _parse_envelope_json(line: bytes, prefix: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = line.removeprefix(prefix).decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ContractValidationError) as exc:
        raise ContractValidationError(
            {"status": "INVALID", "errors": [f"malformed {label} marker"]}
        ) from exc
    if not isinstance(value, dict):
        raise ContractValidationError(
            {"status": "INVALID", "errors": [f"{label} marker must contain an object"]}
        )
    return value


def extract_provider_payload(log_path: Path, output_path: Path) -> dict[str, Any]:
    """Extract one successful provider payload from a complete runner log."""

    try:
        log_identity = log_path.resolve(strict=True)
        output_identity = output_path.resolve(strict=False)
        stream = log_path.read_bytes()
    except OSError as exc:
        raise ContractValidationError(
            {"status": "INVALID", "errors": [f"cannot read runner log {log_path}: {exc}"]}
        ) from exc
    if log_identity == output_identity:
        raise ContractValidationError(
            {
                "status": "INVALID",
                "errors": ["runner log and canonical output paths must be distinct"],
            }
        )

    lines = stream.splitlines(keepends=True)
    invocation_lines = [
        index for index, line in enumerate(lines) if line.startswith(_INVOCATION_PREFIX)
    ]
    session_lines = [
        index for index, line in enumerate(lines) if line.startswith(_SESSION_PREFIX)
    ]
    result_lines = [
        index for index, line in enumerate(lines) if line.startswith(_RESULT_PREFIX)
    ]
    failure_lines = [
        index for index, line in enumerate(lines) if line.startswith(_FAILURE_PREFIX)
    ]
    errors: list[str] = []
    if stream.count(_INVOCATION_PREFIX) != 1 or len(invocation_lines) != 1:
        errors.append("runner log must contain exactly one invocation marker")
    if stream.count(_RESULT_PREFIX) != 1 or len(result_lines) != 1:
        errors.append("runner log must contain exactly one terminal result sentinel")
    if stream.count(_FAILURE_PREFIX) or failure_lines:
        errors.append("runner log must not contain a failure sentinel")
    session_occurrences = stream.count(_SESSION_PREFIX)
    if session_occurrences != len(session_lines):
        errors.append("session marker must occupy its own runner-log line")
    if session_occurrences > 1 or len(session_lines) > 1:
        errors.append("runner log must contain at most one session marker")
    if errors:
        raise ContractValidationError({"status": "INVALID", "errors": errors})

    invocation_index = invocation_lines[0]
    result_index = result_lines[0]
    if invocation_index >= result_index:
        raise ContractValidationError(
            {
                "status": "INVALID",
                "errors": ["invocation marker must precede the terminal result sentinel"],
            }
        )
    if any(line.strip() for line in lines[:invocation_index]):
        raise ContractValidationError(
            {
                "status": "INVALID",
                "errors": ["runner log contains content before the invocation marker"],
            }
        )
    if result_index != len(lines) - 1:
        raise ContractValidationError(
            {
                "status": "INVALID",
                "errors": ["result sentinel must be the terminal runner-log line"],
            }
        )

    invocation_line = lines[invocation_index].rstrip(b"\r\n")
    result_line = lines[result_index].rstrip(b"\r\n")
    invocation = _parse_envelope_json(
        invocation_line, _INVOCATION_PREFIX, "invocation"
    )
    result = _parse_envelope_json(result_line, _RESULT_PREFIX, "result")
    invocation_id = _canonical_uuid(invocation.get("id"), "invocation marker id")
    session: dict[str, Any] | None = None
    payload_start = invocation_index + 1
    if session_lines:
        session_index = session_lines[0]
        if session_index != invocation_index + 1:
            errors.append(
                "session marker must immediately follow the invocation marker before provider payload"
            )
        else:
            session_line = lines[session_index].rstrip(b"\r\n")
            session = _parse_envelope_json(session_line, _SESSION_PREFIX, "session")
            if session.get("agent_runner_invocation_id") != invocation_id:
                errors.append(
                    "session agent_runner_invocation_id must equal the invocation marker id"
                )
            payload_start = session_index + 1
    if not _nonblank(invocation.get("source")):
        errors.append("invocation marker source must be a non-blank string")
    if result.get("id") != invocation_id:
        errors.append("result id must equal the invocation marker id")
    if result.get("status") != "succeeded":
        errors.append("result status must equal succeeded")
    if result.get("success") is not True:
        errors.append("result success must equal true")
    if result.get("exit_code") != 0:
        errors.append("result exit_code must equal zero")
    if errors:
        raise ContractValidationError({"status": "INVALID", "errors": errors})

    payload = b"".join(lines[payload_start:result_index])
    if not payload.strip():
        raise ContractValidationError(
            {"status": "INVALID", "errors": ["provider payload must not be empty"]}
        )
    first_line = payload.splitlines()[0]
    if first_line.startswith(
        (_INVOCATION_PREFIX, _SESSION_PREFIX, _RESULT_PREFIX, _FAILURE_PREFIX)
    ):
        raise ContractValidationError(
            {
                "status": "INVALID",
                "errors": ["provider payload must begin with its own canonical content"],
            }
        )

    _write_bytes(output_path, payload)
    return {
        "schema": "runner-provider-extraction-v1",
        "status": "VALID",
        "invocation_uuid": invocation_id,
        "provider_source": invocation["source"],
        "log_path": str(log_path),
        "log_sha256": hashlib.sha256(stream).hexdigest(),
        "output_path": str(output_path),
        "output_sha256": hashlib.sha256(payload).hexdigest(),
        "session": session,
        "result": result,
    }


def initialize_pr_review_run(
    review_root: Path,
    source_repo_root: Path,
    pr_number: int,
    base_sha: str,
    head_sha: str,
    invocation_uuid: str,
) -> dict[str, Any]:
    """Allocate one immutable PR-review run root and its owned checkout identity."""

    errors: list[str] = []
    canonical_review_root, review_errors = _canonical_absolute_path(
        str(review_root), "review_root"
    )
    canonical_repo_root, repo_errors = _canonical_absolute_path(
        str(source_repo_root), "source_repo_root"
    )
    errors.extend(review_errors)
    errors.extend(repo_errors)
    if not isinstance(pr_number, int) or pr_number <= 0:
        errors.append("pr_number must be a positive integer")
    for value, label in ((base_sha, "base_sha"), (head_sha, "head_sha")):
        if not isinstance(value, str) or not _FULL_OID.fullmatch(value):
            errors.append(f"{label} must be a full lowercase Git OID")
    try:
        invocation_uuid = _canonical_uuid(invocation_uuid, "invocation_uuid")
    except ContractValidationError as exc:
        errors.extend(exc.decision["errors"])
    if errors:
        raise ContractValidationError({"status": "INVALID", "errors": errors})
    assert canonical_review_root is not None
    assert canonical_repo_root is not None

    run_id = (
        f"pr-{pr_number}-base-{base_sha}-head-{head_sha}-inv-{invocation_uuid}"
    )
    run_root = Path(canonical_review_root) / "runs" / run_id
    worktree_path = run_root / "head-worktree"
    ownership_path = run_root / "worktree-ownership.json"
    private_root = f"refs/pr-review/{pr_number}/runs/{run_id}"
    manifest = {
        "schema": "pr-review-run-v1",
        "run_id": run_id,
        "pr_number": pr_number,
        "invocation_uuid": invocation_uuid,
        "source_repo_root": canonical_repo_root,
        "review_root": canonical_review_root,
        "run_root": str(run_root),
        "worktree_path": str(worktree_path),
        "worktree_ownership_path": str(ownership_path),
        "base_ref": f"{private_root}/base",
        "head_ref": f"{private_root}/head",
        "base_sha": base_sha,
        "head_sha": head_sha,
    }
    ownership = {
        "schema": "pr-review-worktree-ownership-v1",
        "run_id": run_id,
        "invocation_uuid": invocation_uuid,
        "source_repo_root": canonical_repo_root,
        "run_root": str(run_root),
        "worktree_path": str(worktree_path),
        "head_sha": head_sha,
    }

    run_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_root.mkdir()
    except FileExistsError as exc:
        raise ContractValidationError(
            {
                "status": "INVALID",
                "errors": [f"immutable PR-review run already exists: {run_root}"],
            }
        ) from exc
    try:
        _write_json(ownership_path, ownership)
        _write_json(run_root / "pr-review-run.json", manifest)
    except BaseException:
        for path in (ownership_path, run_root / "pr-review-run.json"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        try:
            run_root.rmdir()
        except OSError:
            pass
        raise
    return manifest


def cleanup_pr_review_worktree(
    run_manifest: dict[str, Any], terminal_artifact: Path
) -> dict[str, Any]:
    """Remove only the clean detached worktree owned by one durable review run."""

    errors: list[str] = []
    if set(run_manifest) != _PR_REVIEW_RUN_FIELDS:
        errors.append(
            "PR-review run fields must exactly equal: "
            + ",".join(sorted(_PR_REVIEW_RUN_FIELDS))
        )
    if run_manifest.get("schema") != "pr-review-run-v1":
        errors.append("PR-review run schema must equal pr-review-run-v1")
    run_root_value, run_root_errors = _canonical_absolute_path(
        run_manifest.get("run_root"), "run_root"
    )
    worktree_value, worktree_errors = _canonical_absolute_path(
        run_manifest.get("worktree_path"), "worktree_path"
    )
    source_value, source_errors = _canonical_absolute_path(
        run_manifest.get("source_repo_root"), "source_repo_root"
    )
    errors.extend(run_root_errors)
    errors.extend(worktree_errors)
    errors.extend(source_errors)
    if run_root_value and worktree_value:
        worktree_path = Path(worktree_value)
        if worktree_path.parent != Path(run_root_value) or worktree_path.name != "head-worktree":
            errors.append("worktree_path must be the exact head-worktree child of run_root")
    ownership_path = Path(str(run_manifest.get("worktree_ownership_path", "")))
    try:
        ownership = _load_json(ownership_path)
    except ContractValidationError as exc:
        errors.extend(exc.decision["errors"])
        ownership = {}
    if ownership and set(ownership) != _PR_REVIEW_OWNERSHIP_FIELDS:
        errors.append(
            "worktree ownership fields must exactly equal: "
            + ",".join(sorted(_PR_REVIEW_OWNERSHIP_FIELDS))
        )
    for field in _PR_REVIEW_OWNERSHIP_FIELDS - {"schema"}:
        if ownership.get(field) != run_manifest.get(field):
            errors.append(f"worktree ownership mismatch: {field}")
    if ownership.get("schema") != "pr-review-worktree-ownership-v1":
        errors.append("worktree ownership schema is invalid")

    try:
        terminal_identity = terminal_artifact.resolve(strict=True)
    except OSError as exc:
        errors.append(f"terminal artifact must exist before cleanup: {exc}")
        terminal_identity = None
    if terminal_identity is not None and run_root_value is not None:
        if terminal_identity.parent != Path(run_root_value):
            errors.append("terminal artifact must be a direct child of the owned run root")
    if errors:
        raise ContractValidationError({"status": "INVALID", "errors": errors})
    assert source_value is not None
    assert worktree_value is not None

    listing = subprocess.run(
        ["git", "-C", source_value, "worktree", "list", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    registered = {
        line.removeprefix("worktree ")
        for line in listing.stdout.splitlines()
        if line.startswith("worktree ")
    }
    if listing.returncode != 0 or worktree_value not in registered:
        errors.append("owned worktree is not registered in source_repo_root")
    observed_head = subprocess.run(
        ["git", "-C", worktree_value, "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if observed_head.returncode != 0 or observed_head.stdout.strip() != run_manifest.get(
        "head_sha"
    ):
        errors.append("owned worktree HEAD does not equal the run head SHA")
    dirty = subprocess.run(
        ["git", "-C", worktree_value, "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    if dirty.returncode != 0 or dirty.stdout:
        errors.append("owned worktree must be clean before non-forced cleanup")
    if errors:
        raise ContractValidationError({"status": "INVALID", "errors": errors})

    removed = subprocess.run(
        ["git", "-C", source_value, "worktree", "remove", worktree_value],
        check=False,
        capture_output=True,
        text=True,
    )
    if removed.returncode != 0:
        raise ContractValidationError(
            {
                "status": "INVALID",
                "errors": [f"safe worktree removal failed: {removed.stderr.strip()}"],
            }
        )
    return {
        "schema": "pr-review-worktree-cleanup-v1",
        "status": "REMOVED",
        "run_id": run_manifest["run_id"],
        "invocation_uuid": run_manifest["invocation_uuid"],
        "worktree_path": worktree_value,
        "head_sha": run_manifest["head_sha"],
        "terminal_artifact_path": str(terminal_artifact),
        "terminal_artifact_sha256": _sha256_file(terminal_artifact),
        "private_refs_preserved": [run_manifest["base_ref"], run_manifest["head_ref"]],
    }


def _current_artifact(
    record: dict[str, Any],
    path_field: str,
    hash_field: str,
    errors: list[str],
    *,
    label: str,
) -> Path | None:
    canonical, path_errors = _canonical_absolute_path(record.get(path_field), path_field)
    errors.extend(path_errors)
    recorded_hash = record.get(hash_field)
    if not isinstance(recorded_hash, str) or not _SHA256.fullmatch(recorded_hash):
        errors.append(f"{hash_field} must be a lowercase SHA-256")
        recorded_hash = None
    if canonical is None:
        return None
    path = Path(canonical)
    try:
        current_hash = _sha256_file(path)
    except OSError as exc:
        errors.append(f"cannot hash {label} {path}: {exc}")
        return path
    if recorded_hash is not None and current_hash != recorded_hash:
        errors.append(f"{label} hash mismatch")
    return path


def render_process_tree_audit_report(
    binding: dict[str, Any], verdict: str, *, body: str = ""
) -> str:
    """Render the canonical header-first process-audit report envelope."""

    report_identity = binding["report_identity"]
    subtree = binding["subtree_root_uuid"] or "none"
    suffix = f"\n{body.rstrip()}\n" if body.strip() else "\n"
    return (
        "# Process Tree Audit\n\n"
        f"Operator/workflow: {report_identity['operator_file']}\n"
        f"Root invocation UUID: {binding['root_invocation_uuid']}\n"
        f"Subtree root UUID: {subtree}\n"
        f"Trace JSON: {binding['process_tree']['path']}\n"
        f"Expected process: {binding['expected_process']['path']}\n"
        f"Verdict: {verdict}\n\n"
        "## Machine Binding\n"
        f"{_PROCESS_TREE_AUDIT_BINDING_PREFIX}"
        f"{_canonical_json(binding).decode('utf-8')}\n"
        f"{suffix}"
    )


def _trace_nodes(
    node: Any, errors: list[str], *, location: str = "root"
) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        errors.append(f"process tree {location} must be an object")
        return []
    invocation = node.get("invocation")
    children = node.get("children")
    if not isinstance(invocation, dict):
        errors.append(f"process tree {location}.invocation must be an object")
        invocation = {}
    if not isinstance(children, list):
        errors.append(f"process tree {location}.children must be a list")
        children = []
    flattened = [{"node": node, "invocation": invocation, "location": location}]
    for index, child in enumerate(children):
        flattened.extend(
            _trace_nodes(child, errors, location=f"{location}.children[{index}]")
        )
    return flattened


def _validate_process_tree_binding_artifact(
    value: Any, label: str, errors: list[str]
) -> Path | None:
    if not isinstance(value, dict) or set(value) != _PROCESS_TREE_AUDIT_ARTIFACT_FIELDS:
        errors.append(f"{label} binding fields must exactly equal path,sha256")
        return None
    return _current_artifact(value, "path", "sha256", errors, label=label)


def _load_process_tree_audit_report(
    report_path: Path, errors: list[str]
) -> tuple[str | None, dict[str, Any]]:
    try:
        report_identity = report_path.resolve(strict=True)
        lines = report_identity.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"cannot read process audit report {report_path}: {exc}")
        return None, {}

    nonblank = [line for line in lines if line]
    identity_prefixes = (
        "Operator/workflow: ",
        "Root invocation UUID: ",
        "Subtree root UUID: ",
        "Trace JSON: ",
        "Expected process: ",
    )
    if not lines or lines[0] != "# Process Tree Audit":
        errors.append("process audit report must begin with # Process Tree Audit")
    if len(nonblank) < 7 or nonblank[0] != "# Process Tree Audit":
        errors.append("process audit report canonical identity envelope is incomplete")
    else:
        for index, prefix in enumerate(identity_prefixes, start=1):
            if not nonblank[index].startswith(prefix):
                errors.append(
                    "process audit report identity lines must immediately follow the header in canonical order"
                )
                break
        if not nonblank[6].startswith("Verdict: "):
            errors.append("process audit report verdict must follow the identity lines")

    verdict_lines = [line for line in lines if line.lstrip().startswith("Verdict:")]
    verdict = None
    if len(verdict_lines) != 1:
        errors.append("process audit report must contain exactly one canonical Verdict line")
    elif verdict_lines[0] not in {
        "Verdict: PASS",
        "Verdict: FAIL",
        "Verdict: NEEDS_INPUT",
    }:
        errors.append("process audit report canonical verdict is invalid")
    else:
        verdict = verdict_lines[0].removeprefix("Verdict: ")

    binding_lines = [
        line for line in lines if line.startswith(_PROCESS_TREE_AUDIT_BINDING_PREFIX)
    ]
    if lines.count("## Machine Binding") != 1 or len(binding_lines) != 1:
        errors.append(
            "process audit report must contain exactly one canonical machine-binding section"
        )
        return verdict, {}
    section_index = lines.index("## Machine Binding")
    next_heading = next(
        (
            index
            for index in range(section_index + 1, len(lines))
            if lines[index].startswith("## ")
        ),
        len(lines),
    )
    section_lines = [line for line in lines[section_index + 1 : next_heading] if line]
    if section_lines != binding_lines:
        errors.append("process audit machine-binding section must contain only its binding row")
    payload = binding_lines[0].removeprefix(_PROCESS_TREE_AUDIT_BINDING_PREFIX)
    try:
        binding = json.loads(payload, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, ContractValidationError) as exc:
        errors.append(f"process audit report machine binding is invalid: {exc}")
        return verdict, {}
    if not isinstance(binding, dict) or set(binding) != _PROCESS_TREE_AUDIT_BINDING_FIELDS:
        errors.append(
            "process audit machine-binding fields must exactly equal: "
            + ",".join(sorted(_PROCESS_TREE_AUDIT_BINDING_FIELDS))
        )
        return verdict, {}
    if payload != _canonical_json(binding).decode("utf-8"):
        errors.append("process audit machine binding must use canonical JSON")
    if binding.get("schema") != "process-tree-audit-binding-v1":
        errors.append("process audit machine-binding schema is invalid")
    if binding.get("mode") not in {"blocking", "advisory"}:
        errors.append("process audit machine-binding mode is invalid")

    identity = binding.get("report_identity")
    if (
        not isinstance(identity, dict)
        or set(identity) != _PROCESS_TREE_AUDIT_REPORT_IDENTITY_FIELDS
    ):
        errors.append("process audit report identity fields are invalid")
        identity = {}
    else:
        if identity.get("schema") != "process-tree-audit-report-v1":
            errors.append("process audit report identity schema is invalid")
        if identity.get("path") != str(report_identity):
            errors.append("process audit report identity path mismatch")
        if not _nonblank(identity.get("operator_file")):
            errors.append("process audit report operator_file must be non-blank")

    operator_path = _validate_process_tree_binding_artifact(
        binding.get("operator_artifact"), "process audit operator artifact", errors
    )
    if operator_path is not None and identity:
        operator_file = identity.get("operator_file")
        if isinstance(operator_file, str):
            named_operator = Path(operator_file)
            if not named_operator.is_absolute():
                errors.append("process audit report operator_file must be an absolute path")
            else:
                try:
                    named_operator = named_operator.resolve(strict=True)
                except OSError as exc:
                    errors.append(
                        f"cannot resolve process audit report operator_file: {exc}"
                    )
                else:
                    if operator_path != named_operator:
                        errors.append("process audit operator artifact path mismatch")

    audit_history_value = binding.get("audit_history")
    audit_history_path = None
    if audit_history_value is not None:
        audit_history_path = _validate_process_tree_binding_artifact(
            audit_history_value, "process audit history", errors
        )

    try:
        root_uuid = _canonical_uuid(
            binding.get("root_invocation_uuid"), "process audit root_invocation_uuid"
        )
    except ContractValidationError as exc:
        errors.extend(exc.decision["errors"])
        root_uuid = ""
    subtree_uuid = binding.get("subtree_root_uuid")
    if subtree_uuid is not None:
        try:
            _canonical_uuid(subtree_uuid, "process audit subtree_root_uuid")
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])

    expected_path = _validate_process_tree_binding_artifact(
        binding.get("expected_process"), "process audit expected process", errors
    )
    trace_path = _validate_process_tree_binding_artifact(
        binding.get("process_tree"), "process audit process tree", errors
    )
    companions = binding.get("companion_artifacts")
    companion_paths: list[Path] = []
    if not isinstance(companions, list):
        errors.append("process audit companion_artifacts must be a list")
        companions = []
    for index, companion in enumerate(companions):
        path = _validate_process_tree_binding_artifact(
            companion, f"process audit companion_artifacts[{index}]", errors
        )
        if path is not None:
            companion_paths.append(path)
    companion_values = [str(path) for path in companion_paths]
    if companion_values != sorted(companion_values):
        errors.append("process audit companion artifact rows must be sorted by path")
    all_paths = [
        path
        for path in (operator_path, audit_history_path, expected_path, trace_path)
        if path is not None
    ]
    all_paths.extend(companion_paths)
    if len(all_paths) != len(set(all_paths)):
        errors.append("process audit bound artifact paths must be pairwise distinct")
    if report_identity in all_paths:
        errors.append("process audit machine binding must not hash-reference its own report")

    if trace_path is not None:
        try:
            trace = _load_json(trace_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
            trace = {}
        trace_nodes = _trace_nodes(trace.get("root"), errors)
        trace_ids = [node["invocation"].get("id") for node in trace_nodes]
        if trace.get("requested_id") != root_uuid:
            errors.append("process audit trace requested_id does not match binding root")
        if not trace_nodes or trace_nodes[0]["invocation"].get("id") != root_uuid:
            errors.append("process audit trace root invocation does not match binding root")
        if subtree_uuid is not None and trace_ids.count(subtree_uuid) != 1:
            errors.append("process audit subtree root must occur exactly once in the trace")

    bound_process_tree = binding.get("process_tree")
    bound_expected_process = binding.get("expected_process")
    expected_identity_lines = [
        f"Operator/workflow: {identity.get('operator_file')}",
        f"Root invocation UUID: {binding.get('root_invocation_uuid')}",
        f"Subtree root UUID: {subtree_uuid or 'none'}",
        f"Trace JSON: {bound_process_tree.get('path') if isinstance(bound_process_tree, dict) else None}",
        f"Expected process: {bound_expected_process.get('path') if isinstance(bound_expected_process, dict) else None}",
    ]
    if len(nonblank) >= 6 and nonblank[1:6] != expected_identity_lines:
        errors.append("process audit identity lines do not match the machine binding")
    return verdict, binding


def validate_process_tree_audit_report(report_path: Path) -> dict[str, Any]:
    """Validate one canonical producer-owned process-audit report and binding."""

    errors: list[str] = []
    verdict, binding = _load_process_tree_audit_report(report_path, errors)
    return {
        "schema": "process-tree-audit-report-validation-v1",
        "status": "VALID" if not errors else "INVALID",
        "verdict": verdict,
        "binding": binding,
        "errors": errors,
    }


def _successful_provider_payload(log_path: Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="operational-contract-log-") as directory:
        output = Path(directory) / "payload.txt"
        extract_provider_payload(log_path, output)
        return output.read_bytes()


def _test_audit_expected_nodes(
    expected: dict[str, Any], root_uuid: str, errors: list[str]
) -> dict[str, dict[str, Any]]:
    required_fields = {
        "schema",
        "test_audit_invocation_uuid",
        "base_sha",
        "head_sha",
        "nodes",
    }
    if set(expected) != required_fields:
        errors.append(
            "test-audit expected-process fields must exactly equal: "
            + ",".join(sorted(required_fields))
        )
    if expected.get("schema") != "test-audit-expected-process-v2":
        errors.append("test-audit expected-process schema is invalid")
    if expected.get("test_audit_invocation_uuid") != root_uuid:
        errors.append("expected-process root invocation UUID mismatch")
    nodes = expected.get("nodes")
    if not isinstance(nodes, list):
        errors.append("expected-process nodes must be a list")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or set(node) != _TEST_AUDIT_NODE_FIELDS:
            errors.append(f"expected-process nodes[{index}] fields are invalid")
            continue
        node_id = node.get("id")
        if (
            not isinstance(node_id, str)
            or node_id not in _TEST_AUDIT_NODE_SPECS
            or node_id in indexed
        ):
            errors.append(f"expected-process nodes[{index}] id is invalid or duplicate")
            continue
        operator, model = _TEST_AUDIT_NODE_SPECS[node_id]
        fixed = {
            "required": True,
            "operator_or_role": operator,
            "model": model,
            "parent": "root",
            "log_sha256_join_field": "log_sha256",
            "canonical_output_sha256_join_field": "canonical_output_sha256",
            "extraction_metadata_sha256_join_field": "extraction_metadata_sha256",
            "provider_source_join_field": "provider_source",
            "output_mode": "stdout-extracted",
        }
        for field, value in fixed.items():
            if node.get(field) != value:
                errors.append(f"expected-process {node_id}.{field} is invalid")
        _current_artifact(
            node,
            "prompt_path",
            "prompt_sha256",
            errors,
            label=f"expected-process {node_id} prompt",
        )
        for field in ("log_path", "canonical_output_path", "extraction_metadata_path"):
            _canonical, path_errors = _canonical_absolute_path(
                node.get(field), f"expected-process {node_id}.{field}"
            )
            errors.extend(path_errors)
        indexed[node_id] = node
    if list(indexed) != list(_TEST_AUDIT_NODE_SPECS):
        errors.append("expected-process nodes must equal the exact canonical child order")
    return indexed


def _test_audit_dispatch_nodes(
    dispatch: dict[str, Any],
    expected_nodes: dict[str, dict[str, Any]],
    root_uuid: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    required_fields = {
        "schema",
        "test_audit_invocation_uuid",
        "base_sha",
        "head_sha",
        "expected_process_path",
        "expected_process_sha256",
        "nodes",
    }
    if set(dispatch) != required_fields:
        errors.append(
            "test-audit dispatch-evidence fields must exactly equal: "
            + ",".join(sorted(required_fields))
        )
    if dispatch.get("schema") != "test-audit-dispatch-evidence-v2":
        errors.append("test-audit dispatch-evidence schema is invalid")
    if dispatch.get("test_audit_invocation_uuid") != root_uuid:
        errors.append("dispatch-evidence root invocation UUID mismatch")
    nodes = dispatch.get("nodes")
    if not isinstance(nodes, list):
        errors.append("dispatch-evidence nodes must be a list")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    all_paths: list[str] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or set(node) != _TEST_AUDIT_CHILD_FIELDS:
            errors.append(f"dispatch-evidence nodes[{index}] fields are invalid")
            continue
        node_id = node.get("id")
        expected_node = expected_nodes.get(node_id) if isinstance(node_id, str) else None
        if not isinstance(node_id, str) or expected_node is None or node_id in indexed:
            errors.append(f"dispatch-evidence nodes[{index}] id is invalid or duplicate")
            continue
        operator, model = _TEST_AUDIT_NODE_SPECS[node_id]
        if node.get("operator_or_role") != operator:
            errors.append(f"dispatch-evidence {node_id} operator mismatch")
        if node.get("model") != model:
            errors.append(f"dispatch-evidence {node_id} model mismatch")
        if not _nonblank(node.get("provider_source")):
            errors.append(f"dispatch-evidence {node_id} provider_source is invalid")
        if node.get("parent_invocation_uuid") != root_uuid:
            errors.append(f"dispatch-evidence {node_id} parent must equal root UUID")
        try:
            _canonical_uuid(node.get("invocation_uuid"), f"{node_id} invocation_uuid")
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
        for field in (
            "prompt_path",
            "log_path",
            "canonical_output_path",
            "extraction_metadata_path",
        ):
            if node.get(field) != expected_node.get(field):
                errors.append(f"dispatch-evidence {node_id}.{field} mismatch")
            if isinstance(node.get(field), str):
                all_paths.append(node[field])
        if node.get("output_mode") != "stdout-extracted":
            errors.append(f"dispatch-evidence {node_id} output mode is invalid")
        for stem, label in (
            ("prompt", "prompt"),
            ("log", "runner log"),
            ("canonical_output", "canonical output"),
            ("extraction_metadata", "extraction metadata"),
        ):
            _current_artifact(
                node,
                f"{stem}_path",
                f"{stem}_sha256",
                errors,
                label=f"dispatch-evidence {node_id} {label}",
            )
        indexed[node_id] = node
    if list(indexed) != list(_TEST_AUDIT_NODE_SPECS):
        errors.append("dispatch-evidence nodes must equal the exact canonical child order")
    if len(all_paths) != len(set(all_paths)):
        errors.append("test-audit child artifact paths must be pairwise distinct")
    return indexed


def _test_audit_bound_companions(
    proof: dict[str, Any], child_artifacts: list[Any]
) -> list[dict[str, Any]]:
    rows = [
        {
            "path": proof.get("dispatch_evidence_path"),
            "sha256": proof.get("dispatch_evidence_sha256"),
        },
        {
            "path": proof.get("process_tree_audit_prompt_path"),
            "sha256": proof.get("process_tree_audit_prompt_sha256"),
        },
    ]
    for child in child_artifacts:
        if not isinstance(child, dict):
            continue
        for stem in (
            "prompt",
            "log",
            "canonical_output",
            "extraction_metadata",
        ):
            rows.append(
                {
                    "path": child.get(f"{stem}_path"),
                    "sha256": child.get(f"{stem}_sha256"),
                }
            )
    return sorted(rows, key=lambda row: str(row.get("path")))


def _process_trace_entries(
    trace: dict[str, Any], root_uuid: str, errors: list[str], *, context: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if trace.get("requested_id") != root_uuid:
        errors.append(f"process tree requested_id must equal {context} root UUID")
    flattened = _trace_nodes(trace.get("root"), errors)
    if not flattened:
        errors.append(f"process tree must contain the {context} root node")
        return [], []
    root_invocation = flattened[0]["invocation"]
    if root_invocation.get("id") != root_uuid:
        errors.append(f"process tree root invocation id must equal {context} root UUID")

    all_ids = [entry["invocation"].get("id") for entry in flattened]
    duplicate_ids = sorted(
        {node_id for node_id in all_ids if node_id is not None and all_ids.count(node_id) > 1}
    )
    if duplicate_ids:
        errors.append(
            "process tree invocation UUIDs must be unique: " + ",".join(duplicate_ids)
        )

    root_node = flattened[0]["node"]
    root_children = root_node.get("children") if isinstance(root_node, dict) else None
    if not isinstance(root_children, list):
        return flattened, []
    direct_entries = [
        {"node": child, "invocation": child.get("invocation", {})}
        for child in root_children
        if isinstance(child, dict)
    ]
    return flattened, direct_entries


def _validate_bound_process_node(
    node_id: str,
    declared: dict[str, Any],
    matches: list[dict[str, Any]],
    direct_entries: list[dict[str, Any]],
    root_uuid: str,
    node_specs: dict[str, tuple[str, str]],
    errors: list[str],
    *,
    require_leaf: bool,
) -> None:
    child_uuid = declared.get("invocation_uuid")
    if len(matches) != 1:
        errors.append(f"process tree {node_id} invocation UUID must occur exactly once")
        return
    entry = matches[0]
    invocation = entry["invocation"]
    direct_ids = [direct["invocation"].get("id") for direct in direct_entries]
    if direct_ids.count(child_uuid) != 1:
        errors.append(f"process tree {node_id} must be one direct child of the root")
    if invocation.get("parent_id") != root_uuid:
        errors.append(f"process tree {node_id} actual parent must equal root UUID")
    expected_operator, expected_model = node_specs[node_id]
    if declared.get("operator_or_role") != expected_operator:
        errors.append(f"process tree {node_id} operator/role declaration mismatch")
    if declared.get("model") != expected_model:
        errors.append(f"process tree {node_id} declared model mismatch")
    if invocation.get("model_name") != expected_model:
        errors.append(f"process tree {node_id} actual model mismatch")
    if invocation.get("agent_runner_invocation_id") != child_uuid:
        errors.append(f"process tree {node_id} runner invocation identity mismatch")
    source = invocation.get("source")
    if not _nonblank(source):
        errors.append(f"process tree {node_id} actual source is invalid")
    if invocation.get("status") != "succeeded":
        errors.append(f"process tree {node_id} status must equal succeeded")
    if invocation.get("success") is not True:
        errors.append(f"process tree {node_id} success must equal true")
    if invocation.get("exit_code") != 0:
        errors.append(f"process tree {node_id} exit_code must equal zero")
    if not _nonblank(invocation.get("finished_at")):
        errors.append(f"process tree {node_id} must be terminal with finished_at")
    if require_leaf and entry["node"].get("children"):
        errors.append(f"process tree {node_id} must not contain nested children")

    log_path = declared.get("log_path")
    output_path = declared.get("canonical_output_path")
    if not isinstance(log_path, str) or not isinstance(output_path, str):
        return
    try:
        with tempfile.TemporaryDirectory(prefix="process-trace-payload-") as directory:
            extracted_path = Path(directory) / "provider-output"
            metadata = extract_provider_payload(Path(log_path), extracted_path)
            extracted = extracted_path.read_bytes()
    except (OSError, ContractValidationError) as exc:
        detail = exc.decision["errors"] if isinstance(exc, ContractValidationError) else [str(exc)]
        errors.extend(f"process tree {node_id} runner log: {error}" for error in detail)
        return
    if metadata.get("invocation_uuid") != child_uuid:
        errors.append(f"process tree {node_id} log invocation UUID mismatch")
    if metadata.get("provider_source") != source:
        errors.append(f"process tree {node_id} authoritative source mismatch")
    if declared.get("provider_source") != metadata.get("provider_source"):
        errors.append(f"process tree {node_id} dispatch source join mismatch")
    result = metadata.get("result")
    if (
        not isinstance(result, dict)
        or result.get("id") != child_uuid
        or result.get("status") != "succeeded"
        or result.get("success") is not True
        or result.get("exit_code") != 0
    ):
        errors.append(f"process tree {node_id} runner result is not successful")
    if declared.get("output_mode") == "stdout-extracted":
        try:
            canonical_output = Path(output_path).read_bytes()
        except OSError as exc:
            errors.append(f"process tree {node_id} canonical output is unreadable: {exc}")
        else:
            if canonical_output != extracted:
                errors.append(
                    f"process tree {node_id} canonical output bytes do not equal extracted provider output"
                )


def _validate_leaf_fanout_against_trace(
    trace: dict[str, Any],
    root_uuid: str,
    dispatch_nodes: dict[str, dict[str, Any]],
    node_specs: dict[str, tuple[str, str]],
    errors: list[str],
    *,
    context: str,
    exact_count_error: str,
) -> None:
    """Validate one exact fanout whose declared children must all be leaves."""

    flattened, direct_entries = _process_trace_entries(
        trace, root_uuid, errors, context=context
    )
    if not flattened:
        return

    descendants = flattened[1:]
    declared_ids = {
        node.get("invocation_uuid")
        for node in dispatch_nodes.values()
        if isinstance(node.get("invocation_uuid"), str)
    }
    unexpected_ids = sorted(
        str(entry["invocation"].get("id"))
        for entry in descendants
        if entry["invocation"].get("id") not in declared_ids
    )
    if unexpected_ids:
        errors.append("process tree contains extra nested nodes: " + ",".join(unexpected_ids))
    if len(descendants) != len(dispatch_nodes):
        errors.append(exact_count_error)

    for node_id, declared in dispatch_nodes.items():
        child_uuid = declared.get("invocation_uuid")
        matches = [
            entry for entry in descendants if entry["invocation"].get("id") == child_uuid
        ]
        _validate_bound_process_node(
            node_id,
            declared,
            matches,
            direct_entries,
            root_uuid,
            node_specs,
            errors,
            require_leaf=True,
        )


def _validate_orchestrator_route_against_trace(
    trace: dict[str, Any],
    root_uuid: str,
    dispatch_nodes: dict[str, dict[str, Any]],
    node_specs: dict[str, tuple[str, str]],
    errors: list[str],
    *,
    stage: str,
) -> None:
    """Validate only the feature root's exact route/auditor direct children."""

    flattened, direct_entries = _process_trace_entries(
        trace, root_uuid, errors, context=f"feature-route {stage}"
    )
    if not flattened:
        return
    declared_ids = {
        node.get("invocation_uuid")
        for node in dispatch_nodes.values()
        if isinstance(node.get("invocation_uuid"), str)
    }
    unexpected_ids = sorted(
        str(entry["invocation"].get("id"))
        for entry in direct_entries
        if entry["invocation"].get("id") not in declared_ids
    )
    if unexpected_ids:
        errors.append(
            "feature route process tree contains undeclared direct root children: "
            + ",".join(unexpected_ids)
        )
    if len(direct_entries) != len(dispatch_nodes):
        errors.append(
            "pre-audit process tree must contain exactly the declared route child"
            if stage == "pre-audit"
            else "final process tree must contain exactly the route child and independent auditor child"
        )

    for node_id, declared in dispatch_nodes.items():
        child_uuid = declared.get("invocation_uuid")
        matches = [
            entry
            for entry in direct_entries
            if entry["invocation"].get("id") == child_uuid
        ]
        _validate_bound_process_node(
            node_id,
            declared,
            matches,
            direct_entries,
            root_uuid,
            node_specs,
            errors,
            require_leaf=node_id != "route-child",
        )


def _validate_test_audit_trace(
    trace: dict[str, Any],
    root_uuid: str,
    dispatch_nodes: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    _validate_leaf_fanout_against_trace(
        trace,
        root_uuid,
        dispatch_nodes,
        _TEST_AUDIT_NODE_SPECS,
        errors,
        context="test-audit",
        exact_count_error="process tree must contain exactly the three declared child nodes",
    )
    flattened = _trace_nodes(trace.get("root"), [])
    descendants = flattened[1:]
    for node_id, declared in dispatch_nodes.items():
        child_uuid = declared.get("invocation_uuid")
        matches = [
            entry for entry in descendants if entry["invocation"].get("id") == child_uuid
        ]
        if len(matches) != 1:
            continue
        source = matches[0]["invocation"].get("source")
        metadata_path = declared.get("extraction_metadata_path")
        if not isinstance(metadata_path, str):
            continue
        try:
            metadata = _load_json(Path(metadata_path))
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
            continue
        if metadata.get("invocation_uuid") != child_uuid:
            errors.append(f"process tree {node_id} extraction invocation UUID mismatch")
        if metadata.get("provider_source") != source:
            errors.append(f"process tree {node_id} authoritative source mismatch")
        if declared.get("provider_source") != metadata.get("provider_source"):
            errors.append(f"process tree {node_id} dispatch source join mismatch")
        for field in ("log_path", "log_sha256", "output_path", "output_sha256"):
            declared_field = (
                "canonical_output_path"
                if field == "output_path"
                else "canonical_output_sha256"
                if field == "output_sha256"
                else field
            )
            if metadata.get(field) != declared.get(declared_field):
                errors.append(f"process tree {node_id} extraction {field} mismatch")
        result = metadata.get("result")
        if (
            not isinstance(result, dict)
            or result.get("id") != child_uuid
            or result.get("status") != "succeeded"
            or result.get("success") is not True
            or result.get("exit_code") != 0
        ):
            errors.append(f"process tree {node_id} extraction result is not successful")


def validate_test_audit_nested_proof(
    proof: dict[str, Any], *, proof_path: Path | None = None
) -> dict[str, Any]:
    """Validate independently audited test-audit fanout and current artifact hashes."""

    errors: list[str] = []
    if set(proof) != _TEST_AUDIT_PROOF_FIELDS:
        errors.append(
            "test-audit nested proof fields must exactly equal: "
            + ",".join(sorted(_TEST_AUDIT_PROOF_FIELDS))
        )
    if proof.get("schema") != "test-audit-nested-proof-v1":
        errors.append("test-audit nested proof schema is invalid")
    try:
        root_uuid = _canonical_uuid(
            proof.get("test_audit_invocation_uuid"), "test_audit_invocation_uuid"
        )
    except ContractValidationError as exc:
        errors.extend(exc.decision["errors"])
        root_uuid = ""
    for field in ("base_sha", "head_sha"):
        value = proof.get(field)
        if not isinstance(value, str) or not _FULL_OID.fullmatch(value):
            errors.append(f"nested proof {field} must be a full lowercase Git OID")
    artifact_fields = (
        ("expected_process_path", "expected_process_sha256", "expected process"),
        ("dispatch_evidence_path", "dispatch_evidence_sha256", "dispatch evidence"),
        ("process_tree_path", "process_tree_sha256", "process tree"),
        (
            "process_tree_audit_prompt_path",
            "process_tree_audit_prompt_sha256",
            "process audit prompt",
        ),
        ("process_tree_audit_path", "process_tree_audit_sha256", "process audit report"),
        (
            "process_tree_audit_log_path",
            "process_tree_audit_log_sha256",
            "process audit log",
        ),
    )
    paths: dict[str, Path] = {}
    for path_field, hash_field, label in artifact_fields:
        path = _current_artifact(proof, path_field, hash_field, errors, label=label)
        if path is not None:
            paths[path_field] = path
    if len(paths.values()) != len(set(paths.values())):
        errors.append("nested process-proof artifact paths must be pairwise distinct")

    try:
        expected = _load_json(paths["expected_process_path"])
    except (KeyError, ContractValidationError) as exc:
        if isinstance(exc, ContractValidationError):
            errors.extend(exc.decision["errors"])
        expected = {}
    expected_nodes = _test_audit_expected_nodes(expected, root_uuid, errors)
    for field in ("base_sha", "head_sha"):
        if expected.get(field) != proof.get(field):
            errors.append(f"expected-process {field} mismatch")

    try:
        dispatch = _load_json(paths["dispatch_evidence_path"])
    except (KeyError, ContractValidationError) as exc:
        if isinstance(exc, ContractValidationError):
            errors.extend(exc.decision["errors"])
        dispatch = {}
    if dispatch.get("expected_process_path") != proof.get("expected_process_path"):
        errors.append("dispatch-evidence expected-process path mismatch")
    if dispatch.get("expected_process_sha256") != proof.get("expected_process_sha256"):
        errors.append("dispatch-evidence expected-process hash mismatch")
    for field in ("base_sha", "head_sha"):
        if dispatch.get(field) != proof.get(field):
            errors.append(f"dispatch-evidence {field} mismatch")
    dispatch_nodes = _test_audit_dispatch_nodes(
        dispatch, expected_nodes, root_uuid, errors
    )
    child_artifacts = proof.get("child_artifacts")
    if not isinstance(child_artifacts, list):
        errors.append("nested proof child_artifacts must be a list")
        child_artifacts = []
    if child_artifacts != list(dispatch_nodes.values()):
        errors.append("nested proof child_artifacts must exactly equal dispatch evidence")
    child_artifacts_sha256 = hashlib.sha256(_canonical_json(child_artifacts)).hexdigest()

    trace_path = paths.get("process_tree_path")
    if trace_path is not None:
        try:
            trace = _load_json(trace_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
            trace = {}
        _validate_test_audit_trace(trace, root_uuid, dispatch_nodes, errors)

    report_path = paths.get("process_tree_audit_path")
    if report_path is not None:
        report_verdict, binding = _load_process_tree_audit_report(report_path, errors)
        if report_verdict != "PASS":
            errors.append("process audit report canonical verdict must equal PASS")
        expected_binding = {
            "schema": "process-tree-audit-binding-v1",
            "mode": "blocking",
            "report_identity": {
                "schema": "process-tree-audit-report-v1",
                "path": str(report_path.resolve(strict=False)),
                "operator_file": str(_REPO_ROOT / "agents/test-audit-gate.md"),
            },
            "operator_artifact": {
                "path": str(_REPO_ROOT / "agents/test-audit-gate.md"),
                "sha256": _sha256_file(_REPO_ROOT / "agents/test-audit-gate.md"),
            },
            "audit_history": None,
            "root_invocation_uuid": root_uuid,
            "subtree_root_uuid": None,
            "expected_process": {
                "path": proof.get("expected_process_path"),
                "sha256": proof.get("expected_process_sha256"),
            },
            "process_tree": {
                "path": proof.get("process_tree_path"),
                "sha256": proof.get("process_tree_sha256"),
            },
            "companion_artifacts": _test_audit_bound_companions(
                proof, child_artifacts
            ),
        }
        if binding != expected_binding:
            errors.append("process audit report producer-owned binding mismatch")

    audit_log_path = paths.get("process_tree_audit_log_path")
    if audit_log_path is not None:
        try:
            payload = _successful_provider_payload(audit_log_path)
        except (OSError, ContractValidationError) as exc:
            detail = (
                exc.decision["errors"]
                if isinstance(exc, ContractValidationError)
                else [str(exc)]
            )
            errors.extend(f"process audit log: {error}" for error in detail)
        else:
            payload_lines = payload.decode("utf-8", errors="replace").splitlines()
            if not payload_lines or payload_lines[-1] != "PASS":
                errors.append("process audit final stdout line must equal PASS")
    if proof.get("verdict") != "PASS":
        errors.append("nested process proof verdict must equal PASS")

    proof_identity = str(proof_path.resolve(strict=False)) if proof_path else None
    proof_sha256 = None
    if proof_path is not None:
        try:
            proof_sha256 = _sha256_file(proof_path)
        except OSError as exc:
            errors.append(f"cannot hash nested proof {proof_path}: {exc}")
    return {
        "schema": "test-audit-nested-proof-validation-v1",
        "status": "VALID" if not errors else "INVALID",
        "test_audit_invocation_uuid": root_uuid or None,
        "base_sha": proof.get("base_sha"),
        "head_sha": proof.get("head_sha"),
        "nested_proof_path": proof_identity,
        "nested_proof_sha256": proof_sha256,
        "child_artifacts_sha256": child_artifacts_sha256,
        "errors": errors,
    }


def validate_test_audit_result(
    result: dict[str, Any],
    *,
    expected_root_uuid: str | None = None,
    expected_base_sha: str | None = None,
    expected_head_sha: str | None = None,
) -> dict[str, Any]:
    """Validate a test-audit result and its independently proven nested fanout."""

    errors: list[str] = []
    result_fields = set(result)
    allowed_fields = _TEST_AUDIT_RESULT_FIELDS | {"local_coverage_command_sha256"}
    required_fields = _TEST_AUDIT_RESULT_FIELDS | (
        {"local_coverage_command_sha256"}
        if result.get("mode") == "pr-review"
        else set()
    )
    if not required_fields <= result_fields or not result_fields <= allowed_fields:
        errors.append(
            "test-audit result fields do not match the selected mode; required: "
            + ",".join(sorted(required_fields))
            + "; allowed: "
            + ",".join(sorted(allowed_fields))
        )
    if result.get("schema") != "test-audit-result-v2":
        errors.append("test-audit result schema is invalid")
    if result.get("status") not in {"PASS", "PARTIAL", "FAIL"}:
        errors.append("test-audit result status is invalid")
    if result.get("mode") not in {"implementation", "pr-review"}:
        errors.append("test-audit result mode is invalid")
    try:
        root_uuid = _canonical_uuid(
            result.get("test_audit_invocation_uuid"), "test_audit_invocation_uuid"
        )
    except ContractValidationError as exc:
        errors.extend(exc.decision["errors"])
        root_uuid = ""
    if expected_root_uuid is not None and root_uuid != expected_root_uuid:
        errors.append("test-audit result root invocation UUID mismatch")
    for field, expected_value in (
        ("base_sha", expected_base_sha),
        ("head_sha", expected_head_sha),
    ):
        value = result.get(field)
        if not isinstance(value, str) or not _FULL_OID.fullmatch(value):
            errors.append(f"test-audit result {field} must be a full lowercase Git OID")
        if expected_value is not None and value != expected_value:
            errors.append(f"test-audit result {field} mismatch")
    merge_base_sha = result.get("merge_base_sha")
    if not isinstance(merge_base_sha, str) or not _FULL_OID.fullmatch(merge_base_sha):
        errors.append("test-audit result merge_base_sha must be a full lowercase Git OID")
    diff_sha256 = result.get("diff_sha256")
    if not isinstance(diff_sha256, str) or not _SHA256.fullmatch(diff_sha256):
        errors.append("test-audit result diff_sha256 must be a lowercase SHA-256")
    if result.get("mode") == "pr-review" or "local_coverage_command_sha256" in result:
        coverage_command_sha256 = result.get("local_coverage_command_sha256")
        if not isinstance(coverage_command_sha256, str) or not _SHA256.fullmatch(
            coverage_command_sha256
        ):
            errors.append(
                "test-audit result local_coverage_command_sha256 must be a lowercase SHA-256"
            )

    gate_path = _current_artifact(
        result,
        "gate_report_path",
        "gate_report_sha256",
        errors,
        label="test-audit gate report",
    )
    if gate_path is not None:
        try:
            gate_lines = gate_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"cannot read test-audit gate report: {exc}")
            gate_lines = []
        if not gate_lines or gate_lines[0] != f"Verdict: {result.get('status')}":
            errors.append("test-audit gate verdict does not match result status")

    nested_path = _current_artifact(
        result,
        "nested_proof_path",
        "nested_proof_sha256",
        errors,
        label="test-audit nested proof",
    )
    if nested_path is not None:
        try:
            nested = _load_json(nested_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
            nested = {}
    else:
        nested = {}
    if result.get("nested_process_proof") != nested:
        errors.append("embedded nested process proof does not equal nested proof artifact")
    nested_decision = validate_test_audit_nested_proof(nested, proof_path=nested_path)
    errors.extend(nested_decision["errors"])
    if nested_decision.get("test_audit_invocation_uuid") != root_uuid:
        errors.append("nested proof root invocation UUID mismatch")
    for field in ("base_sha", "head_sha"):
        if nested_decision.get(field) != result.get(field):
            errors.append(f"nested proof {field} does not match test-audit result")

    validation_path = _current_artifact(
        result,
        "nested_proof_validation_path",
        "nested_proof_validation_sha256",
        errors,
        label="test-audit nested proof validation",
    )
    if validation_path is not None:
        try:
            recorded_validation = _load_json(validation_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
            recorded_validation = {}
        if recorded_validation != nested_decision:
            errors.append("nested proof validation artifact is stale or mismatched")

    return {
        "schema": "test-audit-result-validation-v1",
        "status": "VALID" if not errors else "INVALID",
        "test_audit_invocation_uuid": root_uuid or None,
        "base_sha": result.get("base_sha"),
        "head_sha": result.get("head_sha"),
        "nested_proof_sha256": result.get("nested_proof_sha256"),
        "child_artifacts_sha256": nested_decision.get("child_artifacts_sha256"),
        "errors": errors,
    }


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and value == value.strip() and bool(value)


def _canonical_absolute_path(value: Any, label: str) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    if not _nonblank(value) or not Path(value).is_absolute():
        return None, [f"{label} must be a canonical absolute path"]
    if any(part in {".", ".."} for part in value.split("/")):
        errors.append(f"{label} must not contain . or .. components")
    path = Path(value)
    if value != str(path):
        errors.append(f"{label} must use its exact normalized lexical spelling")
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        errors.append(f"{label} cannot be resolved: {exc}")
        return None, errors
    if str(path) != str(resolved):
        errors.append(
            f"{label} lexical path must equal resolve(strict=False); symlink and alias paths are forbidden"
        )
    return str(resolved), errors


def _validate_string_list(
    value: Any, label: str, *, allow_empty: bool
) -> tuple[list[str], list[str]]:
    if not isinstance(value, list) or (not allow_empty and not value):
        return [], [f"{label} must be a {'possibly empty' if allow_empty else 'non-empty'} string list"]
    if any(not _nonblank(item) for item in value):
        return [], [f"{label} entries must be non-blank trimmed strings"]
    if len(value) != len(set(value)):
        return list(value), [f"{label} entries must be unique"]
    return list(value), []


def _validate_provider_bundle(label: str, bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = [field for field in _PROVIDER_FIELDS if field not in bundle]
    if missing:
        errors.append(f"{label} missing fields: {','.join(missing)}")
        return errors
    if set(bundle) != set(_PROVIDER_FIELDS):
        extra = sorted(set(bundle) - set(_PROVIDER_FIELDS))
        if extra:
            errors.append(f"{label} unknown fields: {','.join(extra)}")
    if not _nonblank(bundle["pr_url"]) or not bundle["pr_url"].startswith("https://"):
        errors.append(f"{label}.pr_url must be an exact https URL")
    if not isinstance(bundle["pr_number"], int) or bundle["pr_number"] <= 0:
        errors.append(f"{label}.pr_number must be a positive integer")
    if bundle["state"] != "OPEN":
        errors.append(f"{label}.state must equal OPEN")
    if not isinstance(bundle["is_draft"], bool):
        errors.append(f"{label}.is_draft must be a boolean")
    for field in ("base_ref_name", "head_ref_name"):
        if not _nonblank(bundle[field]):
            errors.append(f"{label}.{field} must be a non-blank exact branch name")
    for field in ("base_ref_oid", "head_ref_oid"):
        value = bundle[field]
        if not isinstance(value, str) or not _FULL_OID.fullmatch(value):
            errors.append(f"{label}.{field} must be a full lowercase Git OID")
    return errors


def validate_pr_currentness(
    reviewed: dict[str, Any],
    immediate: dict[str, Any],
    fetched_base_sha: str,
    fetched_head_sha: str,
    *,
    context: str,
    expected_draft: bool | None = None,
) -> dict[str, Any]:
    """Compare immutable reviewed PR identity with one immediate provider capture."""

    errors = _validate_provider_bundle("reviewed", reviewed)
    errors.extend(_validate_provider_bundle("immediate", immediate))
    if not isinstance(fetched_base_sha, str) or not _FULL_OID.fullmatch(
        fetched_base_sha
    ):
        errors.append("fetched_base_sha must be a full lowercase Git OID")
    if not isinstance(fetched_head_sha, str) or not _FULL_OID.fullmatch(
        fetched_head_sha
    ):
        errors.append("fetched_head_sha must be a full lowercase Git OID")

    equality = {
        "reviewed_draft_snapshot": reviewed.get("is_draft") is True,
        "state_open": immediate.get("state") == "OPEN",
        "immediate_draft_expected": expected_draft is None
        or immediate.get("is_draft") is expected_draft,
        "pr_url_equal": immediate.get("pr_url") == reviewed.get("pr_url"),
        "pr_number_equal": immediate.get("pr_number") == reviewed.get("pr_number"),
        "base_name_equal": immediate.get("base_ref_name")
        == reviewed.get("base_ref_name"),
        "head_name_equal": immediate.get("head_ref_name")
        == reviewed.get("head_ref_name"),
        "provider_base_equals_fetched": immediate.get("base_ref_oid")
        == fetched_base_sha,
        "fetched_base_equals_reviewed": fetched_base_sha
        == reviewed.get("base_ref_oid"),
        "provider_head_equals_fetched": immediate.get("head_ref_oid")
        == fetched_head_sha,
        "fetched_head_equals_reviewed": fetched_head_sha
        == reviewed.get("head_ref_oid"),
    }
    for name, passed in equality.items():
        if not passed:
            errors.append(f"identity inequality: {name}")

    accepted = not errors
    return {
        "schema": "pr-currentness-validation-v1",
        "context": context,
        "expected_draft": expected_draft,
        "status": "READY" if accepted else "STALE_CURRENTNESS",
        "final_equality_result": "PASS" if accepted else "FAIL",
        "reviewed": {field: reviewed.get(field) for field in _PROVIDER_FIELDS},
        "immediate": {field: immediate.get(field) for field in _PROVIDER_FIELDS},
        "fetched_base_sha": fetched_base_sha,
        "fetched_head_sha": fetched_head_sha,
        "equality": equality,
        "errors": errors,
        "required_action": (
            "proceed"
            if accepted
            else "perform-no-ready-or-merge-side-effect-and-rerun-parent-sensitive-gates"
        ),
    }


def require_pr_currentness(
    reviewed: dict[str, Any],
    immediate: dict[str, Any],
    fetched_base_sha: str,
    fetched_head_sha: str,
    *,
    context: str,
    expected_draft: bool | None = None,
) -> dict[str, Any]:
    decision = validate_pr_currentness(
        reviewed,
        immediate,
        fetched_base_sha,
        fetched_head_sha,
        context=context,
        expected_draft=expected_draft,
    )
    if decision["status"] != "READY":
        raise ContractValidationError(decision)
    return decision


def _validate_pr_currentness_result(label: str, evidence: dict[str, Any]) -> list[str]:
    required = {
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
    if not isinstance(evidence, dict) or set(evidence) != required:
        return [f"{label} must use the exact pr-currentness-validation-v1 key set"]
    reviewed = evidence.get("reviewed")
    immediate = evidence.get("immediate")
    context = evidence.get("context")
    expected_draft = evidence.get("expected_draft")
    fetched_base_sha = evidence.get("fetched_base_sha")
    fetched_head_sha = evidence.get("fetched_head_sha")
    if not isinstance(reviewed, dict) or not isinstance(immediate, dict):
        return [f"{label} provider bundles must be mappings"]
    if not isinstance(context, str) or not _nonblank(context):
        return [f"{label}.context must be a non-blank trimmed string"]
    if expected_draft is not None and not isinstance(expected_draft, bool):
        return [f"{label}.expected_draft must be null or a boolean"]
    if not isinstance(fetched_base_sha, str) or not isinstance(fetched_head_sha, str):
        return [f"{label} fetched base/head SHAs must be strings"]
    recomputed = validate_pr_currentness(
        reviewed,
        immediate,
        fetched_base_sha,
        fetched_head_sha,
        context=context,
        expected_draft=expected_draft,
    )
    if evidence != recomputed:
        return [f"{label} is malformed, stale, or not reproducible"]
    return []


def validate_ready_state_restoration(
    promoted: dict[str, Any],
    restored: dict[str, Any] | None,
    fetched_base_sha: str | None,
    fetched_head_sha: str | None,
    *,
    owner: str,
    undo_attempted: bool,
    undo_exit_code: int | None,
    requery_succeeded: bool,
    merge_attempt_started: bool,
) -> dict[str, Any]:
    """Prove that a promoted PR was restored to draft before replay."""

    recovery_state = _READY_STATE_OWNERS.get(owner)
    errors: list[str] = []
    if recovery_state is None:
        errors.append("owner must name one declared ready-state merge owner")

    if merge_attempt_started:
        if undo_attempted:
            errors.append("ready undo is forbidden after a merge attempt starts")
        return {
            "schema": "ready-state-restoration-validation-v1",
            "owner": owner,
            "status": "BLOCKED:merge-attempt-started",
            "undo_permitted": False,
            "replay_permitted": False,
            "identity_equal": False,
            "errors": errors
            or ["merge attempt has started; provider outcome requires non-replayable review"],
        }

    errors.extend(_validate_provider_bundle("promoted", promoted))
    if promoted.get("is_draft") is not False:
        errors.append("promoted.is_draft must equal false")
    if not undo_attempted:
        errors.append("ready undo must be attempted before replay")
    if undo_exit_code != 0:
        errors.append("ready undo must exit zero")
    if not requery_succeeded:
        errors.append("post-undo provider requery must succeed")
    if restored is None:
        errors.append("post-undo provider identity is required")
    else:
        errors.extend(_validate_provider_bundle("restored", restored))
        if restored.get("is_draft") is not True:
            errors.append("restored.is_draft must equal true")

    for value, label in (
        (fetched_base_sha, "fetched_base_sha"),
        (fetched_head_sha, "fetched_head_sha"),
    ):
        if not isinstance(value, str) or not _FULL_OID.fullmatch(value):
            errors.append(f"{label} must be a full lowercase Git OID")

    identity_fields = tuple(field for field in _PROVIDER_FIELDS if field != "is_draft")
    identity_equal = restored is not None and all(
        restored.get(field) == promoted.get(field) for field in identity_fields
    )
    if not identity_equal:
        errors.append(
            "post-undo URL/number/state/base/head identity must equal the promoted identity"
        )
    if restored is not None:
        if restored.get("base_ref_oid") != fetched_base_sha:
            errors.append("restored base OID must equal the freshly fetched base SHA")
        if restored.get("head_ref_oid") != fetched_head_sha:
            errors.append("restored head OID must equal the freshly fetched head SHA")

    accepted = not errors
    return {
        "schema": "ready-state-restoration-validation-v1",
        "owner": owner,
        "status": recovery_state
        if accepted
        else "BLOCKED:ready-state-restoration-failed",
        "undo_permitted": True,
        "replay_permitted": accepted,
        "identity_equal": identity_equal,
        "promoted": {field: promoted.get(field) for field in _PROVIDER_FIELDS},
        "restored": (
            {field: restored.get(field) for field in _PROVIDER_FIELDS}
            if restored is not None
            else None
        ),
        "fetched_base_sha": fetched_base_sha,
        "fetched_head_sha": fetched_head_sha,
        "errors": errors,
    }


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _recursive_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _recursive_keys(child)}
    return set()


def _lineage_artifact(
    acceptance: dict[str, Any],
    field: str,
    errors: list[str],
    *,
    extra_fields: set[str] | None = None,
) -> tuple[Path | None, str | None]:
    entry = acceptance.get(field)
    required = {"path", "sha256"} | (extra_fields or set())
    if not isinstance(entry, dict) or set(entry) != required:
        errors.append(f"{field} fields must exactly equal: {','.join(sorted(required))}")
        return None, None
    canonical, path_errors = _canonical_absolute_path(entry.get("path"), f"{field}.path")
    errors.extend(path_errors)
    recorded_hash = entry.get("sha256")
    if not isinstance(recorded_hash, str) or not _SHA256.fullmatch(recorded_hash):
        errors.append(f"{field}.sha256 must be a lowercase SHA-256")
        recorded_hash = None
    if canonical is None:
        return None, recorded_hash
    path = Path(canonical)
    try:
        actual_hash = _sha256_file(path)
    except OSError as exc:
        errors.append(f"cannot hash {field}.path {path}: {exc}")
        return path, recorded_hash
    if recorded_hash is not None and actual_hash != recorded_hash:
        errors.append(f"{field} hash mismatch")
    return path, actual_hash


def _load_process_binding(path: Path, errors: list[str]) -> dict[str, Any]:
    verdict, binding = _load_process_tree_audit_report(path, errors)
    if verdict != "PASS":
        errors.append("process report canonical verdict must equal Verdict: PASS")
    return binding


def _valid_ticket_site_url(value: Any, backend: str) -> bool:
    if not _nonblank(value):
        return False
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        return False
    host = parsed.hostname.lower() if parsed.hostname else ""
    if backend == "linear":
        return host == "linear.app"
    return bool(host) and host != "linear.app" and not host.endswith(".linear.app")


def _validate_ticket_operation_expected_context(
    expected: dict[str, Any], errors: list[str]
) -> None:
    if set(expected) != _TICKET_OPERATION_EXPECTED_CONTEXT_FIELDS:
        errors.append(
            "ticket operation expected context fields must exactly equal: "
            + ",".join(sorted(_TICKET_OPERATION_EXPECTED_CONTEXT_FIELDS))
        )
    if expected.get("schema") != "ticket-operation-expected-context-v1":
        errors.append(
            "ticket operation expected context schema must equal ticket-operation-expected-context-v1"
        )
    backend = expected.get("backend")
    if backend not in {"jira", "linear"}:
        errors.append("ticket operation expected context backend must equal jira or linear")
        backend = ""
    if not _valid_ticket_site_url(expected.get("ticket_site_url"), backend):
        errors.append("ticket operation expected context ticket_site_url is invalid")
    if not _nonblank(expected.get("ticket_key")):
        errors.append("ticket operation expected context ticket_key must be non-blank")
    if expected.get("operation") != "comment-readback":
        errors.append("ticket operation expected context operation must equal comment-readback")
    if expected.get("owning_route") != "implementation-pipeline":
        errors.append(
            "ticket operation expected context owning_route must equal implementation-pipeline"
        )
    if (
        not isinstance(expected.get("attempt_number"), int)
        or expected.get("attempt_number", 0) <= 0
    ):
        errors.append("ticket operation expected context attempt_number must be positive")
    if not isinstance(expected.get("pr_number"), int) or expected.get("pr_number", 0) <= 0:
        errors.append("ticket operation expected context pr_number must be positive")
    pr_url = expected.get("pr_url")
    parsed_pr = urlparse(pr_url) if isinstance(pr_url, str) else None
    if (
        parsed_pr is None
        or parsed_pr.scheme != "https"
        or parsed_pr.netloc.lower() != "github.com"
        or not parsed_pr.path.endswith(f"/pull/{expected.get('pr_number')}")
    ):
        errors.append("ticket operation expected context PR URL/number identity is invalid")
    for field in (
        "reviewed_base_branch",
        "reviewed_base_ref",
        "reviewed_head_branch",
        "reviewed_head_ref",
    ):
        if not _nonblank(expected.get(field)):
            errors.append(f"ticket operation expected context {field} must be non-blank")
    for field in ("reviewed_base_sha", "reviewed_head_sha"):
        value = expected.get(field)
        if not isinstance(value, str) or not _FULL_OID.fullmatch(value):
            errors.append(
                f"ticket operation expected context {field} must be a full lowercase Git OID"
            )


def _valid_remote_url(
    value: Any,
    backend: str,
    comment_id: Any,
    *,
    expected_site_url: Any,
    expected_ticket_key: Any,
) -> bool:
    if not _nonblank(value) or not _nonblank(comment_id):
        return False
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    if comment_id not in value:
        return False
    expected_site = urlparse(expected_site_url) if isinstance(expected_site_url, str) else None
    if expected_site is None or parsed.netloc.lower() != expected_site.netloc.lower():
        return False
    segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    ticket_key = str(expected_ticket_key)
    if backend == "linear":
        return any(
            segments[index : index + 2] == ["issue", ticket_key]
            for index in range(max(0, len(segments) - 1))
        )
    return any(
        segments[index : index + 4] == ["issue", ticket_key, "comment", str(comment_id)]
        for index in range(max(0, len(segments) - 3))
    )


def validate_ticket_operation_result(
    result: dict[str, Any],
    expected_context: dict[str, Any],
    *,
    result_path: Path | None = None,
    expected_context_path: Path | None = None,
) -> dict[str, Any]:
    """Validate one Jira/Linear producer-owned comment and exact readback result."""

    errors: list[str] = []
    _validate_ticket_operation_expected_context(expected_context, errors)
    if set(result) != _TICKET_OPERATION_RESULT_FIELDS:
        errors.append(
            "ticket operation result fields must exactly equal: "
            + ",".join(sorted(_TICKET_OPERATION_RESULT_FIELDS))
        )
    if result.get("schema") != "ticket-operation-result-v1":
        errors.append("ticket operation result schema must equal ticket-operation-result-v1")
    backend = result.get("backend")
    if backend not in {"jira", "linear"}:
        errors.append("ticket operation result backend must equal jira or linear")
        backend = ""
    if not _nonblank(result.get("ticket_key")):
        errors.append("ticket operation result ticket_key must be non-blank")
    if result.get("operation") != "comment-readback":
        errors.append("ticket operation result operation must equal comment-readback")
    if result.get("status") != "PASS":
        errors.append("ticket operation result status must equal PASS")
    if result.get("owning_route") != "implementation-pipeline":
        errors.append("ticket operation result owning_route must equal implementation-pipeline")
    if not isinstance(result.get("attempt_number"), int) or result.get("attempt_number", 0) <= 0:
        errors.append("ticket operation result attempt_number must be positive")
    if not isinstance(result.get("pr_number"), int) or result.get("pr_number", 0) <= 0:
        errors.append("ticket operation result pr_number must be positive")
    pr_url = result.get("pr_url")
    parsed_pr = urlparse(pr_url) if isinstance(pr_url, str) else None
    if (
        parsed_pr is None
        or parsed_pr.scheme != "https"
        or parsed_pr.netloc.lower() != "github.com"
        or not parsed_pr.path.endswith(f"/pull/{result.get('pr_number')}")
    ):
        errors.append("ticket operation result PR URL/number identity is invalid")
    for field in (
        "reviewed_base_branch",
        "reviewed_base_ref",
        "reviewed_head_branch",
        "reviewed_head_ref",
    ):
        if not _nonblank(result.get(field)):
            errors.append(f"ticket operation result {field} must be non-blank")
    for field in ("reviewed_base_sha", "reviewed_head_sha"):
        value = result.get(field)
        if not isinstance(value, str) or not _FULL_OID.fullmatch(value):
            errors.append(f"ticket operation result {field} must be a full lowercase Git OID")
    for field in ("comment_body_sha256", "readback_body_sha256"):
        value = result.get(field)
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            errors.append(f"ticket operation result {field} must be a lowercase SHA-256")
    if result.get("readback_body_sha256") != result.get("comment_body_sha256"):
        errors.append("ticket operation result readback body hash mismatch")

    comment_id = result.get("remote_comment_id")
    comment_url = result.get("remote_comment_url")
    if not _valid_remote_url(
        comment_url,
        backend,
        comment_id,
        expected_site_url=expected_context.get("ticket_site_url"),
        expected_ticket_key=expected_context.get("ticket_key"),
    ):
        errors.append("ticket operation result remote comment identity is invalid")
    if result.get("readback_status") != "PASS":
        errors.append("ticket operation result readback_status must equal PASS")
    if result.get("readback_ticket_key") != result.get("ticket_key"):
        errors.append("ticket operation result readback ticket identity mismatch")
    if result.get("readback_comment_id") != comment_id:
        errors.append("ticket operation result readback comment id mismatch")
    if result.get("readback_comment_url") != comment_url:
        errors.append("ticket operation result readback comment URL mismatch")

    expected_operator = {
        "jira": "agents/jira-operator.md",
        "linear": "agents/linear-operator.md",
    }.get(backend)
    if result.get("producer_operator") != expected_operator:
        errors.append("ticket operation result producer operator/backend mismatch")
    try:
        producer_uuid = _canonical_uuid(
            result.get("producer_invocation_uuid"), "producer_invocation_uuid"
        )
    except ContractValidationError as exc:
        errors.extend(exc.decision["errors"])
        producer_uuid = ""

    producer_log_path = _current_artifact(
        result,
        "producer_log_path",
        "producer_log_sha256",
        errors,
        label="ticket operation producer log",
    )
    producer_output_path = _current_artifact(
        result,
        "producer_output_path",
        "producer_output_sha256",
        errors,
        label="ticket operation producer output",
    )
    support_paths = [path for path in (producer_log_path, producer_output_path) if path]
    if len(support_paths) != len(set(support_paths)):
        errors.append("ticket operation producer log/output paths must be distinct")
    if result_path is not None:
        result_identity = result_path.resolve(strict=False)
        if result_identity in support_paths:
            errors.append("ticket operation result must not self-reference as producer evidence")

    # These support artifacts are operation/readback identity projections.
    # Hashes and equality checks bind their bytes and asserted identities;
    # they do not authenticate transcripts, request order or remote execution.
    producer_log: dict[str, Any] = {}
    if producer_log_path is not None:
        try:
            producer_log = _load_json(producer_log_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    if producer_log and set(producer_log) != _TICKET_OPERATION_PRODUCER_LOG_FIELDS:
        errors.append(
            "ticket operation producer log fields must exactly equal: "
            + ",".join(sorted(_TICKET_OPERATION_PRODUCER_LOG_FIELDS))
        )
    producer_log_expected = {
        "schema": "ticket-operation-producer-log-v1",
        "backend": backend,
        "ticket_key": result.get("ticket_key"),
        "operation": result.get("operation"),
        "status": result.get("status"),
        "producer_operator": result.get("producer_operator"),
        "producer_invocation_uuid": producer_uuid,
        "comment_body_sha256": result.get("comment_body_sha256"),
        "remote_comment_id": comment_id,
        "remote_comment_url": comment_url,
        "readback_status": result.get("readback_status"),
        "readback_ticket_key": result.get("readback_ticket_key"),
        "readback_comment_id": result.get("readback_comment_id"),
        "readback_comment_url": result.get("readback_comment_url"),
        "readback_body_sha256": result.get("readback_body_sha256"),
    }
    if producer_log != producer_log_expected:
        errors.append("ticket operation producer log does not equal canonical operation identity")

    producer_output: dict[str, Any] = {}
    if producer_output_path is not None:
        try:
            producer_output = _load_json(producer_output_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    if producer_output and set(producer_output) != _TICKET_OPERATION_PRODUCER_OUTPUT_FIELDS:
        errors.append(
            "ticket operation producer output fields must exactly equal: "
            + ",".join(sorted(_TICKET_OPERATION_PRODUCER_OUTPUT_FIELDS))
        )
    producer_output_expected = {
        "schema": "ticket-operation-readback-v1",
        "backend": backend,
        "ticket_key": result.get("ticket_key"),
        "status": result.get("readback_status"),
        "comment_id": result.get("readback_comment_id"),
        "comment_url": result.get("readback_comment_url"),
        "body_sha256": result.get("readback_body_sha256"),
    }
    if producer_output != producer_output_expected:
        errors.append("ticket operation producer output does not equal exact readback identity")

    for field in _TICKET_OPERATION_EXPECTED_RESULT_FIELDS:
        if result.get(field) != expected_context.get(field):
            errors.append(f"ticket operation result {field} mismatch")

    result_sha256 = None
    if result_path is not None:
        try:
            result_sha256 = _sha256_file(result_path)
        except OSError as exc:
            errors.append(f"cannot hash ticket operation result {result_path}: {exc}")
    expected_context_sha256 = None
    if expected_context_path is not None:
        try:
            expected_context_sha256 = _sha256_file(expected_context_path)
        except OSError as exc:
            errors.append(
                f"cannot hash ticket operation expected context {expected_context_path}: {exc}"
            )
    return {
        "schema": "ticket-operation-result-validation-v1",
        "status": "VALID" if not errors else "INVALID",
        "expected_context_path": (
            str(expected_context_path.resolve(strict=False))
            if expected_context_path is not None
            else None
        ),
        "expected_context_sha256": expected_context_sha256,
        "result_path": str(result_path.resolve(strict=False)) if result_path else None,
        "result_sha256": result_sha256,
        "producer_invocation_uuid": producer_uuid or None,
        "errors": errors,
    }


def _owned_process_proof_companions(
    proofs: Any,
    errors: list[str],
    *,
    owner: str,
    stages: tuple[str, ...],
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(proofs, list):
        errors.append(f"{label} owned_process_proofs must be a list")
        return []
    companions: list[dict[str, Any]] = []
    seen_stages: list[Any] = []
    paths: list[Path] = []
    for index, proof in enumerate(proofs):
        if not isinstance(proof, dict) or set(proof) != _OWNED_PROCESS_PROOF_FIELDS:
            errors.append(
                f"{label} owned_process_proofs[{index}] fields are invalid"
            )
            continue
        stage = proof.get("stage")
        seen_stages.append(stage)
        if proof.get("owner") != owner:
            errors.append(
                f"{label} owned_process_proofs[{index}].owner is invalid"
            )
        if stage not in stages:
            errors.append(
                f"{label} owned_process_proofs[{index}].stage is invalid"
            )
        for stem in ("expected_process", "process_tree", "process_tree_audit"):
            path = _current_artifact(
                proof,
                f"{stem}_path",
                f"{stem}_sha256",
                errors,
                label=f"{label} {stage} {stem}",
            )
            if path is not None:
                paths.append(path)
            companions.append(
                {
                    "path": proof.get(f"{stem}_path"),
                    "sha256": proof.get(f"{stem}_sha256"),
                }
            )
    if tuple(seen_stages) != stages:
        errors.append(
            f"{label} owned_process_proofs must equal exact {','.join(stages)} order"
        )
    if len(paths) != len(set(paths)):
        errors.append(f"{label} owned process-proof paths must be pairwise distinct")
    return sorted(companions, key=lambda row: str(row.get("path")))


def _implementation_owned_process_proof_companions(
    route_output: dict[str, Any], errors: list[str]
) -> list[dict[str, Any]]:
    return _owned_process_proof_companions(
        route_output.get("owned_process_proofs"),
        errors,
        owner="implementation-pipeline",
        stages=_IMPLEMENTATION_PROCESS_PROOF_STAGES,
        label="implementation route",
    )


def _validate_refactoring_auditor_collection_shape(
    reports: Any,
    *,
    stage: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(reports, list):
        errors.append(f"{label} must be an array")
        return
    if len(reports) != len(_REFACTORING_AUDITOR_ROLES):
        errors.append(
            f"{label} must contain exactly {len(_REFACTORING_AUDITOR_ROLES)} reports"
        )
    roles: list[Any] = []
    for index, report in enumerate(reports):
        if not isinstance(report, dict) or set(report) != _REFACTORING_AUDITOR_REPORT_FIELDS:
            errors.append(f"{label}[{index}] fields are invalid")
            continue
        roles.append(report.get("role"))
        if report.get("stage") != stage:
            errors.append(f"{label}[{index}].stage must equal {stage}")
    if tuple(roles) != _REFACTORING_AUDITOR_ROLES:
        errors.append(f"{label} must contain the exact canonical auditor role order")


def _validate_refactoring_auditor_report_verdict(
    report_path: Path, *, role: str, label: str, errors: list[str]
) -> None:
    try:
        lines = report_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"cannot read {label} {report_path}: {exc}")
        return
    if role == "validation-integrity-auditor":
        final_nonblank_line = next(
            (line for line in reversed(lines) if line.strip()), None
        )
        verdict_lines = [
            line
            for line in lines
            if line in {"LOW", "MEDIUM", "HIGH"}
            or line.startswith(("Verdict:", "NEEDS_INPUT:", "BLOCKED:"))
        ]
        if verdict_lines != ["LOW"] or final_nonblank_line != "LOW":
            errors.append(
                f"{label} must end with exactly one canonical validation-integrity LOW token"
            )
        return
    verdict_lines = [line for line in lines if line.startswith("Verdict:")]
    if verdict_lines != ["Verdict: LOW"]:
        errors.append(f"{label} must contain exactly one canonical Verdict: LOW line")


def _validate_refactoring_auditor_index(
    index: dict[str, Any],
    *,
    feature_branch: str,
    ticket_id: Any,
    attempt_number: Any,
    route_invocation_uuid: str,
    child: dict[str, Any],
    errors: list[str],
) -> None:
    if set(index) != _REFACTORING_AUDITOR_INDEX_FIELDS:
        errors.append(
            "refactoring auditor index fields must exactly equal: "
            + ",".join(sorted(_REFACTORING_AUDITOR_INDEX_FIELDS))
        )
    expected_identity = {
        "schema": "refactoring-auditor-index-v1",
        "owning_route": "refactoring",
        "refactoring_invocation_uuid": route_invocation_uuid,
        "feature_branch": feature_branch,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "auditor_baseline_sha": child.get("auditor_baseline_sha"),
        "pre_merge_current_head": child.get("pre_merge_auditor_current_head"),
        "post_merge_current_head": child.get("post_merge_auditor_current_head"),
    }
    for field, expected in expected_identity.items():
        if index.get(field) != expected:
            errors.append(f"refactoring auditor index {field} mismatch")

    stage_specs = (
        (
            "pre-merge",
            "pre_merge_reports",
            child.get("pre_merge_auditor_reports"),
            child.get("pre_merge_auditor_current_head"),
        ),
        (
            "post-merge",
            "post_merge_reports",
            child.get("post_merge_auditor_reports"),
            child.get("post_merge_auditor_current_head"),
        ),
    )
    indexed_paths: list[Path] = []
    rounds: list[int] = []
    for stage, field, route_reports, expected_head in stage_specs:
        reports = index.get(field)
        label = f"refactoring auditor index {field}"
        _validate_refactoring_auditor_collection_shape(
            reports, stage=stage, label=label, errors=errors
        )
        if reports != route_reports:
            errors.append(f"refactoring route child {field} must equal auditor index")
        if not isinstance(reports, list):
            continue
        stage_rounds: list[int] = []
        for report_index, report in enumerate(reports):
            if not isinstance(report, dict) or set(report) != _REFACTORING_AUDITOR_REPORT_FIELDS:
                continue
            row_label = f"{label}[{report_index}]"
            report_path = _current_artifact(
                report,
                "report_path",
                "report_sha256",
                errors,
                label=f"{row_label} report",
            )
            if report_path is not None:
                indexed_paths.append(report_path)
                _validate_refactoring_auditor_report_verdict(
                    report_path,
                    role=str(report.get("role")),
                    label=f"{row_label} report",
                    errors=errors,
                )
            if report.get("verdict") != "LOW":
                errors.append(f"{row_label}.verdict must equal LOW")
            round_number = report.get("round")
            if (
                not isinstance(round_number, int)
                or isinstance(round_number, bool)
                or round_number <= 0
            ):
                errors.append(f"{row_label}.round must be a positive integer")
            else:
                stage_rounds.append(round_number)
            if report.get("baseline_sha") != child.get("auditor_baseline_sha"):
                errors.append(f"{row_label}.baseline_sha mismatch")
            if report.get("current_head_sha") != expected_head:
                errors.append(f"{row_label}.current_head_sha mismatch")
        if stage_rounds and len(set(stage_rounds)) != 1:
            errors.append(f"{label} must use one exact round")
        rounds.extend(stage_rounds[:1])
    if len(rounds) == 2 and rounds[0] != rounds[1]:
        errors.append("refactoring auditor pre-merge and post-merge rounds must match")
    if len(indexed_paths) != len(set(indexed_paths)):
        errors.append("refactoring auditor report paths must be pairwise distinct")


def _validate_refactoring_route_result(
    route_output: dict[str, Any],
    *,
    feature_branch: str,
    ticket_id: Any,
    attempt_number: Any,
    route_invocation_uuid: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    if set(route_output) != _REFACTORING_ROUTE_RESULT_FIELDS:
        errors.append(
            "refactoring route result fields must exactly equal: "
            + ",".join(sorted(_REFACTORING_ROUTE_RESULT_FIELDS))
        )
    if route_output.get("schema") != "refactoring-route-result-v1":
        errors.append("refactoring route result schema is invalid")
    if route_output.get("state") != "VERIFIED_MERGED":
        errors.append("refactoring route result state must equal VERIFIED_MERGED")
    if route_output.get("refactoring_invocation_uuid") != route_invocation_uuid:
        errors.append("refactoring route result invocation UUID mismatch")
    ticket_system = route_output.get("ticket_system")
    source_key = (
        "jira_issue_key"
        if ticket_system == "jira"
        else "linear_issue_key"
        if ticket_system == "linear"
        else None
    )
    ticket_source = route_output.get("ticket_source")
    valid_ticket_source = source_key is not None and isinstance(ticket_source, dict)
    if valid_ticket_source:
        assert source_key is not None and isinstance(ticket_source, dict)
        valid_ticket_source = (
            set(ticket_source) == {source_key}
            and ticket_source.get(source_key) == ticket_id
        )
    if not valid_ticket_source:
        errors.append("refactoring route result ticket source mismatch")
    if route_output.get("integration_branch_name") != feature_branch:
        errors.append("refactoring route result integration branch must equal feature_branch")
    for field in ("final_integration_sha",):
        if not isinstance(route_output.get(field), str) or not _FULL_OID.fullmatch(
            route_output[field]
        ):
            errors.append(f"refactoring route result {field} must be a full Git OID")
    current_artifacts: dict[str, Path] = {}
    for stem in (
        "pre_merge_expected_process",
        "pre_merge_dispatch_evidence",
        "pre_merge_process_tree",
        "pre_merge_process_tree_audit",
        "expected_process",
        "dispatch_evidence",
        "process_tree",
        "process_tree_audit",
        "auditor_index",
    ):
        path = _current_artifact(
            route_output,
            f"{stem}_path",
            f"{stem}_sha256",
            errors,
            label=f"refactoring route {stem}",
        )
        if path is not None:
            current_artifacts[stem] = path
    companions = _owned_process_proof_companions(
        route_output.get("owned_process_proofs"),
        errors,
        owner="refactoring-orchestrator",
        stages=("pre-merge", "final"),
        label="refactoring route",
    )
    child = route_output.get("child")
    if not isinstance(child, dict) or set(child) != _REFACTORING_ROUTE_CHILD_FIELDS:
        errors.append(
            "refactoring route child fields must exactly equal: "
            + ",".join(sorted(_REFACTORING_ROUTE_CHILD_FIELDS))
        )
        return companions
    if child.get("ticket_source") != ticket_source:
        errors.append("refactoring route child ticket source mismatch")
    for field in (
        "dispatched_base_branch",
        "open_observed_base_ref_name",
        "pre_merge_observed_base_ref_name",
        "merged_observed_base_ref_name",
    ):
        if child.get(field) != feature_branch:
            errors.append(f"refactoring route child {field} must equal feature_branch")
    try:
        child_uuid = _canonical_uuid(
            child.get("child_invocation_uuid"), "refactoring child invocation UUID"
        )
    except ContractValidationError as exc:
        errors.extend(exc.decision["errors"])
        child_uuid = ""
    if child_uuid == route_invocation_uuid:
        errors.append("refactoring child invocation UUID must differ from route UUID")
    implementation_path = _current_artifact(
        child,
        "implementation_result_path",
        "implementation_result_sha256",
        errors,
        label="refactoring implementation result",
    )
    implementation_result: dict[str, Any] = {}
    if implementation_path is not None:
        try:
            implementation_result = _load_json(implementation_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    for field, expected in (
        ("schema", "implementation-pipeline-result-v1"),
        ("status", "VERIFIED_DRAFT_PR"),
        ("ticket_id", ticket_id),
        ("owning_route", "implementation-pipeline"),
        ("route_attempt_number", attempt_number),
        ("base_branch", feature_branch),
        ("base_ref", f"refs/remotes/origin/{feature_branch}"),
    ):
        if implementation_result.get(field) != expected:
            errors.append(f"refactoring implementation result {field} mismatch")
    nested_missing = sorted(
        _IMPLEMENTATION_ROUTE_OUTPUT_REQUIRED_FIELDS - set(implementation_result)
    )
    if nested_missing:
        errors.append(
            "refactoring implementation result missing required fields: "
            + ",".join(nested_missing)
        )
    if implementation_result.get("ticket_system") != ticket_system:
        errors.append("refactoring implementation result ticket_system mismatch")
    for stem in ("ticket_operation_expected_context", "ticket_operation_result"):
        path = _current_artifact(
            child,
            f"{stem}_path",
            f"{stem}_sha256",
            errors,
            label=f"refactoring child {stem}",
        )
        if path is not None and (
            child.get(f"{stem}_path") != implementation_result.get(f"{stem}_path")
            or child.get(f"{stem}_sha256")
            != implementation_result.get(f"{stem}_sha256")
        ):
            errors.append(f"refactoring child {stem} binding mismatch")
    child_companions = _owned_process_proof_companions(
        child.get("owned_process_proofs"),
        errors,
        owner="implementation-pipeline",
        stages=_IMPLEMENTATION_PROCESS_PROOF_STAGES,
        label="refactoring child",
    )
    if child.get("owned_process_proofs") != implementation_result.get(
        "owned_process_proofs"
    ):
        errors.append("refactoring child owned process proofs mismatch implementation result")
    companions.extend(child_companions)
    expected_values = {
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
    for field, expected in expected_values.items():
        if child.get(field) != expected:
            errors.append(f"refactoring route child {field} mismatch")
    nested_pr_url = implementation_result.get("pr_url")
    nested_pr_number = implementation_result.get("pr_number")
    nested_base_sha = implementation_result.get("phase_8_reviewed_base_sha")
    nested_head_branch = implementation_result.get("head_branch")
    nested_head_sha = implementation_result.get("phase_8_reviewed_head_sha")
    for field, expected in (
        ("pr_url", nested_pr_url),
        ("pr_number", nested_pr_number),
        ("declared_head_branch", nested_head_branch),
        ("declared_head_sha", nested_head_sha),
        ("reviewed_base_sha", nested_base_sha),
    ):
        if child.get(field) != expected:
            errors.append(
                f"refactoring route child {field} mismatch nested implementation reviewed identity"
            )
    if (
        not isinstance(nested_pr_number, int)
        or isinstance(nested_pr_number, bool)
        or nested_pr_number <= 0
    ):
        errors.append("refactoring implementation result pr_number must be positive")
    parsed_pr = urlparse(nested_pr_url) if isinstance(nested_pr_url, str) else None
    if (
        parsed_pr is None
        or parsed_pr.scheme != "https"
        or parsed_pr.netloc.lower() != "github.com"
        or not parsed_pr.path.endswith(f"/pull/{nested_pr_number}")
    ):
        errors.append("refactoring implementation result PR URL/number identity is invalid")
    errors.extend(
        _validate_short_branch(
            nested_head_branch, "refactoring nested implementation reviewed head branch"
        )
    )
    if implementation_result.get("head_ref") != f"refs/heads/{nested_head_branch}":
        errors.append("refactoring implementation result head_ref mismatch reviewed head branch")

    base_sha = child.get("reviewed_base_sha")
    merge_sha = child.get("merge_sha")
    for field in (
        "declared_head_sha",
        "open_observed_base_sha",
        "open_observed_head_sha",
        "pre_merge_observed_base_sha",
        "pre_merge_observed_head_sha",
        "pre_merge_base_sha",
        "reviewed_base_sha",
        "expected_head_guard_sha",
        "merged_observed_base_sha",
        "merged_observed_head_sha",
        "merged_observed_merge_sha",
        "merge_sha",
        "refreshed_integration_sha",
        "merge_first_parent_sha",
        "auditor_baseline_sha",
        "pre_merge_auditor_current_head",
        "post_merge_auditor_current_head",
    ):
        if not isinstance(child.get(field), str) or not _FULL_OID.fullmatch(child[field]):
            errors.append(f"refactoring route child {field} must be a full Git OID")
    for field in (
        "open_observed_base_sha",
        "pre_merge_observed_base_sha",
        "pre_merge_base_sha",
        "merged_observed_base_sha",
    ):
        if child.get(field) != nested_base_sha:
            errors.append(f"refactoring route child {field} must equal nested reviewed base")
    for field in (
        "declared_head_branch",
        "open_observed_head_ref_name",
        "pre_merge_observed_head_ref_name",
        "merged_observed_head_ref_name",
    ):
        if child.get(field) != nested_head_branch:
            errors.append(f"refactoring route child {field} must equal nested reviewed head")
    for field in (
        "declared_head_sha",
        "open_observed_head_sha",
        "pre_merge_observed_head_sha",
        "expected_head_guard_sha",
        "merged_observed_head_sha",
        "pre_merge_auditor_current_head",
    ):
        if child.get(field) != nested_head_sha:
            errors.append(f"refactoring route child {field} must equal nested reviewed head")
    if child.get("merged_observed_merge_sha") != merge_sha:
        errors.append("refactoring route child provider merge SHA mismatch")
    if child.get("merge_first_parent_sha") != base_sha:
        errors.append("refactoring route child first parent mismatch")
    if child.get("refreshed_integration_sha") != route_output.get("final_integration_sha"):
        errors.append("refactoring route final integration SHA mismatch")
    if child.get("post_merge_auditor_current_head") != route_output.get(
        "final_integration_sha"
    ):
        errors.append(
            "refactoring route child post_merge_auditor_current_head must equal final integration SHA"
        )
    if child.get("auditor_baseline_sha") != nested_base_sha:
        errors.append("refactoring route child auditor baseline must equal nested reviewed base")
    for stage, field in (
        ("pre-merge", "pre_merge_auditor_reports"),
        ("post-merge", "post_merge_auditor_reports"),
    ):
        _validate_refactoring_auditor_collection_shape(
            child.get(field),
            stage=stage,
            label=f"refactoring route child {field}",
            errors=errors,
        )
    auditor_index: dict[str, Any] | None = None
    if (auditor_index_path := current_artifacts.get("auditor_index")) is not None:
        try:
            auditor_index = _load_json(auditor_index_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    if auditor_index is not None:
        _validate_refactoring_auditor_index(
            auditor_index,
            feature_branch=feature_branch,
            ticket_id=ticket_id,
            attempt_number=attempt_number,
            route_invocation_uuid=route_invocation_uuid,
            child=child,
            errors=errors,
        )
    for stem in ("pre_merge_evidence", "pre_merge_process_tree_audit", "process_tree_audit"):
        _current_artifact(
            child,
            f"{stem}_path",
            f"{stem}_sha256",
            errors,
            label=f"refactoring child {stem}",
        )
    if child.get("pre_merge_evidence_verdict") != "PASS":
        errors.append("refactoring route child pre-merge evidence must equal PASS")
    return sorted(companions, key=lambda row: str(row.get("path")))


def _route_process_node_specs(owning_route: str) -> dict[str, tuple[str, str]]:
    route_spec = _ROUTE_KIND_SPECS[owning_route]
    return {
        "route-child": (route_spec["operator"], route_spec["model"]),
        "independent-process-auditor": ("process-tree-auditor", "gpt-high"),
    }


def _route_expected_nodes(
    expected: dict[str, Any],
    *,
    stage: str,
    root_uuid: str,
    ticket_id: Any,
    attempt_number: Any,
    owning_route: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if set(expected) != _ROUTE_PROCESS_EXPECTED_FIELDS:
        errors.append(
            f"{stage} expected-process fields must exactly equal: "
            + ",".join(sorted(_ROUTE_PROCESS_EXPECTED_FIELDS))
        )
    if expected.get("schema") != "feature-route-expected-process-v1":
        errors.append(f"{stage} expected-process schema is invalid")
    coverage_command_sha256 = expected.get("local_coverage_command_sha256")
    if not isinstance(coverage_command_sha256, str) or not _SHA256.fullmatch(
        coverage_command_sha256
    ):
        errors.append(
            f"{stage} expected-process local_coverage_command_sha256 must be a lowercase SHA-256"
        )
    route_spec = _ROUTE_KIND_SPECS[owning_route]
    for field, value in (
        ("stage", stage),
        ("feature_invocation_uuid", root_uuid),
        ("ticket_id", ticket_id),
        ("attempt_number", attempt_number),
        ("owning_route", owning_route),
        ("expected_direct_operator", route_spec["operator"]),
        ("expected_direct_model", route_spec["model"]),
        ("child_result_schema", route_spec["result_schema"]),
        ("child_result_sha256_join_field", "child_result_sha256"),
        ("route_invocation_uuid_join_field", "route_invocation_uuid"),
    ):
        if expected.get(field) != value:
            errors.append(f"{stage} expected-process {field} mismatch")
    child_result_path, path_errors = _canonical_absolute_path(
        expected.get("child_result_path"), f"{stage} expected-process child_result_path"
    )
    errors.extend(path_errors)
    nodes = expected.get("nodes")
    if not isinstance(nodes, list):
        errors.append(f"{stage} expected-process nodes must be a list")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    all_paths: list[str] = []
    expected_ids = _ROUTE_PROCESS_STAGE_NODES[stage]
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or set(node) != _ROUTE_PROCESS_EXPECTED_NODE_FIELDS:
            errors.append(f"{stage} expected-process nodes[{index}] fields are invalid")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or node_id not in expected_ids or node_id in indexed:
            errors.append(f"{stage} expected-process nodes[{index}] id is invalid or duplicate")
            continue
        operator, model = _route_process_node_specs(owning_route)[node_id]
        output_mode = "file-produced" if node_id == "route-child" else "stdout-extracted"
        fixed = {
            "required": True,
            "operator_or_role": operator,
            "model": model,
            "parent": "root",
            "log_sha256_join_field": "log_sha256",
            "canonical_output_sha256_join_field": "canonical_output_sha256",
            "output_mode": output_mode,
        }
        for field, value in fixed.items():
            if node.get(field) != value:
                errors.append(f"{stage} expected-process {node_id}.{field} is invalid")
        _current_artifact(
            node,
            "prompt_path",
            "prompt_sha256",
            errors,
            label=f"{stage} expected-process {node_id} prompt",
        )
        for field in ("prompt_path", "log_path", "canonical_output_path"):
            canonical, path_errors = _canonical_absolute_path(
                node.get(field), f"{stage} expected-process {node_id}.{field}"
            )
            errors.extend(path_errors)
            if canonical is not None:
                all_paths.append(canonical)
        if node_id == "route-child" and (
            canonical_output := node.get("canonical_output_path")
        ):
            if canonical_output != child_result_path:
                errors.append(
                    f"{stage} expected-process route-child canonical output must equal child_result_path"
                )
        indexed[node_id] = node
    if tuple(indexed) != expected_ids:
        errors.append(f"{stage} expected-process nodes must equal the exact canonical child order")
    if len(all_paths) != len(set(all_paths)):
        errors.append(f"{stage} expected-process artifact paths must be pairwise distinct")
    return indexed


def _route_dispatch_nodes(
    dispatch: dict[str, Any],
    expected_nodes: dict[str, dict[str, Any]],
    *,
    stage: str,
    root_uuid: str,
    ticket_id: Any,
    attempt_number: Any,
    owning_route: str,
    local_coverage_command_sha256: Any,
    expected_path: Path,
    expected_sha256: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if set(dispatch) != _ROUTE_PROCESS_DISPATCH_FIELDS:
        errors.append(
            f"{stage} dispatch evidence fields must exactly equal: "
            + ",".join(sorted(_ROUTE_PROCESS_DISPATCH_FIELDS))
        )
    if dispatch.get("schema") != "feature-route-dispatch-evidence-v1":
        errors.append(f"{stage} dispatch evidence schema is invalid")
    route_spec = _ROUTE_KIND_SPECS[owning_route]
    raw_nodes = dispatch.get("nodes")
    route_node = next(
        (
            node
            for node in raw_nodes
            if isinstance(node, dict) and node.get("id") == "route-child"
        ),
        {},
    ) if isinstance(raw_nodes, list) else {}
    fixed = {
        "stage": stage,
        "feature_invocation_uuid": root_uuid,
        "local_coverage_command_sha256": local_coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": owning_route,
        "expected_direct_operator": route_spec["operator"],
        "expected_direct_model": route_spec["model"],
        "child_result_schema": route_spec["result_schema"],
        "child_result_path": expected_nodes.get("route-child", {}).get(
            "canonical_output_path"
        ),
        "child_result_sha256": route_node.get("canonical_output_sha256"),
        "route_invocation_uuid": route_node.get("invocation_uuid"),
        "expected_process_path": str(expected_path),
        "expected_process_sha256": expected_sha256,
    }
    for field, value in fixed.items():
        if dispatch.get(field) != value:
            errors.append(f"{stage} dispatch evidence {field} mismatch")
    nodes = dispatch.get("nodes")
    if not isinstance(nodes, list):
        errors.append(f"{stage} dispatch evidence nodes must be a list")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    all_paths: list[str] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or set(node) != _ROUTE_PROCESS_DISPATCH_NODE_FIELDS:
            errors.append(f"{stage} dispatch evidence nodes[{index}] fields are invalid")
            continue
        node_id = node.get("id")
        expected_node = expected_nodes.get(node_id) if isinstance(node_id, str) else None
        if not isinstance(node_id, str) or expected_node is None or node_id in indexed:
            errors.append(f"{stage} dispatch evidence nodes[{index}] id is invalid or duplicate")
            continue
        operator, model = _route_process_node_specs(owning_route)[node_id]
        if node.get("operator_or_role") != operator:
            errors.append(f"{stage} dispatch evidence {node_id} operator mismatch")
        if node.get("model") != model:
            errors.append(f"{stage} dispatch evidence {node_id} model mismatch")
        if node.get("parent_invocation_uuid") != root_uuid:
            errors.append(f"{stage} dispatch evidence {node_id} parent mismatch")
        try:
            _canonical_uuid(node.get("invocation_uuid"), f"{stage} {node_id} invocation_uuid")
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
        if not _nonblank(node.get("provider_source")):
            errors.append(f"{stage} dispatch evidence {node_id} provider_source is invalid")
        for field in ("prompt_path", "log_path", "canonical_output_path", "output_mode"):
            if node.get(field) != expected_node.get(field):
                errors.append(f"{stage} dispatch evidence {node_id}.{field} mismatch")
        for stem, label in (
            ("prompt", "prompt"),
            ("log", "runner log"),
            ("canonical_output", "canonical output"),
        ):
            path = _current_artifact(
                node,
                f"{stem}_path",
                f"{stem}_sha256",
                errors,
                label=f"{stage} dispatch evidence {node_id} {label}",
            )
            if path is not None:
                all_paths.append(str(path))
        indexed[node_id] = node
    if tuple(indexed) != _ROUTE_PROCESS_STAGE_NODES[stage]:
        errors.append(f"{stage} dispatch evidence nodes must equal the exact canonical child order")
    if len(all_paths) != len(set(all_paths)):
        errors.append(f"{stage} dispatch child artifact paths must be pairwise distinct")
    return indexed


def _validate_route_process_stage(
    acceptance: dict[str, Any],
    artifact_paths: dict[str, Path],
    artifact_hashes: dict[str, str],
    *,
    stage: str,
    root_uuid: str,
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    prefix = "pre_audit" if stage == "pre-audit" else "final"
    owning_route = acceptance.get("owning_route")
    if owning_route not in _ROUTE_KIND_SPECS:
        errors.append(f"{stage} route proof owning_route is invalid")
        owning_route = "implementation-pipeline"
    expected_path = artifact_paths.get(f"{prefix}_expected_process")
    dispatch_path = artifact_paths.get(f"{prefix}_dispatch_snapshot")
    trace_path = artifact_paths.get(f"{prefix}_trace")
    expected: dict[str, Any] = {}
    dispatch: dict[str, Any] = {}
    trace: dict[str, Any] = {}
    if expected_path is not None:
        try:
            expected = _load_json(expected_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    expected_nodes = _route_expected_nodes(
        expected,
        stage=stage,
        root_uuid=root_uuid,
        ticket_id=acceptance.get("ticket_id"),
        attempt_number=acceptance.get("attempt_number"),
        owning_route=owning_route,
        errors=errors,
    )
    if dispatch_path is not None and expected_path is not None:
        try:
            dispatch = _load_json(dispatch_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
        dispatch_nodes = _route_dispatch_nodes(
            dispatch,
            expected_nodes,
            stage=stage,
            root_uuid=root_uuid,
            ticket_id=acceptance.get("ticket_id"),
            attempt_number=acceptance.get("attempt_number"),
            owning_route=owning_route,
            local_coverage_command_sha256=expected.get(
                "local_coverage_command_sha256"
            ),
            expected_path=expected_path,
            expected_sha256=artifact_hashes.get(f"{prefix}_expected_process", ""),
            errors=errors,
        )
    else:
        dispatch_nodes = {}
    if trace_path is not None:
        try:
            trace = _load_json(trace_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
        _validate_orchestrator_route_against_trace(
            trace,
            root_uuid,
            dispatch_nodes,
            _route_process_node_specs(owning_route),
            errors,
            stage=stage,
        )
    return expected, dispatch, dispatch_nodes


def _artifact_ref(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve(strict=False)), "sha256": _sha256_file(path)}


def _child_process_proof_refs(
    companions: list[dict[str, Any]], route_output: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    proof_rows: list[Any] = []
    if route_output.get("schema") == "implementation-pipeline-result-v1":
        proof_rows = route_output.get("owned_process_proofs", [])
    elif route_output.get("schema") == "refactoring-route-result-v1":
        proof_rows = list(route_output.get("owned_process_proofs", []))
        child = route_output.get("child")
        if isinstance(child, dict):
            proof_rows.extend(child.get("owned_process_proofs", []))
    companion_index = {
        (row.get("path"), row.get("sha256")) for row in companions if isinstance(row, dict)
    }
    for proof in proof_rows:
        if not isinstance(proof, dict):
            continue
        for artifact in ("expected_process", "process_tree", "process_tree_audit"):
            path = proof.get(f"{artifact}_path")
            sha256 = proof.get(f"{artifact}_sha256")
            if (path, sha256) not in companion_index:
                continue
            rows.append(
                {
                    "owner": proof.get("owner"),
                    "stage": proof.get("stage"),
                    "artifact": artifact,
                    "path": path,
                    "sha256": sha256,
                }
            )
    return sorted(rows, key=lambda row: (row["owner"], row["stage"], row["artifact"]))


def validate_route_process_proof(
    *,
    owning_route: str,
    feature_branch: str,
    ticket_id: str,
    attempt_number: int,
    route_evidence_path: Path,
    pre_audit_expected_path: Path,
    pre_audit_dispatch_path: Path,
    pre_audit_trace_path: Path,
    process_report_path: Path,
    process_report_binding_path: Path,
    final_expected_path: Path,
    final_dispatch_path: Path,
    final_trace_path: Path,
) -> dict[str, Any]:
    """Validate route-discriminated feature-root process proof without merge fields."""

    errors: list[str] = []
    if owning_route not in _ROUTE_KIND_SPECS:
        errors.append("owning_route must equal implementation-pipeline or refactoring")
    errors.extend(_validate_short_branch(feature_branch, "feature_branch"))
    if not _nonblank(ticket_id):
        errors.append("ticket_id must be non-blank")
    if not isinstance(attempt_number, int) or attempt_number <= 0:
        errors.append("attempt_number must be positive")
    route_spec = _ROUTE_KIND_SPECS.get(
        owning_route, _ROUTE_KIND_SPECS["implementation-pipeline"]
    )
    supplied_paths = {
        "route_evidence": route_evidence_path,
        "pre_audit_expected_process": pre_audit_expected_path,
        "pre_audit_dispatch_snapshot": pre_audit_dispatch_path,
        "pre_audit_trace": pre_audit_trace_path,
        "process_report": process_report_path,
        "process_report_binding": process_report_binding_path,
        "final_expected_process": final_expected_path,
        "final_dispatch_snapshot": final_dispatch_path,
        "final_trace": final_trace_path,
    }
    artifact_paths: dict[str, Path] = {}
    artifact_hashes: dict[str, str] = {}
    for field, path in supplied_paths.items():
        try:
            identity = path.resolve(strict=True)
            artifact_paths[field] = identity
            artifact_hashes[field] = _sha256_file(identity)
        except OSError as exc:
            errors.append(f"cannot hash route process {field} {path}: {exc}")
    if len(set(artifact_paths.values())) != len(artifact_paths):
        errors.append("route process supplied artifact paths must be pairwise distinct")
    proof_identity = {
        "feature_branch": feature_branch,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": owning_route,
    }
    binding = (
        _load_process_binding(artifact_paths["process_report"], errors)
        if "process_report" in artifact_paths
        else {}
    )
    root_uuid = ""
    if binding:
        if binding.get("mode") != "blocking":
            errors.append("process report mode must equal blocking")
        report_identity = binding.get("report_identity")
        if not isinstance(report_identity, dict) or report_identity.get(
            "operator_file"
        ) != str(_REPO_ROOT / "agents/feature-orchestrator.md"):
            errors.append("process report operator identity mismatch")
        if binding.get("subtree_root_uuid") is not None:
            errors.append("process report subtree root must be none")
        try:
            root_uuid = _canonical_uuid(
                binding.get("root_invocation_uuid"), "route process root_invocation_uuid"
            )
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    separate_binding: dict[str, Any] = {}
    binding_path = artifact_paths.get("process_report_binding")
    if binding_path is not None:
        try:
            separate_binding = _load_json(binding_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    if separate_binding != binding:
        errors.append("process report binding artifact must equal the embedded machine binding")

    pre_expected, pre_dispatch, pre_nodes = _validate_route_process_stage(
        proof_identity,
        artifact_paths,
        artifact_hashes,
        stage="pre-audit",
        root_uuid=root_uuid,
        errors=errors,
    )
    final_expected, final_dispatch, final_nodes = _validate_route_process_stage(
        proof_identity,
        artifact_paths,
        artifact_hashes,
        stage="final",
        root_uuid=root_uuid,
        errors=errors,
    )
    coverage_command_sha256 = pre_expected.get("local_coverage_command_sha256")
    if final_expected.get("local_coverage_command_sha256") != coverage_command_sha256:
        errors.append(
            "final expected process must preserve local_coverage_command_sha256"
        )
    if pre_expected.get("nodes") and final_expected.get("nodes"):
        if pre_expected["nodes"][0] != final_expected["nodes"][0]:
            errors.append("final expected process must preserve the exact pre-audit route child")
    else:
        errors.append("route process expected manifests must contain the route child")
    if pre_nodes.get("route-child") != final_nodes.get("route-child"):
        errors.append("final dispatch evidence must preserve the exact pre-audit route child")
    route_node = pre_nodes.get("route-child", {})
    child_result_path_value = route_node.get("canonical_output_path")
    child_result_path: Path | None = None
    route_output: dict[str, Any] = {}
    if isinstance(child_result_path_value, str):
        try:
            child_result_path = Path(child_result_path_value).resolve(strict=True)
            route_output = _load_json(child_result_path)
            artifact_paths["child_result"] = child_result_path
            artifact_hashes["child_result"] = _sha256_file(child_result_path)
        except (OSError, ContractValidationError) as exc:
            detail = exc.decision["errors"] if isinstance(exc, ContractValidationError) else [str(exc)]
            errors.extend(f"child result: {error}" for error in detail)
    else:
        errors.append("route process child result path is invalid")
    if route_output.get("schema") != route_spec["result_schema"]:
        errors.append("route child result schema does not match owning route")
    route_uuid = route_node.get("invocation_uuid")
    companions: list[dict[str, Any]] = []
    if owning_route == "implementation-pipeline":
        required_missing = sorted(_IMPLEMENTATION_ROUTE_OUTPUT_REQUIRED_FIELDS - set(route_output))
        if required_missing:
            errors.append(
                "implementation route output missing required fields: "
                + ",".join(required_missing)
            )
        for field, expected in (
            ("status", "VERIFIED_DRAFT_PR"),
            ("ticket_id", ticket_id),
            ("owning_route", owning_route),
            ("route_attempt_number", attempt_number),
            ("base_branch", feature_branch),
            ("base_ref", f"refs/remotes/origin/{feature_branch}"),
        ):
            if route_output.get(field) != expected:
                errors.append(f"implementation route output {field} mismatch")
        companions = _implementation_owned_process_proof_companions(route_output, errors)
    elif owning_route == "refactoring":
        companions = _validate_refactoring_route_result(
            route_output,
            feature_branch=feature_branch,
            ticket_id=ticket_id,
            attempt_number=attempt_number,
            route_invocation_uuid=route_uuid if isinstance(route_uuid, str) else "",
            errors=errors,
        )
    child_process_refs = _child_process_proof_refs(companions, route_output)

    route_evidence: dict[str, Any] = {}
    route_evidence_identity = artifact_paths.get("route_evidence")
    if route_evidence_identity is not None:
        try:
            route_evidence = _load_json(route_evidence_identity)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    if set(route_evidence) != _ROUTE_EVIDENCE_FIELDS:
        errors.append(
            "route evidence fields must exactly equal: "
            + ",".join(sorted(_ROUTE_EVIDENCE_FIELDS))
        )
    for field, expected in (
        ("schema", "feature-route-evidence-v1"),
        ("ticket_id", ticket_id),
        ("attempt_number", attempt_number),
        ("owning_route", owning_route),
        ("verdict", "PASS"),
    ):
        if route_evidence.get(field) != expected:
            errors.append(f"route evidence {field} mismatch")
    provider_reviewed_identity = route_evidence.get("provider_reviewed_identity")
    if not isinstance(provider_reviewed_identity, dict) or provider_reviewed_identity.get(
        "base_ref_name"
    ) != feature_branch:
        errors.append("route evidence provider base_ref_name must equal feature_branch")
    if owning_route == "refactoring" and isinstance(route_output.get("child"), dict):
        child = route_output["child"]
        expected_provider_identity = {
            "pr_url": child.get("pr_url"),
            "pr_number": child.get("pr_number"),
            "state": child.get("open_pr_state"),
            "is_draft": child.get("open_observed_is_draft"),
            "base_ref_name": child.get("open_observed_base_ref_name"),
            "base_ref_oid": child.get("open_observed_base_sha"),
            "head_ref_name": child.get("open_observed_head_ref_name"),
            "head_ref_oid": child.get("open_observed_head_sha"),
        }
        if provider_reviewed_identity != expected_provider_identity:
            errors.append(
                "refactoring route evidence provider reviewed identity mismatch child open observation"
            )
    child_ref = (
        _artifact_ref(child_result_path)
        if child_result_path is not None and child_result_path.exists()
        else None
    )
    if route_evidence.get("route_output") != child_ref:
        errors.append("route evidence child result binding mismatch")

    if binding:
        if binding.get("expected_process") != (
            _artifact_ref(artifact_paths["pre_audit_expected_process"])
            if "pre_audit_expected_process" in artifact_paths
            else None
        ):
            errors.append("process report expected_process binding mismatch")
        if binding.get("process_tree") != (
            _artifact_ref(artifact_paths["pre_audit_trace"])
            if "pre_audit_trace" in artifact_paths
            else None
        ):
            errors.append("process report trace binding mismatch")
        expected_companions = sorted(
            [
                _artifact_ref(artifact_paths[field])
                for field in (
                    "route_evidence",
                    "child_result",
                    "pre_audit_dispatch_snapshot",
                )
                if field in artifact_paths
            ]
            + companions,
            key=lambda row: str(row.get("path")),
        )
        auditor_expected = next(
            (
                node
                for node in final_expected.get("nodes", [])
                if isinstance(node, dict) and node.get("id") == "independent-process-auditor"
            ),
            {},
        )
        auditor_prompt_path = auditor_expected.get("prompt_path")
        auditor_prompt_sha256 = auditor_expected.get("prompt_sha256")
        if isinstance(auditor_prompt_path, str) and isinstance(
            auditor_prompt_sha256, str
        ):
            expected_companions.append(
                {
                    "path": auditor_prompt_path,
                    "sha256": auditor_prompt_sha256,
                }
            )
            expected_companions.sort(key=lambda row: str(row.get("path")))
        if binding.get("companion_artifacts") != expected_companions:
            errors.append("process report companion artifact binding mismatch")
    discovered = {
        "route_prompt": route_node.get("prompt_path"),
        "route_log": route_node.get("log_path"),
        "child_result": route_node.get("canonical_output_path"),
    }
    auditor_node = final_nodes.get("independent-process-auditor", {})
    discovered.update(
        {
            "process_auditor_prompt": auditor_node.get("prompt_path"),
            "process_auditor_log": auditor_node.get("log_path"),
            "process_auditor_output": auditor_node.get("canonical_output_path"),
        }
    )
    for field, value in discovered.items():
        if not isinstance(value, str):
            errors.append(f"route process {field} path is invalid")
            continue
        try:
            path = Path(value).resolve(strict=True)
            artifact_paths[field] = path
            artifact_hashes[field] = _sha256_file(path)
        except OSError as exc:
            errors.append(f"cannot hash route process {field} {value}: {exc}")
    report = artifact_paths.get("process_report")
    output = artifact_paths.get("process_auditor_output")
    if report is not None and output is not None:
        try:
            if report.read_bytes() != output.read_bytes():
                errors.append(
                    "process report bytes must equal the provider-only independent auditor output"
                )
        except OSError as exc:
            errors.append(f"cannot compare process report and auditor output: {exc}")
    all_proof_paths = [artifact_paths.get(field) for field in _ROUTE_PROOF_ARTIFACT_FIELDS]
    if None not in all_proof_paths and len(all_proof_paths) != len(set(all_proof_paths)):
        errors.append("route process proof artifact paths must be pairwise distinct")
    artifacts = {
        field: _artifact_ref(artifact_paths[field])
        for field in _ROUTE_PROOF_ARTIFACT_FIELDS
        if field in artifact_paths
    }
    return {
        "schema": "feature-route-process-proof-validation-v1",
        "status": "PASS" if not errors else "INVALID",
        "feature_branch": feature_branch,
        "local_coverage_command_sha256": coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": owning_route,
        "expected_direct_operator": route_spec["operator"],
        "expected_direct_model": route_spec["model"],
        "child_result_schema": route_spec["result_schema"],
        "route_invocation_uuid": route_uuid,
        "artifacts": artifacts,
        "child_owned_process_proofs": child_process_refs,
        "errors": errors,
    }


def validate_route_attempt_proof(proof_path: Path) -> dict[str, Any]:
    """Re-hash one closed route-attempt envelope and rerun common route semantics."""

    errors: list[str] = []
    try:
        proof_identity = proof_path.resolve(strict=True)
        proof = _load_json(proof_identity)
        proof_sha256 = _sha256_file(proof_identity)
    except (OSError, ContractValidationError) as exc:
        detail = exc.decision["errors"] if isinstance(exc, ContractValidationError) else [str(exc)]
        return {
            "schema": "feature-route-attempt-proof-validation-v1",
            "status": "INVALID",
            "proof_envelope_path": str(proof_path.resolve(strict=False)),
            "proof_envelope_sha256": None,
            "feature_branch": None,
            "local_coverage_command_sha256": None,
            "ticket_id": None,
            "attempt_number": None,
            "owning_route": None,
            "common_validation": None,
            "route_specific_evidence": None,
            "errors": detail,
        }
    if set(proof) != _ROUTE_ATTEMPT_PROOF_FIELDS:
        errors.append(
            "route attempt proof fields must exactly equal: "
            + ",".join(sorted(_ROUTE_ATTEMPT_PROOF_FIELDS))
        )
    if proof.get("schema") != "feature-route-attempt-proof-v1":
        errors.append("route attempt proof schema is invalid")
    ticket_id = proof.get("ticket_id")
    attempt_number = proof.get("attempt_number")
    owning_route = proof.get("owning_route")
    feature_branch = proof.get("feature_branch")
    coverage_command_sha256 = proof.get("local_coverage_command_sha256")
    errors.extend(_validate_short_branch(feature_branch, "route attempt proof feature_branch"))
    if not isinstance(coverage_command_sha256, str) or not _SHA256.fullmatch(
        coverage_command_sha256
    ):
        errors.append(
            "route attempt proof local_coverage_command_sha256 must be a lowercase SHA-256"
        )
    if not _nonblank(ticket_id):
        errors.append("route attempt proof ticket_id must be non-blank")
    if not isinstance(attempt_number, int) or attempt_number <= 0:
        errors.append("route attempt proof attempt_number must be positive")
    if owning_route not in _ROUTE_KIND_SPECS:
        errors.append("route attempt proof owning_route is invalid")

    artifact_paths: dict[str, Path] = {}
    artifact_refs: dict[str, dict[str, Any]] = {}
    for field in (*_ROUTE_PROOF_ARTIFACT_FIELDS, "common_validation_result", "route_specific_evidence"):
        path, actual_hash = _lineage_artifact(proof, field, errors)
        entry = proof.get(field)
        if isinstance(entry, dict):
            artifact_refs[field] = entry
        if path is not None:
            artifact_paths[field] = path
            if path == proof_identity:
                errors.append(f"route attempt proof {field} must not reference itself")
        if path is not None and actual_hash is not None:
            artifact_refs[field] = {"path": str(path), "sha256": actual_hash}
    if len(artifact_paths) != len(set(artifact_paths.values())):
        errors.append("route attempt proof artifact paths must be pairwise distinct")

    proof_companions = proof.get("child_owned_process_proofs")
    if not isinstance(proof_companions, list):
        errors.append("route attempt proof child_owned_process_proofs must be a list")
        proof_companions = []
    companion_paths: list[Path] = []
    for index, row in enumerate(proof_companions):
        if not isinstance(row, dict) or set(row) != _CHILD_PROCESS_PROOF_REF_FIELDS:
            errors.append(
                f"route attempt proof child_owned_process_proofs[{index}] fields are invalid"
            )
            continue
        path = _current_artifact(
            row,
            "path",
            "sha256",
            errors,
            label=f"route attempt proof child process companion {index}",
        )
        if path is not None:
            companion_paths.append(path)
    if len(companion_paths) != len(set(companion_paths)):
        errors.append("route attempt proof child process companion paths must be distinct")
    if set(companion_paths) & set(artifact_paths.values()):
        errors.append("route attempt proof child process companions must not alias feature artifacts")

    common_validation: dict[str, Any] | None = None
    required_common = {
        "route_evidence",
        "pre_audit_expected_process",
        "pre_audit_dispatch_snapshot",
        "pre_audit_trace",
        "process_report",
        "process_report_binding",
        "final_expected_process",
        "final_dispatch_snapshot",
        "final_trace",
    }
    if required_common <= set(artifact_paths) and isinstance(ticket_id, str) and isinstance(
        attempt_number, int
    ) and isinstance(owning_route, str) and isinstance(feature_branch, str):
        common_validation = validate_route_process_proof(
            owning_route=owning_route,
            feature_branch=feature_branch,
            ticket_id=ticket_id,
            attempt_number=attempt_number,
            route_evidence_path=artifact_paths["route_evidence"],
            pre_audit_expected_path=artifact_paths["pre_audit_expected_process"],
            pre_audit_dispatch_path=artifact_paths["pre_audit_dispatch_snapshot"],
            pre_audit_trace_path=artifact_paths["pre_audit_trace"],
            process_report_path=artifact_paths["process_report"],
            process_report_binding_path=artifact_paths["process_report_binding"],
            final_expected_path=artifact_paths["final_expected_process"],
            final_dispatch_path=artifact_paths["final_dispatch_snapshot"],
            final_trace_path=artifact_paths["final_trace"],
        )
        if common_validation.get("status") != "PASS":
            errors.extend(
                f"common route process proof: {error}"
                for error in common_validation.get("errors", [])
            )
        expected_artifacts = {
            field: proof.get(field) for field in _ROUTE_PROOF_ARTIFACT_FIELDS
        }
        if common_validation.get("artifacts") != expected_artifacts:
            errors.append("common route process validation artifact bindings mismatch")
        if common_validation.get("child_owned_process_proofs") != proof_companions:
            errors.append("common route process child companion bindings mismatch")
        if common_validation.get("local_coverage_command_sha256") != coverage_command_sha256:
            errors.append(
                "common route process local_coverage_command_sha256 mismatch"
            )
    recorded_common: dict[str, Any] = {}
    common_path = artifact_paths.get("common_validation_result")
    if common_path is not None:
        try:
            recorded_common = _load_json(common_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    if common_validation is not None and recorded_common != common_validation:
        errors.append("recorded common route process validation is stale or mismatched")
    if recorded_common.get("status") != "PASS":
        errors.append("recorded common route process validation must equal PASS")

    route_specific: dict[str, Any] = {}
    route_specific_path = artifact_paths.get("route_specific_evidence")
    if route_specific_path is not None:
        try:
            route_specific = _load_json(route_specific_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    if set(route_specific) != _ROUTE_OUTCOME_EVIDENCE_FIELDS:
        errors.append(
            "route-specific evidence fields must exactly equal: "
            + ",".join(sorted(_ROUTE_OUTCOME_EVIDENCE_FIELDS))
        )
    for field, expected in (
        ("schema", "feature-route-attempt-outcome-v1"),
        ("feature_branch", feature_branch),
        ("ticket_id", ticket_id),
        ("attempt_number", attempt_number),
        ("owning_route", owning_route),
        ("child_result", proof.get("child_result")),
    ):
        if route_specific.get(field) != expected:
            errors.append(f"route-specific evidence {field} mismatch")
    authorization = route_specific.get("merge_authorization")
    if route_specific.get("state") == "VERIFIED_MERGED" and owning_route == "implementation-pipeline":
        if not isinstance(authorization, dict) or set(authorization) != {"path", "sha256"}:
            errors.append("implementation merged outcome requires merge authorization path/hash")
        else:
            authorization_path = _current_artifact(
                authorization,
                "path",
                "sha256",
                errors,
                label="implementation merge authorization",
            )
            if authorization_path is not None:
                try:
                    recorded_authorization = _load_json(authorization_path)
                except ContractValidationError as exc:
                    errors.extend(exc.decision["errors"])
                    recorded_authorization = {}
                acceptance_path = recorded_authorization.get("acceptance_path")
                fresh_path = recorded_authorization.get("fresh_currentness_path")
                if isinstance(acceptance_path, str) and isinstance(fresh_path, str):
                    current_authorization = validate_route_artifact_lineage(
                        Path(acceptance_path), Path(fresh_path)
                    )
                    if current_authorization != recorded_authorization:
                        errors.append("implementation merge authorization is stale or mismatched")
                    if current_authorization.get("status") != "MERGE_AUTHORIZED":
                        errors.append("implementation merge authorization must authorize merge")
                else:
                    errors.append("implementation merge authorization paths are invalid")
    elif authorization is not None:
        errors.append("route-specific merge authorization must be null for this outcome")
    return {
        "schema": "feature-route-attempt-proof-validation-v1",
        "status": "PASS" if not errors else "INVALID",
        "proof_envelope_path": str(proof_identity),
        "proof_envelope_sha256": proof_sha256,
        "feature_branch": feature_branch,
        "local_coverage_command_sha256": coverage_command_sha256,
        "ticket_id": ticket_id,
        "attempt_number": attempt_number,
        "owning_route": owning_route,
        "common_validation": common_validation,
        "route_specific_evidence": route_specific,
        "errors": errors,
    }


def _validate_route_evidence(
    route_evidence: dict[str, Any],
    route_evidence_path: Path,
    acceptance: dict[str, Any],
    acceptance_path: Path,
    reviewed: dict[str, Any],
    route_output: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if set(route_evidence) != _ROUTE_EVIDENCE_FIELDS:
        errors.append(
            "route evidence fields must exactly equal: "
            + ",".join(sorted(_ROUTE_EVIDENCE_FIELDS))
        )
    if route_evidence.get("schema") != "feature-route-evidence-v1":
        errors.append("route evidence schema must equal feature-route-evidence-v1")
    if route_evidence.get("ticket_id") != acceptance.get("ticket_id"):
        errors.append("route evidence ticket_id mismatch")
    if route_evidence.get("attempt_number") != acceptance.get("attempt_number"):
        errors.append("route evidence attempt_number mismatch")
    if route_evidence.get("ticket_system") not in {"jira", "linear"}:
        errors.append("route evidence ticket_system must equal jira or linear")
    if not _valid_ticket_site_url(
        route_evidence.get("ticket_site_url"), route_evidence.get("ticket_system", "")
    ):
        errors.append("route evidence ticket_site_url is invalid")
    if route_evidence.get("owning_route") != "implementation-pipeline":
        errors.append("route evidence owning_route must equal implementation-pipeline")
    if route_evidence.get("verdict") != "PASS":
        errors.append("route evidence verdict must equal PASS")
    if route_evidence.get("provider_reviewed_identity") != reviewed:
        errors.append("route evidence provider reviewed identity mismatch")

    reviewed_base = route_evidence.get("reviewed_base_sha")
    reviewed_head = route_evidence.get("reviewed_head_sha")
    if reviewed_base != reviewed.get("base_ref_oid"):
        errors.append("route evidence reviewed_base_sha mismatch")
    if reviewed_head != reviewed.get("head_ref_oid"):
        errors.append("route evidence reviewed_head_sha mismatch")

    route_output_entry = route_evidence.get("route_output")
    if not isinstance(route_output_entry, dict) or set(route_output_entry) != {"path", "sha256"}:
        errors.append("route evidence route_output fields must exactly equal path,sha256")
    elif route_output_entry != acceptance.get("route_output"):
        errors.append("route evidence route_output binding mismatch")

    expected_context_path = _current_artifact(
        route_output,
        "ticket_operation_expected_context_path",
        "ticket_operation_expected_context_sha256",
        errors,
        label="ticket operation expected context",
    )
    expected_context: dict[str, Any] = {}
    if expected_context_path is not None:
        if expected_context_path in {route_evidence_path, acceptance_path}:
            errors.append(
                "ticket operation expected context must not reference route evidence or acceptance"
            )
        try:
            expected_context = _load_json(expected_context_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    expected_route_context = {
        "schema": "ticket-operation-expected-context-v1",
        "backend": route_evidence.get("ticket_system"),
        "ticket_site_url": route_evidence.get("ticket_site_url"),
        "ticket_key": route_evidence.get("ticket_id"),
        "operation": "comment-readback",
        "owning_route": route_evidence.get("owning_route"),
        "attempt_number": route_evidence.get("attempt_number"),
        "pr_url": reviewed.get("pr_url"),
        "pr_number": reviewed.get("pr_number"),
        "reviewed_base_branch": reviewed.get("base_ref_name"),
        "reviewed_base_ref": route_output.get("base_ref"),
        "reviewed_base_sha": reviewed.get("base_ref_oid"),
        "reviewed_head_branch": reviewed.get("head_ref_name"),
        "reviewed_head_ref": route_output.get("head_ref"),
        "reviewed_head_sha": reviewed.get("head_ref_oid"),
    }
    if expected_context != expected_route_context:
        errors.append(
            "ticket operation expected context does not equal feature route caller context"
        )

    ticket_result_ref = route_evidence.get("ticket_operation_result")
    if (
        not isinstance(ticket_result_ref, dict)
        or set(ticket_result_ref) != _TICKET_OPERATION_RESULT_REF_FIELDS
    ):
        errors.append("ticket_operation_result fields must exactly equal path,sha256")
    else:
        artifact_path, path_errors = _canonical_absolute_path(
            ticket_result_ref.get("path"), "ticket_operation_result.path"
        )
        errors.extend(path_errors)
        artifact_hash = ticket_result_ref.get("sha256")
        if not isinstance(artifact_hash, str) or not _SHA256.fullmatch(artifact_hash):
            errors.append("ticket_operation_result.sha256 must be a lowercase SHA-256")
        route_output_ref = {
            "path": route_output.get("ticket_operation_result_path"),
            "sha256": route_output.get("ticket_operation_result_sha256"),
        }
        if ticket_result_ref != route_output_ref:
            errors.append("ticket operation result does not match implementation result binding")
        if artifact_path is not None:
            artifact_identity = Path(artifact_path)
            if artifact_identity in {route_evidence_path, acceptance_path}:
                errors.append("ticket operation result must not reference route evidence or acceptance")
            if artifact_identity == expected_context_path:
                errors.append(
                    "ticket operation result and expected context paths must be distinct"
                )
            try:
                ticket_result = _load_json(artifact_identity)
                actual_hash = _sha256_file(artifact_identity)
            except (OSError, ContractValidationError) as exc:
                detail = exc.decision["errors"] if isinstance(exc, ContractValidationError) else [str(exc)]
                errors.extend(f"ticket operation result: {error}" for error in detail)
            else:
                if artifact_hash != actual_hash:
                    errors.append("ticket operation result hash mismatch")
                validation = validate_ticket_operation_result(
                    ticket_result,
                    expected_context,
                    result_path=artifact_identity,
                    expected_context_path=expected_context_path,
                )
                errors.extend(validation["errors"])

    forbidden_evidence = _recursive_keys(route_evidence) & _FORBIDDEN_FUTURE_HASH_FIELDS
    if forbidden_evidence:
        errors.append(
            "route evidence contains future hash fields: "
            + ",".join(sorted(forbidden_evidence))
        )
    return errors


def validate_route_artifact_lineage(
    acceptance_path: Path, fresh_currentness_path: Path
) -> dict[str, Any]:
    """Authorize a direct merge from acyclic immutable attempt artifacts."""

    errors: list[str] = []
    try:
        acceptance_identity = acceptance_path.resolve(strict=True)
        acceptance = _load_json(acceptance_identity)
        acceptance_sha256 = _sha256_file(acceptance_identity)
    except (OSError, ContractValidationError) as exc:
        detail = exc.decision["errors"] if isinstance(exc, ContractValidationError) else [str(exc)]
        return {
            "schema": "feature-route-artifact-lineage-validation-v1",
            "status": "INVALID",
            "acceptance_path": str(acceptance_path),
            "acceptance_sha256": None,
            "fresh_currentness_path": str(fresh_currentness_path),
            "fresh_currentness_sha256": None,
            "artifact_sha256": {},
            "errors": detail,
        }

    if set(acceptance) != _ACCEPTANCE_FIELDS:
        errors.append(
            "attempt acceptance fields must exactly equal: "
            + ",".join(sorted(_ACCEPTANCE_FIELDS))
        )
    if acceptance.get("schema") != "feature-route-attempt-acceptance-v1":
        errors.append("attempt acceptance schema is invalid")
    feature_branch = acceptance.get("feature_branch")
    errors.extend(_validate_short_branch(feature_branch, "attempt acceptance feature_branch"))
    if not _nonblank(acceptance.get("ticket_id")):
        errors.append("attempt acceptance ticket_id must be non-blank")
    if not isinstance(acceptance.get("attempt_number"), int) or acceptance["attempt_number"] <= 0:
        errors.append("attempt acceptance attempt_number must be positive")
    if acceptance.get("owning_route") != "implementation-pipeline":
        errors.append("attempt acceptance owning_route must equal implementation-pipeline")
    if acceptance.get("construction_order") != _LINEAGE_CONSTRUCTION_ORDER:
        errors.append("attempt acceptance construction_order is invalid")
    forbidden_acceptance = _recursive_keys(acceptance) & _FORBIDDEN_FUTURE_HASH_FIELDS
    if forbidden_acceptance:
        errors.append(
            "attempt acceptance contains self/future hash fields: "
            + ",".join(sorted(forbidden_acceptance))
        )

    artifact_paths: dict[str, Path] = {}
    artifact_hashes: dict[str, str] = {}
    for field in _LINEAGE_ARTIFACT_FIELDS:
        path, actual_hash = _lineage_artifact(acceptance, field, errors)
        if path is not None:
            artifact_paths[field] = path
            if path == acceptance_identity:
                errors.append(f"{field}.path must not reference the acceptance envelope")
        if actual_hash is not None:
            artifact_hashes[field] = actual_hash
    currentness_path, currentness_hash = _lineage_artifact(
        acceptance,
        "pre_ready_currentness",
        errors,
        extra_fields={"status", "final_equality_result"},
    )
    if currentness_path is not None:
        artifact_paths["pre_ready_currentness"] = currentness_path
        if currentness_path == acceptance_identity:
            errors.append("pre_ready_currentness.path must not reference the acceptance envelope")
    if currentness_hash is not None:
        artifact_hashes["pre_ready_currentness"] = currentness_hash
    if len(set(artifact_paths.values())) != len(artifact_paths):
        errors.append("attempt acceptance artifact paths must be pairwise distinct")

    reviewed = acceptance.get("provider_reviewed_identity")
    if not isinstance(reviewed, dict):
        errors.append("provider_reviewed_identity must be an object")
        reviewed = {}
    else:
        errors.extend(_validate_provider_bundle("provider_reviewed_identity", reviewed))
        if reviewed.get("is_draft") is not True:
            errors.append("provider_reviewed_identity.is_draft must equal true")
    if reviewed.get("base_ref_name") != feature_branch:
        errors.append("attempt acceptance provider base_ref_name must equal feature_branch")

    route_output: dict[str, Any] = {}
    route_output_path = artifact_paths.get("route_output")
    if route_output_path is not None:
        try:
            route_output = _load_json(route_output_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    missing_route_output_fields = sorted(
        _IMPLEMENTATION_ROUTE_OUTPUT_REQUIRED_FIELDS - set(route_output)
    )
    if missing_route_output_fields:
        errors.append(
            "implementation route output missing required fields: "
            + ",".join(missing_route_output_fields)
        )
    route_output_expected = {
        "schema": "implementation-pipeline-result-v1",
        "status": "VERIFIED_DRAFT_PR",
        "ticket_id": acceptance.get("ticket_id"),
        "owning_route": "implementation-pipeline",
        "route_attempt_number": acceptance.get("attempt_number"),
        "pr_url": reviewed.get("pr_url"),
        "pr_number": reviewed.get("pr_number"),
        "state": "OPEN",
        "is_draft": True,
        "phase_8_reviewed_is_draft": True,
        "base_branch": reviewed.get("base_ref_name"),
        "base_ref": f"refs/remotes/origin/{reviewed.get('base_ref_name')}",
        "head_branch": reviewed.get("head_ref_name"),
        "head_ref": f"refs/heads/{reviewed.get('head_ref_name')}",
        "phase_8_reviewed_base_sha": reviewed.get("base_ref_oid"),
        "phase_8_reviewed_head_sha": reviewed.get("head_ref_oid"),
        "phase_9_currentness_result": "PASS",
    }
    for field, expected_value in route_output_expected.items():
        if route_output.get(field) != expected_value:
            errors.append(f"implementation route output {field} mismatch")
    owned_process_companions = _implementation_owned_process_proof_companions(
        route_output, errors
    )
    owned_process_paths = {
        Path(row["path"])
        for row in owned_process_companions
        if isinstance(row.get("path"), str)
    }
    if owned_process_paths & ({acceptance_identity} | set(artifact_paths.values())):
        errors.append(
            "implementation owned process-proof paths must not alias feature lineage artifacts"
        )

    route_evidence_path = artifact_paths.get("route_evidence")
    if route_evidence_path is not None:
        try:
            route_evidence = _load_json(route_evidence_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
            route_evidence = {}
        if route_output.get("ticket_system") != route_evidence.get("ticket_system"):
            errors.append("implementation route output ticket_system mismatch")
        errors.extend(
            _validate_route_evidence(
                route_evidence,
                route_evidence_path,
                acceptance,
                acceptance_identity,
                reviewed,
                route_output,
            )
        )

    process_report_path = artifact_paths.get("process_report")
    binding = (
        _load_process_binding(process_report_path, errors)
        if process_report_path is not None
        else {}
    )
    root_uuid = ""
    if binding:
        if binding.get("mode") != "blocking":
            errors.append("process report mode must equal blocking")
        report_identity = binding.get("report_identity")
        if not isinstance(report_identity, dict) or report_identity.get(
            "operator_file"
        ) != str(_REPO_ROOT / "agents/feature-orchestrator.md"):
            errors.append("process report operator identity mismatch")
        if binding.get("subtree_root_uuid") is not None:
            errors.append("process report subtree root must be none")
        try:
            root_uuid = _canonical_uuid(
                binding.get("root_invocation_uuid"), "route process root_invocation_uuid"
            )
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
        if binding.get("expected_process") != acceptance.get("pre_audit_expected_process"):
            errors.append("process report expected_process binding mismatch")
        if binding.get("process_tree") != acceptance.get("pre_audit_trace"):
            errors.append("process report trace binding mismatch")
        expected_companions = sorted(
            [
                acceptance[field]
                for field in (
                    "route_evidence",
                    "route_output",
                    "pre_audit_dispatch_snapshot",
                    "process_auditor_prompt",
                )
                if isinstance(acceptance.get(field), dict)
            ]
            + owned_process_companions,
            key=lambda row: row["path"],
        )
        if binding.get("companion_artifacts") != expected_companions:
            errors.append("process report companion artifact binding mismatch")

    pre_expected, pre_dispatch, pre_nodes = _validate_route_process_stage(
        acceptance,
        artifact_paths,
        artifact_hashes,
        stage="pre-audit",
        root_uuid=root_uuid,
        errors=errors,
    )
    final_expected, final_dispatch, final_nodes = _validate_route_process_stage(
        acceptance,
        artifact_paths,
        artifact_hashes,
        stage="final",
        root_uuid=root_uuid,
        errors=errors,
    )
    pre_expected_nodes = pre_expected.get("nodes")
    final_expected_nodes = final_expected.get("nodes")
    if (
        not isinstance(pre_expected_nodes, list)
        or not isinstance(final_expected_nodes, list)
        or not pre_expected_nodes
        or not final_expected_nodes
        or pre_expected_nodes[0] != final_expected_nodes[0]
    ):
        errors.append("final expected process must preserve the exact pre-audit route child")
    if pre_nodes.get("route-child") != final_nodes.get("route-child"):
        errors.append("final dispatch evidence must preserve the exact pre-audit route child")

    auditor_node = final_nodes.get("independent-process-auditor", {})
    expected_auditor_paths = {
        "prompt_path": acceptance.get("process_auditor_prompt", {}).get("path")
        if isinstance(acceptance.get("process_auditor_prompt"), dict)
        else None,
        "log_path": acceptance.get("process_auditor_log", {}).get("path")
        if isinstance(acceptance.get("process_auditor_log"), dict)
        else None,
        "canonical_output_path": acceptance.get("process_auditor_output", {}).get("path")
        if isinstance(acceptance.get("process_auditor_output"), dict)
        else None,
    }
    for field, expected_value in expected_auditor_paths.items():
        if auditor_node.get(field) != expected_value:
            errors.append(f"independent process auditor {field} binding mismatch")
    if auditor_node.get("invocation_uuid") in {
        None,
        root_uuid,
        pre_nodes.get("route-child", {}).get("invocation_uuid"),
    }:
        errors.append("independent process auditor invocation UUID must be distinct")
    process_auditor_output_path = artifact_paths.get("process_auditor_output")
    if process_report_path is not None and process_auditor_output_path is not None:
        try:
            report_bytes = process_report_path.read_bytes()
            auditor_output_bytes = process_auditor_output_path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot compare process report and auditor output: {exc}")
        else:
            if report_bytes != auditor_output_bytes:
                errors.append(
                    "process report bytes must equal the provider-only independent auditor output"
                )

    common_required = {
        "route_evidence",
        "pre_audit_expected_process",
        "pre_audit_dispatch_snapshot",
        "pre_audit_trace",
        "process_report",
        "process_report_binding",
        "final_expected_process",
        "final_dispatch_snapshot",
        "final_trace",
    }
    if common_required <= set(artifact_paths):
        common_ticket_id = acceptance.get("ticket_id")
        common_attempt_number = acceptance.get("attempt_number")
        common_validation = validate_route_process_proof(
            owning_route="implementation-pipeline",
            feature_branch=feature_branch if isinstance(feature_branch, str) else "",
            ticket_id=common_ticket_id if isinstance(common_ticket_id, str) else "",
            attempt_number=(
                common_attempt_number if isinstance(common_attempt_number, int) else 0
            ),
            route_evidence_path=artifact_paths["route_evidence"],
            pre_audit_expected_path=artifact_paths["pre_audit_expected_process"],
            pre_audit_dispatch_path=artifact_paths["pre_audit_dispatch_snapshot"],
            pre_audit_trace_path=artifact_paths["pre_audit_trace"],
            process_report_path=artifact_paths["process_report"],
            process_report_binding_path=artifact_paths["process_report_binding"],
            final_expected_path=artifact_paths["final_expected_process"],
            final_dispatch_path=artifact_paths["final_dispatch_snapshot"],
            final_trace_path=artifact_paths["final_trace"],
        )
        if common_validation.get("status") != "PASS":
            errors.extend(
                f"common route process proof: {error}"
                for error in common_validation.get("errors", [])
            )
        common_validation_path = artifact_paths.get("common_process_validation")
        if common_validation_path is not None:
            try:
                recorded_common_validation = _load_json(common_validation_path)
            except ContractValidationError as exc:
                errors.extend(exc.decision["errors"])
                recorded_common_validation = {}
            if recorded_common_validation != common_validation:
                errors.append(
                    "recorded common route process validation is stale or mismatched"
                )

    pre_ready: dict[str, Any] = {}
    if currentness_path is not None:
        try:
            pre_ready = _load_json(currentness_path)
        except ContractValidationError as exc:
            errors.extend(exc.decision["errors"])
    currentness_entry = acceptance.get("pre_ready_currentness")
    if isinstance(currentness_entry, dict):
        for field in ("status", "final_equality_result"):
            if currentness_entry.get(field) != pre_ready.get(field):
                errors.append(f"pre-ready currentness {field} binding mismatch")
    if pre_ready.get("schema") != "pr-currentness-validation-v1":
        errors.append("pre-ready currentness schema is invalid")
    errors.extend(_validate_pr_currentness_result("pre-ready currentness", pre_ready))
    if pre_ready.get("status") != "READY" or pre_ready.get("final_equality_result") != "PASS":
        errors.append("pre-ready currentness must be READY/PASS")
    if pre_ready.get("expected_draft") is not True:
        errors.append("pre-ready currentness must require draft state")
    if pre_ready.get("reviewed") != reviewed or pre_ready.get("immediate") != reviewed:
        errors.append("pre-ready currentness provider identity mismatch")

    try:
        fresh_identity = fresh_currentness_path.resolve(strict=True)
        fresh_currentness = _load_json(fresh_identity)
        fresh_currentness_sha256 = _sha256_file(fresh_identity)
    except (OSError, ContractValidationError) as exc:
        detail = exc.decision["errors"] if isinstance(exc, ContractValidationError) else [str(exc)]
        errors.extend(detail)
        fresh_currentness = {}
        fresh_currentness_sha256 = None
        fresh_identity = fresh_currentness_path.resolve(strict=False)
    if fresh_identity == acceptance_identity or fresh_identity in artifact_paths.values():
        errors.append("fresh currentness must be a distinct post-acceptance artifact")
    if fresh_currentness.get("schema") != "pr-currentness-validation-v1":
        errors.append("fresh currentness schema is invalid")
    errors.extend(_validate_pr_currentness_result("fresh currentness", fresh_currentness))
    if (
        fresh_currentness.get("status") != "READY"
        or fresh_currentness.get("final_equality_result") != "PASS"
    ):
        errors.append("fresh currentness must be READY/PASS")
    if fresh_currentness.get("expected_draft") is not False:
        errors.append("fresh currentness must require non-draft state")
    if fresh_currentness.get("reviewed") != reviewed:
        errors.append("fresh currentness reviewed identity mismatch")
    fresh_immediate = fresh_currentness.get("immediate")
    if not isinstance(fresh_immediate, dict):
        errors.append("fresh currentness immediate provider identity is invalid")
    else:
        for field in _PROVIDER_FIELDS:
            expected = False if field == "is_draft" else reviewed.get(field)
            if fresh_immediate.get(field) != expected:
                errors.append(f"fresh currentness immediate identity mismatch: {field}")

    return {
        "schema": "feature-route-artifact-lineage-validation-v1",
        "status": "MERGE_AUTHORIZED" if not errors else "INVALID",
        "acceptance_path": str(acceptance_identity),
        "acceptance_sha256": acceptance_sha256,
        "fresh_currentness_path": str(fresh_identity),
        "fresh_currentness_sha256": fresh_currentness_sha256,
        "artifact_sha256": artifact_hashes,
        "errors": errors,
    }


def _validate_short_branch(branch: Any, label: str) -> list[str]:
    if not _nonblank(branch):
        return [f"{label} must be a non-blank exact short branch name"]
    remote_names = {"origin", "upstream"}
    remotes = subprocess.run(
        ["git", "remote"], check=False, capture_output=True, text=True
    )
    if remotes.returncode == 0:
        remote_names.update(remotes.stdout.splitlines())
    if branch.startswith(("refs/", "remotes/")) or branch.split("/", 1)[0] in remote_names:
        return [f"{label} must not be a full or remote-tracking ref"]
    completed = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or completed.stdout != f"{branch}\n":
        return [f"{label} fails git check-ref-format --branch exact-output validation"]
    return []


def _validate_protected_branches(
    value: Any,
    trunk_branch: Any,
    integration_branch: Any,
    label: str,
) -> tuple[list[str], list[str]]:
    protected, errors = _validate_string_list(value, label, allow_empty=False)
    for index, protected_branch in enumerate(protected):
        errors.extend(
            _validate_short_branch(protected_branch, f"{label}[{index}]")
        )
    for required, required_label in (
        (trunk_branch, "trunk branch"),
        (integration_branch, "integration branch"),
    ):
        if required not in protected:
            errors.append(f"{label} must include the explicit {required_label}")
    canonical_prefix: list[str] = []
    for required in (trunk_branch, integration_branch):
        if isinstance(required, str) and required not in canonical_prefix:
            canonical_prefix.append(required)
    canonical = canonical_prefix + sorted(
        branch for branch in protected if branch not in canonical_prefix
    )
    if protected != canonical:
        errors.append(
            f"{label} must use canonical trunk/integration/lexical order"
        )
    return protected, errors


def validate_refactoring_dispatch(plan: dict[str, Any]) -> dict[str, Any]:
    """Require one refactoring WU to project exactly one ticket PR child."""

    errors: list[str] = []
    required = {
        "schema",
        "ticket_pr_cardinality",
        "branch_name",
        "trunk_branch_name",
        "integration_branch_name",
        "protected_branches",
        "worktree_path",
        "planning_dir",
        "scratch_dir",
        "children",
        "feature_routed",
    }
    optional = {"local_coverage_command"}
    if not required <= set(plan) or set(plan) - required - optional:
        errors.append(
            "dispatch plan fields must equal the required set plus optional local_coverage_command: "
            + ",".join(sorted(required))
        )
    if plan.get("schema") != "refactoring-dispatch-plan-v1":
        errors.append("schema must equal refactoring-dispatch-plan-v1")
    if plan.get("ticket_pr_cardinality") != "exactly-one":
        errors.append("ticket_pr_cardinality must equal exactly-one")
    feature_routed = plan.get("feature_routed")
    if not isinstance(feature_routed, bool):
        errors.append("feature_routed must be a boolean")
    command_supplied = "local_coverage_command" in plan
    local_coverage_command = plan.get("local_coverage_command")
    if feature_routed is True and not command_supplied:
        errors.append("feature-routed dispatch plan must supply local_coverage_command")
    if command_supplied and (
        not isinstance(local_coverage_command, str) or not local_coverage_command.strip()
    ):
        errors.append("local_coverage_command must be a non-blank string")

    branch = plan.get("branch_name")
    trunk = plan.get("trunk_branch_name")
    integration = plan.get("integration_branch_name")
    errors.extend(_validate_short_branch(branch, "branch_name"))
    errors.extend(_validate_short_branch(trunk, "trunk_branch_name"))
    errors.extend(_validate_short_branch(integration, "integration_branch_name"))
    protected, protected_errors = _validate_protected_branches(
        plan.get("protected_branches"),
        trunk,
        integration,
        "protected_branches",
    )
    errors.extend(protected_errors)
    if branch in protected:
        errors.append("branch_name must not be protected")

    top_paths: dict[str, str] = {}
    for field in ("worktree_path", "planning_dir", "scratch_dir"):
        canonical, path_errors = _canonical_absolute_path(plan.get(field), field)
        errors.extend(path_errors)
        if canonical is not None:
            top_paths[field] = canonical
    if len(set(top_paths.values())) != len(top_paths):
        errors.append("worktree_path, planning_dir, and scratch_dir must be distinct")

    children = plan.get("children")
    if not isinstance(children, list) or len(children) != 1:
        errors.append("children must contain exactly one implementation child")
    else:
        child = children[0]
        child_required = {
            "branch_name",
            "worktree_path",
            "planning_dir",
            "scratch_dir",
            "ticket_pr_cardinality",
        }
        expected_child_fields = child_required | (
            {"local_coverage_command"} if command_supplied else set()
        )
        if not isinstance(child, dict) or set(child) != expected_child_fields:
            errors.append(
                "implementation child fields must exactly equal: "
                + ",".join(sorted(expected_child_fields))
            )
        else:
            if child["ticket_pr_cardinality"] != "exactly-one":
                errors.append("child ticket_pr_cardinality must equal exactly-one")
            for field in ("branch_name", "worktree_path", "planning_dir", "scratch_dir"):
                if child[field] != plan.get(field):
                    errors.append(f"child {field} must equal the route projection")
            if command_supplied and child["local_coverage_command"] != local_coverage_command:
                errors.append(
                    "child local_coverage_command must equal the route projection"
                )

    accepted = not errors
    return {
        "schema": "refactoring-dispatch-validation-v1",
        "status": "VALID" if accepted else "INVALID",
        "ticket_pr_cardinality": "exactly-one" if accepted else None,
        "branch_name": branch,
        "local_coverage_command_sha256": (
            hashlib.sha256(local_coverage_command.encode("utf-8")).hexdigest()
            if isinstance(local_coverage_command, str) and local_coverage_command.strip()
            else None
        ),
        "errors": errors,
    }


def require_refactoring_dispatch(plan: dict[str, Any]) -> dict[str, Any]:
    decision = validate_refactoring_dispatch(plan)
    if decision["status"] != "VALID":
        raise ContractValidationError(decision)
    return decision


def _ticket_slug(ticket_id: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", ticket_id.lower()).strip("-")
    return slug


def _route_attempt_names(ticket_id: str, attempt_number: int) -> tuple[str, str]:
    slug = _ticket_slug(ticket_id)
    return slug, f"{slug}-attempt-{attempt_number:04d}"


def validate_route_attempt_transition(
    route_manifest: dict[str, Any], route_index: dict[str, Any]
) -> dict[str, Any]:
    """Validate serialized, immutable route-attempt lineage for one feature."""

    errors: list[str] = []
    if route_manifest.get("schema") != "feature-route-manifest-v2":
        errors.append("route manifest schema must equal feature-route-manifest-v2")
    coverage_command_sha256 = route_manifest.get("local_coverage_command_sha256")
    if not isinstance(coverage_command_sha256, str) or not _SHA256.fullmatch(
        coverage_command_sha256
    ):
        errors.append(
            "route manifest local_coverage_command_sha256 must be a lowercase SHA-256"
        )
    records = route_manifest.get("records")
    if not isinstance(records, list) or not records:
        errors.append("route manifest records must be a non-empty object list")
        records = []
    routes: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not _nonblank(record.get("ticket_id")):
            errors.append(f"route manifest records[{index}] must contain ticket_id")
            continue
        ticket_id = record["ticket_id"]
        if ticket_id in routes:
            errors.append("route manifest ticket ids must be unique")
        routes[ticket_id] = record

    required_index_fields = {
        "schema",
        "state",
        "feature_branch",
        "initial_feature_sha",
        "current_feature_sha",
        "artifact_roots",
        "attempts",
        "accepted_attempts",
    }
    if set(route_index) != required_index_fields:
        errors.append(
            "route attempt index fields must exactly equal: "
            + ",".join(sorted(required_index_fields))
        )
    if route_index.get("schema") != "feature-route-attempt-index-v1":
        errors.append("route attempt index schema must equal feature-route-attempt-index-v1")
    if route_index.get("state") not in {"IN_PROGRESS", "COMPLETE"}:
        errors.append("route attempt index state must equal IN_PROGRESS or COMPLETE")
    errors.extend(_validate_short_branch(route_index.get("feature_branch"), "feature_branch"))
    errors.extend(
        _validate_short_branch(
            route_manifest.get("feature_branch"), "route manifest feature_branch"
        )
    )
    if route_index.get("feature_branch") != route_manifest.get("feature_branch"):
        errors.append("route attempt index feature_branch must equal route manifest feature_branch")
    for field in ("initial_feature_sha", "current_feature_sha"):
        if not isinstance(route_index.get(field), str) or not _FULL_OID.fullmatch(
            route_index[field]
        ):
            errors.append(f"{field} must be a full lowercase Git OID")

    expected_roots = {_ATTEMPT_PROOF_ROOT_FIELD}
    roots = route_index.get("artifact_roots")
    canonical_roots: dict[str, str] = {}
    if not isinstance(roots, dict) or set(roots) != expected_roots:
        errors.append(
            "artifact_roots fields must exactly equal: "
            + ",".join(sorted(expected_roots))
        )
    else:
        for field, value in roots.items():
            canonical, path_errors = _canonical_absolute_path(
                value, f"artifact_roots.{field}"
            )
            errors.extend(path_errors)
            if canonical is not None:
                canonical_roots[field] = canonical
        if len(set(canonical_roots.values())) != len(canonical_roots):
            errors.append("artifact_roots must be pairwise canonically distinct")

    attempts = route_index.get("attempts")
    if not isinstance(attempts, list):
        errors.append("attempts must be a list")
        attempts = []
    accepted_rows = route_index.get("accepted_attempts")
    if not isinstance(accepted_rows, list):
        errors.append("accepted_attempts must be a list")
        accepted_rows = []
    declared_accepted: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(accepted_rows):
        if not isinstance(row, dict):
            errors.append(f"accepted_attempts[{index}] fields are invalid")
            continue
        ticket_id = row.get("ticket_id")
        if not _nonblank(ticket_id) or ticket_id in declared_accepted:
            errors.append("accepted_attempts ticket ids must be non-blank and unique")
            continue
        assert isinstance(ticket_id, str)
        if set(row) != _ACCEPTED_ATTEMPT_BASE_FIELDS:
            errors.append(f"accepted_attempts[{index}] fields are invalid")
        accepted_number = row.get("attempt_number")
        if not isinstance(accepted_number, int) or accepted_number <= 0:
            errors.append(f"accepted_attempts[{index}].attempt_number must be positive")
            accepted_number = 0
        if not isinstance(row.get("merge_sha"), str) or not _FULL_OID.fullmatch(
            row["merge_sha"]
        ):
            errors.append(f"accepted_attempts[{index}].merge_sha must be a full Git OID")
        if row.get("reachable_from_current_feature") is not True:
            errors.append(
                f"accepted_attempts[{index}] must be reachable from current feature"
            )
        declared_accepted[ticket_id] = row

    next_number: dict[str, int] = {ticket_id: 1 for ticket_id in routes}
    computed_accepted: dict[str, dict[str, Any]] = {}
    all_paths: dict[str, str] = {}
    current_feature_sha = route_index.get("initial_feature_sha")
    stale_replay_ticket: str | None = None
    non_replayable_blocked = False
    for index, attempt in enumerate(attempts):
        label = f"attempts[{index}]"
        if non_replayable_blocked:
            errors.append(f"{label} must not follow a non-replayable blocked attempt")
        if not isinstance(attempt, dict) or set(attempt) != _ATTEMPT_FIELDS:
            errors.append(
                f"{label} fields must exactly equal: " + ",".join(sorted(_ATTEMPT_FIELDS))
            )
            continue
        ticket_id = attempt.get("ticket_id")
        number = attempt.get("attempt_number")
        if ticket_id not in routes:
            errors.append(f"{label}.ticket_id is not in the route manifest")
            continue
        if not isinstance(number, int) or number <= 0:
            errors.append(f"{label}.attempt_number must be a positive integer")
            continue
        if number != next_number[ticket_id]:
            errors.append(f"{label} attempt numbers must be contiguous from one")
        next_number[ticket_id] = number + 1
        if stale_replay_ticket is not None and ticket_id != stale_replay_ticket:
            errors.append(
                f"{label} must replay stale ticket {stale_replay_ticket} before another route"
            )
        eligible = [
            route_id
            for route_id, route in routes.items()
            if route_id not in computed_accepted
            and isinstance(route.get("depends_on"), list)
            and set(route["depends_on"]) <= set(computed_accepted)
        ]
        if not eligible or ticket_id != eligible[0]:
            errors.append(
                f"{label}.ticket_id must be the next deterministic eligible route"
            )
        if attempt.get("owning_route") != routes[ticket_id].get("owning_route"):
            errors.append(f"{label}.owning_route must equal the route manifest")
        if attempt.get("dispatch_base_sha") != current_feature_sha:
            errors.append(f"{label}.dispatch_base_sha must equal the serialized feature head")
        for field in (
            "dispatch_base_sha",
            "reviewed_base_sha",
            "reviewed_head_sha",
            "pre_merge_feature_sha",
            "pre_merge_head_sha",
        ):
            if not isinstance(attempt.get(field), str) or not _FULL_OID.fullmatch(
                attempt[field]
            ):
                errors.append(f"{label}.{field} must be a full lowercase Git OID")

        expected_dependencies = routes[ticket_id].get("depends_on")
        if not isinstance(expected_dependencies, list):
            errors.append(f"route manifest dependencies for {ticket_id} must be a list")
            expected_dependencies = []
        proofs = attempt.get("dependency_proofs")
        proof_ids: list[str] = []
        if not isinstance(proofs, list):
            errors.append(f"{label}.dependency_proofs must be a list")
            proofs = []
        for proof_index, proof in enumerate(proofs):
            required = {
                "ticket_id",
                "accepted_attempt_number",
                "merge_sha",
                "reachable_from_dispatch_base",
            }
            if not isinstance(proof, dict) or set(proof) != required:
                errors.append(f"{label}.dependency_proofs[{proof_index}] fields are invalid")
                continue
            dependency_id = proof.get("ticket_id")
            if not isinstance(dependency_id, str):
                errors.append(
                    f"{label}.dependency_proofs[{proof_index}].ticket_id is invalid"
                )
                continue
            proof_ids.append(dependency_id)
            accepted = computed_accepted.get(dependency_id)
            if accepted is None:
                errors.append(
                    f"{label} dependency {dependency_id} has no prior accepted attempt"
                )
                continue
            if proof.get("accepted_attempt_number") != accepted["attempt_number"]:
                errors.append(f"{label} dependency {dependency_id} attempt selection is stale")
            if proof.get("merge_sha") != accepted["merge_sha"]:
                errors.append(f"{label} dependency {dependency_id} merge identity is stale")
            if proof.get("reachable_from_dispatch_base") is not True:
                errors.append(f"{label} dependency {dependency_id} must be reachable")
        if proof_ids != expected_dependencies:
            errors.append(f"{label} dependency proofs must exactly match manifest order")

        slug, stem = _route_attempt_names(ticket_id, number)
        if not slug or slug in {".", ".."} or ".." in slug:
            errors.append(f"{label}.ticket_id has an unsafe derived slug")
        canonical, path_errors = _canonical_absolute_path(
            attempt.get("proof_envelope_path"), f"{label}.proof_envelope_path"
        )
        errors.extend(path_errors)
        proof_validation: dict[str, Any] = {}
        if canonical is not None:
            path = Path(canonical)
            proof_root = canonical_roots.get(_ATTEMPT_PROOF_ROOT_FIELD)
            if proof_root is not None and (
                path.parent != Path(proof_root)
                or path.name != f"{stem}{_ATTEMPT_PROOF_SUFFIX}"
            ):
                errors.append(
                    f"{label}.proof_envelope_path must be the exact direct proof-envelope child"
                )
            if canonical in all_paths:
                errors.append(
                    f"{label}.proof_envelope_path canonically aliases {all_paths[canonical]}"
                )
            all_paths[canonical] = f"{label}.proof_envelope_path"
            recorded_hash = attempt.get("proof_envelope_sha256")
            if not isinstance(recorded_hash, str) or not _SHA256.fullmatch(recorded_hash):
                errors.append(f"{label}.proof_envelope_sha256 must be a lowercase SHA-256")
            try:
                if _sha256_file(path) != recorded_hash:
                    errors.append(f"{label} proof envelope hash mismatch")
            except OSError as exc:
                errors.append(f"{label} proof envelope is unreadable: {exc}")
            proof_validation = validate_route_attempt_proof(path)
            if proof_validation.get("status") != "PASS":
                errors.extend(
                    f"{label} route attempt proof: {error}"
                    for error in proof_validation.get("errors", [])
                )
            for field in ("ticket_id", "attempt_number", "owning_route"):
                if proof_validation.get(field) != attempt.get(field):
                    errors.append(f"{label} route attempt proof {field} mismatch")
            if proof_validation.get("feature_branch") != route_index.get("feature_branch"):
                errors.append(f"{label} route attempt proof feature_branch mismatch")
            if proof_validation.get("local_coverage_command_sha256") != coverage_command_sha256:
                errors.append(
                    f"{label} route attempt proof local coverage command mismatch"
                )
            common_validation = proof_validation.get("common_validation")
            if not isinstance(common_validation, dict) or common_validation.get(
                "feature_branch"
            ) != route_index.get("feature_branch"):
                errors.append(f"{label} common route validation feature_branch mismatch")
            if not isinstance(common_validation, dict) or common_validation.get(
                "local_coverage_command_sha256"
            ) != coverage_command_sha256:
                errors.append(
                    f"{label} common route validation local coverage command mismatch"
                )
            outcome = proof_validation.get("route_specific_evidence")
            if not isinstance(outcome, dict):
                outcome = {}
            if outcome.get("feature_branch") != route_index.get("feature_branch"):
                errors.append(f"{label} route-specific evidence feature_branch mismatch")
            for field in (
                "state",
                "dispatch_base_sha",
                "reviewed_base_sha",
                "reviewed_head_sha",
                "pre_merge_feature_sha",
                "pre_merge_head_sha",
                "merge_sha",
                "resulting_feature_sha",
            ):
                if outcome.get(field) != attempt.get(field):
                    errors.append(f"{label} route-specific evidence {field} mismatch")
            if attempt.get("owning_route") == "refactoring" and attempt.get(
                "state"
            ) == "VERIFIED_MERGED":
                common = proof_validation.get("common_validation")
                child_ref = common.get("artifacts", {}).get("child_result") if isinstance(common, dict) else None
                if isinstance(child_ref, dict) and isinstance(child_ref.get("path"), str):
                    try:
                        refactoring_result = _load_json(Path(child_ref["path"]))
                    except ContractValidationError as exc:
                        errors.extend(exc.decision["errors"])
                        refactoring_result = {}
                    child = refactoring_result.get("child")
                    if not isinstance(child, dict):
                        child = {}
                    for field, actual in (
                        ("dispatch_base_sha", child.get("reviewed_base_sha")),
                        ("reviewed_base_sha", child.get("reviewed_base_sha")),
                        ("reviewed_head_sha", child.get("declared_head_sha")),
                        ("pre_merge_feature_sha", child.get("pre_merge_base_sha")),
                        ("pre_merge_head_sha", child.get("expected_head_guard_sha")),
                        ("merge_sha", child.get("merge_sha")),
                        ("resulting_feature_sha", refactoring_result.get("final_integration_sha")),
                    ):
                        if attempt.get(field) != actual:
                            errors.append(f"{label} refactoring accepted result {field} mismatch")

        state = attempt.get("state")
        if attempt.get("process_verdict") != "PASS":
            errors.append(f"{label}.process_verdict must equal PASS")
        if proof_validation.get("status") != "PASS":
            errors.append(f"{label} requires a current common process PASS")
        if state == "STALE_CURRENTNESS":
            if (
                attempt.get("pre_merge_feature_sha") == attempt.get("reviewed_base_sha")
                and attempt.get("pre_merge_head_sha") == attempt.get("reviewed_head_sha")
            ):
                errors.append(f"{label} stale attempt must prove base or head movement")
            if attempt.get("merge_sha") is not None or attempt.get("resulting_feature_sha") is not None:
                errors.append(f"{label} stale attempt must not record merge side effects")
            current_feature_sha = attempt.get("pre_merge_feature_sha")
            stale_replay_ticket = ticket_id
        elif state == "REPLAY_REQUIRED":
            if attempt.get("merge_sha") is not None or attempt.get("resulting_feature_sha") is not None:
                errors.append(f"{label} replay-required attempt must not record merge side effects")
            current_feature_sha = attempt.get("pre_merge_feature_sha")
            stale_replay_ticket = ticket_id
        elif state == "BLOCKED:ready-state-restoration-failed":
            if attempt.get("merge_sha") is not None or attempt.get("resulting_feature_sha") is not None:
                errors.append(f"{label} restoration blocker must not record merge side effects")
            current_feature_sha = attempt.get("pre_merge_feature_sha")
            stale_replay_ticket = None
            non_replayable_blocked = True
        elif state == "BLOCKED:merge-attempt-started":
            merge_sha = attempt.get("merge_sha")
            if merge_sha is not None and (
                not isinstance(merge_sha, str) or not _FULL_OID.fullmatch(merge_sha)
            ):
                errors.append(f"{label}.merge_sha must be null or a full lowercase Git OID")
            if attempt.get("resulting_feature_sha") is not None:
                errors.append(f"{label} merge-attempt blocker must not claim an accepted feature SHA")
            current_feature_sha = attempt.get("pre_merge_feature_sha")
            stale_replay_ticket = None
            non_replayable_blocked = True
        elif state == "VERIFIED_MERGED":
            if ticket_id in computed_accepted:
                errors.append(f"{label} ticket already has an accepted attempt")
            if not (
                attempt.get("dispatch_base_sha")
                == attempt.get("reviewed_base_sha")
                == attempt.get("pre_merge_feature_sha")
            ):
                errors.append(f"{label} accepted attempt base identities must be equal")
            if attempt.get("pre_merge_head_sha") != attempt.get("reviewed_head_sha"):
                errors.append(f"{label} accepted attempt head identities must be equal")
            merge_sha = attempt.get("merge_sha")
            if not isinstance(merge_sha, str) or not _FULL_OID.fullmatch(merge_sha):
                errors.append(f"{label}.merge_sha must be a full lowercase Git OID")
            if attempt.get("resulting_feature_sha") != merge_sha:
                errors.append(f"{label}.resulting_feature_sha must equal merge_sha")
            computed_accepted[ticket_id] = {
                "attempt_number": number,
                "merge_sha": merge_sha,
            }
            current_feature_sha = attempt.get("resulting_feature_sha")
            stale_replay_ticket = None
        else:
            errors.append(
                f"{label}.state must equal STALE_CURRENTNESS, REPLAY_REQUIRED, "
                "BLOCKED:ready-state-restoration-failed, BLOCKED:merge-attempt-started, "
                "or VERIFIED_MERGED"
            )

    if route_index.get("current_feature_sha") != current_feature_sha:
        errors.append("current_feature_sha must equal the serialized attempt transition head")
    if set(declared_accepted) != set(computed_accepted):
        errors.append("accepted_attempts must select exactly the computed accepted ticket set")
    for ticket_id, accepted in computed_accepted.items():
        declared = declared_accepted.get(ticket_id, {})
        if declared.get("attempt_number") != accepted["attempt_number"]:
            errors.append(f"accepted_attempts selection mismatch for {ticket_id}")
        if declared.get("merge_sha") != accepted["merge_sha"]:
            errors.append(f"accepted_attempts merge mismatch for {ticket_id}")
    if route_index.get("state") == "COMPLETE" and set(computed_accepted) != set(routes):
        errors.append("COMPLETE route index requires one accepted attempt per manifest ticket")

    accepted = not errors
    return {
        "schema": "feature-route-attempt-transition-validation-v1",
        "status": "VALID" if accepted else "INVALID",
        "route_index_state": route_index.get("state"),
        "accepted_attempts": {
            ticket_id: row["attempt_number"] for ticket_id, row in computed_accepted.items()
        },
        "current_feature_sha": current_feature_sha,
        "errors": errors,
    }


def compute_plan_hash(request: dict[str, Any]) -> str:
    hashable = {key: value for key, value in request.items() if key != "plan_hash"}
    return hashlib.sha256(_canonical_json(hashable)).hexdigest()


def _validate_package_plan(
    request: dict[str, Any], errors: list[str]
) -> list[str]:
    selected, selected_errors = _validate_string_list(
        request.get("selected_package_ids"),
        "selected_package_ids",
        allow_empty=False,
    )
    errors.extend(selected_errors)
    package_plan = request.get("package_plan")
    if not isinstance(package_plan, list) or not package_plan:
        errors.append("package_plan must be a non-empty object list")
        return selected

    trunk_branch = request.get("trunk_branch")
    integration_branch = request.get("integration_branch_ref")
    protected_branches, protected_errors = _validate_protected_branches(
        request.get("protected_branches"),
        trunk_branch,
        integration_branch,
        "request protected_branches",
    )
    errors.extend(protected_errors)
    planned: list[str] = []
    dependencies: dict[str, list[str]] = {}
    branches: dict[str, str] = {}
    package_paths: dict[str, str] = {}
    for index, package in enumerate(package_plan):
        label = f"package_plan[{index}]"
        if not isinstance(package, dict):
            errors.append(f"{label} must be an object")
            continue
        if set(package) != _PACKAGE_FIELDS:
            errors.append(
                f"{label} fields must exactly equal: "
                + ",".join(sorted(_PACKAGE_FIELDS))
            )
            continue
        package_id = package.get("package_id")
        if not _nonblank(package_id):
            errors.append(f"{label}.package_id must be a non-blank trimmed string")
            continue
        assert isinstance(package_id, str)
        planned.append(package_id)

        for field in ("target_list", "slice_bounds"):
            if not _nonblank(package.get(field)):
                errors.append(f"{label}.{field} must be a non-blank trimmed string")
        if package.get("refactor_intent") != "no-intended-behavior-change":
            errors.append(
                f"{label}.refactor_intent must equal no-intended-behavior-change"
            )
        for field in ("milestone_evidence_ref", "degradation_evidence_ref"):
            _canonical, path_errors = _canonical_absolute_path(
                package.get(field), f"{label}.{field}"
            )
            errors.extend(path_errors)

        gates, gate_errors = _validate_string_list(
            package.get("inherited_gate_obligations"),
            f"{label}.inherited_gate_obligations",
            allow_empty=False,
        )
        errors.extend(gate_errors)
        if set(gates) != _REQUIRED_PACKAGE_GATES or len(gates) != len(
            _REQUIRED_PACKAGE_GATES
        ):
            errors.append(
                f"{label}.inherited_gate_obligations must equal the exact required gate set"
            )
        package_dependencies, dependency_errors = _validate_string_list(
            package.get("dependencies"),
            f"{label}.dependencies",
            allow_empty=True,
        )
        errors.extend(dependency_errors)
        dependencies[package_id] = package_dependencies
        _criteria, criteria_errors = _validate_string_list(
            package.get("acceptance_criteria"),
            f"{label}.acceptance_criteria",
            allow_empty=False,
        )
        errors.extend(criteria_errors)

        branch = package.get("branch_name")
        errors.extend(_validate_short_branch(branch, f"{label}.branch_name"))
        if branch in protected_branches:
            errors.append(f"{label}.branch_name must not be protected")
        if isinstance(branch, str):
            if branch in branches:
                errors.append(
                    f"{label}.branch_name duplicates {branches[branch]}"
                )
            branches[branch] = label

        canonical_row_paths: dict[str, str] = {}
        for field in (
            "worktree_path",
            "planning_dir",
            "scratch_dir",
            "route_result_path",
        ):
            canonical, path_errors = _canonical_absolute_path(
                package.get(field), f"{label}.{field}"
            )
            errors.extend(path_errors)
            if canonical is not None:
                canonical_row_paths[field] = canonical
                if canonical in package_paths:
                    errors.append(
                        f"{label}.{field} canonically aliases {package_paths[canonical]}"
                    )
                package_paths[canonical] = f"{label}.{field}"
        if len(set(canonical_row_paths.values())) != len(canonical_row_paths):
            errors.append(f"{label} roots and route result must be canonically distinct")
        planning = canonical_row_paths.get("planning_dir")
        result = canonical_row_paths.get("route_result_path")
        if planning is not None and result is not None:
            result_path = Path(result)
            if (
                result_path.parent != Path(planning)
                or result_path.name != "refactoring-route-result.json"
            ):
                errors.append(
                    f"{label}.route_result_path must be the exact direct refactoring-route-result.json child of planning_dir"
                )

    if len(planned) != len(set(planned)):
        errors.append("package_plan package ids must be unique")
    if planned != selected:
        errors.append(
            "package_plan package ids must exactly equal selected_package_ids in order"
        )

    planned_set = set(planned)
    for package_id, package_dependencies in dependencies.items():
        for dependency in package_dependencies:
            if dependency not in planned_set:
                errors.append(
                    f"package {package_id} dependency {dependency} is not package-local"
                )
            if dependency == package_id:
                errors.append(f"package {package_id} must not depend on itself")
    remaining = set(planned)
    completed: set[str] = set()
    while remaining:
        ready = [
            package_id
            for package_id in planned
            if package_id in remaining
            and set(dependencies.get(package_id, [])) <= completed
        ]
        if not ready:
            if not any("is not package-local" in error for error in errors):
                errors.append("package_plan dependencies must be acyclic")
            break
        completed.update(ready)
        remaining.difference_update(ready)
    return selected


def validate_package_execution(
    request: dict[str, Any],
    ticket_map: dict[str, Any],
    current_identity: dict[str, Any],
) -> dict[str, Any]:
    """Validate an immutable scope request before commit-history child dispatch."""

    errors: list[str] = []
    request_required = {
        "schema",
        "ticket_system",
        *_IDENTITY_FIELDS,
        "selected_package_ids",
        "package_plan",
        "source_hashes",
        "plan_hash",
    }
    if set(request) != request_required:
        errors.append(
            "package source request fields must exactly equal: "
            + ",".join(sorted(request_required))
        )
    if request.get("schema") != "refactoring-commit-history-package-source-request-v1":
        errors.append(
            "request schema must equal refactoring-commit-history-package-source-request-v1"
        )
    if request.get("ticket_system") not in {"jira", "linear"}:
        errors.append("request ticket_system must equal jira or linear")
    for field in ("target_identity_sha256",):
        if not isinstance(request.get(field), str) or not _SHA256.fullmatch(
            request[field]
        ):
            errors.append(f"request {field} must be a SHA-256")
    for field in ("history_base_sha", "history_frontier_sha", "integration_branch_sha"):
        if not isinstance(request.get(field), str) or not _FULL_OID.fullmatch(
            request[field]
        ):
            errors.append(f"request {field} must be a full Git OID")
    for field in (
        "target",
        "history_base_ref",
        "history_frontier_ref",
    ):
        if not _nonblank(request.get(field)):
            errors.append(f"request {field} must be non-blank")
    errors.extend(_validate_short_branch(request.get("trunk_branch"), "request trunk_branch"))
    errors.extend(
        _validate_short_branch(
            request.get("integration_branch_ref"), "request integration_branch_ref"
        )
    )
    source_hashes = request.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        errors.append("source_hashes must be a non-empty object")
    elif any(
        not _nonblank(key)
        or not isinstance(value, str)
        or not _SHA256.fullmatch(value)
        for key, value in source_hashes.items()
    ):
        errors.append("source_hashes keys must be non-blank and values must be SHA-256")

    selected = _validate_package_plan(request, errors)
    expected_hash = compute_plan_hash(request)
    if request.get("plan_hash") != expected_hash:
        errors.append("request plan_hash does not match canonical request content")

    current_required = {"schema", *_IDENTITY_FIELDS}
    if set(current_identity) != current_required:
        errors.append(
            "current identity fields must exactly equal: "
            + ",".join(sorted(current_required))
        )
    if (
        current_identity.get("schema")
        != "refactoring-commit-history-current-identity-v1"
    ):
        errors.append(
            "current identity schema must equal refactoring-commit-history-current-identity-v1"
        )
    for field in _IDENTITY_FIELDS:
        if current_identity.get(field) != request.get(field):
            errors.append(f"current identity mismatch: {field}")

    map_required = {"schema", "plan_hash", "ticket_system", "packages"}
    if set(ticket_map) != map_required:
        errors.append(
            "ticket source map fields must exactly equal: "
            + ",".join(sorted(map_required))
        )
    if ticket_map.get("schema") != "refactoring-commit-history-package-ticket-source-v1":
        errors.append(
            "ticket source map schema must equal refactoring-commit-history-package-ticket-source-v1"
        )
    if ticket_map.get("plan_hash") != request.get("plan_hash"):
        errors.append("ticket source map plan_hash must equal request plan_hash")
    if ticket_map.get("ticket_system") != request.get("ticket_system"):
        errors.append("ticket source map ticket_system must equal request ticket_system")

    packages = ticket_map.get("packages")
    mapped_ids: list[str] = []
    issue_ids: list[str] = []
    expected_key = (
        "jira_issue_key" if request.get("ticket_system") == "jira" else "linear_issue_key"
    )
    if not isinstance(packages, list) or not packages:
        errors.append("ticket source map packages must be a non-empty object list")
    else:
        for index, package in enumerate(packages):
            if not isinstance(package, dict) or set(package) != {
                "package_id",
                "ticket_source",
            }:
                errors.append(
                    f"ticket source map packages[{index}] must contain only package_id and ticket_source"
                )
                continue
            package_id = package["package_id"]
            source = package["ticket_source"]
            if not _nonblank(package_id):
                errors.append(f"ticket source map packages[{index}].package_id is invalid")
                continue
            mapped_ids.append(package_id)
            if not isinstance(source, dict) or set(source) != {expected_key}:
                errors.append(
                    f"ticket source map packages[{index}].ticket_source must contain only {expected_key}"
                )
                continue
            issue_id = source[expected_key]
            if not _nonblank(issue_id):
                errors.append(f"ticket source map packages[{index}] issue key is invalid")
            else:
                issue_ids.append(issue_id)
    if len(mapped_ids) != len(set(mapped_ids)):
        errors.append("ticket source map package ids must be unique")
    if set(mapped_ids) != set(selected):
        errors.append("ticket source map package set must exactly equal selected package set")
    if len(issue_ids) != len(set(issue_ids)):
        errors.append("ticket source map issue identities must be unique")

    accepted = not errors
    return {
        "schema": "refactoring-commit-history-execute-validation-v1",
        "status": "VALID" if accepted else "INVALID",
        "plan_hash": request.get("plan_hash"),
        "selected_package_ids": selected,
        "mapped_package_ids": mapped_ids,
        "identity_equal": not any(
            error.startswith("current identity mismatch:") for error in errors
        ),
        "package_set_equal": set(mapped_ids) == set(selected),
        "errors": errors,
    }


def require_package_execution(
    request: dict[str, Any],
    ticket_map: dict[str, Any],
    current_identity: dict[str, Any],
) -> dict[str, Any]:
    decision = validate_package_execution(request, ticket_map, current_identity)
    if decision["status"] != "VALID":
        raise ContractValidationError(decision)
    return decision


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    currentness = subparsers.add_parser("validate-pr-currentness")
    currentness.add_argument("--reviewed", type=Path, required=True)
    currentness.add_argument("--immediate", type=Path, required=True)
    currentness.add_argument("--fetched-base-sha", required=True)
    currentness.add_argument("--fetched-head-sha", required=True)
    currentness.add_argument("--context", required=True)
    currentness.add_argument("--expected-draft", choices=("true", "false"))
    currentness.add_argument("--output", type=Path, required=True)

    restoration = subparsers.add_parser("validate-ready-state-restoration")
    restoration.add_argument("--promoted", type=Path, required=True)
    restoration.add_argument("--restored", type=Path)
    restoration.add_argument("--fetched-base-sha")
    restoration.add_argument("--fetched-head-sha")
    restoration.add_argument("--owner", choices=tuple(_READY_STATE_OWNERS), required=True)
    restoration.add_argument("--undo-attempted", choices=("true", "false"), required=True)
    restoration.add_argument("--undo-exit-code", type=int)
    restoration.add_argument("--requery-succeeded", choices=("true", "false"), required=True)
    restoration.add_argument(
        "--merge-attempt-started", choices=("true", "false"), required=True
    )
    restoration.add_argument("--output", type=Path, required=True)

    lineage = subparsers.add_parser("validate-route-artifact-lineage")
    lineage.add_argument("--acceptance", type=Path, required=True)
    lineage.add_argument("--fresh-currentness", type=Path, required=True)
    lineage.add_argument("--output", type=Path, required=True)

    route_process = subparsers.add_parser("validate-route-process-proof")
    route_process.add_argument(
        "--owning-route", choices=tuple(_ROUTE_KIND_SPECS), required=True
    )
    route_process.add_argument("--feature-branch", required=True)
    route_process.add_argument("--ticket-id", required=True)
    route_process.add_argument("--attempt-number", type=int, required=True)
    route_process.add_argument("--route-evidence", type=Path, required=True)
    route_process.add_argument("--pre-audit-expected", type=Path, required=True)
    route_process.add_argument("--pre-audit-dispatch", type=Path, required=True)
    route_process.add_argument("--pre-audit-trace", type=Path, required=True)
    route_process.add_argument("--process-report", type=Path, required=True)
    route_process.add_argument("--process-report-binding", type=Path, required=True)
    route_process.add_argument("--final-expected", type=Path, required=True)
    route_process.add_argument("--final-dispatch", type=Path, required=True)
    route_process.add_argument("--final-trace", type=Path, required=True)
    route_process.add_argument("--output", type=Path, required=True)

    ticket_operation = subparsers.add_parser("validate-ticket-operation-result")
    ticket_operation.add_argument("--result", type=Path, required=True)
    ticket_operation.add_argument("--expected-context", type=Path, required=True)
    ticket_operation.add_argument("--output", type=Path, required=True)

    dispatch = subparsers.add_parser("validate-refactoring-dispatch")
    dispatch.add_argument("--plan", type=Path, required=True)
    dispatch.add_argument("--output", type=Path, required=True)

    attempts = subparsers.add_parser("validate-route-attempts")
    attempts.add_argument("--route-manifest", type=Path, required=True)
    attempts.add_argument("--route-index", type=Path, required=True)
    attempts.add_argument("--output", type=Path, required=True)

    execute = subparsers.add_parser("validate-package-execute")
    execute.add_argument("--request", type=Path, required=True)
    execute.add_argument("--ticket-map", type=Path, required=True)
    execute.add_argument("--current-identity", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)

    extraction = subparsers.add_parser("extract-provider-payload")
    extraction.add_argument("--log", type=Path, required=True)
    extraction.add_argument("--output", type=Path, required=True)
    extraction.add_argument("--metadata", type=Path)

    review_run = subparsers.add_parser("init-pr-review-run")
    review_run.add_argument("--review-root", type=Path, required=True)
    review_run.add_argument("--source-repo-root", type=Path, required=True)
    review_run.add_argument("--pr-number", type=int, required=True)
    review_run.add_argument("--base-sha", required=True)
    review_run.add_argument("--head-sha", required=True)
    review_run.add_argument("--invocation-uuid", required=True)

    cleanup = subparsers.add_parser("cleanup-pr-review-worktree")
    cleanup.add_argument("--run-manifest", type=Path, required=True)
    cleanup.add_argument("--terminal-artifact", type=Path, required=True)
    cleanup.add_argument("--output", type=Path, required=True)

    nested_proof = subparsers.add_parser("validate-test-audit-proof")
    nested_proof.add_argument("--proof", type=Path, required=True)
    nested_proof.add_argument("--output", type=Path, required=True)

    process_audit = subparsers.add_parser("validate-process-tree-audit-report")
    process_audit.add_argument("--report", type=Path, required=True)
    process_audit.add_argument("--output", type=Path, required=True)

    test_audit_result = subparsers.add_parser("validate-test-audit-result")
    test_audit_result.add_argument("--result", type=Path, required=True)
    test_audit_result.add_argument("--expected-root-uuid")
    test_audit_result.add_argument("--expected-base-sha")
    test_audit_result.add_argument("--expected-head-sha")
    test_audit_result.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "validate-pr-currentness":
            decision = validate_pr_currentness(
                _load_json(args.reviewed),
                _load_json(args.immediate),
                args.fetched_base_sha,
                args.fetched_head_sha,
                context=args.context,
                expected_draft=(
                    args.expected_draft == "true"
                    if args.expected_draft is not None
                    else None
                ),
            )
            accepted = decision["status"] == "READY"
        elif args.command == "validate-ready-state-restoration":
            decision = validate_ready_state_restoration(
                _load_json(args.promoted),
                _load_json(args.restored) if args.restored is not None else None,
                args.fetched_base_sha,
                args.fetched_head_sha,
                owner=args.owner,
                undo_attempted=args.undo_attempted == "true",
                undo_exit_code=args.undo_exit_code,
                requery_succeeded=args.requery_succeeded == "true",
                merge_attempt_started=args.merge_attempt_started == "true",
            )
            accepted = decision["status"] in {"REPLAY_REQUIRED", "RETURN_TO_PHASE_8"}
        elif args.command == "validate-route-artifact-lineage":
            decision = validate_route_artifact_lineage(
                args.acceptance, args.fresh_currentness
            )
            accepted = decision["status"] == "MERGE_AUTHORIZED"
        elif args.command == "validate-route-process-proof":
            decision = validate_route_process_proof(
                owning_route=args.owning_route,
                feature_branch=args.feature_branch,
                ticket_id=args.ticket_id,
                attempt_number=args.attempt_number,
                route_evidence_path=args.route_evidence,
                pre_audit_expected_path=args.pre_audit_expected,
                pre_audit_dispatch_path=args.pre_audit_dispatch,
                pre_audit_trace_path=args.pre_audit_trace,
                process_report_path=args.process_report,
                process_report_binding_path=args.process_report_binding,
                final_expected_path=args.final_expected,
                final_dispatch_path=args.final_dispatch,
                final_trace_path=args.final_trace,
            )
            accepted = decision["status"] == "PASS"
        elif args.command == "validate-ticket-operation-result":
            decision = validate_ticket_operation_result(
                _load_json(args.result),
                _load_json(args.expected_context),
                result_path=args.result,
                expected_context_path=args.expected_context,
            )
            accepted = decision["status"] == "VALID"
        elif args.command == "validate-refactoring-dispatch":
            decision = validate_refactoring_dispatch(_load_json(args.plan))
            accepted = decision["status"] == "VALID"
        elif args.command == "validate-route-attempts":
            decision = validate_route_attempt_transition(
                _load_json(args.route_manifest), _load_json(args.route_index)
            )
            accepted = decision["status"] == "VALID"
        elif args.command == "validate-package-execute":
            decision = validate_package_execution(
                _load_json(args.request),
                _load_json(args.ticket_map),
                _load_json(args.current_identity),
            )
            accepted = decision["status"] == "VALID"
        elif args.command == "validate-test-audit-proof":
            decision = validate_test_audit_nested_proof(
                _load_json(args.proof), proof_path=args.proof
            )
            accepted = decision["status"] == "VALID"
        elif args.command == "validate-process-tree-audit-report":
            decision = validate_process_tree_audit_report(args.report)
            accepted = decision["status"] == "VALID"
        elif args.command == "validate-test-audit-result":
            decision = validate_test_audit_result(
                _load_json(args.result),
                expected_root_uuid=args.expected_root_uuid,
                expected_base_sha=args.expected_base_sha,
                expected_head_sha=args.expected_head_sha,
            )
            accepted = decision["status"] == "VALID"
        elif args.command == "extract-provider-payload":
            decision = extract_provider_payload(args.log, args.output)
            if args.metadata is not None:
                _write_json(args.metadata, decision)
            print(args.output)
            return 0
        elif args.command == "init-pr-review-run":
            decision = initialize_pr_review_run(
                args.review_root,
                args.source_repo_root,
                args.pr_number,
                args.base_sha,
                args.head_sha,
                args.invocation_uuid,
            )
            print(Path(decision["run_root"]) / "pr-review-run.json")
            return 0
        else:
            decision = cleanup_pr_review_worktree(
                _load_json(args.run_manifest), args.terminal_artifact
            )
            _write_json(args.output, decision)
            print(args.output)
            return 0
    except ContractValidationError as exc:
        decision = exc.decision
        accepted = False

    decision_output_commands = {
        "validate-pr-currentness",
        "validate-ready-state-restoration",
        "validate-route-artifact-lineage",
        "validate-route-process-proof",
        "validate-ticket-operation-result",
        "validate-refactoring-dispatch",
        "validate-route-attempts",
        "validate-package-execute",
        "validate-test-audit-proof",
        "validate-process-tree-audit-report",
        "validate-test-audit-result",
        "cleanup-pr-review-worktree",
    }
    if args.command in decision_output_commands:
        _write_json(args.output, decision)
    if not accepted:
        print("BLOCKED:" + "; ".join(decision.get("errors", [])), file=sys.stderr)
        return 2
    if args.command in decision_output_commands:
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
