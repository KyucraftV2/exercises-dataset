from groq import GroqError

from backend import groq_assistant


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        data = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in self.tool_calls
            ]
        if exclude_none:
            data = {k: v for k, v in data.items() if v is not None}
        return data


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


def _fake_client(create_fn):
    class _Completions:
        create = staticmethod(create_fn)

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return _Client()


def test_groq_api_error_degrades_to_fallback_message_instead_of_raising(monkeypatch):
    def create(**kwargs):
        raise GroqError("simulated Groq failure")

    monkeypatch.setattr(groq_assistant, "_client_instance", lambda: _fake_client(create))

    result = groq_assistant.run_assistant("dos avec halteres", [], "fr")

    assert result == {
        "message": groq_assistant.FALLBACK_MESSAGES["fr"],
        "exercises": [],
        "program": None,
    }


def test_unknown_tool_call_gets_an_error_reply_and_conversation_continues(monkeypatch):
    responses = iter(
        [
            _FakeResponse(_FakeMessage(tool_calls=[_FakeToolCall("call_1", "not_a_real_tool", "{}")])),
            _FakeResponse(_FakeMessage(content="Voici ta réponse.")),
        ]
    )
    seen_tool_reply_for_call_1 = False

    def create(**kwargs):
        nonlocal seen_tool_reply_for_call_1
        tool_msgs = [m for m in kwargs["messages"] if m.get("role") == "tool"]
        if any(m["tool_call_id"] == "call_1" for m in tool_msgs):
            seen_tool_reply_for_call_1 = True
        return next(responses)

    monkeypatch.setattr(groq_assistant, "_client_instance", lambda: _fake_client(create))

    result = groq_assistant.run_assistant("test", [], "fr")

    assert result["message"] == "Voici ta réponse."
    # the second create() call must have carried a tool reply for the
    # hallucinated call, or the real Groq API would reject the request
    assert seen_tool_reply_for_call_1


def test_malformed_tool_call_arguments_get_an_error_reply_not_a_crash(monkeypatch):
    responses = iter(
        [
            _FakeResponse(
                _FakeMessage(tool_calls=[_FakeToolCall("call_1", "filter_exercises", "{not valid json")])
            ),
            _FakeResponse(_FakeMessage(content="Réponse finale.")),
        ]
    )

    def create(**kwargs):
        return next(responses)

    monkeypatch.setattr(groq_assistant, "_client_instance", lambda: _fake_client(create))

    result = groq_assistant.run_assistant("test", [], "fr")

    assert result["message"] == "Réponse finale."


def test_program_with_truncated_json_degrades_to_fallback(monkeypatch):
    def create(**kwargs):
        return _FakeResponse(
            _FakeMessage(tool_calls=[_FakeToolCall("call_1", "submit_program", '{"message": "oops", "day')])
        )

    monkeypatch.setattr(groq_assistant, "_client_instance", lambda: _fake_client(create))

    result = groq_assistant.run_assistant("programme sur 3 jours", [], "fr")

    assert result == {
        "message": groq_assistant.FALLBACK_MESSAGES["fr"],
        "exercises": [],
        "program": None,
    }
