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
    """Make sure we die when the Tauri host dies, on every platform.

    Linux: prctl(PR_SET_PDEATHSIG, SIGTERM) — the kernel signals us
    immediately when the parent disappears, even on `kill -9`.

    macOS / Windows: no kernel-level equivalent is exposed via plain
    libc/Win32, so we spawn a daemon thread that polls the parent PID
    once a second and SIGTERMs ourselves when it's gone. The 1s lag
    is acceptable because the hostile case (host crashed) is rare and
    the orphan would otherwise live indefinitely.
    """
    if sys.platform == "linux":
        _install_prctl_pdeathsig()
        return
    if sys.platform in ("darwin", "win32"):
        _spawn_parent_pid_watcher()


def _install_prctl_pdeathsig() -> None:
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


def _spawn_parent_pid_watcher() -> None:
    parent_pid = os.getppid()
    if parent_pid <= 1:
        return  # already orphaned, nothing to watch

    def _is_alive(pid: int) -> bool:
        if sys.platform == "win32":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong(0)
                ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
                return bool(ok) and code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        # macOS / other POSIX: signal 0 probes existence + permissions.
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        except OSError:
            return False
        return True

    def _watch() -> None:
        import time

        while True:
            time.sleep(1.0)
            if not _is_alive(parent_pid):
                try:
                    os.kill(os.getpid(), signal.SIGTERM)
                except OSError:
                    os._exit(0)
                return

    import threading

    threading.Thread(target=_watch, daemon=True, name="parent-watcher").start()


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
    # Importing the FastAPI app object directly (vs the "app.main:app"
    # string form) is what makes PyInstaller's static analysis bundle
    # the whole app graph — uvicorn's import_from_string doesn't see
    # past the frozen module table.
    import uvicorn
    from app.main import app as fastapi_app

    sock = _bind_socket(args.host, args.port)
    actual_host, actual_port = sock.getsockname()[:2]
    _emit_ready(actual_host, actual_port)

    config = uvicorn.Config(
        fastapi_app,
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
