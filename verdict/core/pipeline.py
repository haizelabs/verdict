from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Dict, List, Tuple, Union

import rich.console
import rich.layout
import rich.live
import rich.panel
import rich.tree
from PIL import Image
from typing_extensions import Self

from verdict.core.executor import GraphExecutor
from verdict.core.primitive import Block, Layer, MaterializationContext, Unit
from verdict.core.visualization import StreamingLayoutManager
from verdict.dataset import DatasetWrapper
from verdict.model import ModelSelectionPolicy
from verdict.schema import Schema
from verdict.util.exceptions import VerdictDeclarationTimeError
from verdict.util.log import init_logger, logger
from verdict.util.misc import keyboard_interrupt_safe


class Pipeline:
    name: str
    block: Block

    executor: GraphExecutor

    def __init__(self, name: str='Pipeline') -> None:
        super().__init__()
        self.name = name
        self.block = Block()

    def copy(self) -> "Pipeline":
        pipeline = Pipeline(self.name)
        pipeline.block = self.block.copy()
        return pipeline

    def __rshift__(self, other: Union[Unit, Layer, "Block"]) -> Self:
        self.block >>= other
        return self

    def via(self, policy_or_name: Union[ModelSelectionPolicy, str], retries: int=1, **inference_parameters) -> Self:
        self.block.via(policy_or_name, retries, **inference_parameters)
        return self

    def collect_outputs(self, executor: GraphExecutor, block_instance: Block) -> Tuple[Dict[str, Schema], List[str]]:
        leaf_node_prefixes: List[str] = []
        outputs: Dict[str, Schema] = {}

        for node in block_instance.nodes:
            try:
                if node not in executor.outputs:
                    logger.debug(f"Node {node} has no output!")
                    continue

                if not isinstance(executor.outputs[node], Schema): # type: ignore
                    logger.debug(f"Node {node} with output {executor.outputs[node]} is not a Schema") # type: ignore

                for key, value in executor.outputs[node].model_dump().items(): # type: ignore
                    outputs[(column_name := f"{self.name}_{'.'.join(node.prefix)}_{key}")] = value # type: ignore
                    if node in block_instance.leaf_nodes:
                        leaf_node_prefixes.append(column_name)
            except Exception as e:
                raise VerdictDeclarationTimeError(f"Error collecting outputs for node {node} with outputs {executor.outputs[node]}") from e # type: ignore

        return outputs, sorted(list(leaf_node_prefixes))

    @keyboard_interrupt_safe
    def run(
        self,
        input_data: Schema=Schema.empty(),
        max_workers: int=128,
        display: bool=False,
        graceful: bool=False
    ) -> Tuple[Dict[str, Schema], List[str]]:
        self.block = self.block.copy()

        init_logger(self.name)
        logger.info(f"Starting pipeline {self.name}")
        self.executor = GraphExecutor(max_workers=max_workers)

        with (rich.live.Live(auto_refresh=True) if display else nullcontext()) as live: # type: ignore
            context = MaterializationContext(n_instances=1)
            if display:
                context.parent_branch = rich.tree.Tree(self.name)
                context.streaming_layout_manager = StreamingLayoutManager(rich.layout.Layout())

                layout = rich.layout.Layout()
                layout.split_row(
                    rich.layout.Layout(rich.panel.Panel(context.parent_branch, title="Execution Tree"), name="execution"),
                    rich.layout.Layout(rich.panel.Panel(context.streaming_layout_manager.layout, title="Streaming"), name="streaming")
                )

                live.update(layout) # type: ignore

            block_instance, _ = self.block._materialize(context.copy())
            block_instance.source_input = input_data
            block_instance.executor = self.executor

            self.executor.submit(block_instance.root_nodes, input_data) # type: ignore
            self.executor.wait_for_completion(graceful=graceful)

        logger.info(f"Pipeline {self.name} completed")
        return self.collect_outputs(self.executor, block_instance)

    @keyboard_interrupt_safe
    def run_from_dataset(self,
            dataset: DatasetWrapper,
            max_workers: int=128,
            experiment_config=None, # verdict.util.experiment.ExperimentConfig
            display: bool=False,
            graceful: bool=False
        ) -> Tuple["pd.DataFrame", List[str]]: # type: ignore
        self.block = self.block.copy()

        init_logger(self.name)
        logger.info(f"Running pipeline {self.name} on dataset (len={len(dataset)})")
        self.executor = GraphExecutor(max_workers=max_workers)

        dataset_df = dataset.samples.copy()

        with (rich.live.Live(auto_refresh=True) if display else nullcontext()) as live: # type: ignore
            block_instances: Dict[str, Block] = {}

            context = MaterializationContext(n_instances=len(dataset))
            if display:
                context.parent_branch = rich.tree.Tree(self.name)
                context.streaming_layout_manager = StreamingLayoutManager(rich.layout.Layout())

                execution_layout = rich.layout.Layout(name="execution")
                execution_tree_layout = rich.layout.Layout(rich.panel.Panel(context.parent_branch, title="Execution Tree"), ratio=1, name="execution")
                if experiment_config:
                    from verdict.util.experiment import get_experiment_layout
                    execution_layout.split_column(
                        get_experiment_layout(dataset_df, experiment_config),
                        execution_tree_layout
                    )
                else:
                    execution_layout.add_split(execution_tree_layout)

                layout = rich.layout.Layout()
                layout.split_row(
                    execution_layout,
                    rich.layout.Layout(rich.panel.Panel(context.streaming_layout_manager.layout, title="Streaming"), name="streaming")
                )

                live.update(layout) # type: ignore

            prototype, _ = self.block._materialize(context)

            for idx, (row, input_data) in enumerate(dataset):
                block_instance = block_instances[row['hash(row)']] = prototype.clone()
                block_instance.source_input = input_data
                block_instance.executor = self.executor

                self.executor.submit(block_instance.root_nodes, input_data, leader=(idx == 0)) # type: ignore

            self.executor.wait_for_completion(graceful=graceful)

            output = []
            leaf_node_prefixes = set()
            for row_id, block_instance in block_instances.items():
                row_output = {"hash(row)": row_id}
                outputs, _leaf_node_prefixes = self.collect_outputs(self.executor, block_instance)

                row_output.update(outputs)
                leaf_node_prefixes.update(_leaf_node_prefixes)

                if len(row_output) > 1:
                    output.append(row_output)

            if len(output) > 0:
                import pandas as pd
                result_df = pd.merge(
                    dataset_df,
                    pd.DataFrame(output),
                    on="hash(row)",
                    how="right"
                ).drop(columns=["hash(row)"])
            else:
                result_df = dataset_df

            if display and experiment_config:
                from verdict.util.experiment import get_experiment_layout
                execution_layout["experiment"].update(get_experiment_layout(result_df, experiment_config))
                live.refresh() # type: ignore

            return result_df, sorted(list(leaf_node_prefixes))

    @keyboard_interrupt_safe
    def run_from_list(
        self,
        dataset: List[Schema],
        max_workers: int = 128,
        experiment_config=None, # verdict.util.experiment.ExperimentConfig
        display: bool = False,
        graceful: bool = False,
    ) -> Tuple[Dict[str, Schema], List[str]]:
        from datasets import Dataset  # type: ignore[import-untyped]
        vedict_dataset = DatasetWrapper(
            Dataset.from_list([data.model_dump() for data in dataset])
        )
        return self.run_from_dataset(
            vedict_dataset, max_workers, experiment_config, display, graceful
        )

    def checkpoint(self, path: Path):
        # TODO
        pass

    def restore(self, path: Path):
        # TODO
        pass

    def plot(self, display=False) -> Image.Image:
        return self.block.materialize().plot(display)
