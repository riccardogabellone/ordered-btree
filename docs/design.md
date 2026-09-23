# Design decisions

## 1. Own mutable structure; expose immutable descriptions

A useful Rust-inspired property is not “every object is frozen”; it is that
callers cannot retain an ordinary public mutable reference into structural
storage. Splits and merges need efficient list updates, so `_Node` remains
mutable, slotted, and private. Its leaf status is derived from `children`, removing
an independent flag that could contradict the structure.

The degree has no public setter. There is no public `root` or `BTreeNode`.
`inspect()` explicitly pays for a complete detached graph of frozen dataclasses
whose keys/children are tuples. `snapshot()` pays for a sorted tuple. Neither
operation claims to deep-freeze arbitrary user objects. `copy()` clones mutable
nodes without comparing keys and shares key references.

**Alternative rejected for this version:** freezing every node and path-copying
every update. Persistent trees can make old roots useful snapshots and support a
different reader/writer model, but add allocation, memory-retention, and API
complexity. There was no stated need for persistent versions. They are a distinct
feature, not a requirement for safe encapsulation.

Python privacy, `frozen=True`, and `__slots__` are not a borrow checker or a
security boundary. A caller can deliberately reach underscore fields, and
objects returned by `search` are the original key references. Ordering-relevant
state must remain unchanged. The examples use frozen record keys, with payloads
excluded from ordering. A frozen object containing a mutable list is still not
deeply immutable.

## 2. Search first, commit without comparisons

Moving a replacement separator before the final user comparison would risk
partial mutation if the comparison raises. Rebalancing before establishing key
presence would also make an unsuccessful deletion observably change structure.

The implementation instead records `(parent, child_index)` frames during one
comparison-only search. No lists, size, or version are modified in that phase.

Insertion inserts at the known leaf slot, then splits overflowing nodes upward.
An overflow has `2t` keys; promoting position `t-1` leaves `t-1` keys on the left
and `t` on the right, both valid. Cascading promotion follows recorded indices;
no new comparison descent is needed.

Deletion locates a key first. For an internal separator it extracts an extreme
from a suitable adjacent subtree using only child indices, assigns the
replacement, then repairs the leaf underflow upward. Prefer the predecessor if
the left child has room; otherwise use a successor when the right child has room;
when both are minimal, predecessor extraction and bottom-up repair are valid.
Borrowing moves a sibling key through the parent. If neither sibling can spare,
a merge joins the underfull node, a separator, and a minimal sibling. The merged
occupancy is within capacity. Parent underflow propagates until repaired or the
root is contracted. All this work is comparator-free.

This strengthens **comparator-exception safety**, not general transactional
safety. There is no rollback log for allocation failure during list changes or
asynchronous interruption. A callback that mutates key ordering or private
storage violates the precondition. Bulk construction consumes its iterable
incrementally and can fail before returning an instance.

No-op updates have no structural side effects. This also allows accurate iterator
invalidation: duplicate insertion, missing deletion and empty clearing do not
increment the version.

## 3. Ordering is not Python equality

A stable strict weak ordering is sufficient: incomparable-in-both-directions
keys must form transitive equivalence classes, and those classes must be ordered.
The first equivalent key is retained. `search` returns that stored representative,
not the probe and not a node. Only `<` is called. This is compatible with
`bisect_left`, whose candidate is already known not to be less than the probe;
only the reverse test is needed to determine equivalence.

An arbitrary `__lt__` method is not evidence that its laws hold. NaN keys, cyclic
preferences, partial set-inclusion orders, and keys that mutate their own order
are unsupported. Runtime law checking would be incomplete or expensive, so this
is a documented contract, not a misleading universal key validator.

`None` remains reserved for open endpoints and missing results. Supporting it as
a key would require sentinel/default or exception-based lookup changes, and in
most cases a projection-based ordering. That is intentionally deferred.

## 4. Fail-fast iteration with bounded state

Each iterator captures the tree version during creation, before its first
`next()`. Range creation also validates endpoint order and seeks the lower bound
with bisection at each level. A cursor retains ancestor slots plus the current
leaf and leaf index. It walks successive leaves/separators without recursive
generator delegation or repeated lower-bound tests. A leaf scan updates an
integer instead of allocating one stack tuple for each key.

Each `next()` checks modification and same-tree re-entrancy. The hot-path guard
is inlined to avoid allocating a contextmanager per element. Internal separator
transitions can descend `O(h)` levels, but total iteration is `O(n)` and a range
is `O(h log t + k)`. A stop comparison is made before consuming its candidate,
allowing a failed comparison to be retried without losing a key. Comparator-originated
`StopIteration` (including a subclass or truth-conversion failure) is translated
into `RuntimeError` with exception chaining. Letting it escape as `StopIteration`
would make `list()` silently truncate and violate permanent iterator exhaustion.
The candidate remains unconsumed; other comparison exceptions propagate unchanged.

A successful commit increments the version, even when a delete followed by an
insert restores the original size. Duplicates, missing deletes and empty clears
do not. Exhausted iterators remain exhausted. After a modification error the
iterator releases traversal references and becomes exhausted. An outstanding
iterator still retains its owning tree; snapshots/copies retain shared keys.

**Alternative rejected:** prohibiting all mutations while any iterator exists.
That is closer to a dynamic read-borrow policy but requires managing abandoned
iterators and surprising object lifetimes. Fail-fast behavior allows normal
Python loops and explicit snapshot-based mutation without implicit long-lived
locks.

## 5. Re-entrancy and threads are different

A per-instance active-operation flag rejects callbacks that try to traverse or
mutate that same tree, including from `<` and key `repr`. Metadata reads are safe.
Removed representatives and roots are retained until normal mutation exits so
their finalizers do not see the intermediate commit state.

The flag is not an atomic mutex. No same-instance concurrency guarantee is made,
including for free-threaded Python. Applications supply their own lock and hold
it across compound operations or iterator consumption. Independent instances
can be used independently, subject to key-object sharing and comparator safety.

## 6. Validator and test independence

`validate()` does not call public iteration or assume child counts are correct.
It checks storage type, occupancy and child count before following children; it
tracks object identities to detect cycles/shared nodes, checks strict local
order and inherited separator bounds, enforces uniform leaf depth, and compares
the accumulated key count with size. Comparator failures are allowed to propagate.

The stress tests additionally use an independent raw-node traversal and a
sorted-list/set model. Thus a shared error in `validate()` and iteration is less
likely to hide a balancing error. Coverage is evidence of exercised code, not a
proof of correctness. Fault injection fails each comparison position in selected
updates and verifies exact structural fingerprints and iterator validity.

## 7. Conservative scope

The library intentionally has no map API, multiset semantics, rank/select,
key-projection callback, automatic locking, persistence, serialization format,
or set equality/operators. These require separate semantics and tests. The
minimum supported syntax remains Python 3.12; no 3.14-only dependency is needed.
The default degree remains two, with workload-specific tuning recommended.

## 8. Development and distribution boundaries

uv manages contributor environments and the committed dependency lock; setuptools
is the PEP 517 build backend. Development tools are a dependency group, not
consumer extras or runtime requirements. Strict mypy checks complement runtime
and property tests. The `py.typed` marker ships with the runtime package.

The wheel contains only the runtime package and distribution metadata. The sdist
also includes public documentation, tests, examples and verification tools.
GitHub configuration belongs to the repository/project ZIP, not the installed
package. Generated evidence, virtual environments and local agent instructions
are excluded from Git and release artifacts.

The license is MIT and the distribution name is `ordered-btree`. Explicit
publication safeguards remain until the owner authorizes publishing; local build
and validation success are independent of that authorization.

## Primary references

- Python bisect semantics: https://docs.python.org/3.14/library/bisect.html
- Python free-threading guidance: https://docs.python.org/3.14/howto/free-threading-python.html
- Typed-package marker: https://typing.python.org/en/latest/spec/distributing.html

These references support language/tooling details, not a claim that this
particular implementation is verified by those projects.
