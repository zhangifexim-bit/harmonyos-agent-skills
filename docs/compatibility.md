# Compatibility

## Supported workflow

- Windows PowerShell 5.1 or PowerShell 7 for the DevEco environment probe.
- Python 3.10 or newer for repository validation and tests.
- Git for tracked/staged/history checks.
- HarmonyOS application projects built with DevEco Studio and Hvigor.

The documentation and Git checks are broadly platform-neutral. The bundled environment probe is Windows-specific because it checks Windows environment scopes, standard installation directories, and registry metadata.

## Version-sensitive surfaces

The following must be discovered from the target project or local tool help:

- project/module mode and available Hvigor tasks;
- product and `buildMode` parameters;
- SDK directory layout and API component names;
- DevEco-bundled Node and JBR locations;
- `--stop-daemon` invocation;
- `hap-sign-tool.jar` location and `verify-app`/`verify-profile` flags;
- signing configuration schema and credential format.

Do not convert example commands into hardcoded paths. Huawei documents that DevEco Studio's integrated terminal can provide built-in environment variables; external shells may differ. The Build Doctor treats that difference as environment evidence, not a source-code defect.

## Degradation

If a component cannot be validated safely, report `UNKNOWN`. If a configured candidate exists but fails structural or executable validation, report `INVALID`. Missing platform tools should block only the checks that depend on them; they must not be reported as passing.
