"""Shared test helpers: a throwaway git repo with two commits."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

FIXED_DATE = "2026-11-19T12:00:00+00:00"


def git(args, cwd, env_extra=None):
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = FIXED_DATE
    env["GIT_COMMITTER_DATE"] = FIXED_DATE
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                          text=True, env=env)
    assert proc.returncode == 0, "git %s failed: %s" % (args, proc.stderr)
    return proc.stdout


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aw-test-")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(["init", "-b", "main"], self.repo)
        git(["config", "user.email", "test@example.com"], self.repo)
        git(["config", "user.name", "Test"], self.repo)
        (self.repo / "README.md").write_text("# repo\n", encoding="utf-8")
        git(["add", "."], self.repo)
        git(["commit", "-m", "initial"], self.repo)
        (self.repo / "app.py").write_text("x = 1\n", encoding="utf-8")
        git(["add", "."], self.repo)
        git(["commit", "-m", "add app"], self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def commit_in(self, path, filename, content, message):
        p = Path(path) / filename
        p.write_text(content, encoding="utf-8")
        git(["add", "."], path)
        git(["commit", "-m", message], path)
