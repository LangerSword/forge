import pytest

from forge.openai_provider import ModelResponse, OpenAIProvider, ProviderError


class FakeClient:
    class Responses:
        def create(self, **kwargs):
            assert kwargs['model'] == 'gpt-5-nano'
            return type('R', (), {'output_text': '{"ok":true}', 'usage': None})()

    responses = Responses()

    def responses_create_legacy(self, **kwargs):
        assert kwargs['model'] == 'gpt-5-nano'
        return type('R', (), {'output_text': '{"ok":true}', 'usage': None})()


def test_provider_is_pinned_and_mockable(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    provider = OpenAIProvider(api_key='test-only', client=FakeClient())
    result = provider.complete(instructions='return JSON', input_text='hello')
    assert isinstance(result, ModelResponse)
    assert result.model == 'gpt-5-nano'
    assert result.text == '{"ok":true}'


def test_provider_requires_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(ProviderError) as exc:
        OpenAIProvider(client=FakeClient(), load_env=False).complete(instructions='x', input_text='y')
    assert exc.value.kind == 'missing_credentials'
