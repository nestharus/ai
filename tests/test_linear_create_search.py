"""Reconcile create intent through the real client and a local HTTP transport."""

import io
import json
import urllib.request

import pytest

from clients.linear.client import LinearClient, LinearClientError
from clients.linear.create_reconciliation import reconcile_create


TEAM_ID = "00000000-0000-0000-0000-000000000001"
PROJECT_ID = "00000000-0000-0000-0000-000000000002"
ISSUE_ID = "00000000-0000-0000-0000-000000000003"
TITLE = "Export selected records"


def _candidate(title=TITLE):
    return {
        "id": ISSUE_ID, "identifier": "ACR-72", "title": title,
        "url": "https://linear.app/fixture/issue/ACR-72",
        "state": {"id": "state-1", "name": "Todo", "type": "unstarted"},
        "team": {"id": TEAM_ID, "key": "ACR", "name": "Fixture"},
        "labels": {"nodes": []},
    }


@pytest.fixture
def local_reconcile(monkeypatch, record_property):
    calls = []
    search_response = None

    def transport(request, timeout):
        payload = json.loads(request.data)
        calls.append(payload)
        assert request.full_url == "https://api.linear.app/graphql"
        assert request.get_method() == "POST"
        query, variables = payload["query"], payload["variables"]
        assert not query.lstrip().startswith("mutation"), "Reconciliation attempted a mutation"
        if query.startswith("query SearchIssues("):
            assert variables == {
                "filter": {"team": {"id": {"eq": TEAM_ID}},
                           "title": {"containsIgnoreCase": TITLE},
                           "project": {"id": {"eq": PROJECT_ID}}},
                "first": 100, "includeArchived": True,
            }
            response = search_response
        elif "teams(first: 100" in query:
            response = {"data": {"teams": {"nodes": [{"id": TEAM_ID, "key": "ACR", "name": "Fixture"}],
                                          "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
        elif "projects(" in query:
            assert variables["teamId"] == TEAM_ID
            response = {"data": {"projects": {"nodes": [{"id": PROJECT_ID, "slugId": "selected", "name": "Selected"}],
                                             "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
        elif "issue(id: $issueId)" in query:
            assert variables == {"issueId": ISSUE_ID}
            issue = _candidate()
            issue.update(description="Original brief", project={"id": PROJECT_ID, "slugId": "selected",
                                                                "teams": {"nodes": [{"id": TEAM_ID}]}})
            response = {"data": {"issue": issue}}
        else:
            pytest.fail(f"Unexpected query: {query}")
        return io.BytesIO(json.dumps(response).encode("utf-8"))

    def invoke(response):
        nonlocal search_response
        search_response = response
        return reconcile_create(LinearClient(api_key="local-fixture-only"), "ACR", TITLE, "selected")

    monkeypatch.setattr(urllib.request, "urlopen", transport)
    yield invoke, calls
    record_property("requests", json.dumps(calls))


@pytest.mark.parametrize("response", [
    {}, {"data": None}, {"data": []}, {"data": {}},
    {"data": {"issues": None}}, {"data": {"issues": []}},
    {"data": {"issues": {}}}, {"data": {"issues": {"nodes": None}}},
    {"data": {"issues": {"nodes": {}}}}, {"data": {"issues": {"nodes": ""}}},
])
def test_malformed_search_collection_cannot_authorize_create(local_reconcile, response):
    invoke, calls = local_reconcile
    with pytest.raises(LinearClientError) as error:
        invoke(response)
    assert error.value.code == "INVALID_RESPONSE"
    assert calls[-1]["query"].startswith("query SearchIssues(")


@pytest.mark.parametrize("node", [None, False, 7, [], "unreadable"])
@pytest.mark.parametrize("full_page", [False, True])
def test_malformed_search_entry_cannot_disappear(local_reconcile, node, full_page):
    invoke, calls = local_reconcile
    nodes = [_candidate(TITLE + " later") for _ in range(99)] if full_page else []
    nodes.append(node)
    with pytest.raises(LinearClientError) as error:
        invoke({"data": {"issues": {"nodes": nodes}}})
    assert error.value.code == "INVALID_RESPONSE"
    assert calls[-1]["query"].startswith("query SearchIssues(")


@pytest.mark.parametrize("field", ["id", "identifier", "title", "url"])
@pytest.mark.parametrize("value", [None, 7, [], "   ", "absent"])
def test_unreadable_candidate_identity_cannot_be_filtered_into_absence(local_reconcile, field, value):
    invoke, calls = local_reconcile
    node = _candidate(TITLE + " later")
    if value == "absent":
        node.pop(field)
    else:
        node[field] = value
    with pytest.raises(LinearClientError) as error:
        invoke({"data": {"issues": {"nodes": [node]}}})
    assert error.value.code == "INVALID_RESPONSE"
    assert calls[-1]["query"].startswith("query SearchIssues(")


@pytest.mark.parametrize("nodes", [[], [_candidate(TITLE + " later")]])
def test_valid_empty_or_nonmatching_search_keeps_zero_candidate_outcome(local_reconcile, nodes):
    invoke, calls = local_reconcile
    assert invoke({"data": {"issues": {"nodes": nodes}}}) == {
        "team_id": TEAM_ID, "project_id": PROJECT_ID, "issue": None,
    }
    assert calls[-1]["query"].startswith("query SearchIssues(")


def test_valid_exact_scoped_candidate_is_read_back_and_reused(local_reconcile):
    invoke, calls = local_reconcile
    result = invoke({"data": {"issues": {"nodes": [_candidate()]}}})
    assert result["issue"]["id"] == ISSUE_ID
    assert result["issue"]["team"]["id"] == TEAM_ID
    assert result["issue"]["project"]["id"] == PROJECT_ID
    assert calls[-1]["variables"] == {"issueId": ISSUE_ID}


def test_valid_full_page_still_blocks_before_filtering(local_reconcile):
    invoke, calls = local_reconcile
    nodes = [_candidate(TITLE + " later") for _ in range(100)]
    with pytest.raises(LinearClientError) as error:
        invoke({"data": {"issues": {"nodes": nodes}}})
    assert error.value.code == "AMBIGUOUS_ISSUE"
    assert calls[-1]["query"].startswith("query SearchIssues(")
