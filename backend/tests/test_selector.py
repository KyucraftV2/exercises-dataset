from backend import selector


def test_valid_modes_no_longer_include_claude():
    assert selector.VALID_MODES == ("local", "groq")


def test_unknown_ai_mode_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("AI_MODE", "not-a-real-mode")
    assert selector.get_mode() == "local"


def test_local_mode_only_supports_its_own_keyword_languages(monkeypatch):
    monkeypatch.setenv("AI_MODE", "local")
    langs = selector.get_supported_langs()
    assert langs == sorted(selector.SUPPORTED_LANGS)
    assert "fr" in langs and "en" in langs


def test_groq_mode_supports_every_dataset_language(monkeypatch):
    import scripting as s

    monkeypatch.setenv("AI_MODE", "groq")
    assert selector.get_supported_langs() == s.list_languages()
