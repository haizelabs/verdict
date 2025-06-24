from __future__ import annotations

import logging
import signal
import sys
import threading
from functools import wraps
from typing import Any, Callable, Optional, Type


def is_signal_safe():
    """
    Strictly check if the current environment is safe for signal handling.

    Returns:
        bool: True only if ALL signal safety conditions are met
    """
    # Must be in the main thread
    if threading.current_thread() is not threading.main_thread():
        return False

    # Must be in the main interpreter
    if not hasattr(sys, "argv"):
        return False

    # Additional interpreter state checks
    if not sys.modules.get("__main__"):
        return False

    # Check if the interpreter is shutting down
    if sys is None or threading is None:
        return False

    return True


def keyboard_interrupt_safe(func: Callable[[Any], Any]) -> Callable[[Any], Any]:
    @wraps(func)
    def wrapped(self: Any, *args, **kwargs) -> Any:
        if is_signal_safe():
            original_handler = signal.getsignal(signal.SIGINT)
            signal.signal(
                signal.SIGINT, lambda signum, frame: self.executor.graceful_shutdown()
            )

            try:
                return func(self, *args, **kwargs)
            except KeyboardInterrupt:
                self.executor.graceful_shutdown()
            finally:
                signal.signal(signal.SIGINT, original_handler)
        else:
            return func(self, *args, **kwargs)

    return wrapped


class DisableLogger:
    def __init__(self, logger_name: str, all: bool = False) -> None:
        self.logger = logging.getLogger(logger_name)
        self.previous_level: Optional[int] = None
        self.all = all

    def __enter__(self) -> None:
        self.previous_level = self.logger.level
        new_level = logging.CRITICAL
        if self.all:
            new_level += 1
        self.logger.setLevel(new_level)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.logger.setLevel(self.previous_level)  # type: ignore


def lightweight(cls: Type) -> Type:
    cls.lightweight = True
    return cls
