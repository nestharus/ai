"""Python client for the Linear GraphQL API.

This module provides a Python interface to the Linear API using direct
GraphQL queries over urllib. It is the single low-level Linear GraphQL client.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
from typing import Any, cast

LINEAR_API_URL = "https://api.linear.app/graphql"
ALLOWED_ESTIMATES = {1, 2, 3, 5, 8, 13, 21, 40, 100}
ROUTINE_MANAGER_OWNED_STATES: frozenset[str] = frozenset(
    {"Todo", "In Progress", "Done"}
)
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def normalize_description_for_readback(description: str) -> str:
    """Normalize only Linear's observed unordered-list marker canonicalization."""
    normalized: list[str] = []
    fence: tuple[str, int] | None = None
    for line in description.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        fence_match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", body)
        if fence is None and fence_match:
            marker = fence_match.group(1)
            fence = (marker[0], len(marker))
        elif fence is not None and fence_match:
            marker = fence_match.group(1)
            remainder = fence_match.group(2)
            if (
                marker[0] == fence[0]
                and len(marker) >= fence[1]
                and not remainder.strip()
            ):
                fence = None
        elif fence is None:
            thematic_break = re.match(r"^ {0,3}(?:-[ \t]*){3,}$", body)
            if not thematic_break:
                body = re.sub(r"^( {0,3})-([ \t]+)", r"\1*\2", body)
        normalized.append(body + ending)
    return "".join(normalized)


def _remove_one_terminal_newline(value: str) -> str:
    if value.endswith("\r\n"):
        return value[:-2]
    if value.endswith("\n"):
        return value[:-1]
    return value


def descriptions_match_after_linear_canonicalization(
    expected: str, actual: str
) -> bool:
    """Compare descriptions without accepting unobserved semantic drift."""
    list_canonicalized = normalize_description_for_readback(expected)
    allowed = {
        expected,
        list_canonicalized,
        _remove_one_terminal_newline(expected),
        _remove_one_terminal_newline(list_canonicalized),
    }
    return actual in allowed


class LinearClientError(Exception):
    """Raised when a Linear API operation fails.

    Standard error codes:
        MISSING_API_KEY: No API key provided and LINEAR_API_KEY env var not set.
        EMPTY_API_KEY: API key is empty or whitespace-only.
        API_ERROR: HTTP error from Linear API (includes status code).
        PARSE_ERROR: Failed to parse JSON response or non-UTF-8 response.
        GRAPHQL_ERROR: GraphQL-level errors returned by the API.
        NOT_FOUND: Requested resource (issue, team, etc.) not found.
        INVALID_RESPONSE: Linear response is missing required query fields.
        INVALID_PRIORITY: Priority value not in valid range 0-4.
        NO_UPDATES: No fields provided to update an issue.
        INVALID_INPUT: User input failed client-side validation.
        PAGINATION_ERROR: Pagination did not advance properly.
    """

    def __init__(self, code: str, message: str) -> None:
        """Initialize the error with a code and message.

        Args:
            code: Error code identifying the type of error.
            message: Human-readable error message.
        """
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _search_issue_nodes(result: dict[str, Any]) -> list[Any]:
    """Require a search collection instead of interpreting unreadable data as empty."""
    data = result.get("data")
    issues = data.get("issues") if isinstance(data, dict) else None
    nodes = issues.get("nodes") if isinstance(issues, dict) else None
    if not isinstance(nodes, list):
        raise LinearClientError(
            "INVALID_RESPONSE", "Linear search response requires data.issues.nodes as a list"
        )
    return nodes


def _validate_search_issue_identity(node: Any) -> None:
    """Reject unreadable candidates before callers can filter them into absence."""
    if not isinstance(node, dict):
        raise LinearClientError("INVALID_RESPONSE", "Linear search issue must be an object")
    invalid = [
        field for field in ("id", "identifier", "title", "url")
        if not isinstance(node.get(field), str) or not node[field].strip()
    ]
    if invalid:
        raise LinearClientError(
            "INVALID_RESPONSE",
            "Linear search issue requires non-blank strings: " + ", ".join(invalid),
        )


class LinearClient:
    """Python client for the Linear GraphQL API.

    Provides methods for fetching and updating Linear tickets, attachments,
    comments, projects, teams, and workflow states.

    Attributes:
        _api_key: The Linear API key used for authentication.
        _teams_cache: Cached teams list to avoid redundant API calls.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Linear client.

        Args:
            api_key: Optional Linear API key. If not provided, defaults to
                the LINEAR_API_KEY environment variable.

        Raises:
            LinearClientError: If no API key is provided and LINEAR_API_KEY
                environment variable is not set (MISSING_API_KEY), or if the
                API key is empty or whitespace-only (EMPTY_API_KEY).
        """
        self._teams_cache: dict[bool, list[dict[str, Any]]] = {}
        if api_key is not None:
            if not api_key.strip():
                raise LinearClientError(
                    "EMPTY_API_KEY",
                    "API key is empty or whitespace-only",
                )
            self._api_key = api_key.strip()
        else:
            env_key = os.environ.get("LINEAR_API_KEY")
            if not env_key:
                raise LinearClientError(
                    "MISSING_API_KEY",
                    "LINEAR_API_KEY must be provided or set in environment",
                )
            env_key = env_key.strip()
            if not env_key:
                raise LinearClientError(
                    "EMPTY_API_KEY",
                    "LINEAR_API_KEY environment variable is empty or whitespace-only",
                )
            self._api_key = env_key

    def _run_graphql(
        self, query: str, variables: dict[str, Any] | None = None, timeout: int = 30
    ) -> dict[str, Any]:
        """Run a GraphQL query against Linear API.

        All user-supplied values must be passed via the variables parameter,
        not interpolated into the query string. Query strings should only
        contain static GraphQL structure and $variable placeholders.

        Args:
            query: GraphQL query string with $variable placeholders.
            variables: Dictionary of variable values to send with the query.
            timeout: Request timeout in seconds. Defaults to 30.

        Returns:
            Parsed JSON response data.

        Raises:
            LinearClientError: If the API call fails due to network issues
                (API_ERROR), HTTP errors (API_ERROR), GraphQL errors
                (GRAPHQL_ERROR), or malformed responses (PARSE_ERROR).
        """
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        try:
            data = json.dumps(payload).encode("utf-8")
        except TypeError as e:
            raise LinearClientError(
                "PARSE_ERROR",
                f"Failed to serialize request payload to JSON: {e}",
            ) from e
        req = urllib.request.Request(
            LINEAR_API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": self._api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                try:
                    response_body = raw.decode("utf-8")
                except UnicodeDecodeError as e:
                    raise LinearClientError(
                        "PARSE_ERROR",
                        f"Linear API returned non-UTF-8 response: {e}",
                    ) from e
        except urllib.error.HTTPError as e:
            raise LinearClientError(
                "API_ERROR",
                f"Linear API HTTP error: {e.code} {e.reason}",
            ) from e
        except urllib.error.URLError as e:
            raise LinearClientError(
                "API_ERROR",
                f"Linear API request failed: {e.reason}",
            ) from e
        except TimeoutError as e:
            raise LinearClientError(
                "API_ERROR",
                f"Linear API request timed out after {timeout} seconds",
            ) from e

        try:
            result_raw: Any = json.loads(response_body)
            if not isinstance(result_raw, dict):
                raise LinearClientError(
                    "PARSE_ERROR",
                    "Linear API returned non-object JSON response",
                )
            result: dict[str, Any] = result_raw
        except json.JSONDecodeError as e:
            raise LinearClientError(
                "PARSE_ERROR",
                f"Linear API returned malformed JSON: {e}",
            ) from e

        errors = result.get("errors")
        if errors is not None:
            if not isinstance(errors, list):
                raise LinearClientError(
                    "PARSE_ERROR",
                    "Linear API returned malformed errors field",
                )
            error_messages = [
                str(message)
                for err in errors
                if isinstance(err, dict) and (message := err.get("message"))
            ]
            joined_messages = (
                "; ".join(error_messages) if error_messages else "Unknown error"
            )
            raise LinearClientError(
                "GRAPHQL_ERROR", f"Linear API error: {joined_messages}"
            )

        return result

    def _resolve_team_id(self, team: str) -> str | None:
        """Resolve a team identifier to a team UUID.

        Attempts to resolve the team identifier in the following order:
        1. Early reject empty/whitespace-only or excessively long strings
        2. If the string matches UUID pattern, return as-is
        3. Search teams by key (case-insensitive)
        4. Search teams by name (case-insensitive)

        Args:
            team: Team identifier - can be a UUID, team key, or team name.

        Returns:
            The team UUID if found, None otherwise.
        """
        trimmed = team.strip()
        if not trimmed or len(trimmed) > 100:
            return None

        # UUID pattern: 8-4-4-4-12 hex characters
        uuid_pattern = re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        )
        if uuid_pattern.match(trimmed):
            return trimmed

        # Fetch all teams and search by key, then by name (case-insensitive)
        teams = self.list_teams(include_archived=True)
        team_lower = trimmed.lower()

        # First, search by key (case-insensitive)
        for t in teams:
            if t.get("key", "").lower() == team_lower:
                return str(t.get("id"))

        # Then, search by name (case-insensitive)
        for t in teams:
            if t.get("name", "").lower() == team_lower:
                return str(t.get("id"))

        return None

    def _validate_priority(self, priority: int | None) -> None:
        """Validate that priority is within the valid range.

        Args:
            priority: Priority value to validate. Can be None (no validation
                needed) or an integer from 0-4.

        Raises:
            LinearClientError: If priority is not None and not in range 0-4.
        """
        if priority is not None and (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority < 0
            or priority > 4
        ):
            raise LinearClientError(
                "INVALID_PRIORITY",
                f"Priority must be between 0 and 4, got: {priority}",
            )

    def _validate_estimate(self, estimate: int | None) -> None:
        """Validate that estimate is an allowed story-point value."""
        if estimate is None:
            return
        if (
            not isinstance(estimate, int)
            or isinstance(estimate, bool)
            or estimate not in ALLOWED_ESTIMATES
        ):
            allowed = ", ".join(str(value) for value in sorted(ALLOWED_ESTIMATES))
            raise LinearClientError(
                "INVALID_INPUT",
                f"estimate must be a fibonacci point value: {allowed}",
            )

    def get_issue(self, issue_id: str) -> dict[str, Any]:
        """Fetch issue details by ID.

        Args:
            issue_id: Linear issue ID (e.g., "NES-24" or UUID).

        Returns:
            Dictionary with issue data including:
            - id: str
            - identifier: str
            - title: str
            - description: str | None
            - priority: int
            - estimate: int | None
            - url: str
            - branchName: str
            - createdAt: str
            - updatedAt: str
            - completedAt: str | None
            - canceledAt: str | None
            - dueDate: str | None
            - team: dict | None (id, name, key)
            - assignee: dict | None (id, name, email)
            - state: dict | None (id, name, type)
            - project: dict | None (id, name, slugId, teams)
            - labels: list[dict]
            - parent: dict | None (id, identifier, title)

        Raises:
            LinearClientError: If the operation fails.
        """
        query = """
query($issueId: String!) {
  issue(id: $issueId) {
    id
    identifier
    title
    description
    priority
    estimate
    url
    branchName
    createdAt
    updatedAt
    completedAt
    canceledAt
    dueDate
    team {
      id
      name
      key
    }
    assignee {
      id
      name
      email
    }
    state {
      id
      name
      type
    }
    project {
      id
      slugId
      name
      teams {
        nodes {
          id
          key
          name
        }
      }
    }
    labels {
      nodes {
        id
        name
        color
        team {
          id
          key
        }
      }
    }
    parent {
      id
      identifier
      title
    }
  }
}
"""
        variables = {"issueId": issue_id}
        result = self._run_graphql(query, variables)
        issue = result.get("data", {}).get("issue")
        if not issue:
            raise LinearClientError("NOT_FOUND", f"Issue not found: {issue_id}")

        if "project" not in issue:
            raise LinearClientError(
                "INVALID_RESPONSE",
                "Linear issue response missing required field: project",
            )

        project = issue.get("project")
        if isinstance(project, dict):
            teams = project.get("teams")
            if isinstance(teams, dict):
                team_nodes = teams.get("nodes")
                if not isinstance(team_nodes, list):
                    raise LinearClientError(
                        "INVALID_RESPONSE",
                        "Linear issue response missing required field: project.teams.nodes",
                    )
                project = {**project, "teams": team_nodes}
            else:
                raise LinearClientError(
                    "INVALID_RESPONSE",
                    "Linear issue response missing required field: project.teams",
                )
        elif project is not None:
            raise LinearClientError(
                "INVALID_RESPONSE",
                "Linear issue response field project must be an object or null",
            )

        if "labels" not in issue or issue.get("labels") is None:
            raise LinearClientError(
                "INVALID_RESPONSE",
                "Linear issue response missing required field: labels",
            )

        labels = issue.get("labels")
        if not isinstance(labels, dict):
            raise LinearClientError(
                "INVALID_RESPONSE",
                "Linear issue response field labels must be an object",
            )
        label_nodes = labels.get("nodes")
        if not isinstance(label_nodes, list):
            raise LinearClientError(
                "INVALID_RESPONSE",
                "Linear issue response missing required field: labels.nodes",
            )

        # Build the response with proper structure
        return {
            "id": issue.get("id"),
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "description": issue.get("description"),
            "priority": issue.get("priority"),
            "estimate": issue.get("estimate"),
            "url": issue.get("url"),
            "branchName": issue.get("branchName"),
            "createdAt": issue.get("createdAt"),
            "updatedAt": issue.get("updatedAt"),
            "completedAt": issue.get("completedAt"),
            "canceledAt": issue.get("canceledAt"),
            "dueDate": issue.get("dueDate"),
            "team": issue.get("team"),
            "assignee": issue.get("assignee"),
            "state": issue.get("state"),
            "project": project,
            "labels": label_nodes,
            "parent": issue.get("parent"),
        }

    def get_ticket_info(self, ticket_id: str) -> dict[str, Any]:
        """Get basic ticket info from Linear.

        Args:
            ticket_id: Linear ticket ID (e.g., "NES-123" or UUID).

        Returns:
            Dictionary with ticket data including:
            - id: str (UUID)
            - identifier: str (e.g., "NES-123")
            - title: str
            - branch_name: str
            - state: str (state name)
            - state_type: str (state type)
            - team_id: str (team UUID)

        Raises:
            LinearClientError: If ticket not found or API call fails.
        """
        query = """
query($ticketId: String!) {
  issue(id: $ticketId) {
    id
    identifier
    title
    branchName
    state {
      id
      name
      type
    }
    team {
      id
    }
  }
}
"""
        variables = {"ticketId": ticket_id}
        result = self._run_graphql(query, variables)
        issue = result.get("data", {}).get("issue")
        if not issue:
            raise LinearClientError("NOT_FOUND", f"Ticket not found: {ticket_id}")

        return {
            "id": issue.get("id"),
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "branch_name": issue.get("branchName"),
            "state": (issue.get("state") or {}).get("name"),
            "state_type": (issue.get("state") or {}).get("type"),
            "team_id": (issue.get("team") or {}).get("id"),
        }

    def create_issue(
        self,
        title: str,
        team: str,
        description: str | None = None,
        assignee_id: str | None = None,
        project_id: str | None = None,
        priority: int | None = None,
        state_id: str | None = None,
        parent_id: str | None = None,
        label_ids: list[str] | None = None,
        estimate: int | None = None,
    ) -> dict[str, Any]:
        """Create a new issue in Linear.

        Args:
            title: The title of the issue.
            team: Team identifier - can be a UUID, team key (e.g., "NES"),
                or team name (e.g., "Neshq"). Will be resolved to UUID.
            description: Optional issue description in Markdown format.
            assignee_id: Optional UUID of the user to assign the issue to.
            project_id: Optional UUID of the project to add the issue to.
            priority: Optional priority level (0=No priority, 1=Urgent,
                2=High, 3=Normal, 4=Low).
            state_id: Optional UUID of the workflow state.
            parent_id: Optional UUID of the parent issue (for sub-issues).
            label_ids: Optional list of label UUIDs to apply to the issue.
            estimate: Optional fibonacci story-point estimate.

        Returns:
            Dictionary containing the created issue data:
            - id: Issue UUID
            - identifier: Issue identifier (e.g., "NES-123")
            - title: Issue title
            - url: Issue URL
            - branchName: Suggested branch name for the issue

        Raises:
            LinearClientError: If team not found, priority is invalid,
                or API call fails.
        """
        self._validate_priority(priority)
        self._validate_estimate(estimate)

        team_id = self._resolve_team_id(team)
        if team_id is None:
            raise LinearClientError("NOT_FOUND", f"Team not found: {team}")

        mutation = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      title
      url
      branchName
    }
  }
}
"""
        input_data: dict[str, Any] = {
            "title": title,
            "teamId": team_id,
        }

        if description is not None:
            input_data["description"] = description
        if assignee_id is not None:
            input_data["assigneeId"] = assignee_id
        if project_id is not None:
            input_data["projectId"] = project_id
        if priority is not None:
            input_data["priority"] = priority
        if state_id is not None:
            input_data["stateId"] = state_id
        if parent_id is not None:
            input_data["parentId"] = parent_id
        if label_ids:
            input_data["labelIds"] = label_ids
        if estimate is not None:
            input_data["estimate"] = estimate

        variables = {"input": input_data}
        result = self._run_graphql(mutation, variables)

        issue_create = result.get("data", {}).get("issueCreate", {})
        if not issue_create.get("success"):
            raise LinearClientError("API_ERROR", "Failed to create issue")

        issue = issue_create.get("issue", {})
        return {
            "id": issue.get("id"),
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "url": issue.get("url"),
            "branchName": issue.get("branchName"),
        }

    def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        assignee_id: str | None = None,
        project_id: str | None = None,
        priority: int | None = None,
        state_id: str | None = None,
        parent_id: str | None = None,
        label_ids: list[str] | None = None,
        estimate: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue in Linear.

        Args:
            issue_id: UUID or identifier of the issue to update.
            title: Optional new title for the issue.
            description: Optional new description in Markdown format.
            status: Optional state ID (backwards compatibility alias for state_id).
            assignee_id: Optional UUID of the user to assign the issue to.
            project_id: Optional UUID of the project to add the issue to.
            priority: Optional priority level (0=No priority, 1=Urgent,
                2=High, 3=Normal, 4=Low).
            state_id: Optional UUID of the workflow state.
            parent_id: Optional UUID of the parent issue (for sub-issues).
            label_ids: Optional list of label UUIDs to apply to the issue.
            estimate: Optional fibonacci story-point estimate.

        Returns:
            Dictionary containing the updated issue data:
            - id: Issue UUID
            - identifier: Issue identifier (e.g., "NES-123")
            - title: Issue title
            - url: Issue URL
            - updatedAt: ISO timestamp when issue was last updated

        Raises:
            LinearClientError: If no fields to update (NO_UPDATES), priority
                is invalid (INVALID_PRIORITY), or API call fails.
        """
        self._validate_priority(priority)
        self._validate_estimate(estimate)

        # Build input object with only provided fields
        input_data: dict[str, Any] = {}

        if title is not None:
            input_data["title"] = title
        if description is not None:
            input_data["description"] = description
        if assignee_id is not None:
            input_data["assigneeId"] = assignee_id
        if project_id is not None:
            input_data["projectId"] = project_id
        if priority is not None:
            input_data["priority"] = priority
        # status is backwards compat alias for state_id
        if state_id is not None:
            input_data["stateId"] = state_id
        elif status is not None:
            input_data["stateId"] = status
        if parent_id is not None:
            input_data["parentId"] = parent_id
        if label_ids is not None:
            input_data["labelIds"] = label_ids
        if estimate is not None:
            input_data["estimate"] = estimate

        if not input_data:
            raise LinearClientError(
                "NO_UPDATES",
                "At least one field must be provided to update an issue",
            )

        mutation = """
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue {
      id
      identifier
      title
      url
      updatedAt
    }
  }
}
"""
        variables = {"id": issue_id, "input": input_data}
        result = self._run_graphql(mutation, variables)

        issue_update = result.get("data", {}).get("issueUpdate", {})
        if not issue_update.get("success"):
            raise LinearClientError("API_ERROR", f"Failed to update issue: {issue_id}")

        issue = issue_update.get("issue", {})
        return {
            "id": issue.get("id"),
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "url": issue.get("url"),
            "updatedAt": issue.get("updatedAt"),
        }

    def list_comments(self, issue_id: str) -> dict[str, Any]:
        """List all comments for a Linear issue with pagination.

        First fetches the issue to get the UUID if an identifier is provided
        (e.g., "NES-123"), then retrieves all comments using pagination.

        Args:
            issue_id: Issue identifier (e.g., "NES-123") or UUID.

        Returns:
            Dictionary containing:
            - issueId: UUID of the issue
            - issueIdentifier: Issue identifier (e.g., "NES-123")
            - comments: List of comment dictionaries, each containing:
                - id: Comment UUID
                - body: Comment body text
                - createdAt: ISO timestamp when comment was created
                - updatedAt: ISO timestamp when comment was last updated
                - user: User info dict with id, name, email (or None)
            - totalCount: Total number of comments retrieved

        Raises:
            LinearClientError: If the issue is not found or API call fails.
        """
        all_comments: list[dict[str, Any]] = []
        cursor: str | None = None
        issue_uuid: str | None = None
        issue_identifier: str | None = None

        while True:
            query = """
query IssueComments($id: String!, $after: String) {
  issue(id: $id) {
    id
    identifier
    comments(first: 100, after: $after) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        body
        createdAt
        updatedAt
        user {
          id
          name
          email
        }
      }
    }
  }
}
"""
            variables: dict[str, Any] = {"id": issue_id}
            if cursor is not None:
                variables["after"] = cursor

            result = self._run_graphql(query, variables)
            issue = result.get("data", {}).get("issue")
            if not issue:
                raise LinearClientError("NOT_FOUND", f"Issue not found: {issue_id}")

            # Capture issue UUID and identifier on first iteration
            if issue_uuid is None:
                issue_uuid = issue.get("id")
                issue_identifier = issue.get("identifier")

            comments_data = issue.get("comments") or {}
            nodes = comments_data.get("nodes", [])

            for node in nodes:
                user_data = node.get("user")
                user_info: dict[str, Any] | None = None
                if user_data:
                    user_info = {
                        "id": user_data.get("id"),
                        "name": user_data.get("name"),
                        "email": user_data.get("email"),
                    }
                all_comments.append(
                    {
                        "id": node.get("id"),
                        "body": node.get("body"),
                        "createdAt": node.get("createdAt"),
                        "updatedAt": node.get("updatedAt"),
                        "user": user_info,
                    }
                )

            page_info = comments_data.get("pageInfo", {})
            next_cursor = page_info.get("endCursor")
            if not page_info.get("hasNextPage"):
                break
            if not next_cursor or next_cursor == cursor:
                raise LinearClientError(
                    "PAGINATION_ERROR",
                    "Pagination did not advance: missing or repeated endCursor",
                )
            cursor = next_cursor

        return {
            "issueId": issue_uuid,
            "issueIdentifier": issue_identifier,
            "comments": all_comments,
            "totalCount": len(all_comments),
        }

    def create_comment(self, issue_id: str, body: str) -> dict[str, Any]:
        """Create a comment on a Linear issue.

        Args:
            issue_id: Issue identifier (e.g., "NES-123") or UUID.
            body: The comment body in Markdown format.

        Returns:
            Dictionary containing the created comment data:
            - id: Comment UUID
            - body: Comment body text
            - createdAt: ISO timestamp when comment was created
            - issueId: UUID of the issue the comment belongs to
            - user: User info dict with id, name, email (or None)

        Raises:
            LinearClientError: If the issue is not found or API call fails.
        """
        mutation = """
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment {
      id
      body
      createdAt
      issue {
        id
      }
      user {
        id
        name
        email
      }
    }
  }
}
"""
        variables = {"input": {"issueId": issue_id, "body": body}}
        result = self._run_graphql(mutation, variables)

        comment_create = result.get("data", {}).get("commentCreate", {})
        if not (isinstance(comment_create, dict) and comment_create.get("success")):
            raise LinearClientError(
                "API_ERROR",
                f"Failed to create comment on issue: {issue_id}",
            )

        comment = comment_create.get("comment", {})
        user_data = comment.get("user")
        user_info: dict[str, Any] | None = None
        if user_data:
            user_info = {
                "id": user_data.get("id"),
                "name": user_data.get("name"),
                "email": user_data.get("email"),
            }

        return {
            "id": comment.get("id"),
            "body": comment.get("body"),
            "createdAt": comment.get("createdAt"),
            "issueId": comment.get("issue", {}).get("id"),
            "user": user_info,
        }

    def list_projects(
        self, team_id: str | None = None, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """List all projects in the Linear workspace.

        Fetches projects with cursor-based pagination to retrieve all results.
        Optionally filters by team.

        Args:
            team_id: Optional team UUID or team key/name to filter projects.
                If a team key or name is provided, it will be resolved to UUID.
            include_archived: Whether to include archived projects. Defaults to False.

        Returns:
            List of project dictionaries, each containing:
            - id: Project UUID
            - name: Project name
            - description: Project description
            - url: Project URL
            - slugId: Project slug ID
            - startedAt: ISO timestamp when project was started
            - completedAt: ISO timestamp when project was completed
            - targetDate: Target completion date
            - createdAt: ISO timestamp when project was created
            - updatedAt: ISO timestamp when project was last updated
            - archivedAt: ISO timestamp when archived (or None)
            - state: Project state
            - lead: Project lead (user info)
            - teams: List of teams associated with the project

        Raises:
            LinearClientError: If the API call fails or team not found.
        """
        resolved_team_id: str | None = None
        if team_id is not None:
            resolved_team_id = self._resolve_team_id(team_id)
            if resolved_team_id is None:
                raise LinearClientError("NOT_FOUND", f"Team not found: {team_id}")

        all_projects: list[dict[str, Any]] = []
        cursor: str | None = None

        query_with_team_filter = """
query($includeArchived: Boolean!, $teamId: ID!, $first: Int!, $after: String) {
  projects(
    first: $first
    includeArchived: $includeArchived
    filter: {accessibleTeams: {id: {eq: $teamId}}}
    after: $after
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      name
      description
      url
      slugId
      startedAt
      completedAt
      targetDate
      createdAt
      updatedAt
      archivedAt
      state
      lead {
        id
        name
        email
      }
      teams {
        nodes {
          id
          name
          key
        }
      }
    }
  }
}
"""
        query_without_team_filter = """
query($includeArchived: Boolean!, $first: Int!, $after: String) {
  projects(first: $first, includeArchived: $includeArchived, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      name
      description
      url
      slugId
      startedAt
      completedAt
      targetDate
      createdAt
      updatedAt
      archivedAt
      state
      lead {
        id
        name
        email
      }
      teams {
        nodes {
          id
          name
          key
        }
      }
    }
  }
}
"""
        query = (
            query_with_team_filter
            if resolved_team_id is not None
            else query_without_team_filter
        )

        while True:
            variables: dict[str, Any] = {
                "includeArchived": include_archived,
                "first": 100,
            }
            if resolved_team_id is not None:
                variables["teamId"] = resolved_team_id
            if cursor is not None:
                variables["after"] = cursor

            result = self._run_graphql(query, variables)
            projects_data = result.get("data", {}).get("projects", {})
            nodes = projects_data.get("nodes", [])
            # Flatten teams.nodes to teams for cleaner API
            for node in nodes:
                if "teams" in node and isinstance(node["teams"], dict):
                    node["teams"] = node["teams"].get("nodes", [])
            all_projects.extend(nodes)

            page_info = projects_data.get("pageInfo", {})
            next_cursor = page_info.get("endCursor")
            if not page_info.get("hasNextPage"):
                break
            if not next_cursor or next_cursor == cursor:
                raise LinearClientError(
                    "PAGINATION_ERROR",
                    "Pagination did not advance: missing or repeated endCursor",
                )
            cursor = next_cursor

        return all_projects

    def resolve_project_id(
        self,
        team: str,
        project: str,
        include_archived: bool = False,
    ) -> str:
        """Resolve a Linear project UUID or slugId within a team's visible projects."""
        token = project.strip()
        if not token:
            raise LinearClientError(
                "NOT_FOUND", "Project not found: empty project token"
            )

        projects = self.list_projects(team_id=team, include_archived=include_archived)
        matches: list[dict[str, Any]] = []
        if UUID_RE.match(token):
            matches = [p for p in projects if p.get("id") == token]
        elif "://" not in token and "/" not in token:
            matches = [p for p in projects if p.get("slugId") == token]

        if not matches:
            raise LinearClientError(
                "NOT_FOUND", f"Project not found for team {team}: {project}"
            )

        distinct_ids = {str(match.get("id")) for match in matches if match.get("id")}
        if not distinct_ids:
            raise LinearClientError(
                "NOT_FOUND", f"Project not found for team {team}: {project}"
            )
        if len(distinct_ids) > 1:
            raise LinearClientError(
                "AMBIGUOUS_PROJECT",
                f"Project token matches multiple projects for team {team}: {project}",
            )
        return next(iter(distinct_ids))

    def list_teams(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """List all teams in the Linear workspace.

        Fetches teams with cursor-based pagination to retrieve all results.
        Results are cached per include_archived value for the lifetime of the
        client instance to avoid redundant API calls.

        Args:
            include_archived: Whether to include archived teams. Defaults to False.

        Returns:
            List of team dictionaries, each containing:
            - id: Team UUID
            - name: Team name
            - key: Team key (e.g., "NES")
            - description: Team description
            - createdAt: ISO timestamp when team was created
            - updatedAt: ISO timestamp when team was last updated
            - archivedAt: ISO timestamp when archived (or None)
            - private: Whether the team is private
            - timezone: Team timezone

        Raises:
            LinearClientError: If the API call fails.
        """
        # Return cached result if available
        if include_archived in self._teams_cache:
            return self._teams_cache[include_archived]

        all_teams: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            query = """
query($includeArchived: Boolean!, $after: String) {
  teams(first: 100, includeArchived: $includeArchived, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      name
      key
      description
      createdAt
      updatedAt
      archivedAt
      private
      timezone
    }
  }
}
"""
            variables: dict[str, Any] = {"includeArchived": include_archived}
            if cursor is not None:
                variables["after"] = cursor

            result = self._run_graphql(query, variables)
            teams_data = result.get("data", {}).get("teams", {})
            nodes = teams_data.get("nodes", [])
            all_teams.extend(nodes)

            page_info = teams_data.get("pageInfo", {})
            next_cursor = page_info.get("endCursor")
            if not page_info.get("hasNextPage"):
                break
            if not next_cursor or next_cursor == cursor:
                raise LinearClientError(
                    "PAGINATION_ERROR",
                    "Pagination did not advance: missing or repeated endCursor",
                )
            cursor = next_cursor

        # Cache the result for future calls
        self._teams_cache[include_archived] = all_teams
        return all_teams

    def fetch_github_attachments(self, ticket_id: str) -> list[dict[str, Any]]:
        """Fetch all GitHub PR attachments for a ticket with pagination.

        Args:
            ticket_id: Linear ticket ID (e.g., "NES-123" or UUID).

        Returns:
            List of attachment dictionaries with url and title.

        Raises:
            LinearClientError: If the API call fails.
        """
        all_attachments: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            query = """
query($ticketId: String!, $after: String) {
  issue(id: $ticketId) {
    attachments(
      first: 100
      filter: {url: {contains: "github.com"}}
      after: $after
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        url
        title
      }
    }
  }
}
"""
            variables: dict[str, Any] = {"ticketId": ticket_id}
            if cursor is not None:
                variables["after"] = cursor

            result = self._run_graphql(query, variables)
            issue = result.get("data", {}).get("issue")
            if not issue:
                raise LinearClientError("NOT_FOUND", f"Ticket not found: {ticket_id}")

            attachments = issue.get("attachments", {})
            nodes = attachments.get("nodes", [])
            all_attachments.extend(nodes)

            page_info = attachments.get("pageInfo", {})
            next_cursor = page_info.get("endCursor")
            if not page_info.get("hasNextPage"):
                break
            if not next_cursor or next_cursor == cursor:
                raise LinearClientError(
                    "PAGINATION_ERROR",
                    "Pagination did not advance: missing or repeated endCursor",
                )
            cursor = next_cursor

        return all_attachments

    def get_done_state_id(self, team_id: str) -> str:
        """Get the 'Done' workflow state ID for a team.

        Args:
            team_id: Linear team ID (UUID).

        Returns:
            The workflow state ID for 'Done' state.

        Raises:
            LinearClientError: If no done state found or API call fails.
        """
        query = """
query($teamId: String!) {
  team(id: $teamId) {
    states(filter: {type: {eq: "completed"}}) {
      nodes {
        id
        name
        type
      }
    }
  }
}
"""
        variables = {"teamId": team_id}
        result = self._run_graphql(query, variables)
        team = result.get("data", {}).get("team")
        if not team:
            raise LinearClientError("NOT_FOUND", f"Team not found: {team_id}")
        states = team.get("states", {}).get("nodes", [])

        if states:
            state_id = states[0].get("id")
            if not state_id:
                raise LinearClientError(
                    "NOT_FOUND",
                    f"No 'Done' state ID found for team {team_id}",
                )
            return str(state_id)

        raise LinearClientError(
            "NOT_FOUND", f"No 'Done' state found for team {team_id}"
        )

    def list_workflow_states(self, team_id: str) -> list[dict[str, Any]]:
        """List the workflow states for a team."""
        query = """
query($teamId: String!) {
  team(id: $teamId) {
    states {
      nodes {
        id
        name
        type
      }
    }
  }
}
"""
        result = self._run_graphql(query, {"teamId": team_id})
        team = result.get("data", {}).get("team")
        if team is None:
            raise LinearClientError("NOT_FOUND", f"Team not found: {team_id}")
        if not isinstance(team, dict):
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Linear team response must be an object: {team_id}",
            )
        states_payload = team.get("states")
        if not isinstance(states_payload, dict):
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Workflow states missing for team: {team_id}",
            )
        states = states_payload.get("nodes", [])
        if not isinstance(states, list):
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Workflow states missing for team: {team_id}",
            )
        if not all(isinstance(state, dict) for state in states):
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Workflow state entries must be objects for team: {team_id}",
            )
        return cast(list[dict[str, Any]], states)

    def resolve_workflow_state_id_for_issue(
        self, issue_id: str, target_status: str
    ) -> dict[str, Any]:
        """Resolve a routine target status to a state ID on the issue's team."""
        normalized_target = target_status.strip()
        if not normalized_target:
            raise LinearClientError(
                "INVALID_INPUT",
                "target_status must not be blank",
            )
        if normalized_target not in ROUTINE_MANAGER_OWNED_STATES:
            allowed = ", ".join(sorted(ROUTINE_MANAGER_OWNED_STATES))
            raise LinearClientError(
                "INVALID_INPUT",
                f"target_status must be one of the routine manager-owned states: {allowed}",
            )

        query = """
query($issueId: String!) {
  issue(id: $issueId) {
    id
    identifier
    state {
      id
      name
      type
    }
    team {
      id
      key
      name
    }
  }
}
"""
        result = self._run_graphql(query, {"issueId": issue_id})
        issue = result.get("data", {}).get("issue")
        if issue is None:
            raise LinearClientError("NOT_FOUND", f"Issue not found: {issue_id}")
        if not isinstance(issue, dict):
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Linear issue response must be an object: {issue_id}",
            )

        team = issue.get("team") or {}
        if not isinstance(team, dict):
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Linear issue response field team must be an object: {issue_id}",
            )
        team_id = team.get("id")
        if not team_id:
            raise LinearClientError(
                "NOT_FOUND",
                f"Issue has no owning team: {issue_id}",
            )
        resolved_issue_id = issue.get("id")
        if not resolved_issue_id:
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Linear issue response missing required field: id for {issue_id}",
            )

        state = issue.get("state")
        if state is not None and not isinstance(state, dict):
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Linear issue response field state must be an object or null: {issue_id}",
            )
        state = state or {}
        if state and not state.get("id"):
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Linear issue response missing required field: state.id for {issue_id}",
            )
        matches = [
            workflow_state
            for workflow_state in self.list_workflow_states(str(team_id))
            if workflow_state.get("name") == normalized_target
        ]
        if not matches:
            raise LinearClientError(
                "NOT_FOUND",
                f"No workflow state named {normalized_target!r} on issue team {team_id}",
            )
        if len(matches) > 1:
            raise LinearClientError(
                "AMBIGUOUS_STATE",
                f"Multiple workflow states named {normalized_target!r} on issue team {team_id}",
            )
        target_state = matches[0]
        resolved_target_state_id = target_state.get("id")
        if not resolved_target_state_id:
            raise LinearClientError(
                "INVALID_RESPONSE",
                f"Workflow state missing required field: id for team {team_id}",
            )
        return {
            "issue_id": resolved_issue_id,
            "identifier": issue.get("identifier"),
            "team_id": team_id,
            "before_state_id": state.get("id"),
            "before_state_name": state.get("name"),
            "target_state_id": resolved_target_state_id,
            "target_state_name": target_state.get("name"),
        }

    def transition_issue(self, issue_id: str, target_status: str) -> dict[str, Any]:
        """Perform a routine manager-owned status transition."""
        resolved = self.resolve_workflow_state_id_for_issue(issue_id, target_status)
        target_state_id = resolved.get("target_state_id")
        if not target_state_id:
            raise LinearClientError(
                "NOT_FOUND",
                f"No workflow state ID resolved for issue: {issue_id}",
            )

        if resolved.get("before_state_id") != target_state_id:
            self.update_issue(
                issue_id=str(resolved["issue_id"]),
                state_id=str(target_state_id),
            )
        return {
            "issue_id": resolved["issue_id"],
            "identifier": resolved["identifier"],
            "beforeStatus": resolved["before_state_name"],
            "afterStatus": resolved["target_state_name"],
            "stateId": target_state_id,
        }

    def set_ticket_state(self, issue_uuid: str, state_id: str) -> dict[str, Any]:
        """Update a Linear ticket's state.

        Args:
            issue_uuid: Linear issue UUID (not the identifier like NES-123).
            state_id: Target workflow state ID.

        Returns:
            Dictionary containing the updated issue state:
            - stateName: The name of the new state (e.g., "Done")

        Raises:
            LinearClientError: If the API call fails or update is unsuccessful.
        """
        mutation = """
mutation($issueId: String!, $stateId: String!) {
  issueUpdate(id: $issueId, input: {stateId: $stateId}) {
    success
    issue {
      state {
        name
      }
    }
  }
}
"""
        variables = {"issueId": issue_uuid, "stateId": state_id}
        result = self._run_graphql(mutation, variables)
        issue_update = result.get("data", {}).get("issueUpdate", {})
        if not issue_update.get("success"):
            raise LinearClientError(
                "API_ERROR", f"Failed to update state for issue: {issue_uuid}"
            )
        return {"stateName": issue_update.get("issue", {}).get("state", {}).get("name")}

    def update_comment(self, comment_id: str, body: str) -> dict[str, Any]:
        """Update an existing comment on a Linear issue.

        Args:
            comment_id: Comment UUID to update.
            body: The new comment body in Markdown format.

        Returns:
            Dictionary containing the updated comment data:
            - id: Comment UUID
            - body: Comment body text
            - updatedAt: ISO timestamp when comment was updated

        Raises:
            LinearClientError: If the comment is not found or API call fails.
        """
        mutation = """
mutation CommentUpdate($id: String!, $input: CommentUpdateInput!) {
  commentUpdate(id: $id, input: $input) {
    success
    comment {
      id
      body
      updatedAt
    }
  }
}
"""
        variables = {"id": comment_id, "input": {"body": body}}
        result = self._run_graphql(mutation, variables)

        comment_update = result.get("data", {}).get("commentUpdate", {})
        if not (isinstance(comment_update, dict) and comment_update.get("success")):
            raise LinearClientError(
                "API_ERROR",
                f"Failed to update comment: {comment_id}",
            )

        comment = comment_update.get("comment", {})
        return {
            "id": comment.get("id"),
            "body": comment.get("body"),
            "updatedAt": comment.get("updatedAt"),
        }

    def get_comment_by_title(self, issue_id: str, title: str) -> dict[str, Any] | None:
        """Find a comment by its title (first line or # header).

        Searches through all comments on an issue and returns the first one
        whose body starts with the given title (with or without # prefix).

        Args:
            issue_id: Issue identifier (e.g., "NES-123") or UUID.
            title: The title to search for (e.g., "Architecture Design").

        Returns:
            Comment dictionary if found, None otherwise. Contains:
            - id: Comment UUID
            - body: Comment body text
            - createdAt: ISO timestamp
            - updatedAt: ISO timestamp

        Raises:
            LinearClientError: If the issue is not found or API call fails.
        """
        comments_result = self.list_comments(issue_id)
        comments = comments_result.get("comments", [])

        # Normalize title for matching
        title_normalized = title.strip().lstrip("#").strip()

        for comment in comments:
            body = comment.get("body", "")
            if not body:
                continue

            # Get first line and normalize
            first_line = body.split("\n")[0].strip().lstrip("#").strip()

            if first_line == title_normalized:
                return cast("dict[str, Any]", comment)

        return None

    def upsert_comment(self, issue_id: str, title: str, body: str) -> dict[str, Any]:
        r"""Create or update a comment by title.

        If a comment with the given title exists, updates it. Otherwise creates
        a new comment. The title should be the first line of the body.

        Args:
            issue_id: Issue identifier (e.g., "NES-123") or UUID.
            title: The title for the comment (will be matched against first line).
            body: The full comment body in Markdown format. Should start with
                the title (e.g., "# Architecture Design\n\n...").

        Returns:
            Dictionary containing the comment data:
            - id: Comment UUID
            - body: Comment body text
            - createdAt: ISO timestamp (for new comments)
            - updatedAt: ISO timestamp (for updated comments)
            - created: Boolean indicating if comment was newly created

        Raises:
            LinearClientError: If the issue is not found or API call fails.
        """
        existing = self.get_comment_by_title(issue_id, title)

        if existing:
            updated = self.update_comment(existing["id"], body)
            return {
                "id": updated["id"],
                "body": updated["body"],
                "updatedAt": updated["updatedAt"],
                "created": False,
            }
        else:
            created = self.create_comment(issue_id, body)
            return {
                "id": created["id"],
                "body": created["body"],
                "createdAt": created["createdAt"],
                "created": True,
            }

    def list_unresolved_comments(self, issue_id: str) -> dict[str, Any]:
        """List unresolved comments for a Linear issue with pagination.

        Fetches only comments that have not been resolved (resolvedAt is null).

        Args:
            issue_id: Issue identifier (e.g., "NES-123") or UUID.

        Returns:
            Dictionary containing:
            - issueId: UUID of the issue
            - issueIdentifier: Issue identifier (e.g., "NES-123")
            - comments: List of unresolved comment dictionaries, each containing:
                - id: Comment UUID
                - body: Comment body text
                - createdAt: ISO timestamp when comment was created
                - updatedAt: ISO timestamp when comment was last updated
                - user: User info dict with id, name, email (or None for system comments)
            - totalCount: Total number of unresolved comments retrieved

        Raises:
            LinearClientError: If the issue is not found or API call fails.
        """
        all_comments: list[dict[str, Any]] = []
        cursor: str | None = None
        issue_uuid: str | None = None
        issue_identifier: str | None = None

        while True:
            query = """
query IssueUnresolvedComments($id: String!, $after: String) {
  issue(id: $id) {
    id
    identifier
    comments(first: 100, after: $after) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        body
        createdAt
        updatedAt
        resolvedAt
        user {
          id
          name
          email
        }
      }
    }
  }
}
"""
            variables: dict[str, Any] = {"id": issue_id}
            if cursor is not None:
                variables["after"] = cursor

            result = self._run_graphql(query, variables)
            issue = result.get("data", {}).get("issue")
            if not issue:
                raise LinearClientError("NOT_FOUND", f"Issue not found: {issue_id}")

            # Capture issue UUID and identifier on first iteration
            if issue_uuid is None:
                issue_uuid = issue.get("id")
                issue_identifier = issue.get("identifier")

            comments_data = issue.get("comments") or {}
            nodes = comments_data.get("nodes", [])

            for node in nodes:
                # Skip resolved comments
                if node.get("resolvedAt") is not None:
                    continue

                user_data = node.get("user")
                user_info: dict[str, Any] | None = None
                if user_data:
                    user_info = {
                        "id": user_data.get("id"),
                        "name": user_data.get("name"),
                        "email": user_data.get("email"),
                    }
                all_comments.append(
                    {
                        "id": node.get("id"),
                        "body": node.get("body"),
                        "createdAt": node.get("createdAt"),
                        "updatedAt": node.get("updatedAt"),
                        "user": user_info,
                    }
                )

            page_info = comments_data.get("pageInfo", {})
            next_cursor = page_info.get("endCursor")
            if not page_info.get("hasNextPage"):
                break
            if not next_cursor or next_cursor == cursor:
                raise LinearClientError(
                    "PAGINATION_ERROR",
                    "Pagination did not advance: missing or repeated endCursor",
                )
            cursor = next_cursor

        return {
            "issueId": issue_uuid,
            "issueIdentifier": issue_identifier,
            "comments": all_comments,
            "totalCount": len(all_comments),
        }

    def search_issues(
        self,
        *,
        team_key: str | None = None,
        team_id: str | None = None,
        title_contains: str | None = None,
        title_starts_with: str | None = None,
        project: str | None = None,
        label_names: list[str] | None = None,
        include_archived: bool = False,
        first: int = 50,
    ) -> list[dict[str, Any]]:
        """Search issues by team, title, and labels in one request.

        Args:
            team_key: Team key or name to resolve before searching. Mutually
                exclusive with ``team_id``.
            team_id: Team UUID to use directly. Mutually exclusive with
                ``team_key``.
            title_contains: Case-insensitive title substring filter. Empty
                strings are treated as omitted.
            title_starts_with: Title prefix filter. Empty strings are treated
                as omitted.
            project: Optional project UUID or slugId resolved within the team.
            label_names: Label names resolved within the team to ID filters.
                Blank entries are ignored after trimming whitespace.
            include_archived: Whether archived issues are included.
            first: Maximum number of issues to return, from 1 through 100.

        Returns:
            A single page of issue dictionaries with flattened ``labels``.

        Raises:
            LinearClientError: ``INVALID_INPUT`` for invalid arguments,
                ``NOT_FOUND`` when a team key cannot be resolved,
                ``INVALID_RESPONSE`` for unreadable search collections or candidates, and
                ``API_ERROR``, ``PARSE_ERROR``, or ``GRAPHQL_ERROR`` propagated
                from the GraphQL transport.
        """
        if (team_key is None) == (team_id is None):
            raise LinearClientError(
                "INVALID_INPUT",
                "Exactly one of team_key or team_id must be provided",
            )
        if first < 1 or first > 100:
            raise LinearClientError(
                "INVALID_INPUT",
                "first must be between 1 and 100",
            )

        if team_key is not None:
            resolved_team_id = self._resolve_team_id(team_key)
            if resolved_team_id is None:
                raise LinearClientError("NOT_FOUND", f"Team not found: {team_key}")
            team_token = team_key
        else:
            resolved_team_id = team_id.strip()
            if not resolved_team_id:
                raise LinearClientError(
                    "INVALID_INPUT",
                    "team_id must not be empty",
                )
            team_token = resolved_team_id

        query = """query SearchIssues($filter: IssueFilter!, $first: Int!, $includeArchived: Boolean!) {
  issues(filter: $filter, first: $first, includeArchived: $includeArchived) {
    nodes {
      id
      identifier
      title
      url
      state {
        id
        name
        type
      }
      team {
        id
        key
        name
      }
      labels {
        nodes {
          id
          name
        }
      }
    }
  }
}
"""
        issue_filter: dict[str, Any] = {"team": {"id": {"eq": resolved_team_id}}}
        if title_contains:
            issue_filter.setdefault("title", {})["containsIgnoreCase"] = title_contains
        if title_starts_with:
            issue_filter.setdefault("title", {})["startsWith"] = title_starts_with
        if project:
            project_id = self.resolve_project_id(team_token, project)
            issue_filter["project"] = {"id": {"eq": project_id}}
        normalized_label_names = [
            name.strip() for name in label_names or [] if name.strip()
        ]
        if normalized_label_names:
            label_ids = self.resolve_label_ids(
                team_token,
                normalized_label_names,
                create_missing=False,
            )
            issue_filter["labels"] = {"id": {"in": label_ids}}

        result = self._run_graphql(
            query,
            {
                "filter": issue_filter,
                "first": first,
                "includeArchived": include_archived,
            },
        )
        nodes = _search_issue_nodes(result)

        issues: list[dict[str, Any]] = []
        for node in nodes:
            _validate_search_issue_identity(node)
            if "labels" not in node or node.get("labels") is None:
                identifier = node.get("identifier") or node.get("id") or "<unknown>"
                raise LinearClientError(
                    "INVALID_RESPONSE",
                    f"Linear issue response missing required field: labels for {identifier}",
                )
            labels = node.get("labels")
            if not isinstance(labels, dict):
                identifier = node.get("identifier") or node.get("id") or "<unknown>"
                raise LinearClientError(
                    "INVALID_RESPONSE",
                    f"Linear issue response field labels must be an object for {identifier}",
                )
            label_nodes = labels.get("nodes")
            if not isinstance(label_nodes, list):
                identifier = node.get("identifier") or node.get("id") or "<unknown>"
                raise LinearClientError(
                    "INVALID_RESPONSE",
                    f"Linear issue response missing required field: labels.nodes for {identifier}",
                )
            issues.append(
                {
                    "id": node.get("id"),
                    "identifier": node.get("identifier"),
                    "title": node.get("title"),
                    "url": node.get("url"),
                    "state": node.get("state"),
                    "team": node.get("team"),
                    "labels": label_nodes,
                }
            )
        return issues

    def list_labels(self, team: str) -> list[dict[str, Any]]:
        """List issue labels visible to a team.

        Returns labels owned by the team plus workspace-level labels
        (Linear treats workspace labels as visible from every team).

        Args:
            team: Team identifier (UUID, key, or name).

        Returns:
            List of dicts with keys ``id``, ``name``, ``color``,
            ``description``, ``team``. ``team`` is ``None`` for
            workspace-level labels.

        Raises:
            LinearClientError: If team not found or API call fails.
        """
        team_id = self._resolve_team_id(team)
        if team_id is None:
            raise LinearClientError("NOT_FOUND", f"Team not found: {team}")

        query = """
query LabelsForTeam($teamId: ID!, $first: Int!, $after: String) {
  issueLabels(
    filter: {or: [{team: {id: {eq: $teamId}}}, {team: {null: true}}]}
    first: $first
    after: $after
  ) {
    nodes {
      id
      name
      color
      description
      team { id key name }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""
        labels: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            result = self._run_graphql(
                query,
                {"teamId": team_id, "first": 50, "after": cursor},
            )
            data = result.get("data")
            if not isinstance(data, dict):
                raise LinearClientError(
                    "INVALID_RESPONSE", "Linear label response is missing data"
                )
            connection = data.get("issueLabels")
            if not isinstance(connection, dict):
                raise LinearClientError(
                    "INVALID_RESPONSE", "Linear label response is missing issueLabels"
                )
            nodes = connection.get("nodes")
            if not isinstance(nodes, list) or not all(
                isinstance(node, dict) for node in nodes
            ):
                raise LinearClientError(
                    "INVALID_RESPONSE", "Linear label response is missing issueLabels.nodes"
                )
            labels.extend(cast(list[dict[str, Any]], nodes))

            page_info = connection.get("pageInfo")
            if not isinstance(page_info, dict) or not isinstance(
                page_info.get("hasNextPage"), bool
            ):
                raise LinearClientError(
                    "PAGINATION_ERROR", "Linear label pagination metadata is malformed"
                )
            if not page_info["hasNextPage"]:
                return labels
            next_cursor = page_info.get("endCursor")
            if (
                not isinstance(next_cursor, str)
                or not next_cursor
                or next_cursor in seen_cursors
            ):
                raise LinearClientError(
                    "PAGINATION_ERROR",
                    "Pagination did not advance: missing or repeated endCursor",
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    def create_label(
        self,
        team: str,
        name: str,
        color: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new issue label scoped to a team.

        Args:
            team: Team identifier (UUID, key, or name).
            name: Label name. Must be unique within the team.
            color: Optional hex color (e.g. ``"#5e6ad2"``).
            description: Optional human-readable description.

        Returns:
            Dict with ``id``, ``name``, ``color``, ``description``.

        Raises:
            LinearClientError: If team not found or API call fails.
        """
        team_id = self._resolve_team_id(team)
        if team_id is None:
            raise LinearClientError("NOT_FOUND", f"Team not found: {team}")

        mutation = """
mutation IssueLabelCreate($input: IssueLabelCreateInput!) {
  issueLabelCreate(input: $input) {
    success
    issueLabel { id name color description }
  }
}
"""
        input_data: dict[str, Any] = {"name": name, "teamId": team_id}
        if color is not None:
            input_data["color"] = color
        if description is not None:
            input_data["description"] = description

        result = self._run_graphql(mutation, {"input": input_data})
        payload = result.get("data", {}).get("issueLabelCreate", {})
        if not payload.get("success"):
            raise LinearClientError("API_ERROR", f"Failed to create label: {name}")
        label = payload.get("issueLabel") or {}
        return cast(dict[str, Any], label)

    def resolve_label_ids(
        self,
        team: str,
        label_names: list[str],
        create_missing: bool = False,
    ) -> list[str]:
        """Resolve a list of label names to their UUIDs on a team.

        Args:
            team: Team identifier (UUID, key, or name).
            label_names: Label names to resolve (case-sensitive match).
            create_missing: If True, any name with no existing match is
                created via :meth:`create_label`. If False, missing
                labels raise ``LinearClientError("NOT_FOUND", ...)``.

        Returns:
            List of UUIDs in the same order as ``label_names``.
            Duplicate names in the input produce duplicate UUIDs.

        Raises:
            LinearClientError: If team not found, label not found and
                ``create_missing=False``, or API call fails.
        """
        if not label_names:
            return []
        labels_by_name: dict[str, dict[str, list[str]]] = {}
        for label in self.list_labels(team):
            name = label.get("name")
            label_id = label.get("id")
            if not name or not label_id:
                continue
            tier = "team" if label.get("team") else "workspace"
            labels_by_name.setdefault(name, {"team": [], "workspace": []})[tier].append(
                label_id
            )

        existing: dict[str, str] = {}
        for name, tiers in labels_by_name.items():
            chosen_tier = tiers["team"] or tiers["workspace"]
            if len(chosen_tier) > 1:
                raise LinearClientError(
                    "AMBIGUOUS_LABEL",
                    f"Label name is duplicated in the same tier on team {team}: {name}",
                )
            if chosen_tier:
                existing[name] = chosen_tier[0]
        resolved: list[str] = []
        for name in label_names:
            if name in existing:
                resolved.append(existing[name])
                continue
            if not create_missing:
                raise LinearClientError(
                    "NOT_FOUND",
                    f"Label not found on team {team}: {name}",
                )
            new_label = self.create_label(team, name)
            existing[name] = new_label["id"]
            resolved.append(new_label["id"])
        return resolved

    def apply_labels(
        self,
        issue_id: str,
        team: str,
        label_names: list[str],
        create_missing: bool = False,
        replace: bool = False,
    ) -> dict[str, Any]:
        """Apply (add or replace) labels on an existing issue.

        Args:
            issue_id: Issue identifier (e.g. ``"NES-128"``) or UUID.
            team: Team identifier used to scope label resolution and
                creation. Pass the team that owns the issue.
            label_names: Names to apply.
            create_missing: When ``True`` any unknown name is created.
            replace: When ``True`` the issue's labels are replaced with
                ``label_names``. When ``False`` (default) the named
                labels are merged with the issue's existing labels.

        Returns:
            Dict with the updated issue ``id`` and ``labels`` list.

        Raises:
            LinearClientError: If issue not found, team not found,
                label resolution fails, or API call fails.
        """
        team_id = self._resolve_team_id(team)
        if team_id is None:
            raise LinearClientError("NOT_FOUND", f"Team not found: {team}")

        label_query = """
query($id: String!) {
  issue(id: $id) {
    team { id key }
    labels { nodes { id } }
  }
}
"""
        label_result = self._run_graphql(label_query, {"id": issue_id})
        issue = (label_result.get("data") or {}).get("issue")
        if not isinstance(issue, dict) or not issue:
            raise LinearClientError("NOT_FOUND", f"Issue not found: {issue_id}")
        issue_team_id = (
            ((issue.get("team") or {}).get("id")) if isinstance(issue, dict) else None
        )
        if issue_team_id != team_id:
            raise LinearClientError(
                "INVALID_INPUT",
                f"Issue/team mismatch for {issue_id}: expected team {team}",
            )

        ids_to_apply = self.resolve_label_ids(team, label_names, create_missing)

        if replace:
            final_ids = list(dict.fromkeys(ids_to_apply))
        else:
            nodes = ((issue.get("labels") or {}).get("nodes")) or []
            current_ids = [n.get("id") for n in nodes if n.get("id")]
            final_ids = list(dict.fromkeys(current_ids + ids_to_apply))

        return self.update_issue(issue_id, label_ids=final_ids)


# Module-level thread-safe default client pattern
_client_lock = threading.Lock()
_default_client: LinearClient | None = None


def _get_default_client() -> LinearClient:
    """Get or create the default LinearClient instance.

    This is the canonical implementation for obtaining a module-level
    LinearClient instance. It uses double-checked locking to ensure
    thread-safety while minimizing lock contention.

    Returns:
        The default LinearClient instance.

    Raises:
        LinearClientError: If LINEAR_API_KEY environment variable is not set.
    """
    global _default_client
    if _default_client is None:
        with _client_lock:
            if _default_client is None:
                _default_client = LinearClient()
    return _default_client
