# Contributing

## Setup

```bash
git clone <this repo>
cd exercises-dataset
make install-dev   # creates .venv, installs backend + dev dependencies
make env           # copies .env.example -> .env (AI_MODE=local, no API key needed)
make run           # starts the site at http://localhost:8000
```

Run `make help` for the full list of available commands.

## Before submitting a change

```bash
make lint   # ruff check
make test   # pytest backend/tests/ (always runs in AI_MODE=local - never hits the paid Groq API)
```

Both also run in CI (`.github/workflows/ci.yml`) on every push and pull request.

## Conventions

- Conventional Commits (`fix: ...`, `feat: ...`, `chore: ...`, `docs: ...`, `test: ...`,
  `refactor: ...`).
- One focused branch/PR per change - avoid bundling unrelated fixes together.
- Add or update tests under `backend/tests/` for any behavior change.
- See `data/exercises.schema.json` before touching `data/exercises.json` directly - it's the
  source of truth for the record shape.

## Reporting an issue

Open a GitHub issue with steps to reproduce. For a data problem (wrong exercise info, a broken
image/GIF, a mistagged field), include the exercise `id`.
