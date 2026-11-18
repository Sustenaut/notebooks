"""The site behind oauth2-proxy: the access gate on each request and websocket, the front page, the notebooks."""

import json

import pytest
from pubtest.http import asgi
from pytest_bdd import given, parsers, scenarios, then, when

from notebooks_lib import serve
from notebooks_lib.access_check import DEGRADED, NO_ROLE, OK, Decision

scenarios("serve.feature")


class Check:
    """An access check that answers from a table of people, and records what it was asked."""

    def __init__(self):
        self.answers = {}
        self.asked = []

    def check(self, person, token, write=False):
        self.asked.append((person, token, write))
        return self.answers.get(person, Decision(False, NO_ROLE))


@pytest.fixture
def check():
    return Check()


@pytest.fixture
def http_client(ctx):
    return lambda method, path, headers, body: asgi(ctx.app)(method, path, headers, body)


def notebooks(reached):
    """What stands behind the gate: notebooks that answer "notebook", and record each scope that reaches them."""

    async def app(scope, receive, send):
        reached.append(scope["type"])
        if scope["type"] == "websocket":
            await send({"type": "websocket.accept"})
        elif scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"notebook"})

    return app


@given(parsers.parse('the access check answers "{reason}" for "{email}"'))
def check_answers(check, reason, email):
    allowed = reason in (OK, DEGRADED)
    check.answers[email] = Decision(allowed, reason, frozenset({"notebooks"}) if allowed else frozenset())


@given("the notebooks behind the gate")
def behind_the_gate(ctx, check):
    ctx.reached = []
    ctx.app = serve.AccessGate(notebooks(ctx.reached), check)


@given("the site built from the repository's notebooks")
def built_site(ctx, check):
    ctx.app = serve.build(check)


@given("the front page of the notebooks in the scratch directory")
def front_page(ctx):
    ctx.app = serve.index(serve.notebook_paths(ctx.directory))


@when(parsers.parse('a websocket opens "{path}"'))
def websocket(ctx, path):
    headers = [(k.lower().encode(), v.encode()) for k, v in getattr(ctx, "headers", {}).items()]
    scope = {"type": "websocket", "path": path, "query_string": b"", "headers": headers}
    sent = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    async def connect():
        await ctx.app(scope, receive, send)
        return sent

    ctx.attempt(connect)


@when("the server starts the site")
def lifespan(ctx):
    async def start():
        await ctx.app({"type": "lifespan"}, None, None)
        return ctx.reached

    ctx.attempt(start)


@when("the notebooks in the scratch directory are given their addresses")
def addresses(ctx):
    ctx.attempt(lambda: list(serve.notebook_paths(ctx.directory)))


@when("the site is made from the environment")
def from_environment(ctx):
    ctx.attempt(serve.from_environment)


@when(parsers.parse('the site module is asked for "{name}"'))
def module_attribute(ctx, name):
    ctx.attempt(lambda: getattr(serve, name))


@then("the access check was asked:")
def asked(check, datatable):
    header, *rows = datatable
    wanted = [(row[0], row[1], json.loads(row[2])) for row in rows]
    assert header == ["person", "token", "write"], header
    assert check.asked == wanted, check.asked
