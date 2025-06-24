import time
from concurrent.futures import ThreadPoolExecutor

from verdict.util.ratelimit import UnlimitedRateLimiter

rate_limiter = UnlimitedRateLimiter()


def execute(i: int):
    start = time.perf_counter()
    print(f"start {i}")
    event = rate_limiter.acquire()
    event.wait()

    print(f"work {i}")
    time.sleep(2)
    print(f"done {i} ({time.perf_counter() - start:.2f}s)")

    rate_limiter.release()


with ThreadPoolExecutor(max_workers=10) as executor:
    for i in range(10):
        executor.submit(execute, i)
