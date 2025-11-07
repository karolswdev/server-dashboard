#!/usr/bin/env python3
"""Telegram webhook handler (Flask blueprint)."""

from flask import Blueprint, request, jsonify
import uuid
from pathlib import Path
from typing import Optional, Callable

from .api import TelegramAPI
from jobs.models import Job, JobStatus

telegram_bp = Blueprint('telegram', __name__)

# Global state (set by app initialization)
_telegram_api: Optional[TelegramAPI] = None
_telegram_enabled_func: Optional[Callable[[], bool]] = None
_enqueue_job_func: Optional[Callable[[Job], None]] = None
_storage_root: Optional[Path] = None


def init_webhook(
    telegram_api: TelegramAPI,
    telegram_enabled_func: Callable[[], bool],
    enqueue_job_func: Callable[[Job], None],
    storage_root: Path
):
    """Initialize webhook with dependencies.

    Args:
        telegram_api: Telegram API client
        telegram_enabled_func: Function returning if Telegram is enabled
        enqueue_job_func: Function to enqueue jobs
        storage_root: Storage root path
    """
    global _telegram_api, _telegram_enabled_func, _enqueue_job_func, _storage_root
    _telegram_api = telegram_api
    _telegram_enabled_func = telegram_enabled_func
    _enqueue_job_func = enqueue_job_func
    _storage_root = storage_root


@telegram_bp.route('/telegram/webhook', methods=['POST'])
def webhook():
    """Handle Telegram webhook updates."""
    if not _telegram_api or not _telegram_enabled_func or not _enqueue_job_func:
        return jsonify({"error": "Webhook not initialized"}), 500

    update = request.get_json()
    if not update:
        return jsonify({"ok": True})

    # Extract message
    message = update.get('message')
    if not message:
        return jsonify({"ok": True})

    chat_id = str(message['chat']['id'])
    text = message.get('text', '')

    # Check if Telegram is enabled
    if not _telegram_enabled_func():
        try:
            _telegram_api.send_message(
                chat_id,
                "⚠️ Telegram bot is currently disabled by administrator."
            )
        except Exception:
            pass
        return jsonify({"ok": True})

    # Handle /help command
    if text.startswith('/help'):
        help_text = _get_help_text()
        try:
            _telegram_api.send_message(chat_id, help_text)
        except Exception as e:
            print(f"Failed to send help: {e}")
        return jsonify({"ok": True})

    # Handle /im2vid command
    if text.startswith('/im2vid'):
        return _handle_im2vid(message, chat_id, text)

    return jsonify({"ok": True})


def _handle_im2vid(message: dict, chat_id: str, text: str) -> tuple:
    """Handle /im2vid command.

    Args:
        message: Telegram message dict
        chat_id: Chat ID
        text: Message text

    Returns:
        Flask response tuple
    """
    # Check for image
    photo = message.get('photo')
    if not photo:
        try:
            _telegram_api.send_message(
                chat_id,
                "⚠️ Please attach an image with the `/im2vid` command."
            )
        except Exception:
            pass
        return jsonify({"ok": True}), 200

    # Parse prompt from command
    # Format: /im2vid <prompt>
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        try:
            _telegram_api.send_message(
                chat_id,
                "⚠️ Usage: `/im2vid <your prompt>`\n\nExample: `/im2vid slow camera orbit, cinematic lighting`"
            )
        except Exception:
            pass
        return jsonify({"ok": True}), 200

    prompt = parts[1].strip()

    # Download image
    try:
        # Get largest photo
        largest_photo = max(photo, key=lambda p: p.get('file_size', 0))
        file_info = _telegram_api.get_file(largest_photo['file_id'])
        file_path_tg = file_info['file_path']

        # Create job
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            status=JobStatus.QUEUED,
            created_at=Job.now(),
            updated_at=Job.now(),
            prompt=prompt,
            input_image_url=f"telegram://{file_path_tg}",  # Special marker
            telegram_chat_id=chat_id,
            params={
                "seed": 1,
                "duration_seconds": 5,
                "fps": 24,
                "resolution": "768x768"
            }
        )

        # Download image to job input dir
        input_dir = _storage_root / job_id / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "input.png"

        _telegram_api.download_file(file_path_tg, image_path)

        # Enqueue job
        _enqueue_job_func(job)

        # Notify user
        _telegram_api.send_message(
            chat_id,
            f"✅ Job queued: `{job_id}`\n\n"
            f"Prompt: {prompt}\n\n"
            f"Your video will be sent here when ready!"
        )

    except Exception as e:
        print(f"Error handling /im2vid: {e}")
        try:
            _telegram_api.send_message(
                chat_id,
                f"❌ Failed to queue job: {str(e)}"
            )
        except Exception:
            pass

    return jsonify({"ok": True}), 200


def _get_help_text() -> str:
    """Get help text for bot commands.

    Returns:
        Help text string
    """
    return """🎥 **Image to Video Bot**

**Commands:**

`/im2vid <prompt>` - Generate video from image
  • Attach an image with the command
  • Example: `/im2vid slow camera orbit, cinematic`

`/help` - Show this help message

**Setup:**
For setup instructions, visit the admin dashboard or check the README-telegram.md file.

**Support:**
Contact your administrator for help.
"""
