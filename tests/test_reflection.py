import json

from forge.openai_provider import OpenAIProvider
from forge.reflection import SkillCandidate, reflect_failure


class FakeResponses:
    def create(self, **kwargs):
        return type('R', (), {
            'output_text': json.dumps({
                'skill_id': 'repair-name-normalizer',
                'kind': 'skill',
                'applies_when': 'C0 name normalizer test failure',
                'procedure': ['Read failure', 'repair candidate', 'rerun frozen tests'],
                'exceptions': ['Do not edit frozen tests'],
                'verification': ['4 frozen tests pass'],
                'evidence_refs': ['run:test-reflect'],
                'status': 'candidate',
            }), 'usage': None})()


class FakeClient:
    responses = FakeResponses()


def test_reflection_returns_strict_candidate():
    result = reflect_failure(
        OpenAIProvider(api_key='test-only', client=FakeClient(), load_env=False),
        run_id='test-reflect',
        evidence={'task_id': 'c0-name-normalizer-v1', 'failure_code': 'test_failure'},
    )
    assert isinstance(result.candidate, SkillCandidate)
    assert result.candidate.status == 'candidate'


def test_reflection_rejects_non_json():
    class Bad:
        class responses:
            @staticmethod
            def create(**kwargs):
                return type('R', (), {'output_text': 'not json', 'usage': None})()
    result = reflect_failure(OpenAIProvider(api_key='test-only', client=Bad(), load_env=False), run_id='bad', evidence={})
    assert result.candidate is None
    assert result.error.startswith('reflection_failed')
