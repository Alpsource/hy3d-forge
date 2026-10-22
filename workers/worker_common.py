"""Minimal HTTP worker, standard library only.

These scripts run inside a backend's own virtualenv, so they must not assume anything
beyond the standard library - the two Hunyuan3D releases pin different web stacks, and a
worker that needed fastapi would couple the router to whichever version each venv happens
to hold.

Protocol:
    GET  /health    -> 200 {"status": "ok", "backend": name}
    POST /generate  -> 200 {"output_path": str, "stats": {...}}  |  500 {"error": str}
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict

MAX_BODY_BYTES = 1 * 1024 * 1024


def prepare_image(image, mode, rembg):
    """Apply background removal according to `mode`.

    "auto"   - cut out unless the image already carries real transparency
    "always" - cut out regardless, for a cutout that still has background baked in
    "never"  - use the image exactly as given

    "auto" only inspects the alpha channel, so an RGBA image whose alpha is partly
    transparent is taken to be a finished cutout even when it is not. That is the case
    "always" exists for.
    """
    if mode == "never":
        return image
    if mode == "always":
        return rembg(image.convert("RGB"))

    already_cut_out = image.mode == "RGBA" and image.getextrema()[3][0] < 255
    return image if already_cut_out else rembg(image.convert("RGB"))


def run_worker(name: str, generate: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    """Serve `generate` over HTTP until terminated."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args, _ = parser.parse_known_args()

    # One job at a time: the GPU is the bottleneck and the models are not reentrant.
    # /health stays responsive because the server is threaded.
    gpu_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send(200, {"status": "ok", "backend": name})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/generate":
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_BODY_BYTES:
                    self._send(400, {"error": "bad Content-Length"})
                    return
                payload = json.loads(self.rfile.read(length))
            except Exception as error:
                self._send(400, {"error": f"bad request: {error}"})
                return

            with gpu_lock:
                try:
                    self._send(200, generate(payload))
                except Exception as error:
                    traceback.print_exc()
                    self._send(500, {"error": f"{type(error).__name__}: {error}"})

        def log_message(self, fmt, *fmt_args):  # keep the router's log readable
            sys.stderr.write(f"[{name}] {fmt % fmt_args}\n")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[{name}] listening on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
