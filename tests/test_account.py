"""Only synthetic credentials and an in-memory keyring; never the login keyring."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

import pytest
from google.auth.exceptions import RefreshError, TransportError
from google.oauth2.credentials import Credentials

from quiettube.account import Account, AccountError, AUTH_URI, TOKEN_URI, SCOPES, SecretVault, parse_client

CLIENT_ID = 'synthetic-test.apps.googleusercontent.com'
SECRET = 'synthetic-secret-not-a-real-credential'
TOKEN = 'synthetic-access'
REFRESH = 'synthetic-refresh'


def client():
    return {'installed': {'client_id': CLIENT_ID, 'client_secret': SECRET,
                          'auth_uri': AUTH_URI, 'token_uri': TOKEN_URI}}


def tokens(expired=False):
    expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=-1 if expired else 1)
    return json.loads(Credentials(TOKEN, refresh_token=REFRESH, token_uri=TOKEN_URI,
                                 client_id=CLIENT_ID, client_secret=SECRET, scopes=SCOPES,
                                 expiry=expiry).to_json())


class MemoryVault:
    def __init__(self, value=None):
        self.value = deepcopy(value or {})
        self.writes = 0
    def read(self):
        return deepcopy(self.value)
    def write(self, value):
        self.value = deepcopy(value)
        self.writes += 1
    def delete(self):
        self.value = {}


@pytest.fixture
def account(tmp_path):
    return Account(tmp_path, MemoryVault())


def test_import_is_private_keyring_only_and_does_not_touch_browser_session(account, tmp_path):
    source = tmp_path / 'download.json'
    source.write_text(json.dumps(client()))
    cookies = tmp_path / 'youtube-session.txt'
    cookies.write_text('synthetic cookie snapshot')
    cache = tmp_path / 'account-feed.json'
    cache.write_text('old metadata')
    result = account.configure({'client_file': str(source)})
    assert result == {'configured': True, 'authorization_saved': False, 'client_changed': True}
    assert account.vault.value == {'client': client()}
    assert source.read_text() == json.dumps(client())
    assert cookies.read_text() == 'synthetic cookie snapshot'
    assert not cache.exists()
    assert {p.name for p in tmp_path.iterdir()} == {'download.json', 'youtube-session.txt', 'oauth.lock'}
    assert SECRET not in json.dumps(result)
    assert (tmp_path / 'oauth.lock').stat().st_mode & 0o777 == 0o600


def test_manual_fields_and_json_produce_same_configuration(account):
    result = account.configure({'client_id': '  ' + CLIENT_ID, 'client_secret': SECRET + ' '})
    assert result['configured']
    assert account.vault.value['client'] == client()


@pytest.mark.parametrize('mutation', [
    lambda c: {'web': c['installed']},
    lambda c: {'type': 'service_account', 'private_key': SECRET},
    lambda c: {'installed': {**c['installed'], 'token_uri': 'https://attacker.invalid/token'}},
    lambda c: {'installed': {**c['installed'], 'auth_uri': 'https://attacker.invalid/auth'}},
    lambda c: {'installed': {**c['installed'], 'client_id': 'not-a-client'}},
    lambda c: {'installed': {**c['installed'], 'client_secret': 'bad secret'}},
    lambda c: {'installed': []},
    lambda c: [],
])
def test_bad_import_never_overwrites_working_configuration(account, tmp_path, mutation):
    account.vault.value = {'client': client(), 'tokens': tokens()}
    before = deepcopy(account.vault.value)
    source = tmp_path / 'download.json'
    source.write_text(json.dumps(mutation(client())))
    with pytest.raises(AccountError) as error:
        account.configure({'client_file': str(source)})
    assert error.value.code == 'invalid_client'
    assert SECRET not in str(error.value)
    assert account.vault.value == before
    assert account.vault.writes == 0


def test_oversized_and_invalid_json_rejected_without_echoing_content(account, tmp_path):
    path = tmp_path / 'download.json'
    for raw in [SECRET, '{"installed":', 'x' * 16385]:
        path.write_text(raw)
        with pytest.raises(AccountError) as error:
            account.configure({'client_file': str(path)})
        assert SECRET not in str(error.value)
    assert account.vault.writes == 0


def test_same_configuration_preserves_tokens_but_changed_client_clears_them(account):
    account.vault.value = {'client': client(), 'tokens': tokens()}
    result = account.configure({'client_id': CLIENT_ID, 'client_secret': SECRET})
    assert result['authorization_saved'] and not result['client_changed']
    result = account.configure({'client_id': 'another-test.apps.googleusercontent.com', 'client_secret': SECRET})
    assert not result['authorization_saved'] and result['client_changed']
    assert 'tokens' not in account.vault.value


def test_refresh_persists_rotation_and_never_writes_tokens_to_disk(account, monkeypatch):
    account.vault.value = {'client': client(), 'tokens': tokens(expired=True)}
    def refresh(credentials, request):
        credentials.token = 'synthetic-new-access'
        credentials._refresh_token = 'synthetic-rotated-refresh'
        credentials.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    monkeypatch.setattr(Credentials, 'refresh', refresh)
    assert account.access_token() == 'synthetic-new-access'
    assert account.vault.value['tokens']['refresh_token'] == 'synthetic-rotated-refresh'
    assert account.access_token(rejected_token=TOKEN) == 'synthetic-new-access'
    assert account.vault.writes == 1  # a concurrent stale 401 must reuse the renewed token
    assert all(TOKEN.encode() not in p.read_bytes() for p in account.directory.iterdir())


def test_revoked_refresh_clears_authorization_not_configuration(account, monkeypatch):
    account.vault.value = {'client': client(), 'tokens': tokens(expired=True)}
    def refresh(*_):
        raise RefreshError('SECRET_SERVER_OUTPUT', {'error': 'invalid_grant'})
    monkeypatch.setattr(Credentials, 'refresh', refresh)
    with pytest.raises(AccountError) as error:
        account.access_token()
    assert error.value.code == 'sign_in_required'
    assert 'SECRET_SERVER_OUTPUT' not in str(error.value)
    assert account.vault.value == {'client': client()}


@pytest.mark.parametrize('failure', [TransportError('PRIVATE'), RefreshError('PRIVATE', {'error': 'temporarily_unavailable'})])
def test_transient_refresh_failure_retains_saved_authorization(account, monkeypatch, failure):
    account.vault.value = {'client': client(), 'tokens': tokens(expired=True)}
    before = deepcopy(account.vault.value)
    def refresh(*_): raise failure
    monkeypatch.setattr(Credentials, 'refresh', refresh)
    with pytest.raises(AccountError) as error:
        account.access_token()
    assert 'PRIVATE' not in str(error.value)
    assert account.vault.value == before


def test_tokens_for_other_client_or_missing_scope_are_rejected(account):
    for token in [{**tokens(), 'client_id': 'different.apps.googleusercontent.com'}, {**tokens(), 'scopes': []}]:
        account.vault.value = {'client': client(), 'tokens': token}
        with pytest.raises(AccountError) as error:
            account.access_token()
        assert error.value.code == 'sign_in_required'


def test_forget_removes_only_personal_oauth(account):
    account.vault.value = {'client': client(), 'tokens': tokens()}
    cookie = account.directory / 'youtube-session.txt'
    cookie.write_text('synthetic cookie')
    assert account.forget() == {'forgotten': True}
    assert account.vault.value == {}
    assert cookie.read_text() == 'synthetic cookie'


def test_vault_missing_service_never_falls_back_to_file(tmp_path, monkeypatch):
    import secretstorage
    def fail(): raise RuntimeError(SECRET)
    monkeypatch.setattr(secretstorage, 'dbus_init', fail)
    vault = SecretVault(tmp_path)
    with pytest.raises(AccountError) as error:
        vault.write({'client': client()})
    assert error.value.code == 'keyring_unavailable'
    assert SECRET not in str(error.value)
    assert list(tmp_path.iterdir()) == []


def test_vault_locked_collection_rejects_write_and_closes_connection(tmp_path, monkeypatch):
    import secretstorage
    calls = []
    class Connection:
        def close(self): calls.append('closed')
    class Collection:
        def __init__(self, connection): pass
        def is_locked(self): return True
        def unlock(self, timeout): calls.append(timeout)
    monkeypatch.setattr(secretstorage, 'dbus_init', Connection)
    monkeypatch.setattr(secretstorage, 'Collection', Collection)
    with pytest.raises(AccountError, match='Unlock'):
        SecretVault(tmp_path).write({'client': client()})
    assert calls == [60, 'closed']


def test_vault_scopes_entries_to_library_and_stores_secret_in_secret_field(tmp_path, monkeypatch):
    vault = SecretVault(tmp_path)
    other = SecretVault(tmp_path / 'other')
    assert vault.attributes != other.attributes
    assert str(tmp_path) not in str(vault.attributes)
    records = []
    class Item:
        def get_secret(self): return records[0][2]
        def delete(self): records.clear()
    class Collection:
        def search_items(self, attrs):
            assert attrs == vault.attributes
            return [Item()] if records else []
        def create_item(self, label, attrs, secret, replace, content_type):
            assert replace and content_type == 'application/json'
            assert SECRET not in str(attrs) and SECRET not in label
            records[:] = [(label, attrs, secret)]
    @contextmanager
    def collection(): yield Collection()
    monkeypatch.setattr(vault, 'collection', collection)
    assert vault.read() == {}
    vault.write({'client': client()})
    assert vault.read() == {'client': client()}
    vault.delete()
    assert vault.read() == {}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('correct_state', [True, False])
def test_real_google_flow_pkce_and_loopback_state_without_google_network(account, monkeypatch, correct_state):
    """Exercise OAuthlib's actual state/PKCE path; intercept only the token HTTP POST."""
    import base64
    import hashlib
    import requests
    account.vault.value = {'client': client()}
    auth_queries, exchanges, threads, errors = [], [], [], []
    def browser_open(self, url, **kwargs):
        query = parse_qs(urlparse(url).query)
        auth_queries.append(query)
        callback = query['redirect_uri'][0]
        assert urlparse(callback).hostname == '127.0.0.1'
        state = query['state'][0] if correct_state else 'incorrect-state'
        def visit():
            try:
                with urlopen(callback + '?' + urlencode({'code': 'synthetic-code', 'state': state}), timeout=5) as response:
                    response.read()
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=visit, daemon=True)
        threads.append(thread)
        thread.start()
        return True
    monkeypatch.setattr('quiettube.account.DesktopBrowser.open', browser_open)
    def send(session, request, **kwargs):
        assert request.url == TOKEN_URI
        fields = parse_qs(request.body)
        exchanges.append(fields)
        verifier = fields['code_verifier'][0]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        assert challenge == auth_queries[0]['code_challenge'][0]
        assert auth_queries[0]['code_challenge_method'] == ['S256']
        result = requests.Response()
        result.status_code = 200
        result.request = request
        result.url = request.url
        result._content = json.dumps({'access_token': TOKEN, 'refresh_token': REFRESH, 'token_type': 'Bearer',
                                      'expires_in': 3600, 'scope': ' '.join(SCOPES)}).encode()
        return result
    monkeypatch.setattr(requests.sessions.Session, 'send', send)
    monkeypatch.setattr('quiettube.youtube_api.api_request', lambda *args: {'items': []})
    if correct_state:
        try:
            result = account.connect()
        except AccountError as error:
            raise AssertionError(f'Synthetic OAuth exchange failed: {error.__context__!r}') from error
        assert result['connected']
        assert account.vault.value['tokens']['refresh_token'] == REFRESH
        assert len(exchanges) == 1
    else:
        from oauthlib.oauth2 import MismatchingStateError
        with pytest.raises(AccountError) as error:
            account.connect()
        assert isinstance(error.value.__context__, MismatchingStateError)
        assert exchanges == []
        assert account.vault.value == {'client': client()}
    assert len(auth_queries) == 1
    for thread in threads: thread.join(timeout=5)
    assert errors == []


def test_worker_protocol_never_echoes_config_or_token_errors(tmp_path, monkeypatch, capsys):
    from quiettube import worker
    request = {'action': 'oauth_configure', 'account_dir': str(tmp_path), 'client_id': CLIENT_ID, 'client_secret': SECRET}
    monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(json.dumps(request).encode())))
    def fail(_): raise RuntimeError(SECRET + TOKEN)
    monkeypatch.setattr(worker, 'execute', fail)
    worker.main()
    raw = capsys.readouterr().out
    assert SECRET not in raw and TOKEN not in raw and CLIENT_ID not in raw
    assert json.loads(raw)['ok'] is False


@pytest.mark.parametrize('payload', [[], None, 'synthetic-private-input'])
def test_worker_rejects_non_object_requests_without_crashing_or_echoing(payload, monkeypatch, capsys):
    from quiettube import worker
    monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))
    worker.main()
    raw = capsys.readouterr().out
    assert json.loads(raw)['ok'] is False
    assert 'synthetic-private-input' not in raw


def test_no_client_json_is_bundled_and_common_download_names_are_ignored():
    import subprocess
    import tomllib
    root = Path(__file__).resolve().parent.parent
    project = tomllib.loads((root / 'pyproject.toml').read_text())
    assert project['tool']['setuptools']['package-data']['quiettube'] == ['style.css', 'icons/*.svg']
    result = subprocess.run(['git', 'check-ignore', 'client_secret_synthetic.apps.googleusercontent.com.json',
                             'oauth-client.json', 'oauth-tokens.json'], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 3
