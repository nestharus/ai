from __future__ import annotations

import hashlib
import inspect
import io
import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from clients.linear import cli as linear_cli
from clients.linear.client import (
    LinearClient,
    LinearClientError,
    descriptions_match_after_linear_canonicalization,
)


def _client(monkeypatch: pytest.MonkeyPatch) -> LinearClient:
    client = LinearClient(api_key="test-key")
    monkeypatch.setattr(client, "_resolve_team_id", lambda _team: "team-1")
    return client


def _label(name: str, label_id: str, team: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "id": label_id,
        "name": name,
        "color": "#000000",
        "description": None,
        "team": team,
    }


def _page(
    nodes: list[dict[str, Any]], *, has_next: bool, cursor: str | None
) -> dict[str, Any]:
    return {
        "data": {
            "issueLabels": {
                "nodes": nodes,
                "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
            }
        }
    }


def test_list_labels_reads_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    calls: list[dict[str, Any]] = []
    responses = iter(
        [
            _page([_label("first", "label-1")], has_next=True, cursor="cursor-1"),
            _page([_label("hardening", "label-2")], has_next=False, cursor=None),
        ]
    )

    def run(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        assert (
            "filter:{or:[{team:{id:{eq:$teamId}}},{team:{null:true}}]}"
            in "".join(query.split())
        )
        assert variables["teamId"] == "team-1"
        calls.append(variables)
        return next(responses)

    monkeypatch.setattr(client, "_run_graphql", run)

    assert [label["name"] for label in client.list_labels("ACR")] == [
        "first",
        "hardening",
    ]
    assert [call["after"] for call in calls] == [None, "cursor-1"]
    assert all(call["first"] == 50 for call in calls)


@pytest.mark.parametrize(
    "page_info",
    [
        None,
        {"hasNextPage": "yes", "endCursor": "cursor-1"},
        {"hasNextPage": True, "endCursor": None},
    ],
)
def test_list_labels_rejects_malformed_pagination(
    monkeypatch: pytest.MonkeyPatch, page_info: Any
) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        client,
        "_run_graphql",
        lambda _query, _variables: {
            "data": {"issueLabels": {"nodes": [], "pageInfo": page_info}}
        },
    )

    with pytest.raises(LinearClientError) as error:
        client.list_labels("ACR")

    assert error.value.code == "PAGINATION_ERROR"


def test_list_labels_rejects_repeated_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    responses = iter(
        [
            _page([], has_next=True, cursor="cursor-1"),
            _page([], has_next=True, cursor="cursor-1"),
        ]
    )
    monkeypatch.setattr(client, "_run_graphql", lambda _query, _variables: next(responses))

    with pytest.raises(LinearClientError) as error:
        client.list_labels("ACR")

    assert error.value.code == "PAGINATION_ERROR"


@pytest.mark.parametrize("response", [{}, {"data": None}, {"data": []}])
def test_list_labels_rejects_malformed_data_envelope(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]
) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(client, "_run_graphql", lambda _query, _variables: response)

    with pytest.raises(LinearClientError) as error:
        client.list_labels("ACR")

    assert error.value.code == "INVALID_RESPONSE"


def test_resolve_label_ids_uses_later_page_without_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    responses = iter(
        [
            _page([], has_next=True, cursor="cursor-1"),
            _page(
                [_label("hardening", "label-later", {"id": "team-1"})],
                has_next=False,
                cursor=None,
            ),
        ]
    )
    monkeypatch.setattr(client, "_run_graphql", lambda _query, _variables: next(responses))
    monkeypatch.setattr(
        client,
        "create_label",
        lambda *_args, **_kwargs: pytest.fail("existing label must not be recreated"),
    )

    assert client.resolve_label_ids("ACR", ["hardening"], create_missing=True) == [
        "label-later"
    ]


def test_resolve_label_ids_preserves_team_precedence_and_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    team = {"id": "team-1"}
    monkeypatch.setattr(
        client,
        "list_labels",
        lambda _team: [
            _label("shared", "workspace-label"),
            _label("shared", "team-label", team),
        ],
    )
    assert client.resolve_label_ids("ACR", ["shared"]) == ["team-label"]

    monkeypatch.setattr(
        client,
        "list_labels",
        lambda _team: [
            _label("duplicate", "team-a", team),
            _label("duplicate", "team-b", team),
        ],
    )
    with pytest.raises(LinearClientError) as error:
        client.resolve_label_ids("ACR", ["duplicate"])
    assert error.value.code == "AMBIGUOUS_LABEL"


def test_apply_labels_cli_preserves_existing_issue_label(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_property: Any,
) -> None:
    client = _client(monkeypatch)
    calls: list[tuple[str, dict[str, Any]]] = []
    responses = iter(
        [
            {"data": {"issue": {
                "team": {"id": "team-1", "key": "ACR"},
                "labels": {"nodes": [{"id": "existing-label"}]},
            }}},
            _page([_label("hardening", "requested-label")], has_next=False, cursor=None),
            {"data": {"issueUpdate": {
                "success": True, "issue": {"id": "issue-1", "identifier": "ACR-1"},
            }}},
        ]
    )

    def run(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        calls.append((query, variables))
        return next(responses)

    monkeypatch.setattr(client, "_run_graphql", run)
    monkeypatch.setattr(linear_cli, "LinearClient", lambda: client)

    linear_cli.main(["apply-labels", "ACR-1", "--team", "ACR", "--labels", "hardening"])

    payload = json.loads(capsys.readouterr().out)
    record_property("graphql_calls", json.dumps(calls))
    record_property("cli_response", json.dumps(payload))
    assert payload["ok"] is True
    assert payload["data"]["id"] == "issue-1"
    assert len(calls) == 3
    assert "team{idkey}labels{nodes{id}}" in "".join(calls[0][0].split())
    assert calls[0][1] == {"id": "ACR-1"}
    assert "issueLabels(" in calls[1][0]
    assert calls[1][1]["teamId"] == "team-1"
    assert "issueUpdate(" in calls[2][0]
    assert calls[2][1] == {
        "id": "ACR-1",
        "input": {"labelIds": ["existing-label", "requested-label"]},
    }


def test_apply_labels_cli_rejects_issue_team_mismatch_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_property: Any,
) -> None:
    client = _client(monkeypatch)
    calls: list[tuple[str, dict[str, Any]]] = []

    def run(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        calls.append((query, variables))
        return {"data": {"issue": {
            "team": {"id": "other-team", "key": "OTHER"},
            "labels": {"nodes": [{"id": "existing-label"}]},
        }}}

    monkeypatch.setattr(client, "_run_graphql", run)
    monkeypatch.setattr(linear_cli, "LinearClient", lambda: client)

    with pytest.raises(SystemExit) as error:
        linear_cli.main([
            "apply-labels", "OTHER-1", "--team", "ACR", "--labels", "new-label",
            "--create-missing",
        ])

    payload = json.loads(capsys.readouterr().out)
    record_property("graphql_calls", json.dumps(calls))
    record_property("cli_response", json.dumps(payload))
    assert error.value.code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_INPUT"
    assert "Issue/team mismatch" in payload["error"]["message"]
    assert len(calls) == 1
    assert "team{idkey}labels{nodes{id}}" in "".join(calls[0][0].split())
    assert calls[0][1] == {"id": "OTHER-1"}


def test_create_issue_cli_repairs_missing_label_preserving_readback_assignment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_property: Any,
) -> None:
    client = _client(monkeypatch)
    calls: list[tuple[str, dict[str, Any]]] = []
    created_issue = {"id": "created-issue", "identifier": "ACR-2"}
    responses = iter(
        [
            _page([_label("hardening", "requested-label")], has_next=False, cursor=None),
            {"data": {"issueCreate": {"success": True, "issue": created_issue}}},
            {"data": {"issue": {
                **created_issue,
                "description": "expected description",
                "project": None,
                "team": {"id": "team-1", "key": "ACR"},
                "labels": {"nodes": [{"id": "existing-label", "name": "existing"}]},
            }}},
            {"data": {"issue": {
                "team": {"id": "team-1", "key": "ACR"},
                "labels": {"nodes": [{"id": "existing-label"}]},
            }}},
            _page([_label("hardening", "requested-label")], has_next=False, cursor=None),
            {"data": {"issueUpdate": {"success": True, "issue": created_issue}}},
        ]
    )

    def run(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        calls.append((query, variables))
        return next(responses)

    monkeypatch.setattr(client, "_run_graphql", run)
    monkeypatch.setattr(linear_cli, "LinearClient", lambda: client)

    linear_cli.main([
        "create-issue", "--team", "ACR", "--title", "Title",
        "--description", "expected description", "--label", "hardening",
    ])

    payload = json.loads(capsys.readouterr().out)
    record_property("graphql_calls", json.dumps(calls))
    record_property("cli_response", json.dumps(payload))
    assert payload["ok"] is True
    assert payload["data"]["id"] == created_issue["id"]
    assert len(calls) == 6
    assert "issueLabels(" in calls[0][0]
    assert "issueCreate(" in calls[1][0]
    assert calls[1][1] == {"input": {
        "teamId": "team-1", "title": "Title", "description": "expected description",
        "labelIds": ["requested-label"],
    }}
    assert "issue(id: $issueId)" in calls[2][0]
    assert calls[2][1] == {"issueId": created_issue["id"]}
    assert "team{idkey}labels{nodes{id}}" in "".join(calls[3][0].split())
    assert calls[3][1] == {"id": created_issue["id"]}
    assert "issueLabels(" in calls[4][0]
    assert "issueUpdate(" in calls[5][0]
    assert calls[5][1] == {
        "id": created_issue["id"],
        "input": {"labelIds": ["existing-label", "requested-label"]},
    }


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("# Heading\n\n- first\n  - nested\n", "# Heading\n\n* first\n  * nested"),
        ("- first\n", "* first\n"),
        ("text\n", "text"),
        ("- first\r\n", "* first"),
    ],
)
def test_description_readback_accepts_observed_linear_canonicalization(
    expected: str, actual: str
) -> None:
    assert descriptions_match_after_linear_canonicalization(expected, actual)


def test_description_readback_tracks_exact_fence_boundary() -> None:
    expected = "````text\n```\n- literal\n````\n- list\n"
    actual = "````text\n```\n- literal\n````\n* list"

    assert descriptions_match_after_linear_canonicalization(expected, actual)


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("# Original\n", "# Changed"),
        ("- first\n", "* second"),
        ("[label](https://example.test/a)\n", "[label](https://example.test/b)"),
        ("text\n\n", "text"),
        ("```text\n- literal\n```\n", "```text\n* literal\n```"),
        ("* first", "- first"),
        ("text", "text\n"),
        ("    - literal\n", "    * literal"),
        ("- - -\n", "* - -"),
    ],
)
def test_description_readback_rejects_material_drift(
    expected: str, actual: str
) -> None:
    assert not descriptions_match_after_linear_canonicalization(expected, actual)


def test_description_readback_reports_unreadable_source_as_client_error(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.md"

    with pytest.raises(LinearClientError) as error:
        linear_cli.verify_issue_description("ACR-1", str(missing))

    assert error.value.code == "INVALID_INPUT"


def test_verify_issue_description_preserves_raw_crlf_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "description.md"
    expected = b"- first\r\n"
    actual = "* first"
    source.write_bytes(expected)

    class StubClient:
        def get_issue(self, issue_id: str) -> dict[str, str]:
            assert issue_id == "ACR-1"
            return {"description": actual}

    monkeypatch.setattr(linear_cli, "LinearClient", StubClient)

    linear_cli.verify_issue_description("ACR-1", str(source))

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["status"] == "MATCH"
    assert payload["data"]["expectedSha256"] == hashlib.sha256(expected).hexdigest()
    assert payload["data"]["actualSha256"] == hashlib.sha256(
        actual.encode()
    ).hexdigest()


def test_verify_issue_description_mismatch_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "description.md"
    source.write_text("expected", encoding="utf-8")

    class StubClient:
        def get_issue(self, _issue_id: str) -> dict[str, str]:
            return {"description": "changed"}

    monkeypatch.setattr(linear_cli, "LinearClient", StubClient)

    with pytest.raises(SystemExit) as error:
        linear_cli.verify_issue_description("ACR-1", str(source))

    payload = json.loads(capsys.readouterr().out)
    assert error.value.code == 1
    assert payload["ok"] is False
    assert payload["data"]["status"] == "MISMATCH"


@pytest.mark.parametrize("readback", [{"description": None}, {}])
def test_verify_empty_description_rejects_absent_readback(
    readback: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "description.md"
    source.write_text("", encoding="utf-8")

    class StubClient:
        def get_issue(self, _issue_id: str) -> dict[str, object]:
            return readback

    monkeypatch.setattr(linear_cli, "LinearClient", StubClient)

    with pytest.raises(SystemExit) as error:
        linear_cli.verify_issue_description("ACR-1", str(source))

    payload = json.loads(capsys.readouterr().out)
    assert error.value.code == 1
    assert payload["ok"] is False
    assert payload["data"]["status"] == "MISMATCH"
    assert payload["data"]["actualSha256"] is None


def test_create_issue_description_file_preserves_terminal_newlines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "description.md"
    expected = "description\r\n\r\n"
    source.write_bytes(expected.encode())
    captured: dict[str, Any] = {}
    created_issue = {"id": "issue-1", "identifier": "ACR-1"}

    class StubClient:
        def create_issue(self, **kwargs: Any) -> dict[str, str]:
            captured.update(kwargs)
            return created_issue

        def get_issue(self, issue_id: str) -> dict[str, str]:
            assert issue_id == created_issue["id"]
            return {"description": expected}

    monkeypatch.setattr(linear_cli, "LinearClient", StubClient)

    linear_cli.create_issue(
        team="ACR", title="Title", description_file=str(source)
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert captured["description"] == expected


def test_create_issue_description_mismatch_blocks_without_second_create(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = {"create": 0, "read": 0}
    created_issue = {
        "id": "issue-1",
        "identifier": "ACR-1",
        "url": "https://linear.app/issue/ACR-1",
    }

    class StubClient:
        def create_issue(self, **_kwargs: Any) -> dict[str, str]:
            calls["create"] += 1
            return created_issue

        def get_issue(self, issue_id: str) -> dict[str, str]:
            assert issue_id == created_issue["id"]
            calls["read"] += 1
            return {"description": "materially changed"}

    monkeypatch.setattr(linear_cli, "LinearClient", StubClient)

    with pytest.raises(SystemExit) as error:
        linear_cli.main(
            [
                "create-issue",
                "--team",
                "ACR",
                "--title",
                "Title",
                "--description",
                "expected description",
            ]
        )

    assert calls == {"create": 1, "read": 1}
    assert error.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "DESCRIPTION_READBACK_MISMATCH"
    assert "Created issue ACR-1" in payload["error"]["message"]
    assert "do not retry creation" in payload["error"]["message"]


def test_create_description_file_is_keyword_only_without_moving_existing_parameters() -> None:
    create_parameters = list(inspect.signature(linear_cli.create_issue).parameters)
    update_parameters = list(inspect.signature(linear_cli.update_issue).parameters)

    assert create_parameters[:7] == [
        "team",
        "title",
        "description",
        "project_id",
        "labels",
        "create_missing_labels",
        "estimate",
    ]
    assert update_parameters == [
        "issue_id",
        "description",
        "description_file",
        "estimate",
    ]
    assert (
        inspect.signature(linear_cli.create_issue).parameters[
            "description_file"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )


@pytest.mark.parametrize("operation", [linear_cli.create_issue, linear_cli.update_issue])
def test_issue_mutations_reject_conflicting_description_inputs(operation: Any) -> None:
    kwargs = {"description": "inline", "description_file": "description.md"}
    if operation is linear_cli.create_issue:
        kwargs.update(team="ACR", title="Title")
    else:
        kwargs.update(issue_id="ACR-1")

    with pytest.raises(LinearClientError) as error:
        operation(**kwargs)

    assert error.value.code == "INVALID_INPUT"
    assert "mutually exclusive" in str(error.value)


def test_list_comments_cli_preserves_issue_identity_across_pages(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_property: Any,
) -> None:
    issue_id = "57c4f289-c39e-4d13-87bd-7ae56f01854b"
    issue_key = "ACR-390"
    comments = [
        {
            "id": "e8d99e44-248c-4c53-9c80-19a413d909bd",
            "body": "First page comment\n",
            "createdAt": "2026-09-01T12:00:00Z",
            "updatedAt": "2026-09-01T12:00:00Z",
            "user": None,
        },
        {
            "id": "e0067d16-64cc-4aee-88cc-8393f701fa79",
            "body": "Second page comment\n",
            "createdAt": "2026-09-02T12:00:00Z",
            "updatedAt": "2026-09-02T12:00:00Z",
            "user": {"id": "user-1", "name": "Reader", "email": "reader@example.test"},
        },
    ]
    responses = iter([
        {"data": {"issue": {
            "id": issue_id, "identifier": issue_key,
            "comments": {
                "nodes": [comments[0]],
                "pageInfo": {"hasNextPage": True, "endCursor": "comment-page-2"},
            },
        }}},
        {"data": {"issue": {
            "id": issue_id, "identifier": issue_key,
            "comments": {
                "nodes": [comments[1]],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }}},
    ])
    calls: list[dict[str, Any]] = []

    def transport(request: urllib.request.Request, timeout: int) -> io.BytesIO:
        calls.append(json.loads(request.data))
        assert request.get_method() == "POST"
        assert request.full_url == "https://api.linear.app/graphql"
        assert request.get_header("Authorization") == "public-comment-fixture-key"
        assert timeout == 30
        return io.BytesIO(json.dumps(next(responses)).encode("utf-8"))

    monkeypatch.setenv("LINEAR_API_KEY", "public-comment-fixture-key")
    monkeypatch.setattr(urllib.request, "urlopen", transport)

    try:
        linear_cli.main(["list-comments", issue_key])
    finally:
        captured = capsys.readouterr()
        record_property("graphql_calls", json.dumps(calls))
        record_property("cli_stdout", captured.out)
        record_property("cli_stderr", captured.err)

    payload = json.loads(captured.out)
    assert len(calls) == 2
    assert next(responses, None) is None
    assert all("query IssueComments(" in call["query"] for call in calls)
    assert all("comments(first: 100, after: $after)" in call["query"] for call in calls)
    assert [call["variables"] for call in calls] == [
        {"id": issue_key},
        {"id": issue_key, "after": "comment-page-2"},
    ]
    assert payload["ok"] is True
    assert payload["data"]["comments"] == comments
    assert payload["data"]["issueId"] == issue_id
    assert payload["data"]["issueIdentifier"] == issue_key
    assert payload["data"]["totalCount"] == 2
