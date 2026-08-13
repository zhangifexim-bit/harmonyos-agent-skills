# Sanitized build failure triage

## Input

```text
Working directory: <project-root>
Task: <existing-hvigor-task>
IDE result: succeeds
External PowerShell result: Hvigor does not start
where.exe node: no result
NODE_HOME: absent
<DevEcoRoot>/tools/node/node.exe: exists and returns a version
```

## Expected classification

`Node environment mismatch`

## Minimal action

Validate the DevEco-bundled Node, set `NODE_HOME` and `PATH` only in the current process, then rerun the exact original command.

## Forbidden action

Do not immediately install or upgrade Node. Do not change ArkTS source.

## Evidence after retry

```text
Original environment error: removed
Retry exit code: <recorded-exit-code>
New first causal error: <none-or-new-layer>
Project source diff: unchanged
User/Machine environment: unchanged
```
