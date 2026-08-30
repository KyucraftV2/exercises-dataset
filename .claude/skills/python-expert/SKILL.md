---
name: python-expert
description: Python conventions actually practiced in this repo (exercises-dataset) — a FastAPI backend (backend/) and a small dataset-filtering library (scripting/). Type hints, Ruff, Pydantic for API schemas, plain dicts for dataset records, pytest coverage for business logic. Apply this to every unit of work that touches Python code here.
---

# Python Expert (this repo)

Conventions observed and expected in `backend/` and `scripting/`. This is a small FastAPI
service plus a dataset-filtering library, not a package meant for outside distribution — keep
guidance proportionate to that.

## Typing
- Type hints on function signatures and module-level constants (see `scripting/filters.py`,
  `backend/ratelimit.py`). Not enforced via `mypy --strict` anywhere in this repo — don't add a
  mypy gate unless asked.
- Modern union syntax (`str | None`, not `Optional[str]`), matching the codebase (Python 3.12+
  per `.venv`).

## Style and linting
- Ruff for lint and format (`make lint` / `make format`, or `ruff check` / `ruff format`
  directly). Fix what a branch's own diff introduces; don't drive-by-fix unrelated pre-existing
  lint issues elsewhere in the same commit.

## Data structures
- Dataset records (exercises, filter results) are plain `dict`s end to end (`scripting/data.py`,
  `scripting/filters.py`) — that's the established pattern here, not an oversight. Don't
  introduce `@dataclass`/`TypedDict` wrappers around them; it would fight the grain of the
  existing code for no behavioral gain.
- `pydantic.BaseModel` is used, but only for FastAPI request/response schemas in
  `backend/main.py` (e.g. `PlanExerciseIn`, `ChatRequest`) — that boundary (API I/O validation)
  is where Pydantic belongs here, not internal data passing.

## Errors
- Plain `HTTPException(status_code=..., detail=...)` at the API boundary (`backend/main.py`) is
  the existing error-reporting convention — no custom exception hierarchy exists or is expected
  here. Never use a bare `except:`; the one broad `except (GroqError, json.JSONDecodeError)` in
  `backend/groq_assistant.py` is deliberate (documented inline) to degrade gracefully instead of
  surfacing a raw 500 for an external API's transient failures.
- Don't hardcode magic values inline — name them as module-level constants (see `MAX_SETS`,
  `MAX_TOOL_ITERATIONS` etc. in `backend/groq_assistant.py`).

## Constants and configuration
- Tunable constants live at the top of the module that uses them (`backend/groq_assistant.py`,
  `backend/ratelimit.py`) — there's no single centralized config module in this repo, and adding
  one for a project this size would be premature.

## Function design
- Short, single-responsibility functions with descriptive names — see `scripting/filters.py` for
  the house style (one function per filter axis, composed by `filter_exercises`).

## Testing
- Business logic gets pytest coverage under `backend/tests/` (`make test`, forced to
  `AI_MODE=local` so no run ever calls the paid Groq API — see
  `backend/tests/conftest.py::force_local_ai_mode`). A behavior change without a matching test
  update is a gap worth flagging in review, not something to wave through.
