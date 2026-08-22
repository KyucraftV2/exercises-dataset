def filter_by_equipment(exercises: list[dict], equipment: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["equipment"] in equipment]


def filter_by_muscle_group(exercises: list[dict], muscle_group: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["muscle_group"] in muscle_group]


def filter_by_body_part(exercises: list[dict], body_part: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["body_part"] in body_part]


def filter_by_category(exercises: list[dict], category: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["category"] in category]


def filter_by_target(exercises: list[dict], target: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["target"] in target]


def filter_exercises(
    exercises: list[dict],
    *,
    equipment: list[str] | None = None,
    muscle_group: list[str] | None = None,
    body_part: list[str] | None = None,
    category: list[str] | None = None,
    target: list[str] | None = None,
) -> list[dict]:
    """Apply every provided filter as an AND. Each filter accepts a list of
    acceptable values so the caller can widen a single criterion."""
    result = exercises
    if equipment:
        result = filter_by_equipment(result, equipment)
    if muscle_group:
        result = filter_by_muscle_group(result, muscle_group)
    if body_part:
        result = filter_by_body_part(result, body_part)
    if category:
        result = filter_by_category(result, category)
    if target:
        result = filter_by_target(result, target)
    return result
