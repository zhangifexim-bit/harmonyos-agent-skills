# Contributing

Contributions should be small, focused, reproducible, and safe to publish.

## Proposing a skill change

Every new or materially changed skill must define:

1. a precise trigger in the frontmatter description;
2. scope and required inputs;
3. an ordered workflow;
4. decision rules and guardrails;
5. stop conditions and forbidden actions;
6. an output contract;
7. validation steps;
8. sanitized examples and automated tests;
9. direct links to any required references or scripts.

Keep `SKILL.md` concise. Move detailed command matrices, version notes, and checklists into one-level-deep `references/` files.

## Security and privacy

Do not commit real signing material, credentials, ciphertext, certificates, profiles, private source, private identifiers, patient or personal data, or absolute personal paths. Use obvious placeholders. A non-empty password field is not evidence that a value is plaintext; never reveal the value to classify it.

## Development checks

From the repository root, run:

```powershell
python -m py_compile scripts\validate_skills.py scripts\scan_private_markers.py
python scripts\validate_skills.py
python -m unittest discover -s tests -v
python scripts\scan_private_markers.py --generic-only
```

When PowerShell is available, parse and execute the environment probe in a read-only test context. Also run `git diff --check` before requesting review.

## Pull requests

- Explain the concrete failure mode or workflow gap.
- List the changed decision rule and evidence.
- Include tests that fail without the change.
- Keep unrelated formatting and refactors out of the pull request.
- Confirm that no generated artifacts or local signing differences are staged.
