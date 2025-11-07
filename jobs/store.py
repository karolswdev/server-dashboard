#!/usr/bin/env python3
"""File-backed job storage."""

import json
import os
from pathlib import Path
from typing import Optional
from .models import Job, JobStatus


class JobStore:
    """File-backed job metadata storage."""

    def __init__(self, storage_root: str):
        """Initialize job store.

        Args:
            storage_root: Base directory for job data (e.g., ./data)
        """
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def _job_dir(self, job_id: str) -> Path:
        """Get job directory path."""
        return self.storage_root / job_id

    def _meta_path(self, job_id: str) -> Path:
        """Get job metadata file path."""
        return self._job_dir(job_id) / "meta.json"

    def save(self, job: Job) -> None:
        """Save job metadata to disk.

        Args:
            job: Job instance to save
        """
        job_dir = self._job_dir(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)

        # Create input/output subdirs
        (job_dir / "input").mkdir(exist_ok=True)
        (job_dir / "output").mkdir(exist_ok=True)

        meta_path = self._meta_path(job.id)
        with open(meta_path, 'w') as f:
            json.dump(job.to_dict(), f, indent=2)

    def load(self, job_id: str) -> Optional[Job]:
        """Load job metadata from disk.

        Args:
            job_id: Job ID to load

        Returns:
            Job instance or None if not found
        """
        meta_path = self._meta_path(job_id)
        if not meta_path.exists():
            return None

        with open(meta_path, 'r') as f:
            data = json.load(f)

        return Job.from_dict(data)

    def update(self, job_id: str, **patch) -> Optional[Job]:
        """Update job fields idempotently.

        Args:
            job_id: Job ID to update
            **patch: Fields to update

        Returns:
            Updated Job instance or None if not found
        """
        job = self.load(job_id)
        if job is None:
            return None

        # Update fields
        for key, value in patch.items():
            if hasattr(job, key):
                setattr(job, key, value)

        # Always update timestamp
        job.updated_at = Job.now()

        self.save(job)
        return job

    def get_input_dir(self, job_id: str) -> Path:
        """Get input directory for job."""
        return self._job_dir(job_id) / "input"

    def get_output_dir(self, job_id: str) -> Path:
        """Get output directory for job."""
        return self._job_dir(job_id) / "output"

    def exists(self, job_id: str) -> bool:
        """Check if job exists."""
        return self._meta_path(job_id).exists()
