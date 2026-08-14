# Changelog

All notable changes to this project will be documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to use semantic versioning after its first public release.

## [0.2.1] - 2026-08-13

### Added

- First-class bounded Codex live-eval runner with fixed argv, `shell=False`, a closed response schema, and an 18-call maximum.
- Versioned canonical registry with 142 action IDs and 17 stop-condition IDs.
- Two Project Audit cases, bringing deterministic reliability contracts to 32.
- Versioned publication identity policy and the named `PUBLIC_IDENTITY_POLICY_PASS` release condition.
- Expanded sanitized compatibility evidence and submission guidance.

### Changed

- Removed the legacy prose-derived ID path and migrated reliability contracts to strict canonical action, stop-condition, classification, and next-action validation.
- Removed the arbitrary runner-command interface; live execution now fails closed unless CLI capability, authentication, environment, and external isolation gates are confirmed.
- Kept live execution status explicit: `LIVE_AGENT_EVAL_NOT_RUN`; no live Agent pass is claimed.

### Fixed

- Added Windows UTF-8 coverage for annotated-tag metadata.
- Made pull-request publication checks use the real `pull_request.head.sha` instead of a synthetic merge commit.
- Made a missing pull-request candidate SHA fail closed without falling back to `github.sha`.

## [0.2.0] - 2026-08-13

### Added

- Deterministic behavioral contract framework with 30 sanitized reliability cases.
- Optional isolated live-agent evaluation harness with explicit execution and quota gates.
- Safe PowerShell installer, ownership markers, conflict detection, and installer tests.
- Versioned machine-readable evidence schema and Skill manifest.
- Field-verified sanitized compatibility evidence.

### Changed

- Removed the Release Signing/Release Check circular dependency.
- Added a unique routing and handoff contract for all four Skills.
- Hardened Build Doctor error transitions and ambiguous DevEco handling.
- Hardened signing reachable-history incidents and Release Check artifact/state-machine identity.
- Added dependency-closure installation/update behavior and dependent-aware uninstall protection.
- Made Release Signing readiness-only and Release Check the sole formal build orchestrator.
- Changed live evaluation grading to canonical action IDs and added Git metadata auditing.

## [0.1.0] - 2026-08-12

### Added

- Four initial HarmonyOS engineering agent skills.
- Read-only DevEco environment doctor with structured and JSON output.
- Release signing safety and Git-boundary guidance.
- Independent final artifact verification workflow.
- Skill validation, privacy scanning, decision fixtures, unit tests, and CI.
