import statistics
from operator import attrgetter
from typing import Any, Callable, List, Union

from verdict.core.primitive import Unit
from verdict.schema import Schema
from verdict.util.exceptions import VerdictExecutionTimeError
from verdict.util.misc import lightweight


@lightweight
class MapUnit(Unit):
    _char: str = "Map"

    accumulate: bool = True
    map_func: Callable[[Union[Any, List[Any]]], Union[Any, List[Any]]]

    def __init__(
        self,
        map_func: Callable[[Union[Any, List[Any]]], Union[Any, List[Any]]],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.data.map_func = lambda x: map_func(x)

    class InputSchema(Schema):
        values: Union[Any, List[Any]]

    class ResponseSchema(Schema):
        values: Union[Any, List[Any]]

    def execute(self, input: InputSchema) -> ResponseSchema:
        try:
            values = input.values
            if len(values) == 1:
                values = values[0]

            output = self.data.map_func(values)
            if isinstance(output, Schema):
                self.OutputSchema = self.ResponseSchema = output.__class__  # type: ignore
                return output  # type: ignore

            return MapUnit.ResponseSchema(values=output)
        except Exception as e:
            raise VerdictExecutionTimeError(
                f"Failed to execute MapUnit: {e} on {input}"
            ) from e


class FieldMapUnit(MapUnit):
    fields: List[str]

    def __init__(
        self,
        map_func: Callable[[Union[Any, List[Any]]], Union[Any, List[Any]]],
        fields: Union[str, List[str]],
        **kwargs,
    ):
        super().__init__(map_func, **kwargs)
        self.fields = fields if isinstance(fields, list) else [fields]

    def execute(self, input: MapUnit.InputSchema) -> MapUnit.ResponseSchema:
        values = input.values

        if len(self.fields) == 0 and len(values) > 0:
            self.fields = list(values[0].model_fields.keys())

        assert all(field in values[0].model_fields for field in self.fields), (
            f"Fields {self.fields} not a subset of input {input.values}"
        )
        return Schema.of(
            **{  # type: ignore
                field: self.data.map_func(list(map(attrgetter(field), values)))
                for field in self.fields
            }
        )

    @staticmethod
    def from_fn(
        fn: Callable[[List[Any]], Any], name: str
    ) -> Callable[[Union[str, List[str]]], "FieldMapUnit"]:
        return lambda fields=[]: FieldMapUnit(fn, fields, name=name)


class MeanPoolUnit(FieldMapUnit):
    def __init__(self, fields: Union[str, List[str]] = []):
        super().__init__(statistics.mean, fields, name="MeanPool")


class MaxPoolUnit(FieldMapUnit):
    def __init__(self, fields: Union[str, List[str]] = []):
        super().__init__(statistics.mode, fields, name="MaxPool")


class MeanVariancePoolUnit(FieldMapUnit):
    def __init__(self, fields: Union[str, List[str]] = []):
        super().__init__(
            lambda x: Schema.inline(mean=float, variance=float)(  # type: ignore
                mean=statistics.mean(x),
                variance=statistics.variance(x) if len(x) > 1 else 0.0,
            ),
            fields,
            name="MeanVariancePool",
        )


__all__ = [
    "MapUnit",
    "MeanPoolUnit",
    "MeanVariancePoolUnit",
    "MaxPoolUnit",
]
