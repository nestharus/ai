from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from clients.linear import estimate_admission


ISSUE = "TEAM-72"
NOTE = "# Estimate refinement\n\nInherited: 3\nRefined: 5\nSource: research\nRationale: added scope\n"
OPERATIONS = [
    ["update-issue", ISSUE, "--estimate", "5"],
    ["create-comment", ISSUE, "--body", NOTE],
    ["upsert-comment", ISSUE, "--title", "Estimate refinement", "--body", NOTE],
]
CAPABILITIES = "outputs:\n- task: update-estimate\nside_effects: [linear-update-estimate]\n"


def _definition(
    root: Path, policy: str = "", *, inherits: Path | None = None,
    capabilities: str = CAPABILITIES,
) -> Path:
    definition = root / "agents" / "linear-operator.md"
    sidecar = root / "contracts" / "operators" / "linear-operator.yaml"
    definition.parent.mkdir(parents=True, exist_ok=True)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    inheritance = f"inherits: {inherits}\nbase_procedure: {inherits}\n" if inherits else ""
    contract = f"schema: operator-contract-v1\n{inheritance}{policy}{capabilities}"
    definition.write_text(f"# Linear wrapper\n\n## Contract\n\n```yaml\n{contract}```\n")
    sidecar.write_text(f"source: agents/linear-operator.md\n{contract}")
    return definition


@pytest.fixture
def requests(monkeypatch: pytest.MonkeyPatch, record_property: Any):
    calls = []

    def transport(request: urllib.request.Request, timeout: int) -> io.BytesIO:
        payload = json.loads(request.data)
        calls.append(payload)
        assert request.full_url == "https://api.linear.app/graphql"
        assert request.get_header("Authorization") == "public-estimate-fixture-key"
        assert timeout == 30
        query = payload["query"]
        if "mutation IssueUpdate(" in query:
            response = {"issueUpdate": {"success": True, "issue": {"id": "issue-uuid"}}}
        elif "mutation CommentCreate(" in query:
            response = {"commentCreate": {"success": True, "comment": {
                "id": "comment-uuid", "body": NOTE, "issue": {"id": "issue-uuid"},
            }}}
        elif "query IssueComments(" in query:
            response = {"issue": {"id": "issue-uuid", "identifier": ISSUE, "comments": {
                "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}}
        else:
            pytest.fail(f"Unexpected GraphQL request: {payload}")
        return io.BytesIO(json.dumps({"data": response}).encode())

    monkeypatch.setenv("LINEAR_API_KEY", "public-estimate-fixture-key")
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    yield calls
    record_property("graphql_calls", json.dumps(calls))


def _invoke(definition, operation, capsys, record_property):
    status = 0
    try:
        estimate_admission.main(["--definition", str(definition), "--", *operation])
    except SystemExit as error:
        status = error.code
    captured = capsys.readouterr()
    record_property("guard_stdout", captured.out)
    record_property("guard_stderr", captured.err)
    return status, json.loads(captured.out)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("policy", ['"true"', "1", "null", "[true]", "{enabled: true}"])
def test_nonboolean_policy_blocks_before_any_request(
    tmp_path, operation, policy, requests, capsys, record_property,
):
    definition = _definition(tmp_path, f"estimate_mutation_enabled: {policy}\n")
    status, payload = _invoke(definition, operation, capsys, record_property)
    assert status == 1
    assert payload["error"]["code"] == "estimate-mutation-policy-invalid"
    assert requests == []


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("policy", ["true", "false", "legacy"])
def test_selected_wrapper_policy_and_inherited_capability(
    tmp_path, operation, policy, requests, capsys, record_property,
):
    base = _definition(tmp_path / "base", "estimate_mutation_enabled: false\n")
    declaration = "" if policy == "legacy" else f"estimate_mutation_enabled: {policy}\n"
    definition = _definition(tmp_path / "project", declaration, inherits=base, capabilities="")
    status, payload = _invoke(definition, operation, capsys, record_property)
    if policy == "false":
        assert status == 1
        assert payload["error"]["code"] == "estimate-mutation-policy-disabled"
        assert requests == []
        return
    assert status == 0
    assert payload["ok"] is True
    if operation[0] == "update-issue":
        assert len(requests) == 1
        assert requests[0]["variables"] == {"id": ISSUE, "input": {"estimate": 5}}
    else:
        assert len(requests) == (2 if operation[0] == "upsert-comment" else 1)
        assert requests[-1]["variables"] == {"input": {"issueId": ISSUE, "body": NOTE}}


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("defect", ["duplicate", "conflict", "source", "unreadable"])
def test_invalid_selected_sidecar_never_falls_back_to_embedded(
    tmp_path, operation, defect, requests, capsys, record_property,
):
    definition = _definition(tmp_path, "estimate_mutation_enabled: true\n")
    sidecar = tmp_path / "contracts/operators/linear-operator.yaml"
    if defect == "duplicate":
        sidecar.write_text(sidecar.read_text() + "estimate_mutation_enabled: true\n")
    elif defect == "conflict":
        sidecar.write_text(sidecar.read_text().replace("enabled: true", "enabled: 1"))
    elif defect == "source":
        other = _definition(tmp_path / "other", "estimate_mutation_enabled: true\n")
        sidecar.write_text(sidecar.read_text().replace("agents/linear-operator.md", str(other)))
    else:
        sidecar.unlink()
        sidecar.symlink_to(tmp_path / "missing-sidecar.yaml")
    status, payload = _invoke(definition, operation, capsys, record_property)
    assert status == 1
    assert payload["error"]["code"] == "estimate-mutation-policy-invalid"
    assert requests == []


@pytest.mark.parametrize("capabilities", ["", "outputs:\n- task: update-estimate\n", "side_effects: [linear-update-estimate]\n"])
def test_absent_policy_requires_both_legacy_capabilities(
    tmp_path, capabilities, requests, capsys, record_property,
):
    definition = _definition(tmp_path, capabilities=capabilities)
    status, payload = _invoke(definition, OPERATIONS[0], capsys, record_property)
    assert status == 1
    assert payload["error"]["code"] == "estimate-mutation-policy-unresolved"
    assert requests == []


def test_embedded_fallback_and_recheck_before_refinement_note(
    tmp_path, requests, capsys, record_property,
):
    definition = _definition(tmp_path, "estimate_mutation_enabled: true\n")
    sidecar = tmp_path / "contracts/operators/linear-operator.yaml"
    sidecar.unlink()
    status, payload = _invoke(definition, OPERATIONS[0], capsys, record_property)
    assert status == 0
    assert payload["ok"] is True
    assert len(requests) == 1
    definition.write_text(definition.read_text().replace("enabled: true", "enabled: false"))
    status, payload = _invoke(definition, OPERATIONS[1], capsys, record_property)
    assert status == 1
    assert payload["error"]["code"] == "estimate-mutation-policy-disabled"
    assert len(requests) == 1
    assert requests[0]["variables"] == {"id": ISSUE, "input": {"estimate": 5}}
