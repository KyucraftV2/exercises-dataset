import scripting as s
from backend import local_selector as ls


def test_flat_selection_matches_equipment_and_category_keywords():
    result = ls.run_local_assistant("pectoraux avec halteres", [], "fr")
    assert result["program"] is None
    assert result["exercises"]
    for exercise in result["exercises"]:
        assert exercise["category"] == "chest"
        assert "dumbbell" in exercise["equipment"]


def test_no_recognized_keyword_asks_for_equipment_and_body_part():
    result = ls.run_local_assistant("bonjour", [], "fr")
    assert result["exercises"] == []
    assert result["program"] is None
    assert result["message"] == ls.NO_FILTER_MESSAGES["fr"]


def test_recognized_but_unmatched_filters_return_no_match_message(monkeypatch):
    monkeypatch.setattr(ls.s, "filter_exercises", lambda *a, **k: [])
    result = ls.run_local_assistant("pectoraux avec halteres", [], "fr")
    assert result["exercises"] == []
    assert result["message"] == ls.NO_MATCH_MESSAGES["fr"]


def test_explicit_day_count_builds_a_push_pull_legs_program():
    result = ls.run_local_assistant("programme sur 3 jours avec halteres", [], "fr")
    assert result["program"] is not None
    assert [day["label"] for day in result["program"]["days"]] == ["Push", "Pull", "Legs"]
    for day in result["program"]["days"]:
        assert day["exercises"]
        for item in day["exercises"]:
            assert "dumbbell" in item["exercise"]["equipment"]


def test_mixed_keyword_builds_a_mix_program_instead_of_push_pull_legs():
    result = ls.run_local_assistant("programme varie sur 2 jours", [], "fr")
    assert result["program"] is not None
    assert [day["label"] for day in result["program"]["days"]] == ["Mix 1", "Mix 2"]


def test_wizard_trigger_without_enough_detail_asks_first_question():
    result = ls.run_local_assistant("aide-moi a choisir un programme", [], "fr")
    assert result["program"] is None
    assert result["message"] == ls.WIZARD_QUESTIONS["fr"][0]


def test_wizard_trigger_with_days_and_equipment_skips_straight_to_a_program():
    result = ls.run_local_assistant("aide-moi a choisir un programme de 3 jours avec halteres", [], "fr")
    assert result["program"] is not None
    assert result["message"] != ls.WIZARD_QUESTIONS["fr"][0]


def test_full_wizard_walkthrough_builds_a_program_from_the_four_answers():
    history = []

    def ask(message):
        nonlocal history
        result = ls.run_local_assistant(message, history, "fr")
        history.append({"role": "user", "text": message})
        history.append({"role": "assistant", "text": result["message"]})
        return result

    r1 = ask("aide-moi a choisir un programme")
    assert r1["message"] == ls.WIZARD_QUESTIONS["fr"][0]

    r2 = ask("prise de muscle")
    assert r2["message"] == ls.WIZARD_QUESTIONS["fr"][1]

    r3 = ask("halteres")
    assert r3["message"] == ls.WIZARD_QUESTIONS["fr"][2]

    r4 = ask("3 jours")
    assert r4["message"] == ls.WIZARD_QUESTIONS["fr"][3]

    final = ask("intermediaire")
    assert final["program"] is not None
    assert len(final["program"]["days"]) == 3
    for day in final["program"]["days"]:
        for item in day["exercises"]:
            assert "dumbbell" in item["exercise"]["equipment"]
            # goal="prise de muscle" + level="intermediaire" -> unadjusted hypertrophy profile
            assert item["sets"] == 4
            assert item["rest_seconds"] == 90


def test_beginner_with_no_explicit_equipment_avoids_complex_equipment():
    equipment = ls._equipment_for_level(None, "beginner")
    assert equipment is not None
    assert not (set(equipment) & ls.COMPLEX_EQUIPMENT)
    # sanity: still covers the vast majority of the real equipment list
    assert set(equipment) == set(s.list_equipment()) - ls.COMPLEX_EQUIPMENT


def test_explicit_equipment_is_respected_even_for_a_beginner():
    equipment = ls._equipment_for_level(["barbell"], "beginner")
    assert equipment == ["barbell"]


def test_extract_limit_caps_at_max_limit():
    assert ls._extract_limit("montre-moi 3 exercices") == 3
    assert ls._extract_limit("montre-moi 50 exercices") == ls.MAX_LIMIT
    assert ls._extract_limit("pectoraux") == ls.DEFAULT_LIMIT
