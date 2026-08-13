from __future__ import annotations

import importlib.util
import json
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
        self.assertEqual(30, len(cases))
        self.assertEqual(30, len({case["id"] for case in cases}))

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

    def test_root_environment_entrypoint_targets_bundled_script(self) -> None:
        wrapper = (REPO_ROOT / "scripts" / "check-deveco-env.ps1").read_text(encoding="utf-8")
        self.assertIn("skills\\harmonyos-build-doctor\\scripts\\check-deveco-env.ps1", wrapper)


if __name__ == "__main__":
    unittest.main()
