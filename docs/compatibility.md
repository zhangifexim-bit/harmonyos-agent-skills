# Compatibility

## Supported workflow

- Windows PowerShell 5.1 or PowerShell 7 for the DevEco environment probe.
- Python 3.10 or newer for repository validation and tests.
- Git for tracked/staged/history checks.
- HarmonyOS application projects built with DevEco Studio and Hvigor.

The documentation and Git checks are broadly platform-neutral. The bundled environment probe is Windows-specific because it checks Windows environment scopes, standard installation directories, and registry metadata.

## Tested environments

This table records evidence, not a universal support promise.

| Status | OS | DevEco Studio | HarmonyOS API | SDK | Bundled Node | Bundled JBR | Hvigor | Scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Field-verified sanitized environment | Windows | 6.1.1 Release | 24 | 6.1.1.125 | 18.20.1 | 21.0.8 | 6.24.3 | Read-only environment discovery and Release workflow evidence |
| Community reported | — | — | — | — | — | — | — | No reports recorded yet |
| Untested | Other combinations | Version-sensitive | Version-sensitive | Version-sensitive | Version-sensitive | Version-sensitive | Version-sensitive | Must be discovered locally |

The verified row contains tool versions only. It deliberately excludes project names, bundle identifiers, user paths, signing identities, fingerprints, and business information.

## Version-sensitive surfaces

The following must be discovered from the target project or local tool help:

- project/module mode and available Hvigor tasks;
- product and `buildMode` parameters;
- SDK directory layout and API component names;
- DevEco-bundled Node and JBR locations;
- `--stop-daemon` invocation;
- `hap-sign-tool.jar` location and `verify-app`/`verify-profile` flags;
- signing configuration schema and credential format.

## Source strategy

For every version-sensitive operation, use sources in this order:

1. the installed tool's local `--help` or equivalent read-only help;
2. the target project's checked-in configuration and wrapper;
3. current official OpenAI documentation for Codex Skill/install behavior or official Huawei documentation for DevEco/HarmonyOS tooling;
4. sanitized examples in this repository.

Examples are never authoritative over local help, project configuration, or official documentation. If those sources disagree or cannot identify an active DevEco installation, fail closed instead of guessing the newest version.

Do not convert example commands into hardcoded paths. Huawei documents that DevEco Studio's integrated terminal can provide built-in environment variables; external shells may differ. The Build Doctor treats that difference as environment evidence, not a source-code defect.

## Degradation

If a component cannot be validated safely, report `UNKNOWN`. If a configured candidate exists but fails structural or executable validation, report `INVALID`. Missing platform tools should block only the checks that depend on them; they must not be reported as passing.
