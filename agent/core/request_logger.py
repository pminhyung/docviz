"""
Silent Request Logger for agent

Automatically logs all API requests and responses to GCS.
This logging is transparent to the client (silent).

Log location:
    gs://mhpark_bucket/poc/reasoning_out_log/{yymm}/{session_id or request_id}/
    ├── request_payload.json     # Client's request payload
    ├── custom_tools.py          # Copy of custom tools file (if provided)
    └── output.jsonl             # Training sample output
"""
import os
import json
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import uuid


# GCS configuration
GCS_LOG_BUCKET = "gs://mhpark_bucket/poc/reasoning_out_log"
LOCAL_LOG_DIR = "/tmp/docviz_agent_logs"


class RequestLogger:
    """
    Silent request/response logger.

    Logs all API requests to GCS in the background without
    affecting the main request processing.
    """

    def __init__(self, local_dir: str = LOCAL_LOG_DIR, gcs_bucket: str = GCS_LOG_BUCKET):
        """
        Initialize the request logger.

        Args:
            local_dir: Local directory for temporary log files
            gcs_bucket: GCS bucket path for uploads
        """
        self._local_dir = Path(local_dir)
        self._gcs_bucket = gcs_bucket
        self._lock = threading.Lock()

        # Ensure local directory exists
        self._local_dir.mkdir(parents=True, exist_ok=True)

    def log_request(
        self,
        request_payload: Dict[str, Any],
        custom_tools_path: Optional[str],
        train_sample: Dict[str, Any],
        session_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Log a request and its output to GCS.

        This method is non-blocking and will not raise exceptions
        that affect the main request processing.

        Args:
            request_payload: The original client request payload
            custom_tools_path: Path to the custom tools .py file (if provided)
            train_sample: The generated training sample (JSONL content)
            session_id: Session ID for batch processing
            request_id: Unique request ID (auto-generated if not provided)

        Returns:
            GCS path where logs were uploaded, or None on failure
        """
        try:
            # Determine directory name
            yymm = datetime.now().strftime("%y%m")
            dir_name = session_id if session_id else (request_id or f"req_{uuid.uuid4().hex[:8]}")

            # Create local directory
            local_dir = self._local_dir / yymm / dir_name
            local_dir.mkdir(parents=True, exist_ok=True)

            # 1. Save request payload (excluding sensitive fields)
            self._save_payload(local_dir, request_payload)

            # 2. Copy custom tools file if provided
            if custom_tools_path:
                self._copy_tools_file(local_dir, custom_tools_path)

            # 3. Append training sample to JSONL
            self._append_jsonl(local_dir, train_sample)

            # 4. Upload to GCS in background
            gcs_path = f"{self._gcs_bucket}/{yymm}/{dir_name}/"
            self._upload_to_gcs_async(str(local_dir), gcs_path)

            return gcs_path

        except Exception as e:
            # Silent fail - log to stderr but don't raise
            import sys
            print(f"[RequestLogger] Warning: Failed to log request: {e}", file=sys.stderr)
            return None

    def _save_payload(self, local_dir: Path, payload: Dict[str, Any]) -> None:
        """Save request payload to JSON file."""
        payload_path = local_dir / "request_payload.json"

        # Filter out sensitive fields
        sensitive_fields = {"api_key", "password", "secret", "token", "auth"}
        safe_payload = {
            k: v for k, v in payload.items()
            if not any(s in k.lower() for s in sensitive_fields)
        }

        # Add metadata
        safe_payload["_logged_at"] = datetime.now().isoformat()

        with self._lock:
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump(safe_payload, f, ensure_ascii=False, indent=2)

    def _copy_tools_file(self, local_dir: Path, tools_path: str) -> None:
        """Copy custom tools .py file to log directory."""
        if not os.path.exists(tools_path):
            return

        dest_path = local_dir / "custom_tools.py"

        try:
            shutil.copy2(tools_path, dest_path)
        except Exception:
            # If copy fails, try to read and write content
            try:
                with open(tools_path, "r", encoding="utf-8") as src:
                    content = src.read()
                with open(dest_path, "w", encoding="utf-8") as dst:
                    dst.write(content)
            except Exception:
                pass  # Silent fail

    def _append_jsonl(self, local_dir: Path, train_sample: Dict[str, Any]) -> None:
        """Append training sample to JSONL file."""
        jsonl_path = local_dir / "output.jsonl"

        with self._lock:
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(train_sample, ensure_ascii=False) + "\n")

    def _upload_to_gcs_async(self, local_dir: str, gcs_path: str) -> None:
        """
        Upload files to GCS in background.

        Uses subprocess.Popen to run gsutil in background,
        so it doesn't block the main thread.
        """
        def do_upload():
            try:
                cmd = ["gsutil", "-m", "cp", "-r", f"{local_dir}/*", gcs_path]
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60  # 1 minute timeout
                )
            except Exception:
                pass  # Silent fail

        # Run in background thread
        thread = threading.Thread(target=do_upload, daemon=True)
        thread.start()

    def cleanup_old_logs(self, days_old: int = 7) -> int:
        """
        Clean up local log files older than specified days.

        Args:
            days_old: Delete logs older than this many days

        Returns:
            Number of directories cleaned up
        """
        import time

        cleaned = 0
        cutoff = time.time() - (days_old * 24 * 60 * 60)

        try:
            for yymm_dir in self._local_dir.iterdir():
                if not yymm_dir.is_dir():
                    continue

                for log_dir in yymm_dir.iterdir():
                    if not log_dir.is_dir():
                        continue

                    # Check modification time
                    mtime = log_dir.stat().st_mtime
                    if mtime < cutoff:
                        shutil.rmtree(log_dir, ignore_errors=True)
                        cleaned += 1

                # Remove empty yymm directories
                if yymm_dir.exists() and not any(yymm_dir.iterdir()):
                    yymm_dir.rmdir()

        except Exception:
            pass

        return cleaned


# Singleton instance
_request_logger: Optional[RequestLogger] = None
_logger_lock = threading.Lock()


def get_request_logger() -> RequestLogger:
    """
    Get the singleton RequestLogger instance.

    Returns:
        The global RequestLogger instance
    """
    global _request_logger

    if _request_logger is None:
        with _logger_lock:
            if _request_logger is None:
                _request_logger = RequestLogger()

    return _request_logger


def log_request(
    request_payload: Dict[str, Any],
    custom_tools_path: Optional[str],
    train_sample: Dict[str, Any],
    session_id: Optional[str] = None,
    request_id: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function to log a request.

    See RequestLogger.log_request for details.
    """
    logger = get_request_logger()
    return logger.log_request(
        request_payload=request_payload,
        custom_tools_path=custom_tools_path,
        train_sample=train_sample,
        session_id=session_id,
        request_id=request_id
    )
