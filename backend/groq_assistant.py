import json
import logging
import os
import time

from groq import Groq, GroqError

import scripting as s

logger = logging.getLogger(__name__)

MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_TOOL_ITERATIONS = 16
DEFAULT_LIMIT = 6
MAX_SELECTED_TOTAL = 12
MAX_SETS = 10
MAX_REST_SECONDS = 600
DEFAULT_SETS = 3
DEFAULT_REPS = "8-12"
DEFAULT_REST_SECONDS = 90

# Per-request wall-clock budget for the whole tool-calling loop, and a
# per-HTTP-call timeout passed to the Groq client. Without these, a
# rate-limited account (the SDK retries 429s with a backoff that can reach
# tens of seconds per call - observed in practice) can turn a single
# /api/chat call into a multi-minute hang across MAX_TOOL_ITERATIONS
# iterations, with no way for the caller to know it's still alive.
#
# This is a best-effort budget, not a hard deadline: it's only checked
# between iterations, so one iteration whose own retry+backoff overruns it
# still completes before the check can bail out on the *next* one. It
# still turns "up to MAX_TOOL_ITERATIONS slow iterations stacked back to
# back" into "roughly one slow iteration" in the worst case, which is the
# actual failure mode this fixes.
REQUEST_TIME_BUDGET_SECONDS = 45.0
PER_CALL_TIMEOUT_SECONDS = 20.0

_client: Groq | None = None


def _client_instance() -> Groq:
    global _client
    if _client is None:
        _client = Groq(timeout=PER_CALL_TIMEOUT_SECONDS, max_retries=1)
    return _client


def _filter_tool_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "filter_exercises",
            "description": (
                "Search the exercise database by any combination of equipment, target "
                "muscle, muscle group and body-part category. Values inside one "
                "parameter are combined with OR, different parameters are combined "
                "with AND. Call this before recommending any exercise - never invent "
                "exercises or values outside the given enums."
            ),
            "parameters": {
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
        },
    }


def _submit_program_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "submit_program",
            "description": (
                "Submit a finished multi-day training program. Only call this when the "
                "user asked for a program/split across several days or sessions - for a "
                "single flat exercise selection, just reply with text instead. Every "
                "exercise_id must be one you saw in a previous filter_exercises result - "
                "any id you didn't actually see will be silently dropped from the "
                "program. Pick sets/reps/rest yourself using standard strength-training "
                "practice - the dataset has no such data."
            ),
            "parameters": {
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
        f"plain text - put the day labels and the 'message' field in language '{lang}'. "
        "A day doesn't have to focus on a single muscle group/type by default (e.g. "
        "'Push'): that's just one reasonable default. If the user asks for a mixed "
        "or varied split, combine several categories/targets per day (several "
        "filter_exercises calls feeding into the same day) instead of one focus per "
        "day - whatever mix of days actually matches what they asked for.\n\n"
        "If the user explicitly asks for help figuring out what to do (e.g. 'aide-moi "
        "à choisir un programme', 'I don't know what program to do', 'what should I "
        "train?') instead of already describing one, don't call any tool yet - ask 1 "
        "to 3 short clarifying questions first (goal, equipment available, days per "
        f"week, experience level - whatever is missing), in language '{lang}'. Once "
        "they've answered enough of that, build the program as usual. If the user's "
        "very first message already gives you enough to work with (equipment and/or "
        "a body part/goal), skip the questions and just build the selection or "
        "program directly - only ask when they're actually asking for guidance.\n\n"
        "If the user states or implies an experience level (beginner/intermediate/"
        "advanced), use it as a heuristic, not a real per-exercise difficulty rating "
        "- the dataset has none. Adjust the sets/reps/rest you pick in submit_program "
        "accordingly (e.g. lower volume and longer rest for a beginner, more for "
        "advanced), and for a beginner who hasn't specified equipment, prefer simpler "
        "movements (bodyweight/dumbbell/machine) over more technical barbell lifts "
        "unless they specifically ask for those."
    )


def _clamp(value, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


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
                    "sets": _clamp(item.get("sets"), 1, MAX_SETS, DEFAULT_SETS),
                    "reps": str(item.get("reps") or DEFAULT_REPS),
                    "rest_seconds": _clamp(
                        item.get("rest_seconds"), 0, MAX_REST_SECONDS, DEFAULT_REST_SECONDS
                    ),
                }
            )
        if exercises:
            days.append({"label": day.get("label", ""), "exercises": exercises})
    return {"days": days}


def run_assistant(message: str, history: list[dict], lang: str) -> dict:
    exercises_by_lang = s.get_lang(s.load_exercises(), lang)
    by_id = {exercise["id"]: exercise for exercise in exercises_by_lang}
    client = _client_instance()

    messages: list[dict] = [{"role": "system", "content": _system_prompt(lang)}]
    messages += [{"role": h["role"], "content": h["text"]} for h in history]
    messages.append({"role": "user", "content": message})

    selected: dict[str, dict] = {}
    tools = [_filter_tool_schema(), _submit_program_schema()]
    fallback = {
        "message": FALLBACK_MESSAGES.get(lang, FALLBACK_MESSAGES["en"]),
        "exercises": [],
        "program": None,
    }

    start_time = time.monotonic()

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            if time.monotonic() - start_time > REQUEST_TIME_BUDGET_SECONDS:
                logger.warning("Groq chat completion exceeded its time budget, degrading to fallback")
                break
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=1536,
                tools=tools,
                messages=messages,
            )

            choice_message = response.choices[0].message
            messages.append(choice_message.model_dump(exclude_none=True))

            tool_calls = choice_message.tool_calls or []
            program_call = next(
                (tc for tc in tool_calls if tc.function.name == "submit_program"), None
            )
            if program_call is not None:
                program_input = json.loads(program_call.function.arguments)
                program = _build_program(program_input, by_id)
                if not program["days"]:
                    return fallback
                return {
                    "message": program_input.get("message", ""),
                    "exercises": [],
                    "program": program,
                }

            if not tool_calls:
                return {
                    "message": choice_message.content or "",
                    "exercises": list(selected.values())[:MAX_SELECTED_TOTAL],
                    "program": None,
                }

            for tool_call in tool_calls:
                # Every tool_call the model made needs a matching "tool" reply
                # before the next request, or the API rejects the whole
                # conversation as malformed - so an unrecognized name (a
                # hallucinated call outside the two tools we actually offer)
                # still gets one, just an error one, instead of being
                # silently dropped.
                if tool_call.function.name != "filter_exercises":
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(
                                {"error": f"Unknown tool '{tool_call.function.name}'"}
                            ),
                        }
                    )
                    continue
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as exc:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"error": f"Malformed arguments: {exc}"}),
                        }
                    )
                    continue
                limit = args.pop("limit", DEFAULT_LIMIT)
                try:
                    matched = s.filter_exercises(exercises_by_lang, **args)
                except TypeError as exc:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"error": str(exc)}),
                        }
                    )
                    continue
                for exercise in matched[:limit]:
                    selected[exercise["id"]] = exercise
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            {
                                "count": len(matched),
                                "returned": [_summarize(ex) for ex in matched[:limit]],
                            }
                        ),
                    }
                )
    except (GroqError, json.JSONDecodeError):
        # A Groq API error (auth, rate limit, timeout, a malformed request we
        # didn't anticipate...) or a truncated/invalid submit_program payload
        # (e.g. the model's tool call got cut off by max_tokens) shouldn't
        # surface as a raw 500 to the user - degrade to the same "couldn't
        # finish" message a loop-exhaustion already returns, but keep the
        # traceback in the server log so it's still debuggable.
        logger.exception("Groq chat completion failed")
        return {
            "message": fallback["message"],
            "exercises": list(selected.values())[:MAX_SELECTED_TOTAL],
            "program": None,
        }

    return {
        "message": fallback["message"],
        "exercises": list(selected.values())[:MAX_SELECTED_TOTAL],
        "program": None,
    }
