"""Caller-owned synchronization: hold the lock for the WHOLE logical operation.

This illustrates locking policy, not a separate thread-safe BTree implementation.
"""

from threading import RLock

from ordered_btree import BTree


def main() -> None:
    tree = BTree[int](keys=range(10))
    lock = RLock()
    with lock:
        tree.insert(20)
        values = tree.snapshot()  # Consume while protected; work on the tuple later.
    print(values)
    with lock:
        for key in tree.range(2, 6):
            print(key)
            # Do not mutate tree here: successful mutations invalidate the iterator.


if __name__ == "__main__":
    main()
