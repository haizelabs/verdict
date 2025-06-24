import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from pydantic import Field
from pydantic.fields import FieldInfo

from verdict.util.exceptions import ConfigurationError


class ScaleType(Enum):
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"


class Scale(ABC):
    T: Type

    def __init__(self, scale_type: ScaleType, end_is_worst: bool = False) -> None:
        self.scale_type = scale_type
        self.end_is_worst = end_is_worst
        self.signifiers = ["best", "worst"] if end_is_worst else ["worst", "best"]

    @abstractmethod
    def pydantic_fields(self, key: str = "output") -> Dict[str, Tuple[Any, Any]]:
        pass

    @abstractmethod
    def prompt(self) -> str:
        pass

    @abstractmethod
    def __str__(self) -> str:
        pass


class DiscreteScale(Scale):
    values: List[Any]

    def __init__(
        self,
        values: Union[List[Any], Tuple[Any, Any], Tuple[Any, Any, Optional[int]]],
        end_is_worst: bool = False,
    ):
        super().__init__(ScaleType.DISCRETE, end_is_worst)
        if isinstance(values, tuple):
            if len(values) == 2:
                values = [*values, 1]
            self.start, self.end, step = values
            if step is None:
                step = 1

            self.T = type(self.start)
            if self.T is int:
                self.values = list(range(self.start, self.end + 1, step))
            elif self.T is float:
                self.values = [
                    round(self.start + i * step, 10)
                    for i in range(int((self.end - self.start) / step) + 1)
                ]
            elif self.T is str:
                self.values = [
                    chr(i) for i in range(ord(self.start), ord(self.end) + 1, step)
                ]
            else:
                raise ConfigurationError(
                    "Invalid values for DiscreteScale: must be a list or a tuple defining a range"
                )
        elif isinstance(values, list):
            self.values = values
        else:
            raise ConfigurationError(
                "Invalid values for DiscreteScale: must be a list or a tuple defining a range"
            )

        if not self.values:
            raise ConfigurationError("Discrete scale must have at least one value")

        self.T = type(self.values[0])

    def pydantic_fields(self, key: str = "output") -> Dict[str, Tuple[Any, FieldInfo]]:
        if self.T in [int, float] and hasattr(self, "start") and hasattr(self, "end"):
            output_field = Field(..., ge=self.start, le=self.end)
        else:
            value_options = "|".join(re.escape(str(value)) for value in self.values)
            output_field = Field(..., pattern=f"^({value_options})$")

        return {
            key: (self.T, output_field),
        }

    def prompt(self) -> str:
        return f"""Respond with a single output value from "{'", "'.join(map(str, self.values))}" where "{self.values[0]}" is {self.signifiers[0]} and "{self.values[-1]}" is {self.signifiers[1]}."""

    def token_support(self) -> List[str]:
        return [str(value) for value in self.values]

    def index(self, token: str) -> int:
        return self.token_support().index(token)

    def value_mapping_fn(self, output: str) -> Any:
        if self.T is int:
            return int(output)

        if self.T is float:
            return float(output)

        return output

    def __str__(self) -> str:
        return ", ".join(
            map(str, self.values[::-1] if self.end_is_worst else self.values)
        )


class BooleanScale(DiscreteScale):
    def __init__(
        self, yes: List[str] = ["yes", "Yes", "YES"], no: List[str] = ["no", "No", "NO"]
    ) -> None:
        values = no + yes
        super().__init__(values=values)

        self.yes = yes
        self.no = no

        self.T = bool

    def pydantic_fields(self, key: str = "output") -> Dict[str, Tuple[Any, FieldInfo]]:
        return {key: (bool, Field(...))}

    def token_support(self) -> List[str]:
        return self.yes + self.no

    def value_mapping_fn(self, output: str) -> bool:
        if output in self.yes:
            return True
        return False

    def __str__(self) -> str:
        return ",".join(map(lambda v: "/".join(v), [self.yes, self.no]))


class ContinuousScale(Scale):
    def __init__(
        self, min_value: float, max_value: float, end_is_worst: bool = False
    ) -> None:
        super().__init__(ScaleType.CONTINUOUS, end_is_worst)
        if min_value >= max_value:
            raise ConfigurationError(
                "Continuous scale minimum must be less than maximum"
            )
        self.min_value = min_value
        self.max_value = max_value

        self.T = float

    def pydantic_fields(self, key: str = "output") -> Dict[str, Tuple[Any, FieldInfo]]:
        return {
            key: (float, Field(..., ge=self.min_value, le=self.max_value)),
        }

    def prompt(self) -> str:
        return f"Provide a score between {self.min_value} ({self.signifiers[0]}) and {self.max_value} ({self.signifiers[1]})."

    def value_mapping_fn(self, output: float) -> float:
        return output

    def __str__(self) -> str:
        return (
            f"{self.max_value} - {self.min_value}"
            if self.end_is_worst
            else f"{self.min_value} - {self.max_value}"
        )


def LikertScale(end_is_worst: bool = False) -> Scale:
    return DiscreteScale((1, 5), end_is_worst)
