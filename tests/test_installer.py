from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "install.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell is required")
class InstallerTests(unittest.TestCase):
    def invoke(self, destination: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-File", str(INSTALLER), "-Destination", str(destination), *arguments],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_fresh_install_all(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            result = self.invoke(destination, "-All")
            self.assertEqual(0, result.returncode, result.stderr)
            installed = {path.name for path in destination.iterdir() if path.is_dir()}
            self.assertEqual({"harmonyos-project-audit", "harmonyos-build-doctor", "harmonyos-release-signing", "harmonyos-release-check"}, installed)

    def test_existing_same_name_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            (destination / "harmonyos-project-audit").mkdir(parents=True)
            result = self.invoke(destination, "-Skill", "harmonyos-project-audit")
            self.assertNotEqual(0, result.returncode)

    def test_what_if_does_not_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            result = self.invoke(destination, "-Skill", "harmonyos-build-doctor", "-WhatIf")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(destination.exists())

    def test_what_if_resolves_dependency_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            result = self.invoke(destination, "-Skill", "harmonyos-release-check", "-WhatIf")
            self.assertEqual(0, result.returncode, result.stderr)
            output = result.stdout + result.stderr
            self.assertIn("harmonyos-release-signing", output)
            self.assertIn("harmonyos-release-check", output)
            self.assertFalse(destination.exists())

    def test_selective_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            result = self.invoke(destination, "-Skill", "harmonyos-release-check")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                {"harmonyos-release-check", "harmonyos-release-signing"},
                {path.name for path in destination.iterdir()},
            )

    def test_existing_owned_dependency_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            self.assertEqual(0, self.invoke(destination, "-Skill", "harmonyos-release-signing").returncode)
            result = self.invoke(destination, "-Skill", "harmonyos-release-check")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Dependency already installed", result.stdout)
            self.assertTrue((destination / "harmonyos-release-check" / "SKILL.md").is_file())

    def test_path_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills with spaces"
            result = self.invoke(destination, "-Skill", "harmonyos-release-signing")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((destination / "harmonyos-release-signing" / "SKILL.md").is_file())

    def test_update_rejects_local_modification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            self.assertEqual(0, self.invoke(destination, "-Skill", "harmonyos-build-doctor").returncode)
            installed = destination / "harmonyos-build-doctor" / "SKILL.md"
            installed.write_text(installed.read_text(encoding="utf-8") + "\nlocal change\n", encoding="utf-8")
            result = self.invoke(destination, "-Skill", "harmonyos-build-doctor", "-Update")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("local modifications", result.stderr)

    def test_update_owned_unmodified_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            self.assertEqual(0, self.invoke(destination, "-Skill", "harmonyos-build-doctor").returncode)
            result = self.invoke(destination, "-Skill", "harmonyos-build-doctor", "-Update")
            self.assertEqual(0, result.returncode, result.stderr)

    def test_update_resolves_missing_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            self.assertEqual(0, self.invoke(destination, "-Skill", "harmonyos-release-check").returncode)
            self.assertEqual(
                0,
                self.invoke(destination, "-Uninstall", "-UninstallSkill", "harmonyos-release-check").returncode,
            )
            self.assertEqual(
                0,
                self.invoke(destination, "-Uninstall", "-UninstallSkill", "harmonyos-release-signing").returncode,
            )
            result = self.invoke(destination, "-Skill", "harmonyos-release-check", "-Update")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((destination / "harmonyos-release-signing" / "SKILL.md").is_file())
            self.assertTrue((destination / "harmonyos-release-check" / "SKILL.md").is_file())

    def test_uninstall_rejects_unowned_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            target = destination / "harmonyos-project-audit"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("synthetic local skill", encoding="utf-8")
            result = self.invoke(destination, "-Uninstall", "-UninstallSkill", "harmonyos-project-audit")
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(target.exists())

    def test_safe_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            self.assertEqual(0, self.invoke(destination, "-Skill", "harmonyos-project-audit").returncode)
            result = self.invoke(destination, "-Uninstall", "-UninstallSkill", "harmonyos-project-audit")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse((destination / "harmonyos-project-audit").exists())

    def test_uninstall_blocks_required_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            self.assertEqual(0, self.invoke(destination, "-Skill", "harmonyos-release-check").returncode)
            result = self.invoke(destination, "-Uninstall", "-UninstallSkill", "harmonyos-release-signing")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("depends on it", result.stderr)
            self.assertTrue((destination / "harmonyos-release-signing").is_dir())

    def test_uninstall_dependency_and_dependent_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            self.assertEqual(0, self.invoke(destination, "-Skill", "harmonyos-release-check").returncode)
            result = self.invoke(
                destination,
                "-Uninstall",
                "-UninstallSkill",
                "harmonyos-release-signing,harmonyos-release-check",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse((destination / "harmonyos-release-signing").exists())
            self.assertFalse((destination / "harmonyos-release-check").exists())

    def test_invalid_destination_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "not-a-directory"
            destination.write_text("synthetic", encoding="utf-8")
            result = self.invoke(destination, "-Skill", "harmonyos-project-audit")
            self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
