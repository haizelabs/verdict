from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from typing import Any, List, Optional, Set

from verdict.core.executor import Task
from verdict.core.visualization import BranchManager
from verdict.schema import Schema
from verdict.util.exceptions import ConfigurationError


# fresh on init/copy, shared on clone
@dataclass
class SynchronizationState:
    lock: threading.Lock

    peers: Set["Task"]  # n_peers

    shared: bool
    branch_lock: threading.Lock
    branch: Optional[BranchManager]

    # shared_output logic
    candidate_assigned: bool
    shared_output: threading.Condition
    output: Optional[Schema]

    output_tokens: List[float]

    def __init__(self) -> None:
        self.lock = threading.Lock()

        self.peers = set()

        self.shared = False  # sets to True on clone
        self.branch_lock = threading.Lock()
        self.branch = None

        self.candidate_assigned = False
        self.shared_output = threading.Condition()
        self.output = None

        self.output_tokens = []

    def add(self, peer: "Unit") -> "SynchronizationState":  # noqa: F821 # type: ignore[name-defined]
        with self.lock:
            self.peers.add(peer)
            self.shared = True
        return self


class UserState:
    def __init__(self) -> None:
        object.__setattr__(self, "_dict", {})

    def __getattr__(self, key: str) -> Any:
        try:
            return self._dict[key]
        except KeyError:
            raise ConfigurationError(f"'UserState' object has no attribute '{key}'")

    def __setattr__(self, key: str, value: Any) -> None:
        self._dict[key] = value

    def copy(self) -> "UserState":
        new = UserState()
        object.__setattr__(
            new, "_dict", {k: copy.copy(v) for k, v in self._dict.items()}
        )
        return new
