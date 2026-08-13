#!/usr/bin/env python3
"""Validate skill metadata, bundled resources, and repository-local links."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
FRONTMATTER_KEY = re.compile(r"^([A-Za-z0-9_-]+):\s*(.+?)\s*$")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
VALID_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class SkillMetadata:
    directory: Path
    name: str
    description: str


def parse_frontmatter(skill_file: Path) -> tuple[dict[str, str], str]:
    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening YAML frontmatter delimiter")
    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise ValueError("missing closing YAML frontmatter delimiter") from exc

    metadata: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:closing], start=2):
        if not line.strip():
            continue
        match = FRONTMATTER_KEY.match(line)
        if not match:
            raise ValueError(f"unsupported frontmatter syntax on line {line_number}")
        key, raw_value = match.groups()
        if key in metadata:
            raise ValueError(f"duplicate frontmatter key: {key}")
        value = raw_value.strip().strip('"\'')
        metadata[key] = value
    return metadata, "\n".join(lines[closing + 1 :])


def discover_skills(repo_root: Path = REPO_ROOT) -> tuple[list[SkillMetadata], list[str]]:
    errors: list[str] = []
    skill_root = repo_root / "skills"
    if not skill_root.is_dir():
        return [], ["skills/: directory is missing"]

    skills: list[SkillMetadata] = []
    for directory in sorted(path for path in skill_root.iterdir() if path.is_dir()):
        skill_file = directory / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{directory.relative_to(repo_root)}: SKILL.md is missing")
            continue
        try:
            metadata, body = parse_frontmatter(skill_file)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{skill_file.relative_to(repo_root)}: {exc}")
            continue

        unknown = sorted(set(metadata) - {"name", "description"})
        missing = sorted({"name", "description"} - set(metadata))
        if unknown:
            errors.append(f"{skill_file.relative_to(repo_root)}: unsupported frontmatter keys {unknown}")
        if missing:
            errors.append(f"{skill_file.relative_to(repo_root)}: missing frontmatter keys {missing}")
            continue

        name = metadata["name"].strip()
        description = metadata["description"].strip()
        if not VALID_NAME.fullmatch(name):
            errors.append(f"{skill_file.relative_to(repo_root)}: invalid skill name {name!r}")
        if name != directory.name:
            errors.append(f"{skill_file.relative_to(repo_root)}: name must match directory")
        if not description:
            errors.append(f"{skill_file.relative_to(repo_root)}: description is empty")
        if not body.strip():
            errors.append(f"{skill_file.relative_to(repo_root)}: instruction body is empty")

        reference_dir = directory / "references"
        reference_files = sorted(reference_dir.glob("*.md")) if reference_dir.is_dir() else []
        if not reference_files:
            errors.append(f"{directory.relative_to(repo_root)}: at least one reference Markdown file is required")
        for reference in reference_files:
            relative_link = reference.relative_to(directory).as_posix()
            if relative_link not in body:
                errors.append(f"{skill_file.relative_to(repo_root)}: reference not linked: {relative_link}")

        scripts_dir = directory / "scripts"
        if scripts_dir.is_dir():
            for script in sorted(path for path in scripts_dir.rglob("*") if path.is_file()):
                relative_link = script.relative_to(directory).as_posix()
                if relative_link not in body:
                    errors.append(f"{skill_file.relative_to(repo_root)}: script not linked: {relative_link}")

        agent_file = directory / "agents" / "openai.yaml"
        if not agent_file.is_file():
            errors.append(f"{directory.relative_to(repo_root)}: agents/openai.yaml is missing")
        else:
            agent_text = agent_file.read_text(encoding="utf-8")
            if f"${name}" not in agent_text:
                errors.append(f"{agent_file.relative_to(repo_root)}: default prompt must mention ${name}")
            short_match = re.search(r'^\s*short_description:\s*"([^"]+)"\s*$', agent_text, re.MULTILINE)
            if not short_match or not 25 <= len(short_match.group(1)) <= 64:
                errors.append(f"{agent_file.relative_to(repo_root)}: short_description must be 25-64 characters")

        skills.append(SkillMetadata(directory=directory, name=name, description=description))

    names = [skill.name for skill in skills]
    duplicates = sorted(name for name in set(names) if names.count(name) > 1)
    if duplicates:
        errors.append(f"skills/: duplicate skill names {duplicates}")
    return skills, errors


def extract_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    if " " in target:
        target = target.split(" ", 1)[0]
    return target


def validate_local_links(repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    resolved_root = repo_root.resolve()
    for markdown_file in sorted(repo_root.rglob("*.md")):
        if ".git" in markdown_file.parts:
            continue
        text = markdown_file.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = extract_link_target(match.group(1))
            if not raw_target or raw_target.startswith("#"):
                continue
            parsed = urlsplit(raw_target)
            if parsed.scheme or parsed.netloc:
                continue
            path_part = unquote(parsed.path).replace("/", str(Path("/")))
            candidate = (markdown_file.parent / path_part).resolve()
            try:
                candidate.relative_to(resolved_root)
            except ValueError:
                errors.append(
                    f"{markdown_file.relative_to(repo_root)}: local link escapes repository: {raw_target}"
                )
                continue
            if not candidate.exists():
                errors.append(f"{markdown_file.relative_to(repo_root)}: broken local link: {raw_target}")
    return errors


def validate_readme_inventory(skills: list[SkillMetadata], repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    for readme_name in ("README.md", "README.zh-CN.md"):
        readme = repo_root / readme_name
        if not readme.is_file():
            errors.append(f"{readme_name}: file is missing")
            continue
        text = readme.read_text(encoding="utf-8")
        for skill in skills:
            expected = f"skills/{skill.name}/SKILL.md"
            if expected not in text:
                errors.append(f"{readme_name}: skill not listed with local link: {skill.name}")
    return errors


def validate_repository(repo_root: Path = REPO_ROOT) -> list[str]:
    skills, errors = discover_skills(repo_root)
    errors.extend(validate_readme_inventory(skills, repo_root))
    errors.extend(validate_local_links(repo_root))
    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        print(f"Skill validation failed with {len(errors)} error(s):")
        for error in errors:
            print(f"- {error}")
        return 1
    skill_count = len(discover_skills()[0])
    print(f"Skill validation passed: {skill_count} skills, metadata, resources, and local links verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
