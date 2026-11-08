"""Personal Desktop OAuth configuration and tokens, held only in Secret Service."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import webbrowser

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .storage import private_directory

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
CACHE_FILE = "account-feed.json"
MAX_CONFIG = 16_384
MAX_VAULT = 65_536


class AccountError(Exception):
    def __init__(self, message, code="account_error"):
        super().__init__(message)
        self.code = code


def parse_client(raw: bytes) -> dict:
    """Accept only a Google Desktop client. Never trust imported endpoints."""
    try:
        if len(raw) > MAX_CONFIG:
            raise ValueError()
        config = json.loads(raw)["installed"]
        ident, secret = config["client_id"].strip(), config["client_secret"].strip()
        if (not re.fullmatch(r"[A-Za-z0-9_-]{3,200}\.apps\.googleusercontent\.com", ident)
                or not 1 <= len(secret) <= 512 or any(char.isspace() for char in secret)):
            raise ValueError()
        if (config.get("auth_uri") not in {AUTH_URI, "https://accounts.google.com/o/oauth2/auth"}
                or config.get("token_uri") != TOKEN_URI):
            raise ValueError()
        return {"installed": {"client_id": ident, "client_secret": secret,
                              "auth_uri": AUTH_URI, "token_uri": TOKEN_URI}}
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        raise AccountError("Choose the JSON for a Google Desktop app client, or paste its Client ID and Client secret. "
                           "Web clients, API keys and service-account keys are not supported.", "invalid_client") from None


class SecretVault:
    """One keyring item per local library; no plaintext/file fallback or exported path."""
    def __init__(self, directory):
        namespace = hashlib.sha256(str(Path(directory).resolve()).encode()).hexdigest()
        self.attributes = {"application": "ch.aboimpinto.QuietTube", "library": namespace, "purpose": "personal-oauth"}

    @contextmanager
    def collection(self):
        import secretstorage
        connection = None
        try:
            connection = secretstorage.dbus_init()
            # Do not silently create an unprotected keyring if the desktop has none.
            collection = secretstorage.Collection(connection)
            if collection.is_locked():
                collection.unlock(timeout=60)
            if collection.is_locked():
                raise AccountError("Unlock your desktop login keyring to use personal OAuth.", "keyring_unavailable")
            yield collection
        except AccountError:
            raise
        except Exception:
            raise AccountError("The desktop keyring is unavailable or locked. Set up and unlock a Secret Service "
                               "keyring (such as GNOME Keyring), then retry. Nothing is saved as plaintext.",
                               "keyring_unavailable") from None
        finally:
            if connection:
                connection.close()

    def read(self):
        with self.collection() as collection:
            item = next(iter(collection.search_items(self.attributes)), None)
            if item is None:
                return {}
            raw = item.get_secret()
            if len(raw) > MAX_VAULT:
                raise AccountError("The saved OAuth entry cannot be read. Remove it and configure your Desktop client again.")
            try:
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError()
                return value
            except (ValueError, TypeError, UnicodeError):
                raise AccountError("The saved OAuth entry cannot be read. Remove it and configure your Desktop client again.") from None

    def write(self, value):
        raw = json.dumps(value).encode()
        if len(raw) > MAX_VAULT:
            raise AccountError("Google returned too much authorization data. No changes were saved.")
        with self.collection() as collection:
            collection.create_item("QuietTube personal OAuth", self.attributes, raw,
                                   replace=True, content_type="application/json")

    def delete(self):
        with self.collection() as collection:
            for item in collection.search_items(self.attributes):
                item.delete()


class DesktopBrowser:
    def open(self, url, **_):
        # Desktop launch is outside the disposable worker group. No URL in logs.
        try:
            subprocess.run(["gio", "open", url], check=True, timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except (OSError, subprocess.SubprocessError):
            raise AccountError("Could not open Google's sign-in page in your default browser.") from None
        return True


class Account:
    def __init__(self, directory: Path, vault=None):
        self.directory = private_directory(Path(directory))
        self.vault = vault if vault is not None else SecretVault(self.directory)

    @contextmanager
    def locked(self):
        # Lock contains no credentials; protects refreshes in independent workers.
        fd = os.open(self.directory / "oauth.lock", os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def configure(self, request):
        try:
            if request.get("client_file"):
                with open(request["client_file"], "rb") as stream:
                    raw = stream.read(MAX_CONFIG + 1)
            else:
                raw = json.dumps({"installed": {"client_id": request.get("client_id", ""),
                    "client_secret": request.get("client_secret", ""), "auth_uri": AUTH_URI,
                    "token_uri": TOKEN_URI}}).encode()
        except (OSError, TypeError):
            raise AccountError("Could not read the selected Desktop client JSON file.", "invalid_client") from None
        client = parse_client(raw)
        with self.locked():
            previous = self.vault.read()
            changed = previous.get("client") != client
            value = {"client": client}
            if not changed and previous.get("tokens"):
                value["tokens"] = previous["tokens"]
            self.vault.write(value)
            if changed:
                (self.directory / CACHE_FILE).unlink(missing_ok=True)
        return {"configured": True, "authorization_saved": bool(value.get("tokens")), "client_changed": changed}

    def client(self, value):
        if not value.get("client"):
            raise AccountError("Import your Desktop client JSON or save its Client ID and Client secret first.",
                               "client_not_configured")
        return parse_client(json.dumps(value["client"]).encode())

    def connect(self):
        with self.locked():
            client = self.client(self.vault.read())
        flow = InstalledAppFlow.from_client_config(client, SCOPES, autogenerate_code_verifier=True)
        webbrowser.register("quiettube-desktop", None, DesktopBrowser())
        try:
            credentials = flow.run_local_server(
                host="127.0.0.1", port=0, timeout_seconds=240,
                browser="quiettube-desktop", authorization_prompt_message=None,
                success_message="Return to QuietTube to check whether sign-in completed. You can close this tab.",
                access_type="offline", prompt="consent")
            granted = credentials.granted_scopes
            if (not credentials.refresh_token or not credentials.has_scopes(SCOPES)
                    or (granted is not None and not set(SCOPES).issubset(granted))):
                raise AccountError("Approve the requested YouTube access to connect QuietTube, then retry sign-in.")
            from .youtube_api import api_request
            api_request(credentials.token, "subscriptions", {"part": "id", "mine": "true", "maxResults": 1})
            with self.locked():
                # A cancelled/replaced configuration must never be resurrected.
                if self.client(self.vault.read()) != client:
                    raise AccountError("The Desktop client changed during sign-in. Please sign in again.")
                self.vault.write({"client": client, "tokens": json.loads(credentials.to_json())})
                (self.directory / CACHE_FILE).unlink(missing_ok=True)
            return {"connected": True, "account_connected": True}
        except AccountError:
            raise
        except Exception:
            raise AccountError("Google sign-in was cancelled, timed out, or could not be completed. Please try again.") from None

    def access_token(self, rejected_token=None):
        with self.locked():
            value = self.vault.read()
            client = self.client(value)["installed"]
            try:
                info = dict(value.get("tokens") or {})
                if info.get("client_id") != client["client_id"] or not set(SCOPES).issubset(info.get("scopes", [])):
                    raise ValueError()
                info.update(client)
                credentials = Credentials.from_authorized_user_info(info)
                if not credentials.refresh_token:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise AccountError("Sign in with Google using your saved Desktop client.", "sign_in_required") from None
            if not credentials.valid or (rejected_token and credentials.token == rejected_token):
                try:
                    credentials.refresh(Request())
                except RefreshError as error:
                    detail = error.args[1] if len(error.args) > 1 and isinstance(error.args[1], dict) else {}
                    if detail.get("error") == "invalid_grant":
                        self.vault.write({"client": value["client"]})
                        (self.directory / CACHE_FILE).unlink(missing_ok=True)
                        raise AccountError("Google authorization expired or was revoked. Sign in with Google again.",
                                           "sign_in_required") from None
                    raise AccountError("Google could not renew access. Retry later; your saved authorization is retained.") from None
                except TransportError:
                    raise AccountError("Could not reach Google to renew access. Check your connection and retry.") from None
                value["tokens"] = json.loads(credentials.to_json())
                self.vault.write(value)
            return credentials.token

    def forget(self):
        # The UI cancels/reaps account workers first. Google revocation is a
        # separate explicit action at the linked Google permissions page.
        with self.locked():
            self.vault.delete()
            (self.directory / CACHE_FILE).unlink(missing_ok=True)
        return {"forgotten": True}
