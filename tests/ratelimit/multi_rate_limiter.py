import time
from concurrent.futures import ThreadPoolExecutor

from verdict.util.ratelimit import (
    ConcurrentRateLimiter,
    RateLimitPolicy,
    TimeWindowRateLimiter,
)

rate_limit = RateLimitPolicy(
    {
        ConcurrentRateLimiter(max_concurrent=1): "requests",
        TimeWindowRateLimiter(
            max_value=2, window_seconds=1, smoothing_factor=1
        ): "requests",
    }
)


def execute(i: int):
    start = time.perf_counter()
    print(f"start {i}")
    event = rate_limit.acquire({"requests": 1})
    event.wait()

    print(f"work {i}")
    time.sleep(2)
    print(f"done {i} ({time.perf_counter() - start:.2f}s)")

    rate_limit.release()


with ThreadPoolExecutor(max_workers=10) as executor:
    for i in range(10):
        executor.submit(execute, i)
