from __future__ import annotations

# Auto-extracted from core.py - do not edit directly.

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict
from typing import Optional
import copy
import json
import os
import secrets
import shutil

from skillpool_app.core import (
    copy_existing_tree,
    ensure_clean_directory,
    load_json,
    read_text,
    remove_path_lexists,
    safe_rmtree,
    utc_now,
    write_json,
)

class MixinPublish:
    """Mixin: preview, preview_all, diff, publish, publish_all..."""

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
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
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


