"""Command-line interface for Linear client operations.

This module provides simple CLI commands for common Linear operations,
intended to simplify usage in shell scripts and Claude command files.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import NoReturn

from .client import (
    LinearClient,
    LinearClientError,
    descriptions_match_after_linear_canonicalization,
)


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that outputs JSON errors to maintain consistent output format."""

    def error(self, message: str) -> NoReturn:
        """Output structured JSON error and exit with code 2."""
        print(
            json.dumps(
                {"ok": False, "error": {"code": "INVALID_INPUT", "message": message}}
            )
        )
        sys.exit(2)


def _read_utf8_file(path: str, label: str) -> str:
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as source:
            return source.read()
    except (OSError, UnicodeError) as error:
        raise LinearClientError(
            "INVALID_INPUT", f"Cannot read {label} file: {path}: {error}"
        ) from error


def get_issue(issue_id: str) -> None:
    """Fetch and print issue details as JSON."""
    client = LinearClient()
    issue = client.get_issue(issue_id)
    print(json.dumps({"ok": True, "data": issue}, indent=2))


def get_issue_description(issue_id: str) -> None:
    """Fetch and print only the issue description as plain text."""
    client = LinearClient()
    issue = client.get_issue(issue_id)
    print(issue.get("description") or "")


def verify_issue_description(issue_id: str, description_file: str) -> None:
    """Verify a local description against Linear's narrow canonicalization."""
    expected = _read_utf8_file(description_file, "description")
    actual = LinearClient().get_issue(issue_id).get("description")
    matches = isinstance(actual, str) and (
        descriptions_match_after_linear_canonicalization(expected, actual)
    )
    print(
        json.dumps(
            {
                "ok": matches,
                "data": {
                    "issue": issue_id,
                    "status": "MATCH" if matches else "MISMATCH",
                    "expectedSha256": hashlib.sha256(expected.encode()).hexdigest(),
                    "actualSha256": (
                        hashlib.sha256(actual.encode()).hexdigest()
                        if isinstance(actual, str)
                        else None
                    ),
                },
            },
            indent=2,
        )
    )
    if not matches:
        sys.exit(1)


def split_plans(issue_id: str, output_dir: str) -> None:
    """Split ticket description into individual plan files.

    Extracts plans from the ticket description (after the `---` separator)
    and writes each plan to a separate file in the output directory.

    Args:
        issue_id: The issue identifier (e.g., NES-24)
        output_dir: Directory to write plan files (e.g., .tmp/plans/NES-24)
    """
    import os
    import re

    client = LinearClient()
    issue = client.get_issue(issue_id)
    description = issue.get("description") or ""

    # Find the plan section after ---
    separator_match = re.search(r"^---\s*$", description, re.MULTILINE)
    if not separator_match:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "NO_PLAN",
                        "message": "No plan found (missing --- separator)",
                    },
                }
            )
        )
        sys.exit(1)

    plan_content = description[separator_match.end() :].strip()

    # Split on "### Plan N:" headers
    plan_pattern = re.compile(r"^### Plan \d+:", re.MULTILINE)
    matches = list(plan_pattern.finditer(plan_content))

    if not matches:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "NO_PLANS",
                        "message": "No plans found (no '### Plan N:' headers)",
                    },
                }
            )
        )
        sys.exit(1)

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    plans = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(plan_content)
        plan_text = plan_content[start:end].strip()

        # Extract plan title from header
        header_line = plan_text.split("\n")[0]
        plan_num = i + 1
        plan_file = os.path.join(output_dir, f"plan{plan_num}.md")

        with open(plan_file, "w", encoding="utf-8") as f:
            f.write(plan_text)

        plans.append({"file": plan_file, "header": header_line})

    print(
        json.dumps(
            {"ok": True, "data": {"plans": plans, "count": len(plans)}}, indent=2
        )
    )


def _split_values(values: list[str] | None) -> list[str] | None:
    """Normalize repeatable comma-delimited CLI values."""
    if not values:
        return None
    normalized = [part.strip() for value in values for part in value.split(",")]
    normalized = [part for part in normalized if part]
    return normalized or None


def list_projects(team: str | None = None, include_archived: bool = False) -> None:
    """List and print projects as JSON."""
    client = LinearClient()
    kwargs = {"team_id": team}
    if include_archived:
        kwargs["include_archived"] = include_archived
    projects = client.list_projects(**kwargs)
    print(json.dumps({"ok": True, "data": {"projects": projects}}, indent=2))


def list_teams() -> None:
    """List and print all teams as JSON."""
    client = LinearClient()
    teams = client.list_teams()
    print(json.dumps({"ok": True, "data": {"teams": teams}}, indent=2))


def list_comments(issue_id: str) -> None:
    """List and print comments on an issue as JSON."""
    client = LinearClient()
    result = client.list_comments(issue_id)
    print(json.dumps({"ok": True, "data": result}, indent=2))


def create_issue(
    team: str,
    title: str,
    description: str | None = None,
    project_id: str | None = None,
    labels: list[str] | None = None,
    create_missing_labels: bool = False,
    estimate: int | None = None,
    *,
    description_file: str | None = None,
) -> None:
    """Create a new issue and print result as JSON.

    When ``labels`` is supplied the names are resolved to UUIDs (creating
    them when ``create_missing_labels=True``) and applied at create-time.
    Resolution failures raise before the issue is created so we never
    produce a half-labeled ticket.
    """
    if description is not None and description_file is not None:
        raise LinearClientError(
            "INVALID_INPUT",
            "description and description_file are mutually exclusive",
        )
    if description_file is not None:
        description = _read_utf8_file(description_file, "description")
    client = LinearClient()
    resolved_project_id: str | None = None
    if project_id:
        resolved_project_id = client.resolve_project_id(team, project_id)
    label_ids: list[str] | None = None
    if labels:
        label_ids = client.resolve_label_ids(
            team, labels, create_missing=create_missing_labels
        )
    create_kwargs = {
        "team": team,
        "title": title,
        "description": description,
        "project_id": resolved_project_id,
        "label_ids": label_ids,
    }
    if estimate is not None:
        create_kwargs["estimate"] = estimate
    issue = client.create_issue(**create_kwargs)
    issue_id = issue.get("id") or issue.get("identifier")
    readback: dict[str, object] | None = None
    if description is not None or (labels and label_ids):
        if not issue_id:
            raise LinearClientError(
                "READBACK_FAILED",
                "Created issue response has no ID for required readback; do not retry creation",
            )
        readback = client.get_issue(issue_id)
    if description is not None and readback is not None:
        actual_description = readback.get("description")
        if not isinstance(actual_description, str) or not (
            descriptions_match_after_linear_canonicalization(
                description, actual_description
            )
        ):
            issue_identity = issue.get("identifier") or issue_id
            issue_url = issue.get("url") or readback.get("url") or "URL unavailable"
            raise LinearClientError(
                "DESCRIPTION_READBACK_MISMATCH",
                f"Created issue {issue_identity} at {issue_url}, but its description "
                "failed canonical readback; do not retry creation",
            )
    if labels and label_ids:
        if issue_id and readback is not None:
            readback_labels = readback.get("labels")
            if not isinstance(readback_labels, list):
                readback_labels = []
            readback_label_ids = {
                label.get("id")
                for label in readback_labels
                if isinstance(label, dict) and label.get("id")
            }
            if any(label_id not in readback_label_ids for label_id in label_ids):
                client.apply_labels(
                    issue_id=issue_id,
                    team=team,
                    label_names=labels,
                    create_missing=create_missing_labels,
                    replace=False,
                )
    print(json.dumps({"ok": True, "data": issue}, indent=2))


def update_issue(
    issue_id: str,
    description: str | None = None,
    description_file: str | None = None,
    estimate: int | None = None,
) -> None:
    """Update an issue and print result as JSON.

    Args:
        issue_id: The issue identifier (e.g., NES-24)
        description: New description text (mutually exclusive with
            description_file)
        description_file: Path to file containing new description
            (mutually exclusive with description)
        estimate: Optional story-point estimate.
    """
    if description is not None and description_file is not None:
        raise LinearClientError(
            "INVALID_INPUT",
            "description and description_file are mutually exclusive",
        )
    if description_file is not None:
        description = _read_utf8_file(description_file, "description")

    client = LinearClient()
    update_kwargs: dict[str, object] = {"issue_id": issue_id}
    if description is not None:
        update_kwargs["description"] = description
    if estimate is not None:
        update_kwargs["estimate"] = estimate
    issue = client.update_issue(**update_kwargs)
    print(json.dumps({"ok": True, "data": issue}, indent=2))


def transition_issue(issue_id: str, target_status: str) -> None:
    """Transition an issue to a routine manager-owned status."""
    client = LinearClient()
    result = client.transition_issue(
        issue_id=issue_id,
        target_status=target_status,
    )
    print(json.dumps({"ok": True, "data": result}, indent=2))


def create_comment(issue_id: str, body: str) -> None:
    """Create and print a comment."""
    client = LinearClient()
    comment = client.create_comment(issue_id=issue_id, body=body)
    print(json.dumps({"ok": True, "data": comment}, indent=2))


def get_comment(issue_id: str, title: str) -> None:
    """Get a comment by title and print result as JSON."""
    client = LinearClient()
    comment = client.get_comment_by_title(issue_id=issue_id, title=title)
    if comment:
        print(json.dumps({"ok": True, "data": comment}, indent=2))
    else:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"No comment with title '{title}' found",
                    },
                }
            )
        )
        sys.exit(1)


def upsert_comment(
    issue_id: str, title: str, body: str | None = None, body_file: str | None = None
) -> None:
    """Create or update a comment by title and print an ok/data JSON envelope.

    Uses client.upsert_comment and print(json.dumps({"ok": True, "data": comment})).

    Args:
        issue_id: The issue identifier (e.g., NES-24)
        title: The comment title to match/create
        body: Comment body text (mutually exclusive with body_file)
        body_file: Path to file containing comment body (mutually exclusive with body)
    """
    # Read body from file if provided
    if body_file:
        with open(body_file, encoding="utf-8") as f:
            body = f.read()

    if not body:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "INVALID_INPUT",
                        "message": "Either --body or --body-file must be provided",
                    },
                }
            )
        )
        sys.exit(2)

    client = LinearClient()
    comment = client.upsert_comment(issue_id=issue_id, title=title, body=body)
    print(json.dumps({"ok": True, "data": comment}, indent=2))


def list_labels(team: str) -> None:
    """List labels on a team."""
    client = LinearClient()
    labels = client.list_labels(team=team)
    print(json.dumps({"ok": True, "data": labels}, indent=2))


def create_label(
    team: str, name: str, color: str | None = None, description: str | None = None
) -> None:
    """Create a label on a team."""
    client = LinearClient()
    label = client.create_label(
        team=team, name=name, color=color, description=description
    )
    print(json.dumps({"ok": True, "data": label}, indent=2))


def apply_labels(
    issue_id: str,
    team: str,
    labels: list[str],
    create_missing: bool,
    replace: bool,
) -> None:
    """Apply (or replace) labels on an existing issue."""
    client = LinearClient()
    result = client.apply_labels(
        issue_id=issue_id,
        team=team,
        label_names=labels,
        create_missing=create_missing,
        replace=replace,
    )
    print(json.dumps({"ok": True, "data": result}, indent=2))


def search_issues(
    *,
    team_key: str | None = None,
    team_id: str | None = None,
    title_contains: str | None = None,
    title_starts_with: str | None = None,
    project: str | None = None,
    labels: list[str] | None = None,
    include_archived: bool = False,
    first: int = 50,
) -> None:
    """Search issues and print results as JSON."""
    client = LinearClient()
    kwargs = {
        "team_key": team_key,
        "team_id": team_id,
        "title_contains": title_contains,
        "title_starts_with": title_starts_with,
        "label_names": labels,
        "include_archived": include_archived,
        "first": first,
    }
    if project is not None:
        kwargs["project"] = project
    issues = client.search_issues(**kwargs)
    print(json.dumps({"ok": True, "data": issues}, indent=2))


def list_issues(
    *,
    team: str,
    project: str | None = None,
    labels: list[str] | None = None,
    include_archived: bool = False,
    first: int = 50,
) -> None:
    """List issues for a team and optional project/label tuple."""
    client = LinearClient()
    kwargs = {
        "team_key": team,
        "include_archived": include_archived,
        "first": first,
    }
    if project is not None or labels is not None:
        kwargs.update(
            {
                "team_id": None,
                "title_contains": None,
                "title_starts_with": None,
                "label_names": labels,
            }
        )
    if project is not None:
        kwargs["project"] = project
    issues = client.search_issues(
        **kwargs,
    )
    print(json.dumps({"ok": True, "data": issues}, indent=2))


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to appropriate command."""
    parser = JsonArgumentParser(
        description="CLI for Linear client operations",
        prog="linear",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # get-issue command
    get_issue_parser = subparsers.add_parser("get-issue", help="Fetch issue details")
    get_issue_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")

    # get-issue-description command
    get_issue_desc_parser = subparsers.add_parser(
        "get-issue-description", help="Fetch issue description as plain text"
    )
    get_issue_desc_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")

    verify_issue_desc_parser = subparsers.add_parser(
        "verify-issue-description",
        help="Compare a local description with Linear's stored Markdown",
    )
    verify_issue_desc_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")
    verify_issue_desc_parser.add_argument(
        "--description-file", required=True, help="Expected Markdown description file"
    )

    # split-plans command
    split_plans_parser = subparsers.add_parser(
        "split-plans", help="Split ticket plans into individual files"
    )
    split_plans_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")
    split_plans_parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write plan files (e.g., .tmp/plans/NES-24)",
    )

    # list-projects command
    list_projects_parser = subparsers.add_parser("list-projects", help="List projects")
    list_projects_parser.add_argument(
        "--team", help="Team key/name/UUID to scope projects"
    )
    list_projects_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived projects",
    )

    # list-teams command
    subparsers.add_parser("list-teams", help="List all teams")

    # list-comments command
    list_comments_parser = subparsers.add_parser(
        "list-comments", help="List comments on an issue"
    )
    list_comments_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")

    # create-issue command
    create_issue_parser = subparsers.add_parser(
        "create-issue", help="Create a new issue"
    )
    create_issue_parser.add_argument(
        "--team", required=True, help="Team identifier (UUID, key, or name)"
    )
    create_issue_parser.add_argument("--title", required=True, help="Issue title")
    create_description_group = create_issue_parser.add_mutually_exclusive_group()
    create_description_group.add_argument("--description", help="Issue description")
    create_description_group.add_argument(
        "--description-file",
        help="Path to an issue description file; preserves original line endings",
    )
    create_issue_parser.add_argument("--project", help="Project UUID or slugId")
    create_issue_parser.add_argument(
        "--estimate",
        type=int,
        help="Story-point estimate (allowed: 1, 2, 3, 5, 8, 13, 21, 40, 100)",
    )
    create_issue_parser.add_argument(
        "--label",
        action="append",
        help="Label name; repeatable and accepts comma-delimited values",
    )
    create_issue_parser.add_argument(
        "--create-missing-labels",
        action="store_true",
        help="Create any label name that does not yet exist on the team",
    )

    # update-issue command
    update_issue_parser = subparsers.add_parser(
        "update-issue", help="Update an issue description"
    )
    update_issue_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")
    update_issue_parser.add_argument("--description", help="New issue description")
    update_issue_parser.add_argument(
        "--description-file", help="Path to file containing new issue description"
    )
    update_issue_parser.add_argument(
        "--estimate",
        type=int,
        help="Story-point estimate (allowed: 1, 2, 3, 5, 8, 13, 21, 40, 100)",
    )

    # transition-issue command
    transition_issue_parser = subparsers.add_parser(
        "transition-issue",
        help="Transition an issue to a routine manager-owned status",
    )
    transition_issue_parser.add_argument("issue_id", help="Issue ID (e.g., ACR-130)")
    transition_issue_parser.add_argument(
        "--target-status",
        required=True,
        help="Target routine status (Todo, In Progress, or Done)",
    )

    # create-comment command
    create_comment_parser = subparsers.add_parser(
        "create-comment", help="Create a comment on an issue"
    )
    create_comment_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")
    create_comment_parser.add_argument("--body", required=True, help="Comment body")

    # get-comment command
    get_comment_parser = subparsers.add_parser(
        "get-comment", help="Get a comment by title"
    )
    get_comment_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")
    get_comment_parser.add_argument(
        "--title", required=True, help="Comment title to search for"
    )

    # search-issues command
    search_issues_parser = subparsers.add_parser(
        "search-issues",
        help="Search Linear issues by team, title, and labels",
    )
    search_issues_team_group = search_issues_parser.add_mutually_exclusive_group(
        required=True
    )
    search_issues_team_group.add_argument(
        "--team-key",
        help="Team key or name to resolve before searching",
    )
    search_issues_team_group.add_argument(
        "--team-id",
        help="Team UUID to search without team-resolution lookup",
    )
    search_issues_parser.add_argument(
        "--title-contains",
        help="Case-insensitive title fragment to match",
    )
    search_issues_parser.add_argument(
        "--title-starts-with",
        help="Title prefix to match",
    )
    search_issues_parser.add_argument(
        "--project",
        help="Project UUID or slugId to filter within the selected team",
    )
    search_issues_parser.add_argument(
        "--label",
        action="append",
        help="Label name filter; repeatable and accepts comma-delimited values",
    )
    search_issues_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived issues",
    )
    search_issues_parser.add_argument(
        "--first",
        type=int,
        default=50,
        help="Maximum issues to request (default: 50)",
    )

    # list-issues command
    list_issues_parser = subparsers.add_parser(
        "list-issues",
        help="List Linear issues by team with optional project and label filters",
    )
    list_issues_parser.add_argument(
        "--team", required=True, help="Team key, name, or UUID to list issues from"
    )
    list_issues_parser.add_argument(
        "--project",
        help="Project UUID or slugId to filter within the selected team",
    )
    list_issues_parser.add_argument(
        "--label",
        action="append",
        help="Label name filter; repeatable and accepts comma-delimited values",
    )
    list_issues_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived issues",
    )
    list_issues_parser.add_argument(
        "--first",
        type=int,
        default=50,
        help="Maximum issues to request, 1-100 (default: 50)",
    )

    # list-labels command
    list_labels_parser = subparsers.add_parser(
        "list-labels", help="List labels on a team"
    )
    list_labels_parser.add_argument(
        "--team", required=True, help="Team identifier (UUID, key, or name)"
    )

    # create-label command
    create_label_parser = subparsers.add_parser(
        "create-label", help="Create a label on a team"
    )
    create_label_parser.add_argument(
        "--team", required=True, help="Team identifier (UUID, key, or name)"
    )
    create_label_parser.add_argument("--name", required=True, help="Label name")
    create_label_parser.add_argument("--color", help="Hex color (e.g. #5e6ad2)")
    create_label_parser.add_argument("--description", help="Label description")

    # apply-labels command
    apply_labels_parser = subparsers.add_parser(
        "apply-labels", help="Apply (or replace) labels on an issue"
    )
    apply_labels_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")
    apply_labels_parser.add_argument(
        "--team",
        required=True,
        help="Team identifier (UUID, key, or name) used for label resolution / creation",
    )
    apply_labels_parser.add_argument(
        "--labels",
        required=True,
        help="Comma-separated label names (e.g. 'hardening,prereq')",
    )
    apply_labels_parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Create any label name that does not yet exist on the team",
    )
    apply_labels_parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the issue's labels (default merges with existing)",
    )

    # upsert-comment command
    upsert_comment_parser = subparsers.add_parser(
        "upsert-comment", help="Create or update a comment by title"
    )
    upsert_comment_parser.add_argument("issue_id", help="Issue ID (e.g., NES-24)")
    upsert_comment_parser.add_argument(
        "--title", required=True, help="Comment title to match/create"
    )
    upsert_comment_parser.add_argument("--body", help="Comment body")
    upsert_comment_parser.add_argument(
        "--body-file", help="Path to file containing comment body"
    )

    if argv and argv[0] == parser.prog:
        argv = argv[1:]
    args = parser.parse_args(argv)

    if not args.command:
        available_commands = ", ".join(subparsers.choices)
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "INVALID_INPUT",
                        "message": f"A command is required. Available commands: {available_commands}",
                    },
                }
            )
        )
        sys.exit(2)

    try:
        if args.command == "get-issue":
            get_issue(args.issue_id)
        elif args.command == "get-issue-description":
            get_issue_description(args.issue_id)
        elif args.command == "verify-issue-description":
            verify_issue_description(args.issue_id, args.description_file)
        elif args.command == "split-plans":
            split_plans(args.issue_id, args.output_dir)
        elif args.command == "list-projects":
            list_projects(team=args.team, include_archived=args.include_archived)
        elif args.command == "list-teams":
            list_teams()
        elif args.command == "list-comments":
            list_comments(args.issue_id)
        elif args.command == "create-issue":
            create_issue(
                team=args.team,
                title=args.title,
                description=args.description,
                description_file=args.description_file,
                project_id=args.project,
                labels=_split_values(args.label),
                create_missing_labels=args.create_missing_labels,
                estimate=args.estimate,
            )
        elif args.command == "update-issue":
            update_issue(
                issue_id=args.issue_id,
                description=args.description,
                description_file=args.description_file,
                estimate=args.estimate,
            )
        elif args.command == "transition-issue":
            transition_issue(
                issue_id=args.issue_id,
                target_status=args.target_status,
            )
        elif args.command == "create-comment":
            create_comment(issue_id=args.issue_id, body=args.body)
        elif args.command == "get-comment":
            get_comment(issue_id=args.issue_id, title=args.title)
        elif args.command == "upsert-comment":
            upsert_comment(
                issue_id=args.issue_id,
                title=args.title,
                body=args.body,
                body_file=args.body_file,
            )
        elif args.command == "search-issues":
            search_issues(
                team_key=args.team_key,
                team_id=args.team_id,
                title_contains=args.title_contains,
                title_starts_with=args.title_starts_with,
                project=args.project,
                labels=_split_values(args.label),
                include_archived=args.include_archived,
                first=args.first,
            )
        elif args.command == "list-issues":
            list_issues(
                team=args.team,
                project=args.project,
                labels=_split_values(args.label),
                include_archived=args.include_archived,
                first=args.first,
            )
        elif args.command == "list-labels":
            list_labels(team=args.team)
        elif args.command == "create-label":
            create_label(
                team=args.team,
                name=args.name,
                color=args.color,
                description=args.description,
            )
        elif args.command == "apply-labels":
            apply_labels(
                issue_id=args.issue_id,
                team=args.team,
                labels=[s.strip() for s in args.labels.split(",") if s.strip()],
                create_missing=args.create_missing,
                replace=args.replace,
            )
    except LinearClientError as e:
        print(
            json.dumps({"ok": False, "error": {"code": e.code, "message": e.message}})
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
