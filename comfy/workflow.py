#!/usr/bin/env python3
"""ComfyUI workflow management - simple template replacement."""

import json
from pathlib import Path
from typing import Dict, Any, Optional


def load_base(workflow_path: Path) -> str:
    """Load base workflow template as string.

    Args:
        workflow_path: Path to workflow JSON template file

    Returns:
        Workflow template string

    Raises:
        FileNotFoundError: If workflow file doesn't exist
    """
    with open(workflow_path, 'r') as f:
        return f.read()


def apply_overrides(
    base_template: str,
    *,
    prompt: str,
    seed: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    fps: Optional[int] = None,
    resolution: Optional[str] = None,
    input_filename: Optional[str] = None
) -> Dict[str, Any]:
    """Apply parameter overrides to workflow template.

    Args:
        base_template: Base workflow template string
        prompt: Text prompt for generation
        seed: Random seed (optional, not used)
        duration_seconds: Video duration in seconds (optional, not used)
        fps: Frames per second (optional, not used)
        resolution: Resolution string like "768x768" (optional, not used)
        input_filename: Input image filename on ComfyUI server (optional, not used)

    Returns:
        Workflow dictionary ready for ComfyUI
    """
    # Escape quotes for JSON
    escaped_prompt = prompt.replace('"', '\\"').replace('\n', '\\n')

    # IMPORTANT: Replace IMAGE_PLACEHOLDER first, then PLACEHOLDER
    # (otherwise PLACEHOLDER inside IMAGE_PLACEHOLDER gets replaced)
    workflow_str = base_template

    # Replace image filename if provided
    if input_filename:
        workflow_str = workflow_str.replace('IMAGE_PLACEHOLDER', input_filename)

    # Replace prompt
    workflow_str = workflow_str.replace('PLACEHOLDER', escaped_prompt)

    # Parse and return as dict
    return json.loads(workflow_str)


def apply_song_overrides(
    base_template: str,
    *,
    description: str,
    lyrics: str
) -> Dict[str, Any]:
    """Apply song parameters to workflow template.

    Args:
        base_template: Base workflow template string
        description: Song description/tags
        lyrics: Song lyrics

    Returns:
        Workflow dictionary ready for ComfyUI
    """
    # Escape quotes for JSON
    escaped_description = description.replace('"', '\\"').replace('\n', '\\n')
    escaped_lyrics = lyrics.replace('"', '\\"').replace('\n', '\\n')

    # Replace placeholders
    workflow_str = base_template
    workflow_str = workflow_str.replace('DESCRIPTION-OF-SONG', escaped_description)
    workflow_str = workflow_str.replace('LYRICS-OF-SONG', escaped_lyrics)

    # Parse and return as dict
    return json.loads(workflow_str)


def validate_params(
    *,
    prompt: str,
    seed: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    fps: Optional[int] = None,
    resolution: Optional[str] = None
) -> tuple[bool, Optional[str]]:
    """Validate workflow parameters.

    Args:
        prompt: Text prompt
        seed: Random seed
        duration_seconds: Video duration
        fps: Frames per second
        resolution: Resolution string

    Returns:
        (is_valid, error_message)
    """
    # Validate prompt
    if not prompt or len(prompt) > 1000:
        return False, "Prompt must be 1-1000 characters"

    # Validate seed
    if seed is not None and (seed < 0 or seed > 2**32 - 1):
        return False, "Seed must be 0 to 4294967295"

    # Validate duration
    if duration_seconds is not None and not (1 <= duration_seconds <= 30):
        return False, "Duration must be 1-30 seconds"

    # Validate FPS
    if fps is not None and not (1 <= fps <= 60):
        return False, "FPS must be 1-60"

    # Validate resolution
    if resolution is not None:
        allowed = ["512x512", "768x768", "1024x576", "1024x1024", "1280x720"]
        if resolution not in allowed:
            return False, f"Resolution must be one of: {', '.join(allowed)}"

    return True, None
