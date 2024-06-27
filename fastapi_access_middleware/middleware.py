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
        test: bool = False,
    ) -> None:
        self.app = app
        self.nats_subject = nats_subject
        if isinstance(nats_servers, str):
            nats_servers = parse_nats_servers(nats_servers)
        self.nats_servers = nats_servers
        self.service_name = service_name
        self.nats_connection = None
        self.test = test

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        url = URL(scope=scope)

        data = {
            "headers": dict(headers),
            "method": scope["method"],
            "path": scope["path"],
            "query_string": scope["query_string"].decode(),
            "raw_path": scope["raw_path"].decode(),
            "scheme": scope["scheme"],
            "service_name": self.service_name,
            "type": scope["type"],
            "url": str(url),
        }
        json_data = json.dumps(data)
        tmp = {}

        if not self.test:
            if self.nats_connection is None or self.nats_connection.is_closed:
                self.nats_connection = await nats.connect(servers=self.nats_servers)

            try:
                response = await self.nats_connection.request(
                    self.nats_subject, json_data.encode(), timeout=5
                )
                tmp = json.loads(response.data.decode())

                print(
                    "Received response: {message}".format(
                        message=response.data.decode()
                    )
                )
            except nats.errors.NoRespondersError:
                print("NATS - No responders available for request")
            except TimeoutError:
                print("NATS - Request timed out")
        else:
            tmp = {"access": True}
            print(json_data)

        is_valid_access = False

        if "access" in tmp:
            is_valid_access = tmp["access"]

        if is_valid_access:
            await self.app(scope, receive, send)
        else:
            response: Response
            response = PlainTextResponse("Unauthorized", status_code=401)
            await response(scope, receive, send)
