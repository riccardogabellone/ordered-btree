# Security policy

## Supported versions and boundaries

This project is an unpublished alpha. There is no supported stable release or
promised security-response SLA yet. Reports about the current development
version are welcome once a reporting channel is available.

The library is an in-process data structure, not a sandbox. User comparison,
representation and finalizer callbacks execute arbitrary Python. Underscore
attributes are private conventions, not access controls. Invalid comparators,
mutable ordering state, private-storage tampering and unsynchronized shared
access violate its documented preconditions. Allocation failure and asynchronous
interruption are not covered by transactional rollback guarantees.

## Reporting a vulnerability

Do not put exploit details, private data or credentials in a public issue.
After repository publication, prefer GitHub's **Security → Report a vulnerability**
when private vulnerability reporting is enabled. If no private channel is shown,
ask the maintainer to provide one, without disclosing the vulnerability publicly.
No private contact address is assumed or published in this package.

Include the affected version/commit, Python build/platform, a minimal reproducer,
the violated contract and likely impact. Remove credentials and personal data.
Ordinary balancing or API bugs without a security impact can use the bug template.

## Maintainer checklist before making the repository public

- Enable private vulnerability reporting and verify how reporters can reach it.
- Enable available secret scanning/push protection and dependency alerts.
- Require reviews/status checks for protected branches and restrict force pushes.
- Keep Actions read-only by default; never run untrusted PR code with secrets or
  `pull_request_target` write privileges. Pin actions to verified full commits.
- Inspect artifacts and source archives for environments, credentials, local
  instructions and unrelated files before sharing them.
- Keep package publication separately approved; use scoped credentials or trusted
  publishing only after repository, index ownership and release controls exist.

The presence of this policy or CI configuration does not mean those remote
settings have been enabled. No remote repository is created by local validation.
