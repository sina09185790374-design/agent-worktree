"""Tests for agent_worktree.worktree + checks (real git repos)."""

import json
import unittest
from pathlib import Path

from agent_worktree import checks, worktree as wt
from agent_worktree.worktree import WorktreeError
from tests.helpers import RepoCase, git


class TestNew(RepoCase):
    def test_new_creates_worktree_branch_and_registry(self):
        entry = wt.new_task(self.repo, "fix-typo")
        self.assertEqual(entry["branch"], "agent/fix-typo")
        self.assertTrue(Path(entry["path"]).is_dir())
        self.assertEqual(
            git(["rev-parse", "HEAD"], entry["path"]).strip(), entry["base"])
        reg = json.loads(wt.registry_path(self.repo).read_text())
        self.assertEqual(reg["tasks"]["fix-typo"]["status"], "active")

    def test_new_twice_refused(self):
        wt.new_task(self.repo, "fix-typo")
        with self.assertRaises(WorktreeError):
            wt.new_task(self.repo, "fix-typo")

    def test_new_existing_branch_refused(self):
        git(["branch", "agent/other"], self.repo)
        with self.assertRaises(WorktreeError):
            wt.new_task(self.repo, "other")

    def test_new_bad_task_name_refused(self):
        for bad in ("", "has space", "../escape", "a" * 65):
            with self.assertRaises(WorktreeError, msg=bad):
                wt.new_task(self.repo, bad)

    def test_new_with_explicit_branch_and_base(self):
        base = git(["rev-parse", "HEAD~1"], self.repo).strip()
        entry = wt.new_task(self.repo, "old-base", branch="custom/x",
                            base="HEAD~1")
        self.assertEqual(entry["branch"], "custom/x")
        self.assertEqual(entry["base"], base)


class TestListStatus(RepoCase):
    def test_list_and_status_clean_then_dirty_then_ahead(self):
        entry = wt.new_task(self.repo, "feat-a")
        rows = wt.list_tasks(self.repo)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dirty"], 0)
        self.assertEqual(rows[0]["ahead"], 0)
        st = wt.status_task(self.repo, "feat-a")
        self.assertEqual(st["ahead"], 0)
        self.assertEqual(st["dirty_files"], [])
        # dirty file
        (Path(entry["path"]) / "app.py").write_text("x = 2\n")
        self.assertEqual(wt.status_task(self.repo, "feat-a")["dirty_files"],
                         [" M app.py"])
        # commit it
        self.commit_in(entry["path"], "app.py", "x = 2\n", "bump x")
        st = wt.status_task(self.repo, "feat-a")
        self.assertEqual(st["ahead"], 1)
        self.assertEqual(st["dirty_files"], [])

    def test_status_unknown_task_refused(self):
        with self.assertRaises(WorktreeError):
            wt.status_task(self.repo, "nope")


class TestDone(RepoCase):
    def test_done_merge_merges_and_removes(self):
        entry = wt.new_task(self.repo, "feat-b")
        self.commit_in(entry["path"], "new.txt", "hi\n", "add new")
        wt.done_task(self.repo, "feat-b", "merge")
        self.assertIn("new.txt",
                      git(["ls-files"], self.repo).splitlines())
        self.assertFalse(Path(entry["path"]).exists())
        self.assertEqual(
            git(["branch", "--list", "agent/feat-b"], self.repo).strip(), "")
        reg = json.loads(wt.registry_path(self.repo).read_text())
        self.assertEqual(reg["tasks"]["feat-b"]["status"], "merged")

    def test_done_merge_refuses_dirty_worktree(self):
        entry = wt.new_task(self.repo, "feat-c")
        (Path(entry["path"]) / "app.py").write_text("x = 9\n")
        with self.assertRaises(WorktreeError):
            wt.done_task(self.repo, "feat-c", "merge")
        self.assertTrue(Path(entry["path"]).exists())  # nothing deleted

    def test_done_merge_refuses_nothing_to_merge(self):
        wt.new_task(self.repo, "feat-d")
        with self.assertRaises(WorktreeError):
            wt.done_task(self.repo, "feat-d", "merge")

    def test_done_merge_refuses_dirty_main(self):
        entry = wt.new_task(self.repo, "feat-e")
        self.commit_in(entry["path"], "new.txt", "hi\n", "add new")
        (self.repo / "README.md").write_text("# dirty main\n")
        with self.assertRaises(WorktreeError):
            wt.done_task(self.repo, "feat-e", "merge")

    def test_done_drop_clean_unmerged_needs_force(self):
        entry = wt.new_task(self.repo, "feat-f")
        self.commit_in(entry["path"], "new.txt", "hi\n", "add new")
        with self.assertRaises(WorktreeError):
            wt.done_task(self.repo, "feat-f", "drop")
        wt.done_task(self.repo, "feat-f", "drop", force=True)
        self.assertFalse(Path(entry["path"]).exists())

    def test_done_drop_refuses_dirty_even_with_force(self):
        entry = wt.new_task(self.repo, "feat-g")
        (Path(entry["path"]) / "app.py").write_text("x = 9\n")
        with self.assertRaises(WorktreeError):
            wt.done_task(self.repo, "feat-g", "drop", force=True)
        self.assertTrue(Path(entry["path"]).exists())

    def test_done_twice_refused(self):
        entry = wt.new_task(self.repo, "feat-h")
        self.commit_in(entry["path"], "new.txt", "hi\n", "add new")
        wt.done_task(self.repo, "feat-h", "merge")
        with self.assertRaises(WorktreeError):
            wt.done_task(self.repo, "feat-h", "merge")


class TestAdopt(RepoCase):
    def test_adopt_dry_run_changes_nothing_then_adopts(self):
        wt.new_task(self.repo, "known")
        manual = self.repo.parent / "repo-twigs" / "manual"
        git(["worktree", "add", "-b", "agent/manual", str(manual)], self.repo)
        plan, _ = wt.adopt_tasks(self.repo, dry_run=True)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["task"], "manual")
        reg = json.loads(wt.registry_path(self.repo).read_text())
        self.assertNotIn("manual", reg["tasks"])
        plan, applied = wt.adopt_tasks(self.repo)
        self.assertEqual(len(applied), 1)
        reg = json.loads(wt.registry_path(self.repo).read_text())
        self.assertEqual(reg["tasks"]["manual"]["branch"], "agent/manual")

    def test_adopt_skips_main_and_detached(self):
        detached = self.repo.parent / "detached-wt"
        git(["worktree", "add", "--detach", str(detached)], self.repo)
        plan, _ = wt.adopt_tasks(self.repo)
        self.assertEqual(plan, [])


class TestChecks(RepoCase):
    def test_check_passes_when_healthy(self):
        wt.new_task(self.repo, "ok-one")
        findings = checks.run_checks(self.repo)
        self.assertTrue(all(ok for ok, _ in findings))

    def test_check_fails_on_missing_worktree(self):
        entry = wt.new_task(self.repo, "gone")
        git(["worktree", "remove", "--force", entry["path"]], self.repo)
        findings = checks.run_checks(self.repo)
        self.assertTrue(any(not ok for ok, _ in findings))

    def test_check_fails_on_orphan(self):
        orphan = self.repo.parent / "orphan-wt"
        git(["worktree", "add", "-b", "agent/orphan", str(orphan)], self.repo)
        findings = checks.run_checks(self.repo)
        self.assertTrue(any(not ok and "orphan" in msg
                            for ok, msg in findings))

    def test_check_fails_on_finished_task_left_on_disk(self):
        entry = wt.new_task(self.repo, "stale")
        self.commit_in(entry["path"], "new.txt", "hi\n", "add new")
        wt.done_task(self.repo, "stale", "merge")
        # simulate a stale re-creation: put the worktree back by hand
        git(["worktree", "add", "-b", "agent/stale",
             entry["path"]], self.repo)
        findings = checks.run_checks(self.repo)
        self.assertTrue(any(not ok for ok, _ in findings))

    def test_check_dirty_is_not_a_failure(self):
        entry = wt.new_task(self.repo, "dirty-ok")
        (Path(entry["path"]) / "app.py").write_text("x = 3\n")
        findings = checks.run_checks(self.repo)
        self.assertTrue(all(ok for ok, _ in findings))


if __name__ == "__main__":
    unittest.main()
