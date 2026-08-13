# Security Policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting or the repository's Security Advisory workflow when available. If private reporting is unavailable, contact the repository owner through a private channel already listed on their GitHub profile. Do not open a public issue containing exploit details or confidential material.

No dedicated security email address is currently published for this project.

Include a concise impact description, affected version or commit, reproduction steps that use synthetic data, and a suggested mitigation when possible.

## Never submit confidential material

Do not attach or paste any of the following into an Issue, Discussion, pull request, test fixture, log, or advisory comment:

- keystores, `.p12`, `.p7b`, private keys, or signing certificates;
- passwords, tokens, API keys, or DevEco credential values;
- signing materials, private signing patches, or credential dumps;
- private project source, schemas, test data, or business rules;
- real bundle identities, certificate fingerprints, machine usernames, or personal paths.

Use minimal synthetic examples. Replace identifiers and paths with explicit placeholders, and confirm the redaction before submitting.

## Supported versions

Security fixes are applied to the latest commit on `main` until the project publishes versioned releases. Older snapshots are not supported.
