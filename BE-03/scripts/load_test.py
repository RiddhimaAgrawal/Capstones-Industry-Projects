"""Tiny load test: fires concurrent requests with one key and reports throughput,
latency percentiles and the 200/429 split (proves the rate limiter works under load).

  python scripts/load_test.py --key apk_xxx --n 500 --concurrency 20
"""
import argparse
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx

p = argparse.ArgumentParser()
p.add_argument("--host", default="http://localhost:8000")
p.add_argument("--key", required=True)
p.add_argument("--n", type=int, default=500)
p.add_argument("--concurrency", type=int, default=20)
a = p.parse_args()


def call(_):
    t = time.perf_counter()
    r = httpx.post(f"{a.host}/v1/analyze/sentiment", json={"text": "This film was great"},
                   headers={"X-API-Key": a.key}, timeout=10)
    return r.status_code, (time.perf_counter() - t) * 1000


start = time.perf_counter()
with ThreadPoolExecutor(a.concurrency) as ex:
    results = list(ex.map(call, range(a.n)))
elapsed = time.perf_counter() - start

lat = sorted(l for _, l in results)
codes = Counter(c for c, _ in results)
print(f"requests={a.n} elapsed={elapsed:.2f}s throughput={a.n / elapsed:.0f} req/s")
print(f"status codes: {dict(codes)}")
print(f"latency ms: p50={statistics.median(lat):.1f} p95={lat[int(.95 * len(lat)) - 1]:.1f} max={lat[-1]:.1f}")
