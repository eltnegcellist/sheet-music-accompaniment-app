"""Sidecar entrypoint for the FastAPI backend.

This module is the PyInstaller target. It does three things the bare
``uvicorn`` CLI cannot:

1. Bind the listening socket itself so callers can request port 0 and
   learn the OS-assigned port back.
2. Surface that port on stdout as a single ``READY {"port": N}`` line so
   the Tauri host can wire ``window.__BACKEND_URL__`` to it.
3. Honour ``--app-data`` / ``--param-set`` by pushing them into the env
   before importing the FastAPI app, so module-level config in
   ``app.main`` picks them up on first import.

Outside Tauri the script is still useful for local development:

    python -m app.server --port 8000 --app-data ./.devdata
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
from typing import NoReturn


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="accompanist-server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="TCP port to bind. 0 (default) lets the OS pick a free port.",
    )
    parser.add_argument(
        "--app-data",
        default=None,
        help="Writable root for caches/state. Exported as APP_DATA_DIR.",
    )
    parser.add_argument(
        "--param-set",
        default=None,
        help="Active pipeline param set id. Exported as PIPELINE_PARAM_SET.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
    )
    return parser.parse_args(argv)


def _apply_env(args: argparse.Namespace) -> None:
    if args.app_data:
        os.environ["APP_DATA_DIR"] = args.app_data
    if args.param_set:
        os.environ["PIPELINE_PARAM_SET"] = args.param_set


def _bind_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.set_inheritable(True)
    return sock


def _emit_ready(host: str, port: int) -> None:
    payload = {"host": host, "port": port}
    sys.stdout.write(f"READY {json.dumps(payload)}\n")
    sys.stdout.flush()


def _install_signal_handlers(server) -> None:
    def _graceful(signum, _frame):  # noqa: ANN001
        server.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _graceful)
        except ValueError:
            # Not on the main thread (Windows multiprocessing); skip.
            pass


def main(argv: list[str] | None = None) -> NoReturn:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _apply_env(args)

    # uvicorn / FastAPI imports are deferred until after env is populated
    # so module-level reads in app.main see the values from --param-set.
    import uvicorn

    sock = _bind_socket(args.host, args.port)
    actual_host, actual_port = sock.getsockname()[:2]
    _emit_ready(actual_host, actual_port)

    config = uvicorn.Config(
        "app.main:app",
        log_level=args.log_level,
        access_log=False,
        # Host/port are unused when we hand uvicorn a pre-bound socket but
        # are still required by Config; pass the resolved values for the
        # benefit of log output.
        host=actual_host,
        port=actual_port,
    )
    server = uvicorn.Server(config)
    _install_signal_handlers(server)

    # Server.run() drives its own asyncio loop and accepts pre-bound sockets.
    server.run(sockets=[sock])
    sys.exit(0)


if __name__ == "__main__":
    main()
