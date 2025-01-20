from __future__ import annotations

# import typing
import json
import time
import nats

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
        exclude_paths: list[str],
        test: bool = False,
    ) -> None:
        self.app = app
        self.nats_subject = nats_subject
        if isinstance(nats_servers, str):
            nats_servers = parse_nats_servers(nats_servers)
        self.nats_servers = nats_servers
        self.service_name = service_name
        self.nats_connection = None
        self.exclude_paths = exclude_paths
        self.test = test

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        if scope["path"] in self.exclude_paths:
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
            "version": "v2",
        }
        json_data = json.dumps(data)
        tmp = {}

        if not self.test:
            try:
                if self.nats_connection is None or self.nats_connection.is_closed:
                    self.nats_connection = await nats.connect(servers=self.nats_servers)

                msg = await self.nats_connection.request(
                    self.nats_subject, json_data.encode(), timeout=5
                )
                tmp = json.loads(msg.data.decode())

                print(f"Received response: {msg.data.decode()}")
            except Exception as exp:  # pylint: disable=broad-exception-caught
                print(f"Error: {exp}")
                response: Response
                response = PlainTextResponse(
                    "500 Internal Server Error", status_code=500
                )
                await response(scope, receive, send)
                return
        else:
            tmp = {"access": True, "id": 0}
            print(json_data)

        is_valid_access = False

        if "access" in tmp:
            is_valid_access = tmp["access"]

        if is_valid_access:
            start = time.time()
            await self.app(scope, receive, send)
            end = time.time()

            response_time = end - start

            row_id = 0
            if "id" in tmp:
                row_id = tmp["id"]

            result = {
                "id": row_id,
                "status": "OK",
                "response_time": format_str_time(response_time),
            }
            result_json = json.dumps(result)

            await self.nats_connection.publish(
                self.nats_subject + ".result", result_json.encode()
            )
        else:
            response: Response
            response = PlainTextResponse("404 Page Not Found", status_code=404)
            await response(scope, receive, send)


def format_str_time(seconds: float) -> str:
    if seconds < 1:
        if seconds < 1e-6:
            return f"{(seconds * 1e9):.3f}ns"
        elif seconds < 1e-3:
            return f"{(seconds * 1e6):.3f}µs"
        else:
            return f"{(seconds * 1000):.3f}ms"
    elif seconds < 60:
        return f"{(seconds):.3f}s"
    elif seconds < 3600:
        return f"{(seconds // 60)}m {(seconds % 60):.3f}s"
    else:
        return f"{(seconds // 3600)}h {((seconds % 3600) // 60)}m {(seconds % 60):.3f}s"
