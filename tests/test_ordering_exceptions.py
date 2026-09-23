from __future__ import annotations

from collections.abc import Callable

import pytest

from ordered_btree import BTree, ReentrantOperationError


class ComparisonFailure(Exception):
    pass


class Controller:
    def __init__(self):
        self.count = 0
        self.fail_at = None
        self.callback = None

    def reset(self, fail_at=None, callback=None):
        self.count = 0
        self.fail_at = fail_at
        self.callback = callback

    def compare(self, a, b):
        self.count += 1
        if self.callback is not None:
            self.callback()
        if self.count == self.fail_at:
            raise ComparisonFailure("injected comparator failure")
        return a < b


class Key:
    __hash__ = None

    def __init__(self, value, control):
        self.value = value
        self.control = control

    def __lt__(self, other):
        return self.control.compare(self.value, other.value)

    def __eq__(self, other):
        raise AssertionError("equality must not be used")

    def __le__(self, other):
        raise AssertionError("<= must not be used")

    def __gt__(self, other):
        raise AssertionError("> must not be used")

    def __ge__(self, other):
        raise AssertionError(">= must not be used")

    def __repr__(self):
        return f"Key({self.value})"


def fingerprint(tree):
    work = [tree._root]
    nodes = []
    while work:
        node = work.pop()
        nodes.append(
            (id(node), tuple(id(k) for k in node.keys), tuple(id(c) for c in node.children))
        )
        work.extend(reversed(node.children))
    return tree._size, tree._version, tuple(nodes)


def test_lt_only_unhashable_keys():
    c = Controller()
    tree = BTree[Key](3, [Key(i, c) for i in range(150)])
    assert not tree.insert(Key(2, c))
    assert tree.search(Key(3, c)).value == 3
    assert [k.value for k in tree.range(Key(17, c), Key(29, c))] == list(range(17, 29))
    tree.validate()
    assert tree.delete(Key(30, c))
    assert tree.pop_min().value == 0
    assert tree.pop_max().value == 149
    tree.validate()


@pytest.mark.parametrize("degree", [2, 3, 8])
@pytest.mark.parametrize(
    "op,value",
    [
        ("insert", -1),
        ("insert", 24),
        ("insert", 200),
        ("delete", 0),
        ("delete", 24),
        ("delete", 77),
        ("delete", 199),
        ("delete", 200),
    ],
)
def test_every_comparison_failure_is_a_true_noop(degree, op, value):
    # Fail at EVERY comparison in this operation, not just its first comparison.
    c = Controller()
    values = list(range(0, 200, 2))
    base = BTree[Key](degree, [Key(v, c) for v in values])
    probe = Key(value, c)
    c.reset()
    getattr(base.copy(), op)(probe)
    comparisons = c.count
    assert comparisons > 0
    for fail_at in range(1, comparisons + 1):
        tree = base.copy()
        iterator = iter(tree)
        before = fingerprint(tree)
        c.reset(fail_at=fail_at)
        with pytest.raises(ComparisonFailure):
            getattr(tree, op)(probe)
        c.reset()
        assert fingerprint(tree) == before
        assert [k.value for k in iterator] == values
        tree.validate()


def test_no_second_comparison_descent_on_insert_or_delete():
    c = Controller()
    base = BTree[Key](2, [Key(i, c) for i in range(300)])
    for value, method in [(301, "insert"), (78, "delete")]:
        key = Key(value, c)
        c.reset()
        base.search(key)
        search_comparisons = c.count
        c.reset(fail_at=search_comparisons + 1)
        assert getattr(base.copy(), method)(key)
        assert c.count == search_comparisons
    c.reset()


def test_internal_successor_extraction_does_not_compare():
    c = Controller()
    tree = BTree[Key](keys=[Key(i, c) for i in (1, 2, 3, 4)])

    # Replacement extraction must be positional, not a second comparison descent.
    def no_successor_comparison(a, b):
        if a == b == 3:
            raise ComparisonFailure()
        return a < b

    c.compare = no_successor_comparison
    assert tree.delete(Key(2, c))
    assert [k.value for k in tree] == [1, 3, 4]
    tree.validate()


def test_pop_and_copy_do_not_compare():
    c = Controller()
    tree = BTree[Key](keys=[Key(i, c) for i in range(100)])
    c.reset(fail_at=1)
    cloned = tree.copy()
    for i in range(50):
        assert tree.pop_min().value == i
        assert tree.pop_max().value == 99 - i
    assert c.count == 0
    assert len(cloned) == 100
    c.reset()
    cloned.validate()


@pytest.mark.parametrize("operation", ["insert", "delete", "search", "range", "validate"])
def test_reentrant_mutation_rejected(operation):
    c = Controller()
    tree = BTree[Key](keys=[Key(i, c) for i in range(20)])
    before = fingerprint(tree)
    c.reset(callback=tree.clear)
    calls: dict[str, Callable] = {
        "insert": lambda: tree.insert(Key(30, c)),
        "delete": lambda: tree.delete(Key(3, c)),
        "search": lambda: tree.search(Key(3, c)),
        "range": lambda: tree.range(Key(3, c), Key(5, c)),
        "validate": tree.validate,
    }
    with pytest.raises(ReentrantOperationError):
        calls[operation]()
    c.reset()
    assert fingerprint(tree) == before
    tree.validate()


def test_reentrant_read_rejected_but_metadata_allowed():
    c = Controller()
    tree = BTree[Key](keys=[Key(i, c) for i in range(5)])
    c.reset(callback=lambda: tree.search(Key(2, c)))
    with pytest.raises(ReentrantOperationError):
        tree.search(Key(1, c))
    c.reset(callback=lambda: (len(tree), tree.t))
    assert tree.search(Key(1, c)).value == 1
    c.reset()


def test_mixed_types_raise_without_mutation():
    tree = BTree[int](keys=range(30))
    before = tree.inspect()
    for method in (tree.search, tree.insert, tree.delete):
        with pytest.raises(TypeError):
            method("not-an-int")
        assert tree.inspect() == before


def test_constructor_iterator_exception_propagates():
    def bad():
        yield 1
        raise RuntimeError("source iterator")

    with pytest.raises(RuntimeError, match="source iterator"):
        BTree[int](keys=bad())
