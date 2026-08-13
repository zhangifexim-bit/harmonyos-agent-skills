# Sanitized final APP verification

## Candidate

```text
Git HEAD: <commit>
Product: default
Build mode: release
Final artifact: <output-directory>/<application>.app
Expected identity/profile/bundle: obtained from an authorized source
```

## Gate record

| Gate | Status | Safe evidence |
| --- | --- | --- |
| Git scope | PASS | intended commit; no unrelated staged content |
| assembleApp | PASS | command and zero exit recorded |
| SignHap / SignApp | PASS | local task evidence recorded |
| final APP selection | PASS | one fresh artifact tied to this build |
| `verify-app` | PASS | zero exit; outputs written to a temporary directory |
| digest | PASS | SHA-256 recorded privately for artifact handoff |
| certificate identity | PASS | matches expected; fingerprint not printed |
| profile type | PASS | Release |
| bundle | PASS | matches expected |
| device smoke | NOT_RUN | requires a human on the exact verified artifact |
| cleanup | PASS | local signing diff restored; Git clean |

Publication remains blocked until the human smoke test and separate publication authorization pass.
