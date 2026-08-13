#!/usr/bin/env python3
"""Scan working, tracked, and staged content without disclosing matched values."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {
    ".git",
    ".hvigor",
    ".idea",
    ".vscode",
    "__pycache__",
    "build",
    "oh_modules",
}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|token|api[_-]?key|client[_-]?secret|private[_-]?key)\b"
    r"\s*[:=]\s*[\"']([^\"'\r\n]+)[\"']"
)
PERSONAL_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:\\Users\\(?!Public(?:\\|$)|Default(?:\\|$))[^\\\s\"']+")
CERTIFICATE_FINGERPRINT = re.compile(r"(?i)\b(?:[0-9A-F]{2}:){19,}[0-9A-F]{2}\b")
AWS_ACCESS_KEY = re.compile(r"\bA" + r"KIA[0-9A-Z]{16}\b")
GITHUB_TOKEN = re.compile(r"\bgh" + r"[pousr]_[A-Za-z0-9]{30,}\b")
PRIVATE_KEY_HEADER = "-" * 5 + "BEGIN " + "PRIVATE" + " KEY" + "-" * 5


@dataclass(frozen=True)
class Finding:
    scope: str
    path: str
    line: int
    rule: str


def run_git(repo_root: Path, args: list[str]) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else b""


def decode_nul_paths(raw: bytes) -> list[str]:
    return [item.decode("utf-8", errors="surrogateescape") for item in raw.split(b"\0") if item]


def working_paths(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        yield path


def read_worktree_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def read_index_text(repo_root: Path, relative_path: str) -> str | None:
    raw = run_git(repo_root, ["show", f":{relative_path}"])
    if not raw or b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    placeholder_tokens = (
        "${",
        "<",
        "example",
        "dummy",
        "redacted",
        "managed-secret",
        "changeme",
        "placeholder",
        "test-only",
    )
    return not normalized or any(token in normalized for token in placeholder_tokens)


def scan_text(text: str, markers: list[str]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    lowered = text.casefold()
    for index, marker in enumerate(markers, start=1):
        offset = lowered.find(marker.casefold())
        if offset >= 0:
            findings.append((text.count("\n", 0, offset) + 1, f"private-marker-{index}"))

    for line_number, line in enumerate(text.splitlines(), start=1):
        if PRIVATE_KEY_HEADER in line:
            findings.append((line_number, "private-key-header"))
        if PERSONAL_WINDOWS_PATH.search(line):
            findings.append((line_number, "personal-windows-path"))
        if CERTIFICATE_FINGERPRINT.search(line):
            findings.append((line_number, "certificate-fingerprint"))
        if AWS_ACCESS_KEY.search(line):
            findings.append((line_number, "cloud-access-key"))
        if GITHUB_TOKEN.search(line):
            findings.append((line_number, "github-token"))
        for match in SECRET_ASSIGNMENT.finditer(line):
            if not is_placeholder(match.group(2)):
                findings.append((line_number, "credential-like-assignment"))
    return findings


def load_markers(repo_root: Path, marker_values: list[str], marker_files: list[Path]) -> list[str]:
    markers = [value for value in marker_values if value]
    resolved_root = repo_root.resolve()
    for marker_file in marker_files:
        resolved_file = marker_file.resolve()
        try:
            resolved_file.relative_to(resolved_root)
        except ValueError:
            pass
        else:
            raise ValueError("private marker files must remain outside the repository")
        for line in resolved_file.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                markers.append(value)
    return list(dict.fromkeys(markers))


def scan_repository(repo_root: Path, markers: list[str]) -> list[Finding]:
    findings: set[Finding] = set()

    for path in working_paths(repo_root):
        text = read_worktree_text(path)
        if text is None:
            continue
        relative = path.relative_to(repo_root).as_posix()
        for line_number, rule in scan_text(text, markers):
            findings.add(Finding("working", relative, line_number, rule))

    tracked = decode_nul_paths(run_git(repo_root, ["ls-files", "-z"]))
    for relative in tracked:
        text = read_worktree_text(repo_root / relative)
        if text is None:
            text = run_git(repo_root, ["show", f"HEAD:{relative}"]).decode("utf-8", errors="replace")
        for line_number, rule in scan_text(text, markers):
            findings.add(Finding("tracked", relative.replace("\\", "/"), line_number, rule))

    staged = decode_nul_paths(
        run_git(repo_root, ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"])
    )
    for relative in staged:
        text = read_index_text(repo_root, relative)
        if text is None:
            continue
        for line_number, rule in scan_text(text, markers):
            findings.add(Finding("staged", relative.replace("\\", "/"), line_number, rule))

    return sorted(findings, key=lambda item: (item.path, item.line, item.scope, item.rule))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument("--marker", action="append", default=[], help="private marker supplied at runtime")
    parser.add_argument(
        "--marker-file",
        action="append",
        type=Path,
        default=[],
        help="UTF-8 marker file that must be outside the repository",
    )
    parser.add_argument(
        "--generic-only",
        action="store_true",
        help="run only built-in generic credential and private-path checks",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = args.repo.resolve()
    if not repo_root.is_dir():
        print("Privacy scan failed: repository root does not exist.")
        return 2
    if args.generic_only and (args.marker or args.marker_file):
        print("Privacy scan failed: --generic-only cannot be combined with private markers.")
        return 2
    try:
        markers = [] if args.generic_only else load_markers(repo_root, args.marker, args.marker_file)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Privacy scan failed: {exc}")
        return 2

    findings = scan_repository(repo_root, markers)
    if findings:
        print(f"Privacy scan failed with {len(findings)} finding(s); matched values are suppressed:")
        for finding in findings:
            print(f"- {finding.scope}: {finding.path}:{finding.line} [{finding.rule}]")
        return 1
    print(
        "Privacy scan passed: working, tracked, and staged content checked; "
        f"{len(markers)} runtime private marker(s) applied."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
