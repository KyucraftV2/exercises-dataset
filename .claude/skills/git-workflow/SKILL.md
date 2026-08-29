---
name: git-workflow
description: Git workflow rules for the TNT (Thursday Night Tournament) project — one branch per demand/fix, Conventional Commits with no Claude co-author, branching from develop (not main), a pr-reviewer loop-engineering gate before merge, and local merge into develop once approved. Apply this to every unit of work.
---

# Git Workflow

## Branching
- ONE branch per demand/feature/fix — never one branch spanning several unrelated changes.
  Prefixes: `feat/`, `fix/`, `chore/`, `refactor/`, `style/`, `docs/`, `test/`.
- Branch from `develop`, not `main`. If a PR is ever opened, it targets `develop`.
- Never commit directly to `develop` or `main` — always go through a branch.

## Commits
- Conventional Commits format: `type(scope): description` (e.g. `fix(admin): valider le token
  côté serveur avant d'afficher le panel`, `feat: add partners page`). Types: `feat`, `fix`,
  `chore`, `refactor`, `style`, `docs`, `test`.
- No `Co-Authored-By` trailer — never make Claude a co-author on commits.
- Commit spontaneously as soon as a coherent unit of work is finished — don't wait to be asked.
- Atomic, logical commits: one coherent change per commit rather than one large final commit.

## Review & merge loop (loop engineering)
Every branch goes through this loop before it reaches `develop` — no direct merge, ever:

1. **Write the code** on the branch, with Conventional Commits, verified locally
   (typecheck/lint/tests/manual check as relevant to what changed).
2. **PR review**: launch the `pr-reviewer` subagent (`Agent` tool, `subagent_type: "pr-reviewer"`)
   to review the diff between the branch and `develop`. It's read-only and returns a verdict:
   APPROUVÉ or À CORRIGER with a list of blocking issues.
3. **If À CORRIGER**: go back to step 1 — fix the blocking issues on the same branch, commit,
   then re-run the review. Repeat until APPROUVÉ. Don't merge on a partial or self-judged fix;
   the loop only ends on an actual APPROUVÉ verdict from the subagent.
4. **If APPROUVÉ**: merge the branch into `develop` locally with `--no-ff` and delete the branch
   (`git branch -d`).

- Never `git push` `develop` (or any branch) without the user explicitly asking for it — merges
  stay local unless told otherwise.
- Trivial changes (typo fix, doc tweak, single-line config) can skip the loop only if the user
  says so explicitly for that change — the default is always to run it.

## Repo hygiene
- Don't stage or commit unrelated in-progress changes the user hasn't confirmed are finished
  (e.g. a WIP image swap sitting in the working tree) — commit only what belongs to the current
  unit of work, and leave the rest untouched.
