"""Google OAuth for the Hub: one client, one token file, stdlib only.

One-time login on the laptop:
    python3 -m connectors.google_auth login client_secret.json ./google-token.json
then copy the token to the VPS as ~/.hermes/google-token.json (chmod 600).
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TOKEN_PATH = Path.home() / ".hermes" / "google-token.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
REFRESH_MARGIN = timedelta(minutes=5)


class AuthError(RuntimeError):
    """Google rejected the token; the owner must log in again."""


class TokenMissing(AuthError):
    """No token file yet (Google login never done)."""


def _post(url: str, fields: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _save(token: dict, path: Path) -> None:
    """Atomic write; the unique 0600 temp file keeps hub-status and infobot refreshing at once apart."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(token))
    os.replace(tmp, path)


def access_token(path=TOKEN_PATH, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    path = Path(path)
    try:
        token = json.loads(path.read_text())
    except FileNotFoundError as err:
        raise TokenMissing("belum login Google") from err
    except (OSError, ValueError) as err:
        raise AuthError(f"token Google rusak: {err}") from err
    expiry = datetime.fromisoformat(token["expiry"]) if token.get("expiry") else now
    if token.get("access_token") and expiry - now > REFRESH_MARGIN:
        return token["access_token"]
    try:
        fresh = _post(TOKEN_URL, {"client_id": token["client_id"], "client_secret": token["client_secret"],
                                  "refresh_token": token["refresh_token"], "grant_type": "refresh_token"})
    except urllib.error.HTTPError as err:
        if "invalid_grant" in err.read().decode("utf-8", "replace"):
            raise AuthError("refresh token Google dicabut atau kedaluwarsa") from err
        raise
    updated = {**token, "access_token": fresh["access_token"],
               "expiry": (now + timedelta(seconds=int(fresh.get("expires_in", 3600)))).isoformat()}
    _save(updated, path)
    return updated["access_token"]


def login(client_file: str, path=TOKEN_PATH) -> None:
    client = json.loads(Path(client_file).read_text())["installed"]
    got: dict = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Login selesai, tab ini boleh ditutup.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Callback)
    redirect = f"http://127.0.0.1:{server.server_port}"
    state = secrets.token_urlsafe(16)
    print("Buka URL ini di browser:\n" + AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state}))
    while "code" not in got and "error" not in got:
        server.handle_request()
    if got.get("state") != state or "code" not in got:
        raise AuthError(f"login gagal: {got.get('error', 'state tidak cocok')}")
    tok = _post(TOKEN_URL, {"code": got["code"], "client_id": client["client_id"],
                            "client_secret": client["client_secret"], "redirect_uri": redirect,
                            "grant_type": "authorization_code"})
    if "refresh_token" not in tok:
        raise AuthError("tidak ada refresh_token; cabut akses app di myaccount.google.com/permissions lalu ulangi")
    _save({"client_id": client["client_id"], "client_secret": client["client_secret"],
           "refresh_token": tok["refresh_token"], "access_token": tok["access_token"],
           "expiry": (datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 3600)))).isoformat()},
          Path(path))
    print(f"Token tersimpan di {path}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "login":
        sys.exit("pakai: python3 -m connectors.google_auth login client_secret.json [token_path]")
    login(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else TOKEN_PATH)
