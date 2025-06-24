import time
from concurrent.futures import ThreadPoolExecutor

from verdict.util.ratelimit import TimeWindowRateLimiter

rate_limiter = TimeWindowRateLimiter(max_value=3, window_seconds=1)


def execute(i: int):
    start = time.perf_counter()
    print(f"start {i}")
    event = rate_limiter.acquire(value=1)
    event.wait()

    print(f"work {i}")
    time.sleep(2)
    print(f"done {i} ({time.perf_counter() - start:.2f}s)")

    rate_limiter.release(value=0)


with ThreadPoolExecutor(max_workers=10) as executor:
    for i in range(10):
        executor.submit(execute, i)
