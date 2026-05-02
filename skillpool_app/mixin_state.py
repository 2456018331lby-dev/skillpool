from __future__ import annotations

# Auto-extracted from core.py - do not edit directly.

from typing import Dict

from skillpool_app.core import (
    REGISTRY_VERSION,
    SCAN_SOURCE_KINDS,
    load_json,
    utc_now,
    write_json,
)


class MixinState:
    """Mixin: load_registry, save_registry, load_clients, save_clients, load_mcp_state..."""

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
        clients = load_json(
            self.clients_path, {"version": REGISTRY_VERSION, "clients": {}}
        )
        if self._migrate_clients(clients):
            self.save_clients(clients)
        return clients

    def save_clients(self, clients: Dict) -> None:
        clients["generated_at"] = utc_now()
        write_json(self.clients_path, clients)

    def load_mcp_state(self) -> Dict:
        self.init_state()
        return load_json(
            self.mcp_state_path, {"version": REGISTRY_VERSION, "clients": {}}
        )

    def save_mcp_state(self, mcp_state: Dict) -> None:
        mcp_state["generated_at"] = utc_now()
        write_json(self.mcp_state_path, mcp_state)

    def load_cleanup_candidates(self) -> Dict:
        self.init_state()
        return load_json(
            self.cleanup_candidates_path,
            {
                "version": REGISTRY_VERSION,
                "generated_at": utc_now(),
                "candidates": {},
                "order": [],
            },
        )

    def save_cleanup_candidates(self, cleanup_state: Dict) -> None:
        cleanup_state["generated_at"] = utc_now()
        write_json(self.cleanup_candidates_path, cleanup_state)

    def load_scan_sources(self) -> Dict:
        self.init_state()
        scan_sources = load_json(
            self.scan_sources_path, {"version": REGISTRY_VERSION, "sources": {}}
        )
        clients = load_json(
            self.clients_path, {"version": REGISTRY_VERSION, "clients": {}}
        )
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

    def _record_preview_metadata(
        self, clients: Dict, client: str, generated_at: str, status: str
    ) -> None:
        client_state = self._require_client(client, clients)
        client_state["last_preview_at"] = generated_at
        client_state["last_preview_status"] = status
        clients["clients"][client] = client_state

    def _record_deep_doctor_metadata(
        self, clients: Dict, client: str, generated_at: str, status: str
    ) -> None:
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
                    skill["client_overrides"][client] = "prefer:{}".format(
                        skill["skill_id"]
                    )
                    changed = True
        return changed

    def _migrate_clients(self, clients: Dict) -> bool:
        changed = False
        for client, config in clients.get("clients", {}).items():
            defaults = self._client_state(
                client, self._default_clients.get(client, config)
            )
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
            if current.get("default_entry") and current.get(
                "notes"
            ) != default_source.get("notes"):
                current["notes"] = default_source.get("notes")
                changed = True
            elif not current.get("notes") and default_source.get("notes"):
                current["notes"] = default_source["notes"]
                changed = True
        return changed
