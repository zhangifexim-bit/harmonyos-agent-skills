from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_scanner():
    path = REPO_ROOT / "scripts" / "scan_git_metadata.py"
    spec = importlib.util.spec_from_file_location("scan_git_metadata", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MetadataAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scanner = load_scanner()

    def test_runtime_marker_is_detected_without_echo(self) -> None:
        marker = "synthetic-private-project"
        self.assertEqual("private-marker-1", self.scanner.matching_rule(f"prefix {marker} suffix", [marker]))

    def test_generic_invalid_email_is_detected(self) -> None:
        self.assertEqual("invalid-email-domain", self.scanner.matching_rule("agent@invalid", []))

    def test_audits_commit_tag_and_ref_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            marker = "synthetic-private-project"
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", marker], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "maintainer@example.invalid"], cwd=repo, check=True)
            (repo / "README.md").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "--", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", f"commit for {marker}"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "tag", "-a", "v0.0.0", "-m", f"tag for {marker}"], cwd=repo, check=True)
            subprocess.run(["git", "branch", f"audit-{marker}"], cwd=repo, check=True)
            findings, counts = self.scanner.audit_repository(repo, [marker])
            self.assertGreaterEqual(counts["commits"], 1)
            self.assertEqual(1, counts["annotated_tags"])
            self.assertTrue(any(item.field == "author-name" for item in findings))
            self.assertTrue(any(item.object_type == "commit" and item.field == "message" for item in findings))
            self.assertTrue(any(item.field == "tagger-name" for item in findings))
            self.assertTrue(any(item.object_type == "tag" and item.field == "message" for item in findings))
            self.assertTrue(any(item.object_type == "ref" and item.field == "name" for item in findings))


if __name__ == "__main__":
    unittest.main()
