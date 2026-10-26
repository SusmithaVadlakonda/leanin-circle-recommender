"""Start the real server, check the endpoints that matter, then stop it.

The in-process API tests can't prove that the server starts, seeds a missing database
and serves over HTTP. This does, launching the app the same way `make run` does.

Usage: python -m scripts.smoke
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STARTUP_TIMEOUT_S = 20


def _ids(response) -> list[int]:
    return [r["circle"]["id"] for r in response.json()["recommendations"]]


CHECKS = [
    (
        "The root URL redirects to the docs",
        "/",
        lambda r: r.status_code == 307 and r.headers.get("location") == "/docs",
    ),
    ("Health check returns 200", "/health", lambda r: r.status_code == 200 and r.json() == {"status": "ok"}),
    ("User 7 gets #5 and #6 first", "/users/7/recommendations", lambda r: _ids(r)[:2] == [5, 6]),
    (
        "User 15 gets at most one of #10, #11 and #12",
        "/users/15/recommendations",
        lambda r: len({10, 11, 12} & set(_ids(r))) <= 1,
    ),
    (
        "User 23 gets #22 first, with #20 and #21 excluded",
        "/users/23/recommendations?include_excluded=true",
        lambda r: _ids(r)[0] == 22 and {20, 21} <= {e["circle_id"] for e in r.json()["excluded"]},
    ),
    (
        "User 42 gets cold start with a nudge",
        "/users/42/recommendations",
        lambda r: r.json()["strategy"] == "cold_start" and bool(r.json()["profile_nudge"]),
    ),
    ("Unknown user returns 404", "/users/999/recommendations", lambda r: r.status_code == 404),
    ("A limit of 0 returns 422", "/users/7/recommendations?limit=0", lambda r: r.status_code == 422),
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_up(base: str, server: subprocess.Popen) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"the server exited during startup with code {server.returncode}")
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"the server didn't answer /health within {STARTUP_TIMEOUT_S} seconds")


def main() -> int:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        # The database doesn't exist yet, so startup has to seed it.
        env = {**os.environ, "CIRCLES_DB_PATH": str(Path(tmp) / "smoke.db")}
        command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
        server = subprocess.Popen([*command, "--log-level", "warning"], cwd=PROJECT_ROOT, env=env)
        try:
            _wait_until_up(base, server)
            for description, path, check in CHECKS:
                try:
                    passed = bool(check(httpx.get(base + path, timeout=5)))
                    detail = ""
                except Exception as exc:  # report the failure and keep checking
                    passed, detail = False, f"  ({type(exc).__name__}: {exc})"
                failures += not passed
                print(f"  {'PASS' if passed else 'FAIL'}  {description}{detail}")
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
    print(f"smoke: {len(CHECKS) - failures} of {len(CHECKS)} checks passed against a live server")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
