# Skill routing

Choose one primary skill for the user's current intent. A handoff is a new, explicit phase; it is not recursion.

| User intent | Primary skill | Do not route here for |
| --- | --- | --- |
| First inspection, takeover, recovery, or baseline | `harmonyos-project-audit` | Deep environment repair or publication orchestration |
| IDE works but a CLI build fails | `harmonyos-build-doctor` | Business ArkTS fixes or signing approval |
| Configure or audit Debug/Release signing | `harmonyos-release-signing` | Final artifact, smoke-test, tag, or publication orchestration |
| Final release candidate, APP verification, smoke test, or publication gate | `harmonyos-release-check` | Publishing without separate authorization |

## Handoff rules

- `harmonyos-project-audit` may recommend Build Doctor, Release Signing, or Release Check after producing its baseline.
- `harmonyos-build-doctor` may recommend Project Audit for missing project facts or another skill after the environment failure is resolved.
- `harmonyos-release-signing` is a leaf skill. It may output `Recommended next skill: harmonyos-release-check`, but it never invokes Release Check.
- `harmonyos-release-check` is the only release orchestrator. It may invoke Release Signing once when valid signing-audit evidence is absent. It must reuse valid evidence and must never recurse.

The dependency graph is declared in [`../skills-manifest.json`](../skills-manifest.json) and validated as a directed acyclic graph in blocking tests.

## Evidence handoff

Human-readable findings remain required. A skill may additionally emit JSON conforming to [`../schemas/evidence.schema.json`](../schemas/evidence.schema.json). Evidence must be redacted, must not contain secrets, and should identify paths by safe category rather than a personal absolute path.
