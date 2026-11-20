# agent-worktree

One git worktree per agent task: a small stdlib-only CLI that gives every
agent task its own isolated checkout on its own branch — so parallel agents
never step on each other's files, and finishing a task is one explicit
command. No network, no keys, no dependencies.

**Pattern** (original code; pattern only, learned from today's radar):
leostera/git-twig gives agents cheap lightweight worktrees — up to 97% less
disk through copy-on-write sharing — plus a bundled skill the agent reads,
an `adopt` flow that organizes existing worktrees instead of moving them
blindly, verification that a new checkout matches the requested commit,
and recovery journals so a failed attempt leaves inspectable state instead
of a half-moved tree. This tool is that idea as a small local Python CLI:
`new` creates the worktree and verifies it, `list`/`status` show live
state, `done --merge` fast-forwards the branch into main, `done --drop`
throws it away, `adopt` registers worktrees it did not create, and
`check` is the CI gate that keeps the registry and the disk in agreement.

## How it works

1. **New.** `new <task>` creates branch `agent/<task>` from `--base`
   (default HEAD) and a worktree at `<repo>-twigs/<task>` beside the main
   checkout. It verifies the new worktree's HEAD equals the base before
   registering the task — if the check fails, the worktree is removed and
   nothing is registered.
2. **Work.** Commit inside the worktree. The main checkout stays clean,
   so another task can merge at any time.
3. **Finish.** `done <task> --merge` fast-forwards the branch into main
   (refuses dirty worktrees, a dirty main checkout, and non-fast-forward
   merges), then removes the worktree and the branch. `done <task> --drop`
   removes both without merging — it refuses dirty worktrees always, and
   refuses unmerged commits unless you pass `--force` (`--force` never
   overrides dirty).
4. **Adopt.** `adopt --dry-run` previews worktrees on disk that the
   registry never heard of; `adopt` registers them. It never moves
   anything.
5. **Check.** CI gate: every registered active worktree must exist on
   disk on the right branch, no two tasks may share a branch, no orphan
   worktree may sit unregistered, and no finished task may still be on
   disk. A dirty worktree is normal work in progress and never fails.

State lives in the repository's common git dir
(`.git/.agent-worktree/registry.json`), so it is reachable from any
worktree of the same repo and never pollutes a working tree.

## Usage

```bash
python3 -m agent_worktree new fix-login-redirect
python3 -m agent_worktree new refactor-auth -b custom/auth --base HEAD~2
python3 -m agent_worktree list
python3 -m agent_worktree list --json
python3 -m agent_worktree status fix-login-redirect
python3 -m agent_worktree done fix-login-redirect --merge
python3 -m agent_worktree done experiment-x --drop --force
python3 -m agent_worktree adopt --dry-run
python3 -m agent_worktree adopt
python3 -m agent_worktree check
python3 -m agent_worktree skill
python3 -m agent_worktree demo --out examples
```

Exit codes: 0 success, 1 refused operation / `check` failed, 2 bad input.
`skill` prints the bundled agent instructions (also in `SKILL.md`) — give
them to an agent so it picks the right checkout and asks before cleanup.

## Tests

```bash
python3 -m unittest discover -s tests -v   # 27 tests, real throwaway git repos
```

---

# agent-worktree (فارسی)

به‌ازای هر وظیفهٔ ایجنت، یک ورک‌تری گیت جدا: یک CLI کوچک فقط با
کتابخانهٔ استاندارد پایتون که به هر وظیفهٔ ایجنت یک چک‌اوت جدا روی
برانچ خودش می‌دهد — تا ایجنت‌های موازی روی فایل‌های هم پا نگذارند و
تمام‌کردن یک وظیفه فقط یک دستور صریح باشد. بدون شبکه، بدون کلید، بدون
وابستگی.

**الگو** (کد اصلی؛ فقط الگو، یادگرفته‌شده از رادار امروز):
leostera/git-twig به ایجنت‌ها ورک‌تری‌های سبک و ارزان می‌دهد — تا ۹۷٪
فضای کمتر با اشتراک copy-on-write — به‌همراه یک اسکیل آماده که ایجنت
می‌خواند، جریان `adopt` که ورک‌تری‌های موجود را به‌جای جابه‌جایی کورکورانه
سازمان می‌دهد، اعتبارسنجی اینکه چک‌اوت جدید دقیقاً همان کمیتی است که
خواسته شده، و ژورنال بازیابی تا تلاش ناموفق به‌جای درخت نیمه‌جابه‌جا‌شده،
وضعیتی قابل‌بازرسی باقی بگذارد. این ابزار همان ایده است در قالب یک CLI
کوچک پایتون: `new` ورک‌تری را می‌سازد و اعتبارسنجی می‌کند، `list` و
`status` وضعیت زنده را نشان می‌دهند، `done --merge` برانچ را fast-forward
به main می‌کند، `done --drop` آن را دور می‌اندازد، `adopt` ورک‌تری‌هایی را
که خودش نساخته ثبت می‌کند، و `check` گیت CI است که رجیستری و دیسک را در
توافق نگه می‌دارد.

## روش کار

۱. **ساخت.** `new <task>` برانچ `agent/<task>` را از `--base` (پیش‌فرض
HEAD) می‌سازد و ورک‌تری را در `<repo>-twigs/<task>` کنار چک‌اوت اصلی قرار
می‌دهد. پیش از ثبت وظیفه بررسی می‌کند که HEAD ورک‌تری جدید دقیقاً همان
base باشد — اگر بررسی شکست بخورد، ورک‌تری حذف می‌شود و چیزی ثبت نمی‌شود.
۲. **کار.** داخل ورک‌تری کامیت کنید. چک‌اوت اصلی تمیز می‌ماند تا وظیفهٔ
دیگر هر وقت خواست مرج شود.
۳. **پایان.** `done <task> --merge` برانچ را fast-forward به main می‌کند
(ورک‌تری کثیف، چک‌اوت اصلی کثیف و مرج غیر fast-forward را رد می‌کند)، بعد
ورک‌تری و برانچ را حذف می‌کند. `done <task> --drop` هر دو را بدون مرج حذف
می‌کند — ورک‌تری کثیف را همیشه رد می‌کند و کامیت‌های مرج‌نشده را بدون
`--force` رد می‌کند (`--force` هرگز جای کثیف‌بودن را نمی‌گیرد).
۴. **پذیرش.** `adopt --dry-run` ورک‌تری‌های روی دیسک را که رجیستری
نمی‌شناسد پیش‌نمایش می‌دهد؛ `adopt` آن‌ها را ثبت می‌کند. هیچ‌چیز را
جابه‌جا نمی‌کند.
۵. **بررسی.** گیت CI: هر ورک‌تری فعال ثبت‌شده باید روی دیسک با برانچ درست
وجود داشته باشد، هیچ دو وظیفه‌ای یک برانچ مشترک ندارند، هیچ ورک‌تری
یتیمی بدون ثبت نمی‌ماند و هیچ وظیفهٔ تمام‌شده‌ای نباید روی دیسک باشد.
ورک‌تری کثیف یعنی کار در جریان است و هرگز گیت را رد نمی‌کند.

وضعیت در دایرکتوری مشترک گیت ریپو ذخیره می‌شود
(`.git/.agent-worktree/registry.json`)، پس از هر ورک‌تری همان ریپو در
دسترس است و درخت کاری را آلوده نمی‌کند.

## تست‌ها

```bash
python3 -m unittest discover -s tests -v   # ۲۷ تست، با ریپوهای واقعی و موقت گیت
```

## License

MIT — see `LICENSE`.
