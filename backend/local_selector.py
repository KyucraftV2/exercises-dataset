"""Keyword-based exercise selector - no external API call, no API key needed.

This is a deliberately simple heuristic: it normalizes the user's message,
looks up known French/English keywords (equipment, body part, target
muscle...) against the dataset's real values, and calls
`scripting.filter_exercises` directly. It won't understand phrasing the
keyword table doesn't cover - see `backend.assistant` for the Claude-backed
mode, which handles free-form requests instead of fixed keywords.
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


def run_local_assistant(message: str, history: list[dict], lang: str) -> dict:
    normalized = _normalize(message)
    filters = _match_filters(normalized)

    if not filters:
        return {"message": NO_FILTER_MESSAGES.get(lang, NO_FILTER_MESSAGES["en"]), "exercises": []}

    exercises_by_lang = s.get_lang(s.load_exercises(), lang)
    matched = s.filter_exercises(exercises_by_lang, **filters)

    if not matched:
        return {"message": NO_MATCH_MESSAGES.get(lang, NO_MATCH_MESSAGES["en"]), "exercises": []}

    limit = _extract_limit(normalized)
    selected = random.sample(matched, min(limit, len(matched)))
    template = FOUND_TEMPLATES.get(lang, FOUND_TEMPLATES["en"])
    return {
        "message": template.format(n=len(selected), desc=_describe_filters(filters, lang)),
        "exercises": selected,
    }
