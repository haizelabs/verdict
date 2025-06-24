"""
Rater agreement metrics
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Union

import rich.box
import rich.console
import rich.layout
import rich.spinner
import rich.table


@dataclass
class Result:
    INVALID_RESULT_SENTINEL = float("nan")

    value: float
    percentage: bool = False

    def __format__(self, format_spec: str) -> str:
        if math.isnan(self.value):
            return "—"
        if "%" in format_spec:
            format_spec = format_spec.replace("%", "")
            return f"{self.value * 100:{format_spec}}%"
        return self.value.__format__(format_spec)

    def __str__(self) -> str:
        return f"{self:.2f%}" if self.percentage else f"{self:.2f}"

    def __rich__(self) -> str:
        return str(self)


spinner = rich.spinner.Spinner("simpleDotsScrolling")


def metric(
    percentage: bool = False,
) -> Callable[[Callable[..., Result]], Callable[..., Result]]:
    def decorator(func: Callable[..., Result]) -> Callable[..., Result]:
        def wrapper(*args, **kwargs) -> Result:
            df, ground_truth_col, prediction_col = args
            if prediction_col not in df.columns:
                return spinner

            try:
                return Result(value=func(*args, **kwargs), percentage=percentage)
            except Exception:
                return Result(
                    value=Result.INVALID_RESULT_SENTINEL, percentage=percentage
                )

        return wrapper

    return decorator


@metric(percentage=True)
def accuracy(df: "pd.DataFrame", ground_truth_col: str, prediction_col: str) -> Result:  # type: ignore
    return (df[ground_truth_col] == df[prediction_col]).mean()  # type: ignore


@metric()
def kappa(df: "pd.DataFrame", ground_truth_col: str, prediction_col: str) -> Result:  # type: ignore
    from sklearn.metrics import cohen_kappa_score  # type: ignore[import-untyped]

    return cohen_kappa_score(df[ground_truth_col], df[prediction_col])


@metric()
def kendall_tau(
    df: "pd.DataFrame", ground_truth_col: str, prediction_col: str
) -> Result:  # type: ignore
    from scipy.stats import kendalltau  # type: ignore[import-untyped]

    return kendalltau(df[ground_truth_col], df[prediction_col]).statistic


@metric()
def spearman_rho(
    df: "pd.DataFrame", ground_truth_col: str, prediction_col: str
) -> Result:  # type: ignore
    from scipy.stats import spearmanr  # type: ignore[import-untyped]

    return spearmanr(df[ground_truth_col], df[prediction_col]).statistic


@metric()
def krippendorff_alpha(
    df: "pd.DataFrame", ground_truth_col: str, prediction_col: str
) -> Result:  # type: ignore
    import pandas as pd

    data_interval = (
        pd.concat([df[ground_truth_col], df[prediction_col]], axis=1).to_numpy().T
    )

    import krippendorff  # type: ignore[import-untyped]

    return krippendorff.alpha(
        reliability_data=data_interval, level_of_measurement="interval"
    )


@dataclass
class ExperimentConfig:
    ground_truth_cols: List[str]
    prediction_cols: List[str]

    pivot_cols: Optional[List[str]] = None


def compute_stats_table(
    df: "pd.DataFrame", experiment_config: ExperimentConfig
) -> list:  # type: ignore
    """
    Compute the raw data for the stats table.

    Returns a list of rows, where each row is a tuple containing the data for a row in the table.
    """
    rows = []

    def _get_row(
        pivot_column: Optional[str],
        pivot_value: Optional[str],
        _df: "pd.DataFrame",
        ground_truth_col: str,
        prediction_col: str,
    ) -> tuple[str, str, str, str, str, Result, Result, Result, Result]:
        return (
            f"{pivot_column}={pivot_value}" if pivot_column and pivot_value else "—",
            str(len(_df)),
            ground_truth_col,
            prediction_col,
            "",
            accuracy(_df, ground_truth_col, prediction_col),
            kappa(_df, ground_truth_col, prediction_col),
            kendall_tau(_df, ground_truth_col, prediction_col),
            spearman_rho(_df, ground_truth_col, prediction_col),
        )

    for ground_truth_col, prediction_col in zip(
        experiment_config.ground_truth_cols, experiment_config.prediction_cols
    ):
        if experiment_config.pivot_cols:
            rows.append(_get_row("*", "*", df, ground_truth_col, prediction_col))
            for pivot_column in experiment_config.pivot_cols:
                for pivot_value, _df in df.groupby(pivot_column):
                    rows.append(
                        _get_row(
                            pivot_column,
                            str(pivot_value),
                            _df,
                            ground_truth_col,
                            prediction_col,
                        )
                    )
        else:
            rows.append(_get_row(None, None, df, ground_truth_col, prediction_col)[2:])

    return rows


def format_stats_table(
    rows: list, experiment_config: ExperimentConfig
) -> rich.table.Table:
    """
    Format the stats table using Rich from a list of rows.

    Returns a rich.table.Table object.
    """
    table = rich.table.Table(box=rich.box.HORIZONTALS, expand=True)

    if experiment_config.pivot_cols:
        table.add_column("Pivot", justify="left", no_wrap=True)
        table.add_column("N", justify="center", no_wrap=True)
    table.add_column("Ground Truth", justify="right", no_wrap=True)
    table.add_column("Prediction", justify="left", no_wrap=True)
    table.add_column()
    table.add_column("Acc.", justify="center")
    table.add_column("Cohen (κ)", justify="center")
    table.add_column("Kendall (τ)", justify="center")
    table.add_column("Spearman (ρ)", justify="center")

    for row in rows:
        table.add_row(*row)

    return table


def stats(
    df: "pd.DataFrame",
    experiment_config: ExperimentConfig,  # type: ignore
) -> tuple[rich.table.Table, list[tuple[Union[str, int]]]]:
    """
    Compute and format the stats table.

    Returns a rich.table.Table object.
    """
    rows = compute_stats_table(df, experiment_config)
    return format_stats_table(rows, experiment_config), rows


def get_experiment_layout(
    df: "pd.DataFrame", experiment_config: ExperimentConfig
) -> rich.layout.Layout:  # type: ignore
    len(
        df[experiment_config.pivot_cols].drop_duplicates()
    ) if experiment_config.pivot_cols else 1

    formatted_table, _ = stats(df, experiment_config)

    console = rich.console.Console()
    console = rich.console.Console(
        width=(console.size.width // 2) - 6,
    )
    with console.capture() as capture:
        console.print(formatted_table)

    height_requested = len(capture.get().split("\n"))

    return rich.layout.Layout(
        rich.panel.Panel(formatted_table, title=f"Agreement (N={len(df)} samples)"),
        size=height_requested,
        name="experiment",
    )


def display_stats(
    df: "pd.DataFrame",
    experiment_config: ExperimentConfig,  # type: ignore
) -> list[tuple[Union[str, int]]]:
    console = rich.console.Console()
    fmt_table, raw_table = stats(df, experiment_config)
    console.print(fmt_table)
    return raw_table
