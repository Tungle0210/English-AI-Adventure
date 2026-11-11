"""Regression tests for upstream Gemini HTTP failures; no live API requests."""
from types import SimpleNamespace
from .main import ai_error


def test_gemini_503_is_explicit_and_preserves_manual_retry_policy():
    status, message = ai_error(SimpleNamespace(code=503))
    assert status == 503
    assert '503' in message
    assert 'không tự' in message.lower()
    assert 'bản nháp' in message.lower()


def test_other_upstream_server_errors_are_not_misreported_as_503():
    for code in (500, 502, 504):
        status, message = ai_error(SimpleNamespace(code=code))
        assert status == 502
        assert str(code) in message
        assert 'Bản nháp' in message


def test_rate_limit_and_configuration_errors_remain_distinct():
    assert ai_error(SimpleNamespace(code=429))[0] == 429
    assert ai_error(SimpleNamespace(code=404))[0] == 502
    assert ai_error(SimpleNamespace(code=403))[0] == 502
