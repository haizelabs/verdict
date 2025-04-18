from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

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
from verdict.util.tracing import Tracer, NoOpTracer, TracingManager
import uuid



class Pipeline:
    name: str
    block: Block

    executor: GraphExecutor
    tracer: Tracer

    def __init__(self, name: str = 'Pipeline', tracer: Optional[Tracer] = None) -> None:
        """
        Initialize a Pipeline.

        Args:
            name: The name of the pipeline.
            tracer: The tracer or tracing manager to use. If None, uses NoOpTracer.
        """
        super().__init__()
        self.name = name
        self.block = Block()
        if tracer is None:
            self.tracer = TracingManager([NoOpTracer()])
        elif isinstance(tracer, TracingManager):
            self.tracer = tracer
        else:
            self.tracer = TracingManager([tracer])

    def add_tracer(self, tracer: Tracer) -> None:
        """
        Add a tracer to the pipeline's TracingManager.

        Args:
            tracer: The tracer to add.
        """
        if not isinstance(self.tracer, TracingManager):
            # Convert current tracer to a TracingManager
            self.tracer = TracingManager([self.tracer])
        self.tracer.tracers.append(tracer)

    def copy(self) -> "Pipeline":
        pipeline = Pipeline(self.name, tracer=self.tracer)
        pipeline.block = self.block.copy()
        return pipeline

    def __rshift__(self, other: Union[Unit, Layer, "Block"]) -> Self:
        self.block >>= other
        return self

    def via(self, policy_or_name: Union[ModelSelectionPolicy, str], retries: int = 1, **inference_parameters) -> Self:
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
        input_data: Schema = Schema.empty(),
        max_workers: int = 128,
        display: bool = False,
        graceful: bool = False,
        tracer: Optional[Tracer] = None,
    ) -> Tuple[Dict[str, Schema], List[str]]:
        """
        Run the pipeline.

        Args:
            input_data: The input schema.
            max_workers: Number of workers.
            display: Whether to display live output.
            graceful: Whether to shut down gracefully.
            tracer: Optional tracer to override the pipeline's tracer for this run.

        Returns:
            Tuple of outputs and leaf node prefixes.
        """
        self.block = self.block.copy()
        init_logger(self.name)
        logger.info(f"Starting pipeline {self.name}")
        tracer_to_use = tracer or self.tracer
        self.executor = GraphExecutor(max_workers=max_workers, tracer=tracer_to_use)

        trace_id = str(uuid.uuid4())
        call_name = f"{getattr(self, 'name', None) or self.__class__.__name__}"
        with tracer_to_use.start_call(
            name=call_name,
            inputs={
                "input_data": input_data,
                "max_workers": max_workers,
                "display": display,
                "graceful": graceful,
            },
            trace_id=trace_id,
            parent_id=None,
        ) as call:
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

                self.executor.submit(
                    block_instance.root_nodes,
                    input_data,
                    trace_id=trace_id,
                    parent_id=call.call_id if call is not None else None,
                ) # type: ignore
                self.executor.wait_for_completion(graceful=graceful)

            logger.info(f"Pipeline {self.name} completed")
            outputs = self.collect_outputs(self.executor, block_instance)
            if call is not None:
                call.set_outputs(outputs)
            return outputs

    @keyboard_interrupt_safe
    def run_from_dataset(
        self,
        dataset: DatasetWrapper,
        max_workers: int = 128,
        experiment_config=None,
        display: bool = False,
        graceful: bool = False,
        tracer: Optional[Tracer] = None,
    ) -> Tuple["pd.DataFrame", List[str]]:
        """
        Run the pipeline on a dataset.

        Args:
            dataset: The dataset wrapper.
            max_workers: Number of workers.
            experiment_config: Experiment config.
            display: Whether to display live output.
            graceful: Whether to shut down gracefully.
            tracer: Optional tracer to override the pipeline's tracer for this run.

        Returns:
            Tuple of DataFrame and leaf node prefixes.
        """
        self.block = self.block.copy()
        init_logger(self.name)
        logger.info(f"Running pipeline {self.name} on dataset (len={len(dataset)})")
        tracer_to_use = tracer or self.tracer
        self.executor = GraphExecutor(max_workers=max_workers, tracer=tracer_to_use)

        dataset_df = dataset.samples.copy()
        trace_id = str(uuid.uuid4())
        call_name = f"{getattr(self, 'name', None) or self.__class__.__name__}"
        with tracer_to_use.start_call(
            name=call_name,
            inputs={
                "dataset": dataset_df,
                "max_workers": max_workers,
                "experiment_config": experiment_config,
                "display": display,
                "graceful": graceful,
            },
            trace_id=trace_id,
            parent_id=None,
        ) as call:
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

                    self.executor.submit(
                        block_instance.root_nodes,
                        input_data,
                        trace_id=trace_id,
                        parent_id=call.call_id if call is not None else None,
                    ) # type: ignore

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
        experiment_config=None,
        display: bool = False,
        graceful: bool = False,
        tracer: Optional[Tracer] = None,
    ) -> Tuple[Dict[str, Schema], List[str]]:
        """
        Run the pipeline on a list of Schemas.

        Args:
            dataset: List of input schemas.
            max_workers: Number of workers.
            experiment_config: Experiment config.
            display: Whether to display live output.
            graceful: Whether to shut down gracefully.
            tracer: Optional tracer to override the pipeline's tracer for this run.

        Returns:
            Tuple of outputs and leaf node prefixes.
        """
        from datasets import Dataset  # type: ignore[import-untyped]
        vedict_dataset = DatasetWrapper(
            Dataset.from_list([data.model_dump() for data in dataset])
        )
        return self.run_from_dataset(
            vedict_dataset, max_workers, experiment_config, display, graceful, tracer=tracer
        )

    def checkpoint(self, path: Path):
        # TODO
        pass

    def restore(self, path: Path):
        # TODO
        pass

    def plot(self, display=False) -> Image.Image:
        return self.block.materialize().plot(display)
