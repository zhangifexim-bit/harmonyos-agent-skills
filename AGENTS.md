# Repository Agent Rules

## Scope

These rules apply only to `harmonyos-agent-skills`. Treat external projects as read-only evidence unless their owner explicitly authorizes a change.

## Public repository boundary

- Assume every tracked file can become public.
- Generalize engineering methods; never copy private source, business rules, data models, product text, identifiers, or machine-specific paths.
- If evidence cannot be safely generalized, omit it.

## Secrets

- Never add keystores, private keys, certificates, profiles, signing patches, passwords, tokens, credential dumps, or real certificate fingerprints.
- Keep local signing material outside this repository.
- Do not print secret values or full sensitive diffs during diagnosis.

## Skill structure

- Each directory under `skills/` must contain `SKILL.md` with only `name` and `description` frontmatter.
- Keep the main workflow concise. Put detailed, version-sensitive material in directly linked `references/` files.
- Bundle deterministic scripts only when they materially reduce unsafe or repeated work.

## Changes and tests

- Make the smallest focused change that satisfies the request.
- Update English and Chinese user documentation together when behavior or installation changes.
- Add or update sanitized examples and tests for changed decision rules.
- Run `python scripts/validate_skills.py`, unit tests, and the generic privacy scan before commit.
- Run `git diff --check` and report any unavailable platform-specific check honestly.

## Git and release hygiene

- Inspect staged content before every commit.
- Do not commit generated build outputs or local-only signing configuration.
- Do not tag, publish, or create a release until validation, artifact verification, device smoke testing, privacy review, and Git cleanliness are complete.
- Never change repository visibility or publish a release without explicit human authorization for that exact action.
