from __future__ import annotations

# Auto-extracted from core.py - do not edit directly.

from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import json
import os
import shutil

from skillpool_app.core import (
    hash_directory,
    utc_now,
    write_json,
)

class MixinSync:
    """Mixin: _sync_skill_template, sync_inspect, _target_skill_sync_preview, _mcp_sync_preview, sync_preview..."""

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



