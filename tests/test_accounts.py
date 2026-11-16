import json
import stat
import urllib.error

from onefix.accounts import Accounts, clean_join, export, purge, steam_check

A, B = "76561190000000001", "76561190000000002"
AUTH, SHARE = "ABCD-EFGHI-JKLM", "CSGO-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


def test_join_form_is_tidied_and_checked():
    values, errors = clean_join({"name": "  Sam   the  Man ", "auth_code": " abcd-efghi-jklm ", "share_code": SHARE + " "})
    assert errors == {}
    assert values == {"name": "Sam the Man", "auth_code": AUTH, "share_code": SHARE}
    _, errors = clean_join({"name": "", "auth_code": "nope", "share_code": "CSGO-short"})
    assert set(errors) == {"name", "auth_code", "share_code"}
    assert "name" in clean_join({"name": "x" * 41, "auth_code": AUTH, "share_code": SHARE})[1]


def test_users_are_saved_updated_and_exported_for_ingest(tmp_path):
    acc = Accounts(tmp_path / "cfg" / "onefix.db")
    assert stat.S_IMODE((tmp_path / "cfg" / "onefix.db").stat().st_mode) == 0o600
    acc.save(A, "Ann", AUTH, SHARE, "2026-11-16T10:00:00Z")
    acc.save(B, "Bob", AUTH, SHARE, "2026-11-16T11:00:00Z")
    acc.save(A, "Annie", "WXYZ-EFGHI-JKLM", SHARE, "2026-11-17T00:00:00Z")
    assert acc.count() == 2 and acc.get(A)["name"] == "Annie" and acc.get("nobody") is None
    assert export(acc) == [
        {"name": "Annie", "steamid": A, "matchAuthCode": "WXYZ-EFGHI-JKLM", "firstShareCode": SHARE},
        {"name": "Bob", "steamid": B, "matchAuthCode": AUTH, "firstShareCode": SHARE},
    ]


def test_removing_a_user_deletes_their_data_at_the_next_purge(tmp_path):
    acc = Accounts(tmp_path / "onefix.db")
    acc.save(A, "Ann", AUTH, SHARE, "t")
    acc.save(B, "Bob", AUTH, SHARE, "t")
    parsed = tmp_path / "parsed"
    for sid in (A, B):
        (parsed / sid).mkdir(parents=True)
        (parsed / sid / "m1.json").write_text("{}")
    state = tmp_path / "ingest-state.json"
    state.write_text(json.dumps({"players": {A: {"lastCode": SHARE, "matches": {}}, B: {"lastCode": SHARE, "matches": {}}}}))

    assert acc.remove(A) is True and acc.remove(A) is False
    assert acc.get(A) is None and acc.removed() == [A]
    assert purge(acc, state, parsed) == [A]
    assert not (parsed / A).exists() and (parsed / B / "m1.json").exists()
    assert list(json.loads(state.read_text())["players"]) == [B]
    assert acc.removed() == [] and purge(acc, state, parsed) == []


def test_rejoining_before_the_purge_keeps_the_new_account(tmp_path):
    acc = Accounts(tmp_path / "onefix.db")
    acc.save(A, "Ann", AUTH, SHARE, "t")
    acc.remove(A)
    acc.save(A, "Ann", AUTH, SHARE, "t2")
    assert acc.removed() == []


class _Res:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_steam_check_maps_steams_answers_and_never_raises():
    seen = []

    def ok(url, timeout):
        seen.append(url)
        return _Res(202)

    assert steam_check("KEY", A, AUTH, SHARE, ok) == "ok"
    assert f"steamid={A}" in seen[0] and "steamidkey=ABCD-EFGHI-JKLM" in seen[0]

    def http(code):
        def fetch(url, timeout):
            raise urllib.error.HTTPError(url, code, "x", None, None)
        return fetch

    assert steam_check("KEY", A, AUTH, SHARE, http(403)) == "rejected"
    assert steam_check("KEY", A, AUTH, SHARE, http(412)) == "unknown_code"
    assert steam_check("KEY", A, AUTH, SHARE, http(500)) == "unreachable"

    def down(url, timeout):
        raise OSError("no network")

    assert steam_check("KEY", A, AUTH, SHARE, down) == "unreachable"
