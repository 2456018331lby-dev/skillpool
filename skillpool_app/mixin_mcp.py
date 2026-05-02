from __future__ import annotations

# Auto-extracted from core.py - do not edit directly.

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import ast
import difflib
import json
import re
import secrets

from skillpool_app.core import (
    utc_now,
    write_json,
    yaml_scalar,
)

class MixinMcp:
    """Mixin: _parse_toml_value, _normalize_mcp_servers, _parse_codex_mcp_config, _parse_claude_mcp_config, _parse_hermes_mcp_config..."""

    def _parse_toml_value(self, raw_value: str):
        value = raw_value.strip()
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        # Try tomllib first (Python 3.11+)
        try:
            import tomllib
            return tomllib.loads("v = {}".format(value)).get("v", value)
        except Exception:
            pass
        # Safer fallback: only allow literal_eval for basic types
        try:
            result = ast.literal_eval(value)
            if isinstance(result, (str, int, float, bool, list)):
                return result
        except (ValueError, SyntaxError):
            pass
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
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
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



