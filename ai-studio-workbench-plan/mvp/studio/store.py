"""File-backed store for runs, assets, cache, usage, and event logs.

The skeleton deliberately uses the filesystem instead of a database so the demo
runs with zero infrastructure. Production can swap this class for Postgres + S3
while keeping the same method signatures.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.runs = self.root / "runs"
        self.cache = self.root / "cache"
        self.logs = self.root / "logs"
        for directory in (self.runs, self.cache, self.logs):
            directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------
    def new_run_id(self, prefix: str = "run") -> str:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return f"{prefix}-{stamp}-{secrets.token_hex(3)}"

    def run_dir(self, run_id: str) -> Path:
        path = self.runs / run_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "assets").mkdir(exist_ok=True)
        return path

    def asset_dir(self, run_id: str) -> Path:
        path = self.run_dir(run_id) / "assets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Atomic writes
    # ------------------------------------------------------------------
    def save_text(self, path: str | Path, content: str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".studio-", text=True)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
        return path

    def save_json(self, path: str | Path, data: Any) -> Path:
        return self.save_text(path, json.dumps(data, ensure_ascii=False, indent=2))

    def append_jsonl(self, path: str | Path, record: dict[str, Any]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------
    def asset_path(self, run_id: str, name: str, suffix: str = "") -> Path:
        safe_name = "".join(c if c.isalnum() or c in "-_." else "-" for c in name)[:80]
        if suffix and not safe_name.endswith(suffix):
            safe_name += suffix
        return self.asset_dir(run_id) / safe_name

    def copy_asset(self, source: str | Path, run_id: str, name: str) -> Path:
        source = Path(source)
        target = self.asset_path(run_id, name, source.suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def cache_path(self, key: str) -> Path:
        return self.cache / key[:2] / key

    def cache_lookup(self, key: str) -> dict[str, Any] | None:
        meta_path = self.cache_path(key) / "meta.json"
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def cache_store(self, key: str, result: dict[str, Any], asset_path: Path) -> None:
        target = self.cache_path(key)
        target.mkdir(parents=True, exist_ok=True)
        if asset_path.exists():
            shutil.copy2(asset_path, target / asset_path.name)
        meta = dict(result)
        meta["cached_filename"] = asset_path.name
        self.save_json(target / "meta.json", meta)

    def cache_copy(self, key: str, run_id: str) -> Path | None:
        meta = self.cache_lookup(key)
        if not meta:
            return None
        filename = meta.get("cached_filename")
        if not filename:
            return None
        source = self.cache_path(key) / filename
        if not source.exists():
            return None
        return self.copy_asset(source, run_id, filename)

    # ------------------------------------------------------------------
    # Usage / events
    # ------------------------------------------------------------------
    def usage_path(self) -> Path:
        return self.root / "usage.jsonl"

    def record_usage(self, record: dict[str, Any]) -> None:
        self.append_jsonl(self.usage_path(), record)

    def log_event(self, run_id: str, event: dict[str, Any]) -> None:
        self.append_jsonl(self.logs / f"{run_id}.jsonl", event)

    def run_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self.logs / f"{run_id}.jsonl"
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
        return records
