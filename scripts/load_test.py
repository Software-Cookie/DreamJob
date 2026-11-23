"""Simple concurrency test: N simulated users upload a résumé at the same moment.

Usage:
    python scripts/load_test.py --url http://localhost:8000 --users 100
"""
import argparse
import asyncio
import statistics
import time
from pathlib import Path

import httpx

RESUME = (Path(__file__).parent / "sample_resume.txt").read_bytes()
WINDOWS = ["24h", "48h", "72h", "1w", "1m"]
TOPS = ["3", "10", "20", "30"]


async def one_user(client, url, i):
    t = time.perf_counter()
    r = await client.post(f"{url}/api/analyze",
                          files={"file": ("resume.txt", RESUME, "text/plain")},
                          data={"window": WINDOWS[i % 5], "top": TOPS[i % 4]},
                          headers={"X-Forwarded-For": f"10.0.{i // 250}.{i % 250}"})  # distinct IPs for rate limiter
    return r.status_code, time.perf_counter() - t


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--users", type=int, default=100)
    a = ap.parse_args()
    async with httpx.AsyncClient(timeout=120, limits=httpx.Limits(max_connections=a.users)) as c:
        await one_user(c, a.url, 0)  # warm the live-search cache
        t0 = time.perf_counter()
        res = await asyncio.gather(*(one_user(c, a.url, i) for i in range(a.users)))
        wall = time.perf_counter() - t0
    lat = sorted(t for _, t in res)
    codes = {}
    for code, _ in res:
        codes[code] = codes.get(code, 0) + 1
    print(f"{a.users} simultaneous users, finished in {wall:.2f}s, status codes {codes}")
    print(f"latency  p50 {statistics.median(lat):.2f}s  p95 {lat[int(len(lat) * .95) - 1]:.2f}s  max {lat[-1]:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
