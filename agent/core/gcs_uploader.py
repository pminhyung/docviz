"""
GCS Uploader

Uploads training JSONL files to Google Cloud Storage.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime


# Default GCS bucket for training data
GCS_BUCKET = "gs://mhpark_bucket/reasoning_api_output"


class GCSUploadError(Exception):
    """Raised when GCS upload fails"""
    pass


def upload_to_gcs(
    local_path: str,
    session_id: str,
    bucket: Optional[str] = None,
    filename: str = "train.jsonl"
) -> str:
    """
    Upload a local file to GCS.

    Uses gsutil for efficient upload with parallel transfer.

    Args:
        local_path: Path to the local file
        session_id: Session identifier (used in GCS path)
        bucket: GCS bucket path (default: GCS_BUCKET)
        filename: Target filename in GCS (default: train.jsonl)

    Returns:
        Full GCS path (gs://...)

    Raises:
        FileNotFoundError: If local_path doesn't exist
        GCSUploadError: If upload fails
    """
    local_file = Path(local_path)
    if not local_file.exists():
        raise FileNotFoundError(f"Local file not found: {local_path}")

    bucket = bucket or GCS_BUCKET

    # Build GCS path with timestamp for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    gcs_path = f"{bucket}/{session_id}/{timestamp}_{filename}"

    # Run gsutil upload
    cmd = ["gsutil", "-m", "cp", str(local_file), gcs_path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise GCSUploadError(f"gsutil upload failed: {error_msg}")

        return gcs_path

    except subprocess.TimeoutExpired:
        raise GCSUploadError(f"Upload timed out after 5 minutes: {local_path}")

    except FileNotFoundError:
        raise GCSUploadError(
            "gsutil not found. Please install Google Cloud SDK: "
            "https://cloud.google.com/sdk/docs/install"
        )

    except Exception as e:
        raise GCSUploadError(f"Upload failed: {e}") from e


def check_gcs_available() -> bool:
    """
    Check if GCS (gsutil) is available and configured.

    Returns:
        True if gsutil is available and authenticated
    """
    try:
        result = subprocess.run(
            ["gsutil", "version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0

    except Exception:
        return False


def get_gcs_url(gcs_path: str) -> str:
    """
    Convert gs:// path to HTTPS URL.

    Args:
        gcs_path: GCS path (gs://bucket/path/file)

    Returns:
        HTTPS URL for browser access
    """
    if not gcs_path.startswith("gs://"):
        return gcs_path

    # gs://bucket/path -> https://storage.googleapis.com/bucket/path
    path = gcs_path[5:]  # Remove "gs://"
    return f"https://storage.googleapis.com/{path}"


def list_gcs_files(gcs_prefix: str) -> list:
    """
    List files in GCS under a prefix.

    Args:
        gcs_prefix: GCS path prefix (gs://bucket/prefix)

    Returns:
        List of file paths

    Raises:
        GCSUploadError: If listing fails
    """
    cmd = ["gsutil", "ls", gcs_prefix]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            if "No URLs matched" in result.stderr:
                return []
            raise GCSUploadError(f"gsutil ls failed: {result.stderr}")

        files = [
            line.strip()
            for line in result.stdout.strip().split("\n")
            if line.strip()
        ]
        return files

    except subprocess.TimeoutExpired:
        raise GCSUploadError("Listing timed out")

    except FileNotFoundError:
        raise GCSUploadError("gsutil not found")

    except Exception as e:
        raise GCSUploadError(f"Listing failed: {e}") from e
