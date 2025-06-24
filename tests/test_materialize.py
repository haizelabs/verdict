import itertools
from typing import Callable

import networkx as nx
import pytest

from verdict.core.executor import Node
from verdict.core.primitive import Block, Layer, Unit


def with_block_wrap(_from, _to):
    def wrap(a: Callable[[], Node], b: Callable[[], Node]):
        for wrap_a, wrap_b in itertools.product([False, True], repeat=2):
            wrapped_a_instance = (Block() >> a()) if wrap_a else a()
            wrapped_b_instance = (Block() >> b()) if wrap_b else b()

            yield a(), wrapped_a_instance, b(), wrapped_b_instance

    def decorator(func):
        parametrize_args = wrap(_from, _to)

        return pytest.mark.parametrize("a, a_wrapped, b, b_wrapped", parametrize_args)(
            func
        )

    return decorator


@with_block_wrap(Unit, Unit)
def test_unit_to_unit(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(), nx.DiGraph([("a", "b")])
    )


# ================================
# Broadcast
# ================================


# n -> n
@with_block_wrap(
    lambda: Layer([Unit()], 3, outer="broadcast"), lambda: Layer([Unit()], 3)
)
def test_broadcast_to_layer_n_to_n(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph([("a1", "b1"), ("a2", "b2"), ("a3", "b3")]),
    )


# ================================
# Dense
# ================================


# 1 -> n
@with_block_wrap(
    lambda: Layer([Unit()], 1, outer="broadcast"), lambda: Layer([Unit()], 3)
)
def test_broadcast_to_layer_1_to_n(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph([("a", "b1"), ("a", "b2"), ("a", "b3")]),
    )


# n -> 1
@with_block_wrap(lambda: Layer([Unit()], 3), lambda: Layer([Unit()], 1))
def test_broadcast_to_layer_n_to_1(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph([("a1", "b"), ("a2", "b"), ("a3", "b")]),
    )


# n -> 1
@with_block_wrap(lambda: Layer([Unit()], 3, outer="broadcast"), Unit)
def test_broadcast_to_unit(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph([("a1", "b"), ("a2", "b"), ("a3", "b")]),
    )


# n -> k (dense)
@with_block_wrap(
    lambda: Layer([Unit()], 2, outer="broadcast"), lambda: Layer([Unit()], 3)
)
def test_broadcast_to_layer_n_to_k(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph(
            [
                ("a1", "b1"),
                ("a2", "b2"),
                ("a1", "b2"),
                ("a2", "b1"),
                ("a1", "b3"),
                ("a2", "b3"),
            ]
        ),
    )


# ================================
# Chain
# ================================


# n -> 1
@with_block_wrap(lambda: Layer([Unit()], 3, inner="chain"), lambda: Layer([Unit()], 1))
def test_chain_to_layer_n_to_1(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph([("a1", "b"), ("a2", "b"), ("a3", "b"), ("a1", "a2"), ("a2", "a3")]),
    )


# n -> k
@with_block_wrap(lambda: Layer([Unit()], 3, inner="chain"), lambda: Layer([Unit()], 2))
def test_chain_to_dense_n_to_k(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph(
            [
                ("a1", "b1"),
                ("a1", "b2"),
                ("a2", "b1"),
                ("a2", "b2"),
                ("a3", "b1"),
                ("a3", "b2"),
                ("a1", "a2"),
                ("a2", "a3"),
            ]
        ),
    )


# ================================
# Chain + Broadcast
# ================================


# n -> n
@with_block_wrap(
    lambda: Layer([Unit()], 3, inner="chain", outer="broadcast"),
    lambda: Layer([Unit()], 3),
)
def test_chain_broadcast_n_to_n(a, a_wrapped, b, b_wrapped):
    graph = Block() >> a_wrapped >> b_wrapped
    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph(
            [("a1", "b1"), ("a2", "b2"), ("a3", "b3"), ("a1", "a2"), ("a2", "a3")]
        ),
    )


# ================================
# Nested
# ================================


# n -> k
@with_block_wrap(lambda: Unit(), lambda: Unit())
def test_nested_layers(a, a_wrapped, b, b_wrapped):
    graph = Block() >> Layer(Layer(a_wrapped, 1) >> b_wrapped, 2) >> Unit()

    assert nx.vf2pp_is_isomorphic(
        graph.materialize().to_networkx(),
        nx.DiGraph([("a1", "b1"), ("b1", "c"), ("a2", "b2"), ("b2", "c")]),
    )
