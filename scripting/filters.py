import random


def filter_by_equipment(exercises: list[dict], equipment: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["equipment"] in equipment]


def filter_by_muscle_group(exercises: list[dict], muscle_group: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["muscle_group"] in muscle_group]


def filter_by_category(exercises: list[dict], category: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["category"] in category]


def filter_by_target(exercises: list[dict], target: list[str]) -> list[dict]:
    return [ex for ex in exercises if ex["target"] in target]


def filter_exercises(
    exercises: list[dict],
    *,
    equipment: list[str] | None = None,
    muscle_group: list[str] | None = None,
    category: list[str] | None = None,
    target: list[str] | None = None,
) -> list[dict]:
    """Apply every provided filter as an AND. Each filter accepts a list of
    acceptable values so the caller can widen a single criterion.

    There is no separate body-part filter: `category` and the dataset's
    `body_part` field always hold the same value, so `category` covers both."""
    result = exercises
    if equipment:
        result = filter_by_equipment(result, equipment)
    if muscle_group:
        result = filter_by_muscle_group(result, muscle_group)
    if category:
        result = filter_by_category(result, category)
    if target:
        result = filter_by_target(result, target)
    return result


def find_alternative(exercises: list[dict], exercise: dict, exclude_ids: set[str]) -> dict | None:
    """Pick a random substitute for `exercise`, e.g. for a 'swap this
    exercise out' action. Tries same-category-and-equipment first, then
    same-category-only (any equipment), then same-target-muscle-only, and
    returns the first tier that has a candidate. Never returns `exercise`
    itself or anything in `exclude_ids`. Returns None if nothing suitable
    exists in any tier."""
    exclude_ids = exclude_ids | {exercise["id"]}
    tiers = (
        filter_exercises(exercises, category=[exercise["category"]], equipment=[exercise["equipment"]]),
        filter_exercises(exercises, category=[exercise["category"]]),
        filter_exercises(exercises, target=[exercise["target"]]),
    )
    for candidates in tiers:
        pool = [ex for ex in candidates if ex["id"] not in exclude_ids]
        if pool:
            return random.choice(pool)
    return None
