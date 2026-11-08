"""Real encrypted Secret Service round-trip on an isolated bus and temporary home data."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def test_real_secret_service_never_writes_plaintext_credentials(tmp_path):
    if not all(shutil.which(tool) for tool in ('dbus-run-session', 'gnome-keyring-daemon')):
        pytest.skip('Install dbus and gnome-keyring for the isolated Secret Service test')
    env = dict(os.environ)
    for name in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_RUNTIME_DIR'):
        directory = tmp_path / name.lower()
        directory.mkdir(mode=0o700)
        env[name] = str(directory)
    env.pop('GNOME_KEYRING_CONTROL', None)
    # This child gets a NEW bus. It must never contact the user's login keyring.
    script = r'''
import os
import json
from pathlib import Path
import subprocess
import sys
from quiettube.account import Account, SecretVault
root = Path(sys.argv[1])
subprocess.run(['gnome-keyring-daemon', '--unlock', '--components=secrets'],
               input=b'synthetic-keyring-password', stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL, check=True, timeout=15)
account = Account(root / 'library')
secret = 'synthetic-only-client-secret-keyring-test'
request = {'action': 'oauth_configure', 'account_dir': str(account.directory),
           'client_id': 'synthetic.apps.googleusercontent.com', 'client_secret': secret}
result = subprocess.run([sys.executable, '-m', 'quiettube.worker'], input=json.dumps(request),
                        capture_output=True, text=True, timeout=15, check=True)
assert json.loads(result.stdout)['configured']
assert secret not in result.stdout + result.stderr
assert account.vault.read()['client']['installed']['client_secret'] == secret
assert SecretVault(root / 'another-library').read() == {}
value = account.vault.read()
value['tokens'] = {'refresh_token': 'synthetic-refresh-keyring-test'}
account.vault.write(value)
assert account.vault.read() == value
keyrings = list((Path(os.environ['XDG_DATA_HOME']) / 'keyrings').glob('*.keyring'))
assert keyrings, 'The test must exercise an on-disk keyring'
for path in root.rglob('*'):
    if path.is_file():
        raw = path.read_bytes()
        assert secret.encode() not in raw
        assert b'synthetic-refresh-keyring-test' not in raw
assert account.forget() == {'forgotten': True}
assert account.vault.read() == {}
'''
    result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parent.parent, env=env,
                            capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stderr
