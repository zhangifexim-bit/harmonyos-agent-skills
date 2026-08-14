from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    script_path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_script("validate_skills.py")
        cls.reliability = load_script("validate_reliability.py")
        cls.scanner = load_script("scan_private_markers.py")

    def test_repository_validation_passes(self) -> None:
        self.assertEqual([], self.validator.validate_repository(REPO_ROOT))

    def test_frontmatter_rejects_unsupported_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_file = Path(temporary) / "SKILL.md"
            skill_file.write_text(
                "---\nname: sample-skill\ndescription: sample\nversion: 1\n---\n# Body\n",
                encoding="utf-8",
            )
            metadata, _ = self.validator.parse_frontmatter(skill_file)
            self.assertEqual({"version"}, set(metadata) - {"name", "description"})

    def test_generic_scanner_detects_secret_without_echo_requirement(self) -> None:
        secret_line = "api_" + "key" + " = " + repr("synthetic-live-credential-value")
        findings = self.scanner.scan_text(secret_line, [])
        self.assertIn((1, "credential-like-assignment"), findings)

    def test_generic_scanner_allows_explicit_placeholder(self) -> None:
        placeholder_line = "keyPassword: \"${SIGNING_KEY_PASSWORD}\""
        self.assertEqual([], self.scanner.scan_text(placeholder_line, []))

    def test_private_marker_is_runtime_only(self) -> None:
        marker = "synthetic-private-identifier"
        findings = self.scanner.scan_text("prefix " + marker + " suffix", [marker])
        self.assertEqual([(1, "private-marker-1")], findings)

    def test_personal_path_detection(self) -> None:
        path = "C:" + "\\" + "Users" + "\\" + "ExampleUser" + "\\" + "project"
        self.assertIn((1, "personal-windows-path"), self.scanner.scan_text(path, []))

    def test_decision_case_contracts(self) -> None:
        cases, errors = self.reliability.validate_cases(REPO_ROOT)
        self.assertEqual([], errors)
        self.assertEqual(32, len(cases))
        self.assertEqual(32, len({case["id"] for case in cases}))
        self.assertEqual(
            {"audit-031-read-only-gate-a", "audit-032-ambiguous-root-or-unknowns"},
            {case["id"] for case in cases if case["skill"] == "harmonyos-project-audit"},
        )

    def test_canonical_registry_and_live_response_schema(self) -> None:
        actions, stops, errors = self.reliability.validate_canonical_registry(REPO_ROOT)
        self.assertEqual([], errors)
        self.assertGreater(len(actions), 100)
        self.assertGreater(len(stops), 10)
        self.assertEqual([], self.reliability.validate_live_eval_schema(REPO_ROOT))

    def make_case_validation_root(self, temporary: str) -> Path:
        root = Path(temporary)
        shutil.copy2(REPO_ROOT / "skills-manifest.json", root / "skills-manifest.json")
        for skill in json.loads((REPO_ROOT / "skills-manifest.json").read_text(encoding="utf-8"))["skills"]:
            target = root / skill["path"]
            target.mkdir(parents=True)
            shutil.copy2(REPO_ROOT / skill["path"] / "SKILL.md", target / "SKILL.md")
        evals = root / "tests" / "evals"
        evals.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "tests" / "evals" / "canonical-ids.json", evals / "canonical-ids.json")
        shutil.copy2(REPO_ROOT / "tests" / "evals" / "reliability-cases.json", evals / "reliability-cases.json")
        return root

    def test_case_validator_rejects_legacy_unknown_duplicate_and_unexpected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_case_validation_root(temporary)
            path = root / "tests" / "evals" / "reliability-cases.json"
            cases = json.loads(path.read_text(encoding="utf-8"))
            cases[0]["expected_actions"] = ["legacy prose"]
            cases[0]["unexpected"] = True
            cases[1]["expected_action_ids"].append(cases[1]["expected_action_ids"][0])
            cases[2]["forbidden_action_ids"].append("UNKNOWN_ACTION_ID")
            path.write_text(json.dumps(cases), encoding="utf-8")
            _, errors = self.reliability.validate_cases(root)
            joined = "\n".join(errors)
            self.assertIn("extra=", joined)
            self.assertIn("duplicate IDs", joined)
            self.assertIn("unknown action IDs", joined)

    def test_registry_validator_rejects_duplicate_and_invalid_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tests" / "evals"
            path.mkdir(parents=True)
            (path / "canonical-ids.json").write_text(
                json.dumps({"schema_version": "1.0", "action_ids": ["VALID_ID", "VALID_ID", "invalid"], "stop_condition_ids": ["STOP_ID"]}),
                encoding="utf-8",
            )
            _, _, errors = self.reliability.validate_canonical_registry(Path(temporary))
            self.assertTrue(any("duplicate" in error for error in errors))
            self.assertTrue(any("invalid canonical ID" in error for error in errors))

    def test_case_validator_fails_closed_on_wrong_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_case_validation_root(temporary)
            path = root / "tests" / "evals" / "reliability-cases.json"
            cases = json.loads(path.read_text(encoding="utf-8"))
            cases[0]["expected_action_ids"] = None
            cases[0]["expected_next_action_id"] = {"invalid": True}
            cases[0]["scenario"] = None
            path.write_text(json.dumps(cases), encoding="utf-8")
            _, errors = self.reliability.validate_cases(root)
            joined = "\n".join(errors)
            self.assertIn("expected_action_ids must be a non-empty array", joined)
            self.assertIn("expected_next_action_id must be a canonical ID", joined)
            self.assertIn("scenario must be a non-empty string", joined)

    def test_skill_dependency_graph_is_dag(self) -> None:
        graph, errors = self.reliability.validate_manifest(REPO_ROOT)
        self.assertEqual([], errors)
        self.assertEqual(["harmonyos-release-signing"], graph["harmonyos-release-check"])
        self.assertEqual([], graph["harmonyos-release-signing"])
        self.assertEqual([], self.reliability.validate_dag(graph))
        self.assertTrue(self.reliability.validate_dag({"a": ["b"], "b": ["a"]}))

    def test_routing_contract_is_unique_and_non_recursive(self) -> None:
        self.assertEqual([], self.reliability.validate_routing(REPO_ROOT))

    def test_evidence_schema_accepts_valid_document(self) -> None:
        document = {
            "schema_version": "1.0",
            "skill": "harmonyos-build-doctor",
            "status": "PASS",
            "classification": "NODE",
            "evidence": [{"kind": "NODE_VERSION", "result": "synthetic version accepted", "source": "bundled runtime", "path_redacted": True}],
            "mutations": ["process environment only"],
            "persistent_changes": False,
            "retry_performed": True,
            "next_action": None,
        }
        self.assertEqual([], self.reliability.validate_evidence_document(document, REPO_ROOT))

    def test_evidence_schema_rejects_secret_shaped_extra_field(self) -> None:
        document = {
            "schema_version": "1.0",
            "skill": "harmonyos-release-signing",
            "status": "PASS",
            "classification": "SIGNING",
            "evidence": [],
            "mutations": [],
            "persistent_changes": False,
            "retry_performed": False,
            "next_action": None,
            "password": "synthetic-forbidden-field",
        }
        self.assertTrue(self.reliability.validate_evidence_document(document, REPO_ROOT))

    def test_live_eval_harness_defaults_to_not_run(self) -> None:
        result = __import__("subprocess").run(
            [sys.executable, str(REPO_ROOT / "scripts" / "run_behavioral_evals.py"), "--case", "build-001-node-missing"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("LIVE_AGENT_EVAL_NOT_RUN", result.stdout)

    def test_live_eval_grading_enforces_expected_and_forbidden_contract(self) -> None:
        harness = load_script("run_behavioral_evals.py")
        case = {
            "id": "synthetic-grade",
            "skill": "harmonyos-build-doctor",
            "expected_action_ids": ["RETRY_ORIGINAL_COMMAND"],
            "forbidden_action_ids": ["PERSIST_ENVIRONMENT"],
            "expected_classification": "NODE",
            "stop_condition_ids": [],
            "expected_next_action_id": "RETRY_ORIGINAL_COMMAND",
        }
        passing = harness.grade(
            case,
            {
                "action_ids": ["RETRY_ORIGINAL_COMMAND"],
                "classification": "NODE",
                "stop_condition_ids": [],
                "next_action_id": "RETRY_ORIGINAL_COMMAND",
                "final_decision": "retry with the corrected process environment",
            },
        )
        failing = harness.grade(
            case,
            {
                "action_ids": ["PERSIST_ENVIRONMENT"],
                "classification": "NODE",
                "stop_condition_ids": [],
                "next_action_id": "PERSIST_ENVIRONMENT",
                "final_decision": "done",
            },
        )
        self.assertEqual("PASS", passing["status"])
        self.assertEqual("FAIL", failing["status"])
        self.assertEqual(["PERSIST_ENVIRONMENT"], failing["forbidden_action_hit"])

    def test_live_eval_prose_cannot_fake_action_ids(self) -> None:
        harness = load_script("run_behavioral_evals.py")
        case = {
            "id": "synthetic-prose",
            "skill": "harmonyos-build-doctor",
            "expected_action_ids": ["RETRY_ORIGINAL_COMMAND"],
            "forbidden_action_ids": ["PERSIST_ENVIRONMENT"],
            "expected_classification": "NODE",
            "stop_condition_ids": [],
            "expected_next_action_id": "RETRY_ORIGINAL_COMMAND",
        }
        result = harness.grade(
            case,
            {
                "action_ids": [],
                "classification": "NODE",
                "stop_condition_ids": [],
                "next_action_id": "RETRY_ORIGINAL_COMMAND",
                "final_decision": "I will retry original command and will not persist environment.",
            },
        )
        self.assertEqual("FAIL", result["status"])
        self.assertEqual(["RETRY_ORIGINAL_COMMAND"], result["expected_action_missing"])

    def test_live_eval_dependency_closure(self) -> None:
        harness = load_script("run_behavioral_evals.py")
        self.assertEqual(
            ["harmonyos-release-signing", "harmonyos-release-check"],
            harness.dependency_closure("harmonyos-release-check"),
        )

    def test_publication_state_machine_order(self) -> None:
        self.assertEqual([], self.reliability.validate_publication_state_machine(REPO_ROOT))

    def test_root_environment_entrypoint_targets_bundled_script(self) -> None:
        wrapper = (REPO_ROOT / "scripts" / "check-deveco-env.ps1").read_text(encoding="utf-8")
        self.assertIn("skills\\harmonyos-build-doctor\\scripts\\check-deveco-env.ps1", wrapper)


if __name__ == "__main__":
    unittest.main()
