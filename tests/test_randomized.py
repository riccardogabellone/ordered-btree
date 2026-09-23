import bisect
import random

import pytest

from ordered_btree import BTree

from .support import check_int_tree


@pytest.mark.parametrize("degree", [2, 3, 8, 32, 128])
def test_random_mixed_operations(degree):
    rng = random.Random(783)
    tree = BTree[int](degree)
    model = []
    for step in range(6000):
        key = rng.randrange(-300, 301)
        action = rng.randrange(6)
        index = bisect.bisect_left(model, key)
        found = index < len(model) and model[index] == key
        if action == 0:
            assert tree.insert(key) == (not found)
            if not found:
                model.insert(index, key)
        elif action == 1:
            assert tree.delete(key) == found
            if found:
                model.pop(index)
        elif action == 2:
            assert tree.search(key) == (key if found else None)
        elif action == 3:
            end = key + rng.randrange(-20, 30)
            assert list(tree.range(key, end)) == model[index : bisect.bisect_left(model, end)]
        elif action == 4 and model:
            assert tree.pop_min() == model.pop(0)
        elif action == 5 and model:
            assert tree.pop_max() == model.pop()
        if step % 101 == 0:
            check_int_tree(tree, model)
    check_int_tree(tree, model)


@pytest.mark.parametrize("degree", [2, 3, 8, 32, 128])
def test_populated_threshold_growth_churn_and_drain(degree):
    rng = random.Random(12983)
    model = list(range(2 * degree - 1))
    insertion = model.copy()
    rng.shuffle(insertion)
    tree = BTree[int](degree, insertion)
    check_int_tree(tree, model)
    assert tree.height() == 1  # An actually full leaf, not a nominal degree fixture.

    assert tree.insert(2 * degree - 1)
    model.append(2 * degree - 1)
    assert tree.height() >= 2
    check_int_tree(tree, model)
    for key in range(2 * degree, 6 * degree):
        assert tree.insert(key)
        model.append(key)
    check_int_tree(tree, model)

    # Unlike the small churn case above, maintain enough keys for internal nodes.
    for step in range(200):
        removed = rng.choice(model)
        assert tree.delete(removed)
        model.remove(removed)
        added = 6 * degree + step
        assert tree.insert(added)
        bisect.insort(model, added)
        check_int_tree(tree, model)
        assert tree.height() >= 2

    deletion = model.copy()
    rng.shuffle(deletion)
    for key in deletion:
        assert tree.delete(key)
        model.remove(key)
        check_int_tree(tree, model)
    assert tree.height() == 0

    for key in reversed(range(-2 * degree, 0)):
        assert tree.insert(key)
        bisect.insort(model, key)
    assert tree.height() >= 2
    check_int_tree(tree, model)
    while model:
        assert tree.pop_min() == model.pop(0)
        if model:
            assert tree.pop_max() == model.pop()
        check_int_tree(tree, model)


@pytest.mark.stress
def test_exhaustive_small_histories():
    from tools.stress import exhaustive

    assert exhaustive(5)["histories"] == 14400
