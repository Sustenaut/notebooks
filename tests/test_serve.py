"""The site behind oauth2-proxy: the access gate on each request and websocket, the front page, the notebooks."""

import asyncio

import pytest

from notebooks_lib import serve
from notebooks_lib.access_check import DEGRADED, NO_ROLE, OK, SIGN_IN, UNAVAILABLE, Decision


class Check:
    """An access check that answers from a table of people, and records what it was asked."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def check(self, person, token, write=False):
        self.asked.append((person, token, write))
        return self.answers.get(person, Decision(False, NO_ROLE))


def call(app, scope_type="http", path="/", headers=(), query=b""):
    """Run one request (or websocket connect) through `app`; the messages it sent back."""
    scope = {"type": scope_type, "path": path, "query_string": query, "headers": list(headers)}
    sent = []

    async def receive():
        return {"type": "websocket.connect"} if scope_type == "websocket" else {"type": "http.request"}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


async def downstream(scope, receive, send):
    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
    else:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"notebook"})


def who(email, token="t"):
    return [(b"x-forwarded-email", email.encode()), (b"x-forwarded-access-token", token.encode())]


GATE_ANSWERS = {
    "member@sustenaut.eu": Decision(True, OK, frozenset({"notebooks"})),
    "reading@sustenaut.eu": Decision(True, DEGRADED, frozenset({"notebooks"})),
    "gone@sustenaut.eu": Decision(False, SIGN_IN),
    "later@sustenaut.eu": Decision(False, UNAVAILABLE),
}


def test_someone_with_the_role_gets_through_and_every_request_is_a_read():
    check = Check(GATE_ANSWERS)
    gate = serve.AccessGate(downstream, check)
    assert call(gate, path="/site_costs", headers=who("member@sustenaut.eu", "tok"))[1]["body"] == b"notebook"
    assert call(gate, "websocket", "/site_costs/ws", who("member@sustenaut.eu"))[0]["type"] == "websocket.accept"
    assert call(gate, path="/x", headers=who("reading@sustenaut.eu"))[0]["status"] == 200
    assert check.asked[0] == ("member@sustenaut.eu", "tok", False)
    assert all(write is False for _, _, write in check.asked)


def test_without_the_role_the_site_refuses():
    gate = serve.AccessGate(downstream, Check(GATE_ANSWERS))
    start, body = call(gate, path="/site_costs", headers=who("stranger@sustenaut.eu"))
    assert start["status"] == 403 and b"team access page" in body["body"]
    assert call(gate, "websocket", "/ws", who("stranger@sustenaut.eu")) == [{"type": "websocket.close", "code": 4403}]


def test_an_ended_session_or_no_email_is_sent_to_sign_in_keeping_where_it_was():
    gate = serve.AccessGate(downstream, Check(GATE_ANSWERS))
    start = call(gate, path="/site_costs/", headers=who("gone@sustenaut.eu"), query=b"a=1")[0]
    assert start["status"] == 302
    assert dict(start["headers"])[b"location"] == b"/oauth2/sign_in?rd=%2Fsite_costs%2F%3Fa%3D1"
    assert dict(call(gate, path="/")[0]["headers"])[b"location"] == b"/oauth2/sign_in?rd=%2F"
    assert call(gate, "websocket", "/ws") == [{"type": "websocket.close", "code": 4401}]


def test_when_auth_cannot_vouch_the_site_says_try_later():
    gate = serve.AccessGate(downstream, Check(GATE_ANSWERS))
    assert call(gate, path="/x", headers=who("later@sustenaut.eu"))[0]["status"] == 503
    assert call(gate, "websocket", "/ws", who("later@sustenaut.eu")) == [{"type": "websocket.close", "code": 4503}]


def test_health_is_open_and_lifespan_passes_through():
    check = Check({})
    gate = serve.AccessGate(downstream, check)
    start, body = call(gate, path="/healthz")
    assert (start["status"], body["body"]) == (200, b"ok") and check.asked == []
    seen = []

    async def lifespan_app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(serve.AccessGate(lifespan_app, check)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_each_notebook_has_its_address_and_the_front_page_links_them(tmp_path):
    (tmp_path / "site_costs.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "data.json").write_text("{}")
    paths = serve.notebook_paths(tmp_path)
    assert list(paths) == ["/b", "/site_costs"]
    start, body = call(serve.index(paths))
    assert dict(start["headers"])[b"content-type"].startswith(b"text/html")
    assert b'<a href="/site_costs">Site costs</a>' in body["body"]


def test_the_built_site_serves_the_front_page_and_the_notebooks_behind_the_gate():
    site = serve.build(Check({"member@sustenaut.eu": Decision(True, OK, frozenset({"notebooks"}))}))
    assert b"/site_costs" in call(site, path="/", headers=who("member@sustenaut.eu"))[1]["body"]
    assert call(site, path="/", headers=who("stranger@sustenaut.eu"))[0]["status"] == 403
    assert call(site, path="/site_costs", headers=who("stranger@sustenaut.eu"))[0]["status"] == 403


def test_the_site_needs_its_sign_in_client(monkeypatch):
    monkeypatch.delenv("NOTEBOOKS_CLIENT_ID", raising=False)
    monkeypatch.delenv("NOTEBOOKS_CLIENT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="make apps"):
        serve.from_environment()
    with pytest.raises(RuntimeError):
        _ = serve.app
    with pytest.raises(AttributeError):
        _ = serve.not_a_name
    monkeypatch.setenv("NOTEBOOKS_CLIENT_ID", "id")
    monkeypatch.setenv("NOTEBOOKS_CLIENT_SECRET", "secret")
    gate = serve.app
    assert isinstance(gate, serve.AccessGate)
    assert (gate.check.client_id, gate.check.role, gate.check.realm_url) == ("id", "notebooks", serve.REALM)
