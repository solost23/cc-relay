# Relay — Intelligent Interrupt Layer

Before executing any non-trivial action, call the `relay__assess_action` MCP tool to decide whether to proceed automatically or pause for user confirmation.

## When to call assess_action

Call it before:
- Writing, modifying, or deleting files
- Running bash commands that change state
- Git operations: commit, push, reset, force operations
- Any database write, update, or drop
- Network requests that send data

Do NOT call it for:
- `file_read`, `bash_read`, `git_log`, `git_status`, `git_diff`, `db_read` action types
- Pure read-only operations (listing directories, viewing logs)

## How to use it

```
relay__assess_action(
    action_type="file_write",
    action_description="Writing updated config to /etc/app/config.yaml"
)
```

If `should_interrupt` is `true`: pause, explain what you're about to do, and wait for the user to confirm.
If `should_interrupt` is `false`: proceed immediately without asking.

**Note:** The first time a new `action_type` is seen (no history), relay will ask once to establish a baseline — except for `low` risk types which always proceed.

## After the user responds — MANDATORY

You MUST always call `relay__record_decision` after the user responds to a confirmation request. This is not optional — without it, relay cannot learn and will keep asking forever.

```
relay__record_decision(
    action_type="file_write",
    action_description="Writing updated config to /etc/app/config.yaml",
    decision="approved",    # or "rejected"
    risk_level="medium"     # use the risk_level returned by assess_action
)
```

Call this even if the user says "no" or "cancel" — record it as `"rejected"`.

## Check what relay has learned

```
relay__get_stats_tool()
```

Returns approval rates per action type and total decision count.

## action_type reference

| action_type | examples |
|---|---|
| `file_read` | reading any file |
| `file_write` | creating or editing files |
| `file_delete` | deleting files |
| `bash_read` | ls, cat, grep, git log |
| `bash_write` | any bash that modifies state |
| `git_commit` | git commit |
| `git_push` | git push |
| `git_reset` | git reset, git checkout -- |
| `git_force_push` | git push --force |
| `db_read` | SELECT queries |
| `db_write` | INSERT, UPDATE |
| `db_drop` | DROP TABLE, DELETE without WHERE |
| `network_request` | curl, API calls that send data |
