"""Run agent-worktree as a module: python3 -m agent_worktree ..."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
