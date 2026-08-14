# Behavioral evaluations

The repository distinguishes deterministic contracts from real agent execution.

## Level 1: deterministic contract evals

Run:

```powershell
python scripts\validate_reliability.py
```

This blocking, offline check validates 32 synthetic cases, the explicit canonical-ID registry, unique routing, dependency closure, the exact publication state machine, and both evidence schemas. Fixture prose is Human/Agent context only; it never generates machine IDs. A pass is reported as `CONTRACT_EVAL_PASS` and is not evidence that an Agent was invoked.

## Level 2: live agent evals

[`../scripts/run_behavioral_evals.py`](../scripts/run_behavioral_evals.py) is a first-class `codex exec` runner. It does not accept arbitrary shell commands. Every call creates a fresh temporary workspace and session, copies only the selected Skill plus its complete manifest dependency closure, redirects the synthetic user home, passes a minimal environment allowlist, requests the closed response schema, and uses an argument vector with `shell=False`.

The harness requires local `codex --version` and `codex exec --help` to prove support for non-interactive execution, prompt stdin, explicit cwd, output schema, final output file, ephemeral execution, ignored user configuration, and read-only sandboxing. It also requires a dedicated external authentication home and an independently confirmed external isolation boundary. Authentication material, raw event streams, stdout/stderr, tokens, private environment values, and chain-of-thought are never stored as evidence.

Dry validation never calls an Agent:

```powershell
python scripts\run_behavioral_evals.py --case build-001-node-missing
```

It reports `LIVE_AGENT_EVAL_NOT_RUN`.

After independently proving the authentication and external isolation gates, an authorized operator can execute the bounded default matrix:

```powershell
python scripts\run_behavioral_evals.py --execute `
  --codex-path <installed-codex-executable> `
  --codex-home <dedicated-external-eval-auth-home> `
  --output <external-sanitized-results-path> `
  --auth-isolation-confirmed `
  --external-isolation-confirmed
```

The default plan is exactly 14 base calls plus one repeat of four high-risk cases, for a hard maximum of 18 calls. Each repeated case must pass twice with identical classification, required/forbidden action results, exact stop-condition set, and next action. Results are not averaged.

Timeout, process failure, missing/empty/oversized output, invalid UTF-8 or JSON, schema mismatch, unknown or duplicate IDs, and contract mismatch are contained per case so the final summary is still written. Safe error classes are `TIMEOUT`, `PROCESS_ERROR`, `OUTPUT_MISSING`, `OUTPUT_TOO_LARGE`, `JSON_INVALID`, `SCHEMA_INVALID`, and `CONTRACT_FAIL`.

Use these statuses precisely:

- `CONTRACT_EVAL_PASS`: deterministic repository contracts passed; no Agent claim.
- `LIVE_AGENT_EVAL_NOT_RUN`: no real Agent call was made.
- `LIVE_AGENT_EVAL_PASS`: every authorized live call and required repeat passed.
- `LIVE_AGENT_EVAL_FAIL` / `ERROR`: at least one live response or runner operation failed.

Live calls remain outside ordinary pull-request CI because they require external authentication, quota, and a separately proven isolation boundary.
