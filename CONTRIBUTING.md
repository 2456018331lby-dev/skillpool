# Contributing to SkillPool

Thanks for contributing to SkillPool.

## Scope

SkillPool is a local-first Python tool for:

- importing and normalizing skills into a unified pool
- previewing, publishing, rolling back, and auditing per-client skill sets
- explaining live vs pool vs published state
- auditing MCP configuration sources without becoming an MCP runtime manager

## Development Principles

- Keep the project dependency-free when possible.
- Prefer Python standard library solutions.
- Keep behavior reversible and auditable.
- Do not add hidden background services.
- Keep client-specific behavior explicit and explainable.

## Local Setup

```powershell
cd %USERPROFILE%\.skill-pool
python -m unittest discover -s tests -v
python skillpool.py status
python skillpool.py inventory
python skillpool.py serve --host 127.0.0.1 --port 8765
```

## Before Opening a PR

- Run tests:
  - `python -m unittest discover -s tests -v`
- If UI files changed, run:
  - `node --check skillpool_app/ui/app.js`
- Update docs when CLI, API, UI, or workflow changes.
- Keep Chinese user-facing copy consistent in the console UI.

## Change Areas

### Core

- [`skillpool_app/core.py`](skillpool_app/core.py)
- Keep registry, clients, publish, rollback, doctor, and inventory logic here.

### CLI

- [`skillpool_app/cli.py`](skillpool_app/cli.py)

### Web Console

- [`skillpool_app/web.py`](skillpool_app/web.py)
- [`skillpool_app/ui/index.html`](skillpool_app/ui/index.html)
- [`skillpool_app/ui/app.js`](skillpool_app/ui/app.js)
- [`skillpool_app/ui/styles.css`](skillpool_app/ui/styles.css)

### Tests

- [`tests/test_skillpool.py`](tests/test_skillpool.py)

## Pull Request Guidance

- Explain why the change is needed.
- List the user-facing behavior change.
- Mention risks and rollback implications.
- Include validation evidence.

## Non-goals

- Do not turn SkillPool into a long-running MCP process manager.
- Do not silently mutate unsupported client MCP configurations.
- Do not make destructive cleanup decisions without an audit path.
