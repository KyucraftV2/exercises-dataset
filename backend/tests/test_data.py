import scripting as s
from scripting import data


def test_load_exercises_returns_the_full_real_dataset():
    exercises = data.load_exercises()
    assert len(exercises) == 1324
    sample = exercises[0]
    for field in ("id", "name", "category", "body_part", "equipment", "target", "muscle_group"):
        assert field in sample
    assert isinstance(sample["equipment"], list)
    assert sample["equipment"]  # never empty


def test_load_schema_describes_the_exercise_shape():
    schema = data.load_schema()
    assert schema["$defs"]["exercise"]["required"]
    assert "equipment" in schema["$defs"]["exercise"]["properties"]
    # the schema was migrated alongside the data - equipment is a list now, not a scalar
    assert schema["$defs"]["exercise"]["properties"]["equipment"]["type"] == "array"


def test_get_lang_flattens_instructions_to_the_requested_language_only():
    exercises = data.load_exercises()[:3]
    flattened = data.get_lang(exercises, "fr")
    for original, translated in zip(exercises, flattened):
        assert translated["instructions"] == original["instructions"]["fr"]
        assert translated["instruction_steps"] == original["instruction_steps"]["fr"]
        # every other field is untouched
        assert translated["id"] == original["id"]
        assert translated["equipment"] == original["equipment"]
    # the original list/dicts aren't mutated in place
    assert isinstance(exercises[0]["instructions"], dict)


def test_get_exercise_by_id_returns_none_for_an_unknown_id():
    assert data.get_exercise_by_id("not-a-real-id", "fr") is None


def test_get_exercise_by_id_returns_the_matching_exercise_in_the_requested_language():
    real_id = data.load_exercises()[0]["id"]
    exercise = data.get_exercise_by_id(real_id, "en")
    assert exercise is not None
    assert exercise["id"] == real_id
    assert isinstance(exercise["instructions"], str)


def test_list_equipment_flattens_the_multi_valued_field_with_no_duplicates():
    equipment = s.list_equipment()
    assert equipment == sorted(set(equipment))
    assert "dumbbell" in equipment
    assert "pull-up bar" in equipment  # only ever appears as a 2nd tag alongside body weight


def test_list_categories_targets_muscle_groups_are_sorted_and_deduplicated():
    for values in (s.list_categories(), s.list_targets(), s.list_muscle_groups()):
        assert values == sorted(set(values))
        assert values  # never empty


def test_list_languages_returns_the_ten_dataset_languages():
    assert s.list_languages() == sorted(
        ["en", "es", "it", "tr", "ru", "zh", "hi", "pl", "ko", "fr"]
    )
