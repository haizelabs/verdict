import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from enum import Enum
from queue import Queue
from types import SimpleNamespace
from typing import Dict, List, Optional, Protocol, Tuple, Union

from verdict.util.exceptions import VerdictSystemError


def disable() -> None:
    from verdict.config import state
    from verdict.util.log import logger

    state.rate_limiter_disabled = True
    logger.info(
        "Rate limiting is disabled. All requests will follow an UnlimitedRateLimiter."
    )


def enable() -> None:
    from verdict.config import state
    from verdict.util.log import logger

    state.rate_limiter_disabled = False
    logger.info(
        "Rate limiting is enabled. All requests will fallback to their configured RateLimitPolicy."
    )


class RateLimiterMetric(Enum):
    REQUESTS = "requests"
    TOKENS = "tokens"


class RateLimiter(ABC):
    @abstractmethod
    def acquire(self, value: Optional[int] = None) -> threading.Event:
        pass

    @abstractmethod
    def release(self, value: Optional[int] = None) -> None:
        pass

    @abstractmethod
    def copy(self) -> "RateLimiter":
        pass

    def __str__(self) -> str:
        return f"{self.__class__.__name__}()"


class UnlimitedRateLimiter(RateLimiter):
    def acquire(self, value: Optional[int] = None) -> threading.Event:
        event = threading.Event()
        event.set()
        return event

    def release(self, value: Optional[int] = None) -> None:
        pass

    def copy(self) -> "UnlimitedRateLimiter":
        return UnlimitedRateLimiter()


class ConcurrentRateLimiter(RateLimiter):
    # config
    max_concurrent: int

    # state
    waiting: Queue[threading.Event]
    lock: threading.RLock
    running: int

    def __init__(self, max_concurrent: int) -> None:
        self.waiting = Queue()

        self.max_concurrent = max_concurrent

        self.lock = threading.RLock()
        self.running = 0

    def copy(self) -> "ConcurrentRateLimiter":
        return ConcurrentRateLimiter(self.max_concurrent)

    def expire(self) -> None:
        with self.lock:
            while self.running < self.max_concurrent and not self.waiting.empty():
                event = self.waiting.get()
                self.running += 1
                event.set()

    def acquire(self, value: Optional[int] = None) -> threading.Event:
        event = threading.Event()
        self.waiting.put(event)

        with self.lock:
            self.expire()

        return event

    def release(self, value: Optional[int] = None) -> None:
        with self.lock:
            self.running -= 1
            self.expire()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(max={self.max_concurrent})"


class TimeWindowRateLimiter(RateLimiter):
    def __init__(
        self, max_value: int, window_seconds: int, smoothing_factor: float = 0.9
    ) -> None:
        self.max_value = max_value
        self.window_seconds = window_seconds
        self.smoothing_factor = smoothing_factor

        self.lock = threading.RLock()
        self.values: deque[Tuple[int, float]] = deque()
        self.waiting: deque[Tuple[threading.Event, int]] = deque()
        self._stop_event = threading.Event()

        # expiration thread
        self._expiration_thread = threading.Thread(
            target=self._expire_and_process, daemon=True
        )
        self._expiration_thread.start()

    def copy(self) -> "TimeWindowRateLimiter":
        return TimeWindowRateLimiter(
            self.max_value, self.window_seconds, self.smoothing_factor
        )

    def _expire_and_process(self) -> None:
        while not self._stop_event.is_set():
            with self.lock:
                self.expire()
                self._process_waiting_tasks()
            time.sleep(0.1)

    def expire(self) -> None:
        now = time.perf_counter()
        while self.values and now - self.values[0][1] > self.window_seconds:
            self.values.popleft()

    def current_sum(self) -> int:
        return sum(value for value, _ in self.values)

    def acquire(self, value: Optional[int] = None) -> threading.Event:
        if value is None:
            raise VerdictSystemError("Value is required for TimeWindowRateLimiter")

        event = threading.Event()
        with self.lock:
            self.expire()

            if self.current_sum() + value <= (self.max_value * self.smoothing_factor):
                self.values.append((value, time.perf_counter()))
                event.set()
            else:
                self.waiting.append((event, value))

        return event

    def _process_waiting_tasks(self) -> None:
        while self.waiting:
            wait_event, wait_value = self.waiting[0]
            if self.current_sum() + wait_value <= (
                self.max_value * self.smoothing_factor
            ):
                self.values.append((wait_value, time.perf_counter()))
                wait_event.set()
                self.waiting.popleft()
            else:
                break

    def release(self, value: Optional[int] = None) -> None:
        if value is None:
            raise VerdictSystemError("Value is required for TimeWindowRateLimiter")

        with self.lock:
            self.values.append((value, time.perf_counter()))
            self._process_waiting_tasks()

    def shutdown(self) -> None:
        """Stop the expiration thread."""
        self._stop_event.set()
        self._expiration_thread.join()

    def __del__(self) -> None:
        self.shutdown()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(max_value={self.max_value}, window_seconds={self.window_seconds}, smoothing_factor={self.smoothing_factor})"


RateLimitConfig = Dict[RateLimiter, Union[str, RateLimiterMetric]]


class MultiEvent(Protocol):
    def wait(self) -> None: ...

    def is_set(self) -> bool: ...


class RateLimitPolicy:
    # config
    rate_limiters: Dict[RateLimiter, RateLimiterMetric]

    def __init__(self, rate_limiters: RateLimitConfig) -> None:
        self.rate_limiters = {
            rate_limiter: RateLimiterMetric(metric)
            for rate_limiter, metric in rate_limiters.items()
        }

    def copy(self) -> "RateLimitPolicy":
        return RateLimitPolicy(
            {
                rate_limiter.copy(): metric
                for rate_limiter, metric in self.rate_limiters.items()
            }
        )

    def acquire(self, values: Dict[str, int] = {}) -> MultiEvent:
        events: List[threading.Event] = []
        for rate_limiter, metric in self.rate_limiters.items():
            events.append(rate_limiter.acquire(values.get(metric.value, 0)))

        return SimpleNamespace(
            wait=lambda: [event.wait() for event in events],
            is_set=lambda: all(event.is_set() for event in events),
        )

    def release(self, values: Dict[str, int] = {}) -> None:
        for rate_limiter, metric in self.rate_limiters.items():
            rate_limiter.release(values.get(metric.value, 0))

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({' | '.join(f'{metric.value}@{rate_limiter}' for rate_limiter, metric in self.rate_limiters.items())})"

    def __repr__(self) -> str:
        return self.__str__()

    @staticmethod
    def of(rpm: int, tpm: int) -> "RateLimitPolicy":
        return RateLimitPolicy(
            {
                TimeWindowRateLimiter(max_value=rpm, window_seconds=60): "requests",
                TimeWindowRateLimiter(max_value=tpm, window_seconds=60): "tokens",
            }
        )

    @staticmethod
    def using(
        requests: Optional[Union[RateLimiter, List[RateLimiter]]] = [],
        tokens: Optional[Union[RateLimiter, List[RateLimiter]]] = [],
    ) -> "RateLimitPolicy":
        requests = requests if isinstance(requests, list) else [requests]
        tokens = tokens if isinstance(tokens, list) else [tokens]

        return RateLimitPolicy(
            {
                **{request: RateLimiterMetric.REQUESTS for request in requests},
                **{token: RateLimiterMetric.TOKENS for token in tokens},
            }
        )
