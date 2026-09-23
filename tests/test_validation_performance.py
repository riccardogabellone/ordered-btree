import math

import pytest

from ordered_btree import BTree, ReentrantOperationError
from ordered_btree._tree import _Cursor, _Node

from .test_ordering_exceptions import Controller, Key


def test_child_count_checked_before_following_children():
    tree = BTree[int](keys=[1, 2, 3, 4])
    tree._root.children.pop()
    with pytest.raises(ValueError, match="child count"):
        tree.validate()


def test_leaf_flag_cannot_diverge_from_children():
    node = _Node([1])
    assert node.leaf
    with pytest.raises(AttributeError):
        node.leaf = True
    node.children.append(_Node())
    assert not node.leaf
    tree = BTree[int](keys=[1])
    tree._root = node
    with pytest.raises(ValueError, match="child count"):
        tree.validate()


@pytest.mark.parametrize(
    "corruption,match",
    [
        (lambda t: setattr(t, "_size", -1), "invalid stored size"),
        (lambda t: setattr(t, "_size", True), "invalid stored size"),
        (lambda t: setattr(t, "_size", len(t) + 1), "size"),
        (lambda t: setattr(t, "_t", 2.0), "degree"),
        (lambda t: setattr(t, "_root", None), "node"),
        (lambda t: setattr(t._root, "keys", (1,)), "lists"),
        (lambda t: setattr(t._root, "children", ()), "lists"),
        (lambda t: t._root.keys.extend([20, 30, 40]), "maximum"),
        (lambda t: t._root.keys.reverse(), "increasing"),
        (lambda t: t._root.keys.__setitem__(0, None), "None"),
    ],
)
def test_malformed_storage(corruption, match):
    tree = BTree[int](keys=[1, 2, 3])
    corruption(tree)
    with pytest.raises(ValueError, match=match):
        tree.validate()


def test_cycles():
    tree = BTree[int](keys=[1, 2, 3, 4])
    tree._root.children[0] = tree._root
    with pytest.raises(ValueError, match="cycle"):
        tree.validate()


def test_shared_children():
    tree = BTree[int](keys=[1, 2, 3, 4])
    tree._root.children[1] = tree._root.children[0]
    with pytest.raises(ValueError, match="shared"):
        tree.validate()


def test_empty_internal_root():
    tree = BTree[int]()
    tree._root.children = [_Node([1])]
    with pytest.raises(ValueError, match="internal root"):
        tree.validate()


def test_missing_children_are_detected_without_indexerror():
    tree = BTree[int](keys=range(30))
    tree._root.children.clear()
    # With derived leaf status, this now presents as a truncated leaf; size fails.
    with pytest.raises(ValueError, match="size"):
        tree.validate()


def test_non_root_underflow():
    tree = BTree[int](keys=[1, 2, 3, 4])
    tree._root.children[0].keys.clear()
    with pytest.raises(ValueError, match="minimum"):
        tree.validate()


@pytest.mark.parametrize("index,value,match", [(0, 3, "upper"), (1, 1, "lower")])
def test_separator_bounds(index, value, match):
    tree = BTree[int](keys=[1, 2, 3, 4])
    tree._root.children[index].keys = [value]
    with pytest.raises(ValueError, match=match):
        tree.validate()


def test_unbalanced_depth():
    tree = BTree[int]()
    tree._root = _Node([5], [_Node([2], [_Node([1]), _Node([3])]), _Node([8])])
    tree._size = 5
    with pytest.raises(ValueError, match="depths"):
        tree.validate()


@pytest.mark.parametrize("degree", [128, 2048, 8192])
def test_empty_tail_range_uses_logarithmic_comparisons(degree):
    c = Controller()
    n = 2 * degree - 1
    tree = BTree[Key](degree, (Key(i, c) for i in range(n)))
    assert tree.height() == 1
    c.reset()
    assert list(tree.range(Key(n, c), Key(n + 1, c))) == []
    assert c.count <= math.ceil(math.log2(n + 1)) + 2


def test_repr_requests_at_most_nine_keys(monkeypatch):
    tree = BTree[int](keys=range(10000))
    calls = 0
    original = _Cursor._advance

    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(_Cursor, "_advance", counted)
    assert "..." in repr(tree)
    assert calls == 9


def test_full_iteration_makes_no_comparisons():
    c = Controller()
    tree = BTree[Key](2, (Key(i, c) for i in range(1000)))
    c.reset(fail_at=1)
    assert len(list(tree)) == 1000
    assert c.count == 0


def test_validator_is_one_linear_pass_not_public_iteration(monkeypatch):
    c = Controller()
    tree = BTree[Key](2, (Key(i, c) for i in range(1000)))

    def forbidden(self):
        raise AssertionError("validate must not use public iteration")

    monkeypatch.setattr(BTree, "__iter__", forbidden)
    c.reset()
    tree.validate()
    assert c.count < 3 * len(tree)


def test_repr_callback_cannot_reenter_tree():
    class ReprKey:
        def __lt__(self, other):
            return False

        def __repr__(self):
            tree.clear()
            return "unreachable"

    tree = BTree[ReprKey](keys=[ReprKey()])
    with pytest.raises(ReentrantOperationError):
        repr(tree)
    assert len(tree) == 1
