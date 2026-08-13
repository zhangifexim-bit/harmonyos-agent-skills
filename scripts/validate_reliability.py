#!/usr/bin/env python3
"""Validate reliability contracts without network access or third-party packages."""

from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "skills-manifest.json"
CASES_PATH = REPO_ROOT / "tests" / "evals" / "reliability-cases.json"
EVIDENCE_SCHEMA_PATH = REPO_ROOT / "schemas" / "evidence.schema.json"
ROUTING_PATH = REPO_ROOT / "docs" / "skill-routing.md"
REQUIRED_CASE_FIELDS = {
    "id",
    "skill",
    "scenario",
    "input",
    "expected_actions",
    "forbidden_actions",
    "expected_classification",
    "stop_conditions",
    "expected_next_action",
}
CLASSIFICATIONS = {"NODE", "SDK", "JAVA", "HVIGOR", "CONFIG", "COMPILE", "SIGNING", "VERIFY", "GIT", "OTHER"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
    seen: set[str] = set()
    scenario_to_skill: dict[str, str] = {}
    for index, case in enumerate(cases):
        label = case.get("id", f"case-{index}") if isinstance(case, dict) else f"case-{index}"
        if not isinstance(case, dict):
            errors.append(f"{label}: case must be an object")
            continue
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        extra = sorted(set(case) - REQUIRED_CASE_FIELDS)
        if missing or extra:
            errors.append(f"{label}: missing={missing}, extra={extra}")
            continue
        if label in seen:
            errors.append(f"{label}: duplicate id")
        seen.add(label)
        if case["skill"] not in graph:
            errors.append(f"{label}: unknown skill {case['skill']}")
        if case["expected_classification"] not in CLASSIFICATIONS:
            errors.append(f"{label}: invalid classification")
        for field in ("input", "expected_actions", "forbidden_actions", "stop_conditions"):
            if not isinstance(case[field], list) or (field != "stop_conditions" and not case[field]):
                errors.append(f"{label}: {field} must be a non-empty array")
            elif not all(isinstance(value, str) and value.strip() for value in case[field]):
                errors.append(f"{label}: {field} values must be non-empty strings")
        expected = {value.casefold().strip() for value in case["expected_actions"]}
        forbidden = {value.casefold().strip() for value in case["forbidden_actions"]}
        overlap = sorted(expected & forbidden)
        if overlap:
            errors.append(f"{label}: expected and forbidden actions overlap: {overlap}")
        scenario_key = case["scenario"].casefold().strip()
        routed = scenario_to_skill.setdefault(scenario_key, case["skill"])
        if routed != case["skill"]:
            errors.append(f"{label}: scenario routes to both {routed} and {case['skill']}")
        if not isinstance(case["expected_next_action"], str) or not case["expected_next_action"].strip():
            errors.append(f"{label}: expected_next_action must be a non-empty string")
    if len(cases) < 24:
        errors.append(f"reliability-cases.json: expected at least 24 cases, found {len(cases)}")
    return cases, errors


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


def validate_repository(repo_root: Path = REPO_ROOT) -> list[str]:
    _, manifest_errors = validate_manifest(repo_root)
    _, case_errors = validate_cases(repo_root)
    errors = manifest_errors + case_errors + validate_evidence_schema(repo_root) + validate_routing(repo_root)
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
    print(f"CONTRACT_EVAL_PASS: {len(cases)} cases; dependency DAG {len(graph)} nodes/{edge_count} edges; routing and evidence schema valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
