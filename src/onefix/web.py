"""Private website for the cards, and the daily sync that feeds it.

Usage: python -m onefix.web

One always-on process: it serves the page from <ONEFIX_WEB_DIR>/data.json (written by
`onefix.publish`) and runs `scripts/sync.sh` once a day. It never reads the Steam config.

Environment:
  ONEFIX_WEB_PASSWORD   shared password for you and your friends. Without it the server only
                        listens on 127.0.0.1 (local preview) and asks for no password.
  ONEFIX_WEB_DIR        folder holding data.json (default parsed/web)
  ONEFIX_SYNC_HOUR_UTC  hour of the daily sync, 0-23 (default 6); "off" for no syncing
  PORT                  port to listen on (default 8000)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from onefix.publish import DATA_FILE

STATIC = Path(__file__).parent / "static"
REPO = Path(__file__).resolve().parents[2]
COOKIE = "onefix_session"
SESSION_SECONDS = 30 * 24 * 3600
STALE_AFTER = timedelta(hours=24)
WRONG_PASSWORD_DELAY = 1.0
MAX_FORM_BYTES = 4096
STATIC_FILES = {
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


def session_token(password: str) -> str:
    """The cookie value. Derived from the password, so it survives restarts and changing the
    password signs everyone out. It cannot be turned back into the password."""
    return hmac.new(password.encode(), b"onefix-session-v1", hashlib.sha256).hexdigest()


def next_run(now: datetime, hour: int) -> datetime:
    """The next time the clock reads `hour`:00 UTC, strictly after `now`."""
    run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return run if run > now else run + timedelta(days=1)


def is_stale(synced_at: str | None, now: datetime) -> bool:
    if not synced_at:
        return True
    try:
        then = datetime.strptime(synced_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return now - then > STALE_AFTER


class Syncer:
    """Runs the sync command, one run at a time."""

    def __init__(self, command: list[str] | None):
        self.command = command
        self._lock = threading.Lock()
        self.running = False
        self.last_ok: bool | None = None

    def start(self) -> bool:
        """Start a run in the background. False if syncing is off or one is already running."""
        if self.command is None:
            return False
        with self._lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self) -> None:
        try:
            self.last_ok = subprocess.run(self.command, cwd=REPO).returncode == 0
        except OSError as err:
            print(f"sync could not start: {err}", flush=True)
            self.last_ok = False
        finally:
            self.running = False

    def state(self) -> dict:
        return {"enabled": self.command is not None, "running": self.running, "last_ok": self.last_ok}


class App:
    def __init__(self, web_dir: Path, password: str | None, syncer: Syncer):
        self.web_dir = web_dir
        self.password = password
        self.syncer = syncer
        self.login_lock = threading.Lock()

    def read_data(self) -> dict | None:
        try:
            return json.loads((self.web_dir / DATA_FILE).read_text())
        except (OSError, ValueError):
            return None

    def signed_in(self, cookie_header: str | None) -> bool:
        if self.password is None:
            return True
        try:
            morsel = SimpleCookie(cookie_header or "").get(COOKIE)
        except Exception:  # a malformed Cookie header is just "not signed in"
            return False
        return morsel is not None and hmac.compare_digest(morsel.value, session_token(self.password))

    def check_password(self, attempt: str) -> bool:
        ok = hmac.compare_digest(attempt.encode(), (self.password or "").encode())
        if not ok:
            with self.login_lock:  # one slow answer at a time: guessing is limited to 1 per second
                time.sleep(WRONG_PASSWORD_DELAY)
        return ok


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "onefix"

        def log_message(self, fmt, *args):  # quiet: the deploy log is for the sync output
            pass

        def _send(self, status: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8",
                  headers: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _redirect(self, to: str, headers: dict | None = None) -> None:
            self._send(303, headers={"Location": to, **(headers or {})})

        def _page(self, name: str, error: str = "") -> None:
            html = (STATIC / name).read_text().replace("<!--ERROR-->", error)
            self._send(200, html.encode(), "text/html; charset=utf-8")

        def _cookie(self, value: str, max_age: int) -> str:
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            return f"{COOKIE}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}"

        def _authed(self) -> bool:
            return app.signed_in(self.headers.get("Cookie"))

        def do_GET(self) -> None:
            path, _, query = self.path.partition("?")
            if path == "/healthz":
                self._send(200, b"ok")
            elif path in STATIC_FILES:
                name, ctype = STATIC_FILES[path]
                self._send(200, (STATIC / name).read_bytes(), ctype)
            elif path == "/login":
                if app.password is None or self._authed():
                    self._redirect("/")
                else:
                    wrong = "wrong" in parse_qs(query)
                    self._page("login.html", '<p class="error" role="alert">Wrong password.</p>' if wrong else "")
            elif path == "/":
                self._page("index.html") if self._authed() else self._redirect("/login")
            elif path == "/api/data":
                if not self._authed():
                    self._json(401, {"error": "sign in"})
                else:
                    self._json(200, {"data": app.read_data(), "sync": app.syncer.state()})
            else:
                self._send(404, b"not found")

        do_HEAD = do_GET

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_FORM_BYTES:
                return self._send(413, b"too large")
            body = self.rfile.read(length).decode("utf-8", "replace")
            if path == "/login":
                attempt = parse_qs(body).get("password", [""])[0]
                if app.password is not None and app.check_password(attempt):
                    self._redirect("/", {"Set-Cookie": self._cookie(session_token(app.password), SESSION_SECONDS)})
                else:
                    self._redirect("/login?wrong=1")
            elif path == "/logout":
                self._redirect("/login", {"Set-Cookie": self._cookie("", 0)})
            elif path == "/api/sync":
                # The custom header cannot be sent by a plain cross-site form.
                if not self._authed() or self.headers.get("X-Onefix") != "1":
                    self._json(401, {"error": "sign in"})
                else:
                    started = app.syncer.start()
                    self._json(202, {"started": started, "sync": app.syncer.state()})
            else:
                self._send(404, b"not found")

    return Handler


def schedule(app: App, hour: int) -> None:
    """Sync at start-up if the data is missing or over a day old, then every day at `hour` UTC."""
    data = app.read_data()
    if is_stale((data or {}).get("synced_at"), datetime.now(timezone.utc)):
        app.syncer.start()
    while True:
        now = datetime.now(timezone.utc)
        time.sleep(max(1.0, (next_run(now, hour) - now).total_seconds()))
        app.syncer.start()


def main() -> None:
    password = os.environ.get("ONEFIX_WEB_PASSWORD") or None
    web_dir = Path(os.environ.get("ONEFIX_WEB_DIR", "parsed/web"))
    port = int(os.environ.get("PORT", "8000"))
    hour_text = os.environ.get("ONEFIX_SYNC_HOUR_UTC", "6").strip().lower()
    hour = None if hour_text == "off" else int(hour_text)
    if hour is not None and not 0 <= hour <= 23:
        raise SystemExit("ONEFIX_SYNC_HOUR_UTC must be 0-23 or 'off'")

    syncer = Syncer(None if hour is None else ["sh", "scripts/sync.sh"])
    app = App(web_dir, password, syncer)
    # No password means no protection, so only this machine may connect.
    host = "0.0.0.0" if password else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), make_handler(app))
    if hour is not None:
        threading.Thread(target=schedule, args=(app, hour), daemon=True).start()
    note = "" if password else " (no ONEFIX_WEB_PASSWORD set: local connections only, no sign-in)"
    print(f"Serving on http://{host}:{port}{note}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
