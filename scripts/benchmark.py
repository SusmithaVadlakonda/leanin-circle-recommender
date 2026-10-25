"""Latency of the recommendations endpoint for every user, measured in process.

Each request goes through the full app: routing, the member lookup, ranking,
explanations and JSON serialization. Network time is left out.

Usage: python -m scripts.benchmark [--rounds N]
Exits non-zero if the 95th percentile exceeds the target.
"""
import argparse
import math
import sys
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using .httpx. with .starlette.testclient. is deprecated")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

TARGET_P95_MS = 50.0
USERS = range(1, 101)


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=5, help="passes over all users (default: 5)")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        with TestClient(create_app(Settings(db_path=Path(tmp) / "bench.db"))) as client:
            for user_id in USERS:  # warm-up
                client.get(f"/users/{user_id}/recommendations")
            timings = []
            for _ in range(args.rounds):
                for user_id in USERS:
                    start = time.perf_counter()
                    response = client.get(f"/users/{user_id}/recommendations")
                    timings.append((time.perf_counter() - start) * 1000)
                    if response.status_code != 200:
                        print(f"bench: user {user_id} returned {response.status_code}", file=sys.stderr)
                        return 1

    p50, p95 = percentile(timings, 50), percentile(timings, 95)
    verdict = "within" if p95 < TARGET_P95_MS else "OVER"
    print(f"bench: {len(timings)} requests | p50 {p50:.1f} ms | p95 {p95:.1f} ms | {verdict} the {TARGET_P95_MS:.0f} ms target")
    return 0 if p95 < TARGET_P95_MS else 1


if __name__ == "__main__":
    sys.exit(main())
