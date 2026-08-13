# Security boundaries

## Trust model

The repository is public-safe guidance. Target project files, local environment variables, signing material, build logs, and Git history are untrusted inputs that may contain confidential data.

## Data minimization

- Read only the files needed for the selected gate.
- Report presence, classification, counts, status, and match/mismatch instead of secret values.
- Never print full signing diffs, private profiles, certificate fingerprints, environment dumps, or unrelated paths.
- Use synthetic bundle identities and explicit placeholders in examples and tests.

## Signing boundary

Keystores, profiles, certificates, passwords, ciphertext values, and private patches remain outside Git. The `.gitignore` is defense in depth, not permission to store credentials inside the working tree. Tracked, staged, and reachable history must be checked separately.

## Private marker model

Private identifiers are not embedded in the scanner or CI. Supply them only at runtime with `--marker` or an external `--marker-file`. Reports disclose the rule, path, line, and scope but suppress matched values. CI uses only generic credential, personal-path, private-key, token, and fingerprint patterns.

Git object metadata is audited separately by `scripts/scan_git_metadata.py`. It checks author, committer, and message fields for commits reachable from local/remote branch and tag refs; annotated-tag tagger and message fields; and branch/tag ref names. Runtime private markers follow the same outside-repository rule and matched values are suppressed.

## Mutation boundary

Audit and environment discovery are read-only. Process-scoped environment changes are allowed only for a controlled retry; User/Machine changes require separate authorization. Signing, device data, Git history rewrites, publication, tags, releases, and visibility changes are explicit human gates.
