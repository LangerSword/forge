import pytest

from forge.observation_policy import ObservationPolicy, ObservationPolicyError, sanitize_observation_html


@pytest.fixture
def policy():
    return ObservationPolicy(frozenset({'drawably.dev'}))


def test_allowlisted_public_url(policy):
    policy.validate_url('https://drawably.dev/')


@pytest.mark.parametrize('url', [
    'https://evil.example/',
    'http://drawably.dev/',
    'https://drawably.dev:80/',
    'https://drawably.dev:8443/',
    'https://user:pass@drawably.dev/',
    'https://drawably.dev/#secret',
    'http://127.0.0.1/',
])
def test_reject_url_escape(policy, url):
    with pytest.raises(ObservationPolicyError):
        policy.validate_url(url)


def test_redirect_must_remain_allowlisted(policy):
    with pytest.raises(ObservationPolicyError):
        policy.validate_redirect('https://drawably.dev/', 'https://evil.example/')


def test_canonical_url(policy):
    assert policy.canonical_url('https://drawably.dev') == 'https://drawably.dev/'
    assert policy.canonical_url('https://drawably.dev/?x=1') == 'https://drawably.dev/?x=1'


def test_source_like_observation_is_rejected():
    with pytest.raises(ObservationPolicyError):
        sanitize_observation_html('<script>sourceMappingURL=app.js</script>')
    assert sanitize_observation_html('<h1>drawably</h1>') == '<h1>drawably</h1>'
