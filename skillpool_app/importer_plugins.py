"""Plugin system for extending SkillPool's import capabilities.

Usage:
    registry = PluginRegistry()
    registry.discover()           # auto-find plugins in this module
    plugin = registry.match("foo.zip")
    if plugin:
        result = plugin.import_from(source)

Core import logic (import_github, import_zip, etc.) remains in mixin_import.py.
Plugins provide a clean extension point for new source types.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


class ImporterPlugin(abc.ABC):
    """Base class for importer plugins."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Short plugin identifier, e.g. 'zip', 'github'."""

    @property
    @abc.abstractmethod
    def supported_schemes(self) -> List[str]:
        """URI schemes this plugin handles, e.g. ['https', 'github:']."""

    @property
    def supported_extensions(self) -> List[str]:
        """File extensions this plugin handles, e.g. ['.zip', '.tar.gz']."""
        return []

    @abc.abstractmethod
    def detect(self, source: str) -> bool:
        """Return True if this plugin can handle *source*."""

    @abc.abstractmethod
    def import_from(self, source: str, **kwargs: Any) -> Dict[str, Any]:
        """Import skills from *source*. Returns an import result dict."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"


class ZipImporterPlugin(ImporterPlugin):
    """Import skills from local .zip archives."""

    @property
    def name(self) -> str:
        return "zip"

    @property
    def supported_schemes(self) -> List[str]:
        return ["file"]

    @property
    def supported_extensions(self) -> List[str]:
        return [".zip"]

    def detect(self, source: str) -> bool:
        return source.lower().endswith(".zip") and Path(source).exists()

    def import_from(self, source: str, **kwargs: Any) -> Dict[str, Any]:
        # Delegates to SkillPool.import_zip at call site
        return {"plugin": self.name, "source": source, "method": "import_zip"}


class GithubImporterPlugin(ImporterPlugin):
    """Import skills from GitHub repositories."""

    @property
    def name(self) -> str:
        return "github"

    @property
    def supported_schemes(self) -> List[str]:
        return ["https"]

    @property
    def supported_extensions(self) -> List[str]:
        return []

    def detect(self, source: str) -> bool:
        source = source.strip().lower()
        return (
            "github.com" in source
            or "/" in source
            and not source.startswith(".")
            and not source.endswith(".zip")
        )

    def import_from(self, source: str, **kwargs: Any) -> Dict[str, Any]:
        return {
            "plugin": self.name,
            "source": source,
            "method": "import_github",
            "ref": kwargs.get("ref"),
            "subdir": kwargs.get("subdir"),
        }


class PluginRegistry:
    """Discover and manage importer plugins."""

    def __init__(self) -> None:
        self._plugins: List[ImporterPlugin] = []

    def register(self, plugin: ImporterPlugin) -> None:
        """Register a plugin instance."""
        if not any(type(p) is type(plugin) for p in self._plugins):
            self._plugins.append(plugin)

    def discover(self) -> None:
        """Auto-register built-in plugins defined in this module."""
        for cls in ImporterPlugin.__subclasses__():
            if not any(type(p) is cls for p in self._plugins):
                self._plugins.append(cls())

    @property
    def plugins(self) -> Sequence[ImporterPlugin]:
        return tuple(self._plugins)

    def match(self, source: str) -> Optional[ImporterPlugin]:
        """Return the first plugin that can handle *source*, or None."""
        for plugin in self._plugins:
            if plugin.detect(source):
                return plugin
        return None

    def match_all(self, source: str) -> List[ImporterPlugin]:
        """Return all plugins that can handle *source*."""
        return [p for p in self._plugins if p.detect(source)]

    def __len__(self) -> int:
        return len(self._plugins)

    def __repr__(self) -> str:
        return f"<PluginRegistry plugins={[p.name for p in self._plugins]}>"
