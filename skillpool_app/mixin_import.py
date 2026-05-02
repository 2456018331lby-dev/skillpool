from __future__ import annotations

# Auto-extracted from core.py - do not edit directly.

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import json
import os
import socket
import time
import urllib.parse
import urllib.request
import zipfile

from skillpool_app.core import (
    ensure_clean_directory,
    read_text,
)

class MixinImport:
    """Mixin: _github_request, _parse_github_locator, import_github, import_zip, import_detect_github..."""

    def _github_request(url: str, dest: Path, timeout: int = 30, max_retries: int = 3) -> None:
        """Download from a GitHub URL with auth token, timeout, and retry logic."""
        headers = {"User-Agent": "skillpool/0.1"}
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("SKILLPOOL_GITHUB_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token

        backoff = 1.0
        last_exc = None
        for attempt in range(max_retries):
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = response.read()
                with dest.open("wb") as fh:
                    fh.write(data)
                return
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else backoff
                    time.sleep(wait)
                    backoff = min(backoff * 2, 8.0)
                    continue
                if exc.code in SkillPool._GITHUB_TRANSIENT_CODES:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 8.0)
                    continue
                raise
            except (urllib.error.URLError, socket.timeout, OSError) as exc:
                last_exc = exc
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
                continue
        raise last_exc

    def _parse_github_locator(self, locator: str, ref: Optional[str], subdir: Optional[str]) -> Tuple[str, str, Optional[str], str]:
        locator = locator.strip()
        parsed = urllib.parse.urlparse(locator)
        if parsed.scheme and parsed.netloc:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) < 2:
                raise ValueError("GitHub URL must include owner/repo")
            owner, repo = parts[0], parts[1].replace(".git", "")
            tree_ref = ref
            tree_subdir = subdir
            if len(parts) >= 4 and parts[2] == "tree":
                tree_ref = tree_ref or parts[3]
                if len(parts) > 4 and not tree_subdir:
                    tree_subdir = "/".join(parts[4:])
        else:
            parts = [part for part in locator.split("/") if part]
            if len(parts) < 2:
                raise ValueError("GitHub locator must look like owner/repo")
            owner, repo = parts[0], parts[1].replace(".git", "")
            tree_ref = ref
            tree_subdir = subdir
        display = "https://github.com/{}/{}".format(owner, repo)
        return owner, repo, tree_ref, tree_subdir or ""

    def import_github(self, locator: str, ref: Optional[str] = None, subdir: Optional[str] = None) -> Dict[str, List[str]]:
        owner, repo, resolved_ref, resolved_subdir = self._parse_github_locator(locator, ref, subdir)
        archive_url = "https://api.github.com/repos/{}/{}/zipball".format(owner, repo)
        if resolved_ref:
            archive_url += "/{}".format(urllib.parse.quote(resolved_ref))
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        cache_zip = self.cache_dir / "github-{}-{}-{}.zip".format(owner, repo, timestamp)
        self._github_request(archive_url, cache_zip)
        extracted = self._extract_archive(cache_zip, "github-{}-{}".format(owner, repo))
        scan_root = extracted
        if resolved_subdir:
            scan_root = extracted / Path(resolved_subdir)
            if not scan_root.exists():
                raise ValueError("Subdir '{}' was not found in archive".format(resolved_subdir))
        imported = self._import_from_directory(
            scan_root,
            source_type="github",
            source_locator="https://github.com/{}/{}".format(owner, repo),
            source_version=resolved_ref or "default",
        )
        self.generate_reports()
        return imported

    def import_zip(self, zip_path: Path) -> Dict[str, List[str]]:
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise ValueError("ZIP file not found: {}".format(zip_path))
        extracted = self._extract_archive(zip_path, zip_path.stem)
        imported = self._import_from_directory(
            extracted,
            source_type="zip",
            source_locator=str(zip_path.resolve()),
            source_version="local",
        )
        self.generate_reports()
        return imported

    def import_detect_github(self, locator: str, ref: Optional[str] = None, subdir: Optional[str] = None) -> Dict[str, object]:
        owner, repo, resolved_ref, resolved_subdir = self._parse_github_locator(locator, ref, subdir)
        archive_url = "https://api.github.com/repos/{}/{}/zipball".format(owner, repo)
        if resolved_ref:
            archive_url += "/{}".format(urllib.parse.quote(resolved_ref))
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        cache_zip = self.cache_dir / "detect-{}-{}-{}.zip".format(owner, repo, timestamp)
        self._github_request(archive_url, cache_zip)
        extracted = self._extract_archive(cache_zip, "detect-{}-{}".format(owner, repo))
        scan_root = extracted
        if resolved_subdir:
            scan_root = extracted / Path(resolved_subdir)
            if not scan_root.exists():
                raise ValueError("Subdir '{}' was not found in archive".format(resolved_subdir))
        skills = self.discover_skills(scan_root)
        relative_paths = [str(path.relative_to(scan_root)).replace("\\", "/") for path in skills]
        template_markers = {"template", "templates", "example", "examples", "sample", "samples"}
        if not skills:
            detected_type = "invalid"
            status = "invalid"
        elif any(any(part.lower() in template_markers for part in Path(path).parts) for path in relative_paths):
            detected_type = "template"
            status = "ok"
        elif len(skills) == 1:
            detected_type = "single_skill"
            status = "ok"
        else:
            detected_type = "multi_skill"
            status = "ok"
        return {
            "source_type": "github",
            "repo": "{}/{}".format(owner, repo),
            "ref": resolved_ref or "default",
            "subdir": resolved_subdir,
            "status": status,
            "detected_type": detected_type,
            "skill_count": len(skills),
            "skills": relative_paths,
            "scan_root": str(scan_root),
        }

    def import_batch(self, manifest_path: Path) -> Dict[str, object]:
        manifest_path = Path(manifest_path)
        if not manifest_path.exists():
            raise ValueError("Batch manifest not found: {}".format(manifest_path))
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("Batch manifest must be a list or an object with 'items'")
        results = []
        imported_skill_ids = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError("Batch manifest item {} must be an object".format(index))
            source_type = item.get("type")
            if source_type == "github":
                result = self.import_github(
                    str(item.get("repo_or_url", "")),
                    ref=item.get("ref") or None,
                    subdir=item.get("subdir") or None,
                )
            elif source_type == "zip":
                result = self.import_zip(Path(str(item.get("zip_path", ""))))
            else:
                raise ValueError("Unsupported batch import type: {}".format(source_type))
            results.append({"index": index, "type": source_type, "result": result})
            imported_skill_ids.extend(result.get("imported_skill_ids", []))
        return {"manifest_path": str(manifest_path), "results": results, "imported_skill_ids": imported_skill_ids}

    def _extract_archive(self, archive_path: Path, prefix: str) -> Path:
        destination = self.cache_dir / "{}-{}".format(prefix, datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
        ensure_clean_directory(destination)
        with zipfile.ZipFile(str(archive_path), "r") as archive:
            archive.extractall(str(destination))
        child_dirs = [path for path in destination.iterdir() if path.is_dir()]
        if len(child_dirs) == 1:
            return child_dirs[0]
        return destination

    def _import_from_directory(self, directory: Path, *, source_type: str, source_locator: str, source_version: str) -> Dict[str, List[str]]:
        skills = self.discover_skills(directory)
        if not skills:
            raise ValueError("No SKILL.md files found under {}".format(directory))
        imported = []
        for skill_dir in skills:
            imported.append(
                self.import_skill_dir(
                    skill_dir,
                    source_type=source_type,
                    source_locator="{}#{}".format(source_locator, skill_dir.relative_to(directory)),
                    source_version=source_version,
                )["skill_id"]
            )
        return {"imported_skill_ids": imported}



