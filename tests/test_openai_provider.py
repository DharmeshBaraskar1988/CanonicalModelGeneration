from canonical_model_generator.api_analyzer.providers.openai import _text_only_input


def test_api_analyzer_provider_builds_text_only_input() -> None:
    messages = _text_only_input("system instructions", '{"operation": "Delete"}')

    assert messages == [
        {"role": "system", "content": "system instructions"},
        {"role": "user", "content": '{"operation": "Delete"}'},
    ]
    assert all(isinstance(message["content"], str) for message in messages)
    assert "image" not in repr(messages).casefold()
