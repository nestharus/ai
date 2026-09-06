"""Required read facts must be complete before reconciliation can authorize writes."""

from copy import deepcopy
import io
import json
import urllib.request

import pytest

from clients.linear import cli
from clients.linear.client import LinearClient, LinearClientError
from clients.linear.create_reconciliation import reconcile_create


TEAM = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
ISSUE = "00000000-0000-0000-0000-000000000003"
KEY = "ACR-72"
TITLE = "Export selected records"
BODY = "## Status\nUpdated body\n"
MISSING = object()
INVALID_STRINGS = [MISSING, None, False, True, 7, [], {}, "", " \t\n"]
VALUE_IDS = ["missing", "null", "false", "true", "number", "list", "object", "empty", "blank"]


def _changed(document, path, value):
    result = deepcopy(document)
    parent = result
    for key in path[:-1]:
        parent = parent[key]
    if value is MISSING:
        del parent[path[-1]]
    else:
        parent[path[-1]] = value
    return result


def _issue():
    return {
        "id": ISSUE, "identifier": KEY, "title": TITLE,
        "url": "https://linear.app/fixture/issue/ACR-72",
        "description": "Exact original brief\n",
        "team": {"id": TEAM, "key": "ACR"},
        "project": {"id": PROJECT, "teams": {"nodes": [{"id": TEAM}]}},
        "labels": {"nodes": []},
    }


@pytest.fixture
def readback(monkeypatch, record_property):
    calls = []
    selected_response = None

    def transport(request, timeout):
        payload = json.loads(request.data)
        query, variables = payload["query"], payload["variables"]
        calls.append({"operation": query.strip().split("{")[0], "variables": variables})
        assert request.full_url == "https://api.linear.app/graphql"
        assert not query.lstrip().startswith("mutation"), "Readback attempted a mutation"
        if "teams(first: 100" in query:
            response = {"data": {"teams": {"nodes": [{"id": TEAM, "key": "ACR"}],
                                          "pageInfo": {"hasNextPage": False}}}}
        elif "projects(" in query:
            response = {"data": {"projects": {"nodes": [{"id": PROJECT, "slugId": "selected"}],
                                             "pageInfo": {"hasNextPage": False}}}}
        elif "query SearchIssues(" in query:
            response = {"data": {"issues": {"nodes": [_issue()]}}}
        elif "issue(id: $issueId)" in query:
            assert variables == {"issueId": ISSUE}
            response = selected_response
        else:
            pytest.fail(f"Unexpected query: {query}")
        return io.BytesIO(json.dumps(response).encode())

    def invoke(response, project="selected"):
        nonlocal selected_response
        selected_response = response
        return reconcile_create(LinearClient(api_key="local-fixture-only"), "ACR", TITLE, project)

    monkeypatch.setattr(urllib.request, "urlopen", transport)
    yield invoke, calls
    record_property("requests", json.dumps(calls))


@pytest.mark.parametrize("path", [("id",), ("identifier",), ("title",), ("url",),
                                 ("team", "id"), ("project", "id")])
@pytest.mark.parametrize("value", INVALID_STRINGS, ids=VALUE_IDS)
def test_candidate_readback_requires_identity_title_and_scope(readback, path, value):
    invoke, calls = readback
    with pytest.raises(LinearClientError) as error:
        invoke({"data": {"issue": _changed(_issue(), path, value)}})
    assert error.value.code == "INVALID_RESPONSE"
    assert calls[-1]["variables"] == {"issueId": ISSUE}


@pytest.mark.parametrize("field", ["team", "project"])
@pytest.mark.parametrize("value", [MISSING, False, True, 7, [], "", "scope"],
                         ids=["missing", "false", "true", "number", "list", "empty", "text"])
def test_candidate_readback_requires_scope_objects(readback, field, value):
    invoke, _ = readback
    with pytest.raises(LinearClientError) as error:
        invoke({"data": {"issue": _changed(_issue(), (field,), value)}})
    assert error.value.code == "INVALID_RESPONSE"


@pytest.mark.parametrize("value", [MISSING, None, False, True, 7, [], {}, "issue"],
                         ids=["missing", "null", "false", "true", "number", "list", "object", "text"])
def test_candidate_readback_requires_an_issue_object(readback, value):
    invoke, _ = readback
    with pytest.raises(LinearClientError) as error:
        invoke(_changed({"data": {"issue": _issue()}}, ("data", "issue"), value))
    assert error.value.code in {"INVALID_RESPONSE", "NOT_FOUND"}


def test_candidate_readback_rejects_changed_id_and_null_team(readback):
    invoke, _ = readback
    for field, value in [("id", "different-issue"), ("team", None)]:
        with pytest.raises(LinearClientError) as error:
            invoke({"data": {"issue": _changed(_issue(), (field,), value)}})
        assert error.value.code == "INVALID_RESPONSE"


@pytest.mark.parametrize("path,value,project,reused", [
    (("title",), TITLE, "selected", True),
    (("title",), "Renamed issue", "selected", False),
    (("team", "id"), "other-team", "selected", False),
    (("project", "id"), "other-project", "selected", False),
    (("project",), None, "selected", False),
    (("project",), None, None, True),
    (("project", "id"), "other-project", None, True),
])
def test_valid_candidate_readback_preserves_reuse_and_exclusion(readback, path, value, project, reused):
    invoke, _ = readback
    result = invoke({"data": {"issue": _changed(_issue(), path, value)}}, project)
    assert (result["issue"] is not None) == reused
    if reused:
        assert result["issue"]["id"] == ISSUE
        assert result["issue"]["description"] == "Exact original brief\n"


def _comment_page(nodes=None, *, next_cursor=None):
    return {"data": {"issue": {
        "id": ISSUE, "identifier": KEY,
        "comments": {
            "nodes": [{"id": "matching-comment", "body": "## Status\nOld body"}] if nodes is None else nodes,
            "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor},
        },
    }}}


@pytest.fixture
def comment_transport(monkeypatch, record_property):
    calls = []
    pages = []
    page_index = 0

    def transport(request, timeout):
        nonlocal page_index
        payload = json.loads(request.data)
        query, variables = payload["query"], payload["variables"]
        calls.append({"operation": query.strip().split("{")[0], "variables": variables})
        assert request.full_url == "https://api.linear.app/graphql"
        if "query IssueComments(" in query:
            assert page_index < len(pages), "Unexpected read, possibly a pagination loop"
            response = pages[page_index]
            page_index += 1
        elif "mutation CommentUpdate(" in query:
            response = {"data": {"commentUpdate": {"success": True, "comment": {
                "id": variables["id"], "body": variables["input"]["body"], "updatedAt": "now",
            }}}}
        elif "mutation CommentCreate(" in query:
            response = {"data": {"commentCreate": {"success": True, "comment": {
                "id": "new-comment", "body": variables["input"]["body"], "createdAt": "now",
                "issue": {"id": ISSUE}, "user": None,
            }}}}
        else:
            pytest.fail(f"Unexpected query: {query}")
        return io.BytesIO(json.dumps(response).encode())

    def configure(responses):
        nonlocal pages
        pages = responses

    monkeypatch.setenv("LINEAR_API_KEY", "local-fixture-only")
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    yield configure, calls
    record_property("requests", json.dumps(calls))


def _assert_comment_blocked(consumer, capsys, calls, codes):
    if consumer == "cli":
        with pytest.raises(SystemExit) as error:
            cli.main(["list-comments", KEY])
        assert error.value.code == 1
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["ok"] is False and "data" not in envelope
        assert envelope["error"]["code"] in codes
    else:
        with pytest.raises(LinearClientError) as error:
            LinearClient().upsert_comment(KEY, "Status", BODY)
        assert error.value.code in codes
    assert not any(call["operation"].startswith("mutation") for call in calls)


def _bad_comment_pages():
    base = _comment_page()
    fields = [
        (("id",), INVALID_STRINGS), (("identifier",), INVALID_STRINGS),
        (("comments",), [MISSING, None, False, 7, [], ""]),
        (("comments", "nodes"), [MISSING, None, False, 7, {}, ""]),
        (("comments", "nodes", 0), [None, False, 7, [], ""]),
        (("comments", "nodes", 0, "id"), INVALID_STRINGS),
        (("comments", "nodes", 0, "body"), [MISSING, None, False, 7, [], {}]),
        (("comments", "pageInfo"), [MISSING, None, False, 7, [], ""]),
        (("comments", "pageInfo", "hasNextPage"), [MISSING, None, 0, 1, [], {}, "", "false"]),
    ]
    for path, values in fields:
        for index, value in enumerate(values):
            yield pytest.param(_changed(base, ("data", "issue", *path), value),
                               id="-".join(map(str, path)) + f"-{index}")
    for index, value in enumerate([MISSING, None, False, True, 7, [], {}, "issue"]):
        yield pytest.param(_changed(base, ("data", "issue"), value), id=f"issue-{index}")


@pytest.mark.parametrize("consumer", ["cli", "upsert"])
@pytest.mark.parametrize("later_page", [False, True], ids=["first", "later"])
@pytest.mark.parametrize("bad_page", list(_bad_comment_pages()))
def test_unreadable_comment_page_never_authorizes_a_mutation(comment_transport, capsys, consumer, later_page, bad_page):
    configure, calls = comment_transport
    pages = [_comment_page(next_cursor="page-2")] if later_page else []
    configure([*pages, bad_page])
    _assert_comment_blocked(consumer, capsys, calls, {"INVALID_RESPONSE", "NOT_FOUND"})


@pytest.mark.parametrize("consumer", ["cli", "upsert"])
@pytest.mark.parametrize("field", ["id", "identifier"])
def test_later_issue_identity_cannot_supply_a_foreign_comment(comment_transport, capsys, consumer, field):
    configure, calls = comment_transport
    foreign = _changed(_comment_page(), ("data", "issue", field), "foreign-issue")
    configure([_comment_page([], next_cursor="page-2"), foreign])
    _assert_comment_blocked(consumer, capsys, calls, {"INVALID_RESPONSE"})


@pytest.mark.parametrize("consumer", ["cli", "upsert"])
def test_first_page_must_belong_to_the_requested_issue(comment_transport, capsys, consumer):
    configure, calls = comment_transport
    foreign = _changed(_comment_page(), ("data", "issue", "id"), "foreign-id")
    foreign = _changed(foreign, ("data", "issue", "identifier"), "OTHER-99")
    configure([foreign])
    _assert_comment_blocked(consumer, capsys, calls, {"INVALID_RESPONSE"})


@pytest.mark.parametrize("requested", [KEY, KEY.lower(), "  " + KEY + "  ", ISSUE])
def test_comment_request_accepts_identifier_or_uuid_without_new_format_gate(comment_transport, capsys, requested):
    configure, calls = comment_transport
    configure([_comment_page([])])
    cli.main(["list-comments", requested])
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert calls[0]["variables"] == {"id": requested}


@pytest.mark.parametrize("consumer", ["cli", "upsert"])
@pytest.mark.parametrize("later_page", [False, True])
@pytest.mark.parametrize("cursor", INVALID_STRINGS, ids=VALUE_IDS)
def test_continuation_requires_a_usable_cursor(comment_transport, capsys, consumer, later_page, cursor):
    configure, calls = comment_transport
    broken = _changed(_comment_page(next_cursor="next"), ("data", "issue", "comments", "pageInfo", "endCursor"), cursor)
    configure([*([_comment_page(next_cursor="page-2")] if later_page else []), broken])
    _assert_comment_blocked(consumer, capsys, calls, {"PAGINATION_ERROR"})


@pytest.mark.parametrize("consumer", ["cli", "upsert"])
@pytest.mark.parametrize("cursors", [["A", "A"], ["A", "B", "A"]], ids=["repeat", "cycle"])
def test_comment_cursor_cannot_be_revisited(comment_transport, capsys, consumer, cursors):
    configure, calls = comment_transport
    configure([_comment_page([], next_cursor=cursor) for cursor in cursors])
    _assert_comment_blocked(consumer, capsys, calls, {"PAGINATION_ERROR"})
    assert len(calls) == len(cursors)


def test_complete_empty_comment_collection_is_success(comment_transport, capsys):
    configure, calls = comment_transport
    configure([_comment_page([])])
    cli.main(["list-comments", KEY])
    assert json.loads(capsys.readouterr().out) == {"ok": True, "data": {
        "issueId": ISSUE, "issueIdentifier": KEY, "comments": [], "totalCount": 0,
    }}
    assert len(calls) == 1


def test_valid_pages_preserve_exact_bodies_optional_user_and_identity(comment_transport, capsys):
    configure, calls = comment_transport
    nodes = [{"id": "empty", "body": ""}, {"id": "spaces", "body": " \n", "user": None},
             {"id": "later", "body": "## Status\nOriginal\n", "user": {"id": "user-1"}}]
    configure([_comment_page(nodes[:2], next_cursor="next"), _comment_page(nodes[2:])])
    cli.main(["list-comments", KEY])
    result = json.loads(capsys.readouterr().out)["data"]
    assert result["issueId"] == ISSUE and result["issueIdentifier"] == KEY
    assert result["totalCount"] == 3
    assert [node["body"] for node in result["comments"]] == [node["body"] for node in nodes]
    assert [node["user"] for node in result["comments"]] == [None, None, {"id": "user-1", "name": None, "email": None}]
    assert [call["variables"] for call in calls] == [{"id": KEY}, {"id": KEY, "after": "next"}]


@pytest.mark.parametrize("existing", [False, True])
def test_upsert_creates_after_complete_absence_or_updates_later_match(comment_transport, existing):
    configure, calls = comment_transport
    configure([_comment_page([{"id": "empty-body", "body": ""}], next_cursor="next"),
               _comment_page(None if existing else [])])
    result = LinearClient().upsert_comment(KEY, "Status", BODY)
    assert result["created"] is not existing
    assert result["id"] == ("matching-comment" if existing else "new-comment")
    assert result["body"] == BODY
    assert len(calls) == 3
    assert calls[-1]["variables"] == ({"id": "matching-comment", "input": {"body": BODY}} if existing
                                       else {"input": {"issueId": KEY, "body": BODY}})
