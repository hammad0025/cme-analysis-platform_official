import pytest

from scripts import cme_api_auth


@pytest.fixture(autouse=True)
def _reset_cache():
    cme_api_auth._cache.update({"token": None, "expires": 0.0})
    yield
    cme_api_auth._cache.update({"token": None, "expires": 0.0})


class _FakeCognito:
    def __init__(self):
        self.calls = 0

    def initiate_auth(self, **kwargs):
        self.calls += 1
        assert kwargs["AuthFlow"] == "USER_PASSWORD_AUTH"
        assert kwargs["AuthParameters"]["USERNAME"] == "ops@example.com"
        return {"AuthenticationResult": {"IdToken": "tok-123", "ExpiresIn": 3600}}


def test_missing_credentials_exits(monkeypatch):
    monkeypatch.delenv("CME_API_USERNAME", raising=False)
    monkeypatch.delenv("CME_API_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="CME_API_USERNAME"):
        cme_api_auth.get_id_token()


def test_token_fetched_and_cached(monkeypatch):
    monkeypatch.setenv("CME_API_USERNAME", "ops@example.com")
    monkeypatch.setenv("CME_API_PASSWORD", "secret")
    fake = _FakeCognito()
    monkeypatch.setattr(cme_api_auth.boto3, "client", lambda *a, **k: fake)

    assert cme_api_auth.get_id_token() == "tok-123"
    assert cme_api_auth.get_id_token() == "tok-123"
    assert fake.calls == 1


def test_auth_headers_bearer_format(monkeypatch):
    monkeypatch.setenv("CME_API_USERNAME", "ops@example.com")
    monkeypatch.setenv("CME_API_PASSWORD", "secret")
    monkeypatch.setattr(cme_api_auth.boto3, "client", lambda *a, **k: _FakeCognito())

    assert cme_api_auth.auth_headers() == {"Authorization": "Bearer tok-123"}


def test_api_session_carries_header(monkeypatch):
    monkeypatch.setenv("CME_API_USERNAME", "ops@example.com")
    monkeypatch.setenv("CME_API_PASSWORD", "secret")
    monkeypatch.setattr(cme_api_auth.boto3, "client", lambda *a, **k: _FakeCognito())

    session = cme_api_auth.api_session()
    assert session.headers["Authorization"] == "Bearer tok-123"
