## Scope

Describe the focused workflow or validation change and why it is needed.

## Evidence

- [ ] Trigger, required inputs, decision rule, stop conditions, and output contract are explicit.
- [ ] Examples and fixtures are synthetic and sanitized.
- [ ] No real signing material, credentials, private source, identities, fingerprints, or personal paths are included.

## Validation

- [ ] `python scripts/validate_skills.py`
- [ ] `python -m unittest discover -s tests -v`
- [ ] `python scripts/scan_private_markers.py --generic-only`
- [ ] PowerShell probe parse/basic execution where available
- [ ] `git diff --check`

## Documentation

- [ ] English and Chinese README content remains synchronized where user-facing behavior changed.
- [ ] CHANGELOG updated when appropriate.
