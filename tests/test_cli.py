"""CLI tests: run `python3 -m agent_worktree` as a subprocess."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from agent_worktree import skill as skill_mod
from tests.helpers import RepoCase, git

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(os.environ, PYTHONPATH=str(ROOT))


def run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "agent_worktree"] + args,
        cwd=str(cwd), capture_output=True, text=True, env=ENV)


class TestCli(RepoCase):
    def test_new_list_status_done_end_to_end(self):
        r = run_cli(["new", "cli-task"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("created worktree", r.stdout)
        r = run_cli(["list"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cli-task", r.stdout)
        r = run_cli(["status", "cli-task"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ahead:  0", r.stdout)
        r = run_cli(["done", "cli-task"], self.repo)
        self.assertEqual(r.returncode, 2)  # flag required, nothing deleted
        r = run_cli(["done", "cli-task", "--drop"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dropped", r.stdout)

    def test_list_json(self):
        run_cli(["new", "json-task"], self.repo)
        r = run_cli(["list", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual(rows[0]["task"], "json-task")

    def test_check_exit_codes(self):
        run_cli(["new", "gate-task"], self.repo)
        r = run_cli(["check"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PASS", r.stdout)
        orphan = self.repo.parent / "orphan-cli"
        git(["worktree", "add", "-b", "agent/orphan-cli", str(orphan)],
            self.repo)
        r = run_cli(["check"], self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stdout)

    def test_skill_prints_bundled_text(self):
        r = run_cli(["skill"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("One git worktree per agent task", r.stdout)
        self.assertEqual(r.stdout.strip(),
                         skill_mod.SKILL_TEXT.strip())

    def test_adopt_dry_run_via_cli(self):
        manual = self.repo.parent / "repo-twigs" / "manual-cli"
        git(["worktree", "add", "-b", "agent/manual-cli", str(manual)],
            self.repo)
        r = run_cli(["adopt", "--dry-run"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would adopt", r.stdout)
        r = run_cli(["adopt"], self.repo)
        self.assertIn("adopted", r.stdout)

    def test_demo_writes_transcript(self):
        out = Path(self.tmp.name) / "demo-out"
        r = run_cli(["demo", "--out", str(out)], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (out / "demo-run.md").read_text(encoding="utf-8")
        for needle in ("new fix-typo", "done fix-typo --merge",
                       "merged fix-typo", "PASS"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
