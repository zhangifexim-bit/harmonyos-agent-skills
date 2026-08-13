#!/usr/bin/env python3
"""Optional live-agent eval harness using synthetic, isolated workspaces.

The harness deliberately has no implicit paid/default runner. Supply a reviewed
non-interactive command template and --execute to make real agent calls.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = REPO_ROOT / "tests" / "evals" / "reliability-cases.json"


def build_prompt(case: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Use the installed skill named below. This is a synthetic read-only evaluation.",
            "Do not use network access, modify GitHub, or access paths outside this workspace.",
            f"Skill: {case['skill']}",
            f"Scenario: {case['scenario']}",
            "Evidence:",
            *[f"- {item}" for item in case["input"]],
            "Return JSON only with keys selected_action, classification, final_decision.",
            "Do not include hidden reasoning or chain-of-thought.",
        ]
    )


def grade(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    selected = str(response.get("selected_action", ""))
    decision = str(response.get("final_decision", ""))
    combined = f"{selected}\n{decision}".casefold()
    expected_hits = [action for action in case["expected_actions"] if action.casefold() in combined]
    expected_missing = [action for action in case["expected_actions"] if action.casefold() not in combined]
    forbidden_hits = [action for action in case["forbidden_actions"] if action.casefold() in combined]
    classification_ok = response.get("classification") == case["expected_classification"]
    stop_condition_ok = not case["stop_conditions"] or any(condition.casefold() in combined for condition in case["stop_conditions"])
    next_action_ok = case["expected_next_action"].casefold() in combined
    return {
        "id": case["id"],
        "skill": case["skill"],
        "selected_action": selected,
        "classification": response.get("classification"),
        "expected_action_hits": expected_hits,
        "expected_action_missing": expected_missing,
        "forbidden_action_hit": forbidden_hits,
        "stop_condition_satisfied": stop_condition_ok,
        "next_action_satisfied": next_action_ok,
        "final_decision": decision,
        "status": "PASS" if classification_ok and not expected_missing and not forbidden_hits and stop_condition_ok and next_action_ok else "FAIL",
    }


def run_case(case: dict[str, Any], command_template: str, timeout: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="harmonyos-agent-eval-") as temporary:
        workspace = Path(temporary)
        skill_target = workspace / ".codex" / "skills" / case["skill"]
        shutil.copytree(REPO_ROOT / "skills" / case["skill"], skill_target)
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
