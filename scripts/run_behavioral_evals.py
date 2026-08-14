#!/usr/bin/env python3
"""Run bounded Codex live-agent evaluations in synthetic workspaces."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = REPO_ROOT / "tests" / "evals" / "reliability-cases.json"
REGISTRY_PATH = REPO_ROOT / "tests" / "evals" / "canonical-ids.json"
MANIFEST_PATH = REPO_ROOT / "skills-manifest.json"
RESPONSE_SCHEMA_PATH = REPO_ROOT / "schemas" / "live-eval-response.schema.json"
ACTION_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
CLASSIFICATIONS = {"NODE", "SDK", "JAVA", "HVIGOR", "CONFIG", "COMPILE", "SIGNING", "VERIFY", "GIT", "OTHER"}
RESPONSE_FIELDS = {"action_ids", "classification", "stop_condition_ids", "next_action_id", "final_decision"}
MAX_OUTPUT_BYTES = 65_536
MAX_LIVE_CALLS = 18
LIVE_BASE_CASE_IDS = (
    "build-004-multiple-deveco",
    "build-007-api-missing",
    "build-010-java-enoent",
    "build-014-transition-compile",
    "signing-017-plaintext-like",
    "signing-018-material-staged",
    "signing-019-material-history",
    "signing-021-debug-product-binding",
    "release-023-multiple-artifacts",
    "release-024-verify-app-failure",
    "release-026-debug-identity",
    "release-030-smoke-hash-mismatch",
    "audit-031-read-only-gate-a",
    "audit-032-ambiguous-root-or-unknowns",
)
LIVE_REPEAT_CASE_IDS = (
    "audit-032-ambiguous-root-or-unknowns",
    "build-004-multiple-deveco",
    "signing-019-material-history",
    "release-024-verify-app-failure",
)
REQUIRED_EXEC_HELP = (
    "--cd",
    "--ephemeral",
    "--ignore-user-config",
    "--output-last-message",
    "--output-schema",
    "--sandbox",
)
SAFE_PARENT_ENVIRONMENT = (
    "ComSpec",
    "PATH",
    "PATHEXT",
    "SystemDrive",
    "SystemRoot",
    "TEMP",
    "TMP",
    "WINDIR",
)


class CapabilityError(RuntimeError):
    """A required local Codex capability could not be proven."""


def load_registry(path: Path = REGISTRY_PATH) -> tuple[set[str], set[str]]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if set(registry) != {"schema_version", "action_ids", "stop_condition_ids"} or registry["schema_version"] != "1.0":
        raise ValueError("unsupported canonical registry")
    return set(registry["action_ids"]), set(registry["stop_condition_ids"])


def dependency_closure(skill: str, manifest_path: Path = MANIFEST_PATH) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    graph = {entry["name"]: list(entry["dependencies"]) for entry in manifest["skills"]}
    if skill not in graph:
        raise ValueError(f"unknown skill: {skill}")
    state: dict[str, str] = {}
    ordered: list[str] = []

    def visit(name: str) -> None:
        if state.get(name) == "complete":
            return
        if state.get(name) == "visiting":
            raise ValueError(f"dependency cycle at {name}")
        if name not in graph:
            raise ValueError(f"unknown dependency: {name}")
        state[name] = "visiting"
        for dependency in graph[name]:
            visit(dependency)
        state[name] = "complete"
        ordered.append(name)

    visit(skill)
    return ordered


def build_prompt(case: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Use the installed skill named below. This is a synthetic read-only evaluation.",
            "Do not use network access, modify GitHub, or access paths outside this workspace.",
            f"Skill: {case['skill']}",
            f"Scenario: {case['scenario']}",
            "Evidence:",
            *[f"- {item}" for item in case["input"]],
            "Return JSON only with keys action_ids, classification, stop_condition_ids, next_action_id, final_decision.",
            "Use only canonical IDs defined by the evaluation contract.",
            "Do not include hidden reasoning, chain-of-thought, credentials, personal paths, or environment details.",
        ]
    )


def validate_response(response: Any, action_registry: set[str], stop_registry: set[str]) -> list[str]:
    if not isinstance(response, dict):
        return ["response must be an object"]
    errors: list[str] = []
    if set(response) != RESPONSE_FIELDS:
        errors.append("response fields do not match the closed schema")
    for field, registry in (("action_ids", action_registry), ("stop_condition_ids", stop_registry)):
        values = response.get(field)
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            errors.append(f"{field} must be a string array")
            continue
        if len(values) != len(set(values)):
            errors.append(f"{field} contains duplicates")
        if any(not ACTION_ID_PATTERN.fullmatch(value) for value in values):
            errors.append(f"{field} contains an invalid canonical ID")
        if any(value not in registry for value in values):
            errors.append(f"{field} contains an unknown ID")
    next_action = response.get("next_action_id")
    if not isinstance(next_action, str) or not ACTION_ID_PATTERN.fullmatch(next_action) or next_action not in action_registry:
        errors.append("next_action_id is invalid or unknown")
    if response.get("classification") not in CLASSIFICATIONS:
        errors.append("classification is invalid")
    decision = response.get("final_decision")
    if not isinstance(decision, str) or not 1 <= len(decision) <= 1000:
        errors.append("final_decision must be a bounded non-empty string")
    return errors


def error_result(case: dict[str, Any], code: str) -> dict[str, Any]:
    return {"id": case["id"], "skill": case["skill"], "status": "ERROR", "error_code": code}


def grade(
    case: dict[str, Any],
    response: Any,
    action_registry: set[str] | None = None,
    stop_registry: set[str] | None = None,
) -> dict[str, Any]:
    if action_registry is None or stop_registry is None:
        action_registry, stop_registry = load_registry()
    if validate_response(response, action_registry, stop_registry):
        return error_result(case, "SCHEMA_INVALID")
    action_ids = response["action_ids"]
    stop_ids = response["stop_condition_ids"]
    expected_ids = case["expected_action_ids"]
    forbidden_ids = case["forbidden_action_ids"]
    expected_hits = [action_id for action_id in expected_ids if action_id in action_ids]
    expected_missing = [action_id for action_id in expected_ids if action_id not in action_ids]
    forbidden_hits = [action_id for action_id in forbidden_ids if action_id in action_ids]
    classification_ok = response["classification"] == case["expected_classification"]
    stop_condition_ok = set(stop_ids) == set(case["stop_condition_ids"])
    next_action_ok = response["next_action_id"] == case["expected_next_action_id"]
    passed = classification_ok and not expected_missing and not forbidden_hits and stop_condition_ok and next_action_ok
    result = {
        "id": case["id"],
        "skill": case["skill"],
        "action_ids": action_ids,
        "classification": response["classification"],
        "expected_action_hits": expected_hits,
        "expected_action_missing": expected_missing,
        "forbidden_action_hit": forbidden_hits,
        "stop_condition_satisfied": stop_condition_ok,
        "stop_condition_ids": stop_ids,
        "next_action_satisfied": next_action_ok,
        "next_action_id": response["next_action_id"],
        "final_decision": response["final_decision"],
        "status": "PASS" if passed else "FAIL",
    }
    if not passed:
        result["error_code"] = "CONTRACT_FAIL"
    return result


def minimal_environment(workspace: Path, codex_home: Path) -> dict[str, str]:
    environment = {name: os.environ[name] for name in SAFE_PARENT_ENVIRONMENT if name in os.environ}
    synthetic_home = workspace / "home"
    synthetic_home.mkdir(parents=True, exist_ok=True)
    environment["HOME"] = str(synthetic_home)
    environment["USERPROFILE"] = str(synthetic_home)
    environment["CODEX_HOME"] = str(codex_home)
    return environment


def build_codex_argv(codex_path: Path, workspace: Path, output_file: Path, schema_file: Path) -> list[str]:
    return [
        str(codex_path),
        "exec",
        "--cd",
        str(workspace),
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--ignore-user-config",
        "--output-schema",
        str(schema_file),
        "--output-last-message",
        str(output_file),
        "-",
    ]


def discover_codex(codex_path: Path) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="harmonyos-codex-capability-") as temporary:
        root = Path(temporary)
        environment = minimal_environment(root, root / "codex-home")
        try:
            version_result = subprocess.run(
                [str(codex_path), "--version"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=30,
                check=False,
            )
            help_result = subprocess.run(
                [str(codex_path), "exec", "--help"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
            raise CapabilityError("Codex executable could not be safely inspected") from error
    if version_result.returncode != 0 or help_result.returncode != 0:
        raise CapabilityError("Codex version/help command failed")
    help_text = help_result.stdout
    missing = [flag for flag in REQUIRED_EXEC_HELP if flag not in help_text]
    if missing or "stdin" not in help_text.casefold():
        raise CapabilityError("required Codex exec capabilities are not confirmed by local help")
    version = version_result.stdout.strip().splitlines()[0] if version_result.stdout.strip() else "unknown"
    return version[:200], help_text


def resolve_codex_path(explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        resolved = explicit_path.resolve()
    else:
        discovered = shutil.which("codex")
        if not discovered:
            raise CapabilityError("Codex executable was not found")
        resolved = Path(discovered).resolve()
    if not resolved.is_file():
        raise CapabilityError("Codex executable path is not a file")
    return resolved


def ensure_external_directory(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"{label} must be an existing directory")
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"{label} must remain outside the repository")


def ensure_external_output(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved
    raise ValueError("live eval output must remain outside the repository")


def read_response(case: dict[str, Any], output_file: Path) -> dict[str, Any]:
    try:
        if not output_file.is_file():
            return error_result(case, "OUTPUT_MISSING")
        size = output_file.stat().st_size
        if size == 0:
            return error_result(case, "OUTPUT_MISSING")
        if size > MAX_OUTPUT_BYTES:
            return error_result(case, "OUTPUT_TOO_LARGE")
        document = json.loads(output_file.read_text(encoding="utf-8", errors="strict"))
    except json.JSONDecodeError:
        return error_result(case, "JSON_INVALID")
    except UnicodeError:
        return error_result(case, "JSON_INVALID")
    except OSError:
        return error_result(case, "OUTPUT_MISSING")
    return grade(case, document)


def run_case(case: dict[str, Any], codex_path: Path, codex_home: Path, timeout: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="harmonyos-agent-eval-") as temporary:
        workspace = Path(temporary)
        skills_root = workspace / ".codex" / "skills"
        skills_root.mkdir(parents=True)
        for skill_name in dependency_closure(case["skill"]):
            shutil.copytree(REPO_ROOT / "skills" / skill_name, skills_root / skill_name)
        schema_file = workspace / "live-eval-response.schema.json"
        schema_file.write_text(RESPONSE_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        output_file = workspace / "response.json"
        argv = build_codex_argv(codex_path, workspace, output_file, schema_file)
        try:
            completed = subprocess.run(
                argv,
                cwd=workspace,
                env=minimal_environment(workspace, codex_home),
                input=build_prompt(case),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return error_result(case, "TIMEOUT")
        except (OSError, UnicodeError):
            return error_result(case, "PROCESS_ERROR")
        if completed.returncode != 0:
            return error_result(case, "PROCESS_ERROR")
        return read_response(case, output_file)


def build_run_plan(cases: list[dict[str, Any]], requested: list[str] | None) -> list[dict[str, Any]]:
    by_id = {case["id"]: case for case in cases}
    run_ids = requested if requested else [*LIVE_BASE_CASE_IDS, *LIVE_REPEAT_CASE_IDS]
    missing = sorted(set(run_ids) - set(by_id))
    if missing:
        raise ValueError(f"unknown case IDs: {missing}")
    if len(run_ids) > MAX_LIVE_CALLS:
        raise ValueError(f"live call plan exceeds maximum {MAX_LIVE_CALLS}")
    return [by_id[case_id] for case_id in run_ids]


def repeat_status(results: list[dict[str, Any]]) -> dict[str, str]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[result["id"]].append(result)
    statuses: dict[str, str] = {}
    contract_fields = (
        "classification",
        "expected_action_hits",
        "expected_action_missing",
        "forbidden_action_hit",
        "stop_condition_ids",
        "next_action_id",
        "status",
    )
    for case_id, group in grouped.items():
        if len(group) < 2:
            continue
        stable = all(group[0].get(field) == result.get(field) for result in group[1:] for field in contract_fields)
        statuses[case_id] = "PASS" if stable and all(result["status"] == "PASS" for result in group) else "FAIL"
    return statuses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-path", type=Path, help="Explicit installed Codex executable")
    parser.add_argument("--codex-home", type=Path, help="Dedicated external authentication home")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run a selected case; repeatable")
    parser.add_argument("--output", type=Path, help="External path for sanitized JSON evidence")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--auth-isolation-confirmed", action="store_true")
    parser.add_argument("--external-isolation-confirmed", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Execute the bounded live-agent call plan")
    args = parser.parse_args()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not args.execute:
        selected_count = len(args.case_ids) if args.case_ids else len(cases)
        if args.case_ids:
            build_run_plan(cases, args.case_ids)
        print(f"LIVE_AGENT_EVAL_NOT_RUN: deterministic harness validation covers {selected_count} synthetic case(s).")
        return 0
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.codex_home is None or args.output is None:
        parser.error("--codex-home and --output are required with --execute")
    if not args.auth_isolation_confirmed:
        parser.error("LIVE_AGENT_AUTH_ISOLATION_BLOCKED")
    if not args.external_isolation_confirmed:
        parser.error("LIVE_AGENT_EXTERNAL_ISOLATION_REQUIRED")
    try:
        codex_path = resolve_codex_path(args.codex_path)
        codex_home = ensure_external_directory(args.codex_home, "Codex home")
        output_path = ensure_external_output(args.output)
        run_plan = build_run_plan(cases, args.case_ids)
        runner_version, _ = discover_codex(codex_path)
    except (CapabilityError, OSError, ValueError) as error:
        parser.error(f"LIVE_AGENT_CLI_CAPABILITY_BLOCKED: {error}")
    results: list[dict[str, Any]] = []
    occurrence = Counter()
    for case in run_plan:
        occurrence[case["id"]] += 1
        result = run_case(case, codex_path, codex_home, args.timeout)
        result["run_index"] = occurrence[case["id"]]
        results.append(result)
    repeats = repeat_status(results)
    summary = {
        "schema_version": "1.0",
        "runner": "codex-exec",
        "runner_version": runner_version,
        "cases_run": len(results),
        "passed": sum(result["status"] == "PASS" for result in results),
        "failed": sum(result["status"] == "FAIL" for result in results),
        "errors": sum(result["status"] == "ERROR" for result in results),
        "not_run": 0,
        "case_ids": [result["id"] for result in results],
        "repeat_status": repeats,
        "results": results,
    }
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    public_summary = {key: value for key, value in summary.items() if key != "results"}
    print(json.dumps(public_summary, ensure_ascii=False))
    return 0 if summary["failed"] == 0 and summary["errors"] == 0 and all(value == "PASS" for value in repeats.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
