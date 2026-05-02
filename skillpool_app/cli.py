from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from skillpool_app.core import SkillPool


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._/\-]*$')
_REPO_OR_URL_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._/\-:@~+%]*$')
_PATH_FORBIDDEN = set(';|&$`()<>\'"\n\r*?!#[]~{}')


def _validate_id(value: str | None, name: str = "identifier") -> str | None:
    """Validate a user-provided identifier; reject shell metacharacters."""
    if value is None:
        return None
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(
            f"Invalid {name}: {value!r} (must start with alphanumeric, "
            f"then alphanumeric/dot/dash/underscore/slash only)"
        )
    return value


def _validate_repo_or_url(value: str) -> str:
    """Validate a repo identifier or URL."""
    if not _REPO_OR_URL_RE.match(value):
        raise ValueError(
            f"Invalid repo/URL: {value!r} (contains disallowed characters)"
        )
    return value


def _validate_path(value: str | None, name: str = "path") -> str | None:
    """Validate a user-provided path; reject metacharacters and '..' traversal."""
    if value is None:
        return None
    normalized = value.replace('\\', '/')
    if any(part == '..' for part in normalized.split('/')):
        raise ValueError(f"Invalid {name}: path traversal (..) not allowed")
    bad = _PATH_FORBIDDEN & set(value)
    if bad:
        raise ValueError(
            f"Invalid {name}: contains forbidden characters: {''.join(sorted(bad))}"
        )
    return value


def _validate_string(value: str | None, name: str = "string") -> str | None:
    """Validate a user-provided string against shell metacharacters."""
    if value is None:
        return None
    bad = _PATH_FORBIDDEN & set(value)
    if bad:
        raise ValueError(
            f"Invalid {name}: contains forbidden characters: {''.join(sorted(bad))}"
        )
    return value


def _validate_ids(values: list[str] | None, name: str = "identifiers") -> list[str] | None:
    """Validate each element in a list of identifiers."""
    if values is None:
        return None
    return [_validate_id(v, name) for v in values]


# ---------------------------------------------------------------------------
# Display helper
# ---------------------------------------------------------------------------


def _print(result: Any) -> None:
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# main() -- dict-dispatch with per-command handler functions
# ---------------------------------------------------------------------------


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

    # -- individual command handlers ----------------------------------------

    def _cmd_init() -> int:
        result = pool.init_state()
        result.update(pool.generate_reports())
        _print(result)
        return 0

    def _cmd_scan_local() -> int:
        _print(pool.scan_local())
        return 0

    def _cmd_import() -> int:
        sub = {
            "github": lambda: _print(pool.import_github(
                _validate_repo_or_url(args.repo_or_url),
                ref=args.ref, subdir=args.subdir)),
            "zip": lambda: _print(pool.import_zip(
                Path(_validate_path(args.zip_path, "zip_path")))),
            "batch": lambda: _print(pool.import_batch(
                Path(_validate_path(args.manifest_path, "manifest_path")))),
            "detect": _cmd_import_detect,
        }
        return sub[args.import_command]()

    def _cmd_import_detect() -> int:
        if args.source_type == "github":
            _print(pool.import_detect_github(
                _validate_repo_or_url(args.repo_or_url),
                ref=args.ref, subdir=args.subdir))
        return 0

    def _cmd_enable() -> int:
        _print(pool.set_enabled_global(_validate_id(args.skill_id, "skill_id"), True))
        return 0

    def _cmd_disable() -> int:
        _print(pool.set_enabled_global(_validate_id(args.skill_id, "skill_id"), False))
        return 0

    def _cmd_override() -> int:
        client = _validate_id(args.client, "client")
        if args.override_command == "set":
            _print(pool.override_set(
                client,
                _validate_id(args.conflict_family, "conflict_family"),
                _validate_id(args.skill_id, "skill_id")))
        elif args.override_command == "list":
            _print(pool.override_list(client))
        elif args.override_command == "inherit":
            _print(pool.override_inherit(
                client,
                _validate_id(args.conflict_family, "conflict_family")))
        elif args.override_command == "disable":
            _print(pool.override_disable(
                client,
                _validate_id(args.conflict_family, "conflict_family")))
        return 0

    def _cmd_publish() -> int:
        if args.publish_all:
            _print(pool.publish_all(force=args.force))
            return 0
        if not args.client:
            parser.error("publish requires a client or --all")
        _print(pool.publish(_validate_id(args.client, "client"), force=args.force))
        return 0

    def _cmd_rollback() -> int:
        subcmd = args.rollback_args[0]
        if subcmd == "list":
            if len(args.rollback_args) != 2:
                parser.error("rollback list requires a client")
            _print(pool.rollback_list(
                _validate_id(args.rollback_args[1], "client")))
            return 0
        if subcmd == "inspect":
            if len(args.rollback_args) != 3:
                parser.error("rollback inspect requires a client and backup_id")
            _print(pool.rollback_inspect(
                _validate_id(args.rollback_args[1], "client"),
                _validate_id(args.rollback_args[2], "backup_id")))
            return 0
        client = _validate_id(subcmd, "client")
        backup_id = _validate_id(args.backup_id, "backup_id") if args.backup_id else None
        if args.latest:
            backup_id = pool.latest_backup_id(client)
        _print(pool.rollback(client, backup_id=backup_id))
        return 0

    def _cmd_preview() -> int:
        if args.preview_all:
            _print(pool.preview_all())
            return 0
        if not args.client:
            parser.error("preview requires a client or --all")
        _print(pool.preview(_validate_id(args.client, "client")))
        return 0

    def _cmd_diff() -> int:
        _print(pool.diff(_validate_id(args.client, "client")))
        return 0

    def _cmd_inventory() -> int:
        include_skills = True
        include_mcp = True
        if args.inventory_skills and not args.inventory_mcp:
            include_mcp = False
        elif args.inventory_mcp and not args.inventory_skills:
            include_skills = False
        _print(
            pool.inventory(
                client=_validate_id(args.client, "client") if args.client else None,
                include_skills=include_skills,
                include_mcp=include_mcp,
                summary_only=(args.client is None and not args.inventory_all),
            )
        )
        return 0

    def _cmd_scan_sources() -> int:
        sub = {
            "list": lambda: _print(pool.scan_sources_list()),
            "add": lambda: _print(pool.scan_source_add(
                _validate_path(args.path, "path"),
                role=args.role,
                client=_validate_id(args.client, "client") if args.client else None,
                path_kind=args.path_kind,
                enabled=not args.disabled)),
            "enable": lambda: _print(pool.scan_source_enable(
                _validate_id(args.id, "id"))),
            "disable": lambda: _print(pool.scan_source_disable(
                _validate_id(args.id, "id"))),
            "scan": lambda: _print(pool.scan_sources_scan(args.id)),
        }
        sub[args.scan_sources_command]()
        return 0

    def _cmd_discovery() -> int:
        sub = {
            "summary": lambda: _print(pool.discovery_summary()),
            "refresh": lambda: (
                _print(pool.discovery_summary(refresh=True))
                if args.summary
                else _print(pool.discovery(refresh=True))
            ),
            "details": lambda: _print(pool.discovery_details(
                _validate_id(args.group, "group"), limit=args.limit)),
        }
        if args.discovery_command in sub:
            sub[args.discovery_command]()
        else:
            _print(pool.discovery())
        return 0

    def _cmd_sync() -> int:
        include_skills, include_mcp = _sync_modes(args)
        source = _validate_id(args.source_client, "source_client")
        targets = _validate_ids(args.targets, "target")
        families = _validate_ids(args.families, "family")
        sub = {
            "inspect": lambda: _print(pool.sync_inspect(
                source, families=families)),
            "preview": lambda: _print(pool.sync_preview(
                source, targets,
                include_skills=include_skills,
                include_mcp=include_mcp,
                families=families)),
            "apply": lambda: _print(pool.sync_apply(
                source, targets,
                include_skills=include_skills,
                include_mcp=include_mcp,
                families=families)),
        }
        sub[args.sync_command]()
        return 0

    def _cmd_batch() -> int:
        clients = _validate_ids(args.clients, "client")
        families = _validate_ids(args.families, "family")
        sub = {
            "disable": lambda: _print(pool.batch_disable(clients, families)),
            "inherit": lambda: _print(pool.batch_inherit(clients, families)),
        }
        sub[args.batch_command]()
        return 0

    def _cmd_mcp() -> int:
        client = _validate_id(args.client, "client")
        sub = {
            "list": lambda: _print(pool.mcp_list(client)),
            "diff": lambda: _print(pool.mcp_diff(client)),
            "enable": lambda: _print(pool.mcp_enable(
                client, _validate_id(args.server_name, "server_name"))),
            "disable": lambda: _print(pool.mcp_disable(
                client, _validate_id(args.server_name, "server_name"))),
            "add": lambda: _print(pool.mcp_add(
                client,
                _validate_id(args.server_name, "server_name"),
                _validate_string(args.mcp_command_value, "command"),
                args=args.args or [],
                enabled=str(args.enabled).lower() == "true")),
            "update": _cmd_mcp_update,
            "remove": lambda: _print(pool.mcp_remove(
                client, _validate_id(args.server_name, "server_name"))),
            "dedupe": _cmd_mcp_dedupe,
        }
        sub[args.mcp_command]()
        return 0

    def _cmd_mcp_update() -> int:
        client = _validate_id(args.client, "client")
        srv = _validate_id(args.server_name, "server_name")
        enabled = None if args.enabled is None else str(args.enabled).lower() == "true"
        _print(
            pool.mcp_update(
                client, srv,
                new_name=_validate_id(args.new_name, "new_name") if args.new_name else None,
                command=_validate_string(args.mcp_command_value, "command") if args.mcp_command_value else None,
                args=args.args,
                enabled=enabled,
            )
        )
        return 0

    def _cmd_mcp_dedupe() -> int:
        client = _validate_id(args.client, "client")
        if client != "codex":
            parser.error("mcp dedupe currently only supports codex")
        _print(pool.mcp_dedupe_codex())
        return 0

    def _cmd_cleanup() -> int:
        sub = {
            "scan": lambda: _print(pool.cleanup_scan()),
            "list": lambda: _print(pool.cleanup_list()),
            "mark": lambda: _print(pool.cleanup_mark(
                _validate_id(args.skill_id, "skill_id"),
                _validate_string(args.label, "label"))),
            "export": lambda: _print(pool.cleanup_export()),
        }
        sub[args.cleanup_command]()
        return 0

    def _cmd_status() -> int:
        _print(pool.status())
        return 0

    def _cmd_doctor() -> int:
        _print(pool.doctor(
            deep=args.deep,
            client=_validate_id(args.client, "client") if args.client else None))
        return 0

    def _cmd_report() -> int:
        _print(pool.generate_reports())
        return 0

    def _cmd_serve() -> int:
        from skillpool_app.web import serve
        return serve(pool, host=args.host, port=args.port,
                     open_browser=args.open_browser)

    # -- top-level dispatch dict --------------------------------------------
    dispatch: dict[str, callable] = {
        "init":         _cmd_init,
        "scan-local":   _cmd_scan_local,
        "import":       _cmd_import,
        "enable":       _cmd_enable,
        "disable":      _cmd_disable,
        "override":     _cmd_override,
        "publish":      _cmd_publish,
        "rollback":     _cmd_rollback,
        "preview":      _cmd_preview,
        "diff":         _cmd_diff,
        "inventory":    _cmd_inventory,
        "scan-sources": _cmd_scan_sources,
        "discovery":    _cmd_discovery,
        "sync":         _cmd_sync,
        "batch":        _cmd_batch,
        "mcp":          _cmd_mcp,
        "cleanup":      _cmd_cleanup,
        "status":       _cmd_status,
        "doctor":       _cmd_doctor,
        "report":       _cmd_report,
        "serve":        _cmd_serve,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.error(f"Unknown command: {args.command}")
        return 2
    return handler()
