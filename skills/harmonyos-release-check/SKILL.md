---
name: harmonyos-release-check
description: Run the final evidence-based gate for a HarmonyOS publication candidate. Use when building a Release APP, reviewing SignHap/SignApp results, verifying a final .app with hap-sign-tool, checking certificate/profile/bundle identity and digest, coordinating a human device smoke test, restoring local signing config, or deciding whether commit/tag/release is allowed.
---

# HarmonyOS Release Check

## Scope

Verify the exact final artifact independently. A successful assemble task or the existence of a signed file is not sufficient release evidence.

## Required inputs

- Clean intended Git commit and explicit release scope.
- Product, module set, Release build mode, expected bundle, certificate identity, and profile type.
- Project-supported Release assemble command.
- Final `.app` path and access to the official `hap-sign-tool.jar` plus JBR/Java.
- Human owner for device smoke testing and publication approval.

## Workflow

1. Audit Git scope, HEAD, staged/dirty state, ignored outputs, and credential boundaries.
2. Audit Release configuration and product/signing binding with `$harmonyos-release-signing`.
3. Run the project-supported Release `assembleApp` command. Capture exact command, exit code, and completed build/sign tasks.
4. Confirm SignHap and SignApp evidence when the local Hvigor version exposes those task names.
5. Resolve exactly one final `.app`; reject stale or ambiguous candidates.
6. Read [the hap-sign-tool verification guide](references/hap-sign-tool-verification.md), inspect local help, and run `verify-app` into a new temporary directory.
7. Hash the final artifact and record the digest as release evidence.
8. Verify the extracted certificate chain against the expected Release identity without publishing the real fingerprint.
9. Verify the extracted profile, profile type, validity, and expected bundle using the active tool's supported read-only commands.
10. Prove the candidate is Release, not Debug, from build mode plus profile/identity evidence.
11. Require a human device smoke test of the exact verified artifact. Record observed result separately from build output.
12. Restore local-only signing configuration and confirm Git clean.
13. Allow commit or tag only after all required evidence passes and the user separately authorizes it.

Use [the release gate matrix](references/release-gate.md) to classify each stage.

## Decision rules

- Fail closed on multiple artifacts, unknown tool versions, verification nonzero exit, identity mismatch, Debug profile, bundle mismatch, stale output, or unclean Git.
- Treat `verify-app` and `verify-profile` command syntax as version-sensitive; inspect local help before execution.
- Write extracted certificate/profile evidence only to a fresh temporary directory and avoid console output containing private identity details.
- Keep build, signing, verification, device testing, and publication as separate states.

## Stop conditions

Stop before device installation if independent verification fails. Stop before tag, release, upload, or visibility change if any gate is incomplete, Git is dirty, the human smoke test is missing, or publication authorization is absent.

## Forbidden actions

- Do not hardcode a DevEco Studio, JBR, SDK, keystore, or user path.
- Do not print real certificate fingerprints, private profiles, passwords, or signing diffs.
- Do not verify an intermediate HAP and infer that the final APP matches.
- Do not substitute Debug signing for Release.
- Do not create a tag or release as a side effect of verification.

## Output contract

Return a gate table with `PASS`, `FAIL`, `BLOCKED`, or `NOT_RUN` for Git scope, Release config, assembleApp, SignHap, SignApp, final APP selection, `verify-app`, digest, certificate identity, profile, bundle, Release-vs-Debug, human smoke test, local config restore, and Git clean. Include safe evidence and one next action for each non-pass state.

## Validation

Re-hash the artifact after all checks and compare it with the smoke-tested file. Confirm temporary verification outputs are outside Git, local signing changes are restored, and no tag/release/publication action occurred without explicit authorization.
