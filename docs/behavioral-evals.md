# Behavioral evaluations

The repository distinguishes deterministic contracts from real agent execution.

## Level 1: deterministic contract evals

Run:

```powershell
python scripts\validate_reliability.py
```

This blocking, offline check validates the 30 synthetic cases, unique routing, required fields, expected/forbidden consistency, stop conditions, the evidence schema, and the dependency DAG. A pass is reported as `CONTRACT_EVAL_PASS`.

## Level 2: live agent evals

[`../scripts/run_behavioral_evals.py`](../scripts/run_behavioral_evals.py) creates a fresh temporary workspace per case, installs the selected Skill plus its complete manifest dependency closure, sets an isolated `CODEX_HOME`, and requests a compact JSON decision. Actions, stop conditions, and next action use canonical `UPPER_SNAKE_CASE` identifiers rather than natural-language substring matching. It fail-closes on malformed or duplicate identifiers, missing expected action IDs, classification mismatch, an inexact stop-condition set, a wrong next-action ID, or any forbidden-action ID. Free-form prose cannot satisfy a required action. It stores machine decisions and PASS/FAIL only, without chain-of-thought.

There is intentionally no implicit runner command. CLI syntax, authentication, subscription availability, sandbox flags, and cost can change. Review current official OpenAI documentation and local CLI help, then supply a non-interactive command that writes JSON to `{output_file}`:

```powershell
python scripts\run_behavioral_evals.py --execute `
  --runner-command '<reviewed command using {workspace} {prompt_file} {output_file}>' `
  --case build-001-node-missing
```

The harness forbids real project access in its prompt and uses synthetic fixtures, but the runner must independently enforce read-only/no-network behavior. Live evals remain optional and non-blocking because they may require authentication, subscription quota, or paid API usage. A dry invocation reports `LIVE_AGENT_EVAL_NOT_RUN`; it is never presented as behavioral success.
