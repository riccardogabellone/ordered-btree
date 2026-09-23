## What and why

Describe the behavior changed and the reproducer or evidence motivating it.

## Verification actually executed

List exact commands, Python/platform versions, results, and skipped checks.
For performance changes, include comparable workloads and regressions as well as gains.

## Checklist

- [ ] A regression test demonstrates the defect before the fix, where applicable.
- [ ] Ordering, exception safety, no-op iteration and ownership contracts are preserved.
- [ ] Docs/examples/changelog reflect public behavior changes.
- [ ] No new runtime dependency or consequential API change is hidden in this PR.
- [ ] No credentials, generated artifacts, raw logs or local agent files are included.
- [ ] I have the right to contribute this material under the project's MIT license.
