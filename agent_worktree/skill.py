"""Bundled agent skill, printed by `agent-worktree skill`.

Same text as SKILL.md at the repo root. Give these instructions to an
agent so it picks the right checkout, branch and location, and asks
before cleanup.
"""

SKILL_TEXT = """# agent-worktree skill

One git worktree per agent task. Never work on the main checkout, and
never share a branch between two tasks.

## Start a task

```
agent-worktree new <task> [--base <rev>]
```

- `<task>` is short and kebab-case, e.g. `fix-login-redirect`.
- The worktree lands in `<repo>-twigs/<task>` next to the main checkout,
  on a fresh branch `agent/<task>` from `--base` (default HEAD).
- The tool verifies the new worktree HEAD equals the base before it
  registers the task. If it refuses, read the reason — do not retry
  with a different name to dodge it.

## While working

- Work only inside that worktree. Commit there; the main checkout stays
  clean so another task can merge.
- `agent-worktree status <task>` shows dirty files and commits ahead of
  the base. `agent-worktree list` shows every task at once.

## Finish a task

```
agent-worktree done <task> --merge   # fast-forward the branch into main
agent-worktree done <task> --drop    # throw the branch away
```

- `--merge` refuses a dirty worktree, a dirty main checkout, and anything
  that is not a fast-forward. Resolve it in the worktree, then retry.
- `--drop` refuses a dirty worktree, always. It refuses unmerged commits
  unless you pass `--force` — and `--force` never overrides dirty.
- Bare `done` without a flag only prints the plan. Choose explicitly.

## Existing worktrees

- `agent-worktree adopt --dry-run` previews unregistered worktrees;
  `agent-worktree adopt` registers them. It never moves anything.
- `agent-worktree check` is the CI gate: registry and disk must agree,
  no orphan worktrees, no finished task left on disk.

## Never

- Never delete a worktree directory by hand (`rm -rf`) — the registry
  will disagree with disk and `check` will fail.
- Never `git worktree remove` a registered worktree directly; use `done`.
- Never work on a branch another task owns.
"""
