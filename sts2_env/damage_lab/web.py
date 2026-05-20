"""Local HTTP interface for the damage validation workbench."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from sts2_env.damage_lab.service import catalog_payload, validate_case, validate_suite


def render_index_html() -> str:
    html_path = Path(__file__).with_name("static") / "index_dual.html"
    return html_path.read_text(encoding="utf-8")


def dispatch_request(method: str, path: str, payload: dict | None = None):
    route = urlparse(path).path
    for prefix in ("/sts2-damage-lab",):
        if route == prefix:
            route = "/"
            break
        if route.startswith(prefix + "/"):
            route = route[len(prefix):]
            break
    if method == "GET" and route == "/":
        return 200, {"Content-Type": "text/html; charset=utf-8"}, render_index_html()
    if method == "GET" and route == "/api/catalog":
        return 200, {"Content-Type": "application/json; charset=utf-8"}, catalog_payload()
    if method == "POST" and route == "/api/validate":
        data = payload or {}
        if "cases" in data:
            return 200, {"Content-Type": "application/json; charset=utf-8"}, validate_suite(data)
        return 200, {"Content-Type": "application/json; charset=utf-8"}, validate_case(data)
    return 404, {"Content-Type": "application/json; charset=utf-8"}, {"error": f"Unknown route: {route}"}


class DamageLabHandler(BaseHTTPRequestHandler):
    """Thin wrapper around pure dispatch helpers."""

    server_version = "DamageLabHTTP/0.1"

    def do_GET(self) -> None:  # noqa: N802
        self._respond("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._respond("POST")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None

    def _respond(self, method: str) -> None:
        try:
            payload = None
            if method == "POST":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8"))
            status, headers, body = dispatch_request(method, self.path, payload)
        except json.JSONDecodeError as exc:
            status, headers, body = 400, {"Content-Type": "application/json; charset=utf-8"}, {"error": f"Invalid JSON: {exc}"}
        except Exception as exc:  # pragma: no cover - safety boundary
            status, headers, body = 500, {"Content-Type": "application/json; charset=utf-8"}, {"error": str(exc)}

        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()

        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        else:
            data = body.encode("utf-8")
        self.wfile.write(data)


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), DamageLabHandler)
    print(f"Damage lab running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
