"""Filesystem watcher for plan-file ingestion."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileMovedEvent
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - optional runtime dependency
    FileSystemEvent = object  # type: ignore[assignment,misc]
    FileMovedEvent = object  # type: ignore[assignment,misc]
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]

from oas_core.plan_file import PlanFile

try:
    from oas_core.schemas.campaign import CampaignSchema
    _SCHEMAS_AVAILABLE = True
except ImportError:
    _SCHEMAS_AVAILABLE = False

__all__ = ["PlanWatcher", "WATCHDOG_AVAILABLE"]

WATCHDOG_AVAILABLE = Observer is not None


@dataclass(frozen=True)
class _ObservedState:
    fingerprint: tuple[int, int]
    first_seen_at: float


class PlanWatcher:
    """Detect stable markdown plan files and load them into campaigns."""

    def __init__(
        self,
        plan_dir: str | Path,
        *,
        pattern: str = "*.md",
        stable_seconds: float = 0.5,
    ) -> None:
        self.plan_dir = Path(plan_dir).expanduser().resolve()
        self.pattern = pattern
        self.stable_seconds = stable_seconds
        self._observed: dict[Path, _ObservedState] = {}
        self._claimed: set[Path] = set()
        self._dirty_paths: set[Path] = set()

    def scan(self, *, now_monotonic: float | None = None) -> list[Path]:
        """Return newly stable plan files that are ready to be processed."""
        now = time.monotonic() if now_monotonic is None else now_monotonic
        self.plan_dir.mkdir(parents=True, exist_ok=True)

        ready: list[Path] = []
        seen: set[Path] = set()
        for path in self._iter_candidates():
            seen.add(path)
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue

            fingerprint = (stat.st_mtime_ns, stat.st_size)
            observed = self._observed.get(path)
            if observed is None or observed.fingerprint != fingerprint:
                self._observed[path] = _ObservedState(
                    fingerprint=fingerprint,
                    first_seen_at=now,
                )
                self._claimed.discard(path)
                continue

            if path in self._claimed:
                continue
            if now - observed.first_seen_at < self.stable_seconds:
                continue

            ready.append(path)
            self._claimed.add(path)

        for path in list(self._observed):
            if path not in seen and not path.exists():
                self._observed.pop(path, None)
                self._claimed.discard(path)

        self._dirty_paths.intersection_update(seen)
        return sorted(ready)

    def load_ready_plans(self, *, now_monotonic: float | None = None) -> list[PlanFile]:
        """Load newly stable plan files into parsed plan objects."""
        return [PlanFile.from_path(path) for path in self.scan(now_monotonic=now_monotonic)]

    def load_ready_campaigns(
        self,
        *,
        now_monotonic: float | None = None,
    ) -> list["CampaignSchema"]:
        """Load newly stable plan files into campaign schemas.

        Requires oas_core.schemas.campaign — raises ImportError if unavailable.
        """
        if not _SCHEMAS_AVAILABLE:
            raise ImportError("oas_core.schemas.campaign not available")
        return [plan.to_campaign() for plan in self.load_ready_plans(now_monotonic=now_monotonic)]

    def mark_dirty(self, path: str | Path) -> None:
        """Notify the watcher that a plan file changed and must re-settle."""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.plan_dir / candidate
        candidate = candidate.resolve()
        if not self._is_plan_candidate(candidate):
            return
        self._dirty_paths.add(candidate)
        self._observed.pop(candidate, None)
        self._claimed.discard(candidate)

    def mark_deleted(self, path: str | Path) -> None:
        """Drop watcher state for a deleted file."""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.plan_dir / candidate
        candidate = candidate.resolve()
        self._dirty_paths.discard(candidate)
        self._observed.pop(candidate, None)
        self._claimed.discard(candidate)

    def build_observer(self) -> Observer:
        """Create a watchdog observer wired to this watcher."""
        if not WATCHDOG_AVAILABLE:
            raise RuntimeError("watchdog is not available")
        observer = Observer()
        observer.schedule(_PlanEventHandler(self), str(self.plan_dir), recursive=False)
        return observer

    def _iter_candidates(self) -> list[Path]:
        if self._dirty_paths:
            candidates = [path for path in self._dirty_paths if self._is_plan_candidate(path)]
            self._dirty_paths.clear()
            return sorted(candidates)

        return sorted(
            path.resolve()
            for path in self.plan_dir.glob(self.pattern)
            if self._is_plan_candidate(path)
        )

    @staticmethod
    def _is_plan_candidate(path: Path) -> bool:
        name = path.name
        if not path.exists() or not path.is_file():
            return False
        if path.suffix.lower() != ".md":
            return False
        if name.startswith("."):
            return False
        if name.endswith(("~", ".tmp", ".part", ".swp", ".swx")):
            return False
        return True


class _PlanEventHandler(FileSystemEventHandler):  # pragma: no cover - thin watchdog shim
    def __init__(self, watcher: PlanWatcher) -> None:
        super().__init__()
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if not getattr(event, "is_directory", False):
            self._watcher.mark_dirty(getattr(event, "src_path"))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not getattr(event, "is_directory", False):
            self._watcher.mark_dirty(getattr(event, "src_path"))

    def on_moved(self, event: FileMovedEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        self._watcher.mark_deleted(getattr(event, "src_path"))
        self._watcher.mark_dirty(getattr(event, "dest_path"))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not getattr(event, "is_directory", False):
            self._watcher.mark_deleted(getattr(event, "src_path"))
