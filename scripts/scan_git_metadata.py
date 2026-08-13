#!/usr/bin/env python3
"""Audit reachable Git metadata and ref names without leaking marker values."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDITED_REF_PREFIXES = ("refs/heads/", "refs/remotes/", "refs/tags/")
GENERIC_PATTERNS = (
    ("invalid-email-domain", re.compile(r"(?i)@(?:invalid|example|localhost)$")),
    ("local-baseline-identity", re.compile(r"(?i)\blocal[ _-]?baseline\b")),
)


@dataclass(frozen=True)
class Finding:
    object_type: str
    object_id: str
    field: str
    rule: str


def git(repo: Path, *arguments: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(arguments)} failed")
    return completed.stdout


def load_markers(repo: Path, values: list[str], files: list[Path]) -> list[str]:
    markers = [value for value in values if value]
    for marker_file in files:
        resolved = marker_file.resolve()
        try:
            resolved.relative_to(repo.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("private marker files must remain outside the repository")
        markers.extend(line.strip() for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip())
    return list(dict.fromkeys(markers))


def matching_rule(value: str, markers: list[str]) -> str | None:
    folded = value.casefold()
    for index, marker in enumerate(markers, start=1):
        if marker.casefold() in folded:
            return f"private-marker-{index}"
    for rule, pattern in GENERIC_PATTERNS:
        if pattern.search(value):
            return rule
    return None


def audited_refs(repo: Path) -> dict[str, str]:
    refs: dict[str, str] = {"HEAD": git(repo, "rev-parse", "HEAD").strip()}
    for line in git(repo, "for-each-ref", "--format=%(refname)%00%(objectname)").splitlines():
        refname, object_id = line.split("\0", 1)
        if refname.startswith(AUDITED_REF_PREFIXES) and refname != "refs/remotes/origin/HEAD":
            refs[refname] = object_id
    return refs


def audit_repository(repo: Path, markers: list[str]) -> tuple[list[Finding], dict[str, int]]:
    refs = audited_refs(repo)
    findings: list[Finding] = []
    for refname, object_id in sorted(refs.items()):
        if refname == "HEAD":
            continue
        rule = matching_rule(refname, markers)
        if rule:
            findings.append(Finding("ref", object_id, "name", rule))
    commit_ids: set[str] = set()
    if refs:
        commit_ids.update(git(repo, "rev-list", *sorted(refs)).splitlines())
    fields = ("author-name", "author-email", "committer-name", "committer-email")
    for commit_id in sorted(commit_ids):
        values = git(repo, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", commit_id).rstrip("\n").split("\0")
        for field, value in zip(fields, values, strict=True):
            rule = matching_rule(value, markers)
            if rule:
                findings.append(Finding("commit", commit_id, field, rule))
        rule = matching_rule(git(repo, "show", "-s", "--format=%B", commit_id), markers)
        if rule:
            findings.append(Finding("commit", commit_id, "message", rule))
    annotated_tags = 0
    for refname, object_id in sorted(refs.items()):
        if not refname.startswith("refs/tags/") or git(repo, "cat-file", "-t", object_id).strip() != "tag":
            continue
        annotated_tags += 1
        tagger_name, tagger_email, tag_message = git(
            repo,
            "for-each-ref",
            refname,
            "--format=%(taggername)%00%(taggeremail)%00%(contents)",
        ).rstrip("\n").split("\0", 2)
        for field, value in (("tagger-name", tagger_name), ("tagger-email", tagger_email), ("message", tag_message)):
            rule = matching_rule(value, markers)
            if rule:
                findings.append(Finding("tag", object_id, field, rule))
    return findings, {"refs": len(refs), "commits": len(commit_ids), "annotated_tags": annotated_tags}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument("--marker-file", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        markers = load_markers(args.repo, args.marker, args.marker_file)
        findings, counts = audit_repository(args.repo.resolve(), markers)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Git metadata audit failed: {error}", file=sys.stderr)
        return 2
    if findings:
        print(f"Git metadata audit detected {len(findings)} finding(s); values suppressed:")
        for finding in findings:
            print(f"- {finding.object_type} {finding.object_id}: {finding.field} ({finding.rule})")
        return 1
    print(
        "Git metadata audit passed: "
        f"{counts['refs']} refs, {counts['commits']} reachable commits, "
        f"{counts['annotated_tags']} annotated tags; {len(markers)} runtime private marker(s); 0 detected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
