# Security Policy

## Supported Usage

SkillPool is intended for local, single-user operation on `127.0.0.1`.

Current design assumptions:

- the web console is local-only
- no remote authentication is implemented
- sensitive local paths may be displayed for auditability

## Reporting a Security Issue

Please do not open a public issue for a sensitive vulnerability before maintainers have had time to assess it.

When reporting, include:

- affected command, API, or UI page
- reproduction steps
- whether local files, credentials, or network exposure are involved
- proposed mitigation if available

## Security Boundaries

- SkillPool copies published skills; it does not execute imported skills during inventory or report generation.
- MCP support currently focuses on configuration inventory, not runtime execution control.
- The console should remain bound to `127.0.0.1` by default.

## Hardening Priorities

- keep write actions behind explicit POST routes
- preserve backup-before-publish behavior
- keep rollback inspect available before rollback execution
- avoid hidden remote exposure
