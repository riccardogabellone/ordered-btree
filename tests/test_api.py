from __future__ import annotations

import copy
import io
import random
from dataclasses import FrozenInstanceError, dataclass

import pytest

from ordered_btree import BTree, NodeSnapshot

from .support import check_int_tree


def test_empty():
    tree = BTree[int]()
    check_int_tree(tree, [])
    assert tree.search(1) is None
    assert tree.snapshot() == ()
    assert tree.inspect() == NodeSnapshot(())
    assert list(tree.range()) == []
    assert not tree.delete(1)
    assert not tree
    assert repr(tree) == "BTree(t=2, size=0, keys=[])"
    for pop in (tree.pop_min, tree.pop_max):
        with pytest.raises(KeyError):
            pop()


@pytest.mark.parametrize("degree", [2, 3, 8, 32, 128])
def test_basic_operations(degree):
    tree = BTree[int](degree, [10, 20, 5, 6, 12, 30, 7, 17])
    expected = [5, 6, 7, 10, 12, 17, 20, 30]
    check_int_tree(tree, expected)
    assert tree.search(6) == 6
    assert tree.search(4) is None
    assert 6 in tree and 4 not in tree
    assert not tree.insert(6)
    assert list(tree.range(6, 18)) == [6, 7, 10, 12, 17]
    for key in expected:
        assert tree.delete(key)
        check_int_tree(tree, [x for x in expected if x > key])


@pytest.mark.parametrize(
    "bounds", [(None, None), (None, 7), (6, None), (7, 7), (18, 6), (-5, 5), (6, 18)]
)
def test_range_bounds(bounds):
    values = [5, 6, 7, 10, 12, 17, 20, 30]
    tree = BTree[int](keys=values)
    lo, hi = bounds
    assert list(tree.range(lo, hi)) == [
        x for x in values if (lo is None or lo <= x) and (hi is None or x < hi)
    ]


@pytest.mark.parametrize("degree", [2, 3, 16, 128])
def test_many_range_endpoints(degree):
    tree = BTree[int](degree, range(-60, 61, 3))
    values = list(tree)
    bounds = [None, *range(-65, 67, 5)]
    for lo in bounds:
        for hi in bounds:
            assert list(tree.range(lo, hi)) == [
                x for x in values if (lo is None or lo <= x) and (hi is None or x < hi)
            ]


@pytest.mark.parametrize("bad", [0, 1, -1, -999])
def test_degree_value_errors(bad):
    with pytest.raises(ValueError):
        BTree(t=bad)


@pytest.mark.parametrize("bad", [True, False, 2.0, 2.5, float("nan"), float("inf"), "2", None])
def test_degree_type_errors(bad):
    with pytest.raises(TypeError):
        BTree(t=bad)


def test_degree_public_configuration_is_readonly():
    tree = BTree[int](3)
    assert tree.t == 3 and tree.min_keys == 2 and tree.max_keys == 5
    for name in ("t", "min_keys", "max_keys", "root"):
        with pytest.raises(AttributeError):
            setattr(tree, name, 8)
    assert not hasattr(tree, "__dict__")


def test_none_reserved_even_when_empty():
    tree = BTree()
    for op in (tree.insert, tree.search, tree.delete, tree.__contains__):
        with pytest.raises(TypeError, match="None"):
            op(None)
    assert not tree


def test_strings_generator_and_duplicates():
    tree = BTree[str](keys=(s for s in ["pear", "apple", "pear", "plum"]))
    assert list(tree) == ["apple", "pear", "plum"]
    assert list(tree.range("pear", None)) == ["pear", "plum"]
    assert tree.min() == "apple" and tree.max() == "plum"


def test_snapshot_is_detached_and_structurally_frozen():
    tree = BTree[int](keys=range(50))
    shape = tree.inspect()
    values = tree.snapshot()
    assert isinstance(shape.keys, tuple)
    assert isinstance(shape.children, tuple)
    assert not shape.leaf
    with pytest.raises(FrozenInstanceError):
        shape.keys = ()
    with pytest.raises(TypeError):
        shape.children[0].keys[0] = 1
    old_repr = repr(shape)
    tree.clear()
    assert tree.snapshot() == ()
    assert values == tuple(range(50))
    assert repr(shape) == old_repr


@dataclass(frozen=True)
class Record:
    order: int
    payload: str

    def __lt__(self, other: Record) -> bool:
        return self.order < other.order


def test_search_returns_original_representative():
    first, later = Record(1, "first"), Record(1, "later")
    tree = BTree[Record](keys=[first])
    assert not tree.insert(later)
    assert tree.search(later) is first
    assert tree.min() is first
    assert tree.snapshot()[0] is first
    assert tree.inspect().keys[0] is first


@pytest.mark.parametrize("factory", [lambda t: t.copy(), copy.copy])
def test_copy_has_distinct_nodes_and_shared_keys(factory):
    keys = [Record(i, str(i)) for i in range(100)]
    source = BTree[Record](keys=keys)
    target = factory(source)
    assert target.t == source.t
    assert target is not source
    assert target.search(keys[42]) is keys[42]
    assert target._root is not source._root
    for value in keys:
        target.delete(value)
    assert len(source) == 100 and len(target) == 0
    source.validate()
    target.validate()


def test_clear_and_reuse():
    tree = BTree[int](keys=range(100))
    tree.clear()
    tree.clear()
    check_int_tree(tree, [])
    tree.insert(2)
    check_int_tree(tree, [2])


@pytest.mark.parametrize("degree", [2, 3, 8, 128])
def test_pop_extremes(degree):
    tree = BTree[int](degree, range(200))
    for i in range(100):
        assert tree.pop_min() == i
        assert tree.pop_max() == 199 - i
        check_int_tree(tree, list(range(i + 1, 199 - i)))


def test_repr_and_display():
    tree = BTree[int](keys=range(20))
    assert repr(tree) == "BTree(t=2, size=20, keys=[0, 1, 2, 3, 4, 5, 6, 7, ...])"
    assert repr(BTree[int](keys=[1, 2])) == "BTree(t=2, size=2, keys=[1, 2])"
    out = io.StringIO()
    tree.display(file=out)
    assert out.getvalue() == tree.format_tree() + "\n"
    assert "internal" in out.getvalue() and "    leaf" in out.getvalue()


@pytest.mark.parametrize("size", [3, 8])
def test_duplicate_on_actually_full_root(size):
    tree = BTree[int](keys=range(1, size + 1))
    assert len(tree._root.keys) == tree.max_keys
    old_root, version, before = tree._root, tree._version, tree.inspect()
    assert not tree.insert(2)
    assert tree._root is old_root and tree._version == version
    assert tree.inspect() == before


def test_missing_delete_no_longer_merges_root():
    tree = BTree[int](keys=[1, 2, 3, 4])
    tree.delete(4)
    shape = tree.inspect()
    assert not shape.leaf
    assert not tree.delete(0)
    assert tree.inspect() == shape
    assert tree.delete(2)
    check_int_tree(tree, [1, 3])
    assert tree.inspect().leaf


@pytest.mark.parametrize("degree", [2, 3, 5, 32])
def test_shuffled_drain(degree):
    values = list(range(1500))
    rng = random.Random(7)
    rng.shuffle(values)
    tree = BTree[int](degree, values)
    model = set(values)
    rng.shuffle(values)
    for i, key in enumerate(values):
        assert tree.delete(key)
        model.remove(key)
        if i % 31 == 0:
            check_int_tree(tree, sorted(model))
    check_int_tree(tree, [])
