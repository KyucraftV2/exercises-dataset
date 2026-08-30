---
name: git-workflow
description: Git workflow rules for this repo (exercises-dataset) — one branch per demand/fix, Conventional Commits with no Claude co-author, branching from main (this repo's real trunk — there is no develop branch here), a pr-reviewer loop-engineering gate before merge, and local merge into main once approved. Apply this to every unit of work.
---

# Git Workflow

## Branching
- ONE branch per demand/feature/fix — never one branch spanning several unrelated changes.
  Prefixes: `feat/`, `fix/`, `chore/`, `refactor/`, `style/`, `docs/`, `test/`.
- Branch from `main` — this repo's actual trunk (confirmed by its merge history; there is no
  `develop` branch here). If a PR is ever opened, it targets `main`.
- Never commit directly to `main` — always go through a branch.

## Commits
- Conventional Commits format: `type(scope): description` (e.g. `fix(auth): redirect 127.0.0.1
  to localhost so Safari keeps the session cookie`, `feat: add partners page`). Types: `feat`,
  `fix`, `chore`, `refactor`, `style`, `docs`, `test`.
- No `Co-Authored-By` trailer — never make Claude a co-author on commits.
- Commit spontaneously as soon as a coherent unit of work is finished — don't wait to be asked.
- Atomic, logical commits: one coherent change per commit rather than one large final commit.

## Review & merge loop (loop engineering)
Every branch goes through this loop before it reaches `main` — no direct merge, ever:

1. **Write the code** on the branch, with Conventional Commits, verified locally
   (`make test`/`make lint`/manual check as relevant to what changed).
2. **PR review**: launch the `pr-reviewer` subagent (`Agent` tool, `subagent_type: "pr-reviewer"`)
   to review the diff between the branch and `main` (use `git diff main...<branch>` — the
   triple-dot form, so a `main` that has moved on with unrelated merges since the branch was cut
   doesn't pollute the diff). It's read-only and returns a verdict: APPROUVÉ or À CORRIGER with a
   list of blocking issues.
3. **If À CORRIGER**: go back to step 1 — fix the blocking issues on the same branch, commit,
   then re-run the review. Repeat until APPROUVÉ. Don't merge on a partial or self-judged fix;
   the loop only ends on an actual APPROUVÉ verdict from the subagent.
4. **If APPROUVÉ**: merge the branch into `main` locally with `--no-ff` and delete the branch
   (`git branch -d`).

- Never `git push` `main` (or any branch) without the user explicitly asking for it — merges
  stay local unless told otherwise.
- Trivial changes (typo fix, doc tweak, single-line config) can skip the loop only if the user
  says so explicitly for that change — the default is always to run it.

## Repo hygiene
- Don't stage or commit unrelated in-progress changes the user hasn't confirmed are finished
  (e.g. a WIP image swap sitting in the working tree) — commit only what belongs to the current
  unit of work, and leave the rest untouched.
