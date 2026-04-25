from __future__ import annotations

import ast
import copy
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


REGISTRY_VERSION = 1
USER_HOME = Path(os.environ.get("USERPROFILE") or str(Path.home()))
HERMES_WSL_DISTRO = os.environ.get("SKILLPOOL_HERMES_DISTRO", "Ubuntu")
HERMES_WSL_HOME = os.environ.get("SKILLPOOL_HERMES_HOME", "/home/mzls").rstrip("/") or "/home/mzls"


def _win_home(*parts: str) -> str:
    return str(USER_HOME.joinpath(*parts))


def _hermes_unc(*parts: str) -> str:
    linux_path = HERMES_WSL_HOME
    if parts:
        linux_path = linux_path.rstrip("/") + "/" + "/".join(part.strip("/\\") for part in parts if part)
    return "\\\\wsl.localhost\\{}{}".format(HERMES_WSL_DISTRO, linux_path.replace("/", "\\"))


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
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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
    frontmatter = {}
    for line in lines[1:end_index]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        frontmatter[key.strip()] = raw_value.strip().strip("'\"")
    body = "\n".join(lines[end_index + 1 :])
    return frontmatter, body


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_directory(directory: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(str(file_path.relative_to(directory)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
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
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]


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


class SkillPool:
    def __init__(self, root: Optional[Path] = None, clients: Optional[Dict[str, Dict[str, Optional[str]]]] = None):
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

    def _client_state(self, client: str, config: Dict[str, Optional[str]]) -> Dict[str, object]:
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

    def _default_scan_sources(self, clients: Optional[Dict] = None) -> Dict[str, object]:
        clients = clients or load_json(self.clients_path, {"version": REGISTRY_VERSION, "clients": {}})
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
                    source_scope=str(item.get("source_scope") or ("global_source" if item["role"] == "global_source" else "client_live")),
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
            existing_clients = load_json(self.clients_path, {"version": REGISTRY_VERSION, "clients": {}})
            changed = False
            for client, config in self._default_clients.items():
                if client not in existing_clients.get("clients", {}):
                    existing_clients.setdefault("clients", {})[client] = self._client_state(client, config)
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
            write_json(self.mcp_state_path, {"version": REGISTRY_VERSION, "clients": {}})
        if not self.cleanup_candidates_path.exists():
            write_json(
                self.cleanup_candidates_path,
                {"version": REGISTRY_VERSION, "generated_at": utc_now(), "candidates": {}, "order": []},
            )
        if not self.scan_sources_path.exists():
            write_json(self.scan_sources_path, self._default_scan_sources(load_json(self.clients_path, {"version": REGISTRY_VERSION, "clients": {}})))
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

    def _console_pid_value(self) -> Tuple[Optional[int], bool, Optional[str]]:
        self.init_state()
        if not self.console_pid_path.exists():
            return None, False, "pid file missing"
        raw = self.console_pid_path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            return None, True, "pid file empty"
        try:
            return int(raw), True, None
        except ValueError:
            return None, True, "pid file invalid"

    def _query_process_command_line(self, pid: int) -> Optional[str]:
        if pid <= 0:
            return None
        try:
            result = subprocess.run(
                _powershell_command(
                    "$process = Get-CimInstance Win32_Process -Filter \"ProcessId = {}\"".format(pid),
                    "if ($null -eq $process) { exit 1 }",
                    "[string]$process.CommandLine",
                ),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        command_line = (result.stdout or "").strip()
        return command_line or None

    def _is_console_online(self) -> bool:
        try:
            with socket.create_connection((self.console_host, self.console_port), timeout=0.6):
                return True
        except OSError:
            return False

    def console_status(self) -> Dict[str, object]:
        pid, has_pid_file, pid_error = self._console_pid_value()
        command_line = self._query_process_command_line(pid or 0) if pid else None
        matches_skillpool = bool(command_line and "skillpool.py" in command_line and " serve" in " {} ".format(command_line))
        online = self._is_console_online()

        management = "stopped"
        message = "SkillPool 控制台已停止。"
        if matches_skillpool:
            management = "managed"
            message = "SkillPool 控制台正在运行，并且由 state/web-console.pid 管理。"
        elif online:
            management = "unmanaged"
            message = "控制台可以访问，但 PID 文件缺失或已失效。"
        elif has_pid_file:
            management = "stale"
            message = "PID 文件存在，但没有指向可用的 skillpool.py serve 进程。"
            if pid_error:
                message = "{} ({})".format(message, pid_error)

        return {
            "status": "running" if online else "stopped",
            "management": management,
            "pid": pid,
            "command_line": command_line,
            "url": self.console_url,
            "pid_path": str(self.console_pid_path),
            "stdout_log": str(self.console_stdout_log_path),
            "stderr_log": str(self.console_stderr_log_path),
            "message": message,
            "has_pid_file": has_pid_file,
            "is_online": online,
        }

    def _read_shortcut_target(self, shortcut_path: Path) -> Optional[str]:
        if not shortcut_path.exists():
            return None
        try:
            result = subprocess.run(
                _powershell_command(
                    "$shell = New-Object -ComObject WScript.Shell",
                    "$shortcut = $shell.CreateShortcut('{}')".format(str(shortcut_path).replace("'", "''")),
                    "[string]$shortcut.TargetPath",
                ),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        target = (result.stdout or "").strip()
        return target or None

    def desktop_shortcut_status(self) -> Dict[str, object]:
        shortcut_path = self.desktop_shortcut_path
        expected_target = str(self.root / "open-console.cmd")
        exists = shortcut_path.exists()
        target_path = self._read_shortcut_target(shortcut_path) if exists else None

        status = "missing"
        message = "桌面快捷方式不存在。"
        if exists and target_path:
            status = "ready" if Path(target_path) == Path(expected_target) else "mismatch"
            message = (
                "桌面快捷方式已就绪。"
                if status == "ready"
                else "桌面快捷方式存在，但目标不是当前 SkillPool 的 open-console.cmd。"
            )
        elif exists:
            status = "unknown"
            message = "桌面快捷方式存在，但当前无法解析它的目标路径。"

        return {
            "status": status,
            "path": str(shortcut_path),
            "exists": exists,
            "target_path": target_path,
            "expected_target": expected_target,
            "message": message,
        }

    def create_desktop_shortcut(self) -> Dict[str, object]:
        self.init_state()
        shortcut_path = self.desktop_shortcut_path
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        target = self.root / "open-console.cmd"
        icon_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "SHELL32.dll"
        result = subprocess.run(
            _powershell_command(
                "$shell = New-Object -ComObject WScript.Shell",
                "$shortcut = $shell.CreateShortcut('{}')".format(str(shortcut_path).replace("'", "''")),
                "$shortcut.TargetPath = '{}'".format(str(target).replace("'", "''")),
                "$shortcut.WorkingDirectory = '{}'".format(str(self.root).replace("'", "''")),
                "$shortcut.Description = 'Open SkillPool local console'",
                "$shortcut.IconLocation = '{},220'".format(str(icon_path).replace("'", "''")),
                "$shortcut.Save()",
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("创建桌面快捷方式失败: {}".format((result.stderr or result.stdout or "").strip() or "unknown error"))
        return self.desktop_shortcut_status()

    def manual_commands(self) -> List[Dict[str, object]]:
        shortcut = self.desktop_shortcut_status()
        return [
            {
                "id": "desktop_shortcut",
                "title": "桌面快捷方式",
                "description": "双击桌面的 SkillPool Console 快捷方式，适合日常启动控制台。",
                "command_preview": shortcut["path"],
                "manual": True,
                "copy_text": shortcut["path"],
                "status": shortcut["status"],
            },
            {
                "id": "open_console",
                "title": "启动控制台",
                "description": "启动本地 SkillPool 服务，并自动打开浏览器。",
                "command_preview": str(self.root / "open-console.cmd"),
                "manual": True,
                "copy_text": str(self.root / "open-console.cmd"),
            },
            {
                "id": "console_status",
                "title": "查看控制台状态",
                "description": "检查控制台服务、PID 文件和日志路径。",
                "command_preview": str(self.root / "console-status.cmd"),
                "manual": True,
                "copy_text": str(self.root / "console-status.cmd"),
            },
            {
                "id": "stop_console_manual",
                "title": "停止控制台",
                "description": "关闭由 SkillPool 管理的本地服务。",
                "command_preview": str(self.root / "stop-console.cmd"),
                "manual": True,
                "copy_text": str(self.root / "stop-console.cmd"),
            },
        ]

    def tool_actions(self) -> Dict[str, object]:
        return {
            "actions": [
                {
                    "id": "preview_all",
                    "title": "全部预览",
                    "category": "安全检查",
                    "risk_level": "safe",
                    "description": "对全部客户端生成预览，不执行发布。",
                    "command_preview": "python skillpool.py preview --all",
                    "online_required": True,
                },
                {
                    "id": "doctor_all_deep",
                    "title": "深度体检",
                    "category": "安全检查",
                    "risk_level": "warning",
                    "description": "运行全部客户端的 deep doctor，检查目标目录、manifest 和配置一致性。",
                    "command_preview": "python skillpool.py doctor --deep",
                    "online_required": True,
                },
                {
                    "id": "cleanup_scan",
                    "title": "扫描清理候选项",
                    "category": "维护",
                    "risk_level": "safe",
                    "description": "重新生成 pool_only、shadowed、source_mismatch 等候选清单。",
                    "command_preview": "python skillpool.py cleanup scan",
                    "online_required": True,
                },
                {
                    "id": "regenerate_reports",
                    "title": "重建全部报告",
                    "category": "维护",
                    "risk_level": "safe",
                    "description": "重建技能索引、冲突、盘点和清理候选报告。",
                    "command_preview": "python skillpool.py report",
                    "online_required": True,
                },
                {
                    "id": "codex_mcp_dedupe",
                    "title": "Codex MCP 去重",
                    "category": "MCP",
                    "risk_level": "warning",
                    "description": "审计并合并 Codex 里的重复 MCP server 配置项。",
                    "command_preview": "python skillpool.py mcp dedupe codex",
                    "online_required": True,
                },
                {
                    "id": "recreate_shortcut",
                    "title": "重建桌面快捷方式",
                    "category": "桌面入口",
                    "risk_level": "safe",
                    "description": "重新生成桌面的 SkillPool Console 快捷方式。",
                    "command_preview": "powershell -File create-desktop-shortcut.ps1",
                    "online_required": True,
                },
                {
                    "id": "stop_console",
                    "title": "停止当前服务",
                    "category": "服务控制",
                    "risk_level": "warning",
                    "description": "停止当前 SkillPool 控制台服务。页面会随之离线。",
                    "command_preview": "stop-console.cmd",
                    "online_required": True,
                },
            ]
        }

    def run_tool_action(self, action_id: str) -> Dict[str, object]:
        action_id = (action_id or "").strip()
        if action_id == "preview_all":
            status = self.status()
            return {
                "action_id": action_id,
                "results": [self.preview(client, detailed=True) for client in sorted(status.get("clients", {}).keys())],
            }
        if action_id == "doctor_all_deep":
            clients = sorted(self.load_clients().get("clients", {}).keys())
            return {"action_id": action_id, "results": [self.doctor(deep=True, client=client) for client in clients]}
        if action_id == "cleanup_scan":
            result = self.cleanup_scan()
            return {"action_id": action_id, "result": result}
        if action_id == "regenerate_reports":
            result = self.get_reports()
            return {"action_id": action_id, "result": result}
        if action_id == "codex_mcp_dedupe":
            result = self.mcp_dedupe_codex()
            return {"action_id": action_id, "result": result}
        if action_id == "recreate_shortcut":
            result = self.create_desktop_shortcut()
            return {"action_id": action_id, "result": result}
        if action_id == "stop_console":
            return {"action_id": action_id, "requires_server_shutdown": True}
        raise ValueError("Unsupported tool action '{}'".format(action_id))

    def system_status(self) -> Dict[str, object]:
        return {
            "console": self.console_status(),
            "shortcut": self.desktop_shortcut_status(),
            "manual_commands": self.manual_commands(),
        }

    def load_registry(self) -> Dict:
        self.init_state()
        registry = load_json(
            self.registry_path,
            {
                "version": REGISTRY_VERSION,
                "generated_at": utc_now(),
                "skills": {},
            },
        )
        if self._migrate_registry(registry):
            self.save_registry(registry)
        return registry

    def save_registry(self, registry: Dict) -> None:
        registry["generated_at"] = utc_now()
        write_json(self.registry_path, registry)
        self.invalidate_discovery_cache()

    def load_clients(self) -> Dict:
        self.init_state()
        clients = load_json(self.clients_path, {"version": REGISTRY_VERSION, "clients": {}})
        if self._migrate_clients(clients):
            self.save_clients(clients)
        return clients

    def save_clients(self, clients: Dict) -> None:
        clients["generated_at"] = utc_now()
        write_json(self.clients_path, clients)

    def load_mcp_state(self) -> Dict:
        self.init_state()
        return load_json(self.mcp_state_path, {"version": REGISTRY_VERSION, "clients": {}})

    def save_mcp_state(self, mcp_state: Dict) -> None:
        mcp_state["generated_at"] = utc_now()
        write_json(self.mcp_state_path, mcp_state)

    def load_cleanup_candidates(self) -> Dict:
        self.init_state()
        return load_json(
            self.cleanup_candidates_path,
            {"version": REGISTRY_VERSION, "generated_at": utc_now(), "candidates": {}, "order": []},
        )

    def save_cleanup_candidates(self, cleanup_state: Dict) -> None:
        cleanup_state["generated_at"] = utc_now()
        write_json(self.cleanup_candidates_path, cleanup_state)

    def load_scan_sources(self) -> Dict:
        self.init_state()
        scan_sources = load_json(self.scan_sources_path, {"version": REGISTRY_VERSION, "sources": {}})
        clients = load_json(self.clients_path, {"version": REGISTRY_VERSION, "clients": {}})
        if self._migrate_scan_sources(scan_sources, clients):
            self.save_scan_sources(scan_sources)
        return scan_sources

    def save_scan_sources(self, scan_sources: Dict) -> None:
        scan_sources["generated_at"] = utc_now()
        write_json(self.scan_sources_path, scan_sources)
        self.invalidate_discovery_cache()

    def load_discovery_cache(self) -> Dict:
        self.init_state()
        return load_json(
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

    def save_discovery_cache(self, discovery_cache: Dict) -> None:
        discovery_cache["version"] = REGISTRY_VERSION
        write_json(self.discovery_cache_path, discovery_cache)

    def invalidate_discovery_cache(self) -> None:
        cache = self.load_discovery_cache()
        cache["stale"] = True
        self.save_discovery_cache(cache)

    def _record_preview_metadata(self, clients: Dict, client: str, generated_at: str, status: str) -> None:
        client_state = self._require_client(client, clients)
        client_state["last_preview_at"] = generated_at
        client_state["last_preview_status"] = status
        clients["clients"][client] = client_state

    def _record_deep_doctor_metadata(self, clients: Dict, client: str, generated_at: str, status: str) -> None:
        client_state = self._require_client(client, clients)
        client_state["last_deep_doctor_at"] = generated_at
        client_state["last_deep_doctor_status"] = status
        clients["clients"][client] = client_state

    def _migrate_registry(self, registry: Dict) -> bool:
        changed = False
        for skill in registry.get("skills", {}).values():
            source_type = skill.get("source_type", "")
            source_locator = skill.get("source_locator", "")
            inferred_client = None
            if source_type == "local-scan" and ":" in source_locator:
                inferred_client = source_locator.split(":", 1)[0]
            defaults = {
                "available_clients": ([inferred_client] if inferred_client else []),
                "source_client": inferred_client,
                "source_scope": "target_dir" if inferred_client else "imported",
                "source_root": "",
                "last_seen_at": skill.get("imported_at") or utc_now(),
                "missing_from_source": False,
            }
            for key, value in defaults.items():
                if key not in skill:
                    skill[key] = value
                    changed = True
            for client, override in list(skill.get("client_overrides", {}).items()):
                if override == "prefer":
                    skill["client_overrides"][client] = "prefer:{}".format(skill["skill_id"])
                    changed = True
        return changed

    def _migrate_clients(self, clients: Dict) -> bool:
        changed = False
        for client, config in clients.get("clients", {}).items():
            defaults = self._client_state(client, self._default_clients.get(client, config))
            for key, value in defaults.items():
                if key not in config:
                    config[key] = value
                    changed = True
        return changed

    def _migrate_scan_sources(self, scan_sources: Dict, clients: Dict) -> bool:
        changed = False
        defaults = self._default_scan_sources(clients).get("sources", {})
        scan_sources.setdefault("sources", {})
        for source in list(scan_sources["sources"].values()):
            role = source.get("role", "global_source")
            path_kind = source.get("path_kind", "stable")
            client = source.get("client")
            source_defaults = self._scan_source_state(
                source.get("path", ""),
                role=role,
                path_kind=path_kind if path_kind in SCAN_SOURCE_KINDS else "stable",
                enabled=bool(source.get("enabled", False)),
                suggested=bool(source.get("suggested", False)),
                client=client,
                notes=str(source.get("notes") or ""),
                source_scope=source.get("source_scope"),
                default_entry=bool(source.get("default_entry", False)),
            )
            for key, value in source_defaults.items():
                if key not in source:
                    source[key] = value
                    changed = True
        for source_id, default_source in defaults.items():
            if source_id not in scan_sources["sources"]:
                scan_sources["sources"][source_id] = default_source
                changed = True
                continue
            current = scan_sources["sources"][source_id]
            for key in ("path", "role", "path_kind", "client", "source_scope"):
                if current.get(key) != default_source.get(key):
                    current[key] = default_source.get(key)
                    changed = True
            if current.get("default_entry") is not True:
                current["default_entry"] = True
                changed = True
            if default_source.get("suggested") and current.get("suggested") is not True:
                current["suggested"] = True
                changed = True
            if current.get("default_entry") and current.get("notes") != default_source.get("notes"):
                current["notes"] = default_source.get("notes")
                changed = True
            elif not current.get("notes") and default_source.get("notes"):
                current["notes"] = default_source["notes"]
                changed = True
        return changed

    def discover_skills(self, source_dir: Path) -> List[Path]:
        if not source_dir.exists():
            return []
        if is_wsl_unc(source_dir):
            found = []
            for skill_md in source_dir.rglob("SKILL.md"):
                if any(part in EXCLUDED_SCAN_DIRS for part in skill_md.parts):
                    continue
                found.append(skill_md.parent)
            if not found:
                found.extend(self._discover_skills_via_wsl(source_dir))
            return sorted(found)
        found = []
        for current_root, dirnames, filenames in os.walk(str(source_dir), topdown=True):
            dirnames[:] = [name for name in dirnames if name not in EXCLUDED_SCAN_DIRS]
            if "SKILL.md" in filenames:
                found.append(Path(current_root))
                dirnames[:] = []
        return sorted(found)

    def _expand_config_path(self, raw_path: str, config_path: Optional[str] = None) -> Path:
        expanded = os.path.expanduser(os.path.expandvars(str(raw_path)))
        path = Path(expanded)
        if not path.is_absolute() and config_path:
            path = Path(config_path).parent / path
        return path

    def _read_openclaw_extra_dirs(self, client_config: Dict[str, object]) -> List[str]:
        config_path = client_config.get("config_path")
        if not config_path or not Path(config_path).exists():
            return []
        try:
            data = json.loads(Path(config_path).read_text(encoding="utf-8"))
        except Exception:
            return []
        extra_dirs = (((data.get("skills") or {}).get("load") or {}).get("extraDirs")) or []
        if isinstance(extra_dirs, str):
            extra_dirs = [extra_dirs]
        result = []
        for item in extra_dirs:
            expanded = self._expand_config_path(str(item), str(config_path))
            result.append(str(expanded))
        return result

    def _source_exists(self, path: str) -> bool:
        source_path = Path(path)
        try:
            return source_path.exists()
        except OSError:
            return False

    def _scan_sources_for_client(
        self,
        client: str,
        *,
        scan_sources: Optional[Dict] = None,
        enabled_only: bool = True,
        include_suggested: bool = False,
    ) -> List[Dict[str, object]]:
        scan_sources = scan_sources or self.load_scan_sources()
        items = []
        for source in scan_sources.get("sources", {}).values():
            if enabled_only and not source.get("enabled"):
                continue
            if not include_suggested and source.get("suggested") and not source.get("enabled"):
                continue
            role = source.get("role")
            source_client = source.get("client")
            if role == "global_source":
                continue
            if source_client != client:
                continue
            items.append(source)
        items.sort(key=lambda item: (str(item.get("path")), str(item.get("source_scope"))))
        return items

    def _client_source_roots(self, client: str, client_config: Dict[str, object]) -> List[Dict[str, str]]:
        scan_sources = self.load_scan_sources()
        roots = []
        seen = set()
        for source in self._scan_sources_for_client(client, scan_sources=scan_sources, enabled_only=True):
            path = str(source.get("path"))
            if path in seen:
                continue
            seen.add(path)
            roots.append({"path": path, "scope": str(source.get("source_scope") or "client_live")})
        if not roots:
            target_dir = str(Path(client_config["target_dir"]))
            roots.append({"path": target_dir, "scope": "target_dir"})
        return roots

    def _scan_source_payload(self, source: Dict[str, object]) -> Dict[str, object]:
        source_path = str(source.get("path") or "")
        payload = dict(source)
        payload["exists"] = self._source_exists(source_path)
        payload["discovered_count"] = int(source.get("last_result_count") or 0)
        return payload

    def scan_sources_list(self) -> Dict[str, object]:
        scan_sources = self.load_scan_sources()
        sources = [
            self._scan_source_payload(source)
            for source in sorted(
                scan_sources.get("sources", {}).values(),
                key=lambda item: (
                    not bool(item.get("enabled")),
                    str(item.get("path_kind") or ""),
                    str(item.get("client") or ""),
                    str(item.get("path") or ""),
                ),
            )
        ]
        return {"sources": sources, "total": len(sources)}

    def _normalize_scan_source_path(self, path: str) -> str:
        raw = str(path or "").strip()
        if not raw:
            raise ValueError("scan source path cannot be empty")
        if raw.startswith("\\\\wsl.localhost\\") or raw.startswith("//wsl.localhost/"):
            return str(Path(raw))
        return str(self._expand_config_path(raw))

    def scan_source_add(
        self,
        path: str,
        *,
        role: str,
        client: Optional[str] = None,
        path_kind: str = "stable",
        enabled: bool = True,
        suggested: bool = False,
        notes: str = "",
    ) -> Dict[str, object]:
        normalized_path = self._normalize_scan_source_path(path)
        if role not in SCAN_SOURCE_ROLES:
            raise ValueError("scan source role must be one of {}".format(sorted(SCAN_SOURCE_ROLES)))
        if path_kind not in SCAN_SOURCE_KINDS:
            raise ValueError("scan source kind must be one of {}".format(sorted(SCAN_SOURCE_KINDS)))
        if role in {"client_live", "both"} and not client:
            raise ValueError("client_live/both scan source requires a client")
        if client:
            self._require_client(client)
        scope = "global_source" if role == "global_source" else "client_live"
        scan_sources = self.load_scan_sources()
        entry = self._scan_source_state(
            normalized_path,
            role=role,
            path_kind=path_kind,
            enabled=enabled,
            suggested=suggested,
            client=client,
            notes=notes,
            source_scope=scope,
            default_entry=False,
        )
        scan_sources["sources"][entry["id"]] = entry
        self.save_scan_sources(scan_sources)
        return self._scan_source_payload(entry)

    def scan_source_update(self, source_id: str, **changes: object) -> Dict[str, object]:
        scan_sources = self.load_scan_sources()
        source = scan_sources.get("sources", {}).get(source_id)
        if not source:
            raise FileNotFoundError("Unknown scan source '{}'".format(source_id))
        if "path" in changes and changes["path"] is not None:
            source["path"] = self._normalize_scan_source_path(str(changes["path"]))
        if "role" in changes and changes["role"] is not None:
            role = str(changes["role"])
            if role not in SCAN_SOURCE_ROLES:
                raise ValueError("scan source role must be one of {}".format(sorted(SCAN_SOURCE_ROLES)))
            source["role"] = role
            source["source_scope"] = "global_source" if role == "global_source" else "client_live"
        if "path_kind" in changes and changes["path_kind"] is not None:
            path_kind = str(changes["path_kind"])
            if path_kind not in SCAN_SOURCE_KINDS:
                raise ValueError("scan source kind must be one of {}".format(sorted(SCAN_SOURCE_KINDS)))
            source["path_kind"] = path_kind
        if "client" in changes:
            source["client"] = changes["client"]
            if source.get("client"):
                self._require_client(str(source["client"]))
        if "enabled" in changes and changes["enabled"] is not None:
            source["enabled"] = bool(changes["enabled"])
        if "suggested" in changes and changes["suggested"] is not None:
            source["suggested"] = bool(changes["suggested"])
        if "notes" in changes and changes["notes"] is not None:
            source["notes"] = str(changes["notes"])
        source["id"] = scan_source_id(str(source["path"]), str(source["role"]), source.get("client"))
        scan_sources["sources"].pop(source_id, None)
        scan_sources["sources"][source["id"]] = source
        self.save_scan_sources(scan_sources)
        return self._scan_source_payload(source)

    def scan_source_remove(self, source_id: str) -> Dict[str, object]:
        scan_sources = self.load_scan_sources()
        source = scan_sources.get("sources", {}).pop(source_id, None)
        if not source:
            raise FileNotFoundError("Unknown scan source '{}'".format(source_id))
        self.save_scan_sources(scan_sources)
        return {"removed": source_id, "path": source.get("path")}

    def scan_source_enable(self, source_id: str) -> Dict[str, object]:
        return self.scan_source_update(source_id, enabled=True)

    def scan_source_disable(self, source_id: str) -> Dict[str, object]:
        return self.scan_source_update(source_id, enabled=False)

    def _scan_source_skill_entries(self, source: Dict[str, object]) -> List[Dict[str, object]]:
        source_path = Path(str(source.get("path")))
        entries = self._discover_skill_entries(source_path, str(source.get("source_scope") or "global_source"))
        for entry in entries:
            entry["path_kind"] = source.get("path_kind")
            entry["role"] = source.get("role")
            entry["client"] = source.get("client")
            entry["scan_source_id"] = source.get("id")
        return entries

    def scan_sources_scan(self, source_id: Optional[str] = None) -> Dict[str, object]:
        scan_sources = self.load_scan_sources()
        candidates = []
        for source in scan_sources.get("sources", {}).values():
            if not source.get("enabled"):
                continue
            if source_id and source.get("id") != source_id:
                continue
            candidates.append(source)
        if source_id and not candidates:
            raise FileNotFoundError("Unknown enabled scan source '{}'".format(source_id))

        results = []
        for source in candidates:
            imported = 0
            discovered = self._scan_source_skill_entries(source)
            if source.get("role") in {"global_source", "both"}:
                for item in discovered:
                    self.import_skill_dir(
                        Path(item["path"]),
                        source_type="local-scan",
                        source_locator="scan-source:{}:{}".format(source["id"], item["path"]),
                        source_version="local",
                        prefer_client=(str(source.get("client")) if source.get("role") == "both" and source.get("client") else None),
                        source_client=(str(source.get("client")) if source.get("role") == "both" and source.get("client") else None),
                        source_scope=str(source.get("source_scope") or "global_source"),
                        source_root=str(source.get("path")),
                    )
                    imported += 1
            source["last_scan_at"] = utc_now()
            source["last_result_count"] = len(discovered)
            results.append(
                {
                    "id": source["id"],
                    "path": source["path"],
                    "role": source["role"],
                    "client": source.get("client"),
                    "source_scope": source.get("source_scope"),
                    "discovered_count": len(discovered),
                    "imported_count": imported,
                }
            )
        self.save_scan_sources(scan_sources)
        self.generate_reports()
        self.refresh_discovery_cache()
        return {"sources": results, "total": len(results)}

    def _acquire_lock(self, operation: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            raise RuntimeError("SkillPool is locked by another operation: {}".format(self.lock_path))
        write_json(
            self.lock_path,
            {
                "operation": operation,
                "pid": os.getpid(),
                "created_at": utc_now(),
            },
        )

    def _release_lock(self) -> None:
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

    def _discover_skills_via_wsl(self, source_dir: Path) -> List[Path]:
        distro, linux_path = unc_wsl_to_linux(source_dir)
        command = "find {} -name SKILL.md -print".format(shlex.quote(linux_path))
        completed = subprocess.run(
            ["wsl", "-d", distro, "bash", "-lc", command],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            return []
        found = []
        output = completed.stdout.decode("utf-8", errors="replace")
        for line in output.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            skill_dir = linux_to_unc_wsl(distro, candidate.rsplit("/", 1)[0])
            if any(part in EXCLUDED_SCAN_DIRS for part in skill_dir.parts):
                continue
            found.append(skill_dir)
        unique = sorted(set(found), key=lambda item: len(item.parts))
        filtered = []
        for skill_dir in unique:
            if any(str(skill_dir).startswith(str(existing) + "\\") for existing in filtered):
                continue
            filtered.append(skill_dir)
        return filtered

    def import_skill_dir(
        self,
        skill_dir: Path,
        *,
        source_type: str,
        source_locator: str,
        source_version: str,
        prefer_client: Optional[str] = None,
        source_client: Optional[str] = None,
        source_scope: str = "imported",
        source_root: Optional[str] = None,
    ) -> Dict[str, str]:
        registry = self.load_registry()
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise ValueError("SKILL.md not found in {}".format(skill_dir))
        frontmatter, body = parse_frontmatter(read_text(skill_md))
        name = frontmatter.get("name") or skill_dir.name
        description = frontmatter.get("description") or next(
            (line.strip() for line in body.splitlines() if line.strip()),
            "",
        )
        normalized_name = slugify(name)
        fingerprint = hash_directory(skill_dir)
        skill_id = "{}--{}".format(normalized_name, fingerprint[:12])
        destination = self.pool_dir / skill_id
        if not destination.exists():
            shutil.copytree(str(skill_dir), str(destination))
        skill = registry["skills"].get(skill_id)
        if skill is None:
            skill = {
                "skill_id": skill_id,
                "name": name,
                "description": description,
                "normalized_name": normalized_name,
                "source_type": source_type,
                "source_locator": source_locator,
                "source_version": source_version,
                "imported_at": utc_now(),
                "fingerprint": fingerprint,
                "files_path": str(destination),
                "enabled_global": "enabled",
                "client_overrides": {},
                "conflict_family": normalized_name,
                "status": "active",
                "published_name": normalized_name,
                "origin_directory_name": skill_dir.name,
                "available_clients": ([prefer_client] if prefer_client else []),
                "source_client": source_client or prefer_client,
                "source_scope": source_scope,
                "source_root": source_root or str(skill_dir.parent),
                "last_seen_at": utc_now(),
                "missing_from_source": False,
                "sources": [],
            }
            registry["skills"][skill_id] = skill
        skill["files_path"] = str(destination)
        skill["source_client"] = source_client or prefer_client or skill.get("source_client")
        skill["source_scope"] = source_scope or skill.get("source_scope", "imported")
        skill["source_root"] = source_root or skill.get("source_root") or str(skill_dir.parent)
        skill["last_seen_at"] = utc_now()
        skill["missing_from_source"] = False
        available_clients = skill.setdefault("available_clients", [])
        if prefer_client and available_clients and prefer_client not in available_clients:
            available_clients.append(prefer_client)
        existing_sources = skill.setdefault("sources", [])
        source_record = {
            "source_type": source_type,
            "source_locator": source_locator,
            "source_version": source_version,
            "source_client": source_client or prefer_client,
            "source_scope": source_scope,
            "source_root": source_root or str(skill_dir.parent),
            "imported_at": utc_now(),
        }
        if source_record not in existing_sources:
            existing_sources.append(source_record)
        if prefer_client:
            skill.setdefault("client_overrides", {})[prefer_client] = "prefer:{}".format(skill_id)
        self.save_registry(registry)
        self._refresh_statuses(registry, self.load_clients())
        return {
            "skill_id": skill_id,
            "name": name,
            "conflict_family": normalized_name,
            "destination": str(destination),
        }

    def scan_local(self) -> Dict[str, int]:
        results: Dict[str, int] = {}
        self.init_state()
        registry = self.load_registry()
        clients = self.load_clients()
        scan_sources = self.load_scan_sources()
        for skill in registry.get("skills", {}).values():
            if skill.get("source_scope") in ("target_dir", "extra_dir", "client_live", "global_source"):
                skill["missing_from_source"] = True
        self.save_registry(registry)
        for client, client_config in clients["clients"].items():
            client_config["extra_dirs"] = [
                str(source["path"])
                for source in self._scan_sources_for_client(client, scan_sources=scan_sources, enabled_only=True)
                if str(source.get("source_scope")) == "extra_dir"
            ]
            clients["clients"][client] = client_config
            results[client] = 0
        results["global_source"] = 0

        for source in scan_sources.get("sources", {}).values():
            if not source.get("enabled"):
                continue
            discovered = self._scan_source_skill_entries(source)
            source["last_scan_at"] = utc_now()
            source["last_result_count"] = len(discovered)
            result_key = str(source.get("client") or "global_source")
            results.setdefault(result_key, 0)
            results[result_key] += len(discovered)
            if source.get("role") not in {"global_source", "both"}:
                continue
            for item in discovered:
                self.import_skill_dir(
                    Path(item["path"]),
                    source_type="local-scan",
                    source_locator="scan-source:{}:{}".format(source["id"], item["path"]),
                    source_version="local",
                    prefer_client=(str(source.get("client")) if source.get("role") == "both" and source.get("client") else None),
                    source_client=(str(source.get("client")) if source.get("role") == "both" and source.get("client") else None),
                    source_scope=str(source.get("source_scope") or "global_source"),
                    source_root=str(source.get("path")),
                )
        self.save_clients(clients)
        self.save_scan_sources(scan_sources)
        self.generate_reports()
        self.refresh_discovery_cache()
        return results

    def _parse_github_locator(self, locator: str, ref: Optional[str], subdir: Optional[str]) -> Tuple[str, str, Optional[str], str]:
        locator = locator.strip()
        parsed = urllib.parse.urlparse(locator)
        if parsed.scheme and parsed.netloc:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) < 2:
                raise ValueError("GitHub URL must include owner/repo")
            owner, repo = parts[0], parts[1].replace(".git", "")
            tree_ref = ref
            tree_subdir = subdir
            if len(parts) >= 4 and parts[2] == "tree":
                tree_ref = tree_ref or parts[3]
                if len(parts) > 4 and not tree_subdir:
                    tree_subdir = "/".join(parts[4:])
        else:
            parts = [part for part in locator.split("/") if part]
            if len(parts) < 2:
                raise ValueError("GitHub locator must look like owner/repo")
            owner, repo = parts[0], parts[1].replace(".git", "")
            tree_ref = ref
            tree_subdir = subdir
        display = "https://github.com/{}/{}".format(owner, repo)
        return owner, repo, tree_ref, tree_subdir or ""

    def import_github(self, locator: str, ref: Optional[str] = None, subdir: Optional[str] = None) -> Dict[str, List[str]]:
        owner, repo, resolved_ref, resolved_subdir = self._parse_github_locator(locator, ref, subdir)
        archive_url = "https://api.github.com/repos/{}/{}/zipball".format(owner, repo)
        if resolved_ref:
            archive_url += "/{}".format(urllib.parse.quote(resolved_ref))
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        cache_zip = self.cache_dir / "github-{}-{}-{}.zip".format(owner, repo, timestamp)
        request = urllib.request.Request(archive_url, headers={"User-Agent": "skillpool/0.1"})
        with urllib.request.urlopen(request) as response, cache_zip.open("wb") as fh:
            fh.write(response.read())
        extracted = self._extract_archive(cache_zip, "github-{}-{}".format(owner, repo))
        scan_root = extracted
        if resolved_subdir:
            scan_root = extracted / Path(resolved_subdir)
            if not scan_root.exists():
                raise ValueError("Subdir '{}' was not found in archive".format(resolved_subdir))
        imported = self._import_from_directory(
            scan_root,
            source_type="github",
            source_locator="https://github.com/{}/{}".format(owner, repo),
            source_version=resolved_ref or "default",
        )
        self.generate_reports()
        return imported

    def import_zip(self, zip_path: Path) -> Dict[str, List[str]]:
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise ValueError("ZIP file not found: {}".format(zip_path))
        extracted = self._extract_archive(zip_path, zip_path.stem)
        imported = self._import_from_directory(
            extracted,
            source_type="zip",
            source_locator=str(zip_path.resolve()),
            source_version="local",
        )
        self.generate_reports()
        return imported

    def import_detect_github(self, locator: str, ref: Optional[str] = None, subdir: Optional[str] = None) -> Dict[str, object]:
        owner, repo, resolved_ref, resolved_subdir = self._parse_github_locator(locator, ref, subdir)
        archive_url = "https://api.github.com/repos/{}/{}/zipball".format(owner, repo)
        if resolved_ref:
            archive_url += "/{}".format(urllib.parse.quote(resolved_ref))
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        cache_zip = self.cache_dir / "detect-{}-{}-{}.zip".format(owner, repo, timestamp)
        request = urllib.request.Request(archive_url, headers={"User-Agent": "skillpool/0.1"})
        with urllib.request.urlopen(request) as response, cache_zip.open("wb") as fh:
            fh.write(response.read())
        extracted = self._extract_archive(cache_zip, "detect-{}-{}".format(owner, repo))
        scan_root = extracted
        if resolved_subdir:
            scan_root = extracted / Path(resolved_subdir)
            if not scan_root.exists():
                raise ValueError("Subdir '{}' was not found in archive".format(resolved_subdir))
        skills = self.discover_skills(scan_root)
        relative_paths = [str(path.relative_to(scan_root)).replace("\\", "/") for path in skills]
        template_markers = {"template", "templates", "example", "examples", "sample", "samples"}
        if not skills:
            detected_type = "invalid"
            status = "invalid"
        elif any(any(part.lower() in template_markers for part in Path(path).parts) for path in relative_paths):
            detected_type = "template"
            status = "ok"
        elif len(skills) == 1:
            detected_type = "single_skill"
            status = "ok"
        else:
            detected_type = "multi_skill"
            status = "ok"
        return {
            "source_type": "github",
            "repo": "{}/{}".format(owner, repo),
            "ref": resolved_ref or "default",
            "subdir": resolved_subdir,
            "status": status,
            "detected_type": detected_type,
            "skill_count": len(skills),
            "skills": relative_paths,
            "scan_root": str(scan_root),
        }

    def import_batch(self, manifest_path: Path) -> Dict[str, object]:
        manifest_path = Path(manifest_path)
        if not manifest_path.exists():
            raise ValueError("Batch manifest not found: {}".format(manifest_path))
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("Batch manifest must be a list or an object with 'items'")
        results = []
        imported_skill_ids = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError("Batch manifest item {} must be an object".format(index))
            source_type = item.get("type")
            if source_type == "github":
                result = self.import_github(
                    str(item.get("repo_or_url", "")),
                    ref=item.get("ref") or None,
                    subdir=item.get("subdir") or None,
                )
            elif source_type == "zip":
                result = self.import_zip(Path(str(item.get("zip_path", ""))))
            else:
                raise ValueError("Unsupported batch import type: {}".format(source_type))
            results.append({"index": index, "type": source_type, "result": result})
            imported_skill_ids.extend(result.get("imported_skill_ids", []))
        return {"manifest_path": str(manifest_path), "results": results, "imported_skill_ids": imported_skill_ids}

    def _extract_archive(self, archive_path: Path, prefix: str) -> Path:
        destination = self.cache_dir / "{}-{}".format(prefix, datetime.utcnow().strftime("%Y%m%d%H%M%S"))
        ensure_clean_directory(destination)
        with zipfile.ZipFile(str(archive_path), "r") as archive:
            archive.extractall(str(destination))
        child_dirs = [path for path in destination.iterdir() if path.is_dir()]
        if len(child_dirs) == 1:
            return child_dirs[0]
        return destination

    def _import_from_directory(self, directory: Path, *, source_type: str, source_locator: str, source_version: str) -> Dict[str, List[str]]:
        skills = self.discover_skills(directory)
        if not skills:
            raise ValueError("No SKILL.md files found under {}".format(directory))
        imported = []
        for skill_dir in skills:
            imported.append(
                self.import_skill_dir(
                    skill_dir,
                    source_type=source_type,
                    source_locator="{}#{}".format(source_locator, skill_dir.relative_to(directory)),
                    source_version=source_version,
                )["skill_id"]
            )
        return {"imported_skill_ids": imported}

    def set_enabled_global(self, skill_id: str, enabled: bool) -> Dict[str, str]:
        registry = self.load_registry()
        skill = self._require_skill(registry, skill_id)
        skill["enabled_global"] = "enabled" if enabled else "disabled"
        self.save_registry(registry)
        self._refresh_statuses(registry, self.load_clients())
        self.generate_reports()
        return {"skill_id": skill_id, "enabled_global": skill["enabled_global"]}

    def _is_preferred(self, skill: Dict[str, object], client: str) -> bool:
        override = skill.get("client_overrides", {}).get(client, "inherit")
        return override == "prefer" or override == "prefer:{}".format(skill["skill_id"])

    def override_set(self, client: str, conflict_family: str, skill_id: str) -> Dict[str, str]:
        registry = self.load_registry()
        self._require_client(client)
        requested = self._require_skill(registry, skill_id)
        if requested["conflict_family"] != conflict_family:
            raise ValueError("Skill '{}' does not belong to conflict family '{}'".format(skill_id, conflict_family))
        for skill in registry["skills"].values():
            if skill["conflict_family"] == conflict_family:
                current = skill.setdefault("client_overrides", {}).get(client, "inherit")
                if current == "prefer" or current.startswith("prefer:"):
                    skill["client_overrides"][client] = "inherit"
        requested.setdefault("client_overrides", {})[client] = "prefer:{}".format(skill_id)
        self.save_registry(registry)
        self._refresh_statuses(registry, self.load_clients())
        self.generate_reports()
        return {"client": client, "conflict_family": conflict_family, "skill_id": skill_id}

    def override_list(self, client: str) -> Dict[str, object]:
        registry = self.load_registry()
        self._require_client(client)
        overrides = []
        for skill in sorted(registry["skills"].values(), key=lambda item: (item["conflict_family"], item["skill_id"])):
            value = skill.get("client_overrides", {}).get(client)
            if value and value != "inherit":
                overrides.append(
                    {
                        "conflict_family": skill["conflict_family"],
                        "skill_id": skill["skill_id"],
                        "override": value,
                    }
                )
        return {"client": client, "overrides": overrides}

    def override_inherit(self, client: str, conflict_family: str) -> Dict[str, object]:
        registry = self.load_registry()
        self._require_client(client)
        count = 0
        for skill in registry["skills"].values():
            if skill["conflict_family"] == conflict_family:
                skill.setdefault("client_overrides", {})[client] = "inherit"
                count += 1
        self.save_registry(registry)
        self._refresh_statuses(registry, self.load_clients())
        self.generate_reports()
        return {"client": client, "conflict_family": conflict_family, "updated": count}

    def override_disable(self, client: str, conflict_family: str) -> Dict[str, object]:
        registry = self.load_registry()
        self._require_client(client)
        count = 0
        for skill in registry["skills"].values():
            if skill["conflict_family"] == conflict_family:
                skill.setdefault("client_overrides", {})[client] = "disabled"
                count += 1
        self.save_registry(registry)
        self._refresh_statuses(registry, self.load_clients())
        self.generate_reports()
        return {"client": client, "conflict_family": conflict_family, "updated": count}

    def _family_members_visible_to_client(self, registry: Dict, client: str, conflict_family: str) -> List[Dict[str, object]]:
        members = [skill for skill in registry["skills"].values() if skill["conflict_family"] == conflict_family]
        return self._visible_members_for_client(client, members)

    def _family_override_value(self, members: List[Dict[str, object]], client: str) -> str:
        overrides = [str(member.get("client_overrides", {}).get(client, "inherit")) for member in members]
        if overrides and all(item == "disabled" for item in overrides):
            return "disabled"
        preferred = next((item for item in overrides if item.startswith("prefer:")), None)
        if preferred:
            return preferred
        if any(item == "prefer" for item in overrides):
            return "prefer"
        return "inherit"

    def _set_family_override_in_registry(
        self,
        registry: Dict,
        *,
        client: str,
        conflict_family: str,
        mode: str,
        skill_id: Optional[str] = None,
    ) -> Dict[str, object]:
        self._require_client(client)
        members = [skill for skill in registry["skills"].values() if skill["conflict_family"] == conflict_family]
        if not members:
            raise ValueError("Unknown conflict family '{}'".format(conflict_family))
        before = self._family_override_value(members, client)
        updated = 0
        if mode == "inherit":
            for skill in members:
                if skill.setdefault("client_overrides", {}).get(client) != "inherit":
                    skill["client_overrides"][client] = "inherit"
                    updated += 1
        elif mode == "disabled":
            for skill in members:
                if skill.setdefault("client_overrides", {}).get(client) != "disabled":
                    skill["client_overrides"][client] = "disabled"
                    updated += 1
        elif mode == "prefer":
            if not skill_id:
                raise ValueError("prefer override requires skill_id")
            requested = self._require_skill(registry, skill_id)
            if requested["conflict_family"] != conflict_family:
                raise ValueError("Skill '{}' does not belong to conflict family '{}'".format(skill_id, conflict_family))
            for skill in members:
                current = skill.setdefault("client_overrides", {}).get(client, "inherit")
                if current != "inherit":
                    skill["client_overrides"][client] = "inherit"
                    updated += 1
            preferred_value = "prefer:{}".format(skill_id)
            if requested.setdefault("client_overrides", {}).get(client) != preferred_value:
                requested["client_overrides"][client] = preferred_value
                updated += 1
        else:
            raise ValueError("Unsupported override mode '{}'".format(mode))
        after = self._family_override_value(members, client)
        return {
            "client": client,
            "conflict_family": conflict_family,
            "mode": mode,
            "skill_id": skill_id,
            "changed": before != after,
            "updated_entries": updated,
            "before": before,
            "after": after,
        }

    def batch_inherit(self, clients_list: List[str], families: List[str]) -> Dict[str, object]:
        if not clients_list:
            raise ValueError("batch inherit requires at least one client")
        if not families:
            raise ValueError("batch inherit requires at least one conflict family")
        registry = self.load_registry()
        clients = self.load_clients()
        results = []
        for client in clients_list:
            self._require_client(client, clients)
            for family in families:
                results.append(self._set_family_override_in_registry(registry, client=client, conflict_family=family, mode="inherit"))
        self.save_registry(registry)
        self._refresh_statuses(registry, clients)
        self.generate_reports(registry=registry, clients=clients)
        return {
            "operation": "inherit",
            "clients": clients_list,
            "families": families,
            "changed_count": sum(1 for item in results if item["changed"]),
            "results": results,
        }

    def batch_disable(self, clients_list: List[str], families: List[str]) -> Dict[str, object]:
        if not clients_list:
            raise ValueError("batch disable requires at least one client")
        if not families:
            raise ValueError("batch disable requires at least one conflict family")
        registry = self.load_registry()
        clients = self.load_clients()
        results = []
        for client in clients_list:
            self._require_client(client, clients)
            for family in families:
                results.append(self._set_family_override_in_registry(registry, client=client, conflict_family=family, mode="disabled"))
        self.save_registry(registry)
        self._refresh_statuses(registry, clients)
        self.generate_reports(registry=registry, clients=clients)
        return {
            "operation": "disable",
            "clients": clients_list,
            "families": families,
            "changed_count": sum(1 for item in results if item["changed"]),
            "results": results,
        }

    def _sync_skill_template(self, source_client: str, *, families: Optional[List[str]] = None) -> Dict[str, object]:
        registry = self.load_registry()
        clients = self.load_clients()
        self._require_client(source_client, clients)
        family_filter = set(families or [])
        published_skill_ids = list(clients["clients"][source_client].get("published_skill_ids", []))
        template_families = []
        seen_families = set()
        for skill_id in published_skill_ids:
            skill = registry["skills"].get(skill_id)
            if not skill:
                continue
            family = skill["conflict_family"]
            if family_filter and family not in family_filter:
                continue
            template_families.append(
                {
                    "conflict_family": family,
                    "mode": "prefer",
                    "skill_id": skill_id,
                    "name": skill.get("name"),
                    "description": skill.get("description", ""),
                }
            )
            seen_families.add(family)
        for family, members in sorted(self._family_members(registry).items()):
            if family_filter and family not in family_filter:
                continue
            if any(member.get("client_overrides", {}).get(source_client) == "disabled" for member in members):
                if family not in seen_families:
                    template_families.append(
                        {
                            "conflict_family": family,
                            "mode": "disabled",
                            "skill_id": None,
                            "name": self._family_display_skill(members).get("name"),
                            "description": self._family_display_skill(members).get("description", ""),
                        }
                    )
                    seen_families.add(family)
        ignored_families = []
        for family in sorted(family_filter):
            if family not in seen_families:
                ignored_families.append({"conflict_family": family, "reason": "源客户端当前没有已发布或显式禁用该 family"})
        return {
            "source_client": source_client,
            "generated_at": utc_now(),
            "published_family_count": len([item for item in template_families if item["mode"] == "prefer"]),
            "disabled_family_count": len([item for item in template_families if item["mode"] == "disabled"]),
            "families": sorted(template_families, key=lambda item: item["conflict_family"]),
            "ignored_families": ignored_families,
        }

    def sync_inspect(self, source_client: str, *, families: Optional[List[str]] = None) -> Dict[str, object]:
        template = self._sync_skill_template(source_client, families=families)
        source_mcp = self.mcp_list(source_client)
        return {
            "source_client": source_client,
            "generated_at": template["generated_at"],
            "skills": template,
            "mcp": {
                "source_status": source_mcp["source_status"],
                "writable": source_mcp.get("writable", False),
                "server_count": len(source_mcp.get("root_servers", [])),
                "servers": [dict(item) for item in source_mcp.get("root_servers", [])],
                "notes": source_mcp.get("notes", []),
            },
        }

    def _target_skill_sync_preview(self, registry: Dict, source_template: Dict[str, object], target_client: str) -> Dict[str, object]:
        actions = []
        summary = {"prefer_exact": 0, "disabled": 0, "noop": 0, "unresolved_family": 0, "unavailable_family": 0}
        for family_item in source_template.get("families", []):
            family = family_item["conflict_family"]
            visible_members = self._family_members_visible_to_client(registry, target_client, family)
            current_override = self._family_override_value([skill for skill in registry["skills"].values() if skill["conflict_family"] == family], target_client)
            if family_item["mode"] == "disabled":
                action_type = "disabled" if current_override != "disabled" else "noop"
                summary[action_type] += 1
                actions.append(
                    {
                        "conflict_family": family,
                        "action": action_type,
                        "mode": "disabled",
                        "reason": "源客户端对该 family 使用显式禁用模板" if action_type != "noop" else "目标客户端已是 disabled",
                    }
                )
                continue
            source_skill_id = str(family_item.get("skill_id") or "")
            exact_match = next((member for member in visible_members if member["skill_id"] == source_skill_id), None)
            if exact_match:
                preferred_value = "prefer:{}".format(source_skill_id)
                action_type = "prefer_exact" if current_override != preferred_value else "noop"
                summary[action_type] += 1
                actions.append(
                    {
                        "conflict_family": family,
                        "action": action_type,
                        "mode": "prefer",
                        "skill_id": source_skill_id,
                        "reason": "目标客户端可见同一 skill_id" if action_type != "noop" else "目标客户端已优先该 skill_id",
                    }
                )
            elif visible_members:
                summary["unresolved_family"] += 1
                actions.append(
                    {
                        "conflict_family": family,
                        "action": "unresolved_family",
                        "mode": "prefer",
                        "skill_id": source_skill_id,
                        "reason": "目标客户端只能看到同族但不是同一个 skill_id",
                        "visible_skill_ids": [member["skill_id"] for member in visible_members],
                    }
                )
            else:
                summary["unavailable_family"] += 1
                actions.append(
                    {
                        "conflict_family": family,
                        "action": "unavailable_family",
                        "mode": "prefer",
                        "skill_id": source_skill_id,
                        "reason": "目标客户端当前完全看不到该 family",
                    }
                )
        return {"client": target_client, "counts": summary, "actions": actions}

    def _mcp_sync_preview(self, source_client: str, target_client: str) -> Dict[str, object]:
        source_payload = self.mcp_list(source_client)
        target_payload = self.mcp_list(target_client)
        if source_payload["source_status"] != "ok" or not source_payload.get("writable"):
            return {
                "client": target_client,
                "source_status": source_payload["source_status"],
                "target_status": target_payload["source_status"],
                "supported": False,
                "actions": [],
                "counts": {"add": 0, "update": 0, "noop": 0},
                "notes": ["源客户端当前没有可写 MCP 模板。"],
            }
        if target_payload["source_status"] != "ok" or not target_payload.get("writable"):
            return {
                "client": target_client,
                "source_status": source_payload["source_status"],
                "target_status": target_payload["source_status"],
                "supported": False,
                "actions": [],
                "counts": {"add": 0, "update": 0, "noop": 0},
                "notes": ["目标客户端当前不支持可靠的 MCP 写入同步。"],
            }
        source_entries = {entry["name"]: dict(entry) for entry in source_payload.get("root_servers", [])}
        target_entries = {entry["name"]: dict(entry) for entry in target_payload.get("root_servers", [])}
        actions = []
        counts = {"add": 0, "update": 0, "noop": 0}
        for name in sorted(source_entries):
            source_entry = source_entries[name]
            target_entry = target_entries.get(name)
            if not target_entry:
                counts["add"] += 1
                actions.append({"server_name": name, "action": "add", "reason": "目标客户端不存在该 server"})
                continue
            if (
                str(target_entry.get("command") or "") != str(source_entry.get("command") or "")
                or [str(item) for item in target_entry.get("args", [])] != [str(item) for item in source_entry.get("args", [])]
                or bool(target_entry.get("enabled", True)) != bool(source_entry.get("enabled", True))
            ):
                counts["update"] += 1
                actions.append({"server_name": name, "action": "update", "reason": "命令、参数或启用状态与源客户端模板不同"})
            else:
                counts["noop"] += 1
                actions.append({"server_name": name, "action": "noop", "reason": "目标客户端已经与源客户端一致"})
        return {
            "client": target_client,
            "source_status": source_payload["source_status"],
            "target_status": target_payload["source_status"],
            "supported": True,
            "actions": actions,
            "counts": counts,
            "notes": ["MCP 同步首版采用 merge：新增/更新 source 的 root servers，不删除目标端独有项。"],
        }

    def sync_preview(
        self,
        source_client: str,
        target_clients: List[str],
        *,
        include_skills: bool = True,
        include_mcp: bool = True,
        families: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        if not include_skills and not include_mcp:
            raise ValueError("sync preview requires skills and/or mcp")
        if not target_clients:
            raise ValueError("sync preview requires at least one target client")
        registry = self.load_registry()
        clients = self.load_clients()
        self._require_client(source_client, clients)
        for target in target_clients:
            self._require_client(target, clients)
            if target == source_client:
                raise ValueError("source client and target client must be different")
        template = self._sync_skill_template(source_client, families=families) if include_skills else None
        targets = []
        blocked_targets = []
        for target in target_clients:
            target_result = {
                "client": target,
                "status": "ready",
                "issues": [],
                "skills": None,
                "mcp": None,
                "publish_preview": None,
            }
            if include_skills:
                target_result["skills"] = self._target_skill_sync_preview(registry, template, target)
                target_result["publish_preview"] = self.preview(target, detailed=True)
                if target_result["publish_preview"]["status"] == "blocked":
                    target_result["status"] = "blocked"
                    target_result["issues"].append("目标客户端当前 preview blocked，不能安全应用同步")
            if include_mcp:
                target_result["mcp"] = self._mcp_sync_preview(source_client, target)
            if target_result["status"] == "blocked":
                blocked_targets.append(target)
            targets.append(target_result)
        return {
            "source_client": source_client,
            "generated_at": utc_now(),
            "include_skills": include_skills,
            "include_mcp": include_mcp,
            "skills_template": template,
            "targets": targets,
            "blocked_targets": blocked_targets,
        }

    def _backup_sync_target_state(self, client: str, client_config: Dict[str, object], *, include_mcp: bool) -> Tuple[str, Path]:
        backup_id = self._backup_client_state(client, client_config)
        backup_dir = self.backups_dir / backup_id / client
        if include_mcp and client_config.get("mcp_config_path"):
            mcp_path = Path(str(client_config["mcp_config_path"]))
            if mcp_path.exists():
                shutil.copy2(str(mcp_path), str(backup_dir / "mcp-config.backup"))
                write_json(
                    backup_dir / "mcp-state.json",
                    {
                        "client": client,
                        "mcp_config_path": str(mcp_path),
                    },
                )
        return backup_id, backup_dir

    def _restore_sync_target_state(self, client: str, client_config: Dict[str, object], backup_dir: Path) -> None:
        self._restore_backup_dir(client, client_config, backup_dir)
        mcp_state_path = backup_dir / "mcp-state.json"
        mcp_backup = backup_dir / "mcp-config.backup"
        if mcp_state_path.exists() and mcp_backup.exists():
            payload = json.loads(mcp_state_path.read_text(encoding="utf-8"))
            target_path = Path(str(payload.get("mcp_config_path", "")))
            if str(target_path):
                shutil.copy2(str(mcp_backup), str(target_path))

    def _apply_skill_sync_actions(self, registry: Dict, target_client: str, actions: List[Dict[str, object]]) -> Dict[str, object]:
        applied = []
        for action in actions:
            if action["action"] not in {"prefer_exact", "disabled"}:
                continue
            if action["action"] == "prefer_exact":
                applied.append(
                    self._set_family_override_in_registry(
                        registry,
                        client=target_client,
                        conflict_family=action["conflict_family"],
                        mode="prefer",
                        skill_id=action["skill_id"],
                    )
                )
            elif action["action"] == "disabled":
                applied.append(
                    self._set_family_override_in_registry(
                        registry,
                        client=target_client,
                        conflict_family=action["conflict_family"],
                        mode="disabled",
                    )
                )
        return {
            "changed_count": sum(1 for item in applied if item["changed"]),
            "results": applied,
        }

    def _apply_mcp_sync_actions(self, source_client: str, target_client: str) -> Dict[str, object]:
        source_payload = self.mcp_list(source_client)
        target_payload = self.mcp_list(target_client)
        if source_payload["source_status"] != "ok" or not source_payload.get("writable"):
            return {
                "client": target_client,
                "changed": False,
                "supported": False,
                "summary": "源客户端不支持可写 MCP 模板同步",
            }
        if target_payload["source_status"] != "ok" or not target_payload.get("writable"):
            return {
                "client": target_client,
                "changed": False,
                "supported": False,
                "summary": "目标客户端不支持可靠的 MCP 写入同步",
            }

        source_entries = [dict(entry) for entry in source_payload.get("root_servers", [])]

        def _mutate(entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], str]:
            existing = {entry["name"]: entry for entry in entries}
            next_index = max([entry.get("order_index", -1) for entry in entries] + [-1]) + 1
            added = 0
            updated = 0
            for source_entry in source_entries:
                current = existing.get(source_entry["name"])
                if current is None:
                    entries.append(
                        {
                            "name": source_entry["name"],
                            "source_kind": "root",
                            "managed": True,
                            "enabled": bool(source_entry.get("enabled", True)),
                            "command": source_entry.get("command"),
                            "args": [str(item) for item in source_entry.get("args", [])],
                            "duplicate_group": None,
                            "notes": [],
                            "order_index": next_index,
                        }
                    )
                    next_index += 1
                    added += 1
                    continue
                if (
                    str(current.get("command") or "") != str(source_entry.get("command") or "")
                    or [str(item) for item in current.get("args", [])] != [str(item) for item in source_entry.get("args", [])]
                    or bool(current.get("enabled", True)) != bool(source_entry.get("enabled", True))
                ):
                    current["command"] = source_entry.get("command")
                    current["args"] = [str(item) for item in source_entry.get("args", [])]
                    current["enabled"] = bool(source_entry.get("enabled", True))
                    updated += 1
            return entries, "MCP merge 完成：新增 {} 个，更新 {} 个".format(added, updated)

        result = self._apply_mcp_mutation(target_client, "sync-merge-from-{}".format(source_client), _mutate)
        result["supported"] = True
        return result

    def sync_apply(
        self,
        source_client: str,
        target_clients: List[str],
        *,
        include_skills: bool = True,
        include_mcp: bool = True,
        families: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        preview = self.sync_preview(
            source_client,
            target_clients,
            include_skills=include_skills,
            include_mcp=include_mcp,
            families=families,
        )
        if preview["blocked_targets"]:
            raise RuntimeError("Refusing sync apply because targets are blocked: {}".format(", ".join(preview["blocked_targets"])))
        self._acquire_lock("sync:{}".format(source_client))
        try:
            results = []
            for target_result in preview["targets"]:
                target_client = target_result["client"]
                clients = self.load_clients()
                client_config = self._require_client(target_client, clients)
                backup_id, backup_dir = self._backup_sync_target_state(
                    target_client,
                    client_config,
                    include_mcp=bool(include_mcp and target_result.get("mcp", {}).get("supported")),
                )
                target_summary = {
                    "client": target_client,
                    "backup_id": backup_id,
                    "status": "success",
                    "skills": None,
                    "mcp": None,
                }
                try:
                    if include_skills and target_result.get("skills"):
                        registry = self.load_registry()
                        clients = self.load_clients()
                        skill_apply = self._apply_skill_sync_actions(registry, target_client, target_result["skills"]["actions"])
                        if skill_apply["changed_count"] > 0:
                            self.save_registry(registry)
                            self._refresh_statuses(registry, clients)
                            self.generate_reports(registry=registry, clients=clients)
                            publish_result = self.publish(target_client, force=True, use_lock=False)
                        else:
                            publish_result = None
                        target_summary["skills"] = {
                            "changed_count": skill_apply["changed_count"],
                            "publish_result": publish_result,
                            "skipped_count": len(
                                [
                                    item
                                    for item in target_result["skills"]["actions"]
                                    if item["action"] in {"unresolved_family", "unavailable_family", "noop"}
                                ]
                            ),
                        }
                    if include_mcp and target_result.get("mcp"):
                        if target_result["mcp"].get("supported"):
                            mcp_result = self._apply_mcp_sync_actions(source_client, target_client)
                            target_summary["mcp"] = {
                                "changed": bool(mcp_result.get("changed")),
                                "summary": mcp_result.get("summary"),
                            }
                        else:
                            target_summary["mcp"] = {
                                "changed": False,
                                "summary": "MCP 暂不支持同步",
                            }
                except Exception as exc:
                    self._restore_sync_target_state(target_client, client_config, backup_dir)
                    target_summary["status"] = "rolled_back"
                    target_summary["error"] = str(exc)
                results.append(target_summary)
            self.generate_reports()
            return {
                "source_client": source_client,
                "generated_at": utc_now(),
                "results": results,
            }
        finally:
            self._release_lock()

    def _target_skill_map(self, target_dir: Path) -> Dict[str, Dict[str, object]]:
        result = {}
        for skill_dir in self.discover_skills(target_dir):
            result[skill_dir.name] = {
                "path": str(skill_dir),
                "fingerprint": hash_directory(skill_dir),
            }
        return result

    def _broken_direct_children(self, directory: Path) -> List[str]:
        if not directory.exists():
            return []
        broken = []
        try:
            for child in directory.iterdir():
                if os.path.lexists(str(child)) and not child.exists():
                    broken.append(str(child))
        except OSError:
            broken.append(str(directory))
        return broken

    def _extra_dir_status(self, client: str, client_config: Dict[str, object], registry: Dict) -> List[Dict[str, object]]:
        statuses = []
        for source in self._client_source_roots(client, client_config):
            source_dir = Path(source["path"])
            discovered_dirs = self.discover_skills(source_dir) if source_dir.exists() else []
            discovered_fingerprints = set(hash_directory(skill_dir) for skill_dir in discovered_dirs)
            managed_fingerprints = set()
            for skill in registry["skills"].values():
                if skill.get("source_client") == client and skill.get("source_root") == str(source_dir):
                    managed_fingerprints.add(skill.get("fingerprint"))
                    continue
                for source_record in skill.get("sources", []):
                    if (
                        source_record.get("source_client") == client
                        and source_record.get("source_root") == str(source_dir)
                    ):
                        managed_fingerprints.add(skill.get("fingerprint"))
                        break
            statuses.append(
                {
                    "path": str(source_dir),
                    "scope": source["scope"],
                    "exists": source_dir.exists(),
                    "skill_count": len(discovered_dirs),
                    "managed_count": len(managed_fingerprints),
                    "managed": not discovered_fingerprints or discovered_fingerprints.issubset(managed_fingerprints),
                }
            )
        return statuses

    def preview(self, client: str, *, detailed: bool = False, persist: bool = True) -> Dict[str, object]:
        clients = self.load_clients()
        registry = self.load_registry()
        client_config = self._require_client(client, clients)
        manifest = self._resolve_manifest(client, registry)
        target_dir = Path(client_config["target_dir"])
        desired = {}
        for skill_id in manifest["published_skill_ids"]:
            skill = registry["skills"][skill_id]
            desired[skill["published_name"]] = {
                "skill_id": skill_id,
                "fingerprint": skill["fingerprint"],
            }
        current = self._target_skill_map(target_dir)
        added = sorted(name for name in desired if name not in current)
        deleted = sorted(name for name in current if name not in desired)
        retained = []
        replaced = []
        for name in sorted(set(desired).intersection(current)):
            if desired[name]["fingerprint"] == current[name]["fingerprint"]:
                retained.append(name)
            else:
                replaced.append(name)
        extra_dir_status = self._extra_dir_status(client, client_config, registry)
        broken_paths = self._broken_direct_children(target_dir)
        config_extra_dirs = self._read_openclaw_extra_dirs(client_config)
        will_rewrite_config = (
            client_config.get("config_mode") == "openclaw-extra-dirs"
            and config_extra_dirs != [str(target_dir)]
        )
        issues = []
        risk = "safe"
        unmanaged = [
            item for item in extra_dir_status
            if item["scope"] == "extra_dir" and item["exists"] and item["skill_count"] > 0 and not item["managed"]
        ]
        if unmanaged:
            issues.append("configured extraDirs contain skills that are not yet managed")
            risk = "blocked"
        missing_extra = [item for item in extra_dir_status if item["scope"] == "extra_dir" and not item["exists"]]
        if missing_extra and risk != "blocked":
            issues.append("configured extraDirs are missing")
            risk = "warning"
        if broken_paths and risk == "safe":
            issues.append("target directory contains broken links or inaccessible direct children")
            risk = "warning"
        if not manifest["published_skill_ids"]:
            issues.append("manifest would publish zero skills")
            risk = "blocked"
        diff = {
            "added": added,
            "replaced": replaced,
            "deleted": deleted,
            "retained": retained,
        }
        result = {
            "client": client,
            "generated_at": utc_now(),
            "status": risk,
            "issues": issues,
            "target_dir": str(target_dir),
            "manifest_path": client_config["manifest_path"],
            "backup_planned": True,
            "will_rewrite_config": will_rewrite_config,
            "config_path": client_config.get("config_path"),
            "published_count": len(manifest["published_skill_ids"]),
            "current_count": len(current),
            "diff_counts": {key: len(value) for key, value in diff.items()},
            "extra_dirs": extra_dir_status,
            "broken_paths": broken_paths,
            "published_skill_ids": manifest["published_skill_ids"],
        }
        if detailed:
            result["diff"] = diff
        if persist:
            publish_root = self.publish_dir / client
            publish_root.mkdir(parents=True, exist_ok=True)
            write_json(publish_root / "preview.json", result)
            write_json(publish_root / "diff.json", {"client": client, "generated_at": result["generated_at"], "diff": diff})
            self._record_preview_metadata(clients, client, result["generated_at"], result["status"])
            self.save_clients(clients)
        return result

    def preview_all(self) -> Dict[str, object]:
        return {
            client: self.preview(client)
            for client in self.load_clients()["clients"]
        }

    def diff(self, client: str) -> Dict[str, object]:
        return self.preview(client, detailed=True)

    def publish(self, client: str, *, force: bool = False, use_lock: bool = True) -> Dict[str, object]:
        if use_lock:
            self._acquire_lock("publish:{}".format(client))
        try:
            preview = self.preview(client, detailed=True)
            if preview["status"] == "blocked":
                raise RuntimeError("Preview is blocked for '{}': {}".format(client, "; ".join(preview["issues"])))
            if client in ("openclaw", "qclaw") and preview["status"] != "safe" and not force:
                raise RuntimeError("Refusing to publish '{}' until preview is safe".format(client))
            clients = self.load_clients()
            registry = self.load_registry()
            client_config = self._require_client(client, clients)
            manifest = self._resolve_manifest(client, registry)
            backup_id = self._backup_client_state(client, client_config)
            backup_dir = self._resolve_backup_dir(client, backup_id)
            try:
                publish_root = self.publish_dir / client
                publish_skills_dir = publish_root / "skills"
                ensure_clean_directory(publish_skills_dir)
                target_dir = Path(client_config["target_dir"])
                target_dir.mkdir(parents=True, exist_ok=True)
                self._clear_existing_skill_dirs(target_dir)
                for skill_id in manifest["published_skill_ids"]:
                    skill = registry["skills"][skill_id]
                    source_dir = Path(skill["files_path"])
                    published_name = skill["published_name"]
                    shutil.copytree(str(source_dir), str(publish_skills_dir / published_name))
                    target_skill_dir = target_dir / published_name
                    remove_path_lexists(target_skill_dir)
                    shutil.copytree(str(source_dir), str(target_skill_dir))
                write_json(publish_root / "manifest.json", manifest)
                if client_config["config_mode"] == "openclaw-extra-dirs" and client_config.get("config_path"):
                    self._rewrite_openclaw_config(Path(client_config["config_path"]), target_dir)
                client_config["last_published_at"] = utc_now()
                client_config["last_backup_id"] = backup_id
                client_config["published_skill_ids"] = manifest["published_skill_ids"]
                clients["clients"][client] = client_config
                self.save_clients(clients)
                self._refresh_statuses(registry, clients)
                self.generate_reports(registry=registry, clients=clients)
                return {
                    "client": client,
                    "backup_id": backup_id,
                    "published_count": len(manifest["published_skill_ids"]),
                    "target_dir": client_config["target_dir"],
                }
            except Exception:
                if backup_dir is not None:
                    self._restore_backup_dir(client, client_config, backup_dir)
                raise
        finally:
            if use_lock:
                self._release_lock()

    def publish_all(self, *, force: bool = False) -> Dict[str, Dict[str, object]]:
        if not force:
            raise RuntimeError("publish --all requires --force; run preview --all first")
        previews = self.preview_all()
        blocked = {client: data["issues"] for client, data in previews.items() if data["status"] == "blocked"}
        if blocked:
            raise RuntimeError("Refusing publish --all because previews are blocked: {}".format(blocked))
        results = {}
        for client in self.load_clients()["clients"]:
            results[client] = self.publish(client, force=True)
        return results

    def rollback(self, client: str, backup_id: Optional[str] = None) -> Dict[str, str]:
        clients = self.load_clients()
        client_config = self._require_client(client, clients)
        backup_dir = self._resolve_backup_dir(client, backup_id or client_config.get("last_backup_id"))
        if backup_dir is None:
            raise ValueError("No backup available for '{}'".format(client))
        self._restore_backup_dir(client, client_config, backup_dir)
        state_backup = backup_dir / "client_state.json"
        if state_backup.exists():
            restored_state = json.loads(state_backup.read_text(encoding="utf-8"))
            clients["clients"][client].update(restored_state)
            self.save_clients(clients)
        self.generate_reports()
        doctor = self.doctor(deep=True, client=client)
        return {"client": client, "restored_from": backup_dir.parent.name, "doctor_status": doctor["checks"][0]["status"]}

    def _restore_backup_dir(self, client: str, client_config: Dict[str, object], backup_dir: Path) -> None:
        target_snapshot = backup_dir / "target"
        target_dir = Path(client_config["target_dir"])
        safe_rmtree(target_dir)
        if target_snapshot.exists():
            copy_existing_tree(target_snapshot, target_dir)
        config_backup = backup_dir / "config.json"
        if config_backup.exists() and client_config.get("config_path"):
            shutil.copy2(str(config_backup), str(Path(client_config["config_path"])))

    def rollback_list(self, client: str) -> Dict[str, object]:
        self._require_client(client)
        backups = []
        for backup_id_dir in sorted((p for p in self.backups_dir.iterdir() if p.is_dir()), reverse=True):
            backup_dir = backup_id_dir / client
            if not backup_dir.exists():
                continue
            backups.append(
                {
                    "backup_id": backup_id_dir.name,
                    "target_exists": (backup_dir / "target").exists(),
                    "config_exists": (backup_dir / "config.json").exists(),
                    "client_state_exists": (backup_dir / "client_state.json").exists(),
                }
            )
        return {"client": client, "backups": backups}

    def rollback_inspect(self, client: str, backup_id: str) -> Dict[str, object]:
        self._require_client(client)
        backup_dir = self._resolve_backup_dir(client, backup_id)
        if backup_dir is None:
            raise ValueError("No backup '{}' for '{}'".format(backup_id, client))
        target_dir = backup_dir / "target"
        state_path = backup_dir / "client_state.json"
        return {
            "client": client,
            "backup_id": backup_id,
            "path": str(backup_dir),
            "target_exists": target_dir.exists(),
            "target_skill_count": len(self.discover_skills(target_dir)) if target_dir.exists() else 0,
            "config_exists": (backup_dir / "config.json").exists(),
            "client_state": load_json(state_path, {}) if state_path.exists() else {},
        }

    def latest_backup_id(self, client: str) -> Optional[str]:
        backups = self.rollback_list(client)["backups"]
        return backups[0]["backup_id"] if backups else None

    def status(self) -> Dict[str, object]:
        registry = self.load_registry()
        clients = self.load_clients()
        enabled = sum(1 for skill in registry["skills"].values() if skill["enabled_global"] == "enabled")
        disabled = sum(1 for skill in registry["skills"].values() if skill["enabled_global"] == "disabled")
        families = {}
        for skill in registry["skills"].values():
            families.setdefault(skill["conflict_family"], []).append(skill["skill_id"])
        return {
            "root": str(self.root),
            "skill_count": len(registry["skills"]),
            "enabled_count": enabled,
            "disabled_count": disabled,
            "conflict_family_count": len(families),
            "shadowed_count": sum(1 for skill in registry["skills"].values() if skill["status"] == "shadowed"),
            "clients": clients["clients"],
        }

    def doctor(self, *, deep: bool = False, client: Optional[str] = None) -> Dict[str, object]:
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
            config_path = Path(config["config_path"]) if config.get("config_path") else None
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
                self._record_deep_doctor_metadata(clients, client_id, generated_at, check["status"])
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

    def _deep_doctor_check(self, client: str, config: Dict[str, object], registry: Dict) -> Dict[str, object]:
        errors = []
        warnings = []
        target_dir = Path(config["target_dir"])
        manifest_path = Path(config["manifest_path"])
        manifest = load_json(manifest_path, {}) if manifest_path.exists() else {}
        published_ids = manifest.get("published_skill_ids", [])
        target_map = self._target_skill_map(target_dir)
        if not published_ids and len(target_map) > 0:
            warnings.append("target contains skills but no manifest has been published yet")
        if published_ids and len(target_map) != len(published_ids):
            errors.append("manifest count {} does not match target skill count {}".format(len(published_ids), len(target_map)))
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
            errors.append("published skills missing from target: {}".format(", ".join(missing[:10])))
        if mismatched:
            errors.append("published skill fingerprints differ from registry: {}".format(", ".join(mismatched[:10])))
        broken_paths = self._broken_direct_children(target_dir)
        if broken_paths:
            warnings.append("target has broken or inaccessible direct children")
        extra_dir_status = self._extra_dir_status(client, config, registry)
        unmanaged = [
            item for item in extra_dir_status
            if item["scope"] == "extra_dir" and item["exists"] and item["skill_count"] > 0 and not item["managed"]
        ]
        if unmanaged:
            errors.append("configured extraDirs contain unmanaged skills")
        missing_extra = [item for item in extra_dir_status if item["scope"] == "extra_dir" and not item["exists"]]
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

    def generate_reports(self, registry: Optional[Dict] = None, clients: Optional[Dict] = None) -> Dict[str, str]:
        registry = registry or self.load_registry()
        clients = clients or self.load_clients()
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        skills_index = self._build_skills_index(registry, clients)
        conflicts = self._build_conflicts_report(registry, clients)
        inventory = self._build_inventory_report()
        cleanup_state = self.load_cleanup_candidates()
        cleanup_candidates = self._build_cleanup_candidates_report(cleanup_state, registry, clients)
        (self.reports_dir / "SKILLS_INDEX.md").write_text(skills_index, encoding="utf-8")
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

    def _discover_skill_entries(self, source_dir: Path, scope: str) -> List[Dict[str, object]]:
        if not source_dir.exists():
            return []
        entries = []
        for skill_dir in self.discover_skills(source_dir):
            skill_md = skill_dir / "SKILL.md"
            try:
                frontmatter, body = parse_frontmatter(read_text(skill_md))
                name = frontmatter.get("name") or skill_dir.name
                description = frontmatter.get("description") or next(
                    (line.strip() for line in body.splitlines() if line.strip()),
                    "",
                )
                entries.append(
                    {
                        "name": name,
                        "description": description,
                        "normalized_name": slugify(name),
                        "directory_name": skill_dir.name,
                        "scope": scope,
                        "path": str(skill_dir),
                        "source_root": str(source_dir),
                        "fingerprint": hash_directory(skill_dir),
                    }
                )
            except Exception as exc:
                entries.append(
                    {
                        "name": skill_dir.name,
                        "description": "",
                        "normalized_name": slugify(skill_dir.name),
                        "directory_name": skill_dir.name,
                        "scope": scope,
                        "path": str(skill_dir),
                        "source_root": str(source_dir),
                        "fingerprint": None,
                        "error": str(exc),
                    }
                )
        entries.sort(key=lambda item: (item["normalized_name"], item["path"]))
        return entries

    def _inventory_pool_skills_for_client(self, client: str, registry: Dict, clients: Dict) -> List[Dict[str, object]]:
        client_map = self._client_map(clients)
        items = []
        for skill in registry["skills"].values():
            available_clients = skill.get("available_clients", [])
            if available_clients and client not in available_clients:
                continue
            items.append(self._skill_payload(skill, client_map))
        items.sort(key=lambda item: (item["name"].lower(), item["skill_id"]))
        return items

    def _published_skill_ids_for_client(self, client: str, client_config: Dict[str, object]) -> List[str]:
        manifest_path = Path(client_config["manifest_path"])
        if manifest_path.exists():
            manifest = load_json(manifest_path, {})
            published = manifest.get("published_skill_ids")
            if isinstance(published, list):
                return list(published)
        return list(client_config.get("published_skill_ids", []))

    def _inventory_diff_payload(self, item: Dict[str, object], reason: str, **extra: object) -> Dict[str, object]:
        payload = {
            "name": item.get("name"),
            "normalized_name": item.get("normalized_name") or item.get("conflict_family"),
            "path": item.get("path") or item.get("files_path"),
            "scope": item.get("scope") or item.get("source_scope"),
            "source_root": item.get("source_root"),
            "fingerprint": item.get("fingerprint"),
            "skill_id": item.get("skill_id"),
            "reason": reason,
        }
        for key, value in extra.items():
            payload[key] = value
        return payload

    def _inventory_skills_for_client(self, client: str, registry: Dict, clients: Dict) -> Dict[str, object]:
        client_config = self._require_client(client, clients)
        target_dir = Path(client_config["target_dir"])
        source_roots = self._client_source_roots(client, client_config)
        role_map: Dict[str, List[str]] = {}
        for source in source_roots:
            if source["scope"] == "target_dir":
                role = "live target"
            elif source["scope"] == "extra_dir":
                role = "live extraDirs"
            else:
                role = "custom live"
            role_map.setdefault(source["path"], []).append(role)
        if is_wsl_unc(target_dir):
            role_map.setdefault(str(target_dir), []).append("external source")
        source_directories = [
            {"path": path, "roles": roles}
            for path, roles in sorted(role_map.items())
        ]

        live_target_entries = self._discover_skill_entries(target_dir, "target_dir")
        live_extra_entries: List[Dict[str, object]] = []
        live_custom_entries: List[Dict[str, object]] = []
        for source in source_roots:
            if source["scope"] == "extra_dir":
                live_extra_entries.extend(self._discover_skill_entries(Path(source["path"]), "extra_dir"))
            elif source["scope"] == "client_live":
                live_custom_entries.extend(self._discover_skill_entries(Path(source["path"]), "client_live"))
        live_entries = sorted(
            live_target_entries + live_extra_entries + live_custom_entries,
            key=lambda item: (item["normalized_name"], item["path"]),
        )

        pool_entries = self._inventory_pool_skills_for_client(client, registry, clients)
        published_ids = self._published_skill_ids_for_client(client, client_config)
        published_entries = [
            self._skill_payload(registry["skills"][skill_id], self._client_map(clients))
            for skill_id in published_ids
            if skill_id in registry["skills"]
        ]

        registry_by_fingerprint: Dict[str, List[Dict[str, object]]] = {}
        pool_by_family: Dict[str, List[Dict[str, object]]] = {}
        for item in pool_entries:
            registry_by_fingerprint.setdefault(item["fingerprint"], []).append(item)
            pool_by_family.setdefault(item["conflict_family"], []).append(item)

        live_fingerprints = {item["fingerprint"] for item in live_entries if item.get("fingerprint")}
        live_target_fingerprints = {item["fingerprint"] for item in live_target_entries if item.get("fingerprint")}

        live_only = []
        source_mismatch = []
        for item in live_entries:
            fingerprint = item.get("fingerprint")
            if not fingerprint or fingerprint in registry_by_fingerprint:
                continue
            family_matches = pool_by_family.get(item["normalized_name"], [])
            if family_matches:
                source_mismatch.append(
                    self._inventory_diff_payload(
                        item,
                        "live 技能与池内同族 skill 的内容或来源不一致",
                        pool_matches=[
                            {
                                "skill_id": match["skill_id"],
                                "path": match.get("files_path"),
                                "scope": match.get("source_scope"),
                            }
                            for match in family_matches
                        ],
                    )
                )
            else:
                live_only.append(self._inventory_diff_payload(item, "live 技能存在，但尚未纳入 SkillPool registry"))

        pool_only = []
        for item in pool_entries:
            if item["fingerprint"] in live_fingerprints:
                continue
            pool_only.append(self._inventory_diff_payload(item, "池内技能当前未出现在客户端 live 目录"))

        published_only = []
        for item in published_entries:
            if item["fingerprint"] in live_target_fingerprints:
                continue
            published_only.append(self._inventory_diff_payload(item, "发布清单包含该技能，但 live target 目录中未找到"))

        return {
            "client": client,
            "source_directories": source_directories,
            "pool_visible_count": len(pool_entries),
            "published_count": len(published_entries),
            "live_target_count": len(live_target_entries),
            "live_extra_dir_count": len(live_extra_entries),
            "live_custom_count": len(live_custom_entries),
            "live_total_count": len(live_entries),
            "unmanaged_live_count": len(live_only) + len(source_mismatch),
            "published_missing_from_live_count": len(published_only),
            "pool_not_published_count": max(len(pool_entries) - len(published_entries), 0),
            "live_only": live_only,
            "pool_only": pool_only,
            "published_only": published_only,
            "source_mismatch": source_mismatch,
            "published_skill_ids": published_ids,
        }

    def _parse_toml_value(self, raw_value: str):
        value = raw_value.strip()
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        try:
            return ast.literal_eval(value)
        except Exception:
            return value.strip("'\"")

    def _normalize_mcp_servers(self, raw_servers: Dict[str, object], source_file: Path, source_kind: str) -> List[Dict[str, object]]:
        servers = []
        for index, (name, config) in enumerate(raw_servers.items()):
            if not isinstance(config, dict):
                continue
            args = config.get("args") or []
            if not isinstance(args, list):
                args = [str(args)]
            notes = []
            if source_kind == "plugin_cache":
                notes.append("该条目来自插件缓存，只读展示。")
            servers.append(
                {
                    "name": name,
                    "source_file": str(source_file),
                    "source_kind": source_kind,
                    "enabled": bool(config.get("enabled", True)),
                    "command": config.get("command"),
                    "args": [str(item) for item in args],
                    "managed": source_kind == "root",
                    "duplicate_group": None,
                    "notes": notes,
                    "order_index": index,
                }
            )
        return servers

    def _parse_codex_mcp_config(self, config_path: Path) -> List[Dict[str, object]]:
        return self._load_codex_mcp_document(config_path)["entries"]

    def _parse_claude_mcp_config(self, config_path: Path, source_kind: str) -> List[Dict[str, object]]:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if "mcpServers" in payload and isinstance(payload["mcpServers"], dict):
            raw_servers = payload["mcpServers"]
        elif "servers" in payload and isinstance(payload["servers"], dict):
            raw_servers = payload["servers"]
        else:
            raw_servers = payload
        if not isinstance(raw_servers, dict):
            raise ValueError("Claude MCP config must contain an object of servers")
        return self._normalize_mcp_servers(raw_servers, config_path, source_kind)

    def _parse_hermes_mcp_config(self, config_path: Path) -> List[Dict[str, object]]:
        servers: Dict[str, Dict[str, object]] = {}
        current_server: Optional[str] = None
        current_key: Optional[str] = None
        inside_section = False
        for raw_line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            if not inside_section:
                if stripped == "mcp_servers:":
                    inside_section = True
                continue
            if indent == 0:
                break
            if indent == 2 and stripped.endswith(":"):
                current_server = stripped[:-1]
                servers.setdefault(current_server, {"args": [], "enabled": True})
                current_key = None
                continue
            if current_server is None:
                continue
            if indent >= 4 and stripped.startswith("- "):
                if current_key == "args":
                    servers[current_server].setdefault("args", []).append(stripped[2:].strip().strip("'\""))
                continue
            if indent >= 4 and ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip()
                current_key = key
                if key == "args":
                    servers[current_server].setdefault("args", [])
                    continue
                if value == "":
                    continue
                if key == "enabled":
                    servers[current_server]["enabled"] = value.lower() == "true"
                elif key == "command":
                    servers[current_server]["command"] = value.strip("'\"")
                elif key == "args":
                    servers[current_server]["args"] = [value.strip("'\"")]
        return self._normalize_mcp_servers(servers, config_path, "root")

    def _load_codex_mcp_document(self, config_path: Path) -> Dict[str, object]:
        original_text = config_path.read_text(encoding="utf-8", errors="replace")
        lines = original_text.splitlines()
        preserved_lines = []
        servers: Dict[str, Dict[str, object]] = {}
        current_server: Optional[str] = None
        inside_mcp_section = False
        index = 0

        while index < len(lines):
            raw_line = lines[index]
            stripped = raw_line.strip()
            section_match = re.match(r"^\[([^\]]+)\]$", stripped)
            if section_match:
                section_name = section_match.group(1)
                if current_server is not None:
                    current_server = None
                if section_name.startswith("mcp_servers."):
                    inside_mcp_section = True
                    server_name = section_name[len("mcp_servers.") :]
                    if "." in server_name:
                        current_server = None
                    else:
                        current_server = server_name
                        servers.setdefault(current_server, {})
                    index += 1
                    continue
                inside_mcp_section = False
                preserved_lines.append(raw_line)
                index += 1
                continue
            if inside_mcp_section:
                if current_server is not None and "=" in stripped:
                    key, value = [part.strip() for part in stripped.split("=", 1)]
                    if key in {"command", "args", "enabled"}:
                        if key == "args" and value.startswith("[") and not value.rstrip().endswith("]"):
                            collected = [value]
                            index += 1
                            while index < len(lines):
                                collected.append(lines[index].strip())
                                if lines[index].strip().endswith("]"):
                                    break
                                index += 1
                            value = " ".join(collected)
                        servers[current_server][key] = self._parse_toml_value(value)
                index += 1
                continue
            preserved_lines.append(raw_line)
            index += 1

        return {
            "original_text": original_text,
            "preserved_lines": preserved_lines,
            "entries": self._normalize_mcp_servers(servers, config_path, "root"),
        }

    def _render_codex_mcp_document(self, document: Dict[str, object], entries: List[Dict[str, object]]) -> str:
        lines = list(document["preserved_lines"])
        if lines and lines[-1].strip():
            lines.append("")
        for entry in entries:
            lines.extend(
                [
                    "[mcp_servers.{}]".format(entry["name"]),
                    "command = {}".format(json.dumps(str(entry["command"] or ""), ensure_ascii=False)),
                    "args = {}".format(json.dumps([str(item) for item in entry.get("args", [])], ensure_ascii=False)),
                    "enabled = {}".format("true" if entry.get("enabled", True) else "false"),
                    "",
                ]
            )
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines) + "\n"

    def _load_claude_mcp_document(self, config_path: Path) -> Dict[str, object]:
        original_text = config_path.read_text(encoding="utf-8-sig")
        payload = json.loads(original_text or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Claude MCP config must be a JSON object")
        key_name: Optional[str]
        if "mcpServers" in payload and isinstance(payload["mcpServers"], dict):
            key_name = "mcpServers"
            raw_servers = payload["mcpServers"]
        elif "servers" in payload and isinstance(payload["servers"], dict):
            key_name = "servers"
            raw_servers = payload["servers"]
        elif all(isinstance(value, dict) for value in payload.values()):
            key_name = None
            raw_servers = payload
        else:
            key_name = "mcpServers"
            raw_servers = {}
        return {
            "original_text": original_text,
            "payload": payload,
            "key_name": key_name,
            "entries": self._normalize_mcp_servers(raw_servers, config_path, "root"),
        }

    def _render_claude_mcp_document(self, document: Dict[str, object], entries: List[Dict[str, object]]) -> str:
        mapping = {}
        for entry in entries:
            mapping[entry["name"]] = {
                "command": entry.get("command"),
                "args": [str(item) for item in entry.get("args", [])],
                "enabled": bool(entry.get("enabled", True)),
            }
        key_name = document["key_name"]
        if key_name is None:
            payload = mapping
        else:
            payload = dict(document["payload"])
            payload[key_name] = mapping
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    def _load_hermes_mcp_document(self, config_path: Path) -> Dict[str, object]:
        original_text = config_path.read_text(encoding="utf-8", errors="replace")
        lines = original_text.splitlines()
        before_lines: List[str] = []
        after_lines: List[str] = []
        servers: Dict[str, Dict[str, object]] = {}
        current_server: Optional[str] = None
        current_key: Optional[str] = None
        inside_section = False
        section_found = False

        for raw_line in lines:
            stripped = raw_line.strip()
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            if not section_found:
                if stripped == "mcp_servers:":
                    section_found = True
                    inside_section = True
                    continue
                before_lines.append(raw_line)
                continue
            if inside_section:
                if stripped and indent == 0:
                    inside_section = False
                    after_lines.append(raw_line)
                    continue
                if not stripped or stripped.startswith("#"):
                    continue
                if indent == 2 and stripped.endswith(":"):
                    current_server = stripped[:-1]
                    current_key = None
                    servers.setdefault(current_server, {"args": [], "enabled": True})
                    continue
                if current_server is None:
                    continue
                if indent >= 4 and stripped.startswith("- "):
                    if current_key == "args":
                        servers[current_server].setdefault("args", []).append(stripped[2:].strip().strip("'\""))
                    continue
                if indent >= 4 and ":" in stripped:
                    key, value = stripped.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    current_key = key
                    if key == "args":
                        servers[current_server].setdefault("args", [])
                        continue
                    if value == "":
                        continue
                    if key == "enabled":
                        servers[current_server]["enabled"] = value.lower() == "true"
                    elif key == "command":
                        servers[current_server]["command"] = value.strip("'\"")
                    elif key == "args":
                        servers[current_server]["args"] = [value.strip("'\"")]
                continue
            after_lines.append(raw_line)

        if not section_found:
            before_lines = list(lines)

        return {
            "original_text": original_text,
            "before_lines": before_lines,
            "after_lines": after_lines,
            "section_found": section_found,
            "entries": self._normalize_mcp_servers(servers, config_path, "root"),
        }

    def _render_hermes_mcp_document(self, document: Dict[str, object], entries: List[Dict[str, object]]) -> str:
        lines = list(document["before_lines"])
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("mcp_servers:")
        for entry in entries:
            lines.append("  {}:".format(entry["name"]))
            lines.append("    command: {}".format(yaml_scalar(entry.get("command") or "")))
            lines.append("    args:")
            for arg in entry.get("args", []):
                lines.append("      - {}".format(yaml_scalar(arg)))
            lines.append("    enabled: {}".format("true" if entry.get("enabled", True) else "false"))
        if document["after_lines"]:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend(document["after_lines"])
        return "\n".join(lines).rstrip() + "\n"

    def _mcp_semantic_key(self, entry: Dict[str, object]) -> str:
        command = str(entry.get("command") or "")
        args = [str(item) for item in entry.get("args") or []]
        if command.lower() in {"cmd", "cmd.exe"} and len(args) >= 2 and args[0].lower() == "/c":
            command = args[1]
            args = args[2:]
        return "{}\0{}".format(command, json.dumps(args, ensure_ascii=False))

    def _base_mcp_name(self, name: str) -> str:
        return re.sub(r"-\d+$", "", name or "")

    def _annotate_mcp_entries(self, entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
        annotated = []
        groups: Dict[str, List[Dict[str, object]]] = {}
        for entry in entries:
            item = dict(entry)
            item["notes"] = list(item.get("notes", []))
            item["duplicate_group"] = None
            groups.setdefault(self._mcp_semantic_key(item), []).append(item)
            annotated.append(item)

        duplicate_groups = []
        for group_entries in groups.values():
            if len(group_entries) < 2:
                continue
            base_names = {self._base_mcp_name(item["name"]) for item in group_entries}
            preferred_name = None
            for base_name in sorted(base_names):
                if any(item["name"] == base_name for item in group_entries) and any(item["name"] != base_name for item in group_entries):
                    preferred_name = base_name
                    break
            if preferred_name is None:
                preferred_name = group_entries[0]["name"]
            group_id = preferred_name
            for item in group_entries:
                item["duplicate_group"] = group_id
                item["notes"] = list(item.get("notes", [])) + ["与其他 server 的 command + args 完全一致。"]
            duplicate_groups.append(
                {
                    "group_id": group_id,
                    "preferred_name": preferred_name,
                    "names": [item["name"] for item in group_entries],
                    "managed_names": [item["name"] for item in group_entries if item.get("managed")],
                    "source_kinds": sorted({item["source_kind"] for item in group_entries}),
                    "command": group_entries[0].get("command"),
                    "args": list(group_entries[0].get("args") or []),
                }
            )
        duplicate_groups.sort(key=lambda item: item["group_id"])
        return annotated, duplicate_groups

    def _unsupported_mcp_payload(self, client: str, notes: List[str], *, source_status: str = "unsupported_source", source_files: Optional[List[str]] = None) -> Dict[str, object]:
        return {
            "client": client,
            "source_status": source_status,
            "source_files": source_files or [],
            "server_count": None,
            "servers": [],
            "root_servers": [],
            "plugin_cache_servers": [],
            "duplicate_groups": [],
            "notes": notes,
            "writable": False,
            "last_changed_at": None,
            "last_backup_id": None,
            "last_operation": None,
            "last_summary": None,
            "last_diff": None,
        }

    def _mcp_payload_for_client(self, client: str, client_config: Dict[str, object]) -> Dict[str, object]:
        mcp_mode = client_config.get("mcp_mode", "unsupported")
        mcp_config_path = client_config.get("mcp_config_path")
        plugin_cache_dir = client_config.get("plugin_cache_dir")
        mcp_state = self.load_mcp_state().get("clients", {}).get(client, {})

        if mcp_mode == "unsupported":
            return self._unsupported_mcp_payload(
                client,
                ["当前未发现稳定的标准 MCP server registry 配置源，暂不输出 MCP 数量。"],
            )

        config_path = Path(mcp_config_path) if mcp_config_path else None
        source_files = [str(config_path)] if config_path else []
        if config_path is None or not config_path.exists():
            payload = self._unsupported_mcp_payload(
                client,
                ["未找到客户端的 MCP 主配置文件，当前无法可靠统计。"],
                source_status="missing_config",
                source_files=source_files,
            )
            payload.update(
                {
                    "last_changed_at": mcp_state.get("last_changed_at"),
                    "last_backup_id": mcp_state.get("last_backup_id"),
                    "last_operation": mcp_state.get("last_operation"),
                    "last_summary": mcp_state.get("last_summary"),
                    "last_diff": mcp_state.get("last_diff"),
                }
            )
            return payload

        try:
            if mcp_mode == "codex-toml":
                root_servers = self._load_codex_mcp_document(config_path)["entries"]
                plugin_servers = []
                notes = ["已从 Codex config.toml 的 [mcp_servers] 解析 MCP 配置。"]
            elif mcp_mode == "claude-json":
                root_doc = self._load_claude_mcp_document(config_path)
                root_servers = root_doc["entries"]
                plugin_servers = []
                plugin_root = Path(plugin_cache_dir) if plugin_cache_dir else None
                if plugin_root and plugin_root.exists():
                    for plugin_file in sorted(plugin_root.rglob(".mcp.json")):
                        source_files.append(str(plugin_file))
                        try:
                            plugin_servers.extend(self._parse_claude_mcp_config(plugin_file, "plugin_cache"))
                        except Exception:
                            continue
                notes = ["已读取 Claude 根 .mcp.json，并用插件缓存中的 .mcp.json 作为补充来源。"]
            elif mcp_mode == "hermes-yaml":
                root_servers = self._load_hermes_mcp_document(config_path)["entries"]
                plugin_servers = []
                notes = ["已从 Hermes WSL config.yaml 的 mcp_servers 段解析 MCP 配置。"]
            else:
                return self._unsupported_mcp_payload(
                    client,
                    ["当前客户端的 MCP 解析模式未定义。"],
                    source_files=source_files,
                )
        except Exception as exc:
            payload = self._unsupported_mcp_payload(
                client,
                ["解析 MCP 配置失败: {}".format(exc)],
                source_status="parse_error",
                source_files=source_files,
            )
            payload.update(
                {
                    "last_changed_at": mcp_state.get("last_changed_at"),
                    "last_backup_id": mcp_state.get("last_backup_id"),
                    "last_operation": mcp_state.get("last_operation"),
                    "last_summary": mcp_state.get("last_summary"),
                    "last_diff": mcp_state.get("last_diff"),
                }
            )
            return payload

        annotated, duplicate_groups = self._annotate_mcp_entries(root_servers + plugin_servers)
        root_names = {entry["name"] for entry in root_servers}
        root_entries = [entry for entry in annotated if entry["name"] in root_names and entry["source_kind"] == "root"]
        plugin_entries = [entry for entry in annotated if entry["source_kind"] != "root"]
        return {
            "client": client,
            "source_status": "ok",
            "source_files": source_files,
            "server_count": len(annotated),
            "servers": annotated,
            "root_servers": root_entries,
            "plugin_cache_servers": plugin_entries,
            "duplicate_groups": duplicate_groups,
            "notes": notes,
            "writable": mcp_mode in {"codex-toml", "claude-json", "hermes-yaml"},
            "last_changed_at": mcp_state.get("last_changed_at"),
            "last_backup_id": mcp_state.get("last_backup_id"),
            "last_backup_path": mcp_state.get("last_backup_path"),
            "last_operation": mcp_state.get("last_operation"),
            "last_summary": mcp_state.get("last_summary"),
            "last_diff": mcp_state.get("last_diff"),
        }

    def _load_editable_mcp_document(self, client: str, client_config: Dict[str, object]) -> Dict[str, object]:
        mcp_mode = client_config.get("mcp_mode")
        config_path = Path(client_config["mcp_config_path"])
        if mcp_mode == "codex-toml":
            return self._load_codex_mcp_document(config_path)
        if mcp_mode == "claude-json":
            return self._load_claude_mcp_document(config_path)
        if mcp_mode == "hermes-yaml":
            return self._load_hermes_mcp_document(config_path)
        raise RuntimeError("Client '{}' does not support writable MCP configuration".format(client))

    def _render_editable_mcp_document(self, client: str, client_config: Dict[str, object], document: Dict[str, object], entries: List[Dict[str, object]]) -> str:
        mcp_mode = client_config.get("mcp_mode")
        if mcp_mode == "codex-toml":
            return self._render_codex_mcp_document(document, entries)
        if mcp_mode == "claude-json":
            return self._render_claude_mcp_document(document, entries)
        if mcp_mode == "hermes-yaml":
            return self._render_hermes_mcp_document(document, entries)
        raise RuntimeError("Client '{}' does not support writable MCP configuration".format(client))

    def _mcp_diff_payload(self, client: str, before_text: str, after_text: str, *, from_label: str, to_label: str) -> Dict[str, object]:
        diff_lines = list(
            difflib.unified_diff(
                before_text.splitlines(),
                after_text.splitlines(),
                fromfile=from_label,
                tofile=to_label,
                lineterm="",
            )
        )
        added_count = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        removed_count = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        return {
            "client": client,
            "text": "\n".join(diff_lines),
            "line_count": len(diff_lines),
            "added_count": added_count,
            "removed_count": removed_count,
        }

    def _backup_mcp_config(self, client: str, config_path: Path, original_text: str, operation: str) -> Tuple[str, Path]:
        backup_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        backup_dir = self.backups_dir / backup_id / "mcp" / client
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / config_path.name).write_text(original_text, encoding="utf-8")
        write_json(
            backup_dir / "metadata.json",
            {
                "client": client,
                "operation": operation,
                "config_path": str(config_path),
                "backup_id": backup_id,
            },
        )
        return backup_id, backup_dir

    def _write_mcp_state(self, client: str, *, backup_id: Optional[str], backup_dir: Optional[Path], operation: str, summary: str, diff_payload: Dict[str, object]) -> None:
        mcp_state = self.load_mcp_state()
        mcp_state.setdefault("clients", {})[client] = {
            "last_changed_at": utc_now(),
            "last_backup_id": backup_id,
            "last_backup_path": str(backup_dir) if backup_dir else None,
            "last_operation": operation,
            "last_summary": summary,
            "last_diff": diff_payload,
        }
        self.save_mcp_state(mcp_state)

    def _managed_mcp_entries(self, payload: Dict[str, object]) -> List[Dict[str, object]]:
        return [dict(entry) for entry in payload.get("root_servers", [])]

    def mcp_list(self, client: str) -> Dict[str, object]:
        clients = self.load_clients()
        client_config = self._require_client(client, clients)
        return self._mcp_payload_for_client(client, client_config)

    def mcp_diff(self, client: str) -> Dict[str, object]:
        payload = self.mcp_list(client)
        return {
            "client": client,
            "source_status": payload["source_status"],
            "writable": payload["writable"],
            "last_backup_id": payload.get("last_backup_id"),
            "last_backup_path": payload.get("last_backup_path"),
            "last_changed_at": payload.get("last_changed_at"),
            "last_operation": payload.get("last_operation"),
            "last_summary": payload.get("last_summary"),
            "diff": payload.get("last_diff"),
            "duplicate_groups": payload.get("duplicate_groups", []),
        }

    def mcp_clients(self) -> Dict[str, object]:
        clients = self.load_clients()
        items = []
        for client in sorted(clients["clients"]):
            payload = self.mcp_list(client)
            items.append(
                {
                    "client": client,
                    "source_status": payload["source_status"],
                    "writable": payload["writable"],
                    "server_count": payload["server_count"],
                    "duplicate_count": len(payload.get("duplicate_groups", [])),
                    "notes": payload["notes"],
                }
            )
        return {"clients": items}

    def _apply_mcp_mutation(self, client: str, operation: str, mutator) -> Dict[str, object]:
        clients = self.load_clients()
        client_config = self._require_client(client, clients)
        payload = self._mcp_payload_for_client(client, client_config)
        if payload["source_status"] != "ok" or not payload["writable"]:
            raise RuntimeError("Client '{}' does not support writable MCP configuration".format(client))

        config_path = Path(client_config["mcp_config_path"])
        document = self._load_editable_mcp_document(client, client_config)
        entries = self._managed_mcp_entries(payload)
        updated_entries, summary = mutator(entries)
        if updated_entries is None:
            updated_entries = entries
        before_text = document["original_text"]
        after_text = self._render_editable_mcp_document(client, client_config, document, updated_entries)
        diff_payload = self._mcp_diff_payload(client, before_text, after_text, from_label="before", to_label="after")

        backup_id = None
        backup_dir = None
        if before_text != after_text:
            backup_id, backup_dir = self._backup_mcp_config(client, config_path, before_text, operation)
            encoding = "utf-8-sig" if client_config.get("mcp_mode") == "claude-json" else "utf-8"
            config_path.write_text(after_text, encoding=encoding)
        self._write_mcp_state(client, backup_id=backup_id, backup_dir=backup_dir, operation=operation, summary=summary, diff_payload=diff_payload)
        self.generate_reports()
        return {
            "client": client,
            "changed": before_text != after_text,
            "backup_id": backup_id,
            "backup_path": str(backup_dir) if backup_dir else None,
            "summary": summary,
            "diff": diff_payload,
            "mcp": self.mcp_list(client),
        }

    def mcp_enable(self, client: str, server_name: str) -> Dict[str, object]:
        def _mutate(entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], str]:
            for entry in entries:
                if entry["name"] == server_name:
                    entry["enabled"] = True
                    return entries, "已启用 '{}'".format(server_name)
            raise ValueError("Unknown MCP server '{}'".format(server_name))

        return self._apply_mcp_mutation(client, "enable", _mutate)

    def mcp_disable(self, client: str, server_name: str) -> Dict[str, object]:
        def _mutate(entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], str]:
            for entry in entries:
                if entry["name"] == server_name:
                    entry["enabled"] = False
                    return entries, "已禁用 '{}'".format(server_name)
            raise ValueError("Unknown MCP server '{}'".format(server_name))

        return self._apply_mcp_mutation(client, "disable", _mutate)

    def mcp_add(self, client: str, server_name: str, command: str, args: Optional[List[str]] = None, enabled: bool = True) -> Dict[str, object]:
        def _mutate(entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], str]:
            if any(entry["name"] == server_name for entry in entries):
                raise ValueError("MCP server '{}' already exists".format(server_name))
            next_index = max([entry.get("order_index", -1) for entry in entries] + [-1]) + 1
            entries.append(
                {
                    "name": server_name,
                    "source_kind": "root",
                    "managed": True,
                    "enabled": enabled,
                    "command": command,
                    "args": [str(item) for item in (args or [])],
                    "duplicate_group": None,
                    "notes": [],
                    "order_index": next_index,
                }
            )
            return entries, "已新增 '{}'".format(server_name)

        return self._apply_mcp_mutation(client, "add", _mutate)

    def mcp_update(
        self,
        client: str,
        server_name: str,
        *,
        new_name: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        enabled: Optional[bool] = None,
    ) -> Dict[str, object]:
        def _mutate(entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], str]:
            target = next((entry for entry in entries if entry["name"] == server_name), None)
            if target is None:
                raise ValueError("Unknown MCP server '{}'".format(server_name))
            if new_name and new_name != server_name and any(entry["name"] == new_name for entry in entries):
                raise ValueError("MCP server '{}' already exists".format(new_name))
            if new_name:
                target["name"] = new_name
            if command is not None:
                target["command"] = command
            if args is not None:
                target["args"] = [str(item) for item in args]
            if enabled is not None:
                target["enabled"] = enabled
            return entries, "已更新 '{}'".format(server_name)

        return self._apply_mcp_mutation(client, "update", _mutate)

    def mcp_remove(self, client: str, server_name: str) -> Dict[str, object]:
        def _mutate(entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], str]:
            remaining = [entry for entry in entries if entry["name"] != server_name]
            if len(remaining) == len(entries):
                raise ValueError("Unknown MCP server '{}'".format(server_name))
            return remaining, "已删除 '{}'".format(server_name)

        return self._apply_mcp_mutation(client, "remove", _mutate)

    def mcp_dedupe_codex(self) -> Dict[str, object]:
        client = "codex"

        def _mutate(entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], str]:
            groups: Dict[str, List[Dict[str, object]]] = {}
            for entry in entries:
                groups.setdefault(self._mcp_semantic_key(entry), []).append(entry)
            kept_entries = []
            removed_names = []
            fixed_groups = 0
            for group_entries in groups.values():
                if len(group_entries) == 1:
                    kept_entries.extend(group_entries)
                    continue
                fixed_groups += 1
                preferred = None
                for entry in group_entries:
                    base_name = self._base_mcp_name(entry["name"])
                    if entry["name"] == base_name and any(other["name"] != base_name for other in group_entries):
                        preferred = entry
                        break
                if preferred is None:
                    preferred = sorted(group_entries, key=lambda item: item.get("order_index", 0))[0]
                preferred["enabled"] = any(item.get("enabled") for item in group_entries)
                kept_entries.append(preferred)
                removed_names.extend([entry["name"] for entry in group_entries if entry is not preferred])
            kept_entries.sort(key=lambda item: item.get("order_index", 0))
            return kept_entries, "Codex MCP 去重完成：修复 {} 组，移除 {}".format(fixed_groups, ", ".join(removed_names) or "0 项")

        return self._apply_mcp_mutation(client, "dedupe", _mutate)

    def _merge_mcp_entries(self, entries: List[Dict[str, object]]) -> List[Dict[str, object]]:
        merged: Dict[str, Dict[str, object]] = {}
        for entry in entries:
            existing = merged.get(entry["name"])
            if existing is None or (existing["source_kind"] != "root" and entry["source_kind"] == "root"):
                merged[entry["name"]] = entry
        return [merged[name] for name in sorted(merged)]

    def _inventory_mcp_for_client(self, client: str, client_config: Dict[str, object]) -> Dict[str, object]:
        payload = self._mcp_payload_for_client(client, client_config)
        servers = payload["servers"]
        server_count = payload["server_count"]
        if payload["source_status"] == "ok":
            servers = self._merge_mcp_entries(payload["servers"])
            server_count = len(servers)
        return {
            "client": client,
            "source_status": payload["source_status"],
            "source_files": payload["source_files"],
            "server_count": server_count,
            "servers": servers,
            "notes": payload["notes"],
        }

    def _family_members(self, registry: Dict) -> Dict[str, List[Dict[str, object]]]:
        families: Dict[str, List[Dict[str, object]]] = {}
        for skill in registry["skills"].values():
            families.setdefault(skill["conflict_family"], []).append(skill)
        return families

    def _family_display_skill(self, members: List[Dict[str, object]]) -> Dict[str, object]:
        status_rank = {"active": 0, "shadowed": 1, "disabled": 2}
        return sorted(
            members,
            key=lambda item: (
                status_rank.get(str(item.get("status")), 9),
                str(item.get("name") or "").lower(),
                str(item.get("imported_at") or ""),
                str(item.get("skill_id") or ""),
            ),
        )[0]

    def _visible_members_for_client(self, client: str, members: List[Dict[str, object]]) -> List[Dict[str, object]]:
        visible = []
        for member in members:
            available_clients = member.get("available_clients", [])
            if available_clients and client not in available_clients:
                continue
            visible.append(member)
        return visible

    def _client_family_inventory_maps(self, registry: Dict, clients: Dict) -> Dict[str, Dict[str, object]]:
        result: Dict[str, Dict[str, object]] = {}
        for client in sorted(clients["clients"].keys()):
            inventory = self._inventory_skills_for_client(client, registry, clients)
            published_family_map = {}
            for skill_id in inventory.get("published_skill_ids", []):
                skill = registry["skills"].get(skill_id)
                if skill:
                    published_family_map[skill["conflict_family"]] = skill_id
            result[client] = {
                "inventory": inventory,
                "published": published_family_map,
                "live_only": {item.get("normalized_name") for item in inventory.get("live_only", [])},
                "pool_only": {item.get("normalized_name") for item in inventory.get("pool_only", [])},
                "source_mismatch": {item.get("normalized_name") for item in inventory.get("source_mismatch", [])},
            }
        return result

    def skills_matrix(
        self,
        *,
        query: Optional[str] = None,
        client: Optional[str] = None,
        anomaly: Optional[str] = None,
        source_scope: Optional[str] = None,
        include_instances: bool = True,
    ) -> Dict[str, object]:
        registry = self.load_registry()
        clients = self.load_clients()
        client_map = self._client_map(clients)
        family_map = self._family_members(registry)
        inventory_maps = self._client_family_inventory_maps(registry, clients)
        query_value = (query or "").strip().lower()
        rows = []
        for family, members in sorted(family_map.items()):
            display = self._family_display_skill(members)
            source_scopes = sorted({str(member.get("source_scope") or "-") for member in members})
            source_clients = sorted({str(member.get("source_client")) for member in members if member.get("source_client")})
            published_for = sorted({client_name for member in members for client_name in client_map.get(member["skill_id"], [])})
            row = {
                "conflict_family": family,
                "name": display.get("name"),
                "description": display.get("description", ""),
                "primary_skill_id": display.get("skill_id"),
                "member_count": len(members),
                "source_scopes": source_scopes,
                "source_clients": source_clients,
                "published_for": published_for,
                "has_conflict": len(members) > 1,
                "clients": {},
                "anomalies": [],
            }
            applicable_clients = 0
            for client_name in sorted(clients["clients"].keys()):
                visible_members = self._visible_members_for_client(client_name, members)
                if not visible_members:
                    row["clients"][client_name] = {"status": "not_applicable", "flags": [], "skill_id": None}
                    continue
                applicable_clients += 1
                published_skill_id = inventory_maps[client_name]["published"].get(family)
                live_only = family in inventory_maps[client_name]["live_only"]
                pool_only = family in inventory_maps[client_name]["pool_only"]
                source_mismatch_flag = family in inventory_maps[client_name]["source_mismatch"]
                enabled_candidates = [
                    member
                    for member in visible_members
                    if member.get("enabled_global") != "disabled"
                    and member.get("client_overrides", {}).get(client_name, "inherit") != "disabled"
                ]
                flags = []
                if any(member.get("status") == "shadowed" for member in visible_members):
                    flags.append("shadowed")
                if source_mismatch_flag:
                    status = "source_mismatch"
                elif published_skill_id:
                    status = "published"
                elif live_only:
                    status = "live_only"
                elif not enabled_candidates:
                    status = "disabled"
                elif pool_only:
                    status = "pool_only"
                elif flags:
                    status = "shadowed"
                else:
                    status = "pool_only"
                row["clients"][client_name] = {
                    "status": status,
                    "flags": flags,
                    "skill_id": published_skill_id,
                    "visible_skill_ids": [member["skill_id"] for member in visible_members],
                }
                if status in {"source_mismatch", "live_only", "pool_only", "disabled", "shadowed"}:
                    row["anomalies"].append({"client": client_name, "type": status})
            if applicable_clients > 1:
                row["anomalies"].append({"client": None, "type": "duplicate_across_clients"})
            if include_instances:
                row["instances"] = [
                    {
                        "skill_id": member["skill_id"],
                        "name": member["name"],
                        "status": member["status"],
                        "enabled_global": member["enabled_global"],
                        "fingerprint": member.get("fingerprint"),
                        "files_path": member.get("files_path"),
                        "source_scope": member.get("source_scope"),
                        "source_client": member.get("source_client"),
                        "source_root": member.get("source_root"),
                        "published_for": sorted(client_map.get(member["skill_id"], [])),
                        "client_overrides": dict(sorted(member.get("client_overrides", {}).items())),
                    }
                    for member in sorted(members, key=lambda item: (str(item.get("name") or "").lower(), item["skill_id"]))
                ]
            if source_scope and source_scope not in row["source_scopes"]:
                continue
            if client and row["clients"].get(client, {}).get("status") == "not_applicable":
                continue
            if anomaly:
                anomaly_types = {item["type"] for item in row["anomalies"]}
                if anomaly not in anomaly_types and row["clients"].get(client or "", {}).get("status") != anomaly:
                    continue
            if query_value:
                haystack = " ".join(
                    [
                        str(row.get("name") or ""),
                        str(row.get("description") or ""),
                        str(row.get("conflict_family") or ""),
                        " ".join(row.get("source_clients") or []),
                        " ".join(row.get("source_scopes") or []),
                    ]
                ).lower()
                if query_value not in haystack:
                    continue
            rows.append(row)
        return {"generated_at": utc_now(), "clients": sorted(clients["clients"].keys()), "total": len(rows), "rows": rows}

    def skills_instances(
        self,
        *,
        client: Optional[str] = None,
        family: Optional[str] = None,
        status: Optional[str] = None,
        enabled_global: Optional[str] = None,
        source_scope: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_dir: str = "asc",
    ) -> Dict[str, object]:
        return self.list_skills(
            client=client,
            family=family,
            status=status,
            enabled_global=enabled_global,
            source_scope=source_scope,
            query=query,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    def _compute_discovery_payload(self) -> Dict[str, object]:
        registry = self.load_registry()
        scan_sources = self.load_scan_sources()
        registry_by_fingerprint: Dict[str, List[Dict[str, object]]] = {}
        registry_by_family = self._family_members(registry)
        for skill in registry["skills"].values():
            registry_by_fingerprint.setdefault(skill.get("fingerprint"), []).append(skill)

        source_summaries = []
        untracked = []
        mismatches = []
        transient_only = []
        for source in sorted(scan_sources.get("sources", {}).values(), key=lambda item: (str(item.get("path_kind")), str(item.get("path")))):
            discovered = self._scan_source_skill_entries(source) if self._source_exists(str(source.get("path"))) else []
            managed_count = 0
            untracked_count = 0
            mismatch_count = 0
            for item in discovered:
                fingerprint = item.get("fingerprint")
                family_matches = registry_by_family.get(item.get("normalized_name"), [])
                if fingerprint and fingerprint in registry_by_fingerprint:
                    managed_count += 1
                    continue
                payload = {
                    "scan_source_id": source.get("id"),
                    "path": item.get("path"),
                    "name": item.get("name"),
                    "normalized_name": item.get("normalized_name"),
                    "source_root": source.get("path"),
                    "path_kind": source.get("path_kind"),
                    "role": source.get("role"),
                    "client": source.get("client"),
                    "reason": "",
                }
                if family_matches:
                    mismatch_count += 1
                    payload["reason"] = "发现了同族但内容不一致的 skill"
                    payload["pool_matches"] = [
                        {"skill_id": match["skill_id"], "path": match.get("files_path"), "source_scope": match.get("source_scope")}
                        for match in family_matches
                    ]
                    mismatches.append(payload)
                else:
                    untracked_count += 1
                    payload["reason"] = "扫描源发现了尚未纳管的 skill"
                    untracked.append(payload)
                    if source.get("path_kind") == "transient":
                        transient_only.append(payload)
            source_summaries.append(
                {
                    "id": source.get("id"),
                    "path": source.get("path"),
                    "role": source.get("role"),
                    "client": source.get("client"),
                    "path_kind": source.get("path_kind"),
                    "enabled": bool(source.get("enabled")),
                    "suggested": bool(source.get("suggested")),
                    "exists": self._source_exists(str(source.get("path"))),
                    "discovered_count": len(discovered),
                    "managed_count": managed_count,
                    "untracked_count": untracked_count,
                    "source_mismatch_count": mismatch_count,
                    "notes": source.get("notes"),
                }
            )
        matrix = self.skills_matrix(include_instances=False)
        duplicates = [
            {
                "conflict_family": row["conflict_family"],
                "name": row["name"],
                "clients": [client_name for client_name, payload in row["clients"].items() if payload.get("status") != "not_applicable"],
            }
            for row in matrix["rows"]
            if any(item["type"] == "duplicate_across_clients" for item in row["anomalies"])
        ]
        return {
            "generated_at": utc_now(),
            "stale": False,
            "sources": source_summaries,
            "untracked_discovered": untracked,
            "source_mismatch": mismatches,
            "transient_only": transient_only,
            "duplicate_across_clients": duplicates,
        }

    def refresh_discovery_cache(self) -> Dict[str, object]:
        payload = self._compute_discovery_payload()
        self.save_discovery_cache(payload)
        return payload

    def discovery(self, *, refresh: bool = False) -> Dict[str, object]:
        cache = self.load_discovery_cache()
        if refresh or not cache.get("generated_at"):
            return self.refresh_discovery_cache()
        return cache

    def discovery_summary(self, *, refresh: bool = False) -> Dict[str, object]:
        payload = self.discovery(refresh=refresh)
        def _first(items):
            return items[0] if items else None
        return {
            "generated_at": payload.get("generated_at"),
            "stale": bool(payload.get("stale")),
            "counts": {
                "sources": len(payload.get("sources", [])),
                "untracked_discovered": len(payload.get("untracked_discovered", [])),
                "source_mismatch": len(payload.get("source_mismatch", [])),
                "transient_only": len(payload.get("transient_only", [])),
                "duplicate_across_clients": len(payload.get("duplicate_across_clients", [])),
            },
            "first_examples": {
                "untracked_discovered": _first(payload.get("untracked_discovered", [])),
                "source_mismatch": _first(payload.get("source_mismatch", [])),
                "transient_only": _first(payload.get("transient_only", [])),
                "duplicate_across_clients": _first(payload.get("duplicate_across_clients", [])),
            },
        }

    def discovery_details(self, group: str, *, limit: Optional[int] = None, refresh: bool = False) -> Dict[str, object]:
        payload = self.discovery(refresh=refresh)
        valid_groups = {
            "sources",
            "untracked_discovered",
            "source_mismatch",
            "transient_only",
            "duplicate_across_clients",
        }
        if group not in valid_groups:
            raise ValueError("Unknown discovery group '{}'".format(group))
        items = list(payload.get(group, []))
        if limit is not None and limit >= 0:
            items = items[:limit]
        return {
            "group": group,
            "generated_at": payload.get("generated_at"),
            "stale": bool(payload.get("stale")),
            "total": len(payload.get(group, [])),
            "items": items,
        }

    def inventory(
        self,
        client: Optional[str] = None,
        *,
        include_skills: bool = True,
        include_mcp: bool = True,
        summary_only: bool = False,
    ) -> Dict[str, object]:
        registry = self.load_registry()
        clients = self.load_clients()
        client_names = [client] if client else sorted(clients["clients"].keys())
        results = []
        for client_name in client_names:
            client_config = self._require_client(client_name, clients)
            payload: Dict[str, object] = {"client": client_name}
            if include_skills:
                payload["skills"] = self._inventory_skills_for_client(client_name, registry, clients)
            if include_mcp:
                payload["mcp"] = self._inventory_mcp_for_client(client_name, client_config)
            results.append(payload)

        generated_at = utc_now()
        if client:
            result = results[0]
            result["generated_at"] = generated_at
            return result
        if summary_only:
            summary = []
            for item in results:
                client_summary = {"client": item["client"]}
                if include_skills:
                    client_summary["skills"] = {
                        key: item["skills"][key]
                        for key in (
                            "pool_visible_count",
                            "published_count",
                            "live_target_count",
                            "live_extra_dir_count",
                            "live_total_count",
                            "unmanaged_live_count",
                            "published_missing_from_live_count",
                            "pool_not_published_count",
                        )
                    }
                if include_mcp:
                    client_summary["mcp"] = {
                        "source_status": item["mcp"]["source_status"],
                        "server_count": item["mcp"]["server_count"],
                        "notes": item["mcp"]["notes"],
                    }
                summary.append(client_summary)
            return {"generated_at": generated_at, "clients": summary}
        return {"generated_at": generated_at, "clients": results}

    def _skill_source_records(self, skill: Dict[str, object]) -> List[Dict[str, object]]:
        records = list(skill.get("sources", []))
        if not records and skill.get("source_locator"):
            records.append(
                {
                    "source_type": skill.get("source_type"),
                    "source_locator": skill.get("source_locator"),
                    "source_version": skill.get("source_version"),
                    "source_client": skill.get("source_client"),
                    "source_scope": skill.get("source_scope"),
                    "source_root": skill.get("source_root"),
                    "imported_at": skill.get("imported_at"),
                }
            )
        records.sort(
            key=lambda item: (
                str(item.get("source_client") or ""),
                str(item.get("source_scope") or ""),
                str(item.get("source_type") or ""),
                str(item.get("source_locator") or ""),
            )
        )
        return records

    def _skill_payload(self, skill: Dict[str, object], client_map: Dict[str, List[str]]) -> Dict[str, object]:
        published_for = sorted(client_map.get(skill["skill_id"], []))
        available_clients = sorted(skill.get("available_clients", []))
        return {
            "skill_id": skill["skill_id"],
            "name": skill["name"],
            "description": skill.get("description", ""),
            "normalized_name": skill.get("normalized_name"),
            "conflict_family": skill["conflict_family"],
            "source_type": skill.get("source_type"),
            "source_locator": skill.get("source_locator"),
            "source_version": skill.get("source_version"),
            "source_scope": skill.get("source_scope"),
            "source_client": skill.get("source_client"),
            "source_root": skill.get("source_root"),
            "enabled_global": skill["enabled_global"],
            "status": skill["status"],
            "published_name": skill["published_name"],
            "available_clients": available_clients,
            "published_for": published_for,
            "client_overrides": dict(sorted(skill.get("client_overrides", {}).items())),
            "fingerprint": skill["fingerprint"],
            "imported_at": skill["imported_at"],
            "last_seen_at": skill.get("last_seen_at"),
            "missing_from_source": skill.get("missing_from_source", False),
            "files_path": skill.get("files_path"),
            "origin_directory_name": skill.get("origin_directory_name"),
            "source_count": len(self._skill_source_records(skill)),
        }

    def _skill_sort_key(self, item: Dict[str, object], sort_by: str):
        status_rank = {"active": 0, "shadowed": 1, "disabled": 2}
        if sort_by == "status":
            return (
                status_rank.get(str(item.get("status")), 99),
                str(item.get("name") or "").lower(),
                str(item.get("skill_id") or ""),
            )
        if sort_by == "imported_at":
            return (
                str(item.get("imported_at") or ""),
                str(item.get("name") or "").lower(),
                str(item.get("skill_id") or ""),
            )
        if sort_by == "last_seen_at":
            return (
                str(item.get("last_seen_at") or ""),
                str(item.get("name") or "").lower(),
                str(item.get("skill_id") or ""),
            )
        if sort_by == "source_scope":
            return (
                str(item.get("source_scope") or ""),
                str(item.get("name") or "").lower(),
                str(item.get("skill_id") or ""),
            )
        return (
            str(item.get("name") or "").lower(),
            str(item.get("conflict_family") or ""),
            str(item.get("skill_id") or ""),
        )

    def list_skills(
        self,
        *,
        client: Optional[str] = None,
        family: Optional[str] = None,
        status: Optional[str] = None,
        enabled_global: Optional[str] = None,
        source_scope: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_dir: str = "asc",
        registry: Optional[Dict] = None,
        clients: Optional[Dict] = None,
    ) -> Dict[str, object]:
        registry = registry or self.load_registry()
        clients = clients or self.load_clients()
        client_map = self._client_map(clients)
        query_value = (query or "").strip().lower()
        sort_by = (sort_by or "name").strip().lower()
        sort_dir = (sort_dir or "asc").strip().lower()
        if sort_by not in {"name", "status", "imported_at", "last_seen_at", "source_scope"}:
            raise ValueError("Unsupported sort_by: {}".format(sort_by))
        if sort_dir not in {"asc", "desc"}:
            raise ValueError("Unsupported sort_dir: {}".format(sort_dir))
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 50), 1), 200)
        items = []
        for skill in registry["skills"].values():
            available_clients = sorted(skill.get("available_clients", []))
            visible_for_client = not available_clients or (client in available_clients if client else True)
            if client and not visible_for_client:
                continue
            if family and skill["conflict_family"] != family:
                continue
            if status and skill["status"] != status:
                continue
            if enabled_global and skill["enabled_global"] != enabled_global:
                continue
            if source_scope and skill.get("source_scope") != source_scope:
                continue
            if query_value:
                haystack = " ".join(
                    [
                        skill["skill_id"],
                        skill["name"],
                        skill.get("description", ""),
                        skill["conflict_family"],
                        skill.get("source_type", ""),
                        skill.get("source_locator", ""),
                        skill.get("source_scope", ""),
                        skill.get("source_client") or "",
                    ]
                ).lower()
                if query_value not in haystack:
                    continue
            items.append(self._skill_payload(skill, client_map))
        items.sort(key=lambda item: self._skill_sort_key(item, sort_by), reverse=sort_dir == "desc")
        total = len(items)
        total_pages = ((total + page_size - 1) // page_size) if total else 0
        if total_pages:
            page = min(page, total_pages)
        start_index = (page - 1) * page_size if total else 0
        paged_items = items[start_index : start_index + page_size]
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "filters": {
                "client": client,
                "family": family,
                "status": status,
                "enabled_global": enabled_global,
                "source_scope": source_scope,
                "query": query,
            },
            "skills": paged_items,
        }

    def get_skill(self, skill_id: str, *, registry: Optional[Dict] = None, clients: Optional[Dict] = None) -> Dict[str, object]:
        registry = registry or self.load_registry()
        clients = clients or self.load_clients()
        skill = registry["skills"].get(skill_id)
        if not skill:
            raise FileNotFoundError("Unknown skill_id: {}".format(skill_id))
        client_map = self._client_map(clients)
        detail = self._skill_payload(skill, client_map)
        related_members = []
        for member in registry["skills"].values():
            if member["conflict_family"] != skill["conflict_family"] or member["skill_id"] == skill_id:
                continue
            payload = self._skill_payload(member, client_map)
            related_members.append(
                {
                    "skill_id": payload["skill_id"],
                    "name": payload["name"],
                    "status": payload["status"],
                    "enabled_global": payload["enabled_global"],
                    "source_scope": payload["source_scope"],
                    "source_client": payload["source_client"],
                    "published_for": payload["published_for"],
                    "client_overrides": payload["client_overrides"],
                }
            )
        related_members.sort(key=lambda item: (item["name"].lower(), item["skill_id"]))
        detail.update(
            {
                "source_records": self._skill_source_records(skill),
                "conflict_member_count": len(related_members) + 1,
                "conflict_members": related_members,
                "family_has_conflict": bool(related_members),
            }
        )
        return detail

    def list_conflicts(
        self,
        *,
        family: Optional[str] = None,
        registry: Optional[Dict] = None,
        clients: Optional[Dict] = None,
    ) -> Dict[str, object]:
        registry = registry or self.load_registry()
        clients = clients or self.load_clients()
        client_map = self._client_map(clients)
        families = {}
        for skill in registry["skills"].values():
            families.setdefault(skill["conflict_family"], []).append(skill)
        conflicts = []
        for family_name, members in sorted(families.items()):
            if family and family_name != family:
                continue
            if len(members) < 2:
                continue
            member_ids = {member["skill_id"] for member in members}
            client_winners = {}
            winner_skill_ids = []
            override_summary = {}
            for client, config in clients["clients"].items():
                winner = next((skill_id for skill_id in config.get("published_skill_ids", []) if skill_id in member_ids), None)
                if winner:
                    client_winners[client] = winner
                    winner_skill_ids.append(winner)
                overrides = []
                for member in members:
                    override = member.get("client_overrides", {}).get(client)
                    if override and override != "inherit":
                        overrides.append({"skill_id": member["skill_id"], "override": override})
                if overrides:
                    override_summary[client] = overrides
            conflict_members = []
            for member in sorted(members, key=lambda item: item["skill_id"]):
                conflict_members.append(
                    {
                        "skill_id": member["skill_id"],
                        "name": member["name"],
                        "source_type": member.get("source_type"),
                        "source_scope": member.get("source_scope"),
                        "source_client": member.get("source_client"),
                        "enabled_global": member["enabled_global"],
                        "status": member["status"],
                        "published_for": sorted(client_map.get(member["skill_id"], [])),
                        "client_overrides": dict(sorted(member.get("client_overrides", {}).items())),
                    }
                )
            conflicts.append(
                {
                    "conflict_family": family_name,
                    "member_count": len(conflict_members),
                    "winner_skill_ids": sorted(set(winner_skill_ids)),
                    "client_winners": client_winners,
                    "override_summary": override_summary,
                    "members": conflict_members,
                }
            )
        return {"total": len(conflicts), "family": family, "conflicts": conflicts}

    def cleanup_scan(self) -> Dict[str, object]:
        registry = self.load_registry()
        clients = self.load_clients()
        client_map = self._client_map(clients)
        existing = self.load_cleanup_candidates()
        previous_labels = {
            skill_id: item.get("label", "candidate")
            for skill_id, item in existing.get("candidates", {}).items()
        }
        previous_notes = {
            skill_id: item.get("manual_note")
            for skill_id, item in existing.get("candidates", {}).items()
        }

        candidates: Dict[str, Dict[str, object]] = {}

        def add_candidate(skill_id: str, reason_type: str, message: str, *, client: Optional[str] = None, extra: Optional[Dict[str, object]] = None) -> None:
            skill = registry["skills"].get(skill_id)
            if not skill:
                return
            payload = self._skill_payload(skill, client_map)
            item = candidates.setdefault(
                skill_id,
                {
                    "skill_id": skill_id,
                    "name": payload["name"],
                    "conflict_family": payload["conflict_family"],
                    "status": payload["status"],
                    "source_scope": payload["source_scope"],
                    "source_client": payload["source_client"],
                    "source_root": payload.get("source_root"),
                    "published_for": payload["published_for"],
                    "label": previous_labels.get(skill_id, "candidate"),
                    "manual_note": previous_notes.get(skill_id),
                    "reasons": [],
                },
            )
            reason_payload = {"type": reason_type, "message": message}
            if client:
                reason_payload["client"] = client
            if extra:
                reason_payload.update(extra)
            item["reasons"].append(reason_payload)

        for client in sorted(clients["clients"]):
            inventory = self.inventory(client=client, include_mcp=False)
            for item in inventory["skills"].get("pool_only", []):
                if item.get("skill_id"):
                    add_candidate(item["skill_id"], "pool_only", item["reason"], client=client)
            for item in inventory["skills"].get("source_mismatch", []):
                for match in item.get("pool_matches", []):
                    if match.get("skill_id"):
                        add_candidate(match["skill_id"], "source_mismatch", item["reason"], client=client, extra={"live_path": item.get("path")})

        normalized_groups: Dict[str, List[Dict[str, object]]] = {}
        for skill in registry["skills"].values():
            if skill["status"] == "shadowed":
                add_candidate(skill["skill_id"], "shadowed", "该 skill 当前处于 shadowed 状态。")
            normalized_groups.setdefault(skill.get("normalized_name") or skill["conflict_family"], []).append(skill)

        conflicts = self.list_conflicts(registry=registry, clients=clients)["conflicts"]
        for conflict in conflicts:
            for member in conflict["members"]:
                if not member.get("published_for"):
                    add_candidate(member["skill_id"], "unpublished_conflict_member", "该冲突族成员当前未发布到任何客户端。")

        for members in normalized_groups.values():
            if len(members) < 2:
                continue
            fingerprints = {member["fingerprint"] for member in members}
            if len(fingerprints) <= 1:
                for member in members:
                    add_candidate(member["skill_id"], "duplicate_name_family", "同名或近似同名 skill 出现多份内容相同的来源记录。")

        order = sorted(candidates, key=lambda skill_id: (candidates[skill_id]["name"].lower(), skill_id))
        cleanup_state = {
            "version": REGISTRY_VERSION,
            "generated_at": utc_now(),
            "candidates": candidates,
            "order": order,
        }
        self.save_cleanup_candidates(cleanup_state)
        self.generate_reports(registry=registry, clients=clients)
        return {"generated_at": cleanup_state["generated_at"], "total": len(order), "candidates": [candidates[skill_id] for skill_id in order]}

    def cleanup_list(self) -> Dict[str, object]:
        cleanup_state = self.load_cleanup_candidates()
        return {
            "generated_at": cleanup_state.get("generated_at"),
            "total": len(cleanup_state.get("order", [])),
            "candidates": [cleanup_state["candidates"][skill_id] for skill_id in cleanup_state.get("order", []) if skill_id in cleanup_state.get("candidates", {})],
        }

    def cleanup_mark(self, skill_id: str, label: str) -> Dict[str, object]:
        if label not in {"candidate", "keep", "ignore"}:
            raise ValueError("cleanup label must be one of candidate, keep, ignore")
        cleanup_state = self.load_cleanup_candidates()
        candidate = cleanup_state.get("candidates", {}).get(skill_id)
        if not candidate:
            raise FileNotFoundError("Unknown cleanup candidate '{}'".format(skill_id))
        candidate["label"] = label
        cleanup_state["candidates"][skill_id] = candidate
        self.save_cleanup_candidates(cleanup_state)
        self.generate_reports()
        return candidate

    def cleanup_export(self) -> Dict[str, object]:
        cleanup_state = self.load_cleanup_candidates()
        registry = self.load_registry()
        clients = self.load_clients()
        markdown = self._build_cleanup_candidates_report(cleanup_state, registry, clients)
        self.cleanup_report_path.write_text(markdown, encoding="utf-8")
        write_json(self.cleanup_export_path, cleanup_state)
        return {
            "markdown_path": str(self.cleanup_report_path),
            "json_path": str(self.cleanup_export_path),
        }

    def inventory_export(self, *, client: Optional[str] = None, format: str = "json") -> Dict[str, object]:
        format = (format or "json").strip().lower()
        inventory = self.inventory(client=client, summary_only=False)
        if format == "json":
            content = json_preview(inventory)
            return {
                "format": "json",
                "filename": "inventory-{}.json".format(client or "all"),
                "content_type": "application/json; charset=utf-8",
                "content": content,
            }
        if format != "markdown":
            raise ValueError("inventory export format must be json or markdown")
        markdown = self._build_inventory_markdown({"generated_at": utc_now(), "clients": [inventory] if client else inventory["clients"]})
        return {
            "format": "markdown",
            "filename": "inventory-{}.md".format(client or "all"),
            "content_type": "text/markdown; charset=utf-8",
            "content": markdown,
        }

    def get_reports(self) -> Dict[str, object]:
        self.generate_reports()
        reports = {}
        for report_id, filename in (
            ("skills_index", "SKILLS_INDEX.md"),
            ("conflicts", "CONFLICTS.md"),
            ("inventory", "INVENTORY.md"),
            ("cleanup_candidates", "CLEANUP_CANDIDATES.md"),
        ):
            path = self.reports_dir / filename
            reports[report_id] = {
                "id": report_id,
                "path": str(path),
                "content": path.read_text(encoding="utf-8") if path.exists() else "",
                "updated_at": (
                    datetime.utcfromtimestamp(path.stat().st_mtime).replace(microsecond=0).isoformat() + "Z"
                    if path.exists()
                    else None
                ),
            }
        return {"reports": reports}

    def _build_skills_index(self, registry: Dict, clients: Dict) -> str:
        skills_data = self.list_skills(registry=registry, clients=clients)["skills"]
        lines = [
            "# SKILLS_INDEX",
            "",
            "生成时间: {}".format(utc_now()),
            "",
            "## 概览",
            "",
            "- 技能总数: {}".format(len(registry["skills"])),
            "- 客户端: {}".format(", ".join(sorted(clients["clients"].keys()))),
            "",
            "## 技能列表",
            "",
            "| skill_id | 名称 | 冲突族 | 来源 | 来源范围 | 来源客户端 | 来源根目录 | 可见客户端 | 全局启用 | 当前状态 | 已发布到 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for skill in skills_data:
            lines.append(
                "| {skill_id} | {name} | {family} | {source} | {source_scope} | {source_client} | {source_root} | {available} | {enabled} | {status} | {published} |".format(
                    skill_id=skill["skill_id"],
                    name=skill["name"].replace("|", "/"),
                    family=skill["conflict_family"],
                    source=(skill["source_type"] or "-"),
                    source_scope=(skill["source_scope"] or "-"),
                    source_client=(skill["source_client"] or "-"),
                    source_root=(skill.get("source_root") or "-").replace("|", "/"),
                    available=", ".join(skill["available_clients"]) or "全部",
                    enabled={"enabled": "已启用", "disabled": "已禁用"}.get(skill["enabled_global"], skill["enabled_global"]),
                    status={"active": "生效中", "shadowed": "被遮蔽", "disabled": "已禁用"}.get(skill["status"], skill["status"]),
                    published=", ".join(skill["published_for"]) or "-",
                )
            )
        return "\n".join(lines) + "\n"

    def _build_conflicts_report(self, registry: Dict, clients: Dict) -> str:
        conflicts = self.list_conflicts(registry=registry, clients=clients)["conflicts"]
        lines = [
            "# CONFLICTS",
            "",
            "生成时间: {}".format(utc_now()),
            "",
        ]
        for conflict in conflicts:
            lines.append("## {}".format(conflict["conflict_family"]))
            lines.append("")
            winners = ", ".join(conflict["winner_skill_ids"]) or "-"
            override_summary = ", ".join(
                "{}={}".format(
                    client,
                    "; ".join("{}:{}".format(item["skill_id"], item["override"]) for item in items),
                )
                for client, items in sorted(conflict["override_summary"].items())
            ) or "-"
            lines.append("- 当前胜出项: `{}`".format(winners))
            lines.append("- 各客户端胜出项: {}".format(", ".join("{}={}".format(client, skill_id) for client, skill_id in sorted(conflict["client_winners"].items())) or "-"))
            lines.append("- Override 摘要: {}".format(override_summary))
            lines.append("")
            lines.append("| skill_id | 名称 | 来源 | 来源范围 | 全局启用 | 当前状态 | 已发布到 | 客户端覆盖 |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
            for skill in conflict["members"]:
                overrides = ", ".join(
                    "{}={}".format(client, value)
                    for client, value in sorted(skill["client_overrides"].items())
                ) or "-"
                lines.append(
                    "| {skill_id} | {name} | {source} | {source_scope} | {enabled} | {status} | {published_for} | {overrides} |".format(
                        skill_id=skill["skill_id"],
                        name=skill["name"].replace("|", "/"),
                        source=skill["source_type"],
                        source_scope={"target_dir": "目标目录", "extra_dir": "额外目录", "imported": "导入项"}.get(skill["source_scope"], skill["source_scope"]),
                        enabled={"enabled": "已启用", "disabled": "已禁用"}.get(skill["enabled_global"], skill["enabled_global"]),
                        status={"active": "生效中", "shadowed": "被遮蔽", "disabled": "已禁用"}.get(skill["status"], skill["status"]),
                        published_for=", ".join(skill["published_for"]) or "-",
                        overrides=overrides,
                    )
                )
            lines.append("")
        if len(lines) == 4:
            lines.extend(["当前没有包含多个技能的冲突族。", ""])
        return "\n".join(lines) + "\n"

    def _build_inventory_markdown(self, inventory: Dict[str, object]) -> str:
        lines = [
            "# INVENTORY",
            "",
            "生成时间: {}".format(inventory["generated_at"]),
            "",
            "## 说明",
            "",
            "- 本报告用于解释每个客户端的 `pool`、`published`、`live target`、`live extraDirs` 与 MCP 配置源差异。",
            "- `unsupported_source` 表示当前没有稳定的标准 MCP server registry 配置源，不能把它当成 `0`。",
            "",
        ]

        for client_entry in inventory["clients"]:
            client = client_entry["client"]
            skills = client_entry.get("skills", {})
            mcp = client_entry.get("mcp", {})
            lines.extend(
                [
                    "## {}".format(client),
                    "",
                    "### 技能盘点",
                    "",
                    "- pool_visible_count: {}".format(skills.get("pool_visible_count", "-")),
                    "- published_count: {}".format(skills.get("published_count", "-")),
                    "- live_target_count: {}".format(skills.get("live_target_count", "-")),
                    "- live_extra_dir_count: {}".format(skills.get("live_extra_dir_count", "-")),
                    "- live_total_count: {}".format(skills.get("live_total_count", "-")),
                    "- unmanaged_live_count: {}".format(skills.get("unmanaged_live_count", "-")),
                    "- published_missing_from_live_count: {}".format(skills.get("published_missing_from_live_count", "-")),
                    "- pool_not_published_count: {}".format(skills.get("pool_not_published_count", "-")),
                    "",
                    "### 技能来源目录",
                    "",
                ]
            )

            source_directories = skills.get("source_directories", [])
            if source_directories:
                for source in source_directories:
                    lines.append(
                        "- {} [{}]".format(
                            source["path"],
                            ", ".join(source.get("roles", [])) or "-",
                        )
                    )
            else:
                lines.append("- 未发现可解释的技能来源目录")
            lines.append("")

            lines.extend(
                [
                    "### 关键差异",
                    "",
                    "- live_only: {}".format(len(skills.get("live_only", []))),
                    "- pool_only: {}".format(len(skills.get("pool_only", []))),
                    "- published_only: {}".format(len(skills.get("published_only", []))),
                    "- source_mismatch: {}".format(len(skills.get("source_mismatch", []))),
                    "",
                ]
            )

            diff_groups = (
                ("live_only", "live 独有"),
                ("pool_only", "仅池内"),
                ("published_only", "发布缺失"),
                ("source_mismatch", "来源不一致"),
            )
            for key, title in diff_groups:
                entries = skills.get(key, [])
                lines.append("#### {}".format(title))
                lines.append("")
                if not entries:
                    lines.append("- 无")
                    lines.append("")
                    continue
                lines.append("| 名称 | skill_id | 路径 | 范围 | 原因 |")
                lines.append("| --- | --- | --- | --- | --- |")
                for item in entries:
                    lines.append(
                        "| {name} | {skill_id} | {path} | {scope} | {reason} |".format(
                            name=(item.get("name") or "-").replace("|", "/"),
                            skill_id=(item.get("skill_id") or "-").replace("|", "/"),
                            path=(item.get("path") or "-").replace("|", "/"),
                            scope=(item.get("scope") or "-").replace("|", "/"),
                            reason=(item.get("reason") or "-").replace("|", "/"),
                        )
                    )
                lines.append("")

            lines.extend(
                [
                    "### MCP 配置盘点",
                    "",
                    "- source_status: {}".format(mcp.get("source_status", "-")),
                    "- server_count: {}".format(
                        mcp["server_count"] if mcp.get("server_count") is not None else "当前无法可靠统计"
                    ),
                    "",
                    "#### 配置源文件",
                    "",
                ]
            )
            source_files = mcp.get("source_files", [])
            if source_files:
                for source_file in source_files:
                    lines.append("- {}".format(source_file))
            else:
                lines.append("- 无")
            lines.append("")

            lines.append("#### MCP Servers")
            lines.append("")
            servers = mcp.get("servers", [])
            if servers:
                lines.append("| 名称 | 启用 | 命令 | 参数 | 来源文件 |")
                lines.append("| --- | --- | --- | --- | --- |")
                for server in servers:
                    lines.append(
                        "| {name} | {enabled} | {command} | {args} | {source_file} |".format(
                            name=(server.get("name") or "-").replace("|", "/"),
                            enabled="是" if server.get("enabled") else "否",
                            command=(server.get("command") or "-").replace("|", "/"),
                            args=(" ".join(server.get("args") or []) or "-").replace("|", "/"),
                            source_file=(server.get("source_file") or "-").replace("|", "/"),
                        )
                    )
            else:
                lines.append("- 当前没有可列出的 MCP server 条目")
            lines.append("")

            lines.append("#### 备注")
            lines.append("")
            for note in mcp.get("notes", []) or ["无"]:
                lines.append("- {}".format(note))
            lines.append("")

        return "\n".join(lines) + "\n"

    def _build_inventory_report(self) -> str:
        return self._build_inventory_markdown(self.inventory(summary_only=False))

    def _build_cleanup_candidates_report(self, cleanup_state: Dict, registry: Dict, clients: Dict) -> str:
        lines = [
            "# CLEANUP_CANDIDATES",
            "",
            "生成时间: {}".format(cleanup_state.get("generated_at") or utc_now()),
            "",
            "## 概览",
            "",
            "- 候选总数: {}".format(len(cleanup_state.get("order", []))),
            "",
            "| skill_id | 名称 | 标签 | 当前状态 | 来源范围 | 来源客户端 | 已发布到 | 原因 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for skill_id in cleanup_state.get("order", []):
            item = cleanup_state.get("candidates", {}).get(skill_id)
            if not item:
                continue
            reasons = "; ".join("{}:{}".format(reason.get("type"), reason.get("message")) for reason in item.get("reasons", [])) or "-"
            lines.append(
                "| {skill_id} | {name} | {label} | {status} | {source_scope} | {source_client} | {published_for} | {reasons} |".format(
                    skill_id=skill_id,
                    name=(item.get("name") or "-").replace("|", "/"),
                    label=item.get("label", "candidate"),
                    status=item.get("status", "-"),
                    source_scope=item.get("source_scope") or "-",
                    source_client=item.get("source_client") or "-",
                    published_for=", ".join(item.get("published_for") or []) or "-",
                    reasons=reasons.replace("|", "/"),
                )
            )
        return "\n".join(lines) + "\n"

    def _resolve_manifest(self, client: str, registry: Dict) -> Dict[str, object]:
        groups = {}
        for skill in registry["skills"].values():
            groups.setdefault(skill["conflict_family"], []).append(skill)
        published = []
        for family, members in sorted(groups.items()):
            candidates = []
            preferred = None
            for skill in members:
                available_clients = skill.get("available_clients", [])
                if available_clients and client not in available_clients:
                    continue
                override = skill.get("client_overrides", {}).get(client, "inherit")
                if skill["enabled_global"] == "disabled":
                    continue
                if override == "disabled":
                    continue
                candidates.append(skill)
                if self._is_preferred(skill, client):
                    preferred = skill
            if not candidates:
                continue
            scope_rank = {"target_dir": 0, "extra_dir": 1, "imported": 2}
            chosen = preferred or sorted(
                candidates,
                key=lambda item: (
                    scope_rank.get(item.get("source_scope", "imported"), 9),
                    item["imported_at"],
                    item["skill_id"],
                ),
            )[0]
            published.append(chosen["skill_id"])
        return {
            "client": client,
            "generated_at": utc_now(),
            "published_skill_ids": published,
        }

    def _clear_existing_skill_dirs(self, target_dir: Path) -> None:
        for skill_dir in self.discover_skills(target_dir):
            safe_rmtree(skill_dir)
        self._remove_empty_dirs(target_dir)

    def _remove_empty_dirs(self, root: Path) -> None:
        if not root.exists():
            return
        for current_root, dirnames, _filenames in os.walk(str(root), topdown=False):
            for dirname in dirnames:
                directory = Path(current_root) / dirname
                if not directory.exists():
                    continue
                try:
                    directory.rmdir()
                except OSError:
                    continue

    def _backup_client_state(self, client: str, client_config: Dict[str, object]) -> str:
        backup_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        backup_root = self.backups_dir / backup_id / client
        backup_root.mkdir(parents=True, exist_ok=True)
        target_dir = Path(client_config["target_dir"])
        if target_dir.exists():
            copy_existing_tree(target_dir, backup_root / "target")
        config_path = client_config.get("config_path")
        if config_path and Path(config_path).exists():
            shutil.copy2(str(Path(config_path)), str(backup_root / "config.json"))
        state_snapshot = {
            "last_published_at": client_config.get("last_published_at"),
            "last_backup_id": client_config.get("last_backup_id"),
            "published_skill_ids": client_config.get("published_skill_ids", []),
        }
        write_json(backup_root / "client_state.json", state_snapshot)
        return backup_id

    def _resolve_backup_dir(self, client: str, backup_id: Optional[str]) -> Optional[Path]:
        if not backup_id:
            return None
        path = self.backups_dir / backup_id / client
        return path if path.exists() else None

    def _rewrite_openclaw_config(self, config_path: Path, target_dir: Path) -> None:
        if not config_path.exists():
            return
        data = json.loads(config_path.read_text(encoding="utf-8"))
        skills = data.setdefault("skills", {})
        load = skills.setdefault("load", {})
        load["extraDirs"] = [str(target_dir)]
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _refresh_statuses(self, registry: Dict, clients: Dict) -> None:
        active_by_client = {}
        for client, config in clients["clients"].items():
            for skill_id in config.get("published_skill_ids", []):
                active_by_client.setdefault(skill_id, []).append(client)
        families = {}
        for skill in registry["skills"].values():
            families.setdefault(skill["conflict_family"], []).append(skill)
        for family, members in families.items():
            chosen_ids = {skill_id for skill_id in active_by_client if skill_id in {member["skill_id"] for member in members}}
            for skill in members:
                if skill["enabled_global"] == "disabled":
                    skill["status"] = "disabled"
                elif skill["skill_id"] in chosen_ids:
                    skill["status"] = "active"
                elif len(members) > 1:
                    skill["status"] = "shadowed"
                else:
                    skill["status"] = "active"
        self.save_registry(registry)

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
