import copy
import operator
import time
from abc import ABCMeta
from dataclasses import dataclass, field
from enum import Enum
from itertools import cycle
from typing import (
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    final,
)

import numpy as np
import rich.align
import rich.console
import rich.layout
import rich.live
import rich.padding
import rich.panel
import rich.progress
import rich.spinner
import rich.table
import rich.text
import rich.tree
from loguru._logger import Logger
from typing_extensions import Self

import verdict.config as config
from verdict.core.executor import ExecutionState, Graph, Node, Task
from verdict.core.synchronization import SynchronizationState, UserState
from verdict.core.visualization import BranchManager, StreamingLayoutManager
from verdict.extractor import Extractor
from verdict.model import ModelConfigurable, ModelSelectionPolicy
from verdict.prompt import Promptable, PromptMessage
from verdict.schema import Schema
from verdict.util.exceptions import (
    ConfigurationError,
    PostProcessError,
    PostValidationError,
    PropagateError,
    VerdictDeclarationTimeError,
    VerdictExecutionTimeError,
)
from verdict.util.log import logger as base_logger
from verdict.util.misc import DisableLogger, shorten_string
from verdict.util.tracing import ExecutionContext


class Previous:
    def __init__(self, dependencies: Set["Unit"]) -> None:
        self.dependencies = sorted(
            list(dependencies), key=lambda node: getattr(node, "_ordering_timestamp", 0)
        )

    def __getattr__(self, key: str) -> Union[Schema, List[Schema]]:
        # e.g., previous.score -> (previous Judge unit dependency).output.score
        if len(self.dependencies) == 1 and hasattr(
            (unit := self.dependencies[0]).output, key
        ):
            return getattr(unit.output, key)

        # e.g., previous.judge -> (previous Judge unit dependency).output
        if (shortname := key.split(".")[0].lower()) in Unit._registry:
            _type = Unit._registry[shortname]
            matches = list(
                filter(
                    lambda node: isinstance(node, _type)
                    or node.__class__.__name__ == _type.__name__,
                    self.dependencies,
                )
            )

            # single dependency
            if len(matches) == 1:
                return matches[0].output

            # multiple dependencies
            return list(map(lambda unit: unit.output, matches))
        else:
            raise ConfigurationError(f"Previous {key.lower()} ({key}) not found")


@dataclass
class Propagator:
    fn: Callable[["Unit", Previous, Schema, Schema], Schema]

    @staticmethod
    def from_fn(
        fn: Callable[["Unit", Previous, Schema, Schema], Schema],
    ) -> "Propagator":
        return Propagator(fn=fn)

    def __call__(
        self, unit: "Unit", previous: Previous, source: Schema, output: Schema
    ) -> Schema:
        if not isinstance(previous, Previous):
            previous = Previous(previous)  # type: ignore

        return self.fn(unit, previous, source, output)

    def __copy__(self) -> "Propagator":
        return Propagator(fn=self.fn)

    @staticmethod
    def default() -> "Propagator":
        return Propagator.from_fn(lambda unit, previous, source, output: output)


class UnitRegistry(ABCMeta):
    _registry: Dict[str, Type["Unit"]] = {}

    def __new__(mcls, name, bases, namespace, **kwargs) -> Type["Unit"]:
        klass = super().__new__(mcls, name, bases, namespace, **kwargs)

        if name != "Unit":
            if "InputSchema" not in namespace and not any(
                hasattr(base, "InputSchema") for base in bases
            ):
                klass.InputSchema = Schema.inline()

            if "ResponseSchema" not in namespace and not any(
                hasattr(base, "ResponseSchema") for base in bases
            ):
                raise ConfigurationError(
                    f"Custom Unit '{name}' must define a 'ResponseSchema' class."
                )

            if "OutputSchema" not in namespace and not any(
                hasattr(base, "OutputSchema") for base in bases
            ):
                klass.OutputSchema = klass.ResponseSchema

        if name and not name.startswith("_") and name != "Unit":
            shortname = name.replace("Unit", "").lower()
            if shortname in mcls._registry:
                base_logger.warning(
                    f"Unit '{name}' (shortname='{shortname}') name collision in UnitRegistry. Replacing existing unit."
                )
            mcls._registry[shortname] = klass

        return klass


@dataclass
class MaterializationContext:
    root_block: Optional["Block"] = None
    prefix: List[str] = field(default_factory=lambda: ["root"])

    parent_branch: Optional[rich.tree.Tree] = None
    streaming_layout_manager: Optional[StreamingLayoutManager] = None

    n_instances: int = 1

    def copy(self) -> "MaterializationContext":
        return MaterializationContext(
            root_block=self.root_block,
            prefix=self.prefix.copy(),
            parent_branch=self.parent_branch,
            streaming_layout_manager=self.streaming_layout_manager,
            n_instances=self.n_instances,
        )

    def add_prefix(self, prefix: str) -> "MaterializationContext":
        self.prefix.append(prefix)
        return self


InputSchemaT = TypeVar("InputSchemaT", bound=Schema)
ResponseSchemaT = TypeVar("ResponseSchemaT", bound=Schema)
OutputSchemaT = TypeVar("OutputSchemaT", bound=Schema)


class DataFlowSchema(Generic[InputSchemaT, ResponseSchemaT, OutputSchemaT]):
    InputSchema: InputSchemaT
    ResponseSchema: ResponseSchemaT
    OutputSchema: OutputSchemaT


class Unit(
    Node,
    Task,
    ModelConfigurable,
    Promptable,
    DataFlowSchema[InputSchemaT, ResponseSchemaT, OutputSchemaT],
    metaclass=UnitRegistry,
):
    lightweight: bool = False

    shared: SynchronizationState  # fresh on init/copy, shared on clone
    data: UserState  # fresh on init, copied on a copy/clone
    model_selection_policy: Optional["ModelSelectionPolicy"] = None

    @property
    def _char(self) -> str:
        return "Unit"

    @final
    @property
    def char(self) -> str:
        model_selection_policy = (
            self.model_selection_policy or config.DEFAULT_MODEL_SELECTION_POLICY
        )
        _char = f"{self._char}"
        if not self.lightweight:
            _char += f" via {self.extractor.format().format(model_name=model_selection_policy.char)}"
        return _char

    def __init__(self, **kwargs):
        Node.__init__(self, **kwargs)
        Task.__init__(self)

        self._ordering_timestamp = time.perf_counter()
        self.shared = SynchronizationState()
        self.data = UserState()

        self._propagator = Propagator.default()

    def copy(self) -> Self:
        new = copy.copy(self)  # shallow (reference) copy

        new._ordering_timestamp = time.perf_counter()
        new.shared = SynchronizationState()
        new.data = (
            self.data.copy()
        )  # 2-level shallow copy (container reference + all values are copy.copy'd)

        return new

    def clone(self) -> Self:
        new = self.copy()
        new.shared = self.shared.add(new)

        return new

    @property
    def description(self) -> Optional[str]:
        return None

    def _materialize(
        self, context: MaterializationContext
    ) -> Tuple[Self, MaterializationContext]:
        context.add_prefix(f"unit[{self._char}{f' {self.name}' if self.name else ''}]")
        self.prefix = context.prefix

        with self.shared.lock:
            if self.shared.branch is None:
                self.shared.branch = BranchManager(
                    self.shared.branch_lock,
                    context.parent_branch,
                    context.n_instances,
                    self.should_pin_output,
                )
        self.shared.branch.update(ExecutionState.WAITING_FOR_DEPENDENCIES, self)

        self.streaming_layout_manager = context.streaming_layout_manager
        if context.root_block is not None:
            context.root_block.add(self.clear_dependencies())
        return self, context

    def __rshift__(self, other: Union["Unit", "Layer", "Block"]):  # type: ignore
        return (Block() >> self) >> other

    def link(self, other: Union["Unit", Graph["Unit"]]) -> None:  # type: ignore
        if self is other:
            return

        if isinstance(other, Unit):
            self.graph.setup_link(self, other)
            return

        with other.freeze():
            for node in other.root_nodes:
                self.link(node)

    def populate_prompt_message(self, input: Schema, logger: Logger) -> PromptMessage:
        return self._prompt.format(
            input_schema=input,
            unit=self,
            previous=Previous(self.dependencies),  # type: ignore
            source=self.source_input,
            logger=logger,
        )

    def execute(
        self, input: InputSchemaT, execution_context: Optional[ExecutionContext] = None
    ) -> OutputSchemaT:
        """
        Execute the unit with tracing.

        Args:
            input: The input schema.
            execution_context: The execution context for this execution (tracing, IDs, etc).

        Returns:
            The output schema.
        """
        if execution_context is None:
            execution_context = ExecutionContext()
        call_name = (
            getattr(self, "_char", None)
            or getattr(self, "char", None)
            or self.__class__.__name__
        )
        with execution_context.trace_call(
            name=call_name,
            inputs={"input": input, "unit": self},
        ) as call:
            logger = base_logger.bind(
                thread_id=self.thread_id, unit=".".join(self.prefix)
            )
            logger.info("Started Unit.execute()")

            if self.model_selection_policy is None:
                self.model_selection_policy = config.DEFAULT_MODEL_SELECTION_POLICY
                logger.debug(
                    f"Using default model selection policy: {self.model_selection_policy}"
                )

            if self.should_stream_output and self.streaming_layout_manager:
                streaming_layout = self.streaming_layout_manager.add(self)

            exceptions: List[Exception] = []
            for attempt_num, client in enumerate(
                self.model_selection_policy.get_clients()
            ):
                logger.info(
                    f"Starting attempt {attempt_num + 1} of {len(self.model_selection_policy)}"
                )

                try:
                    logger.debug(f"Received input: {input.escape()}")

                    conformed_input: Schema = input
                    if not self.InputSchema.is_empty():
                        conformed_input = input.conform(self.InputSchema, logger)
                        logger.debug(
                            f"Conformed input to {self.InputSchema}: {conformed_input.escape()}"
                        )

                    if not hasattr(self, "_prompt"):
                        raise ConfigurationError("Unit must define a prompt.")

                    prompt_message: PromptMessage = self.populate_prompt_message(
                        conformed_input, logger
                    )
                    logger.debug(f"Populated system prompt: {prompt_message.system}")
                    logger.debug(
                        f"Populated user prompt: {shorten_string(prompt_message.user)}"
                    )

                    in_tokens = len(client.encode(prompt_message.user))
                    out_tokens_estimate = np.mean(
                        self.shared.output_tokens or [0.0]
                    ).item()
                    ready = client.model.rate_limit.acquire(
                        {"requests": 1, "tokens": int(in_tokens + out_tokens_estimate)}
                    )
                    logger.debug(
                        f"Prepared in_tokens={in_tokens}, estimated out_tokens={out_tokens_estimate}"
                    )
                    if waiting := not ready.is_set():
                        logger.debug("Rate limit reached. Waiting...")
                    ready.wait()
                    if waiting:
                        logger.debug("Below rate limit again. Resuming...")

                    extractor: Extractor = (
                        self.extractor()
                        if isinstance(self.extractor, type)
                        else self.extractor
                    )
                    extractor.inject(unit=self)
                    logger.debug(f"Using extractor: {extractor}")

                    # exit early right before the inference call
                    if self.executor.is_complete.is_set():
                        logger.error(
                            "Exiting early since executor has been marked is_complete"
                        )
                        return  # type: ignore

                    try:
                        with DisableLogger("LiteLLM"):
                            response_stream, usage = extractor.extract(
                                client, prompt_message, logger
                            )
                            logger.info("Inference call succeeded")
                    except Exception as e:
                        logger.error(f"Inference call failed: {e}")
                        raise VerdictExecutionTimeError() from e

                    if isinstance(response_stream, Iterator):
                        logger.debug("Received streaming response")
                        for response in response_stream:
                            if (
                                self.should_stream_output
                                and self.streaming_layout_manager
                                and streaming_layout
                            ):
                                streaming_layout.update(response)
                    else:
                        response = response_stream
                    logger.debug(f"Received response: {response.escape()}")

                    out_tokens = usage.out_tokens
                    if usage.is_unknown() or usage.out_tokens == -1:
                        out_tokens = len(
                            client.encode(
                                str(response.model_dump())
                                if isinstance(response, Schema)
                                else response
                            )
                        )
                    self.shared.output_tokens.append(out_tokens)
                    client.model.rate_limit.release(
                        {"tokens": min(int(out_tokens - out_tokens_estimate), 0)}
                    )
                    logger.debug(f"Received out_tokens={out_tokens}")

                    try:
                        self.validate(conformed_input, response)
                    except Exception as e:
                        raise PostValidationError() from e
                    logger.debug("Unit.validate() successful")

                    try:
                        output = self.process(conformed_input, response)
                    except Exception as e:
                        raise PostProcessError() from e
                    logger.debug("Unit.process() successful")

                    try:
                        result = self._propagator(
                            self, Previous(self.dependencies), conformed_input, output
                        )  # type: ignore
                        logger.debug(f"Propagated result: {result}")
                        logger.info("Unit.execute() successful")
                        if call is not None:
                            call.set_outputs(result)
                        return result
                    except Exception as e:
                        raise PropagateError() from e
                except VerdictDeclarationTimeError as e:
                    logger.info("User-code/configuration error detected.")
                    raise e
                except Exception as e:
                    exceptions.append(e)
                    logger.info(f"Retrying after exception encountered: {e}")

            raise VerdictExecutionTimeError(
                f"Model Selection Policy {self.model_selection_policy} exhausted"
            ) from exceptions[-1]

    def validate(self, input: InputSchemaT, response: ResponseSchemaT) -> None:
        pass

    def process(
        self, input: InputSchemaT, response: ResponseSchemaT
    ) -> Union[OutputSchemaT, ResponseSchemaT]:
        return response


class LinkType:
    class How(Enum):
        @classmethod
        def from_str(cls, s: str) -> Self:
            return cls[s.upper()]

    class Inner(How):
        NONE = 0  #  U   U   U
        CHAIN = 1  #  U - U - U

    class Outer(How):
        DENSE = 0  #  U   U
        #  |\ /|
        #  |/ \|
        #  U   U

        BROADCAST = 1  #  U   U
        #  |   |
        #  |   |
        #  U   U

        CUMULATIVE = 2  #  U   U
        #  |\  |
        #  |  \|
        #  U   U

        LAST = 3  #  U   U
        #      |
        #      |
        #      U


class Layer(Graph[Node], Node, ModelConfigurable):  # type: ignore
    """
    Ordered list of units.
    """

    order: List[Node]

    how_inner: LinkType.Inner
    how_outer: LinkType.Outer

    root_idx: List[int]
    leaf_idx: List[int]

    @property
    def char(self) -> str:
        return f"Layer({self.how_inner}, {self.how_outer})"

    def __init__(
        self,
        nodes: Union[Node, List[Node]],
        repeat: int = 1,
        inner: Union[str, LinkType.Inner] = LinkType.Inner.NONE,
        outer: Union[str, LinkType.Outer] = LinkType.Outer.DENSE,
    ):
        Graph.__init__(self, node_type=(Node, List[Node]))  # type: ignore
        Node.__init__(self)

        if isinstance(nodes, Node):
            nodes = [nodes]

        self.order = []
        for i, _node in enumerate(cycle(nodes)):
            node = _node.copy()
            if hasattr(node, "idx"):
                node.idx(i + 1)

            node._ordering_timestamp = time.perf_counter()
            node.parent = self
            self.add(node)
            self.order.append(node)
            if len(self.order) >= len(nodes) * repeat:
                break

        self.how_inner = (
            LinkType.Inner.from_str(inner) if isinstance(inner, str) else inner
        )
        self.how_outer = (
            LinkType.Outer.from_str(outer) if isinstance(outer, str) else outer
        )

        self.root_idx = list(range(len(self.order)))
        self.leaf_idx = list(range(len(self.order)))

        if self.how_outer == LinkType.Outer.LAST:
            self.with_leaf(-1)

    def sort(self) -> List[Node]:
        return self.order

    def copy(self) -> Self:
        copy = type(self)(
            list(map(lambda node: node.copy(), self.order)),
            inner=self.how_inner,
            outer=self.how_outer,
        )
        copy.leaf_idx = self.leaf_idx
        copy.root_idx = self.root_idx
        return copy

    def clone(self) -> Self:
        clone = type(self)(
            list(map(lambda node: node.clone(), self.order)),
            inner=self.how_inner,
            outer=self.how_outer,
        )
        clone.leaf_idx = self.leaf_idx
        clone.root_idx = self.root_idx
        return clone

    def _materialize(
        self, context: MaterializationContext
    ) -> Tuple[Self, MaterializationContext]:
        if context.parent_branch:
            context.parent_branch = context.parent_branch.add(self.char)

        order = []
        context = context.copy()

        if self.how_inner == LinkType.Inner.CHAIN:
            with self.freeze_all_nodes():
                for i, node in enumerate(list(self.order)):
                    self.remove(node)

                    with node.freeze(), node.freeze_all_nodes():
                        self.add(
                            materialized := node._materialize(
                                context.copy().add_prefix(f"layer[{i}]")
                            )[0]
                        )

                    order.append(materialized)

                for previous, current in zip(order[:-1], order[1:]):
                    previous >> current

                self.order = order
                return self, context

        for i, node in enumerate(self.order):
            self.remove(node)
            self.add(
                materialized := node._materialize(
                    context.copy().add_prefix(f"layer[{i}]")
                )[0]
            )
            order.append(materialized)
        self.order = order
        return self, context

    def __rshift__(self, other: Union[Unit, "Layer", "Block"]) -> "Block":  # type: ignore
        return (Block() >> self) >> other

    def link(self, other: Union[Unit, "Layer", "Block"]) -> None:  # type: ignore
        if isinstance(other, Layer) and len(self.leaf_nodes) == len(other.root_nodes):
            if self.how_outer == LinkType.Outer.BROADCAST:
                assert len(self.leaf_nodes) == len(other.root_nodes), (
                    "Broadcast link requires equal number of leaf and root nodes"
                )
                with self.freeze(), other.freeze():
                    for a, b in zip(list(self.leaf_nodes), list(other.root_nodes)):
                        a.link(b)
                return
            elif self.how_outer == LinkType.Outer.CUMULATIVE:
                with (
                    self.freeze(),
                    other.freeze(),
                    self.freeze_leaf_nodes(),
                    other.freeze_root_nodes(),
                ):
                    for a_idx, a in enumerate(self.leaf_nodes):
                        for b in other.root_nodes[: a_idx + 1]:
                            a.link(b)
                return

        if isinstance(other, Unit):
            with self.freeze(), other.freeze():
                for node in self.leaf_nodes:
                    node.link(other)
            return

        with (
            self.freeze(),
            other.freeze(),
            self.freeze_leaf_nodes(),
            other.freeze_root_nodes(),
        ):
            for node in other.root_nodes:
                self.link(node)  # type: ignore

    def with_root(self, idx: Union[int, List[int]]) -> "Layer":
        self.root_idx = [idx] if isinstance(idx, int) else idx
        return self

    def with_leaf(self, idx: Union[int, List[int]]) -> "Layer":
        self.leaf_idx = [idx] if isinstance(idx, int) else idx
        return self

    def _idx_to_nodes(self, idx: List[int]) -> List[Node]:
        nodes = operator.itemgetter(*idx)(self.order)
        if not isinstance(nodes, tuple):
            nodes = (nodes,)
        return list(nodes)

    @property
    def root_nodes(self) -> List[Node]:
        return self._idx_to_nodes(self.root_idx)

    @property
    def leaf_nodes(self) -> List[Node]:
        return self._idx_to_nodes(self.leaf_idx)


class Block(Graph[Union[Unit, Layer]], Node, ModelConfigurable):
    use_root: bool = True

    @property
    def char(self) -> str:
        return "Block"

    def __init__(self, name: Optional[str] = None) -> None:
        Node.__init__(self, name)
        Graph.__init__(self, node_type=(Unit, Layer))  # type: ignore

        self.use_root = True

    def __rshift__(self, other: Union[Unit, Layer, "Block"]) -> "Block":  # type: ignore
        other.graph = self

        if isinstance(other, Block):  # merge blocks, update .graph
            with self.freeze(), other.freeze():
                for root in list(other.root_nodes):
                    if len(self.leaf_nodes) == 0:
                        self.add(root)
                    else:
                        for leaf in list(
                            self.root_nodes if self.use_root else self.leaf_nodes
                        ):
                            self.setup_link(leaf, root)
            self.nodes.update(other.nodes)
            return self

        if len(self.nodes) == 0:  # empty block just adds the node
            self.add(other)
            return self.leaf_view()

        with self.freeze():
            for leaf in list(self.root_nodes if self.use_root else self.leaf_nodes):
                self.setup_link(leaf, other)

        return self.leaf_view()

    def leaf_view(self) -> "Block":
        block = self.view()
        block.use_root = False
        return block

    def root_view(self) -> "Block":
        block = self.view()
        block.use_root = True
        return block

    def link(self, other: Union[Unit, Graph["Unit"]]) -> None:  # type: ignore
        with self.freeze():
            for node in list(self.leaf_nodes):
                node.link(other)  # type: ignore

    def materialize(self, _context: Optional[MaterializationContext] = None) -> "Block":
        return self._materialize(_context)[0]

    def _materialize(
        self, _context: Optional[MaterializationContext] = None, init: bool = True
    ) -> Tuple["Block", MaterializationContext]:
        context: MaterializationContext = (_context or MaterializationContext()).copy()
        if init:
            return self.copy()._materialize(context, init=False)

        materialized = Block()
        context.root_block = context.root_block or materialized
        if context.parent_branch:
            context.parent_branch = context.parent_branch.add("Block")

        source_to_destination: Dict[Union[Unit, Layer], Union[Unit, Layer]] = {}

        def map_to_destination(
            node: Union[Unit, Layer], context: MaterializationContext
        ) -> Tuple[Union[Unit, Layer], MaterializationContext]:
            if node not in source_to_destination:
                source_to_destination[node], context = node._materialize(
                    context.copy().add_prefix("block")
                )

            return source_to_destination[node], context

        for source, dependents in list(
            map(lambda node: (node, list(node.dependents)), self.sort())
        ):
            materialized_source, source_context = map_to_destination(source, context)
            materialized_source.graph = materialized

            if len(dependents) == 0 and isinstance(source, Unit):
                materialized.add(materialized_source)
                continue

            for dependent in dependents:
                materialized_dependent, dependent_context = map_to_destination(
                    dependent, source_context
                )  # type: ignore
                materialized_dependent.graph = materialized

                materialized_source.link(materialized_dependent)

        return materialized, context
