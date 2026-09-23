"""An immutable ordering key with a payload excluded from ordering."""

from __future__ import annotations

from dataclasses import dataclass

from ordered_btree import BTree


@dataclass(frozen=True, slots=True)
class Job:
    priority: int
    job_id: int
    description: str = ""

    def __lt__(self, other: Job) -> bool:
        return (self.priority, self.job_id) < (other.priority, other.job_id)


def main() -> None:
    original = Job(1, 42, "First submitted payload")
    jobs = BTree[Job](t=8, keys=[Job(3, 12, "Later"), original])
    probe = Job(1, 42, "A different payload does not change the ordering key")
    assert probe != original  # Dataclass equality includes description.
    assert not jobs.insert(probe)  # BTree equivalence does not.
    assert jobs.search(probe) is original
    assert jobs.pop_min() is original
    print(jobs.snapshot())


if __name__ == "__main__":
    main()
