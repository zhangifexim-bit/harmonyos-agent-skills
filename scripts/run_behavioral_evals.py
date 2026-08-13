#!/usr/bin/env python3
"""Optional live-agent eval harness using synthetic, isolated workspaces.

The harness deliberately has no implicit paid/default runner. Supply a reviewed
non-interactive command template and --execute to make real agent calls.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = REPO_ROOT / "tests" / "evals" / "reliability-cases.json"
MANIFEST_PATH = REPO_ROOT / "skills-manifest.json"
ACTION_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


def canonical_action_id(value: str) -> str:
    """Convert a contract phrase into its stable machine action identifier."""
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


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
            "action_ids and stop_condition_ids must be arrays of canonical UPPER_SNAKE_CASE identifiers.",
            "next_action_id must be one canonical UPPER_SNAKE_CASE identifier.",
            "Do not include hidden reasoning or chain-of-thought.",
        ]
    )


def grade(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    raw_action_ids = response.get("action_ids", [])
    action_ids = raw_action_ids if isinstance(raw_action_ids, list) and all(isinstance(value, str) for value in raw_action_ids) else []
    raw_stop_ids = response.get("stop_condition_ids", [])
    stop_ids = raw_stop_ids if isinstance(raw_stop_ids, list) and all(isinstance(value, str) for value in raw_stop_ids) else []
    next_action_id = response.get("next_action_id") if isinstance(response.get("next_action_id"), str) else ""
    decision = str(response.get("final_decision", ""))
    expected_ids = [canonical_action_id(action) for action in case["expected_actions"]]
    forbidden_ids = [canonical_action_id(action) for action in case["forbidden_actions"]]
    expected_hits = [action_id for action_id in expected_ids if action_id in action_ids]
    expected_missing = [action_id for action_id in expected_ids if action_id not in action_ids]
    forbidden_hits = [action_id for action_id in forbidden_ids if action_id in action_ids]
    classification_ok = response.get("classification") == case["expected_classification"]
    stop_condition_ok = set(stop_ids) == set(case["stop_conditions"])
    expected_next_action_id = canonical_action_id(case["expected_next_action"])
    next_action_ok = next_action_id == expected_next_action_id
    identifiers_valid = (
        isinstance(raw_action_ids, list)
        and isinstance(raw_stop_ids, list)
        and len(action_ids) == len(set(action_ids))
        and len(stop_ids) == len(set(stop_ids))
        and all(ACTION_ID_PATTERN.fullmatch(value) for value in [*action_ids, *stop_ids, next_action_id])
    )
    return {
        "id": case["id"],
        "skill": case["skill"],
        "action_ids": action_ids,
        "classification": response.get("classification"),
        "expected_action_hits": expected_hits,
        "expected_action_missing": expected_missing,
        "forbidden_action_hit": forbidden_hits,
        "stop_condition_satisfied": stop_condition_ok,
        "stop_condition_ids": stop_ids,
        "next_action_satisfied": next_action_ok,
        "next_action_id": next_action_id,
        "identifiers_valid": identifiers_valid,
        "final_decision": decision,
        "status": "PASS" if identifiers_valid and classification_ok and not expected_missing and not forbidden_hits and stop_condition_ok and next_action_ok else "FAIL",
    }


def run_case(case: dict[str, Any], command_template: str, timeout: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="harmonyos-agent-eval-") as temporary:
        workspace = Path(temporary)
        skills_root = workspace / ".codex" / "skills"
        skills_root.mkdir(parents=True)
        for skill_name in dependency_closure(case["skill"]):
            shutil.copytree(REPO_ROOT / "skills" / skill_name, skills_root / skill_name)
        prompt_file = workspace / "prompt.txt"
        output_file = workspace / "response.json"
        prompt_file.write_text(build_prompt(case), encoding="utf-8")
        command = command_template.format(workspace=workspace, prompt_file=prompt_file, output_file=output_file)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(workspace / ".codex")
        completed = subprocess.run(
            shlex.split(command, posix=os.name != "nt"),
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            return {"id": case["id"], "skill": case["skill"], "status": "ERROR", "exit_code": completed.returncode}
        if not output_file.is_file():
            return {"id": case["id"], "skill": case["skill"], "status": "ERROR", "error": "runner did not create output_file"}
        return grade(case, json.loads(output_file.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-command", help="Reviewed command template with {workspace}, {prompt_file}, and {output_file}")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only the selected case id; repeatable")
    parser.add_argument("--output", type=Path, default=Path("behavioral-eval-results.json"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--execute", action="store_true", help="Acknowledge that real agent calls may consume account quota")
    args = parser.parse_args()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in cases if case["id"] in requested]
        missing = requested - {case["id"] for case in cases}
        if missing:
            parser.error(f"unknown case id(s): {sorted(missing)}")
    if not args.execute:
        print(f"LIVE_AGENT_EVAL_NOT_RUN: harness validated for {len(cases)} synthetic case(s); pass --execute and --runner-command to call an agent.")
        return 0
    if not args.runner_command:
        parser.error("--runner-command is required with --execute")
    results = [run_case(case, args.runner_command, args.timeout) for case in cases]
    summary = {
        "schema_version": "1.0",
        "cases_run": len(results),
        "passed": sum(result["status"] == "PASS" for result in results),
        "failed": sum(result["status"] == "FAIL" for result in results),
        "errors": sum(result["status"] == "ERROR" for result in results),
        "results": results,
    }
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}))
    return 0 if summary["failed"] == 0 and summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
