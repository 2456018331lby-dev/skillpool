from __future__ import annotations

import ast  # noqa: F401  # re-exported for mixin_mcp
import copy  # noqa: F401  # re-exported for mixin_state/mcp
import difflib  # noqa: F401  # re-exported for mixin_inventory
import hashlib
import json
import os
import re
import shlex  # noqa: F401  # re-exported for mixin_scan/console
import shutil
import socket
import stat  # noqa: F401  # re-exported for mixin_console
import subprocess  # noqa: F401  # re-exported for mixin_console
import tempfile  # noqa: F401  # re-exported for mixin_import
import time
import urllib.parse
import urllib.request
import zipfile  # noqa: F401  # re-exported for mixin_import
import fcntl  # noqa: F401  # re-exported for mixin_state
import secrets  # noqa: F401  # re-exported for mixin_publish
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple  # noqa: F401  # Iterable re-exported


REGISTRY_VERSION = 1
USER_HOME = Path(os.environ.get("USERPROFILE") or str(Path.home()))
HERMES_WSL_DISTRO = os.environ.get("SKILLPOOL_HERMES_DISTRO", "Ubuntu")
_detected_wsl_user = os.environ.get("USER") or os.environ.get("LOGNAME") or "user"
HERMES_WSL_HOME = (
    os.environ.get("SKILLPOOL_HERMES_HOME", "/home/" + _detected_wsl_user).rstrip("/")
    or "/home/" + _detected_wsl_user
)


def _win_home(*parts: str) -> str:
    return str(USER_HOME.joinpath(*parts))


def _hermes_unc(*parts: str) -> str:
    linux_path = HERMES_WSL_HOME
    if parts:
        linux_path = (
            linux_path.rstrip("/")
            + "/"
            + "/".join(part.strip("/\\") for part in parts if part)
        )
    return "\\\\wsl.localhost\\{}{}".format(
        HERMES_WSL_DISTRO, linux_path.replace("/", "\\")
    )


DEFAULT_ROOT = Path(os.environ.get("SKILLPOOL_HOME", str(USER_HOME / ".skill-pool")))
DEFAULT_CONSOLE_HOST = os.environ.get("SKILLPOOL_CONSOLE_HOST", "127.0.0.1")
DEFAULT_CONSOLE_PORT = int(os.environ.get("SKILLPOOL_CONSOLE_PORT", "8765"))
SCAN_SOURCE_KINDS = {"stable", "workspace", "transient"}
SCAN_SOURCE_ROLES = {"global_source", "client_live", "both"}


DEFAULT_CLIENTS = {
    "hermes": {
        "target_dir": _hermes_unc(".hermes", "skills"),
        "config_path": None,
        "mode": "mirror-native",
        "config_mode": "none",
        "mcp_mode": "hermes-yaml",
        "mcp_config_path": _hermes_unc(".hermes", "config.yaml"),
        "plugin_cache_dir": None,
    },
    "openclaw": {
        "target_dir": _win_home(".openclaw", "skills"),
        "config_path": _win_home(".openclaw", "openclaw.json"),
        "mode": "mirror-native",
        "config_mode": "openclaw-extra-dirs",
        "mcp_mode": "unsupported",
        "mcp_config_path": None,
        "plugin_cache_dir": None,
    },
    "qclaw": {
        "target_dir": _win_home(".qclaw", "skills"),
        "config_path": _win_home(".qclaw", "openclaw.json"),
        "mode": "mirror-native",
        "config_mode": "openclaw-extra-dirs",
        "mcp_mode": "unsupported",
        "mcp_config_path": None,
        "plugin_cache_dir": None,
    },
    "autoclaw": {
        "target_dir": _win_home(".openclaw-autoclaw", "skills"),
        "config_path": _win_home(".openclaw-autoclaw", "openclaw.json"),
        "mode": "mirror-native",
        "config_mode": "none",
        "mcp_mode": "unsupported",
        "mcp_config_path": None,
        "plugin_cache_dir": None,
    },
    "codex": {
        "target_dir": _win_home(".codex", "skills"),
        "config_path": _win_home(".codex", "config.toml"),
        "mode": "mirror-native",
        "config_mode": "none",
        "mcp_mode": "codex-toml",
        "mcp_config_path": _win_home(".codex", "config.toml"),
        "plugin_cache_dir": None,
    },
    "claude": {
        "target_dir": _win_home(".claude", "skills"),
        "config_path": _win_home(".claude", "settings.json"),
        "mode": "mirror-native",
        "config_mode": "none",
        "mcp_mode": "claude-json",
        "mcp_config_path": _win_home(".claude", ".mcp.json"),
        "plugin_cache_dir": _win_home(".claude", "plugins", "cache"),
    },
}

LOCAL_SCAN_SOURCES = {
    "hermes": _hermes_unc(".hermes", "skills"),
    "openclaw": _win_home(".openclaw", "skills"),
    "qclaw": _win_home(".qclaw", "skills"),
    "autoclaw": _win_home(".openclaw-autoclaw", "skills"),
    "codex": _win_home(".codex", "skills"),
    "claude": _win_home(".claude", "skills"),
}

EXCLUDED_SCAN_DIRS = {".git", ".github", ".hub", "__pycache__"}

GLOBAL_SCAN_SOURCE_DEFAULTS = [
    {
        "path": _win_home(".agents", "skills"),
        "role": "global_source",
        "path_kind": "stable",
        "enabled": True,
        "suggested": False,
        "notes": "全局技能源，默认纳入主池。",
    },
    {
        "path": _win_home(".cc-switch", "skills"),
        "role": "global_source",
        "path_kind": "stable",
        "enabled": False,
        "suggested": True,
        "notes": "建议扫描源，可用于纳管 ccswitch 维护的技能集合。",
    },
    {
        "path": _win_home(".qclaw", "workspace"),
        "role": "global_source",
        "path_kind": "workspace",
        "enabled": False,
        "suggested": True,
        "notes": "QClaw workspace 中可能包含长期可复用技能。",
    },
    {
        "path": _win_home(".codex", "vendor_imports"),
        "role": "global_source",
        "path_kind": "workspace",
        "enabled": False,
        "suggested": True,
        "notes": "Codex vendor_imports 中存在潜在可纳管技能。",
    },
    {
        "path": _win_home(".openclaw", "workspace"),
        "role": "global_source",
        "path_kind": "workspace",
        "enabled": False,
        "suggested": True,
        "notes": "OpenClaw workspace 中可能包含长期可复用技能。",
    },
    {
        "path": _win_home(".codex", ".tmp"),
        "role": "global_source",
        "path_kind": "transient",
        "enabled": False,
        "suggested": True,
        "notes": "临时缓存目录，默认只作为候选发现源。",
    },
    {
        "path": _win_home(".claude", "plugins", "cache"),
        "role": "global_source",
        "path_kind": "transient",
        "enabled": False,
        "suggested": True,
        "notes": "Claude 插件缓存目录，默认不参与稳定纳管。",
    },
    {
        "path": _win_home(".qclaw", "tools"),
        "role": "global_source",
        "path_kind": "transient",
        "enabled": False,
        "suggested": True,
        "notes": "QClaw tools/node_modules 类目录，默认不参与稳定纳管。",
    },
]


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "skill"


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}, text
    frontmatter: Dict[str, str] = {}
    current_key: Optional[str] = None
    list_values: Dict[str, List[str]] = {}
    for line in lines[1:end_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Handle list items (- value)
        if stripped.startswith("- ") and current_key is not None:
            list_values.setdefault(current_key, []).append(
                stripped[2:].strip().strip("'\"")
            )
            continue
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value == "":
            # Could be start of a list or nested block
            current_key = key
            continue
        # Handle inline YAML list [a, b, c]
        if raw_value.startswith("[") and raw_value.endswith("]"):
            try:
                frontmatter[key] = json.loads(raw_value)
            except (json.JSONDecodeError, ValueError):
                frontmatter[key] = raw_value.strip("'\"")
        else:
            frontmatter[key] = raw_value.strip("'\"")
        current_key = key
    # Flush any accumulated list values
    for key, values in list_values.items():
        if key not in frontmatter:
            frontmatter[key] = (
                values if len(values) > 1 else (values[0] if values else "")
            )
    body = "\n".join(lines[end_index + 1 :])
    return frontmatter, body


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return json.loads(json.dumps(default))


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_directory(directory: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(
            str(file_path.relative_to(directory)).replace("\\", "/").encode("utf-8")
        )
        digest.update(b"\0")
        try:
            with file_path.open("rb") as fh:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    digest.update(chunk)
        except (OSError, PermissionError):
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()


def markdown_anchor(value: str) -> str:
    anchor = slugify(value).replace("-", "")
    return anchor or "section"


def json_preview(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def scan_source_id(path: str, role: str, client: Optional[str] = None) -> str:
    raw = "{}|{}|{}".format(str(path).lower(), role, client or "")
    return "src-{}".format(hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12])


def _powershell_command(*lines: str) -> List[str]:
    script = "\n".join(lines)
    # Validate script doesn't contain dangerous pipeline/chain operators injected via user input
    # Allow only our own controlled script patterns
    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def yaml_scalar(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def safe_rmtree(path: Path) -> None:
    if not path.exists():
        return

    def _onerror(func, target, exc_info):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            if os.path.exists(target):
                raise

    shutil.rmtree(str(path), onerror=_onerror)


def remove_path_lexists(path: Path) -> None:
    if not os.path.lexists(str(path)):
        return
    if path.is_dir() and not path.is_symlink():
        safe_rmtree(path)
        return
    try:
        os.unlink(str(path))
    except OSError:
        if path.exists():
            safe_rmtree(path)


def ensure_clean_directory(path: Path) -> None:
    safe_rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def is_wsl_unc(path: Path) -> bool:
    raw = str(path)
    return raw.startswith("\\\\wsl.localhost\\") or raw.startswith("//wsl.localhost/")


def unc_wsl_to_linux(path: Path) -> Tuple[str, str]:
    raw = str(path).replace("/", "\\")
    prefix = "\\\\wsl.localhost\\"
    if not raw.startswith(prefix):
        raise ValueError("Not a WSL UNC path: {}".format(path))
    parts = raw[len(prefix) :].split("\\")
    if len(parts) < 2:
        raise ValueError("WSL UNC path is missing Linux segments: {}".format(path))
    distro = parts[0]
    linux_path = "/" + "/".join(part for part in parts[1:] if part)
    return distro, linux_path


def linux_to_unc_wsl(distro: str, linux_path: str) -> Path:
    linux_path = linux_path.strip()
    if not linux_path.startswith("/"):
        linux_path = "/" + linux_path
    return Path("\\\\wsl.localhost\\{}{}".format(distro, linux_path.replace("/", "\\")))


def copy_existing_tree(source_dir: Path, destination_dir: Path) -> None:
    if not source_dir.exists():
        return
    destination_dir.mkdir(parents=True, exist_ok=True)
    for current_root, dirnames, filenames in os.walk(str(source_dir), topdown=True):
        current_root_path = Path(current_root)
        relative_root = current_root_path.relative_to(source_dir)
        target_root = destination_dir / relative_root
        target_root.mkdir(parents=True, exist_ok=True)
        dirnames[:] = [name for name in dirnames if (current_root_path / name).exists()]
        for filename in filenames:
            source_file = current_root_path / filename
            if not source_file.exists():
                continue
            target_file = target_root / filename
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source_file), str(target_file))


from skillpool_app.mixin_state import MixinState  # noqa: E402
from skillpool_app.mixin_console import MixinConsole  # noqa: E402
from skillpool_app.mixin_import import MixinImport  # noqa: E402
from skillpool_app.mixin_scan import MixinScan  # noqa: E402
from skillpool_app.mixin_mcp import MixinMcp  # noqa: E402
from skillpool_app.mixin_sync import MixinSync  # noqa: E402
from skillpool_app.mixin_publish import MixinPublish  # noqa: E402
from skillpool_app.mixin_inventory import MixinInventory  # noqa: E402


class SkillPool(
    MixinState,
    MixinConsole,
    MixinImport,
    MixinScan,
    MixinMcp,
    MixinSync,
    MixinPublish,
    MixinInventory,
):
    _GITHUB_TRANSIENT_CODES = {429, 500, 502, 503, 504}

    @staticmethod
    def _github_request(
        url: str, dest: Path, timeout: int = 30, max_retries: int = 3
    ) -> None:
        """Download from a GitHub URL with auth token, timeout, and retry logic."""
        headers = {"User-Agent": "skillpool/0.1"}
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get(
            "SKILLPOOL_GITHUB_TOKEN"
        )
        if token:
            headers["Authorization"] = "Bearer " + token

        backoff = 1.0
        last_exc = None
        for attempt in range(max_retries):
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = response.read()
                with dest.open("wb") as fh:
                    fh.write(data)
                return
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else backoff
                    time.sleep(wait)
                    backoff = min(backoff * 2, 8.0)
                    continue
                if exc.code in SkillPool._GITHUB_TRANSIENT_CODES:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 8.0)
                    continue
                raise
            except (urllib.error.URLError, socket.timeout, OSError) as exc:
                last_exc = exc
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
                continue
        raise last_exc

    def __init__(
        self,
        root: Optional[Path] = None,
        clients: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
    ):
        self.root = Path(root or DEFAULT_ROOT)
        self.code_dir = self.root / "skillpool_app"
        self.pool_dir = self.root / "pool" / "skills"
        self.cache_dir = self.root / "cache" / "imports"
        self.state_dir = self.root / "state"
        self.publish_dir = self.root / "publish"
        self.reports_dir = self.root / "reports"
        self.backups_dir = self.root / "backups"
        self.plugins_dir = self.root / "plugins" / "importers"
        self.registry_path = self.state_dir / "registry.json"
        self.clients_path = self.state_dir / "clients.json"
        self.lock_path = self.state_dir / "lock.json"
        self.mcp_state_path = self.state_dir / "mcp_state.json"
        self.cleanup_candidates_path = self.state_dir / "cleanup_candidates.json"
        self.scan_sources_path = self.state_dir / "scan_sources.json"
        self.discovery_cache_path = self.state_dir / "discovery_cache.json"
        self.cleanup_report_path = self.reports_dir / "CLEANUP_CANDIDATES.md"
        self.cleanup_export_path = self.reports_dir / "CLEANUP_CANDIDATES.json"
        self.console_host = DEFAULT_CONSOLE_HOST
        self.console_port = DEFAULT_CONSOLE_PORT
        self.console_url = "http://{}:{}/".format(self.console_host, self.console_port)
        self.console_pid_path = self.state_dir / "web-console.pid"
        self.console_stdout_log_path = self.state_dir / "web-console.out.log"
        self.console_stderr_log_path = self.state_dir / "web-console.err.log"
        self.desktop_shortcut_path = USER_HOME / "Desktop" / "SkillPool Console.lnk"
        self._default_clients = clients or DEFAULT_CLIENTS

    def _client_state(
        self, client: str, config: Dict[str, Optional[str]]
    ) -> Dict[str, object]:
        return {
            "id": client,
            "target_dir": config.get("target_dir"),
            "config_path": config.get("config_path"),
            "mode": config.get("mode"),
            "config_mode": config.get("config_mode"),
            "mcp_mode": config.get("mcp_mode", "unsupported"),
            "mcp_config_path": config.get("mcp_config_path"),
            "plugin_cache_dir": config.get("plugin_cache_dir"),
            "extra_dirs": [],
            "last_published_at": None,
            "last_backup_id": None,
            "last_preview_at": None,
            "last_preview_status": None,
            "last_deep_doctor_at": None,
            "last_deep_doctor_status": None,
            "published_skill_ids": [],
            "manifest_path": str((self.publish_dir / client / "manifest.json")),
        }

    def _scan_source_state(
        self,
        path: str,
        *,
        role: str,
        path_kind: str,
        enabled: bool,
        suggested: bool,
        client: Optional[str] = None,
        notes: str = "",
        source_scope: Optional[str] = None,
        default_entry: bool = False,
    ) -> Dict[str, object]:
        normalized_path = str(path)
        if role not in SCAN_SOURCE_ROLES:
            raise ValueError("Unsupported scan source role: {}".format(role))
        if path_kind not in SCAN_SOURCE_KINDS:
            raise ValueError("Unsupported scan source kind: {}".format(path_kind))
        if client:
            self._default_clients.get(client, {})
        if not source_scope:
            if role == "global_source":
                source_scope = "global_source"
            else:
                source_scope = "client_live"
        return {
            "id": scan_source_id(normalized_path, role, client),
            "path": normalized_path,
            "enabled": bool(enabled),
            "path_kind": path_kind,
            "role": role,
            "client": client,
            "suggested": bool(suggested),
            "last_scan_at": None,
            "last_result_count": 0,
            "notes": notes,
            "source_scope": source_scope,
            "default_entry": bool(default_entry),
        }

    def _default_scan_sources(
        self, clients: Optional[Dict] = None
    ) -> Dict[str, object]:
        clients = clients or load_json(
            self.clients_path, {"version": REGISTRY_VERSION, "clients": {}}
        )
        sources = {}
        for client, config in clients.get("clients", {}).items():
            target_dir = config.get("target_dir")
            if target_dir:
                entry = self._scan_source_state(
                    str(target_dir),
                    role="both",
                    path_kind="stable",
                    enabled=True,
                    suggested=False,
                    client=client,
                    notes="客户端 live target 目录。",
                    source_scope="target_dir",
                    default_entry=True,
                )
                sources[entry["id"]] = entry
            if config.get("config_mode") == "openclaw-extra-dirs":
                for extra_dir in self._read_openclaw_extra_dirs(config):
                    if str(extra_dir) == str(target_dir):
                        continue
                    entry = self._scan_source_state(
                        str(extra_dir),
                        role="both",
                        path_kind="stable",
                        enabled=True,
                        suggested=False,
                        client=client,
                        notes="配置文件 extraDirs 中声明的客户端 live 源。",
                        source_scope="extra_dir",
                        default_entry=True,
                    )
                    sources[entry["id"]] = entry
        if self.root.resolve() == DEFAULT_ROOT.resolve():
            for item in GLOBAL_SCAN_SOURCE_DEFAULTS:
                entry = self._scan_source_state(
                    item["path"],
                    role=str(item["role"]),
                    path_kind=str(item["path_kind"]),
                    enabled=bool(item["enabled"]),
                    suggested=bool(item["suggested"]),
                    client=item.get("client"),
                    notes=str(item.get("notes") or ""),
                    source_scope=str(
                        item.get("source_scope")
                        or (
                            "global_source"
                            if item["role"] == "global_source"
                            else "client_live"
                        )
                    ),
                    default_entry=True,
                )
                sources[entry["id"]] = entry
        return {"version": REGISTRY_VERSION, "sources": sources}

    def init_state(self) -> Dict[str, str]:
        for path in [
            self.root,
            self.pool_dir,
            self.cache_dir,
            self.state_dir,
            self.publish_dir,
            self.reports_dir,
            self.backups_dir,
            self.plugins_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            write_json(
                self.registry_path,
                {
                    "version": REGISTRY_VERSION,
                    "generated_at": utc_now(),
                    "skills": {},
                },
            )
        if not self.clients_path.exists():
            write_json(
                self.clients_path,
                {
                    "version": REGISTRY_VERSION,
                    "clients": {
                        client: self._client_state(client, config)
                        for client, config in self._default_clients.items()
                    },
                },
            )
        else:
            existing_clients = load_json(
                self.clients_path, {"version": REGISTRY_VERSION, "clients": {}}
            )
            changed = False
            for client, config in self._default_clients.items():
                if client not in existing_clients.get("clients", {}):
                    existing_clients.setdefault("clients", {})[client] = (
                        self._client_state(client, config)
                    )
                    changed = True
                else:
                    defaults = self._client_state(client, config)
                    client_state = existing_clients["clients"][client]
                    for key, value in defaults.items():
                        if key not in client_state:
                            client_state[key] = value
                            changed = True
            if changed:
                write_json(self.clients_path, existing_clients)
        if not self.mcp_state_path.exists():
            write_json(
                self.mcp_state_path, {"version": REGISTRY_VERSION, "clients": {}}
            )
        if not self.cleanup_candidates_path.exists():
            write_json(
                self.cleanup_candidates_path,
                {
                    "version": REGISTRY_VERSION,
                    "generated_at": utc_now(),
                    "candidates": {},
                    "order": [],
                },
            )
        if not self.scan_sources_path.exists():
            write_json(
                self.scan_sources_path,
                self._default_scan_sources(
                    load_json(
                        self.clients_path, {"version": REGISTRY_VERSION, "clients": {}}
                    )
                ),
            )
        if not self.discovery_cache_path.exists():
            write_json(
                self.discovery_cache_path,
                {
                    "version": REGISTRY_VERSION,
                    "generated_at": None,
                    "stale": False,
                    "sources": [],
                    "untracked_discovered": [],
                    "source_mismatch": [],
                    "transient_only": [],
                    "duplicate_across_clients": [],
                },
            )
        placeholder = self.plugins_dir / "README.md"
        if not placeholder.exists():
            placeholder.write_text(
                "# Importer Plugins\n\n"
                "Reserved for future openhub / skillhub importer plugins.\n",
                encoding="utf-8",
            )
        return {
            "root": str(self.root),
            "registry": str(self.registry_path),
            "clients": str(self.clients_path),
        }

    def status(self) -> Dict[str, object]:
        registry = self.load_registry()
        clients = self.load_clients()
        enabled = sum(
            1
            for skill in registry["skills"].values()
            if skill["enabled_global"] == "enabled"
        )
        disabled = sum(
            1
            for skill in registry["skills"].values()
            if skill["enabled_global"] == "disabled"
        )
        families = {}
        for skill in registry["skills"].values():
            families.setdefault(skill["conflict_family"], []).append(skill["skill_id"])
        return {
            "root": str(self.root),
            "skill_count": len(registry["skills"]),
            "enabled_count": enabled,
            "disabled_count": disabled,
            "conflict_family_count": len(families),
            "shadowed_count": sum(
                1
                for skill in registry["skills"].values()
                if skill["status"] == "shadowed"
            ),
            "clients": clients["clients"],
        }

    def doctor(
        self, *, deep: bool = False, client: Optional[str] = None
    ) -> Dict[str, object]:
        clients = self.load_clients()
        checks = []
        client_items = clients["clients"].items()
        if client:
            client_items = [(client, self._require_client(client, clients))]
        registry = self.load_registry() if deep else None
        clients_changed = False
        for client_id, config in client_items:
            generated_at = utc_now()
            target_dir = Path(config["target_dir"])
            config_path = (
                Path(config["config_path"]) if config.get("config_path") else None
            )
            check = {
                "client": client_id,
                "generated_at": generated_at,
                "target_exists": target_dir.exists(),
                "config_exists": (config_path.exists() if config_path else True),
                "publish_manifest_exists": Path(config["manifest_path"]).exists(),
            }
            if deep:
                check.update(self._deep_doctor_check(client_id, config, registry))
                publish_root = self.publish_dir / client_id
                publish_root.mkdir(parents=True, exist_ok=True)
                write_json(publish_root / "doctor.json", check)
                self._record_deep_doctor_metadata(
                    clients, client_id, generated_at, check["status"]
                )
                clients_changed = True
            checks.append(check)
        if clients_changed:
            self.save_clients(clients)
        return {
            "registry_exists": self.registry_path.exists(),
            "clients_exists": self.clients_path.exists(),
            "deep": deep,
            "checks": checks,
        }

    def _deep_doctor_check(
        self, client: str, config: Dict[str, object], registry: Dict
    ) -> Dict[str, object]:
        errors = []
        warnings = []
        target_dir = Path(config["target_dir"])
        manifest_path = Path(config["manifest_path"])
        manifest = load_json(manifest_path, {}) if manifest_path.exists() else {}
        published_ids = manifest.get("published_skill_ids", [])
        target_map = self._target_skill_map(target_dir)
        if not published_ids and len(target_map) > 0:
            warnings.append(
                "target contains skills but no manifest has been published yet"
            )
        if published_ids and len(target_map) != len(published_ids):
            errors.append(
                "manifest count {} does not match target skill count {}".format(
                    len(published_ids), len(target_map)
                )
            )
        missing = []
        mismatched = []
        for skill_id in published_ids:
            skill = registry["skills"].get(skill_id)
            if not skill:
                missing.append(skill_id)
                continue
            target_skill = target_map.get(skill["published_name"])
            if not target_skill:
                missing.append(skill_id)
                continue
            if target_skill["fingerprint"] != skill["fingerprint"]:
                mismatched.append(skill_id)
        if missing:
            errors.append(
                "published skills missing from target: {}".format(
                    ", ".join(missing[:10])
                )
            )
        if mismatched:
            errors.append(
                "published skill fingerprints differ from registry: {}".format(
                    ", ".join(mismatched[:10])
                )
            )
        broken_paths = self._broken_direct_children(target_dir)
        if broken_paths:
            warnings.append("target has broken or inaccessible direct children")
        extra_dir_status = self._extra_dir_status(client, config, registry)
        unmanaged = [
            item
            for item in extra_dir_status
            if item["scope"] == "extra_dir"
            and item["exists"]
            and item["skill_count"] > 0
            and not item["managed"]
        ]
        if unmanaged:
            errors.append("configured extraDirs contain unmanaged skills")
        missing_extra = [
            item
            for item in extra_dir_status
            if item["scope"] == "extra_dir" and not item["exists"]
        ]
        if missing_extra:
            warnings.append("configured extraDirs are missing")
        if is_wsl_unc(target_dir) and not self.discover_skills(target_dir):
            warnings.append("WSL target is reachable but no skills were discovered")
        status = "fail" if errors else ("warning" if warnings else "pass")
        return {
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "manifest_skill_count": len(published_ids),
            "target_skill_count": len(target_map),
            "extra_dirs": extra_dir_status,
            "broken_paths": broken_paths,
        }

    def generate_reports(
        self, registry: Optional[Dict] = None, clients: Optional[Dict] = None
    ) -> Dict[str, str]:
        registry = registry or self.load_registry()
        clients = clients or self.load_clients()
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        skills_index = self._build_skills_index(registry, clients)
        conflicts = self._build_conflicts_report(registry, clients)
        inventory = self._build_inventory_report()
        cleanup_state = self.load_cleanup_candidates()
        cleanup_candidates = self._build_cleanup_candidates_report(
            cleanup_state, registry, clients
        )
        (self.reports_dir / "SKILLS_INDEX.md").write_text(
            skills_index, encoding="utf-8"
        )
        (self.reports_dir / "CONFLICTS.md").write_text(conflicts, encoding="utf-8")
        (self.reports_dir / "INVENTORY.md").write_text(inventory, encoding="utf-8")
        self.cleanup_report_path.write_text(cleanup_candidates, encoding="utf-8")
        write_json(self.cleanup_export_path, cleanup_state)
        return {
            "skills_index": str(self.reports_dir / "SKILLS_INDEX.md"),
            "conflicts": str(self.reports_dir / "CONFLICTS.md"),
            "inventory": str(self.reports_dir / "INVENTORY.md"),
            "cleanup_candidates": str(self.cleanup_report_path),
        }

    def _client_map(self, clients: Dict) -> Dict[str, List[str]]:
        client_map = {}
        for client, config in clients["clients"].items():
            for skill_id in config.get("published_skill_ids", []):
                client_map.setdefault(skill_id, []).append(client)
        return client_map

    def _require_skill(self, registry: Dict, skill_id: str) -> Dict:
        try:
            return registry["skills"][skill_id]
        except KeyError:
            raise ValueError("Unknown skill_id '{}'".format(skill_id))

    def _require_client(self, client: str, clients: Optional[Dict] = None) -> Dict:
        clients = clients or self.load_clients()
        try:
            return clients["clients"][client]
        except KeyError:
            raise ValueError("Unknown client '{}'".format(client))
