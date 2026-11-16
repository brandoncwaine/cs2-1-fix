from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from onefix.steam_openid import STEAM_OPENID, login_url, verify

BASE = "https://site.example"
NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
STEAMID = "76561190000000001"


def answer(**changes):
    claimed = f"https://steamcommunity.com/openid/id/{STEAMID}"
    params = {
        "state": "abc",
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "id_res",
        "openid.op_endpoint": STEAM_OPENID,
        "openid.claimed_id": claimed,
        "openid.identity": claimed,
        "openid.return_to": f"{BASE}/auth/steam/return?state=abc",
        "openid.response_nonce": "2026-11-16T11:59:30Zrandom",
        "openid.assoc_handle": "1234",
        "openid.signed": "signed,op_endpoint,claimed_id,identity,return_to,response_nonce,assoc_handle",
        "openid.sig": "c2ln",
    }
    params.update(changes)
    return params


def valid(sent):
    return "ns:http://specs.openid.net/auth/2.0\nis_valid:true\n"


def test_login_url_sends_the_browser_to_steam_and_back_to_us():
    url = urlparse(login_url(BASE, "abc"))
    q = parse_qs(url.query)
    assert f"{url.scheme}://{url.netloc}{url.path}" == STEAM_OPENID
    assert q["openid.return_to"] == [f"{BASE}/auth/steam/return?state=abc"]
    assert q["openid.realm"] == [BASE] and q["openid.mode"] == ["checkid_setup"]


def test_a_real_answer_gives_the_steamid_and_is_checked_with_steam():
    asked = []

    def ask(sent):
        asked.append(sent)
        return valid(sent)

    assert verify(answer(), BASE, "abc", NOW, ask) == STEAMID
    assert asked[0]["openid.mode"] == "check_authentication"
    assert asked[0]["openid.sig"] == "c2ln" and "state" not in asked[0]


def test_steam_saying_the_signature_is_bad_means_no_sign_in():
    assert verify(answer(), BASE, "abc", NOW, lambda s: "ns:x\nis_valid:false\n") is None
    assert verify(answer(), BASE, "abc", NOW, lambda s: "not_is_valid:true") is None

    def down(sent):
        raise OSError("no network")

    assert verify(answer(), BASE, "abc", NOW, down) is None


def test_tampered_or_stale_answers_are_refused_without_asking_steam():
    def never(sent):
        raise AssertionError("should not reach Steam")

    other = "https://steamcommunity.com/openid/id/76561190000000002"
    bad = [
        answer(**{"openid.mode": "cancel"}),
        answer(**{"openid.op_endpoint": "https://evil.example/openid"}),
        answer(**{"openid.return_to": "https://evil.example/auth/steam/return?state=abc"}),
        answer(**{"openid.claimed_id": "https://evil.example/openid/id/" + STEAMID}),
        answer(**{"openid.claimed_id": f"https://steamcommunity.com/openid/id/{STEAMID}/x"}),
        answer(**{"openid.identity": other}),
        answer(**{"openid.signed": "signed,op_endpoint,identity,return_to,response_nonce"}),
        answer(**{"openid.response_nonce": "2026-11-16T11:00:00Zold"}),
        answer(**{"openid.response_nonce": "garbage"}),
    ]
    for params in bad:
        assert verify(params, BASE, "abc", NOW, never) is None
    assert verify(answer(), BASE, "a different state", NOW, never) is None
    assert verify(answer(), BASE, "", NOW, never) is None
