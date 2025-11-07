#!/usr/bin/env python3
"""Job queue wrapper."""

import queue
from typing import Optional
from .models import Job


class JobQueue:
    """Thread-safe job queue wrapper."""

    def __init__(self):
        """Initialize job queue."""
        self._queue = queue.Queue()

    def enqueue(self, job: Job) -> None:
        """Add job to queue.

        Args:
            job: Job to enqueue
        """
        self._queue.put(job)

    def dequeue(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Remove and return job from queue (blocking).

        Args:
            timeout: Timeout in seconds (None = block forever)

        Returns:
            Job instance or None if timeout
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    def empty(self) -> bool:
        """Check if queue is empty."""
        return self._queue.empty()
