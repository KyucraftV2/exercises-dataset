import scripting as s

EXERCISES = [
    {"id": "1", "equipment": ["dumbbell"], "category": "chest", "target": "pectorals", "muscle_group": "shoulders"},
    {"id": "2", "equipment": ["barbell"], "category": "chest", "target": "pectorals", "muscle_group": "triceps"},
    {"id": "3", "equipment": ["dumbbell"], "category": "back", "target": "lats", "muscle_group": "biceps"},
    {"id": "4", "equipment": ["body weight"], "category": "legs", "target": "quads", "muscle_group": "glutes"},
]


def test_filter_exercises_with_no_filters_returns_everything():
    assert s.filter_exercises(EXERCISES) == EXERCISES


def test_filter_by_single_field_is_an_or_within_the_field():
    result = s.filter_exercises(EXERCISES, equipment=["dumbbell", "barbell"])
    assert {ex["id"] for ex in result} == {"1", "2", "3"}


def test_filter_by_multiple_fields_is_an_and_across_fields():
    result = s.filter_exercises(EXERCISES, equipment=["dumbbell"], category=["chest"])
    assert {ex["id"] for ex in result} == {"1"}


def test_filter_with_no_matches_returns_empty_list():
    assert s.filter_exercises(EXERCISES, equipment=["kettlebell"]) == []


def test_find_alternative_prefers_same_category_and_equipment():
    # exercise "1": dumbbell/chest - no other dumbbell+chest exercise exists,
    # but there's another chest exercise ("2", barbell) - tier 2 should win
    alt = s.find_alternative(EXERCISES, EXERCISES[0], exclude_ids=set())
    assert alt["id"] == "2"


def test_find_alternative_never_returns_the_original_or_excluded_ids():
    pool = [
        {"id": "1", "equipment": ["dumbbell"], "category": "chest", "target": "pectorals", "muscle_group": "x"},
        {"id": "2", "equipment": ["dumbbell"], "category": "chest", "target": "pectorals", "muscle_group": "x"},
    ]
    alt = s.find_alternative(pool, pool[0], exclude_ids={"2"})
    assert alt is None  # "1" excluded as self, "2" excluded explicitly - nothing left


def test_find_alternative_falls_back_to_target_muscle_tier():
    pool = [
        {"id": "1", "equipment": ["dumbbell"], "category": "chest", "target": "pectorals", "muscle_group": "x"},
        {"id": "2", "equipment": ["barbell"], "category": "legs", "target": "pectorals", "muscle_group": "y"},
    ]
    alt = s.find_alternative(pool, pool[0], exclude_ids=set())
    assert alt["id"] == "2"


def test_find_alternative_returns_none_when_nothing_suitable():
    pool = [{"id": "1", "equipment": ["dumbbell"], "category": "chest", "target": "pectorals", "muscle_group": "x"}]
    assert s.find_alternative(pool, pool[0], exclude_ids=set()) is None


def test_filter_by_equipment_matches_an_exercise_tagged_with_several():
    # e.g. a pull-up: bodyweight, but also needs a fixed pull-up bar
    pool = [
        {"id": "1", "equipment": ["body weight", "pull-up bar"], "category": "back", "target": "lats", "muscle_group": "x"},
        {"id": "2", "equipment": ["body weight"], "category": "waist", "target": "abs", "muscle_group": "y"},
    ]
    assert {ex["id"] for ex in s.filter_exercises(pool, equipment=["pull-up bar"])} == {"1"}
    assert {ex["id"] for ex in s.filter_exercises(pool, equipment=["body weight"])} == {"1", "2"}
