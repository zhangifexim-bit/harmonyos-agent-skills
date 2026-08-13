# HarmonyOS Agent Skills

[English](README.md) | [简体中文](README.zh-CN.md)

Reusable AI agent skills for safer HarmonyOS and DevEco Studio engineering, build troubleshooting, release signing, verification, and Git hygiene.

**Stable:** `v0.1.0` · **Next:** `v0.2.0` Reliability Release candidate

```powershell
.\install.ps1
```

The safe installer installs all four Skills by default, never overwrites an existing same-name directory, and supports `-Skill`, `-Update`, `-Uninstall`, and `-WhatIf`. See [Installation](#installation) for the manual fallback.

> Diagnose the environment before changing the application.

> Evidence before edits.

## Why this exists

Command-line HarmonyOS builds can fail even when DevEco Studio works. Release signing also mixes local credentials, tracked configuration, generated artifacts, and version-sensitive tools. These skills give AI coding agents a conservative workflow for separating environment failures from application defects and for proving release state without exposing credentials.

This repository is an engineering workflow collection, not an ArkTS tutorial or HarmonyOS API encyclopedia.

## Skills

| Skill | Use it for |
| --- | --- |
| [`harmonyos-project-audit`](skills/harmonyos-project-audit/SKILL.md) | Establish a read-only Git, project, build, module, product, SDK, and signing baseline before editing. |
| [`harmonyos-build-doctor`](skills/harmonyos-build-doctor/SKILL.md) | Diagnose Node, SDK, Java, Hvigor, and DevEco CLI failures without prematurely changing application code. |
| [`harmonyos-release-signing`](skills/harmonyos-release-signing/SKILL.md) | Configure and review Debug/Release signing while keeping credentials and local-only changes outside Git. |
| [`harmonyos-release-check`](skills/harmonyos-release-check/SKILL.md) | Build, independently verify, smoke-test, and clean up a publication candidate before tag or release. |

## Which skill should I use?

| Intent | Primary skill |
| --- | --- |
| First inspection, takeover, or baseline | `harmonyos-project-audit` |
| IDE works but the CLI build fails | `harmonyos-build-doctor` |
| Configure or audit signing | `harmonyos-release-signing` |
| Verify a final candidate or publication gate | `harmonyos-release-check` |

Release Signing is a leaf; Release Check is the only release orchestrator. See the complete [routing and handoff contract](docs/skill-routing.md).

## What problems it solves

- An IDE build works, but `hvigorw` cannot find Node, an SDK component, or Java.
- A build error is being mistaken for an ArkTS or business-logic defect.
- A local release signing setup must not leak a keystore, profile, password, or private patch.
- A generated `.app` needs independent signature, profile, identity, bundle, and build-mode evidence.
- A first-time repository handoff needs a reproducible read-only baseline and minimal next action.

## Installation

Clone this repository, then run the fail-safe installer. An explicit `-Destination` wins; otherwise it uses `CODEX_HOME\skills` when configured, then the current user's Codex skills directory. Existing directories are never overwritten by default.

```powershell
.\install.ps1                     # all four Skills
.\install.ps1 -List               # inventory only
.\install.ps1 -Skill harmonyos-build-doctor
.\install.ps1 -All -WhatIf       # preview only
```

`-Update` and `-Uninstall` act only on installations carrying this repository's ownership marker and stop if local modifications are detected. They do not modify `AGENTS.md` or a user project.

Manual installation remains available. Each directory under `skills/` is self-contained:

PowerShell example:

```powershell
git clone <repository-url> harmonyos-agent-skills
Copy-Item -Recurse -LiteralPath .\harmonyos-agent-skills\skills\harmonyos-build-doctor -Destination <codex-skills-directory>
```

You can also keep the repository in a workspace and invoke a skill by its path. Never copy local signing material with a skill.

## Quick start

Invoke the audit skill before asking for changes:

```text
Use $harmonyos-project-audit to establish the current project baseline. Do not edit anything.
```

For a CLI-only build failure:

```text
Use $harmonyos-build-doctor. DevEco Studio works, but the same Hvigor task fails in PowerShell.
```

The environment probe is read-only:

```powershell
.\scripts\check-deveco-env.ps1 -ProjectPath <project-root>
.\scripts\check-deveco-env.ps1 -ProjectPath <project-root> -Json
```

Reliability contracts are machine checked:

```powershell
python scripts\validate_reliability.py
python scripts\run_behavioral_evals.py --case build-001-node-missing
```

The second command validates the optional harness and reports `LIVE_AGENT_EVAL_NOT_RUN`; a real agent is called only with explicit `--execute` and a reviewed runner command. See [behavioral evaluations](docs/behavioral-evals.md).

## Example prompts

- `Use $harmonyos-project-audit to report current state, risks, unknowns, and the smallest safe next action.`
- `Use $harmonyos-build-doctor to diagnose spawn java ENOENT; prefer the IDE-bundled runtime and make no persistent environment changes.`
- `Use $harmonyos-release-signing to review this sanitized build profile without printing password fields.`
- `Use $harmonyos-release-check to verify the final APP independently and stop before tagging.`

See [`examples/`](examples/) for sanitized inputs and expected evidence.

## Safety model

The skills use explicit gates:

1. Inspect read-only evidence first.
2. Distinguish environment, configuration, code, credential, and verification failures.
3. Require authorization before modifying a target project.
4. Prefer process-scoped environment changes over persistent machine changes.
5. Keep signing material outside the repository by default.
6. Verify the final artifact independently; a successful build is not sufficient evidence.
7. Restore local-only configuration and require a clean Git state before tag or publication.

Run the repository checks with:

```powershell
python scripts\validate_skills.py
python -m unittest discover -s tests -v
python scripts\scan_private_markers.py --generic-only
```

For a private-source audit, pass confidential markers at runtime with `--marker` or `--marker-file`; never commit them.

## Repository structure

```text
skills/      Agent-ready skills with references and bundled scripts
scripts/     Repository validation, privacy scanning, and environment entrypoints
examples/    Sanitized build, signing, and release scenarios
tests/       Unit tests and decision-contract fixtures
docs/        Architecture, compatibility, boundaries, and design rationale
.github/     CI, issue forms, and pull request metadata
```

## Compatibility

The workflows target Windows-first DevEco Studio and HarmonyOS application projects, but most audit and Git rules are platform-neutral. One sanitized environment is field-verified; it is evidence, not a claim of universal support. Tool locations, task names, flags, SDK layouts, and signing behavior remain version-sensitive. See [`docs/compatibility.md`](docs/compatibility.md).

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md). Keep pull requests small, include sanitized examples and tests, and never submit real signing material or private project content.

## License

Licensed under the [Apache License 2.0](LICENSE).

## Disclaimer

These skills provide engineering guardrails, not a guarantee that every DevEco Studio or HarmonyOS version behaves identically. Users remain responsible for reviewing signing, device testing, publishing, and account-scoped actions.
