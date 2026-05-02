import json
import io
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import skillpool_app.core as core_module
from skillpool_app.core import SkillPool
from skillpool_app.web import create_server


def make_skill(base: Path, relative: str, name: str, description: str = "") -> Path:
    skill_dir = base / relative
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: {}\ndescription: {}\n---\n\n# {}\n\n{}\n".format(
            name,
            description or name,
            name,
            description or name,
        ),
        encoding="utf-8",
    )
    return skill_dir


class SkillPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="skillpool-test-"))
        self.servers = []
        self.server_threads = []
        self.hermes_config_path = self.temp_dir / "hermes-config.yaml"
        self.openclaw_config_path = self.temp_dir / "openclaw.json"
        self.qclaw_config_path = self.temp_dir / "qclaw.json"
        self.autoclaw_config_path = self.temp_dir / "autoclaw.json"
        self.codex_config_path = self.temp_dir / "codex-config.toml"
        self.claude_settings_path = self.temp_dir / "claude-settings.json"
        self.claude_mcp_path = self.temp_dir / "claude-mcp.json"
        self.claude_plugin_cache = self.temp_dir / "claude-plugin-cache"
        self.claude_plugin_cache.mkdir(parents=True, exist_ok=True)
        self.hermes_config_path.write_text("", encoding="utf-8")
        self.openclaw_config_path.write_text("{}", encoding="utf-8")
        self.qclaw_config_path.write_text("{}", encoding="utf-8")
        self.autoclaw_config_path.write_text("{}", encoding="utf-8")
        self.codex_config_path.write_text("", encoding="utf-8")
        self.claude_settings_path.write_text("{}", encoding="utf-8")
        self.claude_mcp_path.write_text("{}", encoding="utf-8-sig")
        self.clients = {
            "hermes": {
                "target_dir": str(self.temp_dir / "client-targets" / "hermes"),
                "config_path": None,
                "mode": "mirror-native",
                "config_mode": "none",
                "mcp_mode": "hermes-yaml",
                "mcp_config_path": str(self.hermes_config_path),
                "plugin_cache_dir": None,
            },
            "openclaw": {
                "target_dir": str(self.temp_dir / "client-targets" / "openclaw"),
                "config_path": str(self.openclaw_config_path),
                "mode": "mirror-native",
                "config_mode": "openclaw-extra-dirs",
                "mcp_mode": "unsupported",
                "mcp_config_path": None,
                "plugin_cache_dir": None,
            },
            "qclaw": {
                "target_dir": str(self.temp_dir / "client-targets" / "qclaw"),
                "config_path": str(self.qclaw_config_path),
                "mode": "mirror-native",
                "config_mode": "openclaw-extra-dirs",
                "mcp_mode": "unsupported",
                "mcp_config_path": None,
                "plugin_cache_dir": None,
            },
            "autoclaw": {
                "target_dir": str(self.temp_dir / "client-targets" / "autoclaw"),
                "config_path": str(self.autoclaw_config_path),
                "mode": "mirror-native",
                "config_mode": "none",
                "mcp_mode": "unsupported",
                "mcp_config_path": None,
                "plugin_cache_dir": None,
            },
            "codex": {
                "target_dir": str(self.temp_dir / "client-targets" / "codex"),
                "config_path": str(self.codex_config_path),
                "mode": "mirror-native",
                "config_mode": "none",
                "mcp_mode": "codex-toml",
                "mcp_config_path": str(self.codex_config_path),
                "plugin_cache_dir": None,
            },
            "claude": {
                "target_dir": str(self.temp_dir / "client-targets" / "claude"),
                "config_path": str(self.claude_settings_path),
                "mode": "mirror-native",
                "config_mode": "none",
                "mcp_mode": "claude-json",
                "mcp_config_path": str(self.claude_mcp_path),
                "plugin_cache_dir": str(self.claude_plugin_cache),
            },
        }
        self.pool = SkillPool(root=self.temp_dir / "pool-home", clients=self.clients)
        self.pool.init_state()

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.server_threads:
            thread.join(timeout=2)
        shutil.rmtree(str(self.temp_dir))

    def start_web_server(self):
        server = create_server(self.pool, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        self.servers.append(server)
        self.server_threads.append(thread)
        return "http://127.0.0.1:{}".format(server.server_address[1])

    def request_json(self, base_url, path, method="GET", body=None, headers=None):
        data = None
        if body is not None:
            if isinstance(body, bytes):
                data = body
            else:
                data = json.dumps(body).encode("utf-8")
                headers = dict(headers or {})
                headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(base_url + path, data=data, method=method, headers=headers or {})
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def patch_shortcut_subprocess(self):
        original_run = core_module.subprocess.run
        original_console_online = self.pool._is_console_online
        shortcut_path = self.temp_dir / "Desktop" / "SkillPool Console.lnk"
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        self.pool.desktop_shortcut_path = shortcut_path
        self.pool._is_console_online = lambda: False

        class Result:
            def __init__(self, stdout="", stderr="", returncode=0):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode

        def fake_run(command, capture_output=False, text=False, check=False):
            script = command[-1]
            if "Get-CimInstance Win32_Process" in script:
                return Result("", "", 1)
            if "TargetPath =" in script and "CreateShortcut" in script:
                shortcut_path.write_text("shortcut", encoding="utf-8")
                return Result("", "", 0)
            if "CreateShortcut" in script and "TargetPath" in script:
                if shortcut_path.exists():
                    return Result(str(self.pool.root / "open-console.cmd"), "", 0)
                return Result("", "", 1)
            raise AssertionError("Unexpected subprocess call: {}".format(script))

        core_module.subprocess.run = fake_run
        return original_run, original_console_online

    def test_import_skill_dir_registers_and_copies(self):
        source_root = self.temp_dir / "sources"
        skill_dir = make_skill(source_root, "alpha", "Alpha")
        result = self.pool.import_skill_dir(
            skill_dir,
            source_type="local-scan",
            source_locator="test:alpha",
            source_version="local",
            prefer_client="hermes",
        )
        registry = self.pool.load_registry()
        self.assertIn(result["skill_id"], registry["skills"])
        self.assertTrue((self.pool.pool_dir / result["skill_id"] / "SKILL.md").exists())
        self.assertEqual(
            registry["skills"][result["skill_id"]]["client_overrides"]["hermes"],
            "prefer:{}".format(result["skill_id"]),
        )

    def test_scan_local_imports_all_client_sources(self):
        hermes_source = self.temp_dir / "scan" / "hermes"
        openclaw_source = self.temp_dir / "scan" / "openclaw"
        make_skill(hermes_source, "cat/one", "One")
        make_skill(openclaw_source, "two", "Two")
        clients = self.pool.load_clients()
        clients["clients"]["hermes"]["target_dir"] = str(hermes_source)
        clients["clients"]["openclaw"]["target_dir"] = str(openclaw_source)
        self.pool.save_clients(clients)
        result = self.pool.scan_local()
        self.assertEqual(result["hermes"], 1)
        self.assertEqual(result["openclaw"], 1)
        registry = self.pool.load_registry()
        names = {skill["name"] for skill in registry["skills"].values()}
        self.assertEqual(names, {"One", "Two"})

    def test_import_zip_finds_nested_skill(self):
        source_root = self.temp_dir / "zip-source"
        make_skill(source_root, "nested/demo-skill", "Demo Skill")
        archive = self.temp_dir / "skills.zip"
        with zipfile.ZipFile(str(archive), "w") as zf:
            for path in source_root.rglob("*"):
                if path.is_file():
                    zf.write(str(path), str(path.relative_to(source_root)))
        result = self.pool.import_zip(archive)
        self.assertEqual(len(result["imported_skill_ids"]), 1)

    def test_import_zip_rejects_missing_skill(self):
        archive = self.temp_dir / "empty.zip"
        with zipfile.ZipFile(str(archive), "w") as zf:
            zf.writestr("notes/readme.txt", "no skill here")
        with self.assertRaises(ValueError):
            self.pool.import_zip(archive)

    def test_discover_skills_ignores_nested_skill_markdown_inside_skill(self):
        root = self.temp_dir / "nested-source"
        skill_dir = make_skill(root, "outer-skill", "Outer Skill")
        nested = skill_dir / "references" / "nested"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "SKILL.md").write_text("---\nname: Nested\n---\n", encoding="utf-8")
        discovered = self.pool.discover_skills(root)
        self.assertEqual(discovered, [skill_dir])

    def test_scan_local_imports_configured_extra_dirs(self):
        extra_dir = self.temp_dir / "extra-skills"
        make_skill(extra_dir, "extra-one", "Extra One")
        openclaw_config = self.temp_dir / "openclaw.json"
        openclaw_config.write_text(
            json.dumps({"skills": {"load": {"extraDirs": [str(extra_dir)]}}}),
            encoding="utf-8",
        )
        clients = self.pool.load_clients()
        clients["clients"]["openclaw"]["config_path"] = str(openclaw_config)
        clients["clients"]["openclaw"]["target_dir"] = str(self.temp_dir / "empty-target")
        self.pool.save_clients(clients)
        result = self.pool.scan_local()
        self.assertEqual(result["openclaw"], 1)
        registry = self.pool.load_registry()
        skill = next(item for item in registry["skills"].values() if item["name"] == "Extra One")
        self.assertEqual(skill["source_scope"], "extra_dir")
        self.assertEqual(skill["source_client"], "openclaw")
        self.assertIn("openclaw", skill["available_clients"])

    def test_preview_updates_client_metadata_and_writes_diff_artifacts(self):
        source_root = self.temp_dir / "sources"
        make_skill(source_root, "openclaw/preview-skill", "Preview Skill")
        self.pool.import_skill_dir(
            source_root / "openclaw" / "preview-skill",
            source_type="local-scan",
            source_locator="openclaw:preview",
            source_version="local",
            prefer_client="openclaw",
            source_client="openclaw",
            source_scope="target_dir",
            source_root=str(source_root / "openclaw"),
        )
        registry_before = self.pool.registry_path.read_text(encoding="utf-8")
        preview = self.pool.preview("openclaw", detailed=True)
        self.assertEqual(preview["status"], "safe")
        self.assertEqual(preview["diff_counts"]["added"], 1)
        self.assertEqual(registry_before, self.pool.registry_path.read_text(encoding="utf-8"))
        clients = self.pool.load_clients()
        self.assertEqual(clients["clients"]["openclaw"]["last_preview_status"], preview["status"])
        self.assertEqual(clients["clients"]["openclaw"]["last_preview_at"], preview["generated_at"])
        self.assertTrue((self.pool.publish_dir / "openclaw" / "preview.json").exists())
        self.assertTrue((self.pool.publish_dir / "openclaw" / "diff.json").exists())

    def test_scan_sources_scan_and_discovery(self):
        global_dir = self.temp_dir / "shared-scan-source"
        live_dir = self.temp_dir / "custom-live-source"
        transient_dir = self.temp_dir / "transient-scan-source"
        make_skill(global_dir, "alpha-shared", "Alpha Shared")
        make_skill(live_dir, "beta-live", "Beta Live")
        make_skill(transient_dir, "temp-only", "Temp Only")

        added_global = self.pool.scan_source_add(str(global_dir), role="global_source", path_kind="workspace")
        added_live = self.pool.scan_source_add(str(live_dir), role="both", client="hermes", path_kind="workspace")
        self.pool.scan_source_add(str(transient_dir), role="global_source", path_kind="transient", enabled=False, suggested=True)

        listed = self.pool.scan_sources_list()
        self.assertTrue(any(item["id"] == added_global["id"] for item in listed["sources"]))
        self.assertTrue(any(item["id"] == added_live["id"] for item in listed["sources"]))

        scan_result = self.pool.scan_sources_scan()
        self.assertGreaterEqual(scan_result["total"], 2)
        registry = self.pool.load_registry()
        names = {skill["name"] for skill in registry["skills"].values()}
        self.assertIn("Alpha Shared", names)
        self.assertIn("Beta Live", names)

        inventory = self.pool.inventory("hermes", include_mcp=False)
        self.assertTrue(any(item["path"] == str(live_dir) for item in inventory["skills"]["source_directories"]))
        self.assertGreaterEqual(inventory["skills"]["live_total_count"], 1)

        discovery = self.pool.discovery()
        self.assertTrue(any(item["path"] == str(transient_dir / "temp-only") for item in discovery["transient_only"]))
        self.assertTrue(any(source["path"] == str(global_dir) for source in discovery["sources"]))

    def test_skills_matrix_groups_logical_skills(self):
        source_root = self.temp_dir / "sources"
        shared = self.pool.import_skill_dir(
            make_skill(source_root, "shared/alpha", "Alpha Matrix"),
            source_type="github",
            source_locator="repo#alpha",
            source_version="main",
        )
        local = self.pool.import_skill_dir(
            make_skill(source_root, "hermes/alpha-local", "Alpha Matrix", description="preferred for hermes"),
            source_type="local-scan",
            source_locator="hermes:alpha-local",
            source_version="local",
            prefer_client="hermes",
        )
        self.pool.publish("hermes")

        matrix = self.pool.skills_matrix()
        row = next(item for item in matrix["rows"] if item["conflict_family"] == "alpha-matrix")
        self.assertEqual(row["member_count"], 2)
        self.assertEqual(row["clients"]["hermes"]["status"], "published")
        self.assertEqual(row["clients"]["openclaw"]["status"], "pool_only")
        self.assertTrue(any(instance["skill_id"] == shared["skill_id"] for instance in row["instances"]))
        self.assertTrue(any(instance["skill_id"] == local["skill_id"] for instance in row["instances"]))
        self.assertTrue(all(instance["fingerprint"] for instance in row["instances"]))
        self.assertTrue(all(instance["files_path"] for instance in row["instances"]))
        self.assertTrue(any(item["type"] == "duplicate_across_clients" for item in row["anomalies"]))

    def test_system_status_and_tool_actions(self):
        original_run, original_console_online = self.patch_shortcut_subprocess()
        try:
            system = self.pool.system_status()
            self.assertEqual(system["console"]["status"], "stopped")
            self.assertEqual(system["shortcut"]["status"], "missing")

            created = self.pool.create_desktop_shortcut()
            self.assertEqual(created["status"], "ready")
            self.assertTrue(Path(created["path"]).exists())

            actions = self.pool.tool_actions()
            action_ids = {item["id"] for item in actions["actions"]}
            self.assertIn("preview_all", action_ids)
            self.assertIn("recreate_shortcut", action_ids)
        finally:
            core_module.subprocess.run = original_run
            self.pool._is_console_online = original_console_online

    def test_publish_prefers_local_skill_and_rewrites_config(self):
        source_root = self.temp_dir / "sources"
        local = make_skill(source_root, "local/alpha", "Alpha")
        remote = make_skill(source_root, "remote/alpha-remote", "Alpha")
        local_result = self.pool.import_skill_dir(
            local,
            source_type="local-scan",
            source_locator="openclaw:alpha",
            source_version="local",
            prefer_client="openclaw",
        )
        self.pool.import_skill_dir(
            remote,
            source_type="github",
            source_locator="repo#alpha",
            source_version="main",
        )
        publish = self.pool.publish("openclaw")
        self.assertEqual(publish["published_count"], 1)
        target_dir = Path(self.clients["openclaw"]["target_dir"])
        self.assertTrue((target_dir / "alpha" / "SKILL.md").exists())
        config = json.loads(Path(self.clients["openclaw"]["config_path"]).read_text(encoding="utf-8"))
        self.assertEqual(config["skills"]["load"]["extraDirs"], [str(target_dir)])
        clients_state = self.pool.load_clients()
        self.assertEqual(
            clients_state["clients"]["openclaw"]["published_skill_ids"],
            [local_result["skill_id"]],
        )

    def test_publish_skips_other_clients_local_skills(self):
        source_root = self.temp_dir / "sources"
        hermes_skill = make_skill(source_root, "hermes/only-hermes", "Only Hermes")
        openclaw_skill = make_skill(source_root, "openclaw/only-openclaw", "Only OpenClaw")
        hermes_result = self.pool.import_skill_dir(
            hermes_skill,
            source_type="local-scan",
            source_locator="hermes:only-hermes",
            source_version="local",
            prefer_client="hermes",
        )
        openclaw_result = self.pool.import_skill_dir(
            openclaw_skill,
            source_type="local-scan",
            source_locator="openclaw:only-openclaw",
            source_version="local",
            prefer_client="openclaw",
        )
        publish = self.pool.publish("openclaw")
        self.assertEqual(publish["published_count"], 1)
        clients_state = self.pool.load_clients()
        self.assertEqual(
            clients_state["clients"]["openclaw"]["published_skill_ids"],
            [openclaw_result["skill_id"]],
        )
        self.assertNotIn(
            hermes_result["skill_id"],
            clients_state["clients"]["openclaw"]["published_skill_ids"],
        )

    def test_publish_all_requires_force(self):
        with self.assertRaises(RuntimeError):
            self.pool.publish_all()

    def test_override_switches_conflict_choice(self):
        source_root = self.temp_dir / "sources"
        first = make_skill(source_root, "first/conflict", "Conflict Skill")
        second = make_skill(source_root, "second/conflict-two", "Conflict Skill", description="other")
        first_result = self.pool.import_skill_dir(
            first,
            source_type="local-scan",
            source_locator="hermes:first",
            source_version="local",
            prefer_client="hermes",
        )
        second_result = self.pool.import_skill_dir(
            second,
            source_type="github",
            source_locator="repo#second",
            source_version="main",
        )
        self.pool.override_set("hermes", "conflict-skill", second_result["skill_id"])
        publish = self.pool.publish("hermes")
        self.assertEqual(publish["published_count"], 1)
        clients_state = self.pool.load_clients()
        self.assertEqual(
            clients_state["clients"]["hermes"]["published_skill_ids"],
            [second_result["skill_id"]],
        )
        registry = self.pool.load_registry()
        self.assertEqual(registry["skills"][first_result["skill_id"]]["client_overrides"].get("hermes"), "inherit")
        self.assertEqual(
            registry["skills"][second_result["skill_id"]]["client_overrides"].get("hermes"),
            "prefer:{}".format(second_result["skill_id"]),
        )

    def test_override_list_inherit_disable(self):
        source_root = self.temp_dir / "sources"
        skill_dir = make_skill(source_root, "alpha", "Alpha")
        result = self.pool.import_skill_dir(
            skill_dir,
            source_type="local-scan",
            source_locator="hermes:alpha",
            source_version="local",
            prefer_client="hermes",
        )
        listed = self.pool.override_list("hermes")
        self.assertEqual(len(listed["overrides"]), 1)
        self.pool.override_disable("hermes", "alpha")
        registry = self.pool.load_registry()
        self.assertEqual(registry["skills"][result["skill_id"]]["client_overrides"]["hermes"], "disabled")
        self.pool.override_inherit("hermes", "alpha")
        registry = self.pool.load_registry()
        self.assertEqual(registry["skills"][result["skill_id"]]["client_overrides"]["hermes"], "inherit")

    def test_rollback_restores_previous_target(self):
        target_dir = Path(self.clients["openclaw"]["target_dir"])
        make_skill(target_dir, "legacy-skill", "Legacy Skill")
        source_root = self.temp_dir / "sources"
        make_skill(source_root, "new/new-skill", "New Skill")
        self.pool.import_skill_dir(
            source_root / "new" / "new-skill",
            source_type="local-scan",
            source_locator="openclaw:new",
            source_version="local",
            prefer_client="openclaw",
        )
        publish = self.pool.publish("openclaw")
        self.pool.rollback("openclaw", publish["backup_id"])
        self.assertTrue((target_dir / "legacy-skill" / "SKILL.md").exists())
        self.assertFalse((target_dir / "new-skill" / "SKILL.md").exists())

    def test_rollback_list_and_inspect(self):
        target_dir = Path(self.clients["openclaw"]["target_dir"])
        make_skill(target_dir, "legacy-skill", "Legacy Skill")
        source_root = self.temp_dir / "sources"
        make_skill(source_root, "new/new-skill", "New Skill")
        self.pool.import_skill_dir(
            source_root / "new" / "new-skill",
            source_type="local-scan",
            source_locator="openclaw:new",
            source_version="local",
            prefer_client="openclaw",
        )
        publish = self.pool.publish("openclaw")
        listed = self.pool.rollback_list("openclaw")
        self.assertEqual(listed["backups"][0]["backup_id"], publish["backup_id"])
        inspected = self.pool.rollback_inspect("openclaw", publish["backup_id"])
        self.assertEqual(inspected["backup_id"], publish["backup_id"])
        self.assertTrue(inspected["target_exists"])

    def test_deep_doctor_detects_manifest_target_mismatch(self):
        source_root = self.temp_dir / "sources"
        make_skill(source_root, "new/new-skill", "New Skill")
        self.pool.import_skill_dir(
            source_root / "new" / "new-skill",
            source_type="local-scan",
            source_locator="openclaw:new",
            source_version="local",
            prefer_client="openclaw",
        )
        self.pool.publish("openclaw")
        target_dir = Path(self.clients["openclaw"]["target_dir"])
        shutil.rmtree(str(target_dir / "new-skill"))
        result = self.pool.doctor(deep=True, client="openclaw")
        self.assertEqual(result["checks"][0]["status"], "fail")
        self.assertTrue((self.pool.publish_dir / "openclaw" / "doctor.json").exists())

    def test_preview_and_deep_doctor_update_client_metadata(self):
        source_root = self.temp_dir / "sources"
        make_skill(source_root, "new/new-skill", "New Skill")
        self.pool.import_skill_dir(
            source_root / "new" / "new-skill",
            source_type="local-scan",
            source_locator="openclaw:new",
            source_version="local",
            prefer_client="openclaw",
        )
        preview = self.pool.preview("openclaw")
        clients = self.pool.load_clients()
        self.assertEqual(clients["clients"]["openclaw"]["last_preview_status"], preview["status"])
        self.assertEqual(clients["clients"]["openclaw"]["last_preview_at"], preview["generated_at"])
        doctor = self.pool.doctor(deep=True, client="openclaw")
        clients = self.pool.load_clients()
        self.assertEqual(clients["clients"]["openclaw"]["last_deep_doctor_status"], doctor["checks"][0]["status"])
        self.assertEqual(clients["clients"]["openclaw"]["last_deep_doctor_at"], doctor["checks"][0]["generated_at"])

    def test_list_skills_supports_pagination_sort_and_enabled_filter(self):
        source_root = self.temp_dir / "sources"
        alpha = self.pool.import_skill_dir(
            make_skill(source_root, "alpha", "Alpha"),
            source_type="github",
            source_locator="repo#alpha",
            source_version="main",
        )
        beta = self.pool.import_skill_dir(
            make_skill(source_root, "beta", "Beta"),
            source_type="github",
            source_locator="repo#beta",
            source_version="main",
        )
        self.pool.import_skill_dir(
            make_skill(source_root, "gamma", "Gamma"),
            source_type="local-scan",
            source_locator="hermes:gamma",
            source_version="local",
            prefer_client="hermes",
        )
        self.pool.set_enabled_global(beta["skill_id"], False)

        page_one = self.pool.list_skills(page=1, page_size=1, sort_by="name", sort_dir="asc")
        self.assertEqual(page_one["total"], 3)
        self.assertEqual(page_one["page_size"], 1)
        self.assertEqual(page_one["total_pages"], 3)
        self.assertEqual(page_one["skills"][0]["skill_id"], alpha["skill_id"])

        disabled_only = self.pool.list_skills(enabled_global="disabled")
        self.assertEqual(disabled_only["total"], 1)
        self.assertEqual(disabled_only["skills"][0]["skill_id"], beta["skill_id"])

    def test_get_skill_returns_detail_and_conflict_members(self):
        source_root = self.temp_dir / "sources"
        first = self.pool.import_skill_dir(
            make_skill(source_root, "first/conflict", "Conflict Skill"),
            source_type="local-scan",
            source_locator="hermes:first",
            source_version="local",
            prefer_client="hermes",
        )
        second = self.pool.import_skill_dir(
            make_skill(source_root, "second/conflict-two", "Conflict Skill", description="secondary variant"),
            source_type="github",
            source_locator="repo#second",
            source_version="main",
        )

        detail = self.pool.get_skill(first["skill_id"])
        self.assertEqual(detail["skill_id"], first["skill_id"])
        self.assertTrue(detail["family_has_conflict"])
        self.assertEqual(detail["conflict_member_count"], 2)
        self.assertEqual(detail["conflict_members"][0]["skill_id"], second["skill_id"])
        self.assertGreaterEqual(len(detail["source_records"]), 1)

    def test_list_conflicts_supports_family_filter(self):
        source_root = self.temp_dir / "sources"
        self.pool.import_skill_dir(
            make_skill(source_root, "first/conflict", "Conflict Skill"),
            source_type="local-scan",
            source_locator="hermes:first",
            source_version="local",
            prefer_client="hermes",
        )
        self.pool.import_skill_dir(
            make_skill(source_root, "second/conflict-two", "Conflict Skill", description="secondary variant"),
            source_type="github",
            source_locator="repo#second",
            source_version="main",
        )

        conflicts = self.pool.list_conflicts(family="conflict-skill")
        self.assertEqual(conflicts["total"], 1)
        self.assertEqual(conflicts["conflicts"][0]["conflict_family"], "conflict-skill")

    def test_inventory_codex_parses_toml_mcp(self):
        self.codex_config_path.write_text(
            "\n".join(
                [
                    "[mcp_servers.time]",
                    "command = 'uvx'",
                    "args = ['mcp-time', '--fast']",
                    "enabled = true",
                    "",
                    "[mcp_servers.time.env]",
                    "TOKEN = 'ignored'",
                    "",
                    "[mcp_servers.github]",
                    "command = 'node'",
                    "args = ['github.js']",
                ]
            ),
            encoding="utf-8",
        )
        inventory = self.pool.inventory("codex", include_skills=False)
        self.assertEqual(inventory["mcp"]["source_status"], "ok")
        self.assertEqual(inventory["mcp"]["server_count"], 2)
        servers = {item["name"]: item for item in inventory["mcp"]["servers"]}
        self.assertEqual(servers["time"]["command"], "uvx")
        self.assertEqual(servers["time"]["args"], ["mcp-time", "--fast"])
        self.assertTrue(servers["time"]["enabled"])
        self.assertEqual(servers["github"]["source_file"], str(self.codex_config_path))

    def test_inventory_claude_merges_root_and_plugin_cache_mcp(self):
        self.claude_mcp_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "root-server": {"command": "node", "args": ["root.js"]},
                        "shared-server": {"command": "node", "args": ["root-shared.js"]},
                    }
                }
            ),
            encoding="utf-8-sig",
        )
        plugin_dir = self.claude_plugin_cache / "plugin-a"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "plugin-server": {"command": "node", "args": ["plugin.js"]},
                        "shared-server": {"command": "node", "args": ["plugin-shared.js"]},
                    }
                }
            ),
            encoding="utf-8",
        )

        inventory = self.pool.inventory("claude", include_skills=False)
        self.assertEqual(inventory["mcp"]["source_status"], "ok")
        self.assertEqual(inventory["mcp"]["server_count"], 3)
        servers = {item["name"]: item for item in inventory["mcp"]["servers"]}
        self.assertEqual(servers["shared-server"]["source_file"], str(self.claude_mcp_path))
        self.assertEqual(servers["plugin-server"]["source_kind"], "plugin_cache")

    def test_inventory_hermes_parses_yaml_mcp(self):
        self.hermes_config_path.write_text(
            "\n".join(
                [
                    "mcp_servers:",
                    "  time:",
                    "    command: uvx",
                    "    args:",
                    "      - mcp-time",
                    "      - --utc",
                    "    enabled: true",
                ]
            ),
            encoding="utf-8",
        )
        inventory = self.pool.inventory("hermes", include_skills=False)
        self.assertEqual(inventory["mcp"]["source_status"], "ok")
        self.assertEqual(inventory["mcp"]["server_count"], 1)
        self.assertEqual(inventory["mcp"]["servers"][0]["args"], ["mcp-time", "--utc"])

    def test_inventory_unsupported_mcp_sources_do_not_report_zero(self):
        for client in ("openclaw", "qclaw", "autoclaw"):
            with self.subTest(client=client):
                inventory = self.pool.inventory(client, include_skills=False)
                self.assertEqual(inventory["mcp"]["source_status"], "unsupported_source")
                self.assertIsNone(inventory["mcp"]["server_count"])

    def test_inventory_skills_reports_live_pool_published_and_source_mismatch(self):
        source_root = self.temp_dir / "sources"
        published = self.pool.import_skill_dir(
            make_skill(source_root, "published/alpha", "Published Alpha"),
            source_type="local-scan",
            source_locator="openclaw:published-alpha",
            source_version="local",
            prefer_client="openclaw",
        )
        self.pool.publish("openclaw")
        self.pool.import_skill_dir(
            make_skill(source_root, "pool/pool-only", "Pool Only"),
            source_type="github",
            source_locator="repo#pool-only",
            source_version="main",
        )
        self.pool.import_skill_dir(
            make_skill(source_root, "pool/shared", "Shared Name", description="pool variant"),
            source_type="github",
            source_locator="repo#shared-name",
            source_version="main",
        )

        registry = self.pool.load_registry()
        published_name = registry["skills"][published["skill_id"]]["published_name"]
        target_dir = Path(self.clients["openclaw"]["target_dir"])
        shutil.rmtree(str(target_dir / published_name))
        make_skill(target_dir, "live-only", "Live Only")
        make_skill(target_dir, "live-shared", "Shared Name", description="live variant")

        inventory = self.pool.inventory("openclaw", include_mcp=False)
        live_only_names = {item["name"] for item in inventory["skills"]["live_only"]}
        pool_only_names = {item["name"] for item in inventory["skills"]["pool_only"]}
        published_only_names = {item["name"] for item in inventory["skills"]["published_only"]}
        source_mismatch_names = {item["name"] for item in inventory["skills"]["source_mismatch"]}

        self.assertIn("Live Only", live_only_names)
        self.assertIn("Pool Only", pool_only_names)
        self.assertIn("Published Alpha", published_only_names)
        self.assertIn("Shared Name", source_mismatch_names)

    def test_inventory_counts_extra_dirs_as_live_sources(self):
        extra_dir = self.temp_dir / "openclaw-extra"
        make_skill(extra_dir, "extra-one", "Extra One")
        self.openclaw_config_path.write_text(
            json.dumps({"skills": {"load": {"extraDirs": [str(extra_dir)]}}}),
            encoding="utf-8",
        )
        inventory = self.pool.inventory("openclaw", include_mcp=False)
        self.assertEqual(inventory["skills"]["live_extra_dir_count"], 1)
        self.assertEqual(inventory["skills"]["live_total_count"], 1)
        self.assertTrue(any(item["path"] == str(extra_dir) for item in inventory["skills"]["source_directories"]))

    def test_mcp_write_codex_preserves_non_mcp_sections(self):
        self.codex_config_path.write_text(
            "\n".join(
                [
                    'title = "demo"',
                    "",
                    "[mcp_servers.memory]",
                    'command = "npx"',
                    "args = [",
                    '  "-y",',
                    '  "@modelcontextprotocol/server-memory",',
                    "]",
                    "enabled = true",
                    "",
                    "[other]",
                    'value = "keep"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = self.pool.mcp_disable("codex", "memory")
        text = self.codex_config_path.read_text(encoding="utf-8")
        self.assertTrue(result["changed"])
        self.assertIn('title = "demo"', text)
        self.assertIn("[other]", text)
        self.assertIn('value = "keep"', text)
        self.assertIn("enabled = false", text)

    def test_mcp_write_claude_preserves_non_mcp_fields(self):
        self.claude_mcp_path.write_text(
            json.dumps({"theme": "light", "mcpServers": {"alpha": {"command": "node", "args": ["alpha.js"], "enabled": True}}}),
            encoding="utf-8-sig",
        )
        result = self.pool.mcp_add("claude", "beta", "node", args=["beta.js"], enabled=False)
        payload = json.loads(self.claude_mcp_path.read_text(encoding="utf-8-sig"))
        self.assertTrue(result["changed"])
        self.assertEqual(payload["theme"], "light")
        self.assertIn("beta", payload["mcpServers"])
        self.assertFalse(payload["mcpServers"]["beta"]["enabled"])

    def test_mcp_write_hermes_preserves_yaml_outside_mcp_block(self):
        self.hermes_config_path.write_text(
            "\n".join(
                [
                    "profile: demo",
                    "mcp_servers:",
                    "  alpha:",
                    "    command: node",
                    "    args:",
                    "      - alpha.js",
                    "    enabled: true",
                    "workspace: /tmp/demo",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = self.pool.mcp_disable("hermes", "alpha")
        text = self.hermes_config_path.read_text(encoding="utf-8")
        self.assertTrue(result["changed"])
        self.assertIn("profile: demo", text)
        self.assertIn("workspace: /tmp/demo", text)
        self.assertIn("enabled: false", text)

    def test_mcp_dedupe_codex_removes_wrapper_duplicates(self):
        self.codex_config_path.write_text(
            "\n".join(
                [
                    "[mcp_servers.memory]",
                    'command = "npx"',
                    "args = [",
                    '  "-y",',
                    '  "@modelcontextprotocol/server-memory",',
                    "]",
                    "enabled = false",
                    "",
                    "[mcp_servers.memory-1]",
                    'command = "cmd"',
                    "args = [",
                    '  "/c",',
                    '  "npx",',
                    '  "-y",',
                    '  "@modelcontextprotocol/server-memory",',
                    "]",
                    "enabled = true",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = self.pool.mcp_dedupe_codex()
        payload = self.pool.mcp_list("codex")
        names = [item["name"] for item in payload["root_servers"]]
        self.assertTrue(result["changed"])
        self.assertEqual(names, ["memory"])
        self.assertTrue(payload["root_servers"][0]["enabled"])
        self.assertIsNotNone(result["backup_id"])

    def test_mcp_unsupported_write_raises(self):
        with self.assertRaises(RuntimeError):
            self.pool.mcp_enable("openclaw", "anything")

    def test_cleanup_scan_mark_and_export(self):
        source_root = self.temp_dir / "sources"
        first = self.pool.import_skill_dir(
            make_skill(source_root, "first/conflict", "Conflict Skill"),
            source_type="local-scan",
            source_locator="hermes:first",
            source_version="local",
            prefer_client="hermes",
        )
        self.pool.import_skill_dir(
            make_skill(source_root, "second/conflict-two", "Conflict Skill", description="secondary"),
            source_type="github",
            source_locator="repo#second",
            source_version="main",
        )
        cleanup = self.pool.cleanup_scan()
        self.assertGreaterEqual(cleanup["total"], 1)
        marked = self.pool.cleanup_mark(first["skill_id"], "keep")
        self.assertEqual(marked["label"], "keep")
        exported = self.pool.cleanup_export()
        self.assertTrue(Path(exported["markdown_path"]).exists())
        self.assertTrue(Path(exported["json_path"]).exists())

    def test_inventory_export_returns_json_and_markdown(self):
        exported_json = self.pool.inventory_export(client="codex", format="json")
        exported_markdown = self.pool.inventory_export(client="codex", format="markdown")
        self.assertEqual(exported_json["format"], "json")
        self.assertIn('"client": "codex"', exported_json["content"])
        self.assertEqual(exported_markdown["format"], "markdown")
        self.assertIn("# INVENTORY", exported_markdown["content"])

    def test_batch_disable_and_inherit_update_family_overrides(self):
        source_root = self.temp_dir / "batch-source"
        imported = self.pool.import_skill_dir(
            make_skill(source_root, "shared/batch-alpha", "Batch Alpha"),
            source_type="github",
            source_locator="repo#batch-alpha",
            source_version="main",
        )
        family = imported["conflict_family"]

        disabled = self.pool.batch_disable(["codex", "claude"], [family])
        self.assertEqual(disabled["changed_count"], 2)
        registry = self.pool.load_registry()
        members = [item for item in registry["skills"].values() if item["conflict_family"] == family]
        self.assertTrue(all(item["client_overrides"]["codex"] == "disabled" for item in members))
        self.assertTrue(all(item["client_overrides"]["claude"] == "disabled" for item in members))

        inherited = self.pool.batch_inherit(["codex", "claude"], [family])
        self.assertEqual(inherited["changed_count"], 2)
        registry = self.pool.load_registry()
        members = [item for item in registry["skills"].values() if item["conflict_family"] == family]
        self.assertTrue(all(item["client_overrides"]["codex"] == "inherit" for item in members))
        self.assertTrue(all(item["client_overrides"]["claude"] == "inherit" for item in members))

    def test_sync_preview_and_apply_sync_skill_and_supported_mcp(self):
        skill_root = self.temp_dir / "sync-source"
        shared = self.pool.import_skill_dir(
            make_skill(skill_root, "shared/sync-shared", "Sync Shared"),
            source_type="github",
            source_locator="repo#sync-shared",
            source_version="main",
        )
        disabled_skill = self.pool.import_skill_dir(
            make_skill(skill_root, "shared/sync-disabled", "Sync Disabled"),
            source_type="github",
            source_locator="repo#sync-disabled",
            source_version="main",
        )
        self.pool.override_set("codex", shared["conflict_family"], shared["skill_id"])
        self.pool.override_disable("codex", disabled_skill["conflict_family"])
        self.pool.publish("codex")
        self.codex_config_path.write_text(
            "\n".join(
                [
                    "[mcp_servers.time]",
                    'command = "uvx"',
                    'args = ["mcp-time"]',
                    "enabled = true",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        preview = self.pool.sync_preview("codex", ["hermes"], include_skills=True, include_mcp=True)
        self.assertEqual(preview["blocked_targets"], [])
        self.assertEqual(preview["skills_template"]["published_family_count"], 1)
        self.assertEqual(preview["skills_template"]["disabled_family_count"], 1)
        self.assertTrue(preview["targets"][0]["mcp"]["supported"])
        self.assertEqual(preview["targets"][0]["skills"]["counts"]["prefer_exact"], 1)
        self.assertEqual(preview["targets"][0]["skills"]["counts"]["disabled"], 1)

        applied = self.pool.sync_apply("codex", ["hermes"], include_skills=True, include_mcp=True)
        result = applied["results"][0]
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skills"]["changed_count"], 2)
        self.assertTrue((Path(self.clients["hermes"]["target_dir"]) / "sync-shared" / "SKILL.md").exists())

        registry = self.pool.load_registry()
        shared_members = [item for item in registry["skills"].values() if item["conflict_family"] == shared["conflict_family"]]
        disabled_members = [item for item in registry["skills"].values() if item["conflict_family"] == disabled_skill["conflict_family"]]
        self.assertTrue(all(item["client_overrides"]["hermes"] == f"prefer:{shared['skill_id']}" for item in shared_members))
        self.assertTrue(all(item["client_overrides"]["hermes"] == "disabled" for item in disabled_members))

        hermes_mcp = self.pool.mcp_list("hermes")
        self.assertEqual(hermes_mcp["source_status"], "ok")
        self.assertEqual(hermes_mcp["server_count"], 1)
        self.assertEqual(hermes_mcp["root_servers"][0]["name"], "time")

    def test_sync_preview_marks_unresolved_and_unavailable_families(self):
        skill_root = self.temp_dir / "sync-conflicts"
        source_preferred = self.pool.import_skill_dir(
            make_skill(skill_root, "codex/dual-source", "Dual Source", description="codex preferred"),
            source_type="local-scan",
            source_locator="codex:dual-source",
            source_version="local",
            prefer_client="codex",
            source_client="codex",
            source_scope="target_dir",
            source_root=str(skill_root / "codex"),
        )
        self.pool.import_skill_dir(
            make_skill(skill_root, "hermes/dual-target", "Dual Source", description="hermes variant"),
            source_type="local-scan",
            source_locator="hermes:dual-target",
            source_version="local",
            prefer_client="hermes",
            source_client="hermes",
            source_scope="target_dir",
            source_root=str(skill_root / "hermes"),
        )
        unavailable = self.pool.import_skill_dir(
            make_skill(skill_root, "codex/unavailable-only", "Unavailable Only"),
            source_type="local-scan",
            source_locator="codex:unavailable-only",
            source_version="local",
            prefer_client="codex",
            source_client="codex",
            source_scope="target_dir",
            source_root=str(skill_root / "codex"),
        )
        self.pool.publish("codex")

        preview = self.pool.sync_preview("codex", ["hermes"], include_skills=True, include_mcp=False)
        counts = preview["targets"][0]["skills"]["counts"]
        self.assertEqual(counts["unresolved_family"], 1)
        self.assertEqual(counts["unavailable_family"], 1)
        actions = preview["targets"][0]["skills"]["actions"]
        self.assertTrue(any(item["skill_id"] == source_preferred["skill_id"] and item["action"] == "unresolved_family" for item in actions))
        self.assertTrue(any(item["skill_id"] == unavailable["skill_id"] and item["action"] == "unavailable_family" for item in actions))

    def test_discovery_summary_details_and_refresh_use_cache(self):
        transient_dir = self.temp_dir / "cached-discovery"
        make_skill(transient_dir, "temp-only", "Temp Only")
        self.pool.scan_source_add(str(transient_dir), role="global_source", path_kind="transient", enabled=False, suggested=True)
        self.pool.scan_sources_scan()

        summary = self.pool.discovery_summary()
        self.assertEqual(summary["counts"]["transient_only"], 1)
        details = self.pool.discovery_details("transient_only", limit=1)
        self.assertEqual(details["total"], 1)
        self.assertEqual(len(details["items"]), 1)

        shutil.rmtree(str(transient_dir))
        cached_summary = self.pool.discovery_summary()
        self.assertEqual(cached_summary["counts"]["transient_only"], 1)

        refreshed_summary = self.pool.discovery_summary(refresh=True)
        self.assertEqual(refreshed_summary["counts"]["transient_only"], 0)

    def test_import_batch_imports_multiple_items(self):
        zip_root = self.temp_dir / "zip-source"
        make_skill(zip_root, "nested/demo-skill", "Demo Skill")
        archive = self.temp_dir / "skills.zip"
        with zipfile.ZipFile(str(archive), "w") as zf:
            for path in zip_root.rglob("*"):
                if path.is_file():
                    zf.write(str(path), str(path.relative_to(zip_root)))
        manifest = self.temp_dir / "batch.json"
        manifest.write_text(json.dumps([{"type": "zip", "zip_path": str(archive)}]), encoding="utf-8")
        result = self.pool.import_batch(manifest)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(len(result["imported_skill_ids"]), 1)

    def test_import_detect_github_classifies_archive(self):
        source_root = self.temp_dir / "github-source"
        make_skill(source_root, "templates/demo-skill", "Demo Skill")
        archive = self.temp_dir / "detect.zip"
        with zipfile.ZipFile(str(archive), "w") as zf:
            for path in source_root.rglob("*"):
                if path.is_file():
                    zf.write(str(path), str(Path("repo-root") / path.relative_to(source_root)))

        original_urlopen = core_module.urllib.request.urlopen

        class _FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.close()

        def _fake_urlopen(_request, **_kwargs):
            return _FakeResponse(archive.read_bytes())

        core_module.urllib.request.urlopen = _fake_urlopen
        try:
            result = self.pool.import_detect_github("owner/repo")
        finally:
            core_module.urllib.request.urlopen = original_urlopen

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["detected_type"], "template")
        self.assertEqual(result["skill_count"], 1)

    def test_web_serves_home_and_read_only_status_api(self):
        base_url = self.start_web_server()
        clients_before = self.pool.clients_path.read_text(encoding="utf-8")
        registry_before = self.pool.registry_path.read_text(encoding="utf-8")
        with urllib.request.urlopen(base_url + "/") as response:
            html = response.read().decode("utf-8")
        self.assertIn("SkillPool 控制台", html)
        status = self.request_json(base_url, "/api/status")
        self.assertTrue(status["ok"])
        self.assertEqual(status["data"]["root"], str(self.pool.root))
        self.request_json(base_url, "/api/skills")
        self.assertEqual(clients_before, self.pool.clients_path.read_text(encoding="utf-8"))
        self.assertEqual(registry_before, self.pool.registry_path.read_text(encoding="utf-8"))

    def test_web_preview_matches_core_preview_shape(self):
        source_root = self.temp_dir / "sources"
        make_skill(source_root, "new/new-skill", "New Skill")
        self.pool.import_skill_dir(
            source_root / "new" / "new-skill",
            source_type="local-scan",
            source_locator="openclaw:new",
            source_version="local",
            prefer_client="openclaw",
        )
        expected = self.pool.preview("openclaw", detailed=True, persist=False)
        base_url = self.start_web_server()
        response = self.request_json(base_url, "/api/clients/openclaw/preview?detailed=1")
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["client"], expected["client"])
        self.assertEqual(response["data"]["status"], expected["status"])
        self.assertEqual(response["data"]["diff_counts"], expected["diff_counts"])
        self.assertIn("diff", response["data"])

    def test_web_publish_blocked_when_preview_blocked(self):
        base_url = self.start_web_server()
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request_json(base_url, "/api/clients/openclaw/publish", method="POST", body={})
        self.assertEqual(context.exception.code, 409)
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "runtime_error")

    def test_web_rollback_latest_restores_backup(self):
        target_dir = Path(self.clients["openclaw"]["target_dir"])
        make_skill(target_dir, "legacy-skill", "Legacy Skill")
        source_root = self.temp_dir / "sources"
        make_skill(source_root, "new/new-skill", "New Skill")
        self.pool.import_skill_dir(
            source_root / "new" / "new-skill",
            source_type="local-scan",
            source_locator="openclaw:new",
            source_version="local",
            prefer_client="openclaw",
        )
        self.pool.publish("openclaw")
        base_url = self.start_web_server()
        response = self.request_json(base_url, "/api/clients/openclaw/rollback", method="POST", body={"latest": True})
        self.assertTrue(response["ok"])
        self.assertTrue((target_dir / "legacy-skill" / "SKILL.md").exists())
        self.assertFalse((target_dir / "new-skill" / "SKILL.md").exists())

    def test_web_zip_upload_imports_skill(self):
        source_root = self.temp_dir / "zip-source"
        make_skill(source_root, "nested/demo-skill", "Demo Skill")
        archive = self.temp_dir / "skills.zip"
        with zipfile.ZipFile(str(archive), "w") as zf:
            for path in source_root.rglob("*"):
                if path.is_file():
                    zf.write(str(path), str(path.relative_to(source_root)))
        boundary = "----skillpooltestboundary"
        body = b"".join(
            [
                ("--{}\r\n".format(boundary)).encode("utf-8"),
                b'Content-Disposition: form-data; name="zip"; filename="skills.zip"\r\n',
                b"Content-Type: application/zip\r\n\r\n",
                archive.read_bytes(),
                b"\r\n",
                ("--{}--\r\n".format(boundary)).encode("utf-8"),
            ]
        )
        base_url = self.start_web_server()
        response = self.request_json(
            base_url,
            "/api/import/zip",
            method="POST",
            body=body,
            headers={"Content-Type": "multipart/form-data; boundary={}".format(boundary)},
        )
        self.assertTrue(response["ok"])
        self.assertEqual(len(response["data"]["imported_skill_ids"]), 1)

    def test_web_skills_support_pagination_and_detail(self):
        source_root = self.temp_dir / "sources"
        alpha = self.pool.import_skill_dir(
            make_skill(source_root, "alpha", "Alpha"),
            source_type="github",
            source_locator="repo#alpha",
            source_version="main",
        )
        self.pool.import_skill_dir(
            make_skill(source_root, "beta", "Beta"),
            source_type="github",
            source_locator="repo#beta",
            source_version="main",
        )
        base_url = self.start_web_server()

        listing = self.request_json(base_url, "/api/skills?page=1&page_size=1&sort_by=name&sort_dir=asc")
        self.assertTrue(listing["ok"])
        self.assertEqual(listing["data"]["page_size"], 1)
        self.assertEqual(listing["data"]["total_pages"], 2)
        self.assertEqual(len(listing["data"]["skills"]), 1)
        self.assertEqual(listing["data"]["skills"][0]["skill_id"], alpha["skill_id"])

        detail = self.request_json(base_url, f"/api/skills/{alpha['skill_id']}")
        self.assertTrue(detail["ok"])
        self.assertEqual(detail["data"]["skill_id"], alpha["skill_id"])
        self.assertIn("source_records", detail["data"])

    def test_web_conflicts_support_family_filter(self):
        source_root = self.temp_dir / "sources"
        self.pool.import_skill_dir(
            make_skill(source_root, "first/conflict", "Conflict Skill"),
            source_type="local-scan",
            source_locator="hermes:first",
            source_version="local",
            prefer_client="hermes",
        )
        self.pool.import_skill_dir(
            make_skill(source_root, "second/conflict-two", "Conflict Skill", description="secondary variant"),
            source_type="github",
            source_locator="repo#second",
            source_version="main",
        )
        base_url = self.start_web_server()
        response = self.request_json(base_url, "/api/conflicts?family=conflict-skill")
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["total"], 1)
        self.assertEqual(response["data"]["family"], "conflict-skill")

    def test_web_inventory_endpoints_return_summary_and_detail(self):
        self.codex_config_path.write_text(
            "\n".join(
                [
                    "[mcp_servers.time]",
                    "command = 'uvx'",
                    "args = ['mcp-time']",
                ]
            ),
            encoding="utf-8",
        )
        base_url = self.start_web_server()
        summary = self.request_json(base_url, "/api/inventory")
        self.assertTrue(summary["ok"])
        self.assertEqual(len(summary["data"]["clients"]), 6)

        detail = self.request_json(base_url, "/api/inventory/codex")
        self.assertTrue(detail["ok"])
        self.assertEqual(detail["data"]["client"], "codex")
        self.assertIn("mcp", detail["data"])

        skills_only = self.request_json(base_url, "/api/inventory/openclaw/skills")
        self.assertTrue(skills_only["ok"])
        self.assertEqual(skills_only["data"]["client"], "openclaw")
        self.assertIn("skills", skills_only["data"])

        mcp_only = self.request_json(base_url, "/api/inventory/codex/mcp")
        self.assertTrue(mcp_only["ok"])
        self.assertEqual(mcp_only["data"]["client"], "codex")
        self.assertEqual(mcp_only["data"]["mcp"]["source_status"], "ok")

    def test_web_mcp_and_cleanup_endpoints(self):
        self.codex_config_path.write_text(
            "\n".join(
                [
                    "[mcp_servers.memory]",
                    'command = "npx"',
                    'args = ["-y", "@modelcontextprotocol/server-memory"]',
                    "enabled = true",
                    "",
                    "[mcp_servers.memory-1]",
                    'command = "cmd"',
                    'args = ["/c", "npx", "-y", "@modelcontextprotocol/server-memory"]',
                    "enabled = false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        base_url = self.start_web_server()
        mcp_clients = self.request_json(base_url, "/api/mcp/clients")
        self.assertTrue(mcp_clients["ok"])
        self.assertEqual(len(mcp_clients["data"]["clients"]), 6)

        mcp_detail = self.request_json(base_url, "/api/mcp/clients/codex")
        self.assertTrue(mcp_detail["ok"])
        self.assertEqual(mcp_detail["data"]["source_status"], "ok")
        self.assertEqual(len(mcp_detail["data"]["duplicate_groups"]), 1)

        dedupe = self.request_json(base_url, "/api/mcp/clients/codex/dedupe", method="POST", body={})
        self.assertTrue(dedupe["ok"])
        self.assertTrue(dedupe["data"]["changed"])

        cleanup_scan = self.request_json(base_url, "/api/cleanup/scan", method="POST", body={})
        self.assertTrue(cleanup_scan["ok"])
        cleanup_list = self.request_json(base_url, "/api/cleanup")
        self.assertTrue(cleanup_list["ok"])

    def test_web_scan_sources_matrix_and_discovery_endpoints(self):
        source_root = self.temp_dir / "scan-web"
        make_skill(source_root, "alpha", "Web Matrix Alpha")
        self.pool.scan_source_add(str(source_root), role="global_source", path_kind="workspace")
        self.pool.scan_sources_scan()

        base_url = self.start_web_server()
        matrix = self.request_json(base_url, "/api/skills/matrix")
        self.assertTrue(matrix["ok"])
        self.assertTrue(any(row["name"] == "Web Matrix Alpha" for row in matrix["data"]["rows"]))

        instances = self.request_json(base_url, "/api/skills/instances")
        self.assertTrue(instances["ok"])
        self.assertEqual(instances["data"]["total"], 1)

        sources = self.request_json(base_url, "/api/scan-sources")
        self.assertTrue(sources["ok"])
        self.assertTrue(any(item["path"] == str(source_root) for item in sources["data"]["sources"]))

        discovery = self.request_json(base_url, "/api/discovery")
        self.assertTrue(discovery["ok"])
        self.assertIn("sources", discovery["data"])

    def test_web_system_and_tool_action_endpoints(self):
        original_run, original_console_online = self.patch_shortcut_subprocess()
        try:
            base_url = self.start_web_server()
            system = self.request_json(base_url, "/api/system")
            self.assertTrue(system["ok"])
            self.assertEqual(system["data"]["shortcut"]["status"], "missing")

            actions = self.request_json(base_url, "/api/tools/actions")
            self.assertTrue(actions["ok"])
            self.assertTrue(any(item["id"] == "preview_all" for item in actions["data"]["actions"]))

            recreate = self.request_json(base_url, "/api/tools/run", method="POST", body={"action_id": "recreate_shortcut"})
            self.assertTrue(recreate["ok"])
            self.assertEqual(recreate["data"]["result"]["status"], "ready")

            cleanup = self.request_json(base_url, "/api/tools/run", method="POST", body={"action_id": "cleanup_scan"})
            self.assertTrue(cleanup["ok"])
            self.assertIn("result", cleanup["data"])
        finally:
            core_module.subprocess.run = original_run
            self.pool._is_console_online = original_console_online

    def test_web_inventory_export_endpoint(self):
        base_url = self.start_web_server()
        exported = self.request_json(base_url, "/api/inventory/export?client=codex&format=json")
        self.assertTrue(exported["ok"])
        self.assertEqual(exported["data"]["format"], "json")
        self.assertIn('"client": "codex"', exported["data"]["content"])

    def test_web_sync_batch_and_discovery_split_endpoints(self):
        skill_root = self.temp_dir / "web-sync"
        shared = self.pool.import_skill_dir(
            make_skill(skill_root, "shared/web-sync", "Web Sync"),
            source_type="github",
            source_locator="repo#web-sync",
            source_version="main",
        )
        self.pool.override_set("codex", shared["conflict_family"], shared["skill_id"])
        self.pool.publish("codex")
        self.codex_config_path.write_text(
            "\n".join(
                [
                    "[mcp_servers.time]",
                    'command = "uvx"',
                    'args = ["mcp-time"]',
                    "enabled = true",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        transient_dir = self.temp_dir / "web-discovery"
        make_skill(transient_dir, "temp-only", "Temp Only")
        self.pool.scan_source_add(str(transient_dir), role="global_source", path_kind="transient", enabled=False, suggested=True)
        self.pool.scan_sources_scan()

        base_url = self.start_web_server()
        template = self.request_json(base_url, "/api/sync/template/codex")
        self.assertTrue(template["ok"])
        self.assertEqual(template["data"]["source_client"], "codex")
        self.assertEqual(template["data"]["skills"]["published_family_count"], 1)

        preview = self.request_json(
            base_url,
            "/api/sync/preview",
            method="POST",
            body={"source_client": "codex", "target_clients": ["hermes"], "include_skills": True, "include_mcp": True},
        )
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["data"]["targets"][0]["client"], "hermes")

        apply_result = self.request_json(
            base_url,
            "/api/sync/apply",
            method="POST",
            body={"source_client": "codex", "target_clients": ["hermes"], "include_skills": True, "include_mcp": True},
        )
        self.assertTrue(apply_result["ok"])
        self.assertTrue((Path(self.clients["hermes"]["target_dir"]) / "web-sync" / "SKILL.md").exists())
        self.assertEqual(self.pool.mcp_list("hermes")["server_count"], 1)

        disabled = self.request_json(
            base_url,
            "/api/batch/disable",
            method="POST",
            body={"clients": ["claude"], "families": [shared["conflict_family"]]},
        )
        self.assertTrue(disabled["ok"])
        inherited = self.request_json(
            base_url,
            "/api/batch/inherit",
            method="POST",
            body={"clients": ["claude"], "families": [shared["conflict_family"]]},
        )
        self.assertTrue(inherited["ok"])

        summary = self.request_json(base_url, "/api/discovery/summary")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["data"]["counts"]["transient_only"], 1)
        details = self.request_json(base_url, "/api/discovery/details?group=transient_only&limit=1")
        self.assertTrue(details["ok"])
        self.assertEqual(details["data"]["total"], 1)
        self.assertEqual(len(details["data"]["items"]), 1)

        shutil.rmtree(str(transient_dir))
        cached_summary = self.request_json(base_url, "/api/discovery/summary")
        self.assertEqual(cached_summary["data"]["counts"]["transient_only"], 1)
        refreshed = self.request_json(base_url, "/api/discovery/refresh", method="POST", body={"summary": True})
        self.assertTrue(refreshed["ok"])
        self.assertEqual(refreshed["data"]["counts"]["transient_only"], 0)

    # -- New tests from audit fixes --------------------------------------------

    def test_cleanup_old_backups_removes_stale(self):
        """cleanup_old_backups() removes backups older than max_age_days."""
        from skillpool_app.core import write_json, datetime, timezone
        backups_dir = self.pool.backups_dir
        backups_dir.mkdir(parents=True, exist_ok=True)
        # Create an old backup (timestamp prefix from 60 days ago)
        old_ts = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=60)).strftime("%Y%m%d%H%M%S")
        old_id = old_ts + "-deadbeef"
        old_dir = backups_dir / old_id / "hermes"
        old_dir.mkdir(parents=True)
        write_json(old_dir / "state.json", {"test": True})
        # Create a recent backup
        recent_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-aabbccdd"
        recent_dir = backups_dir / recent_id / "hermes"
        recent_dir.mkdir(parents=True)
        write_json(recent_dir / "state.json", {"test": True})
        result = self.pool.cleanup_old_backups(max_age_days=30)
        self.assertEqual(result["removed"], 1)
        self.assertFalse(old_dir.exists())
        self.assertTrue(recent_dir.exists())

    def test_cleanup_old_backups_respects_max_count(self):
        """cleanup_old_backups() keeps at most max_count backups."""
        from skillpool_app.core import write_json
        backups_dir = self.pool.backups_dir
        backups_dir.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            d = backups_dir / f"2026010100000{i:01d}-{'a' * 8}" / "hermes"
            d.mkdir(parents=True)
            write_json(d / "state.json", {"i": i})
        result = self.pool.cleanup_old_backups(max_age_days=365, max_count=3)
        self.assertEqual(result["removed"], 2)

    def test_load_json_corrupted_returns_default(self):
        """load_json() returns default on corrupted JSON."""
        from skillpool_app.core import load_json
        bad = self.temp_dir / "corrupted.json"
        bad.write_text("{invalid json!!!", encoding="utf-8")
        result = load_json(bad, {"fallback": True})
        self.assertEqual(result, {"fallback": True})

    def test_parse_frontmatter_nested_yaml(self):
        """parse_frontmatter() handles multi-line dash lists."""
        from skillpool_app.core import parse_frontmatter
        md = "---\ntitle: Test\n\ntags:\n- python\n- go\n- rust\n---\n\nBody text"
        fm, body = parse_frontmatter(md)
        self.assertEqual(fm["title"], "Test")
        self.assertEqual(fm["tags"], ["python", "go", "rust"])
        self.assertIn("Body text", body)

    def test_parse_frontmatter_inline_json_list(self):
        from skillpool_app.core import parse_frontmatter
        md = '---\nitems: ["a", "b", "c"]\n---\ncontent'
        fm, body = parse_frontmatter(md)
        self.assertEqual(fm["items"], ["a", "b", "c"])

    def test_lock_contention_raises(self):
        """Double _acquire_lock() raises RuntimeError."""
        self.pool.init_state()
        self.pool._acquire_lock("test-op")
        try:
            with self.assertRaises(RuntimeError):
                self.pool._acquire_lock("another-op")
        finally:
            self.pool._release_lock()

    def test_hash_directory_streams_large_file(self):
        """hash_directory() handles files without loading entire content into memory."""
        from skillpool_app.core import hash_directory
        test_dir = self.temp_dir / "hash_test"
        test_dir.mkdir()
        # Write a 2MB file
        big_file = test_dir / "big.bin"
        big_file.write_bytes(b"x" * (2 * 1024 * 1024))
        h = hash_directory(test_dir)
        self.assertEqual(len(h), 64)  # SHA-256 hex digest
        # Deterministic
        self.assertEqual(h, hash_directory(test_dir))


if __name__ == "__main__":
    unittest.main()
