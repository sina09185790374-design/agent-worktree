# agent-worktree demo transcript

```
$ agent-worktree new fix-typo
created worktree /tmp/agent-worktree-demo-f_997tpe/demo-repo-twigs/fix-typo on branch agent/fix-typo
$ agent-worktree list
  fix-typo   agent/fix-typo   head=1520b92 dirty=0 ahead=0
$ agent-worktree status fix-typo
  branch=agent/fix-typo head=dcdc034 ahead=1 dirty=0
$ agent-worktree check
  PASS registry consistent: 1 task(s), 2 worktree(s) on disk
$ agent-worktree done fix-typo --merge
merged fix-typo into main; worktree removed
$ agent-worktree check
  PASS registry consistent: 1 task(s), 1 worktree(s) on disk
```
