import json
from pathlib import Path
from functools import lru_cache

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def load_exercises() -> list[dict]:
    with open(DATA_DIR / "exercises.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_schema() -> dict:
    with open(DATA_DIR / "exercises.schema.json", encoding="utf-8") as f:
        return json.load(f)


def get_lang(exercises: list[dict], lang: str) -> list[dict]:
    """Flatten instructions/instruction_steps to a single language."""
    flattened: list[dict] = []
    for exercise in exercises:
        new_exercise = dict(exercise)
        new_exercise["instructions"] = exercise["instructions"][lang]
        new_exercise["instruction_steps"] = exercise["instruction_steps"][lang]
        flattened.append(new_exercise)
    return flattened


def get_exercise_by_id(exercise_id: str, lang: str) -> dict | None:
    exercise = _index_by_id().get(exercise_id)
    if exercise is None:
        return None
    return get_lang([exercise], lang)[0]


@lru_cache(maxsize=1)
def _index_by_id() -> dict[str, dict]:
    return {exercise["id"]: exercise for exercise in load_exercises()}


def _unique_values(field: str) -> list[str]:
    values = {exercise[field] for exercise in load_exercises()}
    return sorted(values)


def list_equipment() -> list[str]:
    return _unique_values("equipment")


def list_categories() -> list[str]:
    return _unique_values("category")


def list_targets() -> list[str]:
    return _unique_values("target")


def list_muscle_groups() -> list[str]:
    return _unique_values("muscle_group")


def list_languages() -> list[str]:
    sample = load_exercises()[0]
    return sorted(sample["instructions"].keys())
