# Security policy

## Supported versions and boundaries

The initial release line is 0.1.x, with a pre-1.0 API and no promised
security-response SLA. Reports about the latest release or current development
version are welcome. See the repository's releases for versions actually published.

The library is an in-process data structure, not a sandbox. User comparison,
representation and finalizer callbacks execute arbitrary Python. Underscore
attributes are private conventions, not access controls. Invalid comparators,
mutable ordering state, private-storage tampering and unsynchronized shared
access violate its documented preconditions. Allocation failure and asynchronous
interruption are not covered by transactional rollback guarantees.

## Reporting a vulnerability

Do not put exploit details, private data or credentials in a public issue.
Prefer GitHub's **Security → Report a vulnerability** at
https://github.com/riccardogabellone/ordered-btree/security/advisories/new.
If no private channel is shown,
ask the maintainer to provide one, without disclosing the vulnerability publicly.
No private contact address is assumed or published in this package.

Include the affected version/commit, Python build/platform, a minimal reproducer,
the violated contract and likely impact. Remove credentials and personal data.
Ordinary balancing or API bugs without a security impact can use the bug template.

## Maintainer controls to verify remotely

- Enable private vulnerability reporting and verify how reporters can reach it.
- Enable available secret scanning/push protection and dependency alerts.
- Require PRs and the fail-closed CI check for protected main, without admin bypass
  or force pushes. Do not require a second maintainer who does not exist.
- Keep Actions read-only by default; never run untrusted PR code with secrets or
  `pull_request_target` write privileges. Pin actions to verified full commits.
- Inspect artifacts and source archives for environments, credentials, local
  instructions and unrelated files before sharing them.
- Keep production publication separately approved. Trusted Publishing binds the
  upstream repository, direct release.yml jobs and the matching environments.
  Only publisher jobs receive OIDC permissions; builds and index installation
  checks run read-only. Use retained exact-hash artifacts for partial recovery.

The presence of this policy or CI configuration does not mean those remote
settings have been enabled. No remote repository is created by local validation.
