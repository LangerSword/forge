import json
from pathlib import Path

import pytest

from forge.browser_executor import MockBrowserExecutor, capture_sanitized
from forge.observation_policy import ObservationPolicy, ObservationPolicyError


@pytest.fixture
def policy():
    return ObservationPolicy(frozenset({'drawably.dev'}))


def test_sanitized_capture_writes_deterministic_artifact(tmp_path: Path, policy):
    path = capture_sanitized(
        policy=policy,
        executor=MockBrowserExecutor('<h1>drawably</h1>', b'png'),
        url='https://drawably.dev',
        output_dir=tmp_path,
    )
    data = json.loads(path.read_text())
    assert data['target_url'] == 'https://drawably.dev/'
    assert data['html_outline'] == '<h1>drawably</h1>'
    assert len(data['screenshot_sha256']) == 64
    assert data['requests'][0]['url'] == 'https://drawably.dev/'


def test_capture_rejects_source_like_html(tmp_path: Path, policy):
    with pytest.raises(ObservationPolicyError):
        capture_sanitized(
            policy=policy,
            executor=MockBrowserExecutor('<script src="app.js"></script>'),
            url='https://drawably.dev/',
            output_dir=tmp_path,
        )
    assert not (tmp_path / 'observation.json').exists()


def test_capture_rejects_off_list_request(tmp_path: Path, policy):
    executor = MockBrowserExecutor('<h1>ok</h1>')
    executor = type('OffList', (), {'capture': lambda self, url: type('R', (), {
        'url': url, 'html_outline': '<h1>ok</h1>', 'screenshot_sha256': None,
        'request_log': ({'url': 'https://evil.example/', 'method': 'GET', 'purpose': 'asset'},),
    })()})()
    with pytest.raises(ObservationPolicyError):
        capture_sanitized(policy=policy, executor=executor, url='https://drawably.dev/', output_dir=tmp_path)
