"""Positive static-typing smoke tests; checked by mypy, not pytest."""

from typing import assert_type

from ordered_btree import BTree, NodeSnapshot


def check() -> None:
    tree = BTree[int](keys=[1, 2, 3])
    assert_type(tree.search(1), int | None)
    assert_type(tree.insert(4), bool)
    assert_type(tree.delete(2), bool)
    assert_type(tree.pop_min(), int)
    assert_type(tree.snapshot(), tuple[int, ...])
    assert_type(tree.inspect(), NodeSnapshot[int])
    assert_type(tree.copy(), BTree[int])
    for key in tree.range(1, 4):
        assert_type(key, int)
