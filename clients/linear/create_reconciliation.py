"""Read-only duplicate reconciliation for the Linear operator's create procedure.

Declared roles: validator, filter, orchestration.
This helper never creates an issue or substitutes for description verification.
"""

from .client import LinearClient, LinearClientError


def _single_team(client: LinearClient, team_key: str) -> str:
    matches = [team for team in client.list_teams() if team.get("key") == team_key]
    if len(matches) != 1 or not matches[0].get("id"):
        raise LinearClientError("INVALID_INPUT", "Create requires one exact team key")
    return matches[0]["id"]


def _exact_candidate(issue: dict, candidate_id: str, title: str, team_id: str, project_id: str | None) -> bool:
    if not isinstance(issue, dict) or any(
        not isinstance(issue.get(field), str) or not issue[field].strip()
        for field in ("id", "identifier", "title", "url")
    ) or issue["id"] != candidate_id:
        raise LinearClientError("INVALID_RESPONSE", "Duplicate candidate identity is incomplete or changed")
    team = issue.get("team")
    if not isinstance(team, dict) or not isinstance(team.get("id"), str) or not team["id"].strip() or "project" not in issue:
        raise LinearClientError("INVALID_RESPONSE", "Duplicate candidate scope is missing")
    project = issue["project"]
    if project is not None and (
        not isinstance(project, dict) or not isinstance(project.get("id"), str) or not project["id"].strip()
    ):
        raise LinearClientError("INVALID_RESPONSE", "Duplicate candidate project is malformed")
    return (
        issue.get("title") == title
        and issue["team"]["id"] == team_id
        and (project_id is None or (issue.get("project") or {}).get("id") == project_id)
    )


def reconcile_create(client: LinearClient, team_key: str, title: str, project: str | None = None) -> dict:
    if not title or not title.strip():
        raise LinearClientError("INVALID_INPUT", "Create summary must not be blank")
    team_id = _single_team(client, team_key)
    project_id = client.resolve_project_id(team_key, project) if project else None
    candidates = client.search_issues(
        team_id=team_id, title_contains=title, project=project_id,
        include_archived=True, first=100,
    )
    # Search exposes no continuation cursor. A full page cannot prove uniqueness.
    if len(candidates) >= 100:
        raise LinearClientError("AMBIGUOUS_ISSUE", "Duplicate search may be truncated")
    exact = [candidate for candidate in candidates if candidate.get("title") == title]
    matches = _read_matches(client, exact, title, team_id, project_id)
    if len(matches) > 1:
        raise LinearClientError("AMBIGUOUS_ISSUE", "Multiple exact create candidates")
    return {"team_id": team_id, "project_id": project_id, "issue": matches[0] if matches else None}


def _read_matches(client, candidates, title, team_id, project_id):
    matches = {}
    for candidate in candidates:
        candidate_id = candidate.get("id")
        if not candidate_id:
            raise LinearClientError("INVALID_RESPONSE", "Duplicate search candidate has no UUID")
        issue = client.get_issue(candidate_id)
        if _exact_candidate(issue, candidate_id, title, team_id, project_id):
            matches[candidate_id] = issue
    return list(matches.values())
