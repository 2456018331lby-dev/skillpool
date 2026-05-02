from __future__ import annotations

# Auto-extracted from core.py - do not edit directly.

from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import os
import socket
import subprocess

from skillpool_app.core import (
    _powershell_command,
)


class MixinConsole:
    """Mixin: _console_pid_value, _query_process_command_line, _is_console_online, console_status, _read_shortcut_target..."""

    def _console_pid_value(self) -> Tuple[Optional[int], bool, Optional[str]]:
        self.init_state()
        if not self.console_pid_path.exists():
            return None, False, "pid file missing"
        raw = self.console_pid_path.read_text(
            encoding="utf-8", errors="replace"
        ).strip()
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
                    '$process = Get-CimInstance Win32_Process -Filter "ProcessId = {}"'.format(
                        pid
                    ),
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
            with socket.create_connection(
                (self.console_host, self.console_port), timeout=0.6
            ):
                return True
        except OSError:
            return False

    def console_status(self) -> Dict[str, object]:
        pid, has_pid_file, pid_error = self._console_pid_value()
        command_line = self._query_process_command_line(pid or 0) if pid else None
        matches_skillpool = bool(
            command_line
            and "skillpool.py" in command_line
            and " serve" in " {} ".format(command_line)
        )
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
                    "$shortcut = $shell.CreateShortcut('{}')".format(
                        str(shortcut_path).replace("'", "''")
                    ),
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
            status = (
                "ready" if Path(target_path) == Path(expected_target) else "mismatch"
            )
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
        icon_path = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "SHELL32.dll"
        )
        result = subprocess.run(
            _powershell_command(
                "$shell = New-Object -ComObject WScript.Shell",
                "$shortcut = $shell.CreateShortcut('{}')".format(
                    str(shortcut_path).replace("'", "''")
                ),
                "$shortcut.TargetPath = '{}'".format(str(target).replace("'", "''")),
                "$shortcut.WorkingDirectory = '{}'".format(
                    str(self.root).replace("'", "''")
                ),
                "$shortcut.Description = 'Open SkillPool local console'",
                "$shortcut.IconLocation = '{},220'".format(
                    str(icon_path).replace("'", "''")
                ),
                "$shortcut.Save()",
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "创建桌面快捷方式失败: {}".format(
                    (result.stderr or result.stdout or "").strip() or "unknown error"
                )
            )
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
                "results": [
                    self.preview(client, detailed=True)
                    for client in sorted(status.get("clients", {}).keys())
                ],
            }
        if action_id == "doctor_all_deep":
            clients = sorted(self.load_clients().get("clients", {}).keys())
            return {
                "action_id": action_id,
                "results": [
                    self.doctor(deep=True, client=client) for client in clients
                ],
            }
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
