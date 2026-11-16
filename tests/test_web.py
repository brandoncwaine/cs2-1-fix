import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

import onefix.web as web
from onefix.accounts import Accounts
from onefix.web import App, Settings, Syncer, is_stale, make_handler, next_run, read_session, sign_session

SECRET = b"test-secret"
OWNER, ANN, BOB = "76561190000000000", "76561190000000001", "76561190000000002"
AUTH, SHARE = "ABCD-EFGHI-JKLM", "CSGO-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"
JOIN = {"invite": "let-me-in", "name": "Ann", "auth_code": AUTH, "share_code": SHARE}


def _player(steamid, name):
    return {"steamid": steamid, "name": name, "matches": 1, "rounds": 21, "problems": {}, "cards": [
        {"map": "de_nuke", "side": "T", "side_rounds": 9, "status": "insufficient_data",
         "reason": "9 rounds played; need 30.", "rounds_needed": 21}]}


DATA = {"synced_at": "2026-11-16T06:00:00Z",
        "players": [_player(OWNER, "Owner"), _player(ANN, "Ann"), _player(BOB, "Bob")]}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def call(base, path, body=None, who=None, header=True, cookie=None):
    headers = {}
    if who:
        cookie = f"onefix_session={sign_session(SECRET, who, int(time.time()) + 600)}"
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        if header:
            headers["X-Onefix"] = "1"
    req = urllib.request.Request(base + path, data=data, headers=headers)
    try:
        res = urllib.request.build_opener(_NoRedirect).open(req, timeout=5)
    except urllib.error.HTTPError as err:
        res = err
    text = res.read().decode()
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = text
    return res.status, res.headers, parsed


class FakeSyncer(Syncer):
    def __init__(self):
        super().__init__(["true"])
        self.started = 0

    def start(self):
        self.started += 1
        return True


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "WRONG_INVITE_DELAY", 0)
    (tmp_path / "data.json").write_text(json.dumps(DATA))
    servers = []

    def start(check=lambda *a: "ok", ask_steam=None, **overrides):
        settings = Settings(web_dir=tmp_path, base_url="http://site.test", secret=SECRET, invite="let-me-in",
                            owner=OWNER, config_players={OWNER: "Owner"}, api_key="KEY", max_users=2)
        for k, v in overrides.items():
            setattr(settings, k, v)
        app = App(settings, Accounts(tmp_path / "cfg" / "onefix.db"), FakeSyncer(), check=check, ask_steam=ask_steam)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}", app

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def test_nothing_private_without_signing_in(site):
    base, app = site()
    status, headers, _ = call(base, "/")
    assert (status, headers["Location"]) == (303, "/login")
    status, _, body = call(base, "/api/data")
    assert status == 401 and "Owner" not in json.dumps(body)
    for path in ("/api/join", "/api/leave", "/api/remove", "/api/sync"):
        assert call(base, path, body={})[0] == 401
    assert call(base, "/healthz")[0] == 200 and call(base, "/login")[0] == 200
    assert app.syncer.started == 0


def test_forged_expired_and_malformed_sessions_are_refused(site):
    base, _ = site()
    now = int(time.time())
    bad = [
        "x", f"{ANN}.{now + 600}.{'0' * 64}",
        sign_session(b"another secret", ANN, now + 600),
        sign_session(SECRET, ANN, now - 1),
        sign_session(SECRET, "not-a-steamid", now + 600),
    ]
    for value in bad:
        assert call(base, "/api/data", cookie=f"onefix_session={value}")[0] == 401
    assert read_session(SECRET, sign_session(SECRET, ANN, now + 600), now) == ANN


def test_steam_sign_in_round_trip_sets_a_session(site):
    base, _ = site(ask_steam=lambda sent: "is_valid:true\n")
    status, headers, _ = call(base, "/auth/steam")
    assert status == 303 and headers["Location"].startswith("https://steamcommunity.com/openid/login?")
    return_to = parse_qs(urlparse(headers["Location"]).query)["openid.return_to"][0]
    state = parse_qs(urlparse(return_to).query)["state"][0]
    state_cookie = headers["Set-Cookie"].split(";")[0]
    assert state_cookie == f"onefix_state={state}"

    claimed = f"https://steamcommunity.com/openid/id/{ANN}"
    nonce = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + "abc"
    params = {"state": state, "openid.mode": "id_res", "openid.op_endpoint": "https://steamcommunity.com/openid/login",
              "openid.claimed_id": claimed, "openid.identity": claimed, "openid.return_to": return_to,
              "openid.response_nonce": nonce, "openid.sig": "x",
              "openid.signed": "signed,op_endpoint,claimed_id,identity,return_to,response_nonce"}
    back = "/auth/steam/return?" + urllib.parse.urlencode(params)

    # Without the state cookie (a link someone else made), no session.
    status, headers, _ = call(base, back)
    assert headers["Location"] == "/login?failed=1"
    assert "onefix_session=" not in "".join(headers.get_all("Set-Cookie"))

    status, headers, _ = call(base, back, cookie=state_cookie)
    assert (status, headers["Location"]) == (303, "/")
    session = [c for c in headers.get_all("Set-Cookie") if c.startswith("onefix_session=")][0]
    assert "HttpOnly" in session and "SameSite=Lax" in session
    status, _, body = call(base, "/api/data", cookie=session.split(";")[0])
    assert status == 200 and body["me"] == {"steamid": ANN, "name": None, "joined": False, "owner": False, "invited": True}


def test_someone_who_has_not_joined_sees_no_cards(site):
    base, _ = site()
    _, _, body = call(base, f"/api/data?player={OWNER}", who=ANN)
    assert body["player"] is None and "players" not in body and body["joining_open"] is True
    assert call(base, "/api/sync", body={}, who=ANN)[0] == 403


def test_joining_needs_the_invite_code_and_good_codes(site):
    base, app = site()
    status, _, body = call(base, "/api/join", body={**JOIN, "invite": "guess"}, who=ANN)
    assert status == 403 and "invite" in body["fields"]
    status, _, body = call(base, "/api/join", body={**JOIN, "auth_code": "bad"}, who=ANN)
    assert status == 400 and "auth_code" in body["fields"]
    assert call(base, "/api/join", body=JOIN, who=ANN, header=False)[0] == 401
    assert app.accounts.count() == 0 and app.syncer.started == 0

    status, _, body = call(base, "/api/join", body=JOIN, who=ANN)
    assert (status, body["ok"]) == (200, True)
    assert app.accounts.get(ANN)["auth_code"] == AUTH and app.syncer.started == 1
    _, _, body = call(base, "/api/data", who=ANN)
    assert body["me"]["joined"] and body["player"]["steamid"] == ANN


def test_steam_rejecting_the_codes_stops_the_join(site):
    answers = iter(["rejected", "unknown_code", "unreachable"])
    base, app = site(check=lambda key, steamid, auth, share: next(answers))
    status, _, body = call(base, "/api/join", body=JOIN, who=ANN)
    assert status == 400 and "auth_code" in body["fields"]
    status, _, body = call(base, "/api/join", body=JOIN, who=ANN)
    assert status == 400 and "share_code" in body["fields"]
    assert app.accounts.count() == 0
    status, _, body = call(base, "/api/join", body=JOIN, who=ANN)
    assert status == 200 and body["warning"] and app.accounts.count() == 1


def test_each_person_sees_only_their_own_cards(site):
    base, app = site()
    app.accounts.save(ANN, "Ann", AUTH, SHARE, "t")
    app.accounts.save(BOB, "Bob", AUTH, SHARE, "t")
    for wanted in (BOB, OWNER):
        _, _, body = call(base, f"/api/data?player={wanted}", who=ANN)
        assert body["viewing"] == ANN and body["player"]["steamid"] == ANN and "players" not in body
        text = json.dumps(body)
        assert BOB not in text and OWNER not in text and AUTH not in text


def test_the_owner_can_see_everyone_and_remove_invited_people(site):
    base, app = site()
    app.accounts.save(ANN, "Ann", AUTH, SHARE, "t")
    _, _, body = call(base, f"/api/data?player={ANN}", who=OWNER)
    assert body["viewing"] == ANN and body["player"]["steamid"] == ANN
    assert body["players"] == [{"steamid": OWNER, "name": "Owner", "invited": False},
                               {"steamid": ANN, "name": "Ann", "invited": True}]
    assert AUTH not in json.dumps(body)

    assert call(base, "/api/remove", body={"steamid": OWNER}, who=ANN)[0] == 403
    assert call(base, "/api/remove", body={"steamid": ANN}, who=OWNER)[2] == {"ok": True}
    assert app.accounts.get(ANN) is None and app.accounts.removed() == [ANN]
    _, _, body = call(base, "/api/data", who=ANN)  # still in data.json until the next sync
    assert body["me"]["joined"] is False and body["player"] is None


def test_leaving_deletes_my_account_and_hides_my_cards_at_once(site):
    base, app = site()
    app.accounts.save(ANN, "Ann", AUTH, SHARE, "t")
    assert call(base, "/api/leave", body={}, who=ANN)[2] == {"ok": True}
    assert app.accounts.get(ANN) is None and app.syncer.started == 1
    assert call(base, "/api/data", who=ANN)[2]["player"] is None


def test_the_site_can_be_full_or_closed(site):
    base, app = site()
    app.accounts.save(ANN, "Ann", AUTH, SHARE, "t")
    app.accounts.save(BOB, "Bob", AUTH, SHARE, "t")
    new = "76561190000000009"
    status, _, body = call(base, "/api/join", body=JOIN, who=new)
    assert status == 403 and "full" in body["error"]
    # Someone already in can still update their codes, with no invite code.
    status, _, _ = call(base, "/api/join", body={**JOIN, "invite": "", "name": "Annie"}, who=ANN)
    assert status == 200 and app.accounts.get(ANN)["name"] == "Annie"
    assert call(base, "/api/join", body=JOIN, who=OWNER)[0] == 400

    closed, _ = site(invite=None)
    assert call(closed, "/api/join", body=JOIN, who=new)[0] == 403
    assert call(closed, "/api/data", who=new)[2]["joining_open"] is False


def test_syncer_runs_one_at_a_time_and_queues_one_more():
    assert Syncer(None).start() is False
    s = Syncer(["sh", "-c", "exit 3"])
    assert s.start() is True
    for _ in range(200):
        if not s.running:
            break
        threading.Event().wait(0.02)
    assert s.state() == {"enabled": True, "running": False, "last_ok": False}
    s.running = True
    assert s.start() is True and s.again is True


def test_schedule_times():
    at = lambda h, m=0: datetime(2026, 11, 16, h, m, tzinfo=timezone.utc)
    assert next_run(at(5, 59), 6) == at(6)
    assert next_run(at(6), 6) == datetime(2026, 11, 17, 6, tzinfo=timezone.utc)
    assert is_stale(None, at(6)) and is_stale("garbage", at(6))
    assert not is_stale("2026-11-16T00:00:00Z", at(6))
    assert is_stale("2026-11-15T05:00:00Z", at(6))


def test_config_players_come_from_the_environment():
    env = {"ONEFIX_STEAMID": OWNER, "ONEFIX_PLAYER_NAME": "Brandon",
           "ONEFIX_PLAYERS": json.dumps([{"name": "Sam", "steamid": ANN}, {"steamid": "bad"}, "junk"])}
    assert web.config_players(env) == {OWNER: "Brandon", ANN: "Sam"}
    assert web.config_players({"ONEFIX_PLAYERS": "not json"}) == {}


def test_an_owner_in_the_database_manages_their_account_like_anyone_else(site):
    base, app = site(config_players={})  # what main() leaves once the owner has been copied in
    app.accounts.save(OWNER, "Brandon", AUTH, SHARE, "t")
    app.accounts.save(ANN, "Ann", AUTH, SHARE, "t")
    app.accounts.save(BOB, "Bob", AUTH, SHARE, "t")  # the site is now over its limit of 2
    _, _, body = call(base, "/api/data", who=OWNER)
    assert body["me"] == {"steamid": OWNER, "name": "Brandon", "joined": True, "owner": True, "invited": True}
    assert [p["name"] for p in body["players"]] == ["Brandon", "Ann", "Bob"]

    assert call(base, "/api/leave", body={}, who=OWNER)[2] == {"ok": True}
    _, _, body = call(base, f"/api/data?player={ANN}", who=OWNER)
    assert body["me"]["joined"] is False and body["me"]["owner"] is True
    assert body["player"]["steamid"] == ANN  # still the owner: can still see members
    # Rejoining needs no invite code and no free place.
    status, _, _ = call(base, "/api/join", body={**JOIN, "invite": "", "name": "Brandon"}, who=OWNER)
    assert status == 200 and app.accounts.get(OWNER)["name"] == "Brandon"
