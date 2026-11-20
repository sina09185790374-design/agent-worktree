"""CLI for agent-worktree: one git worktree per agent task.

Usage:
  python3 -m agent_worktree new <task> [-b branch] [--base REV]
  python3 -m agent_worktree list [--json]
  python3 -m agent_worktree status <task>
  python3 -m agent_worktree done <task> --merge | --drop [--force]
  python3 -m agent_worktree adopt [--dry-run]
  python3 -m agent_worktree check
  python3 -m agent_worktree skill
  python3 -m agent_worktree demo --out DIR

Exit codes: 0 success, 1 refused operation / check failed, 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import checks as check_mod
from . import skill as skill_mod
from . import worktree as wt
from .worktree import WorktreeError

FIXED_DATE = "2026-11-19T12:00:00+00:00"


def _demo_env():
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = FIXED_DATE
    env["GIT_COMMITTER_DATE"] = FIXED_DATE
    return env


def _demo_git(args, cwd):
    proc = subprocess.run(
        ["git"] + args, cwd=str(cwd), capture_output=True, text=True,
        env=_demo_env(),
    )
    if proc.returncode != 0:
        raise WorktreeError("demo git %s failed: %s"
                            % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def cmd_demo(out):
    """Build a throwaway repo, run the real commands, write a transcript."""
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    tmp = Path(tempfile.mkdtemp(prefix="agent-worktree-demo-"))
    lines = []
    try:
        repo = tmp / "demo-repo"
        repo.mkdir()
        _demo_git(["init", "-b", "main"], repo)
        _demo_git(["config", "user.email", "demo@example.com"], repo)
        _demo_git(["config", "user.name", "Demo"], repo)
        (repo / "README.md").write_text("# demo\n", encoding="utf-8")
        _demo_git(["add", "."], repo)
        _demo_git(["commit", "-m", "initial commit"], repo)
        lines.append("$ agent-worktree new fix-typo")
        entry = wt.new_task(repo, "fix-typo")
        lines.append("created worktree %s on branch %s"
                     % (entry["path"], entry["branch"]))
        lines.append("$ agent-worktree list")
        for row in wt.list_tasks(repo):
            lines.append("  %-10s %-16s head=%s dirty=%s ahead=%s"
                         % (row["task"], row["branch"], row["head"],
                            row["dirty"], row["ahead"]))
        wt_path = Path(entry["path"])
        (wt_path / "README.md").write_text("# demo\n\nfixed.\n",
                                            encoding="utf-8")
        _demo_git(["add", "."], wt_path)
        _demo_git(["commit", "-m", "fix typo"], wt_path)
        lines.append("$ agent-worktree status fix-typo")
        st = wt.status_task(repo, "fix-typo")
        lines.append("  branch=%s head=%s ahead=%d dirty=%d"
                     % (st["branch"], st["head"], st["ahead"],
                        len(st["dirty_files"])))
        lines.append("$ agent-worktree check")
        for ok, msg in check_mod.run_checks(repo):
            lines.append("  %s %s" % ("PASS" if ok else "FAIL", msg))
        lines.append("$ agent-worktree done fix-typo --merge")
        wt.done_task(repo, "fix-typo", "merge")
        lines.append("merged fix-typo into main; worktree removed")
        lines.append("$ agent-worktree check")
        for ok, msg in check_mod.run_checks(repo):
            lines.append("  %s %s" % ("PASS" if ok else "FAIL", msg))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    transcript = "\n".join(lines) + "\n"
    (out / "demo-run.md").write_text(
        "# agent-worktree demo transcript\n\n```\n" + transcript + "```\n",
        encoding="utf-8")
    print(transcript, end="")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="agent-worktree",
        description="One git worktree per agent task.")
    p.add_argument("--version", action="version",
                   version="agent-worktree %s" % wt.VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="create a worktree for a task")
    s.add_argument("task")
    s.add_argument("-b", "--branch")
    s.add_argument("--base", default="HEAD")
    s.add_argument("--worktrees-dir")

    s = sub.add_parser("list", help="list registered tasks with live state")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("status", help="show one task's state")
    s.add_argument("task")

    s = sub.add_parser("done", help="finish a task")
    s.add_argument("task")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--merge", action="store_true")
    g.add_argument("--drop", action="store_true")
    s.add_argument("--force", action="store_true",
                   help="drop unmerged commits (never overrides dirty)")

    s = sub.add_parser("adopt", help="register existing unregistered worktrees")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--worktrees-dir")

    sub.add_parser("check", help="CI gate: registry and disk must agree")
    sub.add_parser("skill", help="print the bundled agent skill")

    s = sub.add_parser("demo", help="run a deterministic demo, write transcript")
    s.add_argument("--out", required=True)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cwd = Path.cwd()
    try:
        if args.cmd == "new":
            entry = wt.new_task(cwd, args.task, branch=args.branch,
                                base=args.base,
                                worktrees_dir=args.worktrees_dir)
            print("created worktree %s on branch %s"
                  % (entry["path"], entry["branch"]))
        elif args.cmd == "list":
            rows = wt.list_tasks(cwd)
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                print("%-16s %-18s %-8s %-6s %-6s %s" % (
                    "TASK", "BRANCH", "HEAD", "DIRTY", "AHEAD", "PATH"))
                for r in rows:
                    print("%-16s %-18s %-8s %-6s %-6s %s" % (
                        r["task"], r["branch"], r["head"] or "-",
                        "-" if r["dirty"] is None else r["dirty"],
                        "-" if r["ahead"] is None else r["ahead"],
                        r["path"]))
        elif args.cmd == "status":
            st = wt.status_task(cwd, args.task)
            print("task:   %s" % st["task"])
            print("branch: %s" % st["branch"])
            print("path:   %s" % st["path"])
            print("base:   %s  head: %s" % (st["base"], st["head"]))
            print("ahead:  %d  behind: %d" % (st["ahead"], st["behind"]))
            print("dirty:  %d file(s)" % len(st["dirty_files"]))
            for f in st["dirty_files"]:
                print("  %s" % f)
        elif args.cmd == "done":
            mode = "merge" if args.merge else "drop"
            entry = wt.done_task(cwd, args.task, mode, force=args.force)
            print("task %r %s; worktree removed" % (args.task, entry["status"]))
        elif args.cmd == "adopt":
            plan, applied = wt.adopt_tasks(
                cwd, worktrees_dir=args.worktrees_dir, dry_run=args.dry_run)
            if not plan:
                print("nothing to adopt")
            for item in plan:
                print("%s task %r branch %r at %s"
                      % ("would adopt" if args.dry_run else "adopted",
                         item["task"], item["branch"], item["path"]))
        elif args.cmd == "check":
            failed = False
            for ok, msg in check_mod.run_checks(cwd):
                print("%s %s" % ("PASS" if ok else "FAIL", msg))
                failed = failed or not ok
            return 1 if failed else 0
        elif args.cmd == "skill":
            print(skill_mod.SKILL_TEXT)
        elif args.cmd == "demo":
            return cmd_demo(args.out)
        return 0
    except WorktreeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
