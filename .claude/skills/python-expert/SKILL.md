---
name: python-expert
description: Python conventions and best practices to enforce across the entire clashOfAI codebase — type hints, PEP 8/Ruff, dataclasses, custom exceptions, centralized constants, single-responsibility functions, strict business/RL separation, and pytest coverage for business logic. Apply this to every unit of work that touches Python code.
---

# Python Expert

Conventions that MUST be respected in every Python file of this project.

## Typing
- Complete type hints everywhere (PEP 484): function signatures, class attributes, module-level
  constants. Code must pass `mypy --strict` with zero errors.
- No untyped `**kwargs`/`*args` unless truly generic; prefer explicit parameters.
- Use `from __future__ import annotations` where useful to keep hints lightweight.

## Style and linting
- PEP 8 compliant. Format, lint, and sort imports with Ruff (`ruff format`, `ruff check`).
  Zero warnings tolerated before a branch can be merged.

## Data structures
- Use `@dataclass` (or `@dataclass(frozen=True)` for immutable value objects) for all state
  structures. Never pass bare `dict`s around as if they were structured objects.

## Errors
- Define custom exceptions for business-rule violations (e.g. `InsufficientResourcesError`,
  `InvalidActionError`), always inheriting from a project-specific base exception.
- Never use a bare `except:`. Never hardcode magic values inline — name them as constants.

## Constants and configuration
- All game/tunable constants live in centralized modules (`data/game_data.py`,
  `core/config.py`). No magic numbers scattered across business or RL code.

## Function design
- Short functions, single responsibility, explicit and descriptive names (no abbreviations
  that aren't obvious).

## Architecture boundary
- Strict separation between business logic (economy, game rules) and RL logic (environments,
  agents). Business modules must never import from `agents/` or depend on Gymnasium/SB3.

## Testing
- Every unit of business logic gets pytest coverage under `tests/`. Tests must pass before a
  branch is eligible for merge.
