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
        expected_ids = {
            "build-001-node-missing",
            "build-002-sdk-env-missing",
            "build-003-java-enoent",
            "signing-001-ciphertext",
            "signing-002-git-boundary",
            "release-001-artifact-verify",
        }
        cases = []
        for case_file in sorted((REPO_ROOT / "tests" / "cases").glob("*.json")):
            cases.append(json.loads(case_file.read_text(encoding="utf-8")))
        self.assertEqual(expected_ids, {case["id"] for case in cases})
        for case in cases:
            self.assertTrue(case["input"])
            self.assertTrue(case["expected"])
            self.assertTrue(case["forbidden"])
            skill_file = REPO_ROOT / "skills" / case["skill"] / "SKILL.md"
            self.assertTrue(skill_file.is_file(), case["id"])

    def test_root_environment_entrypoint_targets_bundled_script(self) -> None:
        wrapper = (REPO_ROOT / "scripts" / "check-deveco-env.ps1").read_text(encoding="utf-8")
        self.assertIn("skills\\harmonyos-build-doctor\\scripts\\check-deveco-env.ps1", wrapper)


if __name__ == "__main__":
    unittest.main()
