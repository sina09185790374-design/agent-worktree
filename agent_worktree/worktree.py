"""Core logic for agent-worktree: one git worktree per agent task.

Stdlib only. All git interaction goes through ``run_git`` (subprocess).
State lives in the repository's common git dir
(``<common>/.agent-worktree/registry.json``) so it is reachable from any
worktree of the same repo and never pollutes a working tree.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

VERSION = "0.1.0"

TASK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
BRANCH_PREFIX = "agent/"


class WorktreeError(Exception):
    """A refused operation: explains why, never deletes anything."""


def run_git(args, cwd, env_extra=None):
    """Run git; return stdout. Raise WorktreeError on failure."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise WorktreeError(
            "git %s failed: %s" % (" ".join(args), proc.stderr.strip())
        )
    return proc.stdout


def git_common_dir(cwd):
    out = run_git(["rev-parse", "--git-common-dir"], cwd).strip()
    p = Path(out)
    if not p.is_absolute():
        p = Path(cwd) / p
    return p.resolve()


def repo_name(cwd):
    out = run_git(["rev-parse", "--show-toplevel"], cwd).strip()
    return Path(out).name


def main_worktree_path(cwd):
    """Path of the main checkout (first entry of `git worktree list`)."""
    entries = list_worktrees(cwd)
    if not entries:
        raise WorktreeError("no worktrees found for this repository")
    return Path(entries[0]["path"])


def registry_path(cwd):
    return git_common_dir(cwd) / ".agent-worktree" / "registry.json"


def load_registry(cwd):
    path = registry_path(cwd)
    if not path.exists():
        return {"version": 1, "worktrees_dir": None, "tasks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WorktreeError("registry is unreadable (%s): %s" % (path, exc))
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), dict):
        raise WorktreeError("registry is corrupt: %s" % path)
    return data


def save_registry(cwd, data):
    path = registry_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def default_worktrees_dir(cwd):
    main = main_worktree_path(cwd)
    return main.parent / (main.name + "-twigs")


def resolve_worktrees_dir(cwd, data, override=None):
    if override:
        return Path(override).expanduser().resolve()
    if data.get("worktrees_dir"):
        return Path(data["worktrees_dir"])
    return default_worktrees_dir(cwd)


def sanitize_task(task):
    """Turn a free-form task label into a registry key / branch suffix."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", task.strip()).strip("-.")
    cleaned = re.sub(r"-{2,}", "-", cleaned).lower()
    return cleaned or "task"


def validate_task(task):
    if not TASK_RE.match(task):
        raise WorktreeError(
            "bad task name %r: use letters, digits, '.', '_' or '-', "
            "starting with a letter or digit (max 64 chars)" % task
        )


def branch_for(task):
    return BRANCH_PREFIX + task


def list_worktrees(cwd):
    """Parse `git worktree list --porcelain` into dicts."""
    out = run_git(["worktree", "list", "--porcelain"], cwd)
    entries, cur = [], {}
    for line in out.splitlines():
        if not line.strip():
            if cur:
                entries.append(cur)
                cur = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            cur["path"] = value
        elif key == "HEAD":
            cur["head"] = value
        elif key == "branch":
            cur["branch"] = value.replace("refs/heads/", "", 1)
        elif key == "bare":
            cur["bare"] = True
        elif key == "detached":
            cur["detached"] = True
    if cur:
        entries.append(cur)
    return entries


def worktree_info(cwd, path):
    """HEAD, dirty files and ahead/behind vs the task's base, for one path."""
    head = run_git(["rev-parse", "--short", "HEAD"], path).strip()
    dirty = run_git(["status", "--porcelain"], path).splitlines()
    return {"head": head, "dirty": [d for d in dirty if d.strip()]}


def ahead_behind(cwd, base, head_ref):
    out = run_git(
        ["rev-list", "--left-right", "--count", "%s...%s" % (base, head_ref)],
        cwd,
    ).strip()
    behind, ahead = out.split()
    return int(ahead), int(behind)


def new_task(cwd, task, branch=None, base="HEAD", worktrees_dir=None):
    """Create a branch + worktree for a task and register it."""
    validate_task(task)
    data = load_registry(cwd)
    if task in data["tasks"] and data["tasks"][task].get("status") == "active":
        raise WorktreeError("task %r already has an active worktree" % task)
    branch = branch or branch_for(task)
    existing = run_git(["branch", "--list", branch], cwd).strip()
    if existing:
        raise WorktreeError("branch %r already exists" % branch)
    base_sha = run_git(["rev-parse", base], cwd).strip()
    wdir = resolve_worktrees_dir(cwd, data, worktrees_dir)
    path = wdir / task
    if path.exists():
        raise WorktreeError("worktree path already exists: %s" % path)
    wdir.mkdir(parents=True, exist_ok=True)
    try:
        run_git(["worktree", "add", "-b", branch, str(path), base_sha], cwd)
    except WorktreeError:
        raise
    # Verify the clone matches the requested base before registering.
    head = run_git(["rev-parse", "HEAD"], path).strip()
    if head != base_sha:
        run_git(["worktree", "remove", "--force", str(path)], cwd)
        raise WorktreeError(
            "new worktree HEAD %s != requested base %s; removed" % (head, base_sha)
        )
    data["worktrees_dir"] = str(wdir)
    data["tasks"][task] = {
        "branch": branch,
        "path": str(path),
        "base": base_sha,
        "status": "active",
    }
    save_registry(cwd, data)
    return data["tasks"][task]


def task_entry(cwd, task):
    data = load_registry(cwd)
    entry = data["tasks"].get(task)
    if entry is None:
        raise WorktreeError("unknown task %r (see `list`)" % task)
    if entry.get("status") != "active":
        raise WorktreeError(
            "task %r is already %s" % (task, entry.get("status"))
        )
    return data, entry


def list_tasks(cwd):
    """Registry tasks enriched with live git state."""
    data = load_registry(cwd)
    on_disk = {e["path"]: e for e in list_worktrees(cwd)}
    rows = []
    for task in sorted(data["tasks"]):
        entry = data["tasks"][task]
        row = {"task": task, **entry}
        disk = on_disk.get(entry["path"])
        if disk is None:
            row["on_disk"] = False
            row["head"] = None
            row["dirty"] = None
            row["ahead"] = None
            row["behind"] = None
        else:
            row["on_disk"] = True
            info = worktree_info(cwd, entry["path"])
            row["head"] = info["head"]
            row["dirty"] = len(info["dirty"])
            try:
                ahead, behind = ahead_behind(
                    cwd, entry["base"], entry["branch"])
            except WorktreeError:
                ahead, behind = None, None
            row["ahead"] = ahead
            row["behind"] = behind
        rows.append(row)
    return rows


def status_task(cwd, task):
    data, entry = task_entry(cwd, task)
    info = worktree_info(cwd, entry["path"])
    ahead, behind = ahead_behind(cwd, entry["base"], entry["branch"])
    return {
        "task": task,
        "branch": entry["branch"],
        "path": entry["path"],
        "base": entry["base"][:12],
        "head": info["head"],
        "dirty_files": info["dirty"],
        "ahead": ahead,
        "behind": behind,
    }


def _remove_worktree_and_branch(cwd, entry, delete_branch=True):
    path = entry["path"]
    run_git(["worktree", "remove", "--force", path], cwd)
    if delete_branch:
        run_git(["branch", "-D", entry["branch"]], cwd)


def done_task(cwd, task, mode, force=False):
    """Finish a task: --merge (ff-only into its base) or --drop."""
    if mode not in ("merge", "drop"):
        raise WorktreeError("done needs --merge or --drop")
    data, entry = task_entry(cwd, task)
    info = worktree_info(cwd, entry["path"])
    if info["dirty"]:
        raise WorktreeError(
            "task %r has %d uncommitted change(s); commit or stash first — "
            "nothing was deleted" % (task, len(info["dirty"]))
        )
    ahead, _ = ahead_behind(cwd, entry["base"], entry["branch"])
    main = main_worktree_path(cwd)
    if mode == "merge":
        if ahead == 0:
            raise WorktreeError(
                "task %r has no commits ahead of its base; nothing to merge"
                % task
            )
        main_dirty = run_git(["status", "--porcelain"], main).splitlines()
        if [d for d in main_dirty if d.strip()]:
            raise WorktreeError(
                "main checkout %s is dirty; commit or stash first" % main
            )
        # ff-only: refuse instead of creating a merge commit.
        run_git(["merge", "--ff-only", entry["branch"]], main)
        _remove_worktree_and_branch(cwd, entry)
        entry["status"] = "merged"
    else:  # drop
        if ahead > 0 and not force:
            raise WorktreeError(
                "task %r has %d unmerged commit(s); pass --force to drop them"
                % (task, ahead)
            )
        _remove_worktree_and_branch(cwd, entry)
        entry["status"] = "dropped"
    save_registry(cwd, data)
    return entry


def adopt_tasks(cwd, worktrees_dir=None, dry_run=False):
    """Register on-disk worktrees the registry does not know about."""
    data = load_registry(cwd)
    known_paths = {e["path"] for e in data["tasks"].values()}
    known_branches = {e["branch"] for e in data["tasks"].values()}
    entries = list_worktrees(cwd)
    plan = []
    for entry in entries[1:]:  # first entry is the main checkout
        if entry.get("bare") or entry.get("detached"):
            continue
        if entry["path"] in known_paths:
            continue
        branch = entry.get("branch")
        if not branch or branch in known_branches:
            continue
        task = sanitize_task(branch.split("/")[-1])
        suffix = 2
        base_task = task
        while task in data["tasks"]:
            task = "%s-%d" % (base_task, suffix)
            suffix += 1
        head = entry.get("head", "")
        plan.append({
            "task": task,
            "branch": branch,
            "path": entry["path"],
            "base": head,
            "status": "active",
        })
    if dry_run:
        return plan, []
    for item in plan:
        data["tasks"][item["task"]] = item
    if worktrees_dir:
        data["worktrees_dir"] = str(Path(worktrees_dir).expanduser().resolve())
    save_registry(cwd, data)
    return plan, plan
