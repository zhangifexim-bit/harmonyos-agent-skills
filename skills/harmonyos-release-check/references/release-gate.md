# Release gate matrix

| Gate | PASS evidence | Fail closed when |
| --- | --- | --- |
| Git scope | Intended HEAD, reviewed diff, no credentials | Wrong root, unrelated changes, sensitive files |
| Release config | Expected product, Release build mode, Release signing binding | Missing/ambiguous binding or Debug identity |
| Build | Release assembleApp exits zero | Failed task or unknown artifact provenance |
| Signing | Expected SignHap/SignApp evidence or documented equivalent | Skipped/failed/ambiguous signing |
| Final artifact | Exactly one fresh `.app` tied to the build | Stale or multiple candidates |
| Signature | Official `verify-app` exits zero | Nonzero, unsupported syntax, missing outputs |
| Identity/profile | Expected certificate, Release profile, expected bundle | Mismatch, expired/invalid, Debug, unknown |
| Digest | SHA-256 recorded and stable | Artifact changes after verification |
| Device smoke | Human tests exact digest on intended device class | Different file, not run, failed observation |
| Cleanup | Local signing diff restored; temp evidence outside Git | Dirty tracked config or staged material |
| Publication | Separate explicit authorization | Any gate incomplete or no authorization |

`BLOCKED` is not `FAIL`: use it when required external evidence or human testing is unavailable. Neither state permits publication.
