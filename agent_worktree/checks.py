"""CI gate for agent-worktree registries: structural checks only.

A dirty worktree is normal work in progress and never fails the gate.
What fails: a registered worktree missing from disk, an on-disk worktree
the registry never heard of, two tasks on one branch, or a finished task
whose worktree is still on disk.
"""

from __future__ import annotations

from . import worktree as wt


def run_checks(cwd):
    """Return a list of (ok, message) findings; empty means nothing found."""
    findings = []
    try:
        data = wt.load_registry(cwd)
    except wt.WorktreeError as exc:
        return [(False, "registry unreadable: %s" % exc)]
    try:
        on_disk = wt.list_worktrees(cwd)
    except wt.WorktreeError as exc:
        return [(False, "git worktree list failed: %s" % exc)]
    by_path = {e["path"]: e for e in on_disk}
    main_path = on_disk[0]["path"] if on_disk else None

    seen_branches = {}
    for task in sorted(data["tasks"]):
        entry = data["tasks"][task]
        branch = entry.get("branch")
        if branch in seen_branches:
            findings.append((False, "tasks %r and %r share branch %r"
                             % (seen_branches[branch], task, branch)))
        else:
            seen_branches[branch] = task
        disk = by_path.get(entry.get("path", ""))
        if entry.get("status") == "active":
            if disk is None:
                findings.append((False, "task %r: registered worktree missing "
                                 "from disk: %s" % (task, entry.get("path"))))
            elif disk.get("branch") != branch:
                findings.append((False, "task %r: disk branch %r != "
                                 "registered %r"
                                 % (task, disk.get("branch"), branch)))
        else:
            if disk is not None:
                findings.append((False, "task %r is %s but its worktree is "
                                 "still on disk: %s"
                                 % (task, entry.get("status"),
                                    entry.get("path"))))
    known_paths = {e.get("path") for e in data["tasks"].values()}
    for entry in on_disk[1:]:  # skip the main checkout
        if entry.get("bare") or entry.get("detached"):
            continue
        if entry["path"] not in known_paths:
            findings.append((False, "orphan worktree on disk, not in "
                             "registry: %s (branch %s) — run `adopt`"
                             % (entry["path"], entry.get("branch"))))
    if not findings:
        findings.append((True, "registry consistent: %d task(s), %d "
                         "worktree(s) on disk"
                         % (len(data["tasks"]), len(on_disk))))
    return findings
