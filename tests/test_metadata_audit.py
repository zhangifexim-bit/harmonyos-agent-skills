from __future__ import annotations

import importlib.util
import json
import os
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

    def initialize_repo(self, root: Path, name: str = "Maintainer Bot", email: str = "maintainer@users.noreply.github.com") -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", name], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", email], cwd=root, check=True)

    def commit_file(self, repo: Path, filename: str, content: str, message: str, name: str, email: str) -> str:
        (repo / filename).write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "--", filename], cwd=repo, check=True)
        environment = dict(os.environ)
        environment.update(
            {
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_COMMITTER_NAME": name,
                "GIT_COMMITTER_EMAIL": email,
            }
        )
        subprocess.run(["git", "commit", "-m", message], cwd=repo, env=environment, check=True, capture_output=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()

    def synthetic_policy(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "allowed_control_identities": [
                {"name": "Maintainer Bot", "email": "maintainer@users.noreply.github.com"},
                {"name": "GitHub", "email": "noreply@github.com"},
            ],
            "allowed_tag_identities": [
                {"name": "Maintainer Bot", "email": "maintainer@users.noreply.github.com"}
            ],
        }

    def test_publication_policy_allows_normal_nonmerge_contributor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.initialize_repo(repo)
            base = self.commit_file(repo, "base.txt", "base\n", "base", "Maintainer Bot", "maintainer@users.noreply.github.com")
            self.commit_file(repo, "contribution.txt", "public\n", "contribution", "Public Contributor", "contributor@public.test")
            candidate = self.commit_file(repo, "candidate.txt", "candidate\n", "candidate", "Maintainer Bot", "maintainer@users.noreply.github.com")
            findings, counts = self.scanner.publication_identity_findings(repo, self.synthetic_policy(), candidate, base)
            self.assertEqual([], findings)
            self.assertEqual(0, counts["merge_commits"])

    def test_publication_policy_rejects_candidate_without_echoing_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.initialize_repo(repo)
            candidate = self.commit_file(repo, "candidate.txt", "candidate\n", "candidate", "Synthetic Person", "person@public.test")
            findings, _ = self.scanner.publication_identity_findings(repo, self.synthetic_policy(), candidate)
            self.assertEqual({"author", "committer"}, {finding.field for finding in findings})
            self.assertTrue(all(finding.rule == "publication-control-identity" for finding in findings))
            self.assertNotIn("person@public.test", repr(findings))

    def test_publication_policy_requires_annotated_authorized_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.initialize_repo(repo)
            candidate = self.commit_file(repo, "candidate.txt", "candidate\n", "candidate", "Maintainer Bot", "maintainer@users.noreply.github.com")
            subprocess.run(["git", "tag", "lightweight"], cwd=repo, check=True)
            with self.assertRaisesRegex(ValueError, "annotated"):
                self.scanner.publication_identity_findings(repo, self.synthetic_policy(), candidate, tag_ref="lightweight")

    def test_unicode_annotated_tag_is_utf8_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.initialize_repo(repo)
            candidate = self.commit_file(repo, "candidate.txt", "candidate\n", "candidate", "Maintainer Bot", "maintainer@users.noreply.github.com")
            subprocess.run(["git", "tag", "-a", "v0.0.1", "-m", "完全虚构的安全标签"], cwd=repo, check=True)
            findings, counts = self.scanner.audit_repository(repo, [])
            self.assertEqual([], findings)
            self.assertEqual(1, counts["annotated_tags"])
            policy_findings, policy_counts = self.scanner.publication_identity_findings(repo, self.synthetic_policy(), candidate, tag_ref="v0.0.1")
            self.assertEqual([], policy_findings)
            self.assertEqual(1, policy_counts["annotated_tags"])

    def test_publication_policy_parser_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(json.dumps({"schema_version": "2.0"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.scanner.load_publication_policy(path)

    def test_repository_publication_policy_passes(self) -> None:
        policy = self.scanner.load_publication_policy(REPO_ROOT / "policies" / "publication-identity.json")
        findings, _ = self.scanner.publication_identity_findings(REPO_ROOT, policy, "HEAD", "v0.2.0")
        self.assertEqual([], findings)

    def test_publication_base_must_be_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.initialize_repo(repo)
            first = self.commit_file(repo, "first.txt", "first\n", "first", "Maintainer Bot", "maintainer@users.noreply.github.com")
            subprocess.run(["git", "checkout", "--orphan", "unrelated"], cwd=repo, check=True, capture_output=True)
            candidate = self.commit_file(repo, "other.txt", "other\n", "other", "Maintainer Bot", "maintainer@users.noreply.github.com")
            with self.assertRaisesRegex(ValueError, "not an ancestor"):
                self.scanner.publication_identity_findings(repo, self.synthetic_policy(), candidate, first)


if __name__ == "__main__":
    unittest.main()
