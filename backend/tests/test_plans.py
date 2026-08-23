import pytest
import scripting as s

from backend import plans, storage


def _real_exercise_id() -> str:
    return s.load_exercises()[0]["id"]


@pytest.fixture(autouse=True)
def user():
    # plans.username has a foreign key on users.username - every test here
    # saves a plan for "alice", so she needs to exist first.
    storage.create_user("alice", "correcthorse")


def test_get_plan_returns_none_when_no_plan_saved():
    assert plans.get_plan("alice") is None


def test_save_and_get_plan_hydrates_exercise_data():
    exercise_id = _real_exercise_id()
    plans.save_plan(
        "alice",
        "fr",
        [
            {
                "weekday": "monday",
                "label": "Push",
                "exercises": [{"exercise_id": exercise_id, "sets": 3, "reps": "8-12", "rest_seconds": 90}],
            }
        ],
    )

    plan = plans.get_plan("alice")
    assert plan["lang"] == "fr"
    day = plan["days"][0]
    assert day["weekday"] == "monday"
    assert day["exercises"][0]["exercise"]["id"] == exercise_id
    assert day["exercises"][0]["sets"] == 3
    assert day["exercises"][0]["done"] is False


def test_hydrate_skips_an_exercise_id_no_longer_in_the_dataset():
    storage.save_plan(
        "alice",
        "fr",
        [{"weekday": None, "label": "Push", "exercises": [{"exercise_id": "not-a-real-id", "done": False}]}],
    )

    plan = plans.get_plan("alice")
    assert plan["days"][0]["exercises"] == []


def test_set_exercise_done_toggles_and_persists():
    exercise_id = _real_exercise_id()
    plans.save_plan(
        "alice",
        "fr",
        [{"weekday": None, "label": "Push", "exercises": [{"exercise_id": exercise_id, "done": False}]}],
    )

    assert plans.set_exercise_done("alice", 0, exercise_id, True) is True
    plan = plans.get_plan("alice")
    assert plan["days"][0]["exercises"][0]["done"] is True


def test_set_exercise_done_returns_false_for_unknown_day_or_exercise():
    exercise_id = _real_exercise_id()
    plans.save_plan(
        "alice",
        "fr",
        [{"weekday": None, "label": "Push", "exercises": [{"exercise_id": exercise_id, "done": False}]}],
    )

    assert plans.set_exercise_done("alice", 5, exercise_id, True) is False
    assert plans.set_exercise_done("alice", 0, "not-a-real-id", True) is False


def test_set_exercise_done_returns_false_when_no_plan_saved():
    assert plans.set_exercise_done("alice", 0, "0001", True) is False


def test_swap_exercise_replaces_with_a_different_exercise_in_the_same_day():
    exercise_id = _real_exercise_id()
    plans.save_plan(
        "alice",
        "fr",
        [{"weekday": None, "label": "Push", "exercises": [{"exercise_id": exercise_id, "done": False}]}],
    )

    updated = plans.swap_exercise("alice", 0, exercise_id)
    assert updated is not None
    new_id = updated["days"][0]["exercises"][0]["exercise"]["id"]
    assert new_id != exercise_id

    # and it's actually persisted, not just returned
    persisted = plans.get_plan("alice")
    assert persisted["days"][0]["exercises"][0]["exercise"]["id"] == new_id


def test_swap_exercise_returns_none_for_unknown_day_or_exercise():
    exercise_id = _real_exercise_id()
    plans.save_plan(
        "alice",
        "fr",
        [{"weekday": None, "label": "Push", "exercises": [{"exercise_id": exercise_id, "done": False}]}],
    )

    assert plans.swap_exercise("alice", 5, exercise_id) is None
    assert plans.swap_exercise("alice", 0, "not-a-real-id") is None


def test_swap_exercise_returns_none_when_no_plan_saved():
    assert plans.swap_exercise("alice", 0, "0001") is None
