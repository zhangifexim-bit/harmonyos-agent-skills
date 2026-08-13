# Architecture

The repository separates trigger metadata, agent reasoning, version-sensitive details, and deterministic checks.

```text
User request
  -> SKILL.md trigger and gate
     -> references/ for detailed decisions and current-tool checks
     -> bundled script for deterministic read-only evidence
        -> explicit output contract
           -> human authorization at high-risk or publication boundaries
```

## Skill package

Each skill is self-contained:

- `SKILL.md` carries only the `name` and trigger-focused `description` frontmatter plus the core workflow.
- `agents/openai.yaml` provides user-facing discovery metadata.
- `references/` holds command catalogs, matrices, and version-sensitive guidance loaded only when needed.
- `scripts/` is used only where a deterministic implementation is safer than repeatedly generated shell code.

## Repository tooling

`scripts/validate_skills.py` validates metadata, unique names, resource links, repository-local links, agent metadata, and README inventory. `scripts/scan_private_markers.py` independently scans working, tracked, and staged content while suppressing matched values. The root environment script is a stable entrypoint to the Build Doctor's bundled implementation.

## Evidence flow

The skills distinguish observation from action and build from release:

```text
Read-only audit -> authorized minimal change -> focused validation
-> Release build -> signing task evidence -> independent artifact verification
-> human device smoke test -> local cleanup -> publication authorization
```

A downstream state never backfills an upstream state. For example, a file named `release` does not prove Release mode, and a successful compile does not prove device behavior.

## Skill dependency graph

```text
harmonyos-project-audit
harmonyos-build-doctor
harmonyos-release-signing
        ^
        |
harmonyos-release-check
```

The first three are independent or leaf workflows. Release Check is the only release orchestrator and may consume Release Signing evidence or invoke that skill once. Release Signing never invokes Release Check. [`../skills-manifest.json`](../skills-manifest.json) is the machine-readable source of truth, and blocking validation rejects cycles.

## Reliability contracts

- [`skill-routing.md`](skill-routing.md) defines one primary route per typical intent and explicit, non-recursive handoffs.
- [`../schemas/evidence.schema.json`](../schemas/evidence.schema.json) defines optional redacted evidence for machine handoff while preserving human-readable output.
- [`../tests/evals/reliability-cases.json`](../tests/evals/reliability-cases.json) contains deterministic synthetic contracts.
- [`behavioral-evals.md`](behavioral-evals.md) distinguishes blocking contract checks from optional real-agent execution.
