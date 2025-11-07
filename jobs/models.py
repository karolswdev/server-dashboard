#!/usr/bin/env python3
"""Job data models and enums."""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List
from datetime import datetime


class JobStatus(str, Enum):
    """Job status states."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELED = "canceled"


@dataclass
class Job:
    """Job data model."""
    id: str
    status: JobStatus
    created_at: str
    updated_at: str
    prompt: str
    input_image_url: Optional[str] = None

    # ComfyUI specific
    prompt_id: Optional[str] = None

    # Progress tracking
    progress: int = 0  # 0-100

    # Results
    files: List[str] = field(default_factory=list)
    error: Optional[str] = None

    # Delivery
    telegram_chat_id: Optional[str] = None
    webhook_url: Optional[str] = None

    # Parameters
    params: dict = field(default_factory=dict)

    def to_dict(self):
        """Convert to dictionary."""
        d = asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict):
        """Create from dictionary."""
        d = d.copy()
        if 'status' in d and isinstance(d['status'], str):
            d['status'] = JobStatus(d['status'])
        return cls(**d)

    @staticmethod
    def now():
        """Get current ISO timestamp."""
        return datetime.utcnow().isoformat() + 'Z'
