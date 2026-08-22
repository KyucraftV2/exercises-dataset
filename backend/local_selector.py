"""Keyword-based exercise selector - no external API call, no API key needed.

This is a deliberately simple heuristic: it normalizes the user's message,
looks up known French/English keywords (equipment, body part, target
muscle...) against the dataset's real values, and calls
`scripting.filter_exercises` directly. It won't understand phrasing the
keyword table doesn't cover - see `backend.assistant` for the Claude-backed
mode, which handles free-form requests instead of fixed keywords.

If the message asks for help figuring out a program (rather than already
describing one), a fixed 3-question wizard (goal, equipment, days/week)
runs instead - see WIZARD_TRIGGER_RE and _current_wizard_step.
"""

import random
import re
import unicodedata

import scripting as s

DEFAULT_LIMIT = 6
MAX_LIMIT = 12

# Languages this heuristic matcher actually understands. The other dataset
# languages (see scripting.list_languages) still work for get_lang/instructions,
# but the matcher and its reply templates only cover these two.
SUPPORTED_LANGS = ("en", "fr")

# keyword (singular, no accents) -> (filter field, values matched as OR).
# A trailing "s?" is appended automatically, so plurals don't need their own entry.
SYNONYMS: dict[str, tuple[str, tuple[str, ...]]] = {
    # equipment
    "haltere": ("equipment", ("dumbbell",)),
    "dumbbell": ("equipment", ("dumbbell",)),
    "barre": ("equipment", ("barbell",)),
    "barbell": ("equipment", ("barbell",)),
    "kettlebell": ("equipment", ("kettlebell",)),
    "cable": ("equipment", ("cable",)),
    "poulie": ("equipment", ("cable",)),
    "elastique": ("equipment", ("band", "resistance band")),
    "band": ("equipment", ("band", "resistance band")),
    "machine": ("equipment", ("leverage machine", "smith machine")),
    "poids du corps": ("equipment", ("body weight",)),
    "poids de corps": ("equipment", ("body weight",)),
    "sans materiel": ("equipment", ("body weight",)),
    "sans equipement": ("equipment", ("body weight",)),
    "bodyweight": ("equipment", ("body weight",)),
    "body weight": ("equipment", ("body weight",)),
    "no equipment": ("equipment", ("body weight",)),
    "swiss ball": ("equipment", ("stability ball",)),
    "stability ball": ("equipment", ("stability ball",)),
    "medicine ball": ("equipment", ("medicine ball",)),
    # category / body part
    "pectoraux": ("category", ("chest",)),
    "poitrine": ("category", ("chest",)),
    "chest": ("category", ("chest",)),
    "dos": ("category", ("back",)),
    "back": ("category", ("back",)),
    "epaule": ("category", ("shoulders",)),
    "shoulder": ("category", ("shoulders",)),
    "avant-bras": ("category", ("lower arms",)),
    "avant bras": ("category", ("lower arms",)),
    "forearm": ("category", ("lower arms",)),
    "bras": ("category", ("upper arms", "lower arms")),
    "arm": ("category", ("upper arms", "lower arms")),
    "abdo": ("category", ("waist",)),
    "ventre": ("category", ("waist",)),
    "waist": ("category", ("waist",)),
    "core": ("category", ("waist",)),
    "cardio": ("category", ("cardio",)),
    "cou": ("category", ("neck",)),
    "neck": ("category", ("neck",)),
    "cuisse": ("category", ("upper legs",)),
    "upper leg": ("category", ("upper legs",)),
    "mollet": ("category", ("lower legs",)),
    "lower leg": ("category", ("lower legs",)),
    "calve": ("category", ("lower legs",)),
    "jambe": ("category", ("upper legs", "lower legs")),
    "leg": ("category", ("upper legs", "lower legs")),
    # target muscles
    "biceps": ("target", ("biceps",)),
    "triceps": ("target", ("triceps",)),
    "fessier": ("target", ("glutes",)),
    "glute": ("target", ("glutes",)),
    "ischio": ("target", ("hamstrings",)),
    "hamstring": ("target", ("hamstrings",)),
    "quadricep": ("target", ("quads",)),
    "quad": ("target", ("quads",)),
    "trapeze": ("target", ("traps",)),
    "trap": ("target", ("traps",)),
    "lats": ("target", ("lats",)),
    "dorsal": ("target", ("lats",)),
    "deltoide": ("target", ("delts",)),
    "delt": ("target", ("delts",)),
    "pectoral": ("target", ("pectorals",)),
    "abductor": ("target", ("abductors",)),
    "adductor": ("target", ("adductors",)),
    "oblique": ("muscle_group", ("obliques",)),
}

FIELD_LABELS = {
    "fr": {
        "equipment": "matériel",
        "category": "zone",
        "target": "muscle cible",
        "muscle_group": "groupe musculaire",
    },
    "en": {
        "equipment": "equipment",
        "category": "body part",
        "target": "target muscle",
        "muscle_group": "muscle group",
    },
}

NO_FILTER_MESSAGES = {
    "fr": 'Dis-moi quel matériel tu as et quelle zone travailler (ex : "pectoraux avec haltères").',
    "en": 'Tell me what equipment you have and which body part to train (e.g. "chest with dumbbells").',
}

NO_MATCH_MESSAGES = {
    "fr": (
        "Je n'ai trouvé aucun exercice correspondant. Essaie de mentionner un "
        "matériel (haltères, poids du corps...) ou une zone (pectoraux, dos, jambes...)."
    ),
    "en": (
        "I couldn't find any matching exercise. Try mentioning equipment "
        "(dumbbells, bodyweight...) or a body part (chest, back, legs...)."
    ),
}

FOUND_TEMPLATES = {
    "fr": "Voici {n} exercice(s) - {desc}.",
    "en": "Here are {n} exercise(s) - {desc}.",
}

PROGRAM_FOUND_TEMPLATES = {
    "fr": "Voici un programme sur {n} jour(s).",
    "en": "Here's a {n}-day program.",
}

DAYS_RE = re.compile(r"(\d+)\s*(jours?|days?|seances?|sessions?)")
PROGRAM_WORD_RE = re.compile(r"\bprogrammes?\b|\bprograms?\b|\bsplit\b")

# Pre-built day splits, picked by requested day count (1-6, see _extract_days).
SPLIT_TEMPLATES: dict[int, list[str]] = {
    1: ["Full Body"],
    2: ["Haut du corps / Upper", "Bas du corps / Lower"],
    3: ["Push", "Pull", "Legs"],
    4: ["Push", "Pull", "Legs", "Full Body"],
    5: ["Push", "Pull", "Legs", "Haut du corps / Upper", "Bas du corps / Lower"],
    6: ["Push", "Pull", "Legs", "Push", "Pull", "Legs"],
}

# Day label -> list of filter kwargs, unioned (OR) to build that day's pool.
DAY_FILTERS: dict[str, list[dict[str, list[str]]]] = {
    "Push": [{"category": ["chest", "shoulders"]}, {"target": ["triceps"]}],
    "Pull": [{"category": ["back"]}, {"target": ["biceps"]}],
    "Legs": [{"category": ["upper legs", "lower legs"]}],
    "Haut du corps / Upper": [
        {"category": ["chest", "back", "shoulders", "upper arms", "lower arms"]}
    ],
    "Bas du corps / Lower": [{"category": ["upper legs", "lower legs"]}],
    "Full Body": [
        {"category": ["chest"]},
        {"category": ["back"]},
        {"category": ["upper legs", "lower legs"]},
        {"category": ["shoulders"]},
    ],
}

# "Mix" split: unlike Push/Pull/Legs (one focus per day) or Full Body (the
# same broad coverage every day), each day combines a different pair/trio of
# muscle groups so no two days look alike. Cycled with `i % len(MIX_COMBOS)`
# for however many days are requested.
MIX_COMBOS: list[list[dict[str, list[str]]]] = [
    [{"category": ["chest", "back"]}],
    [{"category": ["upper legs", "lower legs"]}],
    [{"category": ["shoulders", "upper arms", "lower arms"]}],
    [{"category": ["back", "upper legs"]}],
    [{"category": ["chest", "shoulders"]}],
    [{"category": ["waist", "cardio"]}],
]

MIX_WORD_RE = re.compile(r"\bmix\b|\bmixte\b|\bmixtes\b|\bmelange\b|\bmelanges\b|\bvarie\b|\bvaries\b")

EXERCISES_PER_DAY = 5
DEFAULT_SETS = 3
DEFAULT_REPS = "8-12"
DEFAULT_REST_SECONDS = 90
DEFAULT_PROFILE = {"sets": DEFAULT_SETS, "reps": DEFAULT_REPS, "rest_seconds": DEFAULT_REST_SECONDS}

# "Help me figure out a program" wizard: a fixed 3-question flow for people who
# don't know what to ask for. Progress is inferred from the plain {role, text}
# history the frontend already round-trips - see _current_wizard_step - so no
# extra state needs to travel between requests.
WIZARD_TRIGGER_RE = re.compile(
    r"(\baide\b.*\bprogrammes?\b)|(\bprogrammes?\b.*\baide\b)"
    r"|(\bhelp\b.*\bprograms?\b)|(\bprograms?\b.*\bhelp\b)"
    r"|(je ne sais pas quoi faire)|(not sure what to do)|(dont know what to do)"
)

WIZARD_QUESTIONS = {
    "fr": [
        "Quel est ton objectif ? (perte de poids, prise de muscle, force, forme générale)",
        "Quel matériel as-tu à disposition ? (haltères, barre, poids du corps, machine...)",
        "Combien de jours par semaine veux-tu t'entraîner ? (1 à 6)",
    ],
    "en": [
        "What's your goal? (weight loss, muscle gain, strength, general fitness)",
        "What equipment do you have? (dumbbells, barbell, bodyweight, machine...)",
        "How many days a week do you want to train? (1 to 6)",
    ],
}

# Reverse lookup so wizard progress can be recovered regardless of which
# language a past question was asked in (the user may switch languages
# mid-flow) - every language's question text maps to the same step index.
_QUESTION_TEXT_TO_STEP: dict[str, int] = {
    text: step for lang_questions in WIZARD_QUESTIONS.values() for step, text in enumerate(lang_questions)
}

# goal keywords (already normalized, no accents) -> sets/reps/rest profile
GOAL_PROFILES: list[tuple[tuple[str, ...], dict]] = [
    (
        ("perte", "maigrir", "cardio", "endurance", "fatloss", "weight loss", "lose weight"),
        {"sets": 3, "reps": "15-20", "rest_seconds": 45},
    ),
    (
        ("force", "strength", "puissance", "power"),
        {"sets": 5, "reps": "4-6", "rest_seconds": 150},
    ),
    (
        ("muscle", "masse", "hypertrophie", "hypertrophy", "gain", "bulk"),
        {"sets": 4, "reps": "8-12", "rest_seconds": 90},
    ),
]


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _extract_limit(normalized: str) -> int:
    match = re.search(r"\d+", normalized)
    if not match:
        return DEFAULT_LIMIT
    return max(1, min(int(match.group()), MAX_LIMIT))


def _keyword_pattern(keyword: str) -> re.Pattern:
    # Only offer an optional trailing "s" when the keyword doesn't already
    # end in one - otherwise e.g. "bras" (French, invariable in plural)
    # would also match the unrelated English word "brass".
    suffix = "" if keyword.endswith("s") else "s?"
    return re.compile(r"\b" + re.escape(keyword) + suffix + r"\b")


def _match_filters(normalized: str) -> dict[str, list[str]]:
    matched: dict[str, set[str]] = {"equipment": set(), "category": set(), "target": set(), "muscle_group": set()}
    for keyword, (field, values) in SYNONYMS.items():
        if _keyword_pattern(keyword).search(normalized):
            matched[field].update(values)
    return {field: sorted(values) for field, values in matched.items() if values}


def _describe_filters(filters: dict[str, list[str]], lang: str) -> str:
    labels = FIELD_LABELS.get(lang, FIELD_LABELS["en"])
    return " | ".join(f"{labels[field]}: {', '.join(values)}" for field, values in filters.items())


def _extract_days(normalized: str) -> int | None:
    match = DAYS_RE.search(normalized)
    if match:
        return max(1, min(int(match.group(1)), 6))
    if PROGRAM_WORD_RE.search(normalized):
        return 3  # "programme" / "split" with no explicit day count
    return None


def _build_program_from_specs(
    day_specs: list[tuple[str, list[dict[str, list[str]]]]],
    equipment: list[str] | None,
    exercises_by_lang: list[dict],
    profile: dict | None = None,
) -> dict:
    profile = profile or DEFAULT_PROFILE
    days = []
    used_ids: set[str] = set()
    for label, day_filters in day_specs:
        candidates: dict[str, dict] = {}
        for day_filter in day_filters:
            kwargs = dict(day_filter)
            if equipment:
                kwargs["equipment"] = equipment
            for exercise in s.filter_exercises(exercises_by_lang, **kwargs):
                candidates[exercise["id"]] = exercise

        pool = [ex for ex in candidates.values() if ex["id"] not in used_ids] or list(candidates.values())
        if not pool:
            continue
        chosen = random.sample(pool, min(EXERCISES_PER_DAY, len(pool)))
        used_ids.update(ex["id"] for ex in chosen)
        days.append(
            {
                "label": label,
                "exercises": [
                    {
                        "exercise": exercise,
                        "sets": profile["sets"],
                        "reps": profile["reps"],
                        "rest_seconds": profile["rest_seconds"],
                    }
                    for exercise in chosen
                ],
            }
        )
    return {"days": days}


def _build_program(
    days_count: int,
    equipment: list[str] | None,
    exercises_by_lang: list[dict],
    profile: dict | None = None,
) -> dict:
    specs = [(label, DAY_FILTERS[label]) for label in SPLIT_TEMPLATES[days_count]]
    return _build_program_from_specs(specs, equipment, exercises_by_lang, profile)


def _build_mixed_program(
    days_count: int,
    equipment: list[str] | None,
    exercises_by_lang: list[dict],
    profile: dict | None = None,
) -> dict:
    specs = [(f"Mix {i + 1}", MIX_COMBOS[i % len(MIX_COMBOS)]) for i in range(days_count)]
    return _build_program_from_specs(specs, equipment, exercises_by_lang, profile)


def _match_goal_profile(text: str) -> dict:
    normalized = _normalize(text)
    for keywords, profile in GOAL_PROFILES:
        if any(re.search(r"\b" + re.escape(kw) + r"\b", normalized) for kw in keywords):
            return profile
    return DEFAULT_PROFILE


def _current_wizard_step(history: list[dict]) -> int | None:
    """Which wizard step the incoming message would be answering, based
    purely on whether the conversation's LAST turn was us asking one of
    the wizard's questions (in any language - the user may switch mid-flow).
    None means we're not currently mid-wizard: either it was never
    started, or it already finished (its last message is the built
    program/selection, not a question) - a stale finished run can't be
    mistaken for one still awaiting an answer."""
    if not history or history[-1].get("role") != "assistant":
        return None
    return _QUESTION_TEXT_TO_STEP.get((history[-1].get("text") or "").strip())


def _collect_prior_wizard_answers(history: list[dict], answering_step: int) -> dict[int, str]:
    """Walk backward from just before the question at `answering_step`,
    collecting the contiguous chain of (question, answer) pairs for the
    steps immediately preceding it. Stops at the first gap, so answers
    from an earlier, already-finished wizard run can't leak into this one."""
    answers: dict[int, str] = {}
    step = answering_step
    i = len(history) - 2  # the answer to step `step - 1`, just before history[-1]
    while step > 0 and i >= 1:
        user_turn, assistant_turn = history[i], history[i - 1]
        prev_step = _QUESTION_TEXT_TO_STEP.get((assistant_turn.get("text") or "").strip())
        if user_turn.get("role") != "user" or assistant_turn.get("role") != "assistant" or prev_step != step - 1:
            break
        answers[step - 1] = user_turn["text"]
        step -= 1
        i -= 2
    return answers


def _has_enough_for_direct_program(normalized: str) -> bool:
    """True if a wizard-triggering message already gives enough detail to
    build a program right away (explicit day count + equipment) - in that
    case asking the wizard's questions would just be redundant."""
    return bool(DAYS_RE.search(normalized)) and bool(_match_filters(normalized).get("equipment"))


def _finalize_wizard(answers: dict[int, str], lang: str) -> dict:
    goal_text = answers.get(0, "")
    equipment_text = answers.get(1, "")
    days_text = answers.get(2, "")

    profile = _match_goal_profile(goal_text)
    equipment = _match_filters(_normalize(equipment_text)).get("equipment")
    days_match = re.search(r"\d+", _normalize(days_text))
    days_count = max(1, min(int(days_match.group()), 6)) if days_match else 3

    exercises_by_lang = s.get_lang(s.load_exercises(), lang)
    builder = _build_mixed_program if MIX_WORD_RE.search(_normalize(goal_text)) else _build_program
    program = builder(days_count, equipment, exercises_by_lang, profile)
    if not program["days"]:
        return {"message": NO_MATCH_MESSAGES.get(lang, NO_MATCH_MESSAGES["en"]), "exercises": [], "program": None}
    template = PROGRAM_FOUND_TEMPLATES.get(lang, PROGRAM_FOUND_TEMPLATES["en"])
    return {"message": template.format(n=len(program["days"])), "exercises": [], "program": program}


def run_local_assistant(message: str, history: list[dict], lang: str) -> dict:
    normalized = _normalize(message)
    questions = WIZARD_QUESTIONS.get(lang, WIZARD_QUESTIONS["en"])

    answering_step = _current_wizard_step(history)
    if answering_step is not None:
        # Mid-wizard: this message answers `answering_step` regardless of
        # its content (even if it coincidentally contains trigger words).
        answers = _collect_prior_wizard_answers(history, answering_step)
        answers[answering_step] = message
        next_step = answering_step + 1
        if next_step < len(questions):
            return {"message": questions[next_step], "exercises": [], "program": None}
        return _finalize_wizard(answers, lang)

    if WIZARD_TRIGGER_RE.search(normalized) and not _has_enough_for_direct_program(normalized):
        return {"message": questions[0], "exercises": [], "program": None}

    filters = _match_filters(normalized)
    days_count = _extract_days(normalized)

    if days_count:
        exercises_by_lang = s.get_lang(s.load_exercises(), lang)
        profile = _match_goal_profile(normalized)
        builder = _build_mixed_program if MIX_WORD_RE.search(normalized) else _build_program
        program = builder(days_count, filters.get("equipment"), exercises_by_lang, profile)
        if not program["days"]:
            return {"message": NO_MATCH_MESSAGES.get(lang, NO_MATCH_MESSAGES["en"]), "exercises": [], "program": None}
        template = PROGRAM_FOUND_TEMPLATES.get(lang, PROGRAM_FOUND_TEMPLATES["en"])
        return {"message": template.format(n=len(program["days"])), "exercises": [], "program": program}

    if not filters:
        return {
            "message": NO_FILTER_MESSAGES.get(lang, NO_FILTER_MESSAGES["en"]),
            "exercises": [],
            "program": None,
        }

    exercises_by_lang = s.get_lang(s.load_exercises(), lang)
    matched = s.filter_exercises(exercises_by_lang, **filters)

    if not matched:
        return {
            "message": NO_MATCH_MESSAGES.get(lang, NO_MATCH_MESSAGES["en"]),
            "exercises": [],
            "program": None,
        }

    limit = _extract_limit(normalized)
    selected = random.sample(matched, min(limit, len(matched)))
    template = FOUND_TEMPLATES.get(lang, FOUND_TEMPLATES["en"])
    return {
        "message": template.format(n=len(selected), desc=_describe_filters(filters, lang)),
        "exercises": selected,
        "program": None,
    }
