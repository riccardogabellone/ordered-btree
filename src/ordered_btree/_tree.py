"""A unique ordered-key B-tree with encapsulated mutable storage.

Updates have two phases: a comparison-only search and a comparator-free commit.
All user comparisons must define a stable strict weak ordering; equivalence is
``not (a < b) and not (b < a)``, not Python equality. See docs/design.md for the
exception, aliasing, iterator, and synchronization contracts.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol, Self, TextIO


class Comparable(Protocol):
    """An ordering key; no hashing or equality method is required."""

    def __lt__(self, other: Self, /) -> bool: ...


class ConcurrentModificationError(RuntimeError):
    """An iterator's tree was modified after the iterator was created."""


class ReentrantOperationError(RuntimeError):
    """A callback tried to enter an already active operation on the same tree."""


@dataclass(frozen=True, slots=True)
class NodeSnapshot[T: Comparable]:
    """Detached, structurally immutable diagnostic data.

    Tuples and child snapshots cannot be edited. Stored key objects are shared,
    not deep-copied or frozen. This object is not a live view into a BTree.
    """

    keys: tuple[T, ...]
    children: tuple[NodeSnapshot[T], ...] = ()

    @property
    def leaf(self) -> bool:
        return not self.children


class _Node[T: Comparable]:
    """Private storage. Leaf status is derived, never independently mutable."""

    __slots__ = ("keys", "children")

    def __init__(
        self,
        keys: list[T] | None = None,
        children: list[_Node[T]] | None = None,
    ) -> None:
        self.keys = keys if keys is not None else []
        self.children = children if children is not None else []

    @property
    def leaf(self) -> bool:
        return not self.children


type _Path[T: Comparable] = list[tuple[_Node[T], int]]


class BTree[T: Comparable]:
    """Mutable ordered collection of unique, stably ordered keys.

    ``t`` is a read-only minimum degree, an integer >= 2 (bool is rejected).
    ``keys`` is consumed incrementally; the first equivalent key is retained.
    Only ``<`` is used. None is reserved for absent keys and unbounded ranges.

    Do not mutate ordering-relevant state of stored keys. Private attributes
    are not an API. Public content operations reject same-tree re-entrancy.
    Thread synchronization is the caller's responsibility.
    """

    __slots__ = ("_t", "_root", "_size", "_version", "_busy")

    def __init__(self, t: int = 2, keys: Iterable[T] | None = None) -> None:
        if isinstance(t, bool) or not isinstance(t, int):
            raise TypeError("t must be an integer, not bool")
        degree = int(t)
        if degree < 2:
            raise ValueError("t must be at least 2")
        self._t = degree
        self._root: _Node[T] = _Node()
        self._size = 0
        self._version = 0
        self._busy = False
        if keys is not None:
            for key in keys:
                self.insert(key)

    @property
    def t(self) -> int:
        """Minimum degree; read-only for the lifetime of the tree."""
        return self._t

    @property
    def min_keys(self) -> int:
        """Minimum occupancy of a non-root node."""
        return self._t - 1

    @property
    def max_keys(self) -> int:
        """Maximum occupancy of a node."""
        return 2 * self._t - 1

    def _enter(self) -> None:
        # This is a re-entrancy guard, NOT a thread lock or a borrow checker.
        if self._busy:
            raise ReentrantOperationError("cannot re-enter an active BTree operation")
        self._busy = True

    @contextmanager
    def _operation(self) -> Iterator[None]:
        # Cold paths use the convenient context manager. Hot paths pair _enter
        # with try/finally to avoid allocating a contextmanager for every lookup.
        self._enter()
        try:
            yield
        finally:
            self._busy = False

    @staticmethod
    def _require_key(key: T) -> None:
        if key is None:
            raise TypeError("None is reserved and cannot be a BTree key")

    def _find(self, key: T) -> tuple[_Node[T], int] | None:
        node = self._root
        while True:
            i = bisect_left(node.keys, key)
            # bisect already established not (node.keys[i] < key).
            if i < len(node.keys) and not (key < node.keys[i]):
                return node, i
            if node.leaf:
                return None
            node = node.children[i]

    def _locate(self, key: T) -> tuple[_Node[T], int, bool, _Path[T]]:
        """Find a key or its insertion slot, retaining ancestor child indices."""
        node = self._root
        path: _Path[T] = []
        while True:
            i = bisect_left(node.keys, key)
            if i < len(node.keys) and not (key < node.keys[i]):
                return node, i, True, path
            if node.leaf:
                return node, i, False, path
            path.append((node, i))
            node = node.children[i]

    def search(self, key: T) -> T | None:
        """Return the stored ordering-equivalent key, or None; never a live node."""
        self._enter()
        try:
            self._require_key(key)
            found = self._find(key)
            return found[0].keys[found[1]] if found is not None else None
        finally:
            self._busy = False

    def __contains__(self, key: T) -> bool:
        """Test ordering equivalence. Invalid comparisons propagate unchanged."""
        return self.search(key) is not None

    def insert(self, key: T) -> bool:
        """Insert a new key; False means an equivalent key was already stored.

        Comparator exceptions and duplicate insertion leave structure, content,
        size, and iterator validity unchanged. Allocation failures during commit
        and asynchronous interruption have no rollback guarantee.
        """
        self._enter()
        try:
            self._require_key(key)
            node, i, found, path = self._locate(key)
            if found:
                return False
            # No comparisons or user equality/hashing below this point.
            self._version += 1
            node.keys.insert(i, key)
            self._split_overflow(node, path)
            self._size += 1
            return True
        finally:
            self._busy = False

    def _split_overflow(self, node: _Node[T], path: _Path[T]) -> None:
        maximum = self.max_keys
        median = self._t - 1
        while len(node.keys) > maximum:
            promoted = node.keys[median]
            # Construct the pieces before changing this node's lists. This is
            # not a transaction against every possible allocation failure.
            left_keys = node.keys[:median]
            left_children = node.children[: median + 1] if node.children else []
            right = _Node(
                node.keys[median + 1 :],
                node.children[median + 1 :] if node.children else [],
            )
            if not path:
                root = _Node([promoted], [node, right])
                node.keys = left_keys
                node.children = left_children
                self._root = root
                return
            parent, i = path.pop()
            parent.keys.insert(i, promoted)
            parent.children.insert(i + 1, right)
            node.keys = left_keys
            node.children = left_children
            node = parent

    def delete(self, key: T) -> bool:
        """Remove an ordering-equivalent key; False is a genuine no-op if absent.

        All comparisons precede mutation. Replacement-key extraction, borrowing,
        merging, and root contraction never invoke the comparator.
        """
        self._enter()
        try:
            self._require_key(key)
            node, i, found, path = self._locate(key)
            if not found:
                return False
            self._version += 1
            # Retain the removed representative until the operation is complete,
            # so its destructor cannot observe the commit's intermediate state.
            removed = node.keys[i]
            if node.leaf:
                node.keys.pop(i)
            else:
                left, right = node.children[i : i + 2]
                if len(left.keys) >= self._t or len(right.keys) < self._t:
                    path.append((node, i))
                    replacement, leaf = self._pop_max(left, path)
                else:
                    path.append((node, i + 1))
                    replacement, leaf = self._pop_min(right, path)
                node.keys[i] = replacement
                node = leaf
            self._repair_underflow(node, path)
            self._size -= 1
        finally:
            self._busy = False
        # The reference intentionally lives across _operation's exit.
        del removed
        return True

    @staticmethod
    def _pop_min(node: _Node[T], path: _Path[T]) -> tuple[T, _Node[T]]:
        """Extract an extreme without comparisons; caller repairs underflow."""
        while node.children:
            path.append((node, 0))
            node = node.children[0]
        return node.keys.pop(0), node

    @staticmethod
    def _pop_max(node: _Node[T], path: _Path[T]) -> tuple[T, _Node[T]]:
        """Extract an extreme without comparisons; caller repairs underflow."""
        while node.children:
            i = len(node.children) - 1
            path.append((node, i))
            node = node.children[i]
        return node.keys.pop(), node

    def _repair_underflow(self, node: _Node[T], path: _Path[T]) -> None:
        minimum = self.min_keys
        while path and len(node.keys) < minimum:
            parent, i = path.pop()
            if i > 0 and len(parent.children[i - 1].keys) > minimum:
                self._borrow_left(parent, i)
                break
            if i + 1 < len(parent.children) and len(parent.children[i + 1].keys) > minimum:
                self._borrow_right(parent, i)
                break
            self._merge(parent, i - 1 if i > 0 else i)
            node = parent
        if self._root.children and not self._root.keys:
            self._root = self._root.children[0]

    @staticmethod
    def _borrow_left(parent: _Node[T], i: int) -> None:
        child, left = parent.children[i], parent.children[i - 1]
        child.keys.insert(0, parent.keys[i - 1])
        parent.keys[i - 1] = left.keys.pop()
        if left.children:
            child.children.insert(0, left.children.pop())

    @staticmethod
    def _borrow_right(parent: _Node[T], i: int) -> None:
        child, right = parent.children[i], parent.children[i + 1]
        child.keys.append(parent.keys[i])
        parent.keys[i] = right.keys.pop(0)
        if right.children:
            child.children.append(right.children.pop(0))

    @staticmethod
    def _merge(parent: _Node[T], i: int) -> None:
        left, right = parent.children[i : i + 2]
        left.keys.append(parent.keys.pop(i))
        left.keys.extend(right.keys)
        left.children.extend(right.children)
        parent.children.pop(i + 1)

    def pop_min(self) -> T:
        """Remove and return the minimum without comparisons; KeyError if empty."""
        self._enter()
        try:
            if not self._size:
                raise KeyError("pop_min from an empty BTree")
            self._version += 1
            path: _Path[T] = []
            value, node = self._pop_min(self._root, path)
            self._repair_underflow(node, path)
            self._size -= 1
            return value
        finally:
            self._busy = False

    def pop_max(self) -> T:
        """Remove and return the maximum without comparisons; KeyError if empty."""
        self._enter()
        try:
            if not self._size:
                raise KeyError("pop_max from an empty BTree")
            self._version += 1
            path: _Path[T] = []
            value, node = self._pop_max(self._root, path)
            self._repair_underflow(node, path)
            self._size -= 1
            return value
        finally:
            self._busy = False

    def min(self) -> T | None:
        """Return the stored minimum, or None for an empty tree."""
        self._enter()
        try:
            if not self._size:
                return None
            node = self._root
            while node.children:
                node = node.children[0]
            return node.keys[0]
        finally:
            self._busy = False

    def max(self) -> T | None:
        """Return the stored maximum, or None for an empty tree."""
        self._enter()
        try:
            if not self._size:
                return None
            node = self._root
            while node.children:
                node = node.children[-1]
            return node.keys[-1]
        finally:
            self._busy = False

    def height(self) -> int:
        """Return the number of levels; an empty tree has height zero."""
        self._enter()
        try:
            if not self._size:
                return 0
            depth, node = 1, self._root
            while node.children:
                depth += 1
                node = node.children[0]
            return depth
        finally:
            self._busy = False

    def clear(self) -> None:
        """Remove every key. Clearing an already empty tree is a no-op."""
        self._enter()
        try:
            if not self._size:
                return
            replacement: _Node[T] = _Node()
            old_root = self._root
            self._version += 1
            self._root = replacement
            self._size = 0
        finally:
            self._busy = False
        del old_root

    def __iter__(self) -> Iterator[T]:
        """Create an eager-versioned, fail-fast, ascending iterator."""
        self._enter()
        try:
            return _Cursor(self)
        finally:
            self._busy = False

    def range(self, start: T | None = None, stop: T | None = None) -> Iterator[T]:
        """Iterate [start, stop); None means unbounded on that side.

        Version capture and lower-bound seeking happen NOW, not on first next().
        Bounds are borrowed key objects and must remain stably ordered until
        exhaustion. Reversed/equivalent bounds produce an empty iterator.
        """
        self._enter()
        try:
            empty = start is not None and stop is not None and not (start < stop)
            return _Cursor(self, start, stop, empty=empty)
        finally:
            self._busy = False

    def snapshot(self) -> tuple[T, ...]:
        """Return a detached sorted tuple. Keys are shared, not deep-copied."""
        return tuple(self)

    def inspect(self) -> NodeSnapshot[T]:
        """Copy all structural data into immutable tuples/snapshots; O(n)."""
        with self._operation():
            made: dict[int, NodeSnapshot[T]] = {}
            work = [(self._root, False)]
            while work:
                node, ready = work.pop()
                if not ready:
                    work.append((node, True))
                    work.extend((child, False) for child in reversed(node.children))
                else:
                    made[id(node)] = NodeSnapshot(
                        tuple(node.keys), tuple(made[id(child)] for child in node.children)
                    )
            return made[id(self._root)]

    def copy(self) -> BTree[T]:
        """Clone nodes but share keys; no comparisons and no shared mutable nodes."""
        with self._operation():
            result: BTree[T] = BTree(self._t)
            result._root = _Node(self._root.keys.copy())
            result._size = self._size
            work = [(self._root, result._root)]
            while work:
                source, target = work.pop()
                for child in source.children:
                    clone = _Node(child.keys.copy())
                    target.children.append(clone)
                    work.append((child, clone))
            return result

    def __copy__(self) -> BTree[T]:
        return self.copy()

    def __len__(self) -> int:
        return self._size

    def __repr__(self) -> str:
        with self._operation():
            cursor = _Cursor(self)
            head: list[T] = []
            for _ in range(9):
                try:
                    head.append(cursor._advance())
                except StopIteration:
                    break
            shown = ", ".join(repr(key) for key in head[:8])
            if len(head) > 8:
                shown += ", ..."
            return f"BTree(t={self._t}, size={self._size}, keys=[{shown}])"

    def format_tree(self) -> str:
        """Return a diagnostic indented representation; O(n), not a stable format."""
        with self._operation():
            lines: list[str] = []
            work = [(self._root, 0)]
            while work:
                node, depth = work.pop()
                kind = "leaf" if node.leaf else "internal"
                keys = ", ".join(repr(key) for key in node.keys) or "-"
                lines.append(f"{'    ' * depth}{kind}: [{keys}]")
                work.extend((child, depth + 1) for child in reversed(node.children))
            return "\n".join(lines)

    def display(self, *, file: TextIO | None = None) -> None:
        """Print format_tree() to file (stdout by default)."""
        print(self.format_tree(), file=file)

    def validate(self) -> None:
        """Check raw structure in one iterative pass; ValueError on corruption.

        Shape is checked before indexing children. Detects cycles/shared nodes,
        occupancy, child counts, order/bounds, uneven depths, and size mismatch.
        Comparator exceptions propagate; no validator can prove an arbitrary
        user comparator is a stable strict weak ordering.
        """
        with self._operation():
            if type(self._t) is not int or self._t < 2:
                raise ValueError("invalid minimum degree")
            if type(self._size) is not int or self._size < 0:
                raise ValueError("invalid stored size")
            seen: set[int] = set()
            work: list[tuple[_Node[T], T | None, T | None, int]] = [(self._root, None, None, 0)]
            count = 0
            leaf_depth: int | None = None
            while work:
                node, lower, upper, depth = work.pop()
                if not isinstance(node, _Node):
                    raise ValueError("invalid child node")
                identity = id(node)
                if identity in seen:
                    raise ValueError("cycle or shared child node")
                seen.add(identity)
                if type(node.keys) is not list or type(node.children) is not list:
                    raise ValueError("node storage must consist of lists")
                keys = node.keys
                nkeys = len(keys)
                if nkeys > self.max_keys:
                    raise ValueError("node exceeds maximum occupancy")
                if depth == 0:
                    if node.children and not keys:
                        raise ValueError("internal root must have a key")
                elif nkeys < self.min_keys:
                    raise ValueError("non-root node below minimum occupancy")
                if node.children and len(node.children) != nkeys + 1:
                    raise ValueError("internal node has an invalid child count")
                if any(key is None for key in keys):
                    raise ValueError("None cannot be a stored key")
                for i in range(1, nkeys):
                    if not (keys[i - 1] < keys[i]):
                        raise ValueError("keys must be strictly increasing")
                if keys and lower is not None and not (lower < keys[0]):
                    raise ValueError("key violates lower bound")
                if keys and upper is not None and not (keys[-1] < upper):
                    raise ValueError("key violates upper bound")
                count += nkeys
                if node.leaf:
                    if leaf_depth is None:
                        leaf_depth = depth
                    elif leaf_depth != depth:
                        raise ValueError("leaves have different depths")
                else:
                    for i in range(len(node.children) - 1, -1, -1):
                        lo = keys[i - 1] if i else lower
                        hi = keys[i] if i < nkeys else upper
                        work.append((node.children[i], lo, hi, depth + 1))
            if count != self._size:
                raise ValueError("stored size does not match key count")


class _Cursor[T: Comparable](Iterator[T]):
    """Iterative cursor with a fast leaf scan and a stack of ancestor slots."""

    __slots__ = ("_tree", "_version", "_stack", "_keys", "_index", "_stop", "_done")

    def __init__(
        self,
        tree: BTree[T],
        start: T | None = None,
        stop: T | None = None,
        *,
        empty: bool = False,
    ) -> None:
        self._tree = tree
        self._version = tree._version
        self._stop = stop
        self._done = False
        self._stack: _Path[T] = []
        self._keys: list[T] = []
        self._index = 0
        if empty:
            return
        node = tree._root
        while True:
            i = 0 if start is None else bisect_left(node.keys, start)
            if node.leaf:
                self._keys = node.keys
                self._index = i
                break
            self._stack.append((node, i))
            node = node.children[i]

    def __next__(self) -> T:
        if self._done:
            raise StopIteration
        tree = self._tree
        # Deliberately inline _operation here: allocating a contextmanager for
        # every key dominated otherwise linear scans. The contract is identical.
        if tree._busy:
            raise ReentrantOperationError("cannot re-enter an active BTree operation")
        tree._busy = True
        try:
            if self._version != tree._version:
                self._finish()
                raise ConcurrentModificationError("BTree changed during iteration")
            return self._advance()
        except StopIteration as error:
            if not self._done:
                # A comparator must not masquerade as normal iterator exhaustion.
                raise RuntimeError("upper-bound comparison raised StopIteration") from error
            raise
        finally:
            tree._busy = False

    def _finish(self) -> None:
        self._done = True
        self._stack.clear()
        self._keys = []

    def _advance(self) -> T:
        # Called only while the owning tree's operation guard is held. A leaf
        # scan advances an integer, not a newly allocated stack frame per key.
        i = self._index
        if i < len(self._keys):
            key = self._keys[i]
            if self._stop is not None and not (key < self._stop):
                self._finish()
                raise StopIteration
            self._index = i + 1
            return key
        while self._stack:
            node, i = self._stack[-1]
            if i == len(node.keys):
                self._stack.pop()
                continue
            key = node.keys[i]
            # Check before advancing: a raising comparator can be retried
            # without silently skipping a candidate separator.
            if self._stop is not None and not (key < self._stop):
                self._finish()
                raise StopIteration
            self._stack[-1] = (node, i + 1)
            child = node.children[i + 1]
            while child.children:
                self._stack.append((child, 0))
                child = child.children[0]
            self._keys = child.keys
            self._index = 0
            return key
        self._finish()
        raise StopIteration
