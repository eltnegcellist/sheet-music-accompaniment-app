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


def _bind_to_parent_lifetime() -> None:
    """Ask the kernel to SIGTERM us when the Tauri host dies (Linux).

    Tauri's Command API doesn't expose a pre-exec hook so we install
    PR_SET_PDEATHSIG from inside the child. The signal is delivered by
    the kernel even on `kill -9` of the parent, which closes the orphan
    sidecar window we'd otherwise have on hard crashes. macOS and
    Windows have no direct equivalent; their orphan handling is a
    follow-up (kqueue watcher / Job Object respectively).
    """
    if sys.platform != "linux":
        return
    try:
        import ctypes

        PR_SET_PDEATHSIG = 1
        SIGTERM = 15
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        if libc.prctl(PR_SET_PDEATHSIG, SIGTERM, 0, 0, 0) != 0:
            err = ctypes.get_errno()
            sys.stderr.write(
                f"[server] WARN: prctl(PR_SET_PDEATHSIG) failed errno={err}\n"
            )
    except OSError as exc:
        sys.stderr.write(f"[server] WARN: parent-death wiring failed: {exc}\n")


def _check_bundled_binaries() -> None:
    """Warn early if env-pointed bundled binaries are missing.

    A missing AUDIVERIS_LAUNCHER or TESSERACT_CMD only manifests when
    the user uploads a PDF, which can be many minutes after launch in
    a Tauri build. Surfacing the misconfiguration on stderr at boot
    makes packaging bugs much faster to diagnose.
    """
    pairs = [
        ("AUDIVERIS_LAUNCHER", os.environ.get("AUDIVERIS_LAUNCHER")),
        ("TESSERACT_CMD", os.environ.get("TESSERACT_CMD")),
        ("JAVA_HOME", os.environ.get("JAVA_HOME")),
    ]
    for name, value in pairs:
        if not value:
            continue
        target = value if name != "JAVA_HOME" else f"{value}/bin/java"
        if not os.path.exists(target):
            sys.stderr.write(
                f"[server] WARN: {name}={value!r} but {target} does not exist\n"
            )
            sys.stderr.flush()


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
    _bind_to_parent_lifetime()
    _check_bundled_binaries()

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
