# Sanitized Release signing review

## Input shape

- Product: `default`
- Build mode: `release`
- Release signing config: present and bound to the product
- Keystore/profile/certificate: outside the repository
- Password fields: non-empty managed values; contents not displayed
- Tracked `build-profile.json5`: has a local signing-only diff

## Safe result

| Check | Result |
| --- | --- |
| Release/Debug separation | Confirmed by distinct authorized identity/profile evidence |
| Password classification | `UNDETERMINED` until validated by active DevEco tooling; non-empty is not treated as plaintext |
| Signing material tracked/staged | No |
| Local signing diff | Must not be staged or committed |
| Build | Run only after credential boundary passes |
| Cleanup | Restore the tracked configuration and confirm Git clean |

If a repository-external private patch is used, record only its safe hash and lifecycle state. Never print the patch.
