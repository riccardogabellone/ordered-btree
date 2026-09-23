import pytest

from ordered_btree import BTree, ConcurrentModificationError, ReentrantOperationError

from .test_ordering_exceptions import ComparisonFailure, Controller, Key, fingerprint


@pytest.mark.parametrize("use_range", [False, True])
@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("mutation", ["insert", "delete", "pop_min", "pop_max", "clear"])
def test_fail_fast_on_successful_mutations(use_range, started, mutation):
    tree = BTree[int](keys=range(30))
    cursor = tree.range(0, 29) if use_range else iter(tree)
    if started:
        assert next(cursor) == 0
    if mutation == "insert":
        tree.insert(31)
    elif mutation == "delete":
        tree.delete(15)
    else:
        getattr(tree, mutation)()
    with pytest.raises(ConcurrentModificationError):
        next(cursor)
    with pytest.raises(StopIteration):
        next(cursor)


def test_noops_do_not_invalidate():
    tree = BTree[int](keys=[1, 2, 3, 4])
    tree.delete(4)
    cursor = iter(tree)
    assert next(cursor) == 1
    assert not tree.insert(2)
    assert not tree.delete(0)
    assert list(cursor) == [2, 3]
    empty = BTree[int]()
    cursor = iter(empty)
    empty.clear()
    with pytest.raises(StopIteration):
        next(cursor)


def test_delete_reinsert_same_size_still_invalidates():
    tree = BTree[int](keys=[1, 2, 3])
    cursor = iter(tree)
    tree.delete(2)
    tree.insert(2)
    with pytest.raises(ConcurrentModificationError):
        next(cursor)


@pytest.mark.parametrize("initially_empty", [False, True])
def test_empty_or_exhausted_iterators(initially_empty):
    tree = BTree[int](keys=[] if initially_empty else [1])
    cursor = iter(tree)
    assert list(cursor) == ([] if initially_empty else [1])
    tree.insert(2)
    with pytest.raises(StopIteration):
        next(cursor)


def test_empty_iterator_version_is_captured_before_first_next():
    tree = BTree[int]()
    cursor = iter(tree)
    tree.insert(1)
    with pytest.raises(ConcurrentModificationError):
        next(cursor)


def test_invalid_range_can_still_detect_mutation_before_first_next():
    tree = BTree[int](keys=[1])
    cursor = tree.range(8, 3)
    tree.insert(2)
    with pytest.raises(ConcurrentModificationError):
        next(cursor)


def test_multiple_iterators_and_snapshot_independence():
    tree = BTree[int](keys=range(8))
    left, right = iter(tree), tree.range(4, 7)
    assert next(left) == 0
    assert next(right) == 4
    assert next(left) == 1
    snap = tree.snapshot()
    tree.clear()
    assert snap == tuple(range(8))
    for cursor in (left, right):
        with pytest.raises(ConcurrentModificationError):
            next(cursor)


def test_upper_bound_exception_does_not_skip_candidate():
    c = Controller()
    tree = BTree[Key](keys=[Key(i, c) for i in range(10)])
    cursor = tree.range(None, Key(8, c))
    assert next(cursor).value == 0
    c.reset(fail_at=1)
    with pytest.raises(ComparisonFailure):
        next(cursor)
    c.reset()
    assert next(cursor).value == 1
    assert [k.value for k in cursor] == list(range(2, 8))
    tree.validate()


def test_reentry_from_upper_bound_does_not_mutate():
    c = Controller()
    tree = BTree[Key](keys=[Key(i, c) for i in range(10)])
    cursor = tree.range(None, Key(5, c))
    c.reset(callback=tree.clear)
    with pytest.raises(ReentrantOperationError):
        next(cursor)
    c.reset()
    assert [k.value for k in cursor] == list(range(5))
    assert len(tree) == 10


def test_cursor_reentry_from_comparator_is_rejected():
    c = Controller()
    tree = BTree[Key](keys=[Key(i, c) for i in range(10)])
    cursor = iter(tree)
    c.reset(callback=lambda: next(cursor))
    with pytest.raises(ReentrantOperationError):
        tree.search(Key(2, c))
    c.reset()
    assert [key.value for key in cursor] == list(range(10))


class ComparisonStop(StopIteration):
    pass


@pytest.mark.parametrize("separator", [False, True])
@pytest.mark.parametrize("consumer", [next, list])
@pytest.mark.parametrize("exception_type", [StopIteration, ComparisonStop])
@pytest.mark.parametrize("truth_conversion", [False, True])
def test_comparator_stopiteration_is_not_exhaustion(
    separator, consumer, exception_type, truth_conversion
):
    control = Controller()
    keys = [Key(i, control) for i in (1, 2, 3, 4)]
    tree = BTree[Key](keys=keys)
    assert tree.inspect().keys[0] is keys[1]  # Root separator 2, left leaf 1.
    cursor = tree.range(None, Key(10, control))
    if separator:
        assert next(cursor) is keys[0]
    before = fingerprint(tree)
    other_cursor = iter(tree)
    error = exception_type("comparison failed")

    class FailingTruth:
        def __bool__(self):
            raise error

    def failing_comparison(a, b):
        if truth_conversion:
            return FailingTruth()
        raise error

    comparison = control.compare
    control.compare = failing_comparison
    try:
        with pytest.raises(RuntimeError, match="comparison.*StopIteration") as raised:
            consumer(cursor)
    finally:
        control.compare = comparison

    assert raised.value.__cause__ is error
    assert fingerprint(tree) == before
    expected = keys[1:] if separator else keys
    assert all(a is b for a, b in zip(cursor, expected, strict=True))
    assert all(a is b for a, b in zip(other_cursor, keys, strict=True))
    tree.validate()  # The reentrancy guard was released on the exceptional path.
    tree.insert(Key(5, control))
    with pytest.raises(StopIteration):
        next(cursor)
