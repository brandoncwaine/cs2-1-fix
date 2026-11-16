import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

import pytest

import onefix.web as web
from onefix.web import App, Syncer, is_stale, make_handler, next_run, session_token

PASSWORD = "correct horse"
DATA = {"synced_at": "2026-11-16T06:00:00Z", "players": [{"steamid": "1", "name": "Ann", "cards": []}]}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _call(base, path, data=None, headers=None):
    req = urllib.request.Request(base + path, data=data, headers=headers or {})
    try:
        res = urllib.request.build_opener(_NoRedirect).open(req, timeout=5)
    except urllib.error.HTTPError as err:
        res = err
    return res.status, dict(res.headers), res.read().decode()


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "WRONG_PASSWORD_DELAY", 0)
    (tmp_path / "data.json").write_text(json.dumps(DATA))

    def start(password=PASSWORD, syncer=None):
        app = App(tmp_path, password, syncer or Syncer(None))
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}"

    servers = []
    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def test_nothing_private_is_served_without_signing_in(site):
    base = site()
    status, headers, _ = _call(base, "/")
    assert (status, headers["Location"]) == (303, "/login")
    status, _, body = _call(base, "/api/data")
    assert status == 401 and "Ann" not in body
    assert _call(base, "/api/sync", data=b"", headers={"X-Onefix": "1"})[0] == 401
    assert _call(base, "/healthz")[0] == 200
    assert _call(base, "/login")[0] == 200


def test_wrong_password_gives_no_cookie(site):
    status, headers, _ = _call(site(), "/login", data=b"password=nope")
    assert (status, headers["Location"]) == (303, "/login?wrong=1")
    assert "Set-Cookie" not in headers


def test_right_password_signs_in_and_shows_the_data(site):
    base = site()
    status, headers, _ = _call(base, "/login", data=b"password=correct+horse")
    assert (status, headers["Location"]) == (303, "/")
    cookie = headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and PASSWORD not in cookie
    session = {"Cookie": cookie.split(";")[0]}
    status, _, body = _call(base, "/api/data", headers=session)
    assert status == 200 and json.loads(body)["data"] == DATA
    assert _call(base, "/", headers=session)[0] == 200


def test_a_forged_or_old_cookie_is_refused(site):
    base = site()
    for value in ("", "x", session_token("an old password")):
        assert _call(base, "/api/data", headers={"Cookie": f"onefix_session={value}"})[0] == 401


def test_sync_needs_the_session_and_the_custom_header(site):
    class Recorder(Syncer):
        started = 0

        def start(self):
            self.started += 1
            return True

    syncer = Recorder(["true"])
    base = site(syncer=syncer)
    session = {"Cookie": f"onefix_session={session_token(PASSWORD)}"}
    assert _call(base, "/api/sync", data=b"", headers=session)[0] == 401
    assert syncer.started == 0
    assert _call(base, "/api/sync", data=b"", headers={**session, "X-Onefix": "1"})[0] == 202
    assert syncer.started == 1


def test_missing_data_file_is_reported_as_no_data(site, tmp_path):
    (tmp_path / "data.json").unlink()
    _, _, body = _call(site(password=None), "/api/data")
    assert json.loads(body)["data"] is None


def test_syncer_runs_one_at_a_time_and_records_the_result():
    assert Syncer(None).start() is False
    s = Syncer(["sh", "-c", "exit 3"])
    assert s.start() is True
    for _ in range(200):
        if not s.running:
            break
        threading.Event().wait(0.02)
    assert s.state() == {"enabled": True, "running": False, "last_ok": False}
    s.running = True
    assert s.start() is False


def test_schedule_times():
    at = lambda h, m=0: datetime(2026, 11, 16, h, m, tzinfo=timezone.utc)
    assert next_run(at(5, 59), 6) == at(6)
    assert next_run(at(6), 6) == datetime(2026, 11, 17, 6, tzinfo=timezone.utc)
    assert is_stale(None, at(6)) and is_stale("garbage", at(6))
    assert not is_stale("2026-11-16T00:00:00Z", at(6))
    assert is_stale("2026-11-15T05:00:00Z", at(6))
