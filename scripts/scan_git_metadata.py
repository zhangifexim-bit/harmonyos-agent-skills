#!/usr/bin/env python3
"""Audit reachable Git metadata and publication-control identities safely."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDITED_REF_PREFIXES = ("refs/heads/", "refs/remotes/", "refs/tags/")
GENERIC_PATTERNS = (
    ("invalid-email-domain", re.compile(r"(?i)@(?:invalid|example|localhost)$")),
    ("local-baseline-identity", re.compile(r"(?i)\blocal[ _-]?baseline\b")),
)
POLICY_KEYS = {"schema_version", "allowed_control_identities", "allowed_tag_identities"}
IDENTITY_KEYS = {"name", "email"}


@dataclass(frozen=True)
class Finding:
    object_type: str
    object_id: str
    field: str
    rule: str


def run_git(repo: Path, *arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def git(repo: Path, *arguments: str, input_text: str | None = None) -> str:
    completed = run_git(repo, *arguments, input_text=input_text)
    if completed.returncode != 0:
        raise RuntimeError(f"git command failed: {arguments[0] if arguments else 'unknown'}")
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


def validate_identity_list(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"publication policy {field} must be a non-empty array")
    identities: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for identity in value:
        if not isinstance(identity, dict) or set(identity) != IDENTITY_KEYS:
            raise ValueError(f"publication policy {field} contains an invalid identity")
        name, email = identity.get("name"), identity.get("email")
        if not isinstance(name, str) or not name or not isinstance(email, str) or not email:
            raise ValueError(f"publication policy {field} contains an empty identity")
        key = (name, email)
        if key in seen:
            raise ValueError(f"publication policy {field} contains a duplicate identity")
        seen.add(key)
        identities.append({"name": name, "email": email})
    return identities


def load_publication_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("publication policy could not be loaded") from error
    if not isinstance(policy, dict) or set(policy) != POLICY_KEYS:
        raise ValueError("publication policy fields are invalid")
    if policy["schema_version"] != "1.0":
        raise ValueError("publication policy schema is unsupported")
    return {
        "schema_version": "1.0",
        "allowed_control_identities": validate_identity_list(policy["allowed_control_identities"], "allowed_control_identities"),
        "allowed_tag_identities": validate_identity_list(policy["allowed_tag_identities"], "allowed_tag_identities"),
    }


def identity_allowed(name: str, email: str, allowed: list[dict[str, str]]) -> bool:
    normalized_email = email.strip().removeprefix("<").removesuffix(">")
    return any(name == identity["name"] and normalized_email == identity["email"] for identity in allowed)


def resolve_commit(repo: Path, refname: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{refname}^{{commit}}").strip()


def resolve_ci_candidate_ref(environment: Mapping[str, str] | None = None) -> str:
    """Resolve the event's real candidate, never a pull-request merge checkout."""
    values = os.environ if environment is None else environment
    candidate = values.get("PUBLICATION_CANDIDATE_REF", "").strip()
    if candidate:
        return candidate
    if values.get("GITHUB_ACTIONS", "").casefold() == "true":
        raise ValueError("PUBLICATION_CANDIDATE_REF is required in GitHub Actions")
    return "HEAD"


def inspect_commit_identity(repo: Path, commit_id: str) -> tuple[str, str, str, str]:
    values = git(repo, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", commit_id).rstrip("\n").split("\0")
    if len(values) != 4:
        raise RuntimeError("Git returned an invalid commit identity record")
    return values[0], values[1], values[2], values[3]


def publication_identity_findings(
    repo: Path,
    policy: dict[str, Any],
    candidate_ref: str,
    base_ref: str | None = None,
    tag_ref: str | None = None,
) -> tuple[list[Finding], dict[str, int]]:
    if git(repo, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise ValueError("publication identity cannot be proven from shallow history")
    candidate = resolve_commit(repo, candidate_ref)
    findings: list[Finding] = []
    allowed_control = policy["allowed_control_identities"]
    author_name, author_email, committer_name, committer_email = inspect_commit_identity(repo, candidate)
    for field, name, email in (
        ("author", author_name, author_email),
        ("committer", committer_name, committer_email),
    ):
        if not identity_allowed(name, email, allowed_control):
            findings.append(Finding("candidate", candidate, field, "publication-control-identity"))

    merge_ids: list[str] = []
    if base_ref is not None:
        base = resolve_commit(repo, base_ref)
        ancestry = run_git(repo, "merge-base", "--is-ancestor", base, candidate)
        if ancestry.returncode != 0:
            raise ValueError("publication base is not an ancestor of candidate")
        merge_ids = git(repo, "rev-list", "--merges", f"{base}..{candidate}").splitlines()
        for merge_id in merge_ids:
            values = inspect_commit_identity(repo, merge_id)
            for field, name, email in (
                ("author", values[0], values[1]),
                ("committer", values[2], values[3]),
            ):
                if not identity_allowed(name, email, allowed_control):
                    findings.append(Finding("merge-commit", merge_id, field, "publication-control-identity"))

    tags_checked = 0
    if tag_ref is not None:
        tag_object = git(repo, "rev-parse", "--verify", tag_ref).strip()
        if git(repo, "cat-file", "-t", tag_object).strip() != "tag":
            raise ValueError("publication tag must be annotated")
        tags_checked = 1
        tagger_name, tagger_email = git(
            repo,
            "for-each-ref",
            f"refs/tags/{tag_ref.removeprefix('refs/tags/')}",
            "--format=%(taggername)%00%(taggeremail)",
        ).rstrip("\n").split("\0", 1)
        if not identity_allowed(tagger_name, tagger_email, policy["allowed_tag_identities"]):
            findings.append(Finding("annotated-tag", tag_object, "tagger", "publication-tag-identity"))
    return findings, {"candidate": 1, "merge_commits": len(merge_ids), "annotated_tags": tags_checked}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument("--marker-file", type=Path, action="append", default=[])
    parser.add_argument("--publication-policy", type=Path)
    parser.add_argument("--candidate-ref")
    parser.add_argument("--base-ref")
    parser.add_argument("--tag-ref")
    args = parser.parse_args()
    try:
        repo = args.repo.resolve()
        if args.publication_policy and (args.marker or args.marker_file):
            raise ValueError("publication policy mode cannot be combined with private marker inputs")
        if not args.publication_policy and any((args.candidate_ref, args.base_ref, args.tag_ref)):
            raise ValueError("publication refs require --publication-policy")
        markers = load_markers(repo, args.marker, args.marker_file)
        findings, counts = audit_repository(repo, markers)
        publication_counts: dict[str, int] | None = None
        if args.publication_policy:
            if not args.candidate_ref:
                raise ValueError("--candidate-ref is required with --publication-policy")
            policy = load_publication_policy(args.publication_policy.resolve())
            policy_findings, publication_counts = publication_identity_findings(
                repo,
                policy,
                args.candidate_ref,
                args.base_ref,
                args.tag_ref,
            )
            findings.extend(policy_findings)
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
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
    if publication_counts is not None:
        print(
            "PUBLIC_IDENTITY_POLICY_PASS: "
            f"{publication_counts['candidate']} candidate, {publication_counts['merge_commits']} merge commit(s), "
            f"{publication_counts['annotated_tags']} annotated tag(s); 0 identity finding(s)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
