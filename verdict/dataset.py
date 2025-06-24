from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import dill  # type: ignore[import-untyped]
from typing_extensions import Self

from verdict.schema import Schema
from verdict.util.exceptions import ConfigurationError

InputFn = Callable[[Dict[str, Any]], Schema]


class DatasetWrapper(Iterator[Tuple[Dict[str, Any], Schema]]):
    dataset: "pd.DataFrame"  # type: ignore
    samples: "pd.DataFrame"  # type: ignore

    max_samples: Optional[int]

    input_fn: InputFn

    _iter: Optional[Iterator[Tuple[Dict[str, Any], Schema]]] = None
    _count: int = 0

    def __init__(
        self,
        dataset: "Dataset",  # type: ignore
        input_fn: Optional[InputFn] = None,
        columns: Optional[List[str]] = None,
        max_samples: Optional[int] = None,
    ):
        import pandas as pd

        self.dataset = pd.DataFrame(dataset)
        self.dataset["hash(row)"] = self.dataset.apply(
            lambda row: hash(str(row)), axis=1
        )
        self.max_samples = int(max_samples) if max_samples else None
        self.samples = (
            self.dataset.sample(n=self.max_samples)
            if self.max_samples
            else self.dataset
        )

        if input_fn is not None and columns is not None:
            raise ConfigurationError("Cannot specify both input_fn and columns")

        columns = columns or (self.dataset.columns.difference(["hash(row)"]).tolist())
        self.input_fn = input_fn or (
            lambda row: Schema.of(**{k: v for k, v in row.items() if k in columns})
        )

    def __iter__(self) -> Self:
        samples = []
        for idx, row in self.samples.iterrows():
            samples.append((_row := row.to_dict(), sample := self.input_fn(_row)))
            for key, value in sample.model_dump().items():
                column = f"!{key}"
                if column not in self.samples.columns:
                    self.samples[column] = None

                self.samples.at[idx, column] = value

        self._iter = iter(samples)
        self._count = 0
        return self

    def __next__(self) -> Tuple[Dict[str, Any], Schema]:
        if self._iter is None:
            raise StopIteration

        if self.max_samples and self._count >= self.max_samples:
            self._iter = None
            raise StopIteration

        self._count += 1
        return next(self._iter)

    def __len__(self) -> int:
        return len(self.samples)

    def save(self, path: Path) -> None:
        with open(path, "wb") as f:
            dill.dump(self, f)

    @staticmethod
    def load(path: Path) -> "DatasetWrapper":
        with open(path, "rb") as f:
            return dill.load(f)

    @staticmethod
    def from_hf(
        dataset: Dict[str, "Dataset"],  # type: ignore
        input_fn: Optional[InputFn] = None,
        columns: Optional[List[str]] = None,
        max_samples: Optional[int] = None,
        expand: bool = False,
    ) -> Dict[str, "DatasetWrapper"]:
        from datasets import Dataset  # type: ignore[import-untyped]

        def expand_dataset(dataset: Dataset) -> Dataset:
            expanded_data = []
            for row in dataset:
                max_len = max(
                    len(value) if isinstance(value, list) else 1
                    for value in row.values()
                )
                for i in range(max_len):
                    new_row = {
                        key: value[i]
                        if isinstance(value, list) and i < len(value)
                        else value
                        for key, value in row.items()
                    }

                    for key, value in new_row.items():
                        if isinstance(value, list):
                            new_row[key] = str(value)
                    expanded_data.append(new_row)

            expanded_dict = {
                key: [row[key] for row in expanded_data] for key in expanded_data[0]
            }
            return Dataset.from_dict(expanded_dict)

        return {
            k: DatasetWrapper(
                expand_dataset(v) if expand else v, input_fn, columns, max_samples
            )
            for k, v in dataset.items()
        }

    @staticmethod
    def from_pandas(
        df: "pd.DataFrame",  # type: ignore
        input_fn: Optional[InputFn] = None,
        columns: Optional[List[str]] = None,
        split_column: Optional[str] = None,
        max_samples: Optional[int] = None,
    ):
        from datasets import Dataset  # type: ignore[import-untyped]

        if split_column is not None:
            return DatasetWrapper.from_hf(
                {
                    str(split): Dataset.from_pandas(_df)
                    for split, _df in df.groupby(split_column)
                },
                input_fn,
                columns,
                max_samples,
            )

        return DatasetWrapper.from_hf(
            {"all": Dataset.from_pandas(df)}, input_fn, columns, max_samples
        )
