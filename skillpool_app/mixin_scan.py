from __future__ import annotations

# Auto-extracted from core.py - do not edit directly.

from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
import json
import os
import shlex
import shutil
import subprocess

from skillpool_app.core import (
    EXCLUDED_SCAN_DIRS,
    SCAN_SOURCE_KINDS,
    SCAN_SOURCE_ROLES,
    hash_directory,
    is_wsl_unc,
    linux_to_unc_wsl,
    parse_frontmatter,
    read_text,
    scan_source_id,
    slugify,
    unc_wsl_to_linux,
    utc_now,
)

class MixinScan:
    """Mixin: discover_skills, _expand_config_path, _read_openclaw_extra_dirs, _source_exists, _scan_sources_for_client..."""

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
        lock_data = json.dumps({
            "operation": operation,
            "pid": os.getpid(),
            "created_at": utc_now(),
        })
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, lock_data.encode("utf-8"))
            finally:
                os.close(fd)
        except FileExistsError:
            raise RuntimeError("SkillPool is locked by another operation: {}".format(self.lock_path))

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



