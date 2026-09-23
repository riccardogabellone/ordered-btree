---
name: Bug report
about: Report a reproducible library or tooling defect
---

## Expected and actual behavior

Describe which documented contract is violated.

## Minimal reproduction

Include a self-contained example and, if relevant, the complete traceback.
Do not include credentials or private data. For vulnerabilities, follow SECURITY.md
rather than posting exploit details here.

## Environment

- Package version / commit:
- Python version and build (including free-threaded/GIL status if applicable):
- Operating system:
- uv version (for development/build issues):
- Exact command:

## Checks

- [ ] Ordering-relevant key state stays stable and `<` defines a strict weak order.
- [ ] Shared-instance access is externally synchronized, if applicable.
- [ ] The example does not modify private tree storage (unless testing validation).
