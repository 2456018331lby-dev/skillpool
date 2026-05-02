from __future__ import annotations

# Auto-extracted from core.py - do not edit directly.

from datetime import datetime
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional

from skillpool_app.core import (
    REGISTRY_VERSION,
    hash_directory,
    is_wsl_unc,
    json_preview,
    load_json,
    parse_frontmatter,
    read_text,
    slugify,
    utc_now,
    write_json,
)


class MixinInventory:
    """Mixin: _family_members, _family_display_skill, _visible_members_for_client, _client_family_inventory_maps, skills_matrix..."""

    def _family_members(self, registry: Dict) -> Dict[str, List[Dict[str, object]]]:
        families: Dict[str, List[Dict[str, object]]] = {}
        for skill in registry["skills"].values():
            families.setdefault(skill["conflict_family"], []).append(skill)
        return families

    def _family_display_skill(
        self, members: List[Dict[str, object]]
    ) -> Dict[str, object]:
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

    def _visible_members_for_client(
        self, client: str, members: List[Dict[str, object]]
    ) -> List[Dict[str, object]]:
        visible = []
        for member in members:
            available_clients = member.get("available_clients", [])
            if available_clients and client not in available_clients:
                continue
            visible.append(member)
        return visible

    def _client_family_inventory_maps(
        self, registry: Dict, clients: Dict
    ) -> Dict[str, Dict[str, object]]:
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
                "live_only": {
                    item.get("normalized_name")
                    for item in inventory.get("live_only", [])
                },
                "pool_only": {
                    item.get("normalized_name")
                    for item in inventory.get("pool_only", [])
                },
                "source_mismatch": {
                    item.get("normalized_name")
                    for item in inventory.get("source_mismatch", [])
                },
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
            source_scopes = sorted(
                {str(member.get("source_scope") or "-") for member in members}
            )
            source_clients = sorted(
                {
                    str(member.get("source_client"))
                    for member in members
                    if member.get("source_client")
                }
            )
            published_for = sorted(
                {
                    client_name
                    for member in members
                    for client_name in client_map.get(member["skill_id"], [])
                }
            )
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
                    row["clients"][client_name] = {
                        "status": "not_applicable",
                        "flags": [],
                        "skill_id": None,
                    }
                    continue
                applicable_clients += 1
                published_skill_id = inventory_maps[client_name]["published"].get(
                    family
                )
                live_only = family in inventory_maps[client_name]["live_only"]
                pool_only = family in inventory_maps[client_name]["pool_only"]
                source_mismatch_flag = (
                    family in inventory_maps[client_name]["source_mismatch"]
                )
                enabled_candidates = [
                    member
                    for member in visible_members
                    if member.get("enabled_global") != "disabled"
                    and member.get("client_overrides", {}).get(client_name, "inherit")
                    != "disabled"
                ]
                flags = []
                if any(
                    member.get("status") == "shadowed" for member in visible_members
                ):
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
                    "visible_skill_ids": [
                        member["skill_id"] for member in visible_members
                    ],
                }
                if status in {
                    "source_mismatch",
                    "live_only",
                    "pool_only",
                    "disabled",
                    "shadowed",
                }:
                    row["anomalies"].append({"client": client_name, "type": status})
            if applicable_clients > 1:
                row["anomalies"].append(
                    {"client": None, "type": "duplicate_across_clients"}
                )
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
                        "client_overrides": dict(
                            sorted(member.get("client_overrides", {}).items())
                        ),
                    }
                    for member in sorted(
                        members,
                        key=lambda item: (
                            str(item.get("name") or "").lower(),
                            item["skill_id"],
                        ),
                    )
                ]
            if source_scope and source_scope not in row["source_scopes"]:
                continue
            if (
                client
                and row["clients"].get(client, {}).get("status") == "not_applicable"
            ):
                continue
            if anomaly:
                anomaly_types = {item["type"] for item in row["anomalies"]}
                if (
                    anomaly not in anomaly_types
                    and row["clients"].get(client or "", {}).get("status") != anomaly
                ):
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
        return {
            "generated_at": utc_now(),
            "clients": sorted(clients["clients"].keys()),
            "total": len(rows),
            "rows": rows,
        }

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
            registry_by_fingerprint.setdefault(skill.get("fingerprint"), []).append(
                skill
            )

        source_summaries = []
        untracked = []
        mismatches = []
        transient_only = []
        for source in sorted(
            scan_sources.get("sources", {}).values(),
            key=lambda item: (str(item.get("path_kind")), str(item.get("path"))),
        ):
            discovered = (
                self._scan_source_skill_entries(source)
                if self._source_exists(str(source.get("path")))
                else []
            )
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
                        {
                            "skill_id": match["skill_id"],
                            "path": match.get("files_path"),
                            "source_scope": match.get("source_scope"),
                        }
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
                "clients": [
                    client_name
                    for client_name, payload in row["clients"].items()
                    if payload.get("status") != "not_applicable"
                ],
            }
            for row in matrix["rows"]
            if any(
                item["type"] == "duplicate_across_clients" for item in row["anomalies"]
            )
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
                "duplicate_across_clients": len(
                    payload.get("duplicate_across_clients", [])
                ),
            },
            "first_examples": {
                "untracked_discovered": _first(payload.get("untracked_discovered", [])),
                "source_mismatch": _first(payload.get("source_mismatch", [])),
                "transient_only": _first(payload.get("transient_only", [])),
                "duplicate_across_clients": _first(
                    payload.get("duplicate_across_clients", [])
                ),
            },
        }

    def discovery_details(
        self, group: str, *, limit: Optional[int] = None, refresh: bool = False
    ) -> Dict[str, object]:
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
                payload["skills"] = self._inventory_skills_for_client(
                    client_name, registry, clients
                )
            if include_mcp:
                payload["mcp"] = self._inventory_mcp_for_client(
                    client_name, client_config
                )
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

    def _skill_source_records(
        self, skill: Dict[str, object]
    ) -> List[Dict[str, object]]:
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

    def _skill_payload(
        self, skill: Dict[str, object], client_map: Dict[str, List[str]]
    ) -> Dict[str, object]:
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
        if sort_by not in {
            "name",
            "status",
            "imported_at",
            "last_seen_at",
            "source_scope",
        }:
            raise ValueError("Unsupported sort_by: {}".format(sort_by))
        if sort_dir not in {"asc", "desc"}:
            raise ValueError("Unsupported sort_dir: {}".format(sort_dir))
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 50), 1), 200)
        items = []
        for skill in registry["skills"].values():
            available_clients = sorted(skill.get("available_clients", []))
            visible_for_client = not available_clients or (
                client in available_clients if client else True
            )
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
        items.sort(
            key=lambda item: self._skill_sort_key(item, sort_by),
            reverse=sort_dir == "desc",
        )
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

    def get_skill(
        self,
        skill_id: str,
        *,
        registry: Optional[Dict] = None,
        clients: Optional[Dict] = None,
    ) -> Dict[str, object]:
        registry = registry or self.load_registry()
        clients = clients or self.load_clients()
        skill = registry["skills"].get(skill_id)
        if not skill:
            raise FileNotFoundError("Unknown skill_id: {}".format(skill_id))
        client_map = self._client_map(clients)
        detail = self._skill_payload(skill, client_map)
        related_members = []
        for member in registry["skills"].values():
            if (
                member["conflict_family"] != skill["conflict_family"]
                or member["skill_id"] == skill_id
            ):
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
                winner = next(
                    (
                        skill_id
                        for skill_id in config.get("published_skill_ids", [])
                        if skill_id in member_ids
                    ),
                    None,
                )
                if winner:
                    client_winners[client] = winner
                    winner_skill_ids.append(winner)
                overrides = []
                for member in members:
                    override = member.get("client_overrides", {}).get(client)
                    if override and override != "inherit":
                        overrides.append(
                            {"skill_id": member["skill_id"], "override": override}
                        )
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
                        "client_overrides": dict(
                            sorted(member.get("client_overrides", {}).items())
                        ),
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

        def add_candidate(
            skill_id: str,
            reason_type: str,
            message: str,
            *,
            client: Optional[str] = None,
            extra: Optional[Dict[str, object]] = None,
        ) -> None:
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
                    add_candidate(
                        item["skill_id"], "pool_only", item["reason"], client=client
                    )
            for item in inventory["skills"].get("source_mismatch", []):
                for match in item.get("pool_matches", []):
                    if match.get("skill_id"):
                        add_candidate(
                            match["skill_id"],
                            "source_mismatch",
                            item["reason"],
                            client=client,
                            extra={"live_path": item.get("path")},
                        )

        normalized_groups: Dict[str, List[Dict[str, object]]] = {}
        for skill in registry["skills"].values():
            if skill["status"] == "shadowed":
                add_candidate(
                    skill["skill_id"], "shadowed", "该 skill 当前处于 shadowed 状态。"
                )
            normalized_groups.setdefault(
                skill.get("normalized_name") or skill["conflict_family"], []
            ).append(skill)

        conflicts = self.list_conflicts(registry=registry, clients=clients)["conflicts"]
        for conflict in conflicts:
            for member in conflict["members"]:
                if not member.get("published_for"):
                    add_candidate(
                        member["skill_id"],
                        "unpublished_conflict_member",
                        "该冲突族成员当前未发布到任何客户端。",
                    )

        for members in normalized_groups.values():
            if len(members) < 2:
                continue
            fingerprints = {member["fingerprint"] for member in members}
            if len(fingerprints) <= 1:
                for member in members:
                    add_candidate(
                        member["skill_id"],
                        "duplicate_name_family",
                        "同名或近似同名 skill 出现多份内容相同的来源记录。",
                    )

        order = sorted(
            candidates,
            key=lambda skill_id: (candidates[skill_id]["name"].lower(), skill_id),
        )
        cleanup_state = {
            "version": REGISTRY_VERSION,
            "generated_at": utc_now(),
            "candidates": candidates,
            "order": order,
        }
        self.save_cleanup_candidates(cleanup_state)
        self.generate_reports(registry=registry, clients=clients)
        return {
            "generated_at": cleanup_state["generated_at"],
            "total": len(order),
            "candidates": [candidates[skill_id] for skill_id in order],
        }

    def cleanup_list(self) -> Dict[str, object]:
        cleanup_state = self.load_cleanup_candidates()
        return {
            "generated_at": cleanup_state.get("generated_at"),
            "total": len(cleanup_state.get("order", [])),
            "candidates": [
                cleanup_state["candidates"][skill_id]
                for skill_id in cleanup_state.get("order", [])
                if skill_id in cleanup_state.get("candidates", {})
            ],
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
        markdown = self._build_cleanup_candidates_report(
            cleanup_state, registry, clients
        )
        self.cleanup_report_path.write_text(markdown, encoding="utf-8")
        write_json(self.cleanup_export_path, cleanup_state)
        return {
            "markdown_path": str(self.cleanup_report_path),
            "json_path": str(self.cleanup_export_path),
        }

    def inventory_export(
        self, *, client: Optional[str] = None, format: str = "json"
    ) -> Dict[str, object]:
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
        markdown = self._build_inventory_markdown(
            {
                "generated_at": utc_now(),
                "clients": [inventory] if client else inventory["clients"],
            }
        )
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
                    datetime.utcfromtimestamp(path.stat().st_mtime)
                    .replace(microsecond=0)
                    .isoformat()
                    + "Z"
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
                    enabled={"enabled": "已启用", "disabled": "已禁用"}.get(
                        skill["enabled_global"], skill["enabled_global"]
                    ),
                    status={
                        "active": "生效中",
                        "shadowed": "被遮蔽",
                        "disabled": "已禁用",
                    }.get(skill["status"], skill["status"]),
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
            override_summary = (
                ", ".join(
                    "{}={}".format(
                        client,
                        "; ".join(
                            "{}:{}".format(item["skill_id"], item["override"])
                            for item in items
                        ),
                    )
                    for client, items in sorted(conflict["override_summary"].items())
                )
                or "-"
            )
            lines.append("- 当前胜出项: `{}`".format(winners))
            lines.append(
                "- 各客户端胜出项: {}".format(
                    ", ".join(
                        "{}={}".format(client, skill_id)
                        for client, skill_id in sorted(
                            conflict["client_winners"].items()
                        )
                    )
                    or "-"
                )
            )
            lines.append("- Override 摘要: {}".format(override_summary))
            lines.append("")
            lines.append(
                "| skill_id | 名称 | 来源 | 来源范围 | 全局启用 | 当前状态 | 已发布到 | 客户端覆盖 |"
            )
            lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
            for skill in conflict["members"]:
                overrides = (
                    ", ".join(
                        "{}={}".format(client, value)
                        for client, value in sorted(skill["client_overrides"].items())
                    )
                    or "-"
                )
                lines.append(
                    "| {skill_id} | {name} | {source} | {source_scope} | {enabled} | {status} | {published_for} | {overrides} |".format(
                        skill_id=skill["skill_id"],
                        name=skill["name"].replace("|", "/"),
                        source=skill["source_type"],
                        source_scope={
                            "target_dir": "目标目录",
                            "extra_dir": "额外目录",
                            "imported": "导入项",
                        }.get(skill["source_scope"], skill["source_scope"]),
                        enabled={"enabled": "已启用", "disabled": "已禁用"}.get(
                            skill["enabled_global"], skill["enabled_global"]
                        ),
                        status={
                            "active": "生效中",
                            "shadowed": "被遮蔽",
                            "disabled": "已禁用",
                        }.get(skill["status"], skill["status"]),
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
                    "- pool_visible_count: {}".format(
                        skills.get("pool_visible_count", "-")
                    ),
                    "- published_count: {}".format(skills.get("published_count", "-")),
                    "- live_target_count: {}".format(
                        skills.get("live_target_count", "-")
                    ),
                    "- live_extra_dir_count: {}".format(
                        skills.get("live_extra_dir_count", "-")
                    ),
                    "- live_total_count: {}".format(
                        skills.get("live_total_count", "-")
                    ),
                    "- unmanaged_live_count: {}".format(
                        skills.get("unmanaged_live_count", "-")
                    ),
                    "- published_missing_from_live_count: {}".format(
                        skills.get("published_missing_from_live_count", "-")
                    ),
                    "- pool_not_published_count: {}".format(
                        skills.get("pool_not_published_count", "-")
                    ),
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
                    "- published_only: {}".format(
                        len(skills.get("published_only", []))
                    ),
                    "- source_mismatch: {}".format(
                        len(skills.get("source_mismatch", []))
                    ),
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
                        mcp["server_count"]
                        if mcp.get("server_count") is not None
                        else "当前无法可靠统计"
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
                            args=(" ".join(server.get("args") or []) or "-").replace(
                                "|", "/"
                            ),
                            source_file=(server.get("source_file") or "-").replace(
                                "|", "/"
                            ),
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

    def _build_cleanup_candidates_report(
        self, cleanup_state: Dict, registry: Dict, clients: Dict
    ) -> str:
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
            reasons = (
                "; ".join(
                    "{}:{}".format(reason.get("type"), reason.get("message"))
                    for reason in item.get("reasons", [])
                )
                or "-"
            )
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

    def _discover_skill_entries(
        self, source_dir: Path, scope: str
    ) -> List[Dict[str, object]]:
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

    def _inventory_pool_skills_for_client(
        self, client: str, registry: Dict, clients: Dict
    ) -> List[Dict[str, object]]:
        client_map = self._client_map(clients)
        items = []
        for skill in registry["skills"].values():
            available_clients = skill.get("available_clients", [])
            if available_clients and client not in available_clients:
                continue
            items.append(self._skill_payload(skill, client_map))
        items.sort(key=lambda item: (item["name"].lower(), item["skill_id"]))
        return items

    def _published_skill_ids_for_client(
        self, client: str, client_config: Dict[str, object]
    ) -> List[str]:
        manifest_path = Path(client_config["manifest_path"])
        if manifest_path.exists():
            manifest = load_json(manifest_path, {})
            published = manifest.get("published_skill_ids")
            if isinstance(published, list):
                return list(published)
        return list(client_config.get("published_skill_ids", []))

    def _inventory_diff_payload(
        self, item: Dict[str, object], reason: str, **extra: object
    ) -> Dict[str, object]:
        payload = {
            "name": item.get("name"),
            "normalized_name": item.get("normalized_name")
            or item.get("conflict_family"),
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

    def _inventory_skills_for_client(
        self, client: str, registry: Dict, clients: Dict
    ) -> Dict[str, object]:
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
            {"path": path, "roles": roles} for path, roles in sorted(role_map.items())
        ]

        live_target_entries = self._discover_skill_entries(target_dir, "target_dir")
        live_extra_entries: List[Dict[str, object]] = []
        live_custom_entries: List[Dict[str, object]] = []
        for source in source_roots:
            if source["scope"] == "extra_dir":
                live_extra_entries.extend(
                    self._discover_skill_entries(Path(source["path"]), "extra_dir")
                )
            elif source["scope"] == "client_live":
                live_custom_entries.extend(
                    self._discover_skill_entries(Path(source["path"]), "client_live")
                )
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

        live_fingerprints = {
            item["fingerprint"] for item in live_entries if item.get("fingerprint")
        }
        live_target_fingerprints = {
            item["fingerprint"]
            for item in live_target_entries
            if item.get("fingerprint")
        }

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
                live_only.append(
                    self._inventory_diff_payload(
                        item, "live 技能存在，但尚未纳入 SkillPool registry"
                    )
                )

        pool_only = []
        for item in pool_entries:
            if item["fingerprint"] in live_fingerprints:
                continue
            pool_only.append(
                self._inventory_diff_payload(
                    item, "池内技能当前未出现在客户端 live 目录"
                )
            )

        published_only = []
        for item in published_entries:
            if item["fingerprint"] in live_target_fingerprints:
                continue
            published_only.append(
                self._inventory_diff_payload(
                    item, "发布清单包含该技能，但 live target 目录中未找到"
                )
            )

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
            "pool_not_published_count": max(
                len(pool_entries) - len(published_entries), 0
            ),
            "live_only": live_only,
            "pool_only": pool_only,
            "published_only": published_only,
            "source_mismatch": source_mismatch,
            "published_skill_ids": published_ids,
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
