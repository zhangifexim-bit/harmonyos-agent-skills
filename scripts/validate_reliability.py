#!/usr/bin/env python3
"""Validate reliability contracts without network access or third-party packages."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "skills-manifest.json"
CASES_PATH = REPO_ROOT / "tests" / "evals" / "reliability-cases.json"
CANONICAL_IDS_PATH = REPO_ROOT / "tests" / "evals" / "canonical-ids.json"
EVIDENCE_SCHEMA_PATH = REPO_ROOT / "schemas" / "evidence.schema.json"
LIVE_EVAL_SCHEMA_PATH = REPO_ROOT / "schemas" / "live-eval-response.schema.json"
ROUTING_PATH = REPO_ROOT / "docs" / "skill-routing.md"
REQUIRED_CASE_FIELDS = {
    "id",
    "skill",
    "scenario",
    "input",
    "expected_action_ids",
    "forbidden_action_ids",
    "expected_classification",
    "stop_condition_ids",
    "expected_next_action_id",
}
CLASSIFICATIONS = {"NODE", "SDK", "JAVA", "HVIGOR", "CONFIG", "COMPILE", "SIGNING", "VERIFY", "GIT", "OTHER"}
CANONICAL_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
PUBLICATION_STATES = ["SIGNING_READY", "BUILD_READY", "ARTIFACT_VERIFIED", "SMOKE_TESTED", "GIT_CLEAN", "READY_FOR_PUBLICATION"]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_canonical_registry(repo_root: Path = REPO_ROOT) -> tuple[set[str], set[str], list[str]]:
    errors: list[str] = []
    path = repo_root / "tests" / "evals" / "canonical-ids.json"
    try:
        registry = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        return set(), set(), [f"canonical-ids.json: unable to load registry: {error}"]
    expected_keys = {"schema_version", "action_ids", "stop_condition_ids"}
    if not isinstance(registry, dict) or set(registry) != expected_keys:
        return set(), set(), ["canonical-ids.json: root must contain exactly schema_version, action_ids, and stop_condition_ids"]
    if registry["schema_version"] != "1.0":
        errors.append("canonical-ids.json: schema_version must be 1.0")

    validated: dict[str, set[str]] = {}
    for field in ("action_ids", "stop_condition_ids"):
        values = registry[field]
        if not isinstance(values, list) or not values:
            errors.append(f"canonical-ids.json: {field} must be a non-empty array")
            validated[field] = set()
            continue
        if not all(isinstance(value, str) and CANONICAL_ID_PATTERN.fullmatch(value) for value in values):
            errors.append(f"canonical-ids.json: {field} contains an invalid canonical ID")
        if len(values) != len(set(values)):
            errors.append(f"canonical-ids.json: {field} contains duplicate IDs")
        validated[field] = {value for value in values if isinstance(value, str)}
    overlap = sorted(validated["action_ids"] & validated["stop_condition_ids"])
    if overlap:
        errors.append(f"canonical-ids.json: action and stop-condition registries overlap: {overlap}")
    return validated["action_ids"], validated["stop_condition_ids"], errors


def validate_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, list[str]], list[str]]:
    errors: list[str] = []
    manifest = load_json(repo_root / "skills-manifest.json")
    if manifest.get("schema_version") != "1.0":
        errors.append("skills-manifest.json: schema_version must be 1.0")
    entries = manifest.get("skills")
    if not isinstance(entries, list) or not entries:
        return {}, errors + ["skills-manifest.json: skills must be a non-empty array"]
    graph: dict[str, list[str]] = {}
    for entry in entries:
        if set(entry) != {"name", "path", "dependencies"}:
            errors.append(f"skills-manifest.json: invalid keys for {entry.get('name', '<unknown>')}")
            continue
        name = entry["name"]
        if name in graph:
            errors.append(f"skills-manifest.json: duplicate skill {name}")
        graph[name] = list(entry["dependencies"])
        expected_path = Path("skills") / name
        if Path(entry["path"]) != expected_path or not (repo_root / expected_path / "SKILL.md").is_file():
            errors.append(f"skills-manifest.json: invalid path for {name}")
    for name, dependencies in graph.items():
        for dependency in dependencies:
            if dependency not in graph:
                errors.append(f"skills-manifest.json: {name} depends on unknown skill {dependency}")
            if dependency == name:
                errors.append(f"skills-manifest.json: {name} depends on itself")
    errors.extend(validate_dag(graph))
    return graph, errors


def validate_dag(graph: dict[str, list[str]]) -> list[str]:
    indegree = {name: 0 for name in graph}
    dependents: dict[str, list[str]] = defaultdict(list)
    for name, dependencies in graph.items():
        indegree[name] = len(dependencies)
        for dependency in dependencies:
            if dependency in graph:
                dependents[dependency].append(name)
    queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
    visited: list[str] = []
    while queue:
        name = queue.popleft()
        visited.append(name)
        for dependent in dependents[name]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(visited) != len(graph):
        cyclic = sorted(name for name, degree in indegree.items() if degree > 0)
        return [f"skills-manifest.json: dependency graph contains a cycle involving {cyclic}"]
    return []


def validate_cases(repo_root: Path = REPO_ROOT) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    cases = load_json(repo_root / "tests" / "evals" / "reliability-cases.json")
    if not isinstance(cases, list):
        return [], ["reliability-cases.json: root must be an array"]
    graph, manifest_errors = validate_manifest(repo_root)
    errors.extend(manifest_errors)
    action_registry, stop_registry, registry_errors = validate_canonical_registry(repo_root)
    errors.extend(registry_errors)
    seen: set[str] = set()
    scenario_to_skill: dict[str, str] = {}
    for index, case in enumerate(cases):
        raw_id = case.get("id") if isinstance(case, dict) else None
        label = raw_id if isinstance(raw_id, str) and raw_id else f"case-{index}"
        if not isinstance(case, dict):
            errors.append(f"{label}: case must be an object")
            continue
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        extra = sorted(set(case) - REQUIRED_CASE_FIELDS)
        if missing or extra:
            errors.append(f"{label}: missing={missing}, extra={extra}")
            continue
        if not isinstance(case["id"], str) or not case["id"].strip():
            errors.append(f"{label}: id must be a non-empty string")
            continue
        if label in seen:
            errors.append(f"{label}: duplicate id")
        seen.add(label)
        if not isinstance(case["skill"], str) or case["skill"] not in graph:
            errors.append(f"{label}: unknown skill {case['skill']}")
        if not isinstance(case["expected_classification"], str) or case["expected_classification"] not in CLASSIFICATIONS:
            errors.append(f"{label}: invalid classification")
        arrays_valid = True
        for field in ("input", "expected_action_ids", "forbidden_action_ids", "stop_condition_ids"):
            if not isinstance(case[field], list) or (field != "stop_condition_ids" and not case[field]):
                errors.append(f"{label}: {field} must be a non-empty array")
                arrays_valid = False
            elif not all(isinstance(value, str) and value.strip() for value in case[field]):
                errors.append(f"{label}: {field} values must be non-empty strings")
                arrays_valid = False
            elif len(case[field]) != len(set(case[field])):
                errors.append(f"{label}: {field} contains duplicate IDs")
        next_valid = isinstance(case["expected_next_action_id"], str) and bool(CANONICAL_ID_PATTERN.fullmatch(case["expected_next_action_id"]))
        if not next_valid:
            errors.append(f"{label}: expected_next_action_id must be a canonical ID")
        if arrays_valid and next_valid:
            expected = set(case["expected_action_ids"])
            forbidden = set(case["forbidden_action_ids"])
            overlap = sorted(expected & forbidden)
            if overlap:
                errors.append(f"{label}: expected and forbidden actions overlap: {overlap}")
            unknown_actions = sorted((expected | forbidden | {case["expected_next_action_id"]}) - action_registry)
            if unknown_actions:
                errors.append(f"{label}: unknown action IDs: {unknown_actions}")
            unknown_stops = sorted(set(case["stop_condition_ids"]) - stop_registry)
            if unknown_stops:
                errors.append(f"{label}: unknown stop-condition IDs: {unknown_stops}")
            for field in ("expected_action_ids", "forbidden_action_ids", "stop_condition_ids"):
                if any(not CANONICAL_ID_PATTERN.fullmatch(value) for value in case[field]):
                    errors.append(f"{label}: {field} contains an invalid canonical ID")
        if not isinstance(case["scenario"], str) or not case["scenario"].strip():
            errors.append(f"{label}: scenario must be a non-empty string")
        elif isinstance(case["skill"], str):
            scenario_key = case["scenario"].casefold().strip()
            routed = scenario_to_skill.setdefault(scenario_key, case["skill"])
            if routed != case["skill"]:
                errors.append(f"{label}: scenario routes to both {routed} and {case['skill']}")
    if len(cases) < 24:
        errors.append(f"reliability-cases.json: expected at least 24 cases, found {len(cases)}")
    return cases, errors


def validate_live_eval_schema(repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    try:
        schema = load_json(repo_root / "schemas" / "live-eval-response.schema.json")
    except (OSError, json.JSONDecodeError) as error:
        return [f"live-eval-response.schema.json: unable to load schema: {error}"]
    fields = {"action_ids", "classification", "stop_condition_ids", "next_action_id", "final_decision"}
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        errors.append("live-eval-response.schema.json: root must be a closed object")
    if set(schema.get("required", [])) != fields or set(schema.get("properties", {})) != fields:
        errors.append("live-eval-response.schema.json: response fields do not match the live contract")
    properties = schema.get("properties", {})
    for field in ("action_ids", "stop_condition_ids"):
        rule = properties.get(field, {})
        if rule.get("type") != "array" or rule.get("uniqueItems") is not True or rule.get("items", {}).get("pattern") != CANONICAL_ID_PATTERN.pattern:
            errors.append(f"live-eval-response.schema.json: {field} must contain unique canonical IDs")
    if properties.get("next_action_id", {}).get("pattern") != CANONICAL_ID_PATTERN.pattern:
        errors.append("live-eval-response.schema.json: next_action_id must be canonical")
    if set(properties.get("classification", {}).get("enum", [])) != CLASSIFICATIONS:
        errors.append("live-eval-response.schema.json: classification enum is incomplete")
    final_rule = properties.get("final_decision", {})
    if final_rule.get("type") != "string" or final_rule.get("minLength") != 1 or not isinstance(final_rule.get("maxLength"), int):
        errors.append("live-eval-response.schema.json: final_decision must be a bounded non-empty string")
    return errors


def validate_evidence_schema(repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    schema = load_json(repo_root / "schemas" / "evidence.schema.json")
    required = set(schema.get("required", []))
    expected = {"schema_version", "skill", "status", "classification", "evidence", "mutations", "persistent_changes", "retry_performed", "next_action"}
    if schema.get("additionalProperties") is not False:
        errors.append("evidence.schema.json: additionalProperties must be false")
    if required != expected:
        errors.append("evidence.schema.json: required fields do not match evidence contract")
    if schema.get("properties", {}).get("schema_version", {}).get("const") != "1.0":
        errors.append("evidence.schema.json: schema_version must be fixed at 1.0")
    if "PASS" not in schema.get("properties", {}).get("status", {}).get("enum", []):
        errors.append("evidence.schema.json: status enum is incomplete")
    return errors


def validate_evidence_document(document: Any, repo_root: Path = REPO_ROOT) -> list[str]:
    """Validate the stable subset used by repository evidence handoffs."""
    schema = load_json(repo_root / "schemas" / "evidence.schema.json")
    if not isinstance(document, dict):
        return ["evidence document must be an object"]
    required = set(schema["required"])
    errors: list[str] = []
    missing = sorted(required - set(document))
    extra = sorted(set(document) - set(schema["properties"]))
    if missing:
        errors.append(f"evidence document missing fields: {missing}")
    if extra:
        errors.append(f"evidence document has unsupported fields: {extra}")
    for field in ("schema_version", "skill", "status", "classification"):
        rule = schema["properties"][field]
        if "const" in rule and document.get(field) != rule["const"]:
            errors.append(f"evidence document has invalid {field}")
        if "enum" in rule and document.get(field) not in rule["enum"]:
            errors.append(f"evidence document has invalid {field}")
    for field in ("persistent_changes", "retry_performed"):
        if field in document and not isinstance(document[field], bool):
            errors.append(f"evidence document {field} must be boolean")
    for field in ("evidence", "mutations"):
        if field in document and not isinstance(document[field], list):
            errors.append(f"evidence document {field} must be an array")
    if document.get("next_action") is not None and not isinstance(document.get("next_action"), str):
        errors.append("evidence document next_action must be string or null")
    for index, item in enumerate(document.get("evidence", []) if isinstance(document.get("evidence"), list) else []):
        if not isinstance(item, dict) or not {"kind", "result", "source"}.issubset(item):
            errors.append(f"evidence item {index} is invalid")
            continue
        if set(item) - {"kind", "result", "source", "path_redacted", "sha256"}:
            errors.append(f"evidence item {index} has unsupported fields")
        digest = item.get("sha256")
        if digest is not None and (not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)):
            errors.append(f"evidence item {index} has invalid sha256")
    return errors


def validate_routing(repo_root: Path = REPO_ROOT) -> list[str]:
    text = (repo_root / "docs" / "skill-routing.md").read_text(encoding="utf-8")
    errors: list[str] = []
    graph, manifest_errors = validate_manifest(repo_root)
    errors.extend(manifest_errors)
    for skill in graph:
        if f"`{skill}`" not in text:
            errors.append(f"docs/skill-routing.md: missing route for {skill}")
        skill_text = (repo_root / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        for heading in ("## Use when", "## Do not use when", "## Handoff"):
            if heading not in skill_text:
                errors.append(f"skills/{skill}/SKILL.md: missing {heading}")
    signing = (repo_root / "skills" / "harmonyos-release-signing" / "SKILL.md").read_text(encoding="utf-8")
    if "with `$harmonyos-release-check`" in signing:
        errors.append("harmonyos-release-signing: must not invoke harmonyos-release-check")
    release_check = (repo_root / "skills" / "harmonyos-release-check" / "SKILL.md").read_text(encoding="utf-8")
    if "at most once" not in release_check or "must not recurse" not in release_check:
        errors.append("harmonyos-release-check: missing once-only non-recursive signing rule")
    routing_cases = load_json(repo_root / "tests" / "evals" / "routing-cases.json")
    seen_prompts: set[str] = set()
    seen_ids: set[str] = set()
    for case in routing_cases:
        if set(case) != {"id", "prompt", "expected_skill"}:
            errors.append(f"routing case {case.get('id', '<unknown>')}: invalid fields")
            continue
        prompt = case["prompt"].casefold().strip()
        if case["id"] in seen_ids or prompt in seen_prompts:
            errors.append(f"routing case {case['id']}: duplicate id or prompt")
        seen_ids.add(case["id"])
        seen_prompts.add(prompt)
        if case["expected_skill"] not in graph:
            errors.append(f"routing case {case['id']}: unknown expected skill")
    if len(routing_cases) < 8:
        errors.append("routing-cases.json: expected at least eight typical prompts")
    return errors


def validate_publication_state_machine(repo_root: Path = REPO_ROOT) -> list[str]:
    expected = " -> ".join(PUBLICATION_STATES)
    errors: list[str] = []
    paths = [
        Path("skills/harmonyos-release-check/SKILL.md"),
        Path("skills/harmonyos-release-check/references/release-gate.md"),
        Path("docs/architecture.md"),
    ]
    for relative in paths:
        text = (repo_root / relative).read_text(encoding="utf-8")
        if expected not in text:
            errors.append(f"{relative.as_posix()}: publication state order must be {expected}")
        if "BUILD_READY -> SIGNING_READY" in text:
            errors.append(f"{relative.as_posix()}: contains obsolete build-before-signing order")
    signing = (repo_root / "skills" / "harmonyos-release-signing" / "SKILL.md").read_text(encoding="utf-8")
    if "Do not run formal `assembleApp`" not in signing or "Run the project's Release build" in signing:
        errors.append("harmonyos-release-signing: must not run the formal Release build")
    release_check = (repo_root / "skills" / "harmonyos-release-check" / "SKILL.md").read_text(encoding="utf-8")
    if "only release orchestrator" not in release_check.casefold() or "assembleApp" not in release_check:
        errors.append("harmonyos-release-check: must be the sole formal Release build orchestrator")
    folded_release_check = release_check.casefold()
    required_preflight = ("correct repository root", "intended head", "tracked and staged scope", "credential boundary")
    if "before entering `signing_ready`" not in folded_release_check or any(item not in folded_release_check for item in required_preflight):
        errors.append("harmonyos-release-check: missing distinct pre-SIGNING_READY Git preflight contract")
    if "does not replace the later `GIT_CLEAN`" not in release_check:
        errors.append("harmonyos-release-check: preflight must remain distinct from final GIT_CLEAN")
    condition = "`PUBLIC_IDENTITY_POLICY_PASS` is a required named condition after `GIT_CLEAN` and before `READY_FOR_PUBLICATION`"
    if condition not in release_check:
        errors.append("harmonyos-release-check: publication identity condition is missing or misplaced")
    gate_reference = (repo_root / "skills" / "harmonyos-release-check" / "references" / "release-gate.md").read_text(encoding="utf-8")
    architecture = (repo_root / "docs" / "architecture.md").read_text(encoding="utf-8")
    for relative, text in (("release-gate.md", gate_reference), ("docs/architecture.md", architecture)):
        if "`PUBLIC_IDENTITY_POLICY_PASS`" not in text or "seventh state" not in text:
            errors.append(f"{relative}: publication identity named condition is incomplete")
    signing_sections = {
        heading: signing.split(heading, 1)[1].split("\n## ", 1)[0]
        for heading in ("## Workflow", "## Output contract", "## Validation")
        if heading in signing
    }
    if len(signing_sections) != 3:
        errors.append("harmonyos-release-signing: Workflow, Output contract, and Validation are required")
    elif "SIGNING_READY" not in signing_sections["## Workflow"]:
        errors.append("harmonyos-release-signing: Workflow must terminate at SIGNING_READY")
    for heading in ("## Output contract", "## Validation"):
        if heading in signing_sections and not all(term in signing_sections[heading] for term in ("formal", "final APP", "smoke")):
            errors.append(f"harmonyos-release-signing: {heading[3:]} must exclude downstream build/verification/smoke gates")
    return errors


def validate_repository(repo_root: Path = REPO_ROOT) -> list[str]:
    _, manifest_errors = validate_manifest(repo_root)
    _, case_errors = validate_cases(repo_root)
    errors = manifest_errors + case_errors + validate_evidence_schema(repo_root) + validate_live_eval_schema(repo_root) + validate_routing(repo_root) + validate_publication_state_machine(repo_root)
    return sorted(set(errors))


def main() -> int:
    errors = validate_repository()
    if errors:
        print(f"Reliability validation failed with {len(errors)} error(s):")
        for error in errors:
            print(f"- {error}")
        return 1
    cases, _ = validate_cases()
    graph, _ = validate_manifest()
    edge_count = sum(len(dependencies) for dependencies in graph.values())
    print(f"CONTRACT_EVAL_PASS: {len(cases)} cases; dependency DAG {len(graph)} nodes/{edge_count} edges; routing, state machine, canonical registry, and evidence schemas valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
