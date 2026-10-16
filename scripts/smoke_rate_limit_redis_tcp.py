"""Smoke local do limiter Redis TCP contra um redis:7.4-alpine descartável (127.0.0.1)."""

import asyncio
import socket
import subprocess
import sys
import time

from src.core.rate_limit import RateLimitPolicy, RedisTcpRateLimiter


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _run(port: int) -> None:
    limiter = RedisTcpRateLimiter(f"redis://127.0.0.1:{port}/0")
    policy = RateLimitPolicy("smoke", limit=3, window_seconds=30)
    results = [await limiter.check(policy, "203.0.113.9") for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False], results
    assert 1 <= results[-1].retry_after_seconds <= 30, results[-1]
    other = await limiter.check(policy, "203.0.113.10")
    assert other.allowed is True
    await limiter.aclose()
    print("OK", [(r.allowed, r.retry_after_seconds) for r in results])


def main() -> int:
    port = _free_port()
    name = f"rl-smoke-{port}"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:6379",
            "redis:7.4-alpine",
        ],
        check=True,
        capture_output=True,
    )
    try:
        for _ in range(50):
            ping = subprocess.run(
                ["docker", "exec", name, "redis-cli", "ping"], capture_output=True, text=True
            )
            if ping.stdout.strip() == "PONG":
                break
            time.sleep(0.2)
        asyncio.run(_run(port))
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
