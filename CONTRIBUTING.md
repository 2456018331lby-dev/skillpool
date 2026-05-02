# Contributing to SkillPool

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Development Setup

```bash
# Clone the repository
git clone <your-repo-url> .skill-pool
cd .skill-pool

# Install test dependencies
pip install pytest

# Verify everything works
python -m pytest tests/ -v
```

No external runtime dependencies — SkillPool uses only the Python standard library.

## Running Tests

```bash
# Full test suite
python -m pytest tests/ -v

# Single test
python -m pytest tests/test_skillpool.py::SkillPoolTests::test_publish_prefers_local_skill_and_rewrites_config -v

# Syntax check all modules
python -c "import py_compile; import glob; [py_compile.compile(f, doraise=True) for f in glob.glob('skillpool_app/**/*.py', recursive=True)]"
```

## Code Style

- **PEP 8** with 4-space indentation
- **Type hints** on all public methods
- **Docstrings** on non-trivial functions
- Max line length: 120 characters
- Use `pathlib.Path` for file operations, not `os.path`
- Use `datetime.now(timezone.utc)`, never `datetime.utcnow()`

## Project Structure

```
skillpool_app/
├── core.py              # SkillPool class (thin orchestrator)
├── mixin_state.py       # State persistence (registry, clients, migrations)
├── mixin_console.py     # Desktop console, shortcuts, tool actions
├── mixin_import.py      # GitHub/ZIP/batch import logic
├── mixin_scan.py        # Skill discovery and scan sources
├── mixin_mcp.py         # MCP config management (Codex/Claude/Hermes)
├── mixin_sync.py        # Cross-client sync and conflict resolution
├── mixin_publish.py     # Preview, publish, rollback lifecycle
├── mixin_inventory.py   # Inventory, discovery, cleanup, reports
├── web.py               # HTTP console server
├── cli.py               # CLI argument parsing and dispatch
├── importer_plugins.py  # Plugin system for import sources
└── ui/                  # Web console frontend (HTML/JS/CSS)
```

## Adding a New Client

1. Add entry to `DEFAULT_CLIENTS` in `core.py`
2. Add scan source to `LOCAL_SCAN_SOURCES` if applicable
3. Add MCP config parser if the client has MCP support
4. Add tests covering preview, publish, and rollback

## Adding an Import Plugin

Subclass `ImporterPlugin` in `importer_plugins.py`:

```python
class MyImporterPlugin(ImporterPlugin):
    @property
    def name(self) -> str:
        return "my-source"

    def detect(self, source: str) -> bool:
        return source.startswith("my-scheme://")

    def import_from(self, source: str, **kwargs) -> dict:
        # your import logic
        return {"plugin": self.name, "source": source}
```

## Pull Request Process

1. Fork and create a feature branch
2. Write tests for new functionality
3. Ensure all tests pass: `python -m pytest tests/ -v`
4. Run syntax check (see above)
5. Submit PR with a clear description of changes

## Reporting Issues

- Use GitHub Issues with the provided templates
- Include: Python version, OS, steps to reproduce, expected vs actual behavior
- For security issues, see SECURITY.md

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
