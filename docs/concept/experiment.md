---
label: "Experiment"
icon: beaker
---

In the LLM-as-a-judge literature, there are a number of agreement correlation metrics[^1] that are commonly reported. We provide a `ExperimentConfig` class to help you specify the prediction/ground-truth columns and pivot columns to make computing these metrics easy.

## Usage
```python
from verdict.util.experiment import ExperimentConfig

experiment_config = ExperimentConfig(
    prediction_cols=["Hierarchical_root.block.unit[Map MaxPoolUnit].score"],
    ground_truth_cols=["score"],
    pivot_columns=["language"]
)
```

You can pass this config directly to [`Pipeline.run_from_dataset`](./pipeline.md#usage) and view the results in the console output as they become available or use `display_stats` after execution.
||| Display
~~~python
result_df, leaf_node_prefixes = pipeline.run_from_dataset(
    dataset['eval'],
    experiment_config=experiment_config,
    display=True
)
~~~
||| After Execution
~~~python
from verdict.util.experiment import display_stats, compute_stats_table

# display stats in console
display_stats(result_df, experiment_config)

# return a pandas DataFrame
stats_df = compute_stats_table(result_df, experiment_config)
~~~
|||

[^1]:
    We support the following metrics:

    {.compact}
    | Metric | Package |
    | ------: | :-------: |
    | Accuracy | - |
    | Cohen's Kappa | `sklearn.metrics` |
    | Kendall's Tau | `scipy.stats` |
    | Spearman Rank Correlation | `scipy.stats` |
    | Krippendorff's Alpha | [`krippendorff`](https://pypi.org/project/krippendorff/) |
