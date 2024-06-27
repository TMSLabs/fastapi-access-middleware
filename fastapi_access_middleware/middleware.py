from __future__ import annotations

# import typing
import nats
import json

from starlette.datastructures import URL, Headers
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send


def parse_nats_servers(nats_servers: str) -> list[str]:
    return nats_servers.split(",")


class AccessMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        service_name: str,
        nats_servers: list[str],
        nats_subject: str,
    ) -> None:
        self.app = app
        self.nats_subject = nats_subject
        if isinstance(nats_servers, str):
            nats_servers = parse_nats_servers(nats_servers)
        self.nats_servers = nats_servers
        self.service_name = service_name
        self.nats_connection = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        url = URL(scope=scope)

        print("Headers: {headers}".format(headers=headers))
        print("URL: {url}".format(url=url))
        print("Scope: {scope9}".format(scope=scope))

        data = {
            "url": str(url),
            "service_name": self.service_name,
            "headers": dict(headers),
            "method": scope["method"],
            "path": scope["path"],
            "query_string": scope["query_string"],
        }
        json_data = json.dumps(data)
        if self.nats_connection is None or self.nats_connection.is_closed:
            self.nats_connection = await nats.connect(servers=self.nats_servers)

        response = None

        try:
            response = await self.nats_connection.request(
                self.nats_subject, json_data.encode(), timeout=5
            )
            print("Received response: {message}".format(message=response.data.decode()))
        except nats.errors.NoRespondersError:
            print("NATS - No responders available for request")
        except TimeoutError:
            print("NATS - Request timed out")

        is_valid_access = False

        tmp = json.loads(response.data.decode())

        if "access" in tmp:
            is_valid_access = tmp["access"]

        if is_valid_access:
            await self.app(scope, receive, send)
        else:
            response: Response
            response = PlainTextResponse("Unauthorized", status_code=401)
            await response(scope, receive, send)
