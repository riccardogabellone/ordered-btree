"""Run after installation: python examples/basic.py"""

from ordered_btree import BTree, ConcurrentModificationError


def main() -> None:
    tree = BTree[int](t=32, keys=[10, 20, 5, 6, 12, 30, 7, 17])
    assert list(tree) == [5, 6, 7, 10, 12, 17, 20, 30]
    assert list(tree.range(6, 18)) == [6, 7, 10, 12, 17]
    assert tree.search(6) == 6
    assert tree.search(999) is None
    assert not tree.insert(6)
    stable = tree.snapshot()
    iterator = iter(tree)
    assert next(iterator) == 5
    tree.delete(12)
    try:
        next(iterator)
    except ConcurrentModificationError:
        print("The old iterator correctly detected mutation.")
    assert 12 in stable
    assert 12 not in tree
    assert tree.pop_min() == 5
    assert tree.pop_max() == 30
    tree.validate()
    print(tree)
    print("Unchanged tuple:", stable)


if __name__ == "__main__":
    main()
