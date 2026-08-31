"""Local HTTP collector and dashboard for the Velocity Connect prototype."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit

from .model import MeasurementStore


MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard.html"


def _handler_for(store: MeasurementStore, dashboard_html: bytes) -> type[BaseHTTPRequestHandler]:
    class PrototypeHandler(BaseHTTPRequestHandler):
        server_version = "VelocityConnectPrototype/0.1"

        def _send_bytes(
            self,
            status: HTTPStatus,
            body: bytes,
            content_type: str,
            *,
            cache_control: str = "no-store",
        ) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, sort_keys=True, allow_nan=False).encode("utf-8")
            self._send_bytes(status, body, "application/json; charset=utf-8")

        def _path(self) -> str:
            return urlsplit(self.path).path.rstrip("/") or "/"

        def _discard_bounded_request_body(self) -> None:
            """Drain a small request body before replying on an unknown route.

            Leaving unread POST bytes can make Windows close the socket with a
            TCP reset, hiding the intended HTTP error from the client.
            """
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return
            try:
                content_length = int(raw_length)
            except ValueError:
                self.close_connection = True
                return
            if content_length <= 0:
                return
            if content_length > MAX_REQUEST_BYTES:
                self.close_connection = True
                return
            self.rfile.read(content_length)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = self._path()
            if path == "/healthz":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "velocity-connect-prototype",
                        "timestamp_utc": datetime.now(timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    },
                )
                return
            if path == "/api/v1/status":
                self._send_json(HTTPStatus.OK, store.status())
                return
            if path == "/api/v1/report":
                self._send_json(HTTPStatus.OK, store.report())
                return
            if path == "/":
                self._send_bytes(
                    HTTPStatus.OK,
                    dashboard_html,
                    "text/html; charset=utf-8",
                    cache_control="no-cache",
                )
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self._path() != "/api/v1/samples":
                self._discard_bounded_request_body()
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
                return

            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._send_json(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length is required"})
                return
            try:
                content_length = int(raw_length)
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid Content-Length"})
                return
            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                self._send_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": f"request body must be 1-{MAX_REQUEST_BYTES} bytes"},
                )
                return

            try:
                payload = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "body must be valid UTF-8 JSON"})
                return

            try:
                accepted = store.add(payload)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except OverflowError as exc:
                self._send_json(HTTPStatus.INSUFFICIENT_STORAGE, {"error": str(exc)})
                return
            except OSError as exc:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": f"evidence persistence failed: {exc}"},
                )
                return

            status = HTTPStatus.CREATED if accepted else HTTPStatus.OK
            self._send_json(
                status,
                {
                    "accepted": accepted,
                    "duplicate": not accepted,
                    "sample_count": store.status()["sample_count"],
                },
            )

        def log_message(self, format_string: str, *args: Any) -> None:
            message = (format_string % args).replace("\r", "\\r").replace("\n", "\\n")
            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            sys.stderr.write(f"[{timestamp}] {self.client_address[0]} {message}\n")

    return PrototypeHandler


def create_server(
    host: str,
    port: int,
    store: MeasurementStore,
    dashboard_path: str | Path = DEFAULT_DASHBOARD,
) -> ThreadingHTTPServer:
    dashboard = Path(dashboard_path)
    if not dashboard.is_file():
        raise FileNotFoundError(f"dashboard not found: {dashboard}")
    server = ThreadingHTTPServer((host, port), _handler_for(store, dashboard.read_bytes()))
    server.daemon_threads = True
    return server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind address; keep localhost for v0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", default="out/prototype/samples.jsonl")
    parser.add_argument("--max-samples", type=int, default=50_000)
    parser.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 0 <= args.port <= 65535:
        raise SystemExit("--port must be between 0 and 65535")
    store = MeasurementStore(args.data, max_samples=args.max_samples)
    server = create_server(args.host, args.port, store, args.dashboard)
    bound_host, bound_port = server.server_address[:2]
    print(f"Velocity Connect prototype: http://{bound_host}:{bound_port}")
    print(f"Evidence: {Path(args.data).resolve()}")
    print("LAB PROTOTYPE: monitoring only; do not expose this server to an untrusted network.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping collector.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
