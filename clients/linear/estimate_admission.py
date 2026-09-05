"""Guard the Linear operator's estimate and refinement-note CLI operations.

The operator procedure supplies its already governing definition. This helper
validates that definition's contract; it does not authenticate path arguments
against runner state or impose policy on independent generic CLI invocations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from . import cli
from .client import LinearClientError


_CONTRACT_SECTION = re.compile(r"(?ms)^## Contract\s*$\n(.*?)(?=^##\s|\Z)")
_YAML_FENCE = re.compile(r"(?ms)^```ya?ml\s*$\n(.*?)^```\s*$")
_METADATA = {"source", "model", "description"}


class _UniqueLoader(yaml.SafeLoader):
    def _unique_key(self, node: yaml.Node, existing: dict, deep: bool) -> str:
        key = self.construct_object(node, deep=deep)
        if not isinstance(key, str) or key in existing:
            raise ValueError("contract mapping keys must be unique strings")
        return key

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self._unique_key(key_node, result, deep)
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _parse_contract(text: str) -> dict[str, Any]:
    contract = yaml.load(text, Loader=_UniqueLoader)
    if (
        not isinstance(contract, dict)
        or contract.get("schema") != "operator-contract-v1"
    ):
        raise ValueError("contract schema must be operator-contract-v1")
    return contract


def _embedded_contract(text: str) -> dict[str, Any] | None:
    sections = _CONTRACT_SECTION.findall(text)
    if not sections:
        return None
    if len(sections) != 1:
        raise ValueError("definition must have one Contract section")
    fences = _YAML_FENCE.findall(sections[0])
    if len(fences) != 1:
        raise ValueError("Contract section must have one YAML block")
    return _parse_contract(fences[0])


def _source_path(value: Any, root: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("contract source path must be non-blank")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve(strict=True)


def _required_embedded(text: str) -> dict[str, Any]:
    embedded = _embedded_contract(text)
    if embedded is None:
        raise ValueError("selected definition has no contract")
    return embedded


def _selected_contract(definition: Path) -> dict[str, Any]:
    text = definition.read_text(encoding="utf-8")
    root = definition.parent.parent
    sidecar = root / "contracts" / "operators" / f"{definition.stem}.yaml"
    try:
        sidecar.lstat()
    except FileNotFoundError:
        return _required_embedded(text)
    selected = _parse_contract(sidecar.read_text(encoding="utf-8"))
    if "source" in selected and _source_path(selected["source"], root) != definition:
        raise ValueError("sidecar source does not match the governing definition")
    embedded = _embedded_contract(text)
    projected = {key: value for key, value in selected.items() if key not in _METADATA}
    if embedded is not None and json.dumps(projected, sort_keys=True) != json.dumps(
        embedded, sort_keys=True
    ):
        raise ValueError("sidecar and embedded contracts disagree")
    return selected


def _contract_chain(
    definition: Path, seen: frozenset[Path] = frozenset()
) -> list[dict[str, Any]]:
    definition = definition.resolve(strict=True)
    if definition in seen:
        raise ValueError("cyclic contract inheritance")
    selected = _selected_contract(definition)
    if "inherits" not in selected and "base_procedure" not in selected:
        return [selected]
    root = definition.parent.parent
    inherited = _source_path(selected.get("inherits"), root)
    if inherited != _source_path(selected.get("base_procedure"), root):
        raise ValueError("inherits and base_procedure must name the same definition")
    return [selected, *_contract_chain(inherited, seen | {definition})]


def _capabilities(contract: dict[str, Any], field: str) -> list[Any]:
    values = contract.get(field, [])
    if not isinstance(values, list):
        raise ValueError("contract capabilities must be lists")
    return values


def _legacy_capability(contracts: list[dict[str, Any]]) -> bool:
    outputs = []
    effects = []
    for contract in contracts:
        outputs.extend(_capabilities(contract, "outputs"))
        effects.extend(_capabilities(contract, "side_effects"))
    has_task = any(
        isinstance(output, dict) and output.get("task") == "update-estimate"
        for output in outputs
    )
    return has_task and "linear-update-estimate" in effects


def _admission(definition: Path) -> tuple[bool, str]:
    if not definition.is_absolute():
        raise ValueError("governing definition path must be absolute")
    contracts = _contract_chain(definition)
    selected = contracts[0]
    if "estimate_mutation_enabled" not in selected:
        return _legacy_capability(contracts), "unresolved"
    policy = selected["estimate_mutation_enabled"]
    if type(policy) is not bool:
        raise ValueError("estimate_mutation_enabled must be a YAML boolean")
    return policy, "disabled"


def require_estimate_admission(definition: Path) -> None:
    """Refuse invalid, disabled or unresolved selected policy before a CLI call."""
    try:
        admitted, reason = _admission(definition)
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError) as error:
        raise LinearClientError(
            "estimate-mutation-policy-invalid", str(error)
        ) from error
    if not admitted:
        raise LinearClientError(
            f"estimate-mutation-policy-{reason}",
            "Estimate and refinement note are not admitted",
        )


def main(argv: list[str] | None = None) -> None:
    parser = cli.JsonArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("operation", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    operation = args.operation[1:] if args.operation[:1] == ["--"] else args.operation
    if not operation or operation[0] not in {
        "update-issue", "create-comment", "upsert-comment"
    }:
        parser.error("expected an estimate update or refinement-note CLI operation")
    try:
        require_estimate_admission(args.definition)
    except LinearClientError as error:
        print(json.dumps({
            "ok": False,
            "error": {"code": error.code, "message": error.message},
        }))
        sys.exit(1)
    cli.main(operation)


if __name__ == "__main__":
    main()
