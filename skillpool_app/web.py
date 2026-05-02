from __future__ import annotations

import json
import mimetypes
import re
import secrets
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from skillpool_app.core import SkillPool


UI_DIR = Path(__file__).parent / "ui"


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _first(query: Dict[str, list], key: str, default: Optional[str] = None) -> Optional[str]:
    values = query.get(key)
    if not values:
        return default
    return values[-1]


def _first_int(query: Dict[str, list], key: str, default: int) -> int:
    raw = _first(query, key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Query parameter '{}' must be an integer".format(key)) from exc


class SkillPoolWebServer(ThreadingHTTPServer):
    def __init__(self, address, pool: SkillPool):
        super().__init__(address, SkillPoolRequestHandler)
        self.pool = pool
        self.ui_dir = UI_DIR
        self.csrf_token = secrets.token_urlsafe(32)


class SkillPoolRequestHandler(BaseHTTPRequestHandler):
    server_version = "skillpool-web/0.1"

    def log_message(self, format, *args):
        print("[skillpool-web] " + format % args)

    @property
    def pool(self) -> SkillPool:
        return self.server.pool

    @property
    def csrf_token(self) -> str:
        return self.server.csrf_token

    @staticmethod
    def _safe_path_param(value: str) -> str:
        """Validate a URL path parameter to prevent path traversal."""
        if not value:
            raise ValueError("Empty path parameter")
        if ".." in value or "/" in value or "\\" in value or "\0" in value:
            raise ValueError("Invalid path parameter: {}".format(value))
        return value

    def do_GET(self):
        self._handle(self._route_get)

    def do_POST(self):
        self._handle(self._route_post)

    def _handle(self, handler):
        try:
            handler()
        except FileNotFoundError as exc:
            self._send_error("not_found", str(exc), 404)
        except ValueError as exc:
            self._send_error("bad_request", str(exc), 400)
        except RuntimeError as exc:
            self._send_error("runtime_error", str(exc), 409)
        except PermissionError as exc:
            self._send_error("forbidden", str(exc), 403)
        except Exception as exc:
            self._send_error("internal_error", str(exc), 500)

    def _route_get(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        segments = [unquote(part) for part in path.split("/") if part]

        if path == "/" or path == "/index.html":
            self._send_static(UI_DIR / "index.html")
            return
        if path.startswith("/assets/"):
            self._send_static(UI_DIR / unquote(path[len("/assets/") :]))
            return

        if path == "/api/status":
            self._send_ok(self.pool.status())
            return
        if path == "/api/health":
            self._send_ok({"status": "ok", "service": "skillpool-console"})
            return
        if path == "/api/csrf-token":
            self._send_ok({"csrf_token": self.csrf_token})
            return
        if path == "/api/system":
            self._send_ok(self.pool.system_status())
            return
        if path == "/api/tools/actions":
            self._send_ok(self.pool.tool_actions())
            return
        if path == "/api/skills":
            self._send_ok(
                self.pool.list_skills(
                    page=_first_int(query, "page", 1),
                    page_size=_first_int(query, "page_size", 50),
                    sort_by=_first(query, "sort_by", "name"),
                    sort_dir=_first(query, "sort_dir", "asc"),
                    client=_first(query, "client"),
                    family=_first(query, "family"),
                    status=_first(query, "status"),
                    enabled_global=_first(query, "enabled_global"),
                    source_scope=_first(query, "source_scope"),
                    query=_first(query, "q") or _first(query, "query"),
                )
            )
            return
        if path == "/api/skills/matrix":
            self._send_ok(
                self.pool.skills_matrix(
                    query=_first(query, "q") or _first(query, "query"),
                    client=_first(query, "client"),
                    anomaly=_first(query, "anomaly"),
                    source_scope=_first(query, "source_scope"),
                    include_instances=_truthy(_first(query, "include_instances", "1")),
                )
            )
            return
        if path == "/api/skills/instances":
            self._send_ok(
                self.pool.skills_instances(
                    page=_first_int(query, "page", 1),
                    page_size=_first_int(query, "page_size", 50),
                    sort_by=_first(query, "sort_by", "name"),
                    sort_dir=_first(query, "sort_dir", "asc"),
                    client=_first(query, "client"),
                    family=_first(query, "family"),
                    status=_first(query, "status"),
                    enabled_global=_first(query, "enabled_global"),
                    source_scope=_first(query, "source_scope"),
                    query=_first(query, "q") or _first(query, "query"),
                )
            )
            return
        if len(segments) == 3 and segments[:2] == ["api", "skills"]:
            self._send_ok(self.pool.get_skill(self._safe_path_param(segments[2])))
            return
        if path == "/api/conflicts":
            self._send_ok(self.pool.list_conflicts(family=_first(query, "family")))
            return
        if path == "/api/clients":
            self._send_ok(self.pool.load_clients())
            return
        if path == "/api/reports":
            self._send_ok(self.pool.get_reports())
            return
        if len(segments) == 4 and segments[:3] == ["api", "sync", "template"]:
            families = query.get("family") or None
            self._send_ok(self.pool.sync_inspect(self._safe_path_param(segments[3]), families=families))
            return
        if path == "/api/mcp/clients":
            self._send_ok(self.pool.mcp_clients())
            return
        if len(segments) == 4 and segments[:3] == ["api", "mcp", "clients"]:
            self._send_ok(self.pool.mcp_list(self._safe_path_param(segments[3])))
            return
        if len(segments) == 5 and segments[:3] == ["api", "mcp", "clients"] and segments[4] == "diff":
            self._send_ok(self.pool.mcp_diff(self._safe_path_param(segments[3])))
            return
        if path == "/api/inventory":
            self._send_ok(self.pool.inventory(summary_only=True))
            return
        if path == "/api/import/detect":
            source_type = _first(query, "source_type", "github")
            if source_type != "github":
                raise ValueError("Only github detect is currently supported")
            self._send_ok(
                self.pool.import_detect_github(
                    str(_first(query, "repo_or_url", "") or ""),
                    ref=_first(query, "ref"),
                    subdir=_first(query, "subdir"),
                )
            )
            return
        if path == "/api/inventory/export":
            self._send_ok(
                self.pool.inventory_export(
                    client=_first(query, "client"),
                    format=_first(query, "format", "json") or "json",
                )
            )
            return
        if len(segments) == 3 and segments[:2] == ["api", "inventory"]:
            self._send_ok(self.pool.inventory(client=self._safe_path_param(segments[2])))
            return
        if len(segments) == 4 and segments[:2] == ["api", "inventory"] and segments[3] == "skills":
            inventory = self.pool.inventory(client=self._safe_path_param(segments[2]), include_mcp=False)
            self._send_ok({"client": inventory["client"], "generated_at": inventory["generated_at"], "skills": inventory["skills"]})
            return
        if len(segments) == 4 and segments[:2] == ["api", "inventory"] and segments[3] == "mcp":
            inventory = self.pool.inventory(client=self._safe_path_param(segments[2]), include_skills=False)
            self._send_ok({"client": inventory["client"], "generated_at": inventory["generated_at"], "mcp": inventory["mcp"]})
            return

        if len(segments) == 4 and segments[:2] == ["api", "clients"] and segments[3] == "preview":
            self._send_ok(self.pool.preview(self._safe_path_param(segments[2]), detailed=_truthy(_first(query, "detailed"))))
            return
        if len(segments) == 4 and segments[:2] == ["api", "clients"] and segments[3] == "diff":
            self._send_ok(self.pool.diff(self._safe_path_param(segments[2])))
            return
        if len(segments) == 4 and segments[:2] == ["api", "clients"] and segments[3] == "doctor":
            self._send_ok(self.pool.doctor(deep=_truthy(_first(query, "deep")), client=self._safe_path_param(segments[2])))
            return
        if len(segments) == 4 and segments[:2] == ["api", "clients"] and segments[3] == "backups":
            self._send_ok(self.pool.rollback_list(self._safe_path_param(segments[2])))
            return
        if len(segments) == 5 and segments[:2] == ["api", "clients"] and segments[3] == "backups":
            self._send_ok(self.pool.rollback_inspect(self._safe_path_param(segments[2]), self._safe_path_param(segments[4])))
            return
        if path == "/api/cleanup":
            self._send_ok(self.pool.cleanup_list())
            return
        if path == "/api/cleanup/export":
            self._send_ok(self.pool.cleanup_export())
            return
        if path == "/api/scan-sources":
            self._send_ok(self.pool.scan_sources_list())
            return
        if path == "/api/discovery/summary":
            self._send_ok(self.pool.discovery_summary())
            return
        if path == "/api/discovery/details":
            group = _first(query, "group")
            if not group:
                raise ValueError("Query parameter 'group' is required")
            limit = query.get("limit")
            self._send_ok(self.pool.discovery_details(group, limit=(_first_int(query, "limit", 0) if limit else None)))
            return
        if path == "/api/discovery":
            self._send_ok(self.pool.discovery())
            return

        raise FileNotFoundError(path)

    def _route_post(self):
        self._validate_csrf()
        parsed = urlparse(self.path)
        path = parsed.path
        segments = [unquote(part) for part in path.split("/") if part]

        if path == "/api/override/set":
            payload = self._read_json_body()
            self._send_ok(
                self.pool.override_set(
                    str(payload.get("client", "")),
                    str(payload.get("conflict_family", "")),
                    str(payload.get("skill_id", "")),
                )
            )
            return
        if path == "/api/override/inherit":
            payload = self._read_json_body()
            self._send_ok(self.pool.override_inherit(str(payload.get("client", "")), str(payload.get("conflict_family", ""))))
            return
        if path == "/api/override/disable":
            payload = self._read_json_body()
            self._send_ok(self.pool.override_disable(str(payload.get("client", "")), str(payload.get("conflict_family", ""))))
            return
        if path == "/api/import/github":
            payload = self._read_json_body()
            self._send_ok(
                self.pool.import_github(
                    str(payload.get("repo_or_url", "")),
                    ref=payload.get("ref") or None,
                    subdir=payload.get("subdir") or None,
                )
            )
            return
        if path == "/api/import/batch":
            payload = self._read_json_body()
            self._send_ok(self.pool.import_batch(Path(str(payload.get("manifest_path", "")))))
            return
        if path == "/api/import/detect":
            payload = self._read_json_body()
            source_type = str(payload.get("source_type", "github"))
            if source_type != "github":
                raise ValueError("Only github detect is currently supported")
            self._send_ok(
                self.pool.import_detect_github(
                    str(payload.get("repo_or_url", "")),
                    ref=payload.get("ref") or None,
                    subdir=payload.get("subdir") or None,
                )
            )
            return
        if path == "/api/import/zip":
            self._send_ok(self._import_uploaded_zip())
            return
        if path == "/api/report/regenerate":
            self._send_ok(self.pool.get_reports())
            return
        if path == "/api/sync/preview":
            payload = self._read_json_body()
            self._send_ok(
                self.pool.sync_preview(
                    str(payload.get("source_client", "")),
                    [str(item) for item in payload.get("target_clients", [])],
                    include_skills=bool(payload.get("include_skills", True)),
                    include_mcp=bool(payload.get("include_mcp", True)),
                    families=[str(item) for item in payload.get("families", [])] or None,
                )
            )
            return
        if path == "/api/sync/apply":
            payload = self._read_json_body()
            self._send_ok(
                self.pool.sync_apply(
                    str(payload.get("source_client", "")),
                    [str(item) for item in payload.get("target_clients", [])],
                    include_skills=bool(payload.get("include_skills", True)),
                    include_mcp=bool(payload.get("include_mcp", True)),
                    families=[str(item) for item in payload.get("families", [])] or None,
                )
            )
            return
        if path == "/api/batch/disable":
            payload = self._read_json_body()
            self._send_ok(
                self.pool.batch_disable(
                    [str(item) for item in payload.get("clients", [])],
                    [str(item) for item in payload.get("families", [])],
                )
            )
            return
        if path == "/api/batch/inherit":
            payload = self._read_json_body()
            self._send_ok(
                self.pool.batch_inherit(
                    [str(item) for item in payload.get("clients", [])],
                    [str(item) for item in payload.get("families", [])],
                )
            )
            return
        if path == "/api/discovery/refresh":
            payload = self._read_json_body()
            if bool(payload.get("summary")):
                self._send_ok(self.pool.discovery_summary(refresh=True))
            else:
                self._send_ok(self.pool.discovery(refresh=True))
            return
        if path == "/api/cleanup/scan":
            self._send_ok(self.pool.cleanup_scan())
            return
        if path == "/api/cleanup/mark":
            payload = self._read_json_body()
            self._send_ok(self.pool.cleanup_mark(str(payload.get("skill_id", "")), str(payload.get("label", ""))))
            return
        if path == "/api/scan-sources/add":
            payload = self._read_json_body()
            self._send_ok(
                self.pool.scan_source_add(
                    str(payload.get("path", "")),
                    role=str(payload.get("role", "")),
                    client=payload.get("client") or None,
                    path_kind=str(payload.get("path_kind", "stable") or "stable"),
                    enabled=bool(payload.get("enabled", True)),
                    suggested=bool(payload.get("suggested", False)),
                    notes=str(payload.get("notes", "") or ""),
                )
            )
            return
        if path == "/api/scan-sources/update":
            payload = self._read_json_body()
            self._send_ok(
                self.pool.scan_source_update(
                    str(payload.get("id", "")),
                    path=payload.get("path"),
                    role=payload.get("role"),
                    client=payload.get("client"),
                    path_kind=payload.get("path_kind"),
                    enabled=payload.get("enabled"),
                    suggested=payload.get("suggested"),
                    notes=payload.get("notes"),
                )
            )
            return
        if path == "/api/scan-sources/remove":
            payload = self._read_json_body()
            self._send_ok(self.pool.scan_source_remove(str(payload.get("id", ""))))
            return
        if path == "/api/scan-sources/scan":
            payload = self._read_json_body()
            self._send_ok(self.pool.scan_sources_scan(payload.get("id") or None))
            return
        if path == "/api/tools/run":
            payload = self._read_json_body()
            result = self.pool.run_tool_action(str(payload.get("action_id", "")))
            if result.get("requires_server_shutdown"):
                self._send_ok({"action_id": "stop_console", "stopping": True})
                threading.Thread(target=self._shutdown_console_server, daemon=True).start()
                return
            self._send_ok(result)
            return

        if len(segments) == 4 and segments[:2] == ["api", "skills"] and segments[3] == "enable":
            self._send_ok(self.pool.set_enabled_global(self._safe_path_param(segments[2]), True))
            return
        if len(segments) == 4 and segments[:2] == ["api", "skills"] and segments[3] == "disable":
            self._send_ok(self.pool.set_enabled_global(self._safe_path_param(segments[2]), False))
            return
        if len(segments) == 5 and segments[:3] == ["api", "mcp", "clients"]:
            payload = self._read_json_body()
            client = self._safe_path_param(segments[3])
            action = segments[4]
            if action == "enable":
                self._send_ok(self.pool.mcp_enable(client, str(payload.get("server_name", ""))))
                return
            if action == "disable":
                self._send_ok(self.pool.mcp_disable(client, str(payload.get("server_name", ""))))
                return
            if action == "add":
                self._send_ok(
                    self.pool.mcp_add(
                        client,
                        str(payload.get("server_name", "")),
                        str(payload.get("command", "")),
                        args=[str(item) for item in payload.get("args", [])],
                        enabled=bool(payload.get("enabled", True)),
                    )
                )
                return
            if action == "update":
                enabled = payload.get("enabled")
                self._send_ok(
                    self.pool.mcp_update(
                        client,
                        str(payload.get("server_name", "")),
                        new_name=payload.get("new_name") or None,
                        command=payload.get("command") if "command" in payload else None,
                        args=[str(item) for item in payload.get("args", [])] if "args" in payload else None,
                        enabled=enabled if isinstance(enabled, bool) else None,
                    )
                )
                return
            if action == "remove":
                self._send_ok(self.pool.mcp_remove(client, str(payload.get("server_name", ""))))
                return
        if len(segments) == 5 and segments[:4] == ["api", "mcp", "clients", "codex"] and segments[4] == "dedupe":
            self._send_ok(self.pool.mcp_dedupe_codex())
            return
        if len(segments) == 4 and segments[:2] == ["api", "clients"] and segments[3] == "publish":
            payload = self._read_json_body()
            self._send_ok(self.pool.publish(self._safe_path_param(segments[2]), force=bool(payload.get("force", False))))
            return
        if len(segments) == 4 and segments[:2] == ["api", "clients"] and segments[3] == "rollback":
            payload = self._read_json_body()
            backup_id = payload.get("backup_id") or None
            if payload.get("latest"):
                backup_id = self.pool.latest_backup_id(self._safe_path_param(segments[2]))
            self._send_ok(self.pool.rollback(self._safe_path_param(segments[2]), backup_id=backup_id))
            return

        raise FileNotFoundError(path)

    def _read_json_body(self) -> Dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _validate_csrf(self) -> None:
        """Validate CSRF token on POST requests from browser contexts."""
        # Only enforce CSRF for browser requests (those with Origin or Cookie headers).
        # API clients and tests typically don't send these, so they're exempt.
        has_origin = self.headers.get("Origin") is not None
        has_cookie = self.headers.get("Cookie") is not None
        if not has_origin and not has_cookie:
            return
        token = self.headers.get("X-CSRF-Token", "")
        if not token or not secrets.compare_digest(token, self.csrf_token):
            raise PermissionError("Invalid or missing CSRF token")

    def _parse_multipart(self, content_type: str) -> Dict[str, dict]:
        """Manual multipart/form-data parser. Returns {name: {data, filename, content_type}}."""
        match = re.search(r"boundary=([^;,\s]+)", content_type, re.IGNORECASE)
        if not match:
            raise ValueError("Missing boundary in multipart Content-Type")
        boundary = match.group(1).encode("utf-8")
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 500 * 1024 * 1024:
            raise ValueError("Invalid or excessive Content-Length for upload")
        body = self.rfile.read(content_length)
        parts: Dict[str, dict] = {}
        delimiter = b"--" + boundary
        segments = body.split(delimiter)
        for segment in segments[1:]:
            if segment.strip() == b"--" or segment.strip() == b"":
                continue
            header_end = segment.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            raw_headers = segment[:header_end].decode("utf-8", errors="replace")
            part_body = segment[header_end + 4:]
            if part_body.endswith(b"\r\n"):
                part_body = part_body[:-2]
            disp_match = re.search(
                r'Content-Disposition:\s*form-data;[^"]*name="([^"]*)"', raw_headers, re.IGNORECASE
            )
            name = disp_match.group(1) if disp_match else ""
            fname_match = re.search(
                r'Content-Disposition:\s*form-data;[^"]*filename="([^"]*)"', raw_headers, re.IGNORECASE
            )
            filename = fname_match.group(1) if fname_match else ""
            ct_match = re.search(r"Content-Type:\s*(\S+)", raw_headers, re.IGNORECASE)
            part_ct = ct_match.group(1) if ct_match else ""
            if name:
                parts[name] = {"data": part_body, "filename": filename, "content_type": part_ct}
        return parts

    def _import_uploaded_zip(self) -> Dict:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("ZIP import expects multipart/form-data")
        parts = self._parse_multipart(content_type)
        field = parts.get("zip") or parts.get("file")
        if field is None or not field.get("data"):
            raise ValueError("ZIP upload field must be named 'zip' or 'file'")
        suffix = Path(field.get("filename", "") or "uploaded.zip").suffix or ".zip"
        with tempfile.NamedTemporaryFile(prefix="skillpool-upload-", suffix=suffix, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(field["data"])
        try:
            return self.pool.import_zip(temp_path)
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    def _shutdown_console_server(self) -> None:
        time.sleep(0.2)
        try:
            if self.pool.console_pid_path.exists():
                self.pool.console_pid_path.unlink()
        except OSError:
            pass
        self.server.shutdown()

    def _send_static(self, path: Path):
        root = UI_DIR.resolve()
        target = path.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise FileNotFoundError(str(path))
        if not target.is_file():
            raise FileNotFoundError(str(path))
        body = target.read_bytes()
        mime_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_ok(self, data, status: int = 200):
        self._send_json({"ok": True, "data": data}, status=status)

    def _send_error(self, code: str, message: str, status: int):
        self._send_json({"ok": False, "error": {"code": code, "message": message}}, status=status)

    def _send_json(self, payload, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def create_server(pool: SkillPool, host: str = "127.0.0.1", port: int = 8765) -> SkillPoolWebServer:
    return SkillPoolWebServer((host, port), pool)


def serve(pool: SkillPool, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> int:
    server = create_server(pool, host=host, port=port)
    actual_host, actual_port = server.server_address[:2]
    url = "http://{}:{}/".format(actual_host, actual_port)
    print("SkillPool console listening at {}".format(url))
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSkillPool console stopped")
    finally:
        server.server_close()
    return 0
