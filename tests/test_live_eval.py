from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_harness():
    path = REPO_ROOT / "scripts" / "run_behavioral_evals.py"
    spec = importlib.util.spec_from_file_location("run_behavioral_evals", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LiveEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = load_harness()
        cls.cases = json.loads((REPO_ROOT / "tests" / "evals" / "reliability-cases.json").read_text(encoding="utf-8"))
        cls.case = cls.cases[0]
        cls.actions, cls.stops = cls.harness.load_registry()

    def valid_response(self) -> dict[str, object]:
        return {
            "action_ids": list(self.case["expected_action_ids"]),
            "classification": self.case["expected_classification"],
            "stop_condition_ids": list(self.case["stop_condition_ids"]),
            "next_action_id": self.case["expected_next_action_id"],
            "final_decision": "Synthetic bounded decision.",
        }

    def test_default_plan_is_exactly_bounded_live_matrix(self) -> None:
        plan = self.harness.build_run_plan(self.cases, None)
        self.assertEqual(18, len(plan))
        counts = {case_id: sum(case["id"] == case_id for case in plan) for case_id in self.harness.LIVE_REPEAT_CASE_IDS}
        self.assertEqual({case_id: 2 for case_id in self.harness.LIVE_REPEAT_CASE_IDS}, counts)

    def test_arbitrary_runner_interface_is_absent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "run_behavioral_evals.py"), "--runner-command", "unsafe"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_codex_argv_is_a_fixed_argument_vector(self) -> None:
        argv = self.harness.build_codex_argv(Path("codex.exe"), Path("workspace"), Path("response.json"), Path("schema.json"))
        self.assertEqual("exec", argv[1])
        self.assertIn("read-only", argv)
        self.assertIn("--ignore-user-config", argv)
        self.assertIn("--output-schema", argv)
        self.assertEqual("-", argv[-1])

    def test_environment_is_allowlisted_and_redirects_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"SYNTHETIC_SECRET": "must-not-pass"}, clear=False):
            root = Path(temporary)
            environment = self.harness.minimal_environment(root, root / "auth")
            self.assertNotIn("SYNTHETIC_SECRET", environment)
            self.assertEqual(str(root / "auth"), environment["CODEX_HOME"])
            self.assertEqual(str(root / "home"), environment["USERPROFILE"])

    def test_response_validation_rejects_unexpected_duplicate_unknown_and_invalid_ids(self) -> None:
        response = self.valid_response()
        response["unexpected"] = True
        response["action_ids"] = [self.case["expected_action_ids"][0], self.case["expected_action_ids"][0], "UNKNOWN_ID", "bad-id"]
        errors = self.harness.validate_response(response, self.actions, self.stops)
        joined = "\n".join(errors)
        self.assertIn("closed schema", joined)
        self.assertIn("duplicates", joined)
        self.assertIn("unknown", joined)
        self.assertIn("invalid canonical", joined)

    def test_prose_cannot_satisfy_required_machine_actions(self) -> None:
        response = self.valid_response()
        response["action_ids"] = []
        response["final_decision"] = " ".join(self.case["expected_action_ids"])
        result = self.harness.grade(self.case, response, self.actions, self.stops)
        self.assertEqual("FAIL", result["status"])
        self.assertEqual(self.case["expected_action_ids"], result["expected_action_missing"])

    def test_forbidden_action_and_exact_stop_next_contracts_fail(self) -> None:
        response = self.valid_response()
        response["action_ids"] = [*self.case["expected_action_ids"], self.case["forbidden_action_ids"][0]]
        response["next_action_id"] = self.case["forbidden_action_ids"][0]
        result = self.harness.grade(self.case, response, self.actions, self.stops)
        self.assertEqual("FAIL", result["status"])
        self.assertEqual([self.case["forbidden_action_ids"][0]], result["forbidden_action_hit"])
        self.assertFalse(result["next_action_satisfied"])

    def test_output_failure_classes_are_contained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "response.json"
            self.assertEqual("OUTPUT_MISSING", self.harness.read_response(self.case, output)["error_code"])
            output.write_text("", encoding="utf-8")
            self.assertEqual("OUTPUT_MISSING", self.harness.read_response(self.case, output)["error_code"])
            output.write_text("{", encoding="utf-8")
            self.assertEqual("JSON_INVALID", self.harness.read_response(self.case, output)["error_code"])
            output.write_bytes(b"x" * (self.harness.MAX_OUTPUT_BYTES + 1))
            self.assertEqual("OUTPUT_TOO_LARGE", self.harness.read_response(self.case, output)["error_code"])
            output.write_text(json.dumps({"unexpected": True}), encoding="utf-8")
            self.assertEqual("SCHEMA_INVALID", self.harness.read_response(self.case, output)["error_code"])

    def test_timeout_process_and_unicode_errors_are_contained(self) -> None:
        for side_effect, expected in (
            (subprocess.TimeoutExpired(["codex"], 1), "TIMEOUT"),
            (OSError("synthetic"), "PROCESS_ERROR"),
            (UnicodeDecodeError("utf-8", b"x", 0, 1, "synthetic"), "PROCESS_ERROR"),
        ):
            with self.subTest(expected=expected), patch.object(self.harness.subprocess, "run", side_effect=side_effect):
                result = self.harness.run_case(self.case, Path("codex.exe"), Path("external-auth"), 1)
                self.assertEqual(expected, result["error_code"])

    def test_nonzero_exit_is_contained_without_raw_output(self) -> None:
        completed = SimpleNamespace(returncode=7, stdout="synthetic-sensitive-output", stderr="synthetic-sensitive-error")
        with patch.object(self.harness.subprocess, "run", return_value=completed):
            result = self.harness.run_case(self.case, Path("codex.exe"), Path("external-auth"), 1)
        self.assertEqual({"id": self.case["id"], "skill": self.case["skill"], "status": "ERROR", "error_code": "PROCESS_ERROR"}, result)

    def test_repeat_contract_requires_two_stable_passes(self) -> None:
        result = self.harness.grade(self.case, self.valid_response(), self.actions, self.stops)
        self.assertEqual("PASS", self.harness.repeat_status([result, dict(result)])[self.case["id"]])
        unstable = dict(result, next_action_id="DIFFERENT_REGISTERED_ID")
        self.assertEqual("FAIL", self.harness.repeat_status([result, unstable])[self.case["id"]])


if __name__ == "__main__":
    unittest.main()
