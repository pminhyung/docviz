"""
Session Manager

Manages session-based JSONL accumulation for batch processing.
Sessions allow multiple requests to accumulate training samples
before finalizing and uploading to GCS.
"""

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


# Default session storage directory
SESSION_DIR = "/tmp/docviz_agent_sessions"


class SessionNotFoundError(Exception):
    """Raised when a session is not found"""
    pass


class SessionManager:
    """
    Manages session-based JSONL accumulation.

    Sessions are stored in:
        {SESSION_DIR}/{session_id}/train.jsonl

    Usage:
        manager = SessionManager()
        count = manager.append_sample("session_123", train_sample)
        jsonl_path = manager.finalize("session_123")
        manager.cleanup("session_123")
    """

    _instance: Optional["SessionManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SessionManager":
        """Singleton pattern for global session management"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize session manager (only once)"""
        if getattr(self, "_initialized", False):
            return

        self._sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> metadata
        self._session_locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._session_dir = Path(SESSION_DIR)
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def _get_session_lock(self, session_id: str) -> threading.Lock:
        """Get or create a lock for a session"""
        with self._global_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]

    def _get_session_path(self, session_id: str) -> Path:
        """Get the directory path for a session"""
        return self._session_dir / session_id

    def _get_jsonl_path(self, session_id: str) -> Path:
        """Get the JSONL file path for a session"""
        return self._get_session_path(session_id) / "train.jsonl"

    def append_sample(
        self,
        session_id: str,
        train_sample: Dict[str, Any]
    ) -> int:
        """
        Append a training sample to a session.

        Creates the session if it doesn't exist.

        Args:
            session_id: Session identifier
            train_sample: Training sample dictionary to append

        Returns:
            Current sample count in the session
        """
        lock = self._get_session_lock(session_id)

        with lock:
            # Create session directory if needed
            session_path = self._get_session_path(session_id)
            session_path.mkdir(parents=True, exist_ok=True)

            # Append to JSONL file
            jsonl_path = self._get_jsonl_path(session_id)
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(train_sample, ensure_ascii=False) + "\n")

            # Update metadata
            with self._global_lock:
                if session_id not in self._sessions:
                    self._sessions[session_id] = {
                        "count": 0,
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat(),
                    }

                self._sessions[session_id]["count"] += 1
                self._sessions[session_id]["updated_at"] = datetime.now().isoformat()

                return self._sessions[session_id]["count"]

    def get_sample_count(self, session_id: str) -> int:
        """
        Get the current sample count for a session.

        Args:
            session_id: Session identifier

        Returns:
            Number of samples in the session, or 0 if session doesn't exist
        """
        with self._global_lock:
            if session_id in self._sessions:
                return self._sessions[session_id]["count"]

            # Check if session exists on disk but not in memory
            jsonl_path = self._get_jsonl_path(session_id)
            if jsonl_path.exists():
                # Count lines in file
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    count = sum(1 for _ in f)
                self._sessions[session_id] = {
                    "count": count,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
                return count

            return 0

    def finalize(self, session_id: str) -> str:
        """
        Finalize a session and return the local JSONL path.

        Args:
            session_id: Session identifier

        Returns:
            Path to the JSONL file

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        jsonl_path = self._get_jsonl_path(session_id)

        if not jsonl_path.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")

        return str(jsonl_path)

    def cleanup(self, session_id: str) -> bool:
        """
        Clean up session data.

        Removes session directory and all files.

        Args:
            session_id: Session identifier

        Returns:
            True if session was cleaned up, False if it didn't exist
        """
        lock = self._get_session_lock(session_id)

        with lock:
            session_path = self._get_session_path(session_id)

            if session_path.exists():
                shutil.rmtree(session_path)

            with self._global_lock:
                self._sessions.pop(session_id, None)
                self._session_locks.pop(session_id, None)

                return True

        return False

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session metadata.

        Args:
            session_id: Session identifier

        Returns:
            Session metadata dict or None if session doesn't exist
        """
        with self._global_lock:
            if session_id in self._sessions:
                return self._sessions[session_id].copy()

            # Check disk
            jsonl_path = self._get_jsonl_path(session_id)
            if jsonl_path.exists():
                return {
                    "count": self.get_sample_count(session_id),
                    "path": str(jsonl_path),
                }

            return None

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        List all active sessions.

        Returns:
            Dictionary of session_id -> metadata
        """
        with self._global_lock:
            # Also check for sessions on disk not in memory
            if self._session_dir.exists():
                for session_path in self._session_dir.iterdir():
                    if session_path.is_dir():
                        session_id = session_path.name
                        if session_id not in self._sessions:
                            self.get_sample_count(session_id)  # This loads it

            return {
                session_id: info.copy()
                for session_id, info in self._sessions.items()
            }

    def session_exists(self, session_id: str) -> bool:
        """
        Check if a session exists.

        Args:
            session_id: Session identifier

        Returns:
            True if session exists
        """
        with self._global_lock:
            if session_id in self._sessions:
                return True

            jsonl_path = self._get_jsonl_path(session_id)
            return jsonl_path.exists()


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """
    Get the global SessionManager instance.

    Returns:
        SessionManager singleton instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
