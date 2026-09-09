"""Real transition/CLI evidence with synthetic transport; no provider calls."""

import io
import json
from pathlib import Path
import re
import shlex
import sys
import urllib.request

import pytest

from clients.linear import cli
from clients.linear.client import LinearClient, LinearClientError


class Transport:
    def __init__(self, initial="todo", concurrent=False, acknowledgement=None):
        self.state = initial
        self.concurrent = concurrent
        self.acknowledgement = {"success": True} if acknowledgement is None else acknowledgement
        self.calls = []
        self.readback_state = "current"
        self.readback_error = False

    def __call__(self, request, timeout):
        payload = json.loads(request.data)
        query, variables = payload["query"], payload["variables"]
        assert request.get_header("Authorization") == "public-transition-fixture"
        self.calls.append(variables)
        response = self.respond(query, variables)
        return io.BytesIO(json.dumps(response).encode())

    def respond(self, query, variables):
        if "issueUpdate(" in query:
            assert variables == {"id": "issue-uuid", "input": {"stateId": "done"}}
            assert "state {" not in query
            self.state = "todo" if self.concurrent else "done"
            return {"data": {"issueUpdate": self.acknowledgement}}
        if "teamId" in variables:
            assert variables == {"teamId": "team-uuid"}
            self.state = "todo" if self.concurrent else self.state
            return {"data": {"team": {"states": {"nodes": [
                {"id": "done", "name": "Done"},
            ]}}}}
        return self.issue_response(variables)

    def issue_response(self, variables):
        assert variables == {"issueId": "ACR-529" if len(self.calls) == 1 else "issue-uuid"}
        if self.readback_error and len(self.calls) > 1:
            return {"errors": [{"message": "synthetic read failure"}]}
        state = {"id": self.state, "name": self.state.title()}
        if len(self.calls) > 1 and self.readback_state != "current":
            state = self.readback_state
        return {"data": {"issue": {
            "id": "issue-uuid", "identifier": "ACR-529", "state": state,
            "team": {"id": "team-uuid"}, "project": None, "labels": {"nodes": []},
        }}}


@pytest.fixture
def transport(monkeypatch):
    instance = Transport()
    monkeypatch.setenv("LINEAR_API_KEY", "public-transition-fixture")
    monkeypatch.setattr(urllib.request, "urlopen", instance)
    return instance


def invoke_cli(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["linear", *args])
    cli.main()
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("initial,outcome,count", [
    ("todo", "acknowledged", 3), ("done", "already_matching", 2),
])
@pytest.mark.parametrize("concurrent", [False, True])
def test_transition_evidence(transport, monkeypatch, capsys, initial, outcome, count, concurrent):
    transport.state = initial
    transport.concurrent = concurrent
    result = invoke_cli(monkeypatch, capsys, "transition-issue", "ACR-529", "--target-status", " Done ")
    assert result == {"ok": True, "data": {
        "issue_id": "issue-uuid", "identifier": "ACR-529", "requestedStatus": "Done",
        "initialState": {"id": initial, "name": initial.title()},
        "resolvedTarget": {"id": "done", "name": "Done"}, "outcome": outcome,
    }}
    assert len(transport.calls) == count  # no post-read, no no-op mutation
    assert transport.state == ("todo" if concurrent else "done")


@pytest.mark.parametrize("ack,error", [
    ({"success": False}, "API_ERROR"), ({}, "INVALID_RESPONSE"),
    ({"success": None}, "INVALID_RESPONSE"), ({"success": 1}, "INVALID_RESPONSE"),
    ({"success": "true"}, "INVALID_RESPONSE"), ([], "INVALID_RESPONSE"),
    (True, "INVALID_RESPONSE"), (None, "INVALID_RESPONSE"),
])
@pytest.mark.parametrize("entry", ["client", "cli"])
def test_bad_ack_never_reports_success(transport, monkeypatch, capsys, ack, error, entry):
    transport.acknowledgement = ack
    if entry == "client":
        with pytest.raises(LinearClientError) as caught:
            LinearClient().transition_issue("ACR-529", "Done")
        assert caught.value.code == error
    else:
        with pytest.raises(SystemExit) as caught:
            invoke_cli(monkeypatch, capsys, "transition-issue", "ACR-529", "--target-status", "Done")
        assert caught.value.code == 1
        result = json.loads(capsys.readouterr().out)
        assert result["ok"] is False
        assert result["error"]["code"] == error
        assert "data" not in result
    assert len(transport.calls) == 3  # one attempt, never automatic retry


@pytest.mark.parametrize("concurrent", [False, True])
@pytest.mark.parametrize("initial", ["todo", "done"])
def test_explicit_get_issue_observes_instead_of_echoing_target(transport, monkeypatch, capsys, initial, concurrent):
    transport.state = initial
    transport.concurrent = concurrent
    transition = LinearClient().transition_issue("ACR-529", "Done")
    before_read = len(transport.calls)
    read = invoke_cli(monkeypatch, capsys, "get-issue", transition["issue_id"])
    assert read["ok"] is True
    assert read["data"]["state"] == {"id": transport.state, "name": transport.state.title()}
    assert (read["data"]["state"]["id"] == transition["resolvedTarget"]["id"]) is not concurrent
    assert len(transport.calls) == before_read + 1
    transport.state = "todo"  # a read does not lock state or guarantee durability
    assert read["data"]["state"]["id"] == ("todo" if concurrent else "done")


@pytest.mark.parametrize("state", [None, {}, {"name": "Done"}])
def test_explicit_read_preserves_unverifiable_state(transport, monkeypatch, capsys, state):
    transition = LinearClient().transition_issue("ACR-529", "Done")
    transport.readback_state = state
    read = invoke_cli(monkeypatch, capsys, "get-issue", transition["issue_id"])
    assert read["data"]["state"] == state  # cannot substitute resolvedTarget
    assert transition["outcome"] == "acknowledged"
    assert len(transport.calls) == 4


def test_read_failure_does_not_erase_acknowledgement(transport, monkeypatch, capsys):
    transition = LinearClient().transition_issue("ACR-529", "Done")
    transport.readback_error = True
    with pytest.raises(SystemExit) as caught:
        invoke_cli(monkeypatch, capsys, "get-issue", transition["issue_id"])
    assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert transition["outcome"] == "acknowledged"
    assert len(transport.calls) == 4


def test_operator_documented_command_uses_acknowledgement_contract(transport, monkeypatch, capsys):
    """Execute the documented caller command through the real CLI and transport."""
    root = Path(__file__).resolve().parents[1]
    procedure = (root / "agents/linear-operator.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)```", procedure, re.S)
    command = next(block for block in blocks if "transition-issue" in block)
    argv = shlex.split(command)
    args = argv[argv.index("transition-issue"):]
    args[1] = "ACR-529"  # substitute the fixture issue and its supported target
    args[args.index("--target-status") + 1] = "Done"
    result = invoke_cli(monkeypatch, capsys, *args)
    assert result["data"]["outcome"] == "acknowledged"
    assert result["data"]["initialState"]["name"] == "Todo"
    assert result["data"]["resolvedTarget"]["name"] == "Done"
    assert len(transport.calls) == 3
