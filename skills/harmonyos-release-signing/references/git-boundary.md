# Git boundary for local signing

## Preflight

```powershell
git status --short
git ls-files
git diff --cached --name-only
git log --all --name-only --pretty=format:
```

Inspect outputs for credential file extensions and local signing config. Do not print the content of a sensitive diff.

## Repository-external private patch

When a tracked configuration must be changed locally for signing:

1. Confirm the tracked file is clean and record its blob hash.
2. Create the signing diff in a private location outside the repository.
3. Hash the private patch and store the hash separately from public project content.
4. Apply it locally without staging.
5. Build and verify the final artifact.
6. Restore the tracked file from the known repository blob using a non-destructive, explicit file operation.
7. Confirm the restored file hash, `git diff --check`, and `git status --short`.
8. Remove the private patch according to the user's credential-retention policy.

Never print the patch or its sensitive lines. Never use a broad reset or cleanup command to restore it.

## History incident

If real signing material entered Git history, stop push/publication. Record affected refs and obtain authorization for a dedicated history-rewrite and credential-rotation plan. Deleting the working file is not remediation.
