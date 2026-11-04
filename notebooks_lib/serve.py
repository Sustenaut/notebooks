"""The notebooks as a site: each notebook in notebooks/ as an app at /<name> (code hidden), behind the team access
check.

On the cluster the site sits behind oauth2-proxy, which signs people in with the team realm at
auth.sustenaut.eu and passes the verified email in X-Forwarded-Email and the access token in
X-Forwarded-Access-Token, replacing whatever the browser sent. The site trusts those two, so nothing but the
proxy may reach it (k8s/admin/network-policy.yaml). On every request, and on every websocket a notebook opens,
it asks access_check whether the person still has the role `notebooks` (the team access page at
auth.sustenaut.eu/realms/team/access gives it): a role taken away or a removal is refused at the next request.
Nothing runs between requests. The notebooks change nothing outside the session, so every request is a read:
if auth.sustenaut.eu can't be reached, people who were let in go on reading.

    uvicorn notebooks_lib.serve:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*'

Locally there is no proxy: `make apps` runs `marimo run` instead, and this module refuses to start without the
sign-in client's id and secret.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, MutableMapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .access_check import NO_ROLE, SIGN_IN, AccessCheck

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

REALM = "https://auth.sustenaut.eu/realms/team"
ROLE = "notebooks"
EMAIL_HEADER = b"x-forwarded-email"
TOKEN_HEADER = b"x-forwarded-access-token"
HEALTH = "/healthz"
NOTEBOOKS = Path(__file__).resolve().parent.parent / "notebooks"


class AccessGate:
    """ASGI middleware: lets a request (or a websocket) through only for someone the access check lets in."""

    def __init__(self, app: ASGIApp, check: AccessCheck):
        self.app = app
        self.check = check

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http" and scope["path"] == HEALTH:
            await _respond(send, 200, b"ok")
            return
        headers = dict(scope.get("headers", []))
        email = headers.get(EMAIL_HEADER, b"").decode().strip()
        token = headers.get(TOKEN_HEADER, b"").decode().strip() or None
        if not email:
            decision_reason = SIGN_IN
        else:
            decision = self.check.check(email, token, write=False)
            if decision.allowed:
                await self.app(scope, receive, send)
                return
            decision_reason = decision.reason
        await _refuse(scope, receive, send, decision_reason)


async def _respond(
    send: Send, status: int, body: bytes, headers: list[tuple[bytes, bytes]] | None = None, html: bool = False
) -> None:
    kind = b"text/html; charset=utf-8" if html else b"text/plain; charset=utf-8"
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", kind), (b"cache-control", b"no-store"), *(headers or [])],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _refuse(scope: Scope, receive: Receive, send: Send, reason: str) -> None:
    if scope["type"] == "websocket":
        await receive()  # the websocket.connect message
        # 4401 and 4403 mirror HTTP's 401 and 403; 4503 is "try again later".
        code = {SIGN_IN: 4401, NO_ROLE: 4403}.get(reason, 4503)
        await send({"type": "websocket.close", "code": code})
        return
    if reason == SIGN_IN:
        target = scope["path"] + (f"?{scope['query_string'].decode()}" if scope.get("query_string") else "")
        await _respond(send, 302, b"", [(b"location", f"/oauth2/sign_in?rd={quote(target, safe='')}".encode())])
    elif reason == NO_ROLE:
        await _respond(send, 403, b"Your account doesn't have access to the notebooks. Ask a controller on the team access page.")
    else:
        await _respond(send, 503, b"auth.sustenaut.eu can't be reached, so your access can't be checked. Try again shortly.")


def notebook_paths(notebooks: Path = NOTEBOOKS) -> dict[str, Path]:
    """Each notebook's address: notebooks/site_costs.py is /site_costs."""
    return {f"/{p.stem}": p for p in sorted(notebooks.glob("*.py"))}


def index(paths: dict[str, Path]) -> ASGIApp:
    """The site's front page: a link to each notebook."""
    links = "".join(f'<li><a href="{path}">{path[1:].replace("_", " ").capitalize()}</a></li>' for path in paths)
    body = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f"<title>Sustenaut notebooks</title><h1>Notebooks</h1><ul>{links}</ul></html>"
    ).encode()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await _respond(send, 200, body, html=True)

    return app


def build(check: AccessCheck, notebooks: Path = NOTEBOOKS) -> ASGIApp:
    """Every notebook in `notebooks` as a marimo app at /<name>, a page of links at /, behind the access gate."""
    import marimo

    paths = notebook_paths(notebooks)
    builder = marimo.create_asgi_app(quiet=True, include_code=False)
    for path, notebook in paths.items():
        builder = builder.with_app(path=path, root=str(notebook))
    marimo_app = builder.build()
    front = index(paths)

    async def site(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/":
            await front(scope, receive, send)
        else:
            await marimo_app(scope, receive, send)

    return AccessGate(site, check)


def from_environment() -> ASGIApp:
    client_id = os.environ.get("NOTEBOOKS_CLIENT_ID")
    client_secret = os.environ.get("NOTEBOOKS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "NOTEBOOKS_CLIENT_ID and NOTEBOOKS_CLIENT_SECRET are not set: the site only runs behind oauth2-proxy "
            "with the sign-in client (register-client.sh). Locally, use `make apps`."
        )
    return build(AccessCheck(os.environ.get("NOTEBOOKS_REALM", REALM), client_id, client_secret, role=ROLE))


def __getattr__(name: str) -> ASGIApp:
    # `uvicorn notebooks_lib.serve:app` builds the app on first use, so importing this module needs no secrets.
    if name == "app":
        return from_environment()
    raise AttributeError(name)
