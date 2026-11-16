"""Sign in through Steam (OpenID 2.0). Steam tells us which account signed in; we never see a
password. https://partner.steamgames.com/doc/features/auth#website

`login_url` sends the browser to Steam. Steam sends it back with signed `openid.*` values, and
`verify` asks Steam directly whether that signature is real before trusting the steamid64.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

STEAM_OPENID = "https://steamcommunity.com/openid/login"
CLAIMED_ID_RE = re.compile(r"https://steamcommunity\.com/openid/id/(7656\d{13})")
RETURN_PATH = "/auth/steam/return"
MAX_AGE = timedelta(minutes=5)
_NS = "http://specs.openid.net/auth/2.0"
_SELECT = f"{_NS}/identifier_select"


def login_url(base_url: str, state: str) -> str:
    return STEAM_OPENID + "?" + urllib.parse.urlencode({
        "openid.ns": _NS,
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{base_url}{RETURN_PATH}?state={state}",
        "openid.realm": base_url,
        "openid.identity": _SELECT,
        "openid.claimed_id": _SELECT,
    })


def _ask_steam(params: dict) -> str:
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(STEAM_OPENID, data=data), timeout=15) as res:
        return res.read().decode("utf-8", "replace")


def verify(params: dict, base_url: str, state: str, now: datetime, ask=_ask_steam) -> str | None:
    """The steamid64 that signed in, or None if anything about the response is off.

    `params` are the query values Steam's redirect arrived with; `state` is the value we put in
    the return address when we sent this browser to Steam."""
    if params.get("openid.mode") != "id_res" or params.get("openid.op_endpoint") != STEAM_OPENID:
        return None
    if not state or params.get("openid.return_to") != f"{base_url}{RETURN_PATH}?state={state}":
        return None
    match = CLAIMED_ID_RE.fullmatch(params.get("openid.claimed_id", ""))
    if not match or params.get("openid.identity") != params.get("openid.claimed_id"):
        return None
    # Steam must have signed the fields we rely on.
    signed = set(params.get("openid.signed", "").split(","))
    if not {"claimed_id", "identity", "return_to", "response_nonce", "op_endpoint"} <= signed:
        return None
    # The nonce starts with the time Steam answered: refuse old (possibly replayed) answers.
    try:
        answered = datetime.strptime(params.get("openid.response_nonce", "")[:20], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    if abs(now - answered.replace(tzinfo=timezone.utc)) > MAX_AGE:
        return None
    check = {k: v for k, v in params.items() if k.startswith("openid.")}
    check["openid.mode"] = "check_authentication"
    try:
        answer = ask(check)
    except Exception:
        return None
    if "is_valid:true" not in answer.split("\n"):
        return None
    return match.group(1)
