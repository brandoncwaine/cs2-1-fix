"""Invite-only website for the cards, and the daily sync that feeds it.

Usage: python -m onefix.web

One always-on process. People sign in through Steam, so we learn their steamid64 without ever
seeing a password. A new person needs the invite code, then gives the two codes that let us
fetch their matches (`onefix.accounts`). Everyone sees only their own cards; the owner can see
everyone's and remove people. Cards come from <ONEFIX_WEB_DIR>/data.json (`onefix.publish`),
refreshed by `scripts/sync.sh` once a day and whenever someone joins.

Environment:
  ONEFIX_INVITE_CODE    code a new person must enter (falls back to ONEFIX_WEB_PASSWORD).
                        Without one, nobody new can join.
  ONEFIX_STEAMID        the owner's steamid64 (also the first player in the ingest config)
  ONEFIX_MAX_USERS      most people who may join by invite (default 10)
  ONEFIX_BASE_URL       public address, e.g. https://example.com (default: Railway's public
                        domain, else http://127.0.0.1:<PORT>)
  ONEFIX_HOST           address to listen on (default 127.0.0.1; the cloud image sets 0.0.0.0)
  ONEFIX_WEB_DIR        folder holding data.json (default parsed/web)
  ONEFIX_CONFIG_DIR     private folder for the user database and session secret
  ONEFIX_SYNC_HOUR_UTC  hour of the daily sync, 0-23 (default 6); "off" for no syncing
  ONEFIX_LOCAL_USER     local preview only: act as this steamid64 without signing in.
                        Refused unless listening on 127.0.0.1.
  STEAM_WEB_API_KEY     used to check a new person's codes with Steam before saving them
  PORT                  port to listen on (default 8000)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl

from onefix import steam_openid
from onefix.accounts import OWNER_IMPORTED, STEAMID_RE, Accounts, clean_join, steam_check
from onefix.publish import DATA_FILE

STATIC = Path(__file__).parent / "static"
REPO = Path(__file__).resolve().parents[2]
SESSION_COOKIE = "onefix_session"
STATE_COOKIE = "onefix_state"
SESSION_SECONDS = 30 * 24 * 3600
STATE_SECONDS = 600
STALE_AFTER = timedelta(hours=24)
WRONG_INVITE_DELAY = 1.0
MAX_BODY_BYTES = 4096
STATIC_FILES = {
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    # Map pictures for the card banners: one per map, named after it (de_mirage -> mirage.jpg).
    **{f"/static/maps/{p.name}": (f"maps/{p.name}", "image/jpeg") for p in sorted((STATIC / "maps").glob("*.jpg"))},
}


def sign_session(secret: bytes, steamid: str, expires: int) -> str:
    body = f"{steamid}.{expires}"
    return f"{body}.{hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()}"


def read_session(secret: bytes, value: str, now: int) -> str | None:
    """The steamid64 a session cookie was issued to, or None if it is forged or expired."""
    parts = value.split(".")
    if len(parts) != 3:
        return None
    steamid, expires, _ = parts
    if not hmac.compare_digest(value, sign_session(secret, steamid, int(expires) if expires.isdigit() else 0)):
        return None
    if int(expires) < now or not STEAMID_RE.fullmatch(steamid):
        return None
    return steamid


def load_secret(config_dir: Path) -> bytes:
    """The key that signs session cookies. Kept on disk so sign-ins survive a restart."""
    if os.environ.get("ONEFIX_SESSION_SECRET"):
        return os.environ["ONEFIX_SESSION_SECRET"].encode()
    path = config_dir / "session-secret"
    if not path.exists():
        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(secrets.token_hex(32))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    return path.read_text().strip().encode()


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
    """Runs the sync command, one run at a time. A request during a run queues one more run,
    so someone who joins mid-sync is still picked up."""

    def __init__(self, command: list[str] | None):
        self.command = command
        self._lock = threading.Lock()
        self.running = False
        self.again = False
        self.last_ok: bool | None = None

    def start(self) -> bool:
        """Start a run in the background (or queue one). False if syncing is off."""
        if self.command is None:
            return False
        with self._lock:
            if self.running:
                self.again = True
                return True
            self.running = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self) -> None:
        while True:
            try:
                self.last_ok = subprocess.run(self.command, cwd=REPO).returncode == 0
            except OSError as err:
                print(f"sync could not start: {err}", flush=True)
                self.last_ok = False
            with self._lock:
                if not self.again:
                    self.running = False
                    return
                self.again = False

    def state(self) -> dict:
        return {"enabled": self.command is not None, "running": self.running, "last_ok": self.last_ok}


@dataclass
class Settings:
    web_dir: Path
    base_url: str
    secret: bytes
    invite: str | None = None
    owner: str | None = None
    config_players: dict = field(default_factory=dict)  # steamid -> name, set up outside the site
    api_key: str | None = None
    max_users: int = 10
    local_user: str | None = None


class App:
    def __init__(self, settings: Settings, accounts: Accounts, syncer: Syncer,
                 check=steam_check, ask_steam=None):
        self.s = settings
        self.accounts = accounts
        self.syncer = syncer
        self.check = check
        self.ask_steam = ask_steam  # None = really ask Steam
        self.invite_lock = threading.Lock()

    def read_data(self) -> dict | None:
        try:
            return json.loads((self.s.web_dir / DATA_FILE).read_text())
        except (OSError, ValueError):
            return None

    def user(self, cookie_header: str | None) -> str | None:
        """The signed-in steamid64, if any."""
        if self.s.local_user:
            return self.s.local_user
        try:
            morsel = SimpleCookie(cookie_header or "").get(SESSION_COOKIE)
        except Exception:  # a malformed Cookie header is just "not signed in"
            return None
        return read_session(self.s.secret, morsel.value, int(time.time())) if morsel else None

    def member_name(self, steamid: str) -> str | None:
        """Name of someone whose matches we fetch, or None if they have not joined."""
        if steamid in self.s.config_players:
            return self.s.config_players[steamid]
        row = self.accounts.get(steamid)
        return row["name"] if row else None

    def invite_ok(self, attempt: str) -> bool:
        ok = bool(self.s.invite) and hmac.compare_digest(attempt.encode(), self.s.invite.encode())
        if not ok:
            with self.invite_lock:  # one slow answer at a time: guessing is limited to 1 per second
                time.sleep(WRONG_INVITE_DELAY)
        return ok

    def view(self, me: str, wanted: str | None) -> dict:
        """Everything the page may show to `me`. Only the owner may look at someone else."""
        owner = me == self.s.owner
        name = self.member_name(me)
        out = {
            "me": {"steamid": me, "name": name, "joined": name is not None, "owner": owner,
                   "invited": me not in self.s.config_players},
            "sync": self.syncer.state(), "synced_at": None, "player": None, "viewing": me,
            "joining_open": bool(self.s.invite) and self.accounts.count() < self.s.max_users,
        }
        data = self.read_data() or {}
        out["synced_at"] = data.get("synced_at")
        by_id = {p["steamid"]: p for p in data.get("players", [])}
        if owner:
            people = dict(self.s.config_players)
            people.update({u["steamid"]: u["name"] for u in self.accounts.all()})
            out["players"] = [
                {"steamid": sid, "name": n, "invited": sid not in self.s.config_players}
                for sid, n in people.items()]
            if wanted in people:
                out["viewing"] = wanted
        if name is not None or owner:
            target = out["viewing"]
            if self.member_name(target) is not None:  # removed users vanish at once
                out["player"] = by_id.get(target)
        return out

    def join(self, me: str, form: dict, now: str) -> tuple[int, dict]:
        if me in self.s.config_players:
            return 400, {"error": "Your account is already set up by the site owner."}
        existing = self.accounts.get(me)
        values, errors = clean_join(form)
        if errors:
            return 400, {"fields": errors}
        if not existing and me != self.s.owner:  # the owner needs no invite and no free place
            if not self.s.invite:
                return 403, {"error": "This site is not taking new people right now."}
            if not self.invite_ok(str(form.get("invite") or "").strip()):
                return 403, {"fields": {"invite": "That invite code is not right."}}
            if self.accounts.count() >= self.s.max_users:
                return 403, {"error": "This site is full. Ask the owner to make room."}
        warning = None
        if self.s.api_key:
            result = self.check(self.s.api_key, me, values["auth_code"], values["share_code"])
            if result == "rejected":
                return 400, {"fields": {"auth_code": "Steam did not accept this code for your account."}}
            if result == "unknown_code":
                return 400, {"fields": {"share_code": "Steam does not know this share code for your account."}}
            if result == "unreachable":
                warning = "Steam could not be reached to check your codes. They are saved and will be tried on the next sync."
        self.accounts.save(me, values["name"], values["auth_code"], values["share_code"], now)
        self.syncer.start()
        return 200, {"ok": True, "warning": warning}

    def remove(self, steamid: str) -> bool:
        gone = self.accounts.remove(steamid)
        if gone:
            self.syncer.start()  # the sync begins by deleting removed users' data
        return gone


def make_handler(app: App):
    secure = "; Secure" if app.s.base_url.startswith("https://") else ""

    class Handler(BaseHTTPRequestHandler):
        server_version = "onefix"

        def log_message(self, fmt, *args):  # quiet: the deploy log is for the sync output
            pass

        def _send(self, status: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8",
                  headers: list | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for k, v in headers or []:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _redirect(self, to: str, headers: list | None = None) -> None:
            self._send(303, headers=[("Location", to), *(headers or [])])

        def _page(self, name: str, error: str = "") -> None:
            html = (STATIC / name).read_text().replace("<!--ERROR-->", error)
            self._send(200, html.encode(), "text/html; charset=utf-8")

        def _cookie(self, name: str, value: str, max_age: int) -> tuple:
            # Lax, not Strict: the cookie must survive the redirect back from Steam. Requests
            # that change anything also need the X-Onefix header, which other sites cannot send.
            return ("Set-Cookie", f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax{secure}")

        def _me(self) -> str | None:
            return app.user(self.headers.get("Cookie"))

        def do_GET(self) -> None:
            path, _, query = self.path.partition("?")
            params = dict(parse_qsl(query, keep_blank_values=True))
            if path == "/healthz":
                self._send(200, b"ok")
            elif path in STATIC_FILES:
                name, ctype = STATIC_FILES[path]
                self._send(200, (STATIC / name).read_bytes(), ctype)
            elif path == "/login":
                if self._me():
                    self._redirect("/")
                else:
                    failed = '<p class="error" role="alert">Steam sign-in did not complete. Try again.</p>'
                    self._page("login.html", failed if "failed" in params else "")
            elif path == "/auth/steam":
                state = secrets.token_urlsafe(24)
                self._redirect(steam_openid.login_url(app.s.base_url, state),
                               [self._cookie(STATE_COOKIE, state, STATE_SECONDS)])
            elif path == steam_openid.RETURN_PATH:
                self._steam_return(params)
            elif path == "/":
                self._page("index.html") if self._me() else self._redirect("/login")
            elif path == "/api/data":
                me = self._me()
                if not me:
                    self._json(401, {"error": "sign in"})
                else:
                    self._json(200, app.view(me, params.get("player")))
            else:
                self._send(404, b"not found")

        do_HEAD = do_GET

        def _steam_return(self, params: dict) -> None:
            try:
                morsel = SimpleCookie(self.headers.get("Cookie") or "").get(STATE_COOKIE)
            except Exception:
                morsel = None
            state = morsel.value if morsel else ""
            kwargs = {"ask": app.ask_steam} if app.ask_steam else {}
            steamid = None
            if state and hmac.compare_digest(state, params.get("state", "")):
                steamid = steam_openid.verify(params, app.s.base_url, state, datetime.now(timezone.utc), **kwargs)
            clear_state = self._cookie(STATE_COOKIE, "", 0)
            if not steamid:
                return self._redirect("/login?failed=1", [clear_state])
            session = sign_session(app.s.secret, steamid, int(time.time()) + SESSION_SECONDS)
            self._redirect("/", [clear_state, self._cookie(SESSION_COOKIE, session, SESSION_SECONDS)])

        def _body(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if length < 0 or length > MAX_BODY_BYTES:
                return None
            raw = self.rfile.read(length)
            if not raw:
                return {}
            try:
                obj = json.loads(raw)
            except ValueError:
                return None
            return obj if isinstance(obj, dict) else None

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/logout":
                return self._redirect("/login", [self._cookie(SESSION_COOKIE, "", 0)])
            if path not in ("/api/join", "/api/leave", "/api/remove", "/api/sync"):
                return self._send(404, b"not found")
            me = self._me()
            # The custom header cannot be sent by a plain cross-site form.
            if not me or self.headers.get("X-Onefix") != "1":
                return self._json(401, {"error": "sign in"})
            body = self._body()
            if body is None:
                return self._json(400, {"error": "bad request"})
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if path == "/api/join":
                self._json(*app.join(me, body, now))
            elif path == "/api/leave":
                self._json(200, {"ok": app.remove(me)})
            elif path == "/api/remove":
                if me != app.s.owner:
                    self._json(403, {"error": "owner only"})
                else:
                    self._json(200, {"ok": app.remove(str(body.get("steamid") or ""))})
            elif app.member_name(me) is None and me != app.s.owner:
                self._json(403, {"error": "join first"})
            else:
                self._json(202, {"started": app.syncer.start(), "sync": app.syncer.state()})

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


def config_players(env: dict) -> dict:
    """Players set up through environment variables (steamid -> name). Bad entries are the
    ingest step's job to report; here they are skipped."""
    players = {}
    if STEAMID_RE.fullmatch(env.get("ONEFIX_STEAMID", "")):
        players[env["ONEFIX_STEAMID"]] = env.get("ONEFIX_PLAYER_NAME") or "Me"
    try:
        extra = json.loads(env.get("ONEFIX_PLAYERS") or "[]")
    except ValueError:
        extra = []
    for p in extra if isinstance(extra, list) else []:
        if isinstance(p, dict) and STEAMID_RE.fullmatch(str(p.get("steamid", ""))):
            players.setdefault(p["steamid"], str(p.get("name") or "Player"))
    return players


def main() -> None:
    env = os.environ
    port = int(env.get("PORT", "8000"))
    host = env.get("ONEFIX_HOST", "127.0.0.1")
    config_dir = Path(env.get("ONEFIX_CONFIG_DIR") or Path.home() / ".config" / "onefix")
    hour_text = env.get("ONEFIX_SYNC_HOUR_UTC", "6").strip().lower()
    hour = None if hour_text == "off" else int(hour_text)
    if hour is not None and not 0 <= hour <= 23:
        raise SystemExit("ONEFIX_SYNC_HOUR_UTC must be 0-23 or 'off'")
    local_user = env.get("ONEFIX_LOCAL_USER") or None
    if local_user and (host != "127.0.0.1" or not STEAMID_RE.fullmatch(local_user)):
        raise SystemExit("ONEFIX_LOCAL_USER needs a steamid64 and only works when listening on 127.0.0.1")
    base_url = env.get("ONEFIX_BASE_URL") or (
        f"https://{env['RAILWAY_PUBLIC_DOMAIN']}" if env.get("RAILWAY_PUBLIC_DOMAIN") else f"http://127.0.0.1:{port}")

    settings = Settings(
        web_dir=Path(env.get("ONEFIX_WEB_DIR", "parsed/web")),
        base_url=base_url.rstrip("/"),
        secret=load_secret(config_dir),
        invite=env.get("ONEFIX_INVITE_CODE") or env.get("ONEFIX_WEB_PASSWORD") or None,
        owner=env.get("ONEFIX_STEAMID") or None,
        config_players=config_players(env),
        api_key=env.get("STEAM_WEB_API_KEY") or None,
        max_users=int(env.get("ONEFIX_MAX_USERS", "10")),
        local_user=local_user,
    )
    syncer = Syncer(None if hour is None else ["sh", "scripts/sync.sh"])
    accounts = Accounts(config_dir / "onefix.db")
    # The owner used to be set up only through environment variables. Copy those codes into the
    # database once; after that the owner is an ordinary member who also has the owner's view.
    if settings.owner:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if accounts.import_owner(settings.owner, env.get("ONEFIX_PLAYER_NAME") or "Me",
                                 env.get("STEAM_MATCH_AUTH_CODE", ""), env.get("ONEFIX_FIRST_SHARE_CODE", ""), now):
            print("Owner's codes copied into the user database.", flush=True)
        if accounts.flag(OWNER_IMPORTED):
            settings.config_players.pop(settings.owner, None)
    app = App(settings, accounts, syncer)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    if hour is not None:
        threading.Thread(target=schedule, args=(app, hour), daemon=True).start()
    notes = [] if settings.invite else ["no invite code set: nobody new can join"]
    if local_user:
        notes.append("local preview: signed in as ONEFIX_LOCAL_USER")
    print(f"Serving on http://{host}:{port} as {settings.base_url}" + (f" ({'; '.join(notes)})" if notes else ""), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
