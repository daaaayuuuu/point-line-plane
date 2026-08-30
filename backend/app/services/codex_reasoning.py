from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodexReasoningProgress:
    status: str
    summary: str


@dataclass(slots=True)
class _ProgressState:
    owner_id: str
    project_id: str
    summary: str
    status: str
    updated_at: float


class CodexReasoningProgressStore:
    """Short-lived, process-local progress for an active Codex requirement turn."""

    def __init__(self, *, ttl_seconds: float = 900, max_characters: int = 20_000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_characters = max_characters
        self._lock = threading.Lock()
        self._entries: dict[str, _ProgressState] = {}

    def start(self, progress_id: str, *, owner_id: str, project_id: str) -> None:
        with self._lock:
            self._prune_locked()
            self._entries[progress_id] = _ProgressState(
                owner_id=owner_id,
                project_id=project_id,
                summary="",
                status="running",
                updated_at=time.monotonic(),
            )

    def append(self, progress_id: str, delta: str) -> None:
        if not delta:
            return
        with self._lock:
            state = self._entries.get(progress_id)
            if state is None or state.status != "running":
                return
            state.summary = f"{state.summary}{delta}"[-self.max_characters :]
            state.updated_at = time.monotonic()

    def finish(self, progress_id: str, *, status: str) -> None:
        with self._lock:
            state = self._entries.get(progress_id)
            if state is None:
                return
            state.status = status
            state.updated_at = time.monotonic()

    def read(
        self,
        progress_id: str,
        *,
        owner_id: str,
        project_id: str,
    ) -> CodexReasoningProgress | None:
        with self._lock:
            self._prune_locked()
            state = self._entries.get(progress_id)
            if state is None or state.owner_id != owner_id or state.project_id != project_id:
                return None
            return CodexReasoningProgress(status=state.status, summary=state.summary)

    def _prune_locked(self) -> None:
        cutoff = time.monotonic() - self.ttl_seconds
        expired = [key for key, state in self._entries.items() if state.updated_at < cutoff]
        for key in expired:
            self._entries.pop(key, None)
