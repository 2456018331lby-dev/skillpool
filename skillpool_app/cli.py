from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from skillpool_app.core import SkillPool


def _print(result: Any) -> None:
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillpool", description="Unified skill pool manager")
    parser.add_argument("--root", default=None, help="Override skillpool root directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")
    subparsers.add_parser("scan-local")

    import_parser = subparsers.add_parser("import")
    import_subparsers = import_parser.add_subparsers(dest="import_command", required=True)

    github_parser = import_subparsers.add_parser("github")
    github_parser.add_argument("repo_or_url")
    github_parser.add_argument("--ref", default=None)
    github_parser.add_argument("--subdir", default=None)

    zip_parser = import_subparsers.add_parser("zip")
    zip_parser.add_argument("zip_path")

    batch_parser = import_subparsers.add_parser("batch")
    batch_parser.add_argument("manifest_path")

    detect_parser = import_subparsers.add_parser("detect")
    detect_parser.add_argument("source_type", choices=["github"])
    detect_parser.add_argument("repo_or_url")
    detect_parser.add_argument("--ref", default=None)
    detect_parser.add_argument("--subdir", default=None)

    enable_parser = subparsers.add_parser("enable")
    enable_parser.add_argument("skill_id")

    disable_parser = subparsers.add_parser("disable")
    disable_parser.add_argument("skill_id")

    override_parser = subparsers.add_parser("override")
    override_subparsers = override_parser.add_subparsers(dest="override_command", required=True)
    override_set = override_subparsers.add_parser("set")
    override_set.add_argument("client")
    override_set.add_argument("conflict_family")
    override_set.add_argument("skill_id")
    override_list = override_subparsers.add_parser("list")
    override_list.add_argument("client")
    override_inherit = override_subparsers.add_parser("inherit")
    override_inherit.add_argument("client")
    override_inherit.add_argument("conflict_family")
    override_disable = override_subparsers.add_parser("disable")
    override_disable.add_argument("client")
    override_disable.add_argument("conflict_family")

    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("client", nargs="?")
    publish_parser.add_argument("--all", action="store_true", dest="publish_all")
    publish_parser.add_argument("--force", action="store_true")

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("rollback_args", nargs="+")
    rollback_parser.add_argument("--to", default=None, dest="backup_id")
    rollback_parser.add_argument("--latest", action="store_true")

    preview_parser = subparsers.add_parser("preview")
    preview_parser.add_argument("client", nargs="?")
    preview_parser.add_argument("--all", action="store_true", dest="preview_all")

    diff_parser = subparsers.add_parser("diff")
    diff_parser.add_argument("client")

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("client", nargs="?")
    inventory_parser.add_argument("--mcp", action="store_true", dest="inventory_mcp")
    inventory_parser.add_argument("--skills", action="store_true", dest="inventory_skills")
    inventory_parser.add_argument("--all", action="store_true", dest="inventory_all")

    scan_sources_parser = subparsers.add_parser("scan-sources")
    scan_sources_subparsers = scan_sources_parser.add_subparsers(dest="scan_sources_command", required=True)
    scan_sources_subparsers.add_parser("list")
    scan_sources_add = scan_sources_subparsers.add_parser("add")
    scan_sources_add.add_argument("path")
    scan_sources_add.add_argument("--role", required=True, choices=["global_source", "client_live", "both"])
    scan_sources_add.add_argument("--client", default=None)
    scan_sources_add.add_argument("--kind", default="stable", choices=["stable", "workspace", "transient"], dest="path_kind")
    scan_sources_add.add_argument("--disabled", action="store_true")
    scan_sources_enable = scan_sources_subparsers.add_parser("enable")
    scan_sources_enable.add_argument("id")
    scan_sources_disable = scan_sources_subparsers.add_parser("disable")
    scan_sources_disable.add_argument("id")
    scan_sources_scan = scan_sources_subparsers.add_parser("scan")
    scan_sources_scan.add_argument("--id", default=None)

    discovery_parser = subparsers.add_parser("discovery")
    discovery_subparsers = discovery_parser.add_subparsers(dest="discovery_command", required=False)
    discovery_subparsers.add_parser("summary")
    discovery_refresh = discovery_subparsers.add_parser("refresh")
    discovery_refresh.add_argument("--summary", action="store_true")
    discovery_details = discovery_subparsers.add_parser("details")
    discovery_details.add_argument("group")
    discovery_details.add_argument("--limit", default=None, type=int)

    sync_parser = subparsers.add_parser("sync")
    sync_subparsers = sync_parser.add_subparsers(dest="sync_command", required=True)
    sync_inspect = sync_subparsers.add_parser("inspect")
    sync_inspect.add_argument("source_client")
    sync_inspect.add_argument("--family", action="append", dest="families")
    sync_preview = sync_subparsers.add_parser("preview")
    sync_preview.add_argument("source_client")
    sync_preview.add_argument("--to", action="append", dest="targets", required=True)
    sync_preview.add_argument("--skills", action="store_true")
    sync_preview.add_argument("--mcp", action="store_true")
    sync_preview.add_argument("--family", action="append", dest="families")
    sync_apply = sync_subparsers.add_parser("apply")
    sync_apply.add_argument("source_client")
    sync_apply.add_argument("--to", action="append", dest="targets", required=True)
    sync_apply.add_argument("--skills", action="store_true")
    sync_apply.add_argument("--mcp", action="store_true")
    sync_apply.add_argument("--family", action="append", dest="families")

    batch_parser = subparsers.add_parser("batch")
    batch_subparsers = batch_parser.add_subparsers(dest="batch_command", required=True)
    batch_disable = batch_subparsers.add_parser("disable")
    batch_disable.add_argument("--clients", action="append", dest="clients", required=True)
    batch_disable.add_argument("--family", action="append", dest="families", required=True)
    batch_inherit = batch_subparsers.add_parser("inherit")
    batch_inherit.add_argument("--clients", action="append", dest="clients", required=True)
    batch_inherit.add_argument("--family", action="append", dest="families", required=True)

    mcp_parser = subparsers.add_parser("mcp")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)
    mcp_list = mcp_subparsers.add_parser("list")
    mcp_list.add_argument("client")
    mcp_diff = mcp_subparsers.add_parser("diff")
    mcp_diff.add_argument("client")
    mcp_enable = mcp_subparsers.add_parser("enable")
    mcp_enable.add_argument("client")
    mcp_enable.add_argument("server_name")
    mcp_disable = mcp_subparsers.add_parser("disable")
    mcp_disable.add_argument("client")
    mcp_disable.add_argument("server_name")
    mcp_add = mcp_subparsers.add_parser("add")
    mcp_add.add_argument("client")
    mcp_add.add_argument("server_name")
    mcp_add.add_argument("--command", required=True, dest="mcp_command_value")
    mcp_add.add_argument("--arg", action="append", dest="args")
    mcp_add.add_argument("--enabled", default="true")
    mcp_update = mcp_subparsers.add_parser("update")
    mcp_update.add_argument("client")
    mcp_update.add_argument("server_name")
    mcp_update.add_argument("--new-name", default=None)
    mcp_update.add_argument("--command", default=None, dest="mcp_command_value")
    mcp_update.add_argument("--arg", action="append", dest="args")
    mcp_update.add_argument("--enabled", default=None)
    mcp_remove = mcp_subparsers.add_parser("remove")
    mcp_remove.add_argument("client")
    mcp_remove.add_argument("server_name")
    mcp_dedupe = mcp_subparsers.add_parser("dedupe")
    mcp_dedupe.add_argument("client")

    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_subparsers = cleanup_parser.add_subparsers(dest="cleanup_command", required=True)
    cleanup_subparsers.add_parser("scan")
    cleanup_subparsers.add_parser("list")
    cleanup_mark = cleanup_subparsers.add_parser("mark")
    cleanup_mark.add_argument("skill_id")
    cleanup_mark.add_argument("label")
    cleanup_subparsers.add_parser("export")

    subparsers.add_parser("status")
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("client", nargs="?")
    doctor_parser.add_argument("--deep", action="store_true")
    subparsers.add_parser("report")
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8765, type=int)
    serve_parser.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    pool = SkillPool(root=Path(args.root) if args.root else None)

    def _sync_modes(namespace) -> tuple[bool, bool]:
        include_skills = bool(getattr(namespace, "skills", False))
        include_mcp = bool(getattr(namespace, "mcp", False))
        if not include_skills and not include_mcp:
            return True, True
        return include_skills, include_mcp

    if args.command == "init":
        result = pool.init_state()
        result.update(pool.generate_reports())
        _print(result)
        return 0
    if args.command == "scan-local":
        _print(pool.scan_local())
        return 0
    if args.command == "import":
        if args.import_command == "github":
            _print(pool.import_github(args.repo_or_url, ref=args.ref, subdir=args.subdir))
            return 0
        if args.import_command == "zip":
            _print(pool.import_zip(Path(args.zip_path)))
            return 0
        if args.import_command == "batch":
            _print(pool.import_batch(Path(args.manifest_path)))
            return 0
        if args.import_command == "detect":
            if args.source_type == "github":
                _print(pool.import_detect_github(args.repo_or_url, ref=args.ref, subdir=args.subdir))
                return 0
    if args.command == "enable":
        _print(pool.set_enabled_global(args.skill_id, True))
        return 0
    if args.command == "disable":
        _print(pool.set_enabled_global(args.skill_id, False))
        return 0
    if args.command == "override":
        if args.override_command == "set":
            _print(pool.override_set(args.client, args.conflict_family, args.skill_id))
            return 0
        if args.override_command == "list":
            _print(pool.override_list(args.client))
            return 0
        if args.override_command == "inherit":
            _print(pool.override_inherit(args.client, args.conflict_family))
            return 0
        if args.override_command == "disable":
            _print(pool.override_disable(args.client, args.conflict_family))
            return 0
        return 0
    if args.command == "publish":
        if args.publish_all:
            _print(pool.publish_all(force=args.force))
            return 0
        if not args.client:
            parser.error("publish requires a client or --all")
        _print(pool.publish(args.client, force=args.force))
        return 0
    if args.command == "rollback":
        if args.rollback_args[0] == "list":
            if len(args.rollback_args) != 2:
                parser.error("rollback list requires a client")
            _print(pool.rollback_list(args.rollback_args[1]))
            return 0
        if args.rollback_args[0] == "inspect":
            if len(args.rollback_args) != 3:
                parser.error("rollback inspect requires a client and backup_id")
            _print(pool.rollback_inspect(args.rollback_args[1], args.rollback_args[2]))
            return 0
        client = args.rollback_args[0]
        backup_id = args.backup_id
        if args.latest:
            backup_id = pool.latest_backup_id(client)
        _print(pool.rollback(client, backup_id=backup_id))
        return 0
    if args.command == "preview":
        if args.preview_all:
            _print(pool.preview_all())
            return 0
        if not args.client:
            parser.error("preview requires a client or --all")
        _print(pool.preview(args.client))
        return 0
    if args.command == "diff":
        _print(pool.diff(args.client))
        return 0
    if args.command == "inventory":
        include_skills = True
        include_mcp = True
        if args.inventory_skills and not args.inventory_mcp:
            include_mcp = False
        elif args.inventory_mcp and not args.inventory_skills:
            include_skills = False
        _print(
            pool.inventory(
                client=args.client,
                include_skills=include_skills,
                include_mcp=include_mcp,
                summary_only=(args.client is None and not args.inventory_all),
            )
        )
        return 0
    if args.command == "scan-sources":
        if args.scan_sources_command == "list":
            _print(pool.scan_sources_list())
            return 0
        if args.scan_sources_command == "add":
            _print(
                pool.scan_source_add(
                    args.path,
                    role=args.role,
                    client=args.client,
                    path_kind=args.path_kind,
                    enabled=not args.disabled,
                )
            )
            return 0
        if args.scan_sources_command == "enable":
            _print(pool.scan_source_enable(args.id))
            return 0
        if args.scan_sources_command == "disable":
            _print(pool.scan_source_disable(args.id))
            return 0
        if args.scan_sources_command == "scan":
            _print(pool.scan_sources_scan(args.id))
            return 0
    if args.command == "discovery":
        if args.discovery_command == "summary":
            _print(pool.discovery_summary())
            return 0
        if args.discovery_command == "refresh":
            if args.summary:
                _print(pool.discovery_summary(refresh=True))
            else:
                _print(pool.discovery(refresh=True))
            return 0
        if args.discovery_command == "details":
            _print(pool.discovery_details(args.group, limit=args.limit))
            return 0
        _print(pool.discovery())
        return 0
    if args.command == "sync":
        include_skills, include_mcp = _sync_modes(args)
        if args.sync_command == "inspect":
            _print(pool.sync_inspect(args.source_client, families=args.families))
            return 0
        if args.sync_command == "preview":
            _print(
                pool.sync_preview(
                    args.source_client,
                    args.targets,
                    include_skills=include_skills,
                    include_mcp=include_mcp,
                    families=args.families,
                )
            )
            return 0
        if args.sync_command == "apply":
            _print(
                pool.sync_apply(
                    args.source_client,
                    args.targets,
                    include_skills=include_skills,
                    include_mcp=include_mcp,
                    families=args.families,
                )
            )
            return 0
    if args.command == "batch":
        if args.batch_command == "disable":
            _print(pool.batch_disable(args.clients, args.families))
            return 0
        if args.batch_command == "inherit":
            _print(pool.batch_inherit(args.clients, args.families))
            return 0
        return 0
    if args.command == "mcp":
        if args.mcp_command == "list":
            _print(pool.mcp_list(args.client))
            return 0
        if args.mcp_command == "diff":
            _print(pool.mcp_diff(args.client))
            return 0
        if args.mcp_command == "enable":
            _print(pool.mcp_enable(args.client, args.server_name))
            return 0
        if args.mcp_command == "disable":
            _print(pool.mcp_disable(args.client, args.server_name))
            return 0
        if args.mcp_command == "add":
            _print(pool.mcp_add(args.client, args.server_name, args.mcp_command_value, args=args.args or [], enabled=str(args.enabled).lower() == "true"))
            return 0
        if args.mcp_command == "update":
            enabled = None if args.enabled is None else str(args.enabled).lower() == "true"
            _print(
                pool.mcp_update(
                    args.client,
                    args.server_name,
                    new_name=args.new_name,
                    command=args.mcp_command_value,
                    args=args.args,
                    enabled=enabled,
                )
            )
            return 0
        if args.mcp_command == "remove":
            _print(pool.mcp_remove(args.client, args.server_name))
            return 0
        if args.mcp_command == "dedupe":
            if args.client != "codex":
                parser.error("mcp dedupe currently only supports codex")
            _print(pool.mcp_dedupe_codex())
            return 0
    if args.command == "cleanup":
        if args.cleanup_command == "scan":
            _print(pool.cleanup_scan())
            return 0
        if args.cleanup_command == "list":
            _print(pool.cleanup_list())
            return 0
        if args.cleanup_command == "mark":
            _print(pool.cleanup_mark(args.skill_id, args.label))
            return 0
        if args.cleanup_command == "export":
            _print(pool.cleanup_export())
            return 0
    if args.command == "status":
        _print(pool.status())
        return 0
    if args.command == "doctor":
        _print(pool.doctor(deep=args.deep, client=args.client))
        return 0
    if args.command == "report":
        _print(pool.generate_reports())
        return 0
    if args.command == "serve":
        from skillpool_app.web import serve

        return serve(pool, host=args.host, port=args.port, open_browser=args.open_browser)
    parser.error("Unknown command")
    return 2
