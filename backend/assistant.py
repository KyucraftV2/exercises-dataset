import json
import os

from anthropic import Anthropic

import scripting as s

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOOL_ITERATIONS = 4
DEFAULT_LIMIT = 6
MAX_SELECTED_TOTAL = 12

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
        "describes what kind of workout or exercise selection they want "
        "(equipment available, muscles/body part to train, goal). Use the "
        "filter_exercises tool to search the real exercise database. Combine "
        "several tool calls if needed (e.g. one per muscle group) to build a "
        "good selection. Once you have enough results, write a short reply "
        f"in language '{lang}' explaining the selection you propose - keep it "
        "to a few sentences, the exercise cards themselves are shown "
        "separately by the website."
    )


def run_assistant(message: str, history: list[dict], lang: str) -> dict:
    exercises_by_lang = s.get_lang(s.load_exercises(), lang)
    client = _client_instance()

    messages: list[dict] = [{"role": h["role"], "content": h["text"]} for h in history]
    messages.append({"role": "user", "content": message})

    selected: dict[str, dict] = {}

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=_system_prompt(lang),
            tools=[_filter_tool_schema()],
            messages=messages,
        )

        content_blocks = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": content_blocks})

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block["text"] for block in content_blocks if block["type"] == "text"
            )
            return {
                "message": final_text,
                "exercises": list(selected.values())[:MAX_SELECTED_TOTAL],
            }

        tool_results = []
        for block in content_blocks:
            if block["type"] != "tool_use":
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
    }
