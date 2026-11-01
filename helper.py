#!/usr/bin/env python3
"""Local Spotify helper for the Now Playing overlay.

Why this exists
---------------
The overlay page talks to Spotify directly when it is served from GitHub Pages,
and that is still the supported setup. Inside Streamlabs Desktop and OBS it can
stop working: their embedded Chromium fails the TLS handshake with
accounts.spotify.com (ERR_SSL_PROTOCOL_ERROR) on machines where curl, Chrome and
Python all reach the same host without complaint. The token refresh then dies
about an hour in and the card sits on "Reconnecting..." for the rest of the
stream.

So this script takes over every part that needs TLS. It holds the refresh token,
talks to Spotify over Python's own TLS stack, and serves two things on loopback:

    /             the overlay page, read straight from index.html
    /nowplaying   the latest currently-playing response, wrapped in JSON

The browser source then only ever speaks plain HTTP to 127.0.0.1, where there is
no handshake for the embedded browser to get wrong. index.html notices it is
being served from localhost and switches to reading /nowplaying by itself.

Usage
-----
    python helper.py                  first run asks for your Client ID
    python helper.py --port 8766      if 8765 is taken
    python helper.py --reauth         forget the stored login and log in again

Point the browser source at http://127.0.0.1:8765/ and leave this running.
Standard library only -- nothing to pip install.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SCOPES = "user-read-currently-playing user-read-playback-state"
POLL_SECONDS = 3.0
HTTP_TIMEOUT = 10
# Spotify can keep rejecting a token it just issued (app access revoked from the
# account page). Refreshing cannot fix that, so stop rather than spin forever.
MAX_UNAUTHORIZED = 5

BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "index.html"
CONFIG_PATH = BASE_DIR / "helper_config.json"


class AuthError(Exception):
    """Fatal means no amount of retrying will help: the login must be redone."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


# ---------------------------------------------------------------- shared state

_state_lock = threading.Lock()
_state: dict = {"state": "idle", "message": "Starting"}


def set_state(value: dict) -> None:
    global _state
    with _state_lock:
        _state = value


def get_state() -> dict:
    with _state_lock:
        return _state


# The callback handler runs on a server thread and hands the code back here.
AUTH: dict = {"event": threading.Event(), "code": None, "error": None}


# ----------------------------------------------------------------- HTTP to API


def _request(url: str, *, data: bytes | None = None, headers: dict | None = None):
    """Returns (status, body). Raises AuthError only when there was no reply."""
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        # An error status is still an answer, and its body carries the reason.
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        host = urllib.parse.urlsplit(url).netloc
        raise AuthError(f"could not reach {host}: {exc}", fatal=False) from exc


def post_token(payload: dict) -> dict:
    """One token request, with the two kinds of failure kept apart.

    invalid_grant and other non-429 4xx replies mean the request itself is wrong
    -- dead refresh token, wrong Client ID, a Redirect URI that doesn't match --
    and will stay wrong. 429, 5xx and network trouble are worth another go.
    """
    status, raw = _request(
        "https://accounts.spotify.com/api/token",
        data=urllib.parse.urlencode(payload).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    if status != 200 or "access_token" not in data:
        detail = (
            data.get("error_description")
            or data.get("error")
            or raw[:200].decode("utf-8", "replace")
            or "no detail given"
        )
        fatal = data.get("error") == "invalid_grant" or (400 <= status < 500 and status != 429)
        raise AuthError(f"Spotify rejected the login (HTTP {status}): {detail}", fatal=fatal)
    return data


# --------------------------------------------------------------------- config


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text("utf-8"))
    except (ValueError, OSError) as exc:
        print(f"! {CONFIG_PATH.name} could not be read ({exc}); starting fresh")
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    # This file holds a live refresh token. On POSIX, narrow it to the owner;
    # on Windows the user profile's own ACL already does that, and chmod is a
    # no-op there, so a failure here is not worth stopping for.
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


# ----------------------------------------------------------------------- PKCE


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


class TokenStore:
    """Holds the access token and refreshes it when it is about to expire."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._access: str | None = None
        self._expires_at = 0.0

    def access_token(self) -> str:
        with self._lock:
            if self._access and time.monotonic() < self._expires_at - 30:
                return self._access
            data = post_token(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": self.cfg["refresh_token"],
                    "client_id": self.cfg["client_id"],
                }
            )
            # Spotify rotates the refresh token and invalidates the one just
            # used, so the replacement has to be written out immediately -- and
            # this is exactly why two copies of the overlay sharing one account
            # used to knock each other offline. One process, one token, no race.
            if data.get("refresh_token"):
                self.cfg["refresh_token"] = data["refresh_token"]
                save_config(self.cfg)
            self._access = data["access_token"]
            self._expires_at = time.monotonic() + float(data.get("expires_in", 3600))
            return self._access

    def forget_access(self) -> None:
        with self._lock:
            self._access = None
            self._expires_at = 0.0


# --------------------------------------------------------------------- polling


def poll_once(tokens: TokenStore) -> tuple[str, object]:
    """Returns (kind, payload). Only the token refresh raises."""
    token = tokens.access_token()
    status, raw = _request(
        "https://api.spotify.com/v1/me/player/currently-playing",
        headers={"Authorization": "Bearer " + token},
    )
    if status == 204:
        return "idle", "Nothing playing"
    if status == 401:
        tokens.forget_access()
        return "unauthorized", None
    # Rate limits and Spotify-side outages are momentary: hold the last known
    # state rather than blanking the card over one bad response.
    if status == 429 or status >= 500:
        return "hold", None
    if status >= 400:
        return "idle", "Spotify unavailable"
    try:
        return "ok", json.loads(raw)
    except ValueError:
        return "hold", None


def poll_loop(tokens: TokenStore, stop: threading.Event) -> None:
    unauthorized = 0
    while not stop.is_set():
        try:
            kind, payload = poll_once(tokens)
            if kind == "unauthorized":
                unauthorized += 1
                if unauthorized >= MAX_UNAUTHORIZED:
                    message = (
                        f"Spotify rejected the access token {MAX_UNAUTHORIZED} times running. "
                        "Access was most likely revoked from your Spotify account page."
                    )
                    print(f"! {message}")
                    print("  Re-run with --reauth once you have granted access again.")
                    set_state({"state": "error", "message": message, "fatal": True})
                    return
                set_state({"state": "error", "message": "access token rejected, retrying", "fatal": False})
            else:
                unauthorized = 0
                if kind == "ok":
                    set_state({"state": "ok", "data": payload})
                elif kind == "idle":
                    set_state({"state": "idle", "message": payload})
                # "hold": leave the previous state exactly as it was.
        except AuthError as exc:
            print(f"! {exc}")
            set_state({"state": "error", "message": str(exc), "fatal": exc.fatal})
            if exc.fatal:
                print(f"  The stored login is dead. Re-run with --reauth, or delete {CONFIG_PATH.name}.")
                return
        except Exception as exc:  # the poller must outlive anything unexpected
            print(f"! unexpected poll error: {exc!r}")
        stop.wait(POLL_SECONDS)


# ------------------------------------------------------------------ web server


class Handler(BaseHTTPRequestHandler):
    server_version = "SpotifyOverlayHelper/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # a request line every three seconds would bury the real output

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        split = urllib.parse.urlsplit(self.path)
        path = split.path
        if path in ("/", "/index.html"):
            try:
                body = INDEX_HTML.read_bytes()
            except OSError as exc:
                self._send(500, f"cannot read index.html: {exc}".encode(), "text/plain; charset=utf-8")
                return
            self._send(200, body, "text/html; charset=utf-8")
        elif path == "/nowplaying":
            self._send(200, json.dumps(get_state()).encode(), "application/json")
        elif path == "/callback":
            self._callback(urllib.parse.parse_qs(split.query))
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def _callback(self, query: dict) -> None:
        if AUTH["event"].is_set():
            self._send(200, b"Already handled. You can close this tab.", "text/plain; charset=utf-8")
            return
        if "error" in query:
            AUTH["error"] = query["error"][0]
        elif "code" in query:
            AUTH["code"] = query["code"][0]
        else:
            self._send(400, b"no code in callback", "text/plain; charset=utf-8")
            return
        page = (
            b"<!doctype html><meta charset=utf-8><title>Spotify login</title>"
            b"<body style='background:#121212;color:#eee;font:16px system-ui;padding:48px'>"
            b"<p>Spotify login received. Close this tab and go back to the terminal.</p>"
        )
        self._send(200, page, "text/html; charset=utf-8")
        AUTH["event"].set()


def authorize(client_id: str, redirect_uri: str) -> str:
    verifier, challenge = pkce_pair()
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "scope": SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "redirect_uri": redirect_uri,
        }
    )
    url = "https://accounts.spotify.com/authorize?" + params
    print("\nOpening your browser to log in to Spotify.")
    print("If nothing opens, paste this into a normal browser -- not Streamlabs:\n")
    print("  " + url + "\n")
    try:
        webbrowser.open(url)
    except Exception:  # headless or no default browser; the printed URL still works
        pass
    if not AUTH["event"].wait(timeout=300):
        raise AuthError("timed out waiting for the Spotify login (5 minutes)", fatal=True)
    if AUTH["error"]:
        raise AuthError(f"Spotify refused the authorization: {AUTH['error']}", fatal=True)
    data = post_token(
        {
            "grant_type": "authorization_code",
            "code": AUTH["code"],
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        }
    )
    if not data.get("refresh_token"):
        raise AuthError("Spotify returned no refresh token", fatal=True)
    return data["refresh_token"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    parser.add_argument("--client-id", default=None, help="Spotify app Client ID (stored after the first run)")
    parser.add_argument("--reauth", action="store_true", help="discard the stored login and log in again")
    args = parser.parse_args()

    cfg = load_config()
    if args.client_id:
        cfg["client_id"] = args.client_id.strip()
    if args.reauth:
        cfg.pop("refresh_token", None)

    redirect_uri = f"http://{HOST}:{args.port}/callback"

    if not cfg.get("client_id"):
        print("Your Spotify app's Client ID is needed once.")
        print(f"\nFirst, in the Spotify dashboard, add this exact Redirect URI to the app:\n\n  {redirect_uri}\n")
        try:
            cfg["client_id"] = input("Client ID: ").strip()
        except EOFError:
            cfg["client_id"] = ""
        if not cfg["client_id"]:
            print("No Client ID given; nothing to do.")
            return 1
        # Store it before attempting the login, not after. A Redirect URI typo
        # shouldn't cost you the Client ID as well on every retry.
        save_config(cfg)

    try:
        server = ThreadingHTTPServer((HOST, args.port), Handler)
    except OSError as exc:
        print(f"! cannot listen on {HOST}:{args.port} -- {exc}")
        print(f"  Something else is using that port. Try --port {args.port + 1}.")
        return 1
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if not cfg.get("refresh_token"):
        try:
            cfg["refresh_token"] = authorize(cfg["client_id"], redirect_uri)
        except AuthError as exc:
            print(f"! {exc}")
            print(f"  Check that {redirect_uri} is registered as a Redirect URI on the app.")
            server.shutdown()
            return 1
        print(f"Login stored in {CONFIG_PATH.name}.")
    save_config(cfg)

    tokens = TokenStore(cfg)
    stop = threading.Event()
    threading.Thread(target=poll_loop, args=(tokens, stop), daemon=True).start()

    print(f"\n  Overlay      http://{HOST}:{args.port}/")
    print(f"  Now playing  http://{HOST}:{args.port}/nowplaying")
    print("\nPoint the Streamlabs or OBS browser source at the first URL and leave this running.")
    print("Ctrl-C to stop.\n")
    try:
        # Keep serving even if the poller has given up, so the overlay can show
        # the reason instead of going blank.
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        stop.set()
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
