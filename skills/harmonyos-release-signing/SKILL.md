---
name: harmonyos-release-signing
description: Audit, configure, and validate HarmonyOS Release signing without exposing credentials. Use when working with build-profile signingConfigs, Debug versus Release identities, keyAlias, certpath, profile, storeFile, storePassword, keyPassword, product signing bindings, SignHap/SignApp tasks, or Git-safe local signing configuration.
---

# HarmonyOS Release Signing

## Scope

Handle signing as a credential boundary. Keep real signing material outside the repository and keep Release identity separate from Debug identity.

## Required inputs

- Project root, target product, release build mode, and expected public bundle identity.
- Sanitized signing configuration shape and the locations of credential files, described without secret values.
- Expected certificate identity/profile type from an authorized source.
- Current Git tracked, staged, and history state.

## Workflow

1. Audit `signingConfigs` and `products.<product>.signingConfig` bindings without printing sensitive values.
2. Confirm Release and Debug do not share an unintended identity or profile.
3. Check presence and repository boundary for `keyAlias`, `certpath`, `profile`, `storeFile`, `storePassword`, and `keyPassword`.
4. Classify password fields using [the signing configuration model](references/build-profile-signing.md). A non-empty field is not proof of plaintext.
5. Check whether `.p12`, `.p7b`, `.cer`, keystores, local profiles, or signing patches are tracked, staged, or present in reachable history. Stop on a leak.
6. If modification is authorized, change only the selected Release config and product binding. Do not alter Debug signing unless required and approved.
7. Run the project's Release build and observe SignHap/SignApp task evidence. Do not print command lines that expand secrets.
8. Independently verify the final artifact with `$harmonyos-release-check`.
9. Restore any tracked local-only signing difference and confirm Git clean.

For a repository-external private patch workflow, read [the Git boundary guide](references/git-boundary.md).

## Decision rules

Classify each password field without revealing it:

- `EMPTY`: absent or empty.
- `DEVECO_CIPHERTEXT_CONFIRMED`: verified by the active DevEco tooling or documented local format, without printing the value.
- `DEVECO_CIPHERTEXT_LIKELY`: matches a known local ciphertext structure but was not independently verified.
- `PLAINTEXT_LIKELY`: evidence strongly indicates an unprotected literal and it is not a placeholder.
- `UNDETERMINED`: insufficient evidence; fail closed and request a safe local verification.

Never infer `PLAINTEXT_LIKELY` solely from non-emptiness.

## Stop conditions

Stop before build or commit if signing material is inside the repository, credential classification is unsafe, Release identity/profile expectations are unavailable, the product binding is ambiguous, or a real secret may be in Git history. Stop before key generation, certificate replacement, account actions, upload, or publication unless explicitly authorized.

## Forbidden actions

- Do not output passwords, private keys, ciphertext values, full sensitive diffs, private patches, or real fingerprints.
- Do not add `.p12` or `.p7b`; keep `.cer` outside Git by default.
- Do not use a Debug profile or identity merely because it produces a signed artifact.
- Do not commit a local `build-profile.json5` signing difference.
- Do not rewrite history without an explicit incident-recovery plan and authorization.

## Output contract

Return a redacted table of configuration fields, presence, classification, repository boundary, and evidence. Then report product binding, Release task result, final artifact path category, independent verification status, Git tracked/staged/history checks, cleanup status, and unresolved human confirmations.

## Validation

Require successful Release assemble evidence, SignHap/SignApp evidence where exposed by the local tool version, independent final artifact verification, expected certificate/profile/bundle evidence, restored tracked configuration, and clean Git state.
