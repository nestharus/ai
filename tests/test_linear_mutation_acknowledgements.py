"""Mutation attempts need exact acknowledgements before the guard publishes success."""

import io
import json
from pathlib import Path
import urllib.request

import pytest

from clients.linear import estimate_admission
from clients.linear.client import LinearClient, LinearClientError


ISSUE = "TEAM-72"
TEAM = "00000000-0000-0000-0000-000000000001"
NOTE = "## Estimate refinement\r\n\r\nQuoted 'value'; café $()\nRationale: more work\n\n"
BRANCHES = ["numeric", "direct-note", "upsert-create", "upsert-update"]
SIBLINGS = ["create-issue", "set-state", "create-label"]
MISSING = object()
BAD_VALUES = [MISSING, None, False, True, 0, 1, 7, [], [True], {}, {"value": True}, "", "false"]
BAD_IDS = [MISSING, None, False, True, 7, [], {}, "", " \t\n"]


def _key(branch):
    return {
        "numeric": "issueUpdate", "direct-note": "commentCreate", "upsert-create": "commentCreate",
        "upsert-update": "commentUpdate", "create-issue": "issueCreate", "set-state": "issueUpdate",
        "create-label": "issueLabelCreate",
    }[branch]


def _response(branch):
    return {"data": {_key(branch): {
        "success": True,
        "comment": {"id": "note-existing" if branch == "upsert-update" else "note-created"},
        "issue": {"id": "issue-uuid", "state": {"name": "Done"}},
        "issueLabel": {"id": "label-created", "name": "fixture"},
    }}}


def _replace(mapping, field, value):
    if value is MISSING:
        del mapping[field]
    else:
        mapping[field] = value


@pytest.fixture
def mutation_transport(monkeypatch, record_property):
    state = {"branch": None, "response": None}
    calls = []

    def configure(branch, response):
        state.update(branch=branch, response=response)

    def transport(request, timeout):
        payload = json.loads(request.data)
        query, variables = payload["query"], payload["variables"]
        calls.append({"operation": query.strip().split("{")[0], "variables": variables})
        assert request.full_url == "https://api.linear.app/graphql"
        assert request.get_header("Authorization") == "public-mutation-fixture"
        if "query IssueComments(" in query:
            assert state["branch"] in {"upsert-create", "upsert-update"}
            assert variables == {"id": ISSUE}
            nodes = [{"id": "note-existing", "body": "## Estimate refinement\nOld body"}] if state["branch"] == "upsert-update" else []
            response = {"data": {"issue": {"id": "issue-uuid", "identifier": ISSUE, "comments": {
                "nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}}}
        else:
            assert query.lstrip().startswith("mutation")
            assert _key(state["branch"]) + "(" in query
            response = state["response"]
        return io.BytesIO(json.dumps(response).encode("utf-8"))

    monkeypatch.setenv("LINEAR_API_KEY", "public-mutation-fixture")
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    yield configure, calls
    record_property("attempted_requests", json.dumps(calls, ensure_ascii=False))


@pytest.fixture
def selected_wrapper(tmp_path):
    base = Path(__file__).resolve().parents[1] / "agents/linear-operator.md"
    definition = tmp_path / "agents/linear-operator.md"
    definition.parent.mkdir()
    definition.write_text(
        "# Admitted local wrapper\n\n## Contract\n\n```yaml\n"
        f"schema: operator-contract-v1\ninherits: {base}\nbase_procedure: {base}\n"
        "estimate_mutation_enabled: true\n```\n"
    )
    return definition


def _invoke_guard(definition, branch, capsys, record_property):
    if branch == "numeric":
        operation = ["update-issue", ISSUE, "--estimate", "5"]
    elif branch == "direct-note":
        operation = ["create-comment", ISSUE, "--body", NOTE]
    else:
        operation = ["upsert-comment", ISSUE, "--title", "Estimate refinement", "--body", NOTE]
    status = 0
    try:
        estimate_admission.main(["--definition", str(definition), "--", *operation])
    except SystemExit as error:
        status = error.code
    captured = capsys.readouterr()
    record_property("guard_stdout", captured.out)
    record_property("guard_stderr", captured.err)
    record_property("guard_exit", status)
    return status, json.loads(captured.out)


def _assert_attempt(branch, calls):
    assert len(calls) == (2 if branch.startswith("upsert") else 1)
    assert sum(call["operation"].startswith("mutation") for call in calls) == 1
    expected = {"id": ISSUE, "input": {"estimate": 5}} if branch == "numeric" else (
        {"id": "note-existing", "input": {"body": NOTE}} if branch == "upsert-update"
        else {"input": {"issueId": ISSUE, "body": NOTE}}
    )
    assert calls[-1]["variables"] == expected


@pytest.mark.parametrize("branch", BRANCHES)
@pytest.mark.parametrize("success", BAD_VALUES)
def test_guard_accepts_only_exact_true_after_attempt(selected_wrapper, mutation_transport, capsys, record_property, branch, success):
    configure, calls = mutation_transport
    response = _response(branch)
    _replace(response["data"][_key(branch)], "success", success)
    configure(branch, response)
    status, envelope = _invoke_guard(selected_wrapper, branch, capsys, record_property)
    _assert_attempt(branch, calls)
    assert status == (0 if success is True else 1)
    assert envelope["ok"] is (success is True)
    if success is not True:
        assert "data" not in envelope
        assert envelope["error"]["code"] == ("API_ERROR" if success is False else "INVALID_RESPONSE")
    elif branch != "numeric":
        assert envelope["data"]["id"] == ("note-existing" if branch == "upsert-update" else "note-created")


@pytest.mark.parametrize("branch", BRANCHES)
@pytest.mark.parametrize("level", ["data", "acknowledgement"])
@pytest.mark.parametrize("value", [MISSING, None, False, True, 7, [], [True], "", "ack"])
def test_guard_blocks_unreadable_acknowledgement_containers(selected_wrapper, mutation_transport, capsys, record_property, branch, level, value):
    configure, calls = mutation_transport
    response = _response(branch)
    parent, field = (response, "data") if level == "data" else (response["data"], _key(branch))
    _replace(parent, field, value)
    configure(branch, response)
    status, envelope = _invoke_guard(selected_wrapper, branch, capsys, record_property)
    _assert_attempt(branch, calls)
    assert status == 1 and envelope["ok"] is False
    assert envelope["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("branch", BRANCHES[1:])
@pytest.mark.parametrize("field", ["comment", "id"])
@pytest.mark.parametrize("value", BAD_IDS)
def test_note_success_requires_usable_identity(selected_wrapper, mutation_transport, capsys, record_property, branch, field, value):
    configure, calls = mutation_transport
    response = _response(branch)
    parent = response["data"][_key(branch)]
    if field == "id":
        parent = parent["comment"]
    _replace(parent, field, value)
    configure(branch, response)
    status, envelope = _invoke_guard(selected_wrapper, branch, capsys, record_property)
    _assert_attempt(branch, calls)
    assert status == 1 and envelope["ok"] is False
    assert envelope["error"]["code"] == "INVALID_RESPONSE"


def test_upsert_update_rejects_substituted_note_identity(selected_wrapper, mutation_transport, capsys, record_property):
    configure, calls = mutation_transport
    response = _response("upsert-update")
    response["data"]["commentUpdate"]["comment"]["id"] = "other-note"
    configure("upsert-update", response)
    status, envelope = _invoke_guard(selected_wrapper, "upsert-update", capsys, record_property)
    _assert_attempt("upsert-update", calls)
    assert status == 1 and envelope["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("echo", [MISSING, None, {}, [], "unused", False])
def test_exact_numeric_acknowledgement_does_not_require_echo_fields(selected_wrapper, mutation_transport, capsys, record_property, echo):
    configure, calls = mutation_transport
    response = {"data": {"issueUpdate": {"success": True, "issue": {}}}}
    _replace(response["data"]["issueUpdate"], "issue", echo)
    configure("numeric", response)
    status, envelope = _invoke_guard(selected_wrapper, "numeric", capsys, record_property)
    _assert_attempt("numeric", calls)
    assert status == 0 and envelope["ok"] is True


@pytest.mark.parametrize("branch", BRANCHES)
def test_guard_preserves_graphql_denial_before_acknowledgement(selected_wrapper, mutation_transport, capsys, record_property, branch):
    configure, calls = mutation_transport
    configure(branch, {"errors": [{"message": "LOCAL_MUTATION_DENIED"}]})
    status, envelope = _invoke_guard(selected_wrapper, branch, capsys, record_property)
    _assert_attempt(branch, calls)
    assert status == 1 and envelope["ok"] is False
    assert envelope["error"]["code"] == "GRAPHQL_ERROR"
    assert "LOCAL_MUTATION_DENIED" in envelope["error"]["message"]


def _sibling(branch):
    client = LinearClient()
    if branch == "create-issue":
        return client.create_issue("Fixture issue", TEAM)
    if branch == "set-state":
        return client.set_ticket_state("issue-uuid", "state-uuid")
    return client.create_label(TEAM, "fixture")


@pytest.mark.parametrize("branch", SIBLINGS)
@pytest.mark.parametrize("success", BAD_VALUES)
def test_root_scoped_siblings_share_exact_acknowledgement_rule(mutation_transport, branch, success):
    configure, calls = mutation_transport
    response = _response(branch)
    _replace(response["data"][_key(branch)], "success", success)
    configure(branch, response)
    if success is True:
        assert _sibling(branch)
    else:
        with pytest.raises(LinearClientError) as error:
            _sibling(branch)
        assert error.value.code == ("API_ERROR" if success is False else "INVALID_RESPONSE")
    assert len(calls) == 1 and calls[0]["operation"].startswith("mutation")


@pytest.mark.parametrize("branch", SIBLINGS)
@pytest.mark.parametrize("level", ["data", "acknowledgement"])
@pytest.mark.parametrize("value", [MISSING, None, True, 7, [], "ack"])
def test_root_scoped_siblings_block_unreadable_acknowledgements(mutation_transport, branch, level, value):
    configure, calls = mutation_transport
    response = _response(branch)
    parent, field = (response, "data") if level == "data" else (response["data"], _key(branch))
    _replace(parent, field, value)
    configure(branch, response)
    with pytest.raises(LinearClientError) as error:
        _sibling(branch)
    assert error.value.code == "INVALID_RESPONSE"
    assert len(calls) == 1 and calls[0]["operation"].startswith("mutation")
