import json
import os

from anthropic import Anthropic

import scripting as s

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOOL_ITERATIONS = 8
DEFAULT_LIMIT = 6
MAX_SELECTED_TOTAL = 12
MAX_SETS = 10
MAX_REST_SECONDS = 600

_client: Anthropic | None = None


def _client_instance() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def _filter_tool_schema() -> dict:
    return {
        "name": "filter_exercises",
        "description": (
            "Search the exercise database by any combination of equipment, target "
            "muscle, muscle group and body-part category. Values inside one "
            "parameter are combined with OR, different parameters are combined "
            "with AND. Call this before recommending any exercise - never invent "
            "exercises or values outside the given enums."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "equipment": {
                    "type": "array",
                    "items": {"type": "string", "enum": s.list_equipment()},
                },
                "category": {
                    "type": "array",
                    "items": {"type": "string", "enum": s.list_categories()},
                    "description": "Body part, e.g. chest, back, upper legs",
                },
                "target": {
                    "type": "array",
                    "items": {"type": "string", "enum": s.list_targets()},
                },
                "muscle_group": {
                    "type": "array",
                    "items": {"type": "string", "enum": s.list_muscle_groups()},
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max exercises to return, default {DEFAULT_LIMIT}",
                },
            },
            "additionalProperties": False,
        },
    }


def _submit_program_schema() -> dict:
    return {
        "name": "submit_program",
        "description": (
            "Submit a finished multi-day training program. Only call this when the "
            "user asked for a program/split across several days or sessions - for a "
            "single flat exercise selection, just reply with text instead. Every "
            "exercise_id must be one returned by a previous filter_exercises call. "
            "Pick sets/reps/rest yourself using standard strength-training practice - "
            "the dataset has no such data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Short reply introducing the program, shown to the user as text.",
                },
                "days": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "e.g. 'Day 1 - Push', translated to the reply language",
                            },
                            "exercises": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "exercise_id": {"type": "string"},
                                        "sets": {"type": "integer", "minimum": 1, "maximum": MAX_SETS},
                                        "reps": {
                                            "type": "string",
                                            "description": "e.g. '8-12' or '30s'",
                                        },
                                        "rest_seconds": {
                                            "type": "integer",
                                            "minimum": 0,
                                            "maximum": MAX_REST_SECONDS,
                                        },
                                    },
                                    "required": ["exercise_id", "sets", "reps", "rest_seconds"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["label", "exercises"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["message", "days"],
            "additionalProperties": False,
        },
    }


# Short "couldn't finish" fallback, one per dataset language, so the message
# a rare loop-exhaustion returns still matches the conversation's language.
FALLBACK_MESSAGES = {
    "en": "I couldn't put together a consistent selection - could you clarify your request?",
    "fr": "Je n'ai pas réussi à finaliser une sélection cohérente, peux-tu préciser ta demande ?",
    "es": "No conseguí armar una selección coherente, ¿podrías precisar tu solicitud?",
    "it": "Non sono riuscito a completare una selezione coerente: puoi precisare la richiesta?",
    "tr": "Tutarlı bir seçki oluşturamadım, isteğini biraz daha netleştirebilir misin?",
    "ru": "Не удалось составить связную подборку — уточните, пожалуйста, запрос.",
    "zh": "我没能整理出一份连贯的清单，能再说明一下你的需求吗？",
    "hi": "मैं एक सुसंगत सूची तैयार नहीं कर पाया, क्या आप अपनी माँग स्पष्ट कर सकते हैं?",
    "pl": "Nie udało mi się dobrać spójnego zestawu - czy możesz doprecyzować prośbę?",
    "ko": "일관된 목록을 만들지 못했어요. 요청을 좀 더 구체적으로 말씀해 주시겠어요?",
}


def _summarize(exercise: dict) -> dict:
    return {
        "id": exercise["id"],
        "name": exercise["name"],
        "equipment": exercise["equipment"],
        "category": exercise["category"],
        "target": exercise["target"],
        "muscle_group": exercise["muscle_group"],
        "image": exercise["image"],
        "gif_url": exercise["gif_url"],
    }


def _system_prompt(lang: str) -> str:
    return (
        "You are a concise fitness assistant embedded in a website. The user "
        "describes what kind of workout, exercise selection, or multi-day training "
        "program they want (equipment available, muscles/body part to train, goal, "
        "number of days). Use the filter_exercises tool to search the real exercise "
        "database - combine several calls if needed (e.g. one per muscle group, or "
        "one per day of a program). Never invent an exercise or reference an "
        "exercise_id that wasn't returned by filter_exercises.\n\n"
        "For a flat selection (no days/sessions mentioned), once you have enough "
        f"results just write a short reply in language '{lang}' - keep it to a few "
        "sentences, the exercise cards themselves are shown separately by the "
        "website.\n\n"
        "For a multi-day program/split, once you've gathered exercises for every "
        "day, call submit_program with one entry per day (a label plus its "
        "exercises, each with sets/reps/rest you choose) instead of replying with "
        f"plain text - put the day labels and the 'message' field in language '{lang}'."
    )


def _build_program(payload: dict, by_id: dict[str, dict]) -> dict:
    days = []
    for day in payload.get("days", []):
        exercises = []
        for item in day.get("exercises", []):
            exercise = by_id.get(item.get("exercise_id"))
            if exercise is None:
                continue
            exercises.append(
                {
                    "exercise": exercise,
                    "sets": item.get("sets"),
                    "reps": item.get("reps"),
                    "rest_seconds": item.get("rest_seconds"),
                }
            )
        if exercises:
            days.append({"label": day.get("label", ""), "exercises": exercises})
    return {"days": days}


def run_assistant(message: str, history: list[dict], lang: str) -> dict:
    exercises_by_lang = s.get_lang(s.load_exercises(), lang)
    by_id = {exercise["id"]: exercise for exercise in exercises_by_lang}
    client = _client_instance()

    messages: list[dict] = [{"role": h["role"], "content": h["text"]} for h in history]
    messages.append({"role": "user", "content": message})

    selected: dict[str, dict] = {}
    tools = [_filter_tool_schema(), _submit_program_schema()]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1536,
            system=_system_prompt(lang),
            tools=tools,
            messages=messages,
        )

        content_blocks = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": content_blocks})

        program_block = next(
            (b for b in content_blocks if b["type"] == "tool_use" and b["name"] == "submit_program"),
            None,
        )
        if program_block is not None:
            return {
                "message": program_block["input"].get("message", ""),
                "exercises": [],
                "program": _build_program(program_block["input"], by_id),
            }

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block["text"] for block in content_blocks if block["type"] == "text"
            )
            return {
                "message": final_text,
                "exercises": list(selected.values())[:MAX_SELECTED_TOTAL],
                "program": None,
            }

        tool_results = []
        for block in content_blocks:
            if block["type"] != "tool_use" or block["name"] != "filter_exercises":
                continue
            args = dict(block["input"])
            limit = args.pop("limit", DEFAULT_LIMIT)
            try:
                matched = s.filter_exercises(exercises_by_lang, **args)
            except TypeError as exc:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": json.dumps({"error": str(exc)}),
                        "is_error": True,
                    }
                )
                continue
            for exercise in matched[:limit]:
                selected[exercise["id"]] = exercise
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": json.dumps(
                        {
                            "count": len(matched),
                            "returned": [_summarize(ex) for ex in matched[:limit]],
                        }
                    ),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return {
        "message": FALLBACK_MESSAGES.get(lang, FALLBACK_MESSAGES["en"]),
        "exercises": list(selected.values())[:MAX_SELECTED_TOTAL],
        "program": None,
    }
