"""Execute the operator's documented commands against local retained fixtures."""

import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from clients.linear import cli
from clients.linear.client import LinearClient, LinearClientError
from clients.linear.create_reconciliation import reconcile_create


ROOT = Path(__file__).resolve().parents[1]


def _command(containing):
    text = (ROOT / "agents/linear-operator.md").read_text()
    return next(block for block in re.findall(r"```bash\n(.*?)```", text, re.S) if containing in block)


def _shell(command, env):
    return subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", command],
        cwd=ROOT, env={**os.environ, **env}, capture_output=True, text=True, timeout=20,
    )


def _render(tmp_path, description, *, exit_code=0, envelope_ok=True):
    envelope = {
        "ok": envelope_ok,
        "data": {
            "identifier": "ACR-34", "title": 'Improve: "export" # β 😀\u0085next',
            "state": {"name": "On: hold"}, "parent": {"identifier": "ACR-2"},
            "labels": [{"name": "yes"}, {"name": "quote's: [x]"}],
            "url": "https://linear.app/example/issue/ACR-34", "estimate": 5,
            "description": description,
        },
    }
    # Only get-issue is replaced. The actual documented renderer process runs.
    prefix = '''python3() {
if [[ "$1" == -m && "$2" == clients.linear.cli ]]; then
    printf '%s' "$fixture_envelope"
    return "$fixture_exit"
fi
PYTHONPATH="$fixture_root" command /usr/bin/python3 "$@"
}
'''
    output = tmp_path / "ticket with spaces.md"
    result = _shell(prefix + _command("if ISSUE_JSON="), {
        "fixture_envelope": json.dumps(envelope), "fixture_exit": str(exit_code),
        "fixture_root": str(ROOT), "issue_key": "ACR-34", "output_path": str(output),
    })
    return result, output, envelope["data"]


@pytest.mark.parametrize("provenance", [
    "",
    '**Estimate Source:** layer-3-slice\n**Estimate Rationale:** Three paths: "small".\n',
    '- Estimate Source: layer-3-slice\n- Estimate Rationale: Three paths: "small".\n',
])
def test_bootstrap_process_quotes_metadata_and_preserves_exact_body(tmp_path, provenance):
    body = '\r\n# Scope\r\n\r\n- β item\r\n```text\r\nEstimate Source: fiction\r\n```\r\n' + provenance + '\n\n'
    result, output, issue = _render(tmp_path, body)
    assert result.returncode == 0, result.stderr
    frontmatter, actual_body = output.read_bytes()[4:].split(b"\n---\n", 1)
    metadata = yaml.safe_load(frontmatter)
    assert metadata["summary"] == issue["title"]
    assert metadata["status"] == "On: hold"
    assert metadata["labels"] == ["yes", "quote's: [x]"]
    assert metadata["parent"] == "ACR-2"
    assert metadata["story_point_estimate"] == 5
    assert metadata["estimate_source"] == ("layer-3-slice" if provenance else "missing")
    assert metadata["estimate_rationale"] == ('Three paths: "small".' if provenance else None)
    assert actual_body == body.encode("utf-8")


@pytest.mark.parametrize("body,error", [
    ("Estimate Source: future-method\n", "future-method"),
    ("Estimate Source: prototype-dossier\nEstimate Source: backstop-spike\n", "ambiguous"),
    ("Estimate Rationale:\n", "ambiguous"),
])
def test_bootstrap_keeps_uncertain_provenance_out_of_a_success_artifact(tmp_path, body, error):
    result, output, _ = _render(tmp_path, body)
    assert result.returncode == 2
    assert error in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("exit_code,envelope_ok", [(7, True), (0, False)])
def test_bootstrap_does_not_render_failed_reads(tmp_path, exit_code, envelope_ok):
    result, output, _ = _render(tmp_path, "body", exit_code=exit_code, envelope_ok=envelope_ok)
    assert result.returncode == 2
    assert not output.exists()


def _argv(command, env):
    result = _shell('''python3() {
/usr/bin/python3 -c 'import json,sys;print(json.dumps(sys.argv[1:]))' "$@"
}
''' + command, env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("optional", [False, True])
def test_create_template_sends_optional_flags_in_one_cli_invocation(monkeypatch, tmp_path, optional):
    brief = tmp_path / "brief with spaces.md"
    brief.write_text("# Scope\nExact brief\n")
    args = _argv(_command("create_args=("), {
        "linear_team_key": "ACR", "summary": 'Title: "quoted"', "brief_path": str(brief),
        "resolved_project_id": "project-1" if optional else "",
        "labels": "one,two words" if optional else "", "estimate": "5" if optional else "",
        "create_missing_labels": "true" if optional else "false",
    })
    calls = []
    monkeypatch.setattr(cli, "create_issue", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr("sys.argv", ["linear", *args[2:]])
    cli.main()
    assert len(calls) == 1
    assert calls[0]["title"] == 'Title: "quoted"'
    assert calls[0]["estimate"] == (5 if optional else None)
    assert calls[0]["project_id"] == ("project-1" if optional else None)
    assert calls[0]["create_missing_labels"] is optional


@pytest.mark.parametrize("heading", ["PR Cross-link", "Estimate refinement"])
def test_upsert_retries_and_updated_body_keep_the_same_comment(monkeypatch, heading):
    client = LinearClient(api_key="local-fixture-only")
    comments = []
    creates = []

    def create(issue_id, body):
        comment = {"id": "comment-1", "body": body, "createdAt": "fixture"}
        comments.append(comment)
        creates.append(issue_id)
        return comment

    def update(comment_id, body):
        comments[0].update(body=body, updatedAt="fixture-update")
        return comments[0]

    monkeypatch.setattr(client, "list_comments", lambda _: {"comments": comments})
    monkeypatch.setattr(client, "create_comment", create)
    monkeypatch.setattr(client, "update_comment", update)
    if heading == "PR Cross-link":
        args = _argv(_command('--title "PR Cross-link"'), {})
        body = args[args.index("--body") + 1]
    else:
        body = "## Estimate refinement\n\nInherited: 3\nRefined: 5\nSource: layer-3-slice\nRationale: extra path."
    first = client.upsert_comment("ACR-34", heading, body)
    second = client.upsert_comment("ACR-34", heading, body)
    revised = body + "\nFurther detail."
    third = client.upsert_comment("ACR-34", heading, revised)
    fourth = client.upsert_comment("ACR-34", heading, revised)
    assert [first["created"], second["created"], third["created"], fourth["created"]] == [True, False, False, False]
    assert {result["id"] for result in (first, second, third, fourth)} == {"comment-1"}
    assert creates == ["ACR-34"]
    assert comments[0]["body"] == revised


def _issue(identifier, project="project-1", team="team-1", title="Exact title"):
    return {"id": identifier, "identifier": f"ACR-{identifier}", "title": title,
            "url": f"https://linear.app/example/issue/ACR-{identifier}",
            "team": {"id": team}, "project": {"id": project}, "description": "Same brief"}


def _reconcile_fixture(issues, *, project="project-slug"):
    calls = []

    def search(**kwargs):
        calls.append(kwargs)
        # Deliberately include stale/out-of-scope results to exercise readback checks.
        return [{"id": issue["id"], "title": issue["title"]} for issue in issues]

    client = SimpleNamespace(
        list_teams=lambda: [{"key": "ACR", "id": "team-1"}],
        resolve_project_id=lambda team, token: "project-1",
        search_issues=search,
        get_issue=lambda identifier: next(issue for issue in issues if issue["id"] == identifier),
    )
    return reconcile_create(client, "ACR", "Exact title", project), calls


def test_duplicate_reconciliation_requires_selected_project_and_exact_title():
    wanted = _issue("1")
    other = _issue("2", project="other-project")
    near = _issue("3", title="Exact title plus detail")
    result, calls = _reconcile_fixture([other, near, wanted])
    assert result["issue"] == wanted
    assert result["project_id"] == "project-1"
    assert calls == [{"team_id": "team-1", "title_contains": "Exact title", "project": "project-1",
                      "include_archived": True, "first": 100}]


def test_duplicate_reconciliation_does_not_reuse_other_project_or_team():
    result, _ = _reconcile_fixture([_issue("1", project="other"), _issue("2", team="other")])
    assert result["issue"] is None


@pytest.mark.parametrize("issues", [[_issue("1"), _issue("2")], [_issue(str(n)) for n in range(100)]])
def test_duplicate_reconciliation_blocks_ambiguous_or_full_page(issues):
    with pytest.raises(LinearClientError) as error:
        _reconcile_fixture(issues)
    assert error.value.code == "AMBIGUOUS_ISSUE"


def test_duplicate_reconciliation_without_project_keeps_team_scope():
    result, calls = _reconcile_fixture([_issue("1", project="other")], project=None)
    assert result["issue"]["id"] == "1"
    assert calls[0]["project"] is None


def test_duplicate_reconciliation_blocks_missing_project_identity():
    candidate = _issue("1")
    candidate["project"] = {}
    with pytest.raises(LinearClientError) as error:
        _reconcile_fixture([candidate])
    assert error.value.code == "INVALID_RESPONSE"
