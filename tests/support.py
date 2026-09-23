"""Independent model and raw-node invariant checks used by tests and stress tools."""

from __future__ import annotations

from itertools import pairwise

from ordered_btree import BTree


def check_int_tree(tree: BTree[int], expected: list[int]) -> None:
    """Check structure without using BTree.validate(), iteration, or inspect()."""
    root = tree._root
    seen: set[int] = set()
    depths: set[int] = set()
    values: list[int] = []

    def visit(node, lower, upper, depth):
        assert id(node) not in seen, "cycle/shared node"
        seen.add(id(node))
        assert len(node.keys) <= 2 * tree.t - 1
        assert (node is root and not node.children) or len(node.keys) >= (
            1 if node is root else tree.t - 1
        )
        assert all(a < b for a, b in pairwise(node.keys))
        assert all(lower is None or lower < key for key in node.keys)
        assert all(upper is None or key < upper for key in node.keys)
        if node.children:
            assert len(node.children) == len(node.keys) + 1
            for i, key in enumerate(node.keys):
                visit(node.children[i], lower if i == 0 else node.keys[i - 1], key, depth + 1)
                values.append(key)
            visit(node.children[-1], node.keys[-1], upper, depth + 1)
        else:
            depths.add(depth)
            values.extend(node.keys)

    visit(root, None, None, 0)
    assert len(depths) == 1
    assert values == expected
    assert len(tree) == len(expected)
    assert tree.height() == (next(iter(depths)) + 1 if expected else 0)
    assert tree.min() == (expected[0] if expected else None)
    assert tree.max() == (expected[-1] if expected else None)
    assert list(tree) == expected
    tree.validate()
