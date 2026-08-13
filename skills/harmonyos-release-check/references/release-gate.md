# Release gate matrix

## Required state order

```text
SIGNING_READY -> BUILD_READY -> ARTIFACT_VERIFIED -> SMOKE_TESTED -> GIT_CLEAN -> READY_FOR_PUBLICATION
```

No state may be inferred from a later state. Each transition needs independent evidence.

Before the state machine starts, run a separate Git preflight that proves the correct root, intended HEAD, tracked/staged scope, and credential boundary. This pre-build audit does not satisfy the later `GIT_CLEAN` state.

| Gate | PASS evidence | Fail closed when |
| --- | --- | --- |
| Git scope | Intended HEAD, reviewed diff, no credentials | Wrong root, unrelated changes, sensitive files |
| Release config | Expected product, Release build mode, Release signing binding | Missing/ambiguous binding or Debug identity |
| Signing | Expected SignHap/SignApp evidence or documented equivalent | Skipped/failed/ambiguous signing |
| Build | Release assembleApp exits zero after signing readiness | Failed task, duplicate formal build, or unknown artifact provenance |
| Final artifact | Exactly one fresh `.app` tied to the build | Stale or multiple candidates |
| Signature | Official `verify-app` exits zero | Nonzero, unsupported syntax, missing outputs |
| Identity/profile | Expected certificate, Release profile, expected bundle | Mismatch, expired/invalid, Debug, unknown |
| Digest | SHA-256 recorded and stable | Artifact changes after verification |
| Device smoke | Human tests exact digest on intended device class | Different file, not run, failed observation |
| Cleanup | Local signing diff restored; temp evidence outside Git | Dirty tracked config or staged material |
| Publication | Separate explicit authorization | Any gate incomplete or no authorization |

`BLOCKED` is not `FAIL`: use it when required external evidence or human testing is unavailable. Neither state permits publication.

Freshness requires build start/end timestamps, pre/post output discovery, and SHA-256. The device smoke-test record must carry the same SHA-256 as independent verification; filename equality is not identity evidence.
