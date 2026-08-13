# Design principles

## Evidence before edits

Facts must map to files, commands, tool output, or explicit human observations. Unknown and not-run states remain visible.

## Diagnose by layer

Check Node, SDK, Java, and Hvigor startup before application code. Reclassify the error when the causal stage changes.

## Minimum necessary mutation

Prefer read-only discovery, then current-process environment changes, then the smallest authorized project edit. Do not turn a focused failure into a toolchain upgrade or broad refactor.

## Independent release proof

Build, signing, final artifact verification, device testing, cleanup, and publication are separate gates. Verify the final APP, not an intermediate artifact.

## Secrets are boundaries, not strings

Do not classify or validate credentials by revealing them. A non-empty field is not proof of plaintext. Keep private material and local signing patches outside Git, and scan all reachable repository states before publication.

## Progressive disclosure

Keep `SKILL.md` fast to load. Link directly to one-level-deep references for detailed decisions. Use scripts only where deterministic behavior materially improves safety or reproducibility.
