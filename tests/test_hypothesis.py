"""Required stateful property tests, including populated split/grow/drain histories."""

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from ordered_btree import BTree

from .support import check_int_tree


class TreeMachine(RuleBasedStateMachine):
    @initialize(degree=st.sampled_from([2, 3, 8, 32, 128]))
    def create(self, degree):
        self.tree = BTree[int](degree)
        self.model = set()
        self.grow()

    @rule()
    def grow(self):
        # More than one node can hold, even at t=128; also repopulates cleared trees.
        for key in range(-self.tree.t, self.tree.t + 1):
            assert self.tree.insert(key) == (key not in self.model)
            self.model.add(key)
        assert self.tree.height() >= 2

    @rule(last=st.booleans())
    def drain(self, last):
        for expected in sorted(self.model, reverse=last):
            actual = self.tree.pop_max() if last else self.tree.pop_min()
            assert actual == expected
            self.model.remove(expected)
        assert not self.tree

    @rule(key=st.integers(-500, 500))
    def insert(self, key):
        assert self.tree.insert(key) == (key not in self.model)
        self.model.add(key)

    @rule(key=st.integers(-500, 500))
    def delete(self, key):
        assert self.tree.delete(key) == (key in self.model)
        self.model.discard(key)

    @rule(key=st.integers(-500, 500))
    def search(self, key):
        assert (key in self.tree) == (key in self.model)

    @rule(
        start=st.one_of(st.none(), st.integers(-600, 600)),
        stop=st.one_of(st.none(), st.integers(-600, 600)),
    )
    def range_query(self, start, stop):
        assert list(self.tree.range(start, stop)) == [
            x
            for x in sorted(self.model)
            if (start is None or start <= x) and (stop is None or x < stop)
        ]

    @rule(last=st.booleans())
    def pop_extreme(self, last):
        if self.model:
            expected = max(self.model) if last else min(self.model)
            assert (self.tree.pop_max() if last else self.tree.pop_min()) == expected
            self.model.remove(expected)
        else:
            with pytest.raises(KeyError):
                self.tree.pop_max() if last else self.tree.pop_min()

    @rule()
    def clear(self):
        self.tree.clear()
        self.model.clear()

    @invariant()
    def agrees_with_model(self):
        check_int_tree(self.tree, sorted(self.model))


TestTreeMachine = TreeMachine.TestCase
TestTreeMachine.settings = settings(max_examples=100, stateful_step_count=200, deadline=None)
