"""Invited users: who they are and the two Steam codes needed to fetch their matches.

Kept in a SQLite file in the private config folder (it holds match auth codes). The web server
adds and removes users; `scripts/sync.sh` reads them through this module's command line:

  python -m onefix.accounts export --db FILE            users as JSON for the ingest step
  python -m onefix.accounts purge --db FILE --state FILE --parsed DIR
                                                        finish deleting removed users' data

No Steam password is ever asked for or stored: users sign in on Steam's own site.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

STEAMID_RE = re.compile(r"7656\d{13}")
AUTH_CODE_RE = re.compile(r"[0-9A-Z]{4}-[0-9A-Z]{5}-[0-9A-Z]{4}")
SHARE_CODE_RE = re.compile(r"CSGO(-[A-Za-z0-9]{5}){5}")
NAME_MAX = 40
SHARECODE_API = "https://api.steampowered.com/ICSGOPlayers_730/GetNextMatchSharingCode/v1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  steamid TEXT PRIMARY KEY, name TEXT NOT NULL, auth_code TEXT NOT NULL,
  share_code TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS removed (steamid TEXT PRIMARY KEY);
"""


def clean_join(form: dict) -> tuple[dict, dict]:
    """Tidy and check what a user typed. Returns (values, {field: problem})."""
    name = " ".join(str(form.get("name") or "").split())
    auth = str(form.get("auth_code") or "").strip().upper()
    share = str(form.get("share_code") or "").strip()
    errors = {}
    if not name or len(name) > NAME_MAX or not name.isprintable():
        errors["name"] = f"Enter a name of 1 to {NAME_MAX} characters."
    if not AUTH_CODE_RE.fullmatch(auth):
        errors["auth_code"] = "This should look like XXXX-XXXXX-XXXX."
    if not SHARE_CODE_RE.fullmatch(share):
        errors["share_code"] = "This should look like CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx."
    return {"name": name, "auth_code": auth, "share_code": share}, errors


def steam_check(key: str, steamid: str, auth_code: str, share_code: str, fetch=urllib.request.urlopen) -> str:
    """Ask Steam whether the codes work for this account.

    Returns "ok", "rejected" (auth code is not this account's), "unknown_code" (share code is
    not this account's) or "unreachable". Never raises and never returns the key or codes."""
    query = urllib.parse.urlencode(
        {"key": key, "steamid": steamid, "steamidkey": auth_code, "knowncode": share_code})
    try:
        with fetch(f"{SHARECODE_API}?{query}", timeout=15) as res:
            status = res.status
    except urllib.error.HTTPError as err:
        status = err.code
    except Exception:
        return "unreachable"
    if status in (200, 202):
        return "ok"
    if status == 403:
        return "rejected"
    if status == 412:
        return "unknown_code"
    return "unreachable"


class Accounts:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._db() as db:
            db.executescript(SCHEMA)
        os.chmod(self.path, 0o600)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)  # one connection per call: safe across threads
        db.row_factory = sqlite3.Row
        return db

    def get(self, steamid: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE steamid = ?", (steamid,)).fetchone()
        return dict(row) if row else None

    def all(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM users ORDER BY created_at, steamid")]

    def count(self) -> int:
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def save(self, steamid: str, name: str, auth_code: str, share_code: str, now: str) -> None:
        """Add a user, or replace an existing user's name and codes."""
        with self._db() as db:
            db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?) ON CONFLICT(steamid) DO UPDATE SET "
                "name = excluded.name, auth_code = excluded.auth_code, share_code = excluded.share_code",
                (steamid, name, auth_code, share_code, now))
            db.execute("DELETE FROM removed WHERE steamid = ?", (steamid,))

    def remove(self, steamid: str) -> bool:
        """Forget a user now; their match data is deleted by `purge` before the next sync."""
        with self._db() as db:
            gone = db.execute("DELETE FROM users WHERE steamid = ?", (steamid,)).rowcount > 0
            if gone:
                db.execute("INSERT OR IGNORE INTO removed VALUES (?)", (steamid,))
        return gone

    def removed(self) -> list[str]:
        with self._db() as db:
            return [r[0] for r in db.execute("SELECT steamid FROM removed ORDER BY steamid")]

    def forget_removed(self, steamid: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM removed WHERE steamid = ?", (steamid,))


def export(accounts: Accounts) -> list[dict]:
    """Users in the shape the ingest config uses."""
    return [{"name": u["name"], "steamid": u["steamid"], "matchAuthCode": u["auth_code"],
             "firstShareCode": u["share_code"]} for u in accounts.all()]


def purge(accounts: Accounts, state_file: Path, parsed_dir: Path) -> list[str]:
    """Delete removed users' parsed matches and fetch history. Run only while no sync is running.
    Demo files stay: other players in the same match may still need them."""
    gone = accounts.removed()
    if not gone:
        return []
    state = None
    if state_file.exists():
        state = json.loads(state_file.read_text())
    for steamid in gone:
        if not STEAMID_RE.fullmatch(steamid):  # never build a path from anything else
            continue
        shutil.rmtree(parsed_dir / steamid, ignore_errors=True)
        if state and isinstance(state.get("players"), dict):
            state["players"].pop(steamid, None)
    if state and isinstance(state.get("players"), dict):
        tmp = state_file.with_name(state_file.name + ".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, state_file)
    for steamid in gone:
        accounts.forget_removed(steamid)
    return gone


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["export", "purge"])
    ap.add_argument("--db", required=True)
    ap.add_argument("--state")
    ap.add_argument("--parsed")
    args = ap.parse_args()
    if not Path(args.db).exists():  # nobody has joined yet
        if args.command == "export":
            print("[]")
        return
    accounts = Accounts(Path(args.db))
    if args.command == "export":
        print(json.dumps(export(accounts)))
    else:
        if not args.state or not args.parsed:
            ap.error("purge needs --state and --parsed")
        gone = purge(accounts, Path(args.state), Path(args.parsed))
        if gone:
            print(f"Deleted data for {len(gone)} removed user(s).")


if __name__ == "__main__":
    main()
