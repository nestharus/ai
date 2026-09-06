"""Render a captured get-issue envelope for the operator's bootstrap read.

Declared roles: parser, formatter, orchestration.
No client construction or ticket requests occur in this module.
"""

import json
import re
import sys
from pathlib import Path

import yaml


_LABEL = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?Estimate (Source|Rationale)"
    r"(?:\*\*)?:[ \t]*(?:\*\*)?[ \t]*(.*?)[ \t]*$",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_SOURCES = {"prototype-dossier", "layer-2-magnitude", "layer-3-slice", "backstop-spike", "missing"}


def _description_labels(description: str) -> dict[str, list[str]]:
    labels: dict[str, list[str]] = {"source": [], "rationale": []}
    fence = None
    for line in description.splitlines():
        marker = _FENCE.match(line)
        fence, is_fence = _fence_state(fence, marker, line)
        if is_fence or fence is not None:
            continue
        match = _LABEL.match(line)
        if match:
            labels[match[1].lower()].append(match[2])
    return labels


def _fence_state(fence, marker, line):
    if not marker:
        return fence, False
    token = marker[1]
    if fence is None:
        return token, True
    if token[0] == fence[0] and len(token) >= len(fence) and not line[marker.end():].strip():
        return None, True
    return fence, True


def _label_value(values: list[str], absent, label: str):
    if not values:
        return absent
    if len(set(values)) != 1 or not values[0]:
        raise ValueError(f"estimate-provenance-ambiguous: {label}={values!r}")
    return values[0]


def estimate_provenance(description: str) -> tuple[str, str | None]:
    labels = _description_labels(description)
    source = _label_value(labels["source"], "missing", "source")
    rationale = _label_value(labels["rationale"], None, "rationale")
    if source not in _SOURCES:
        raise ValueError(f"estimate-provenance-unrecognized: source={source!r}")
    return source, rationale


def render_ticket(envelope: dict) -> bytes:
    if envelope.get("ok") is not True or not isinstance(envelope.get("data"), dict):
        raise ValueError("get-issue did not return a success envelope")
    issue = envelope["data"]
    description = issue.get("description") or ""
    source, rationale = estimate_provenance(description)
    metadata = {
        "key": issue.get("identifier", ""),
        "summary": issue.get("title", ""),
        "status": (issue.get("state") or {}).get("name", ""),
        "parent": (issue.get("parent") or {}).get("identifier", ""),
        "labels": [label.get("name", "") for label in (issue.get("labels") or [])],
        "url": issue.get("url", ""),
        "story_point_estimate": issue.get("estimate"),
        "estimate_source": source,
        "estimate_rationale": rationale,
        "estimate_field": "estimate",
    }
    frontmatter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=False)
    return ("---\n" + frontmatter + "---\n").encode("utf-8") + description.encode("utf-8")


def main() -> int:
    try:
        rendered = render_ticket(json.load(sys.stdin))
        Path(sys.argv[1]).write_bytes(rendered)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError) as error:
        print(f"BLOCKED:ticket-read: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
