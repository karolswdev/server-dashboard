#!/usr/bin/env python3
"""Telegram polling mode (alternative to webhook)."""

import threading
import time
from typing import Optional, Callable
from pathlib import Path

from .api import TelegramAPI
from jobs.models import Job, JobStatus
from jobs.store import JobStore
from jobs.queue import JobQueue
from ollama_helper import OllamaHelper


class TelegramPoller:
    """Polls Telegram for updates instead of using webhooks."""

    def __init__(
        self,
        telegram_api: TelegramAPI,
        telegram_enabled_func: Callable[[], bool],
        enqueue_job_func: Callable[[Job], None],
        storage_root: Path
    ):
        """Initialize poller.

        Args:
            telegram_api: Telegram API client
            telegram_enabled_func: Function returning if Telegram is enabled
            enqueue_job_func: Function to enqueue jobs
            storage_root: Storage root path
        """
        self.telegram_api = telegram_api
        self.telegram_enabled_func = telegram_enabled_func
        self.enqueue_job_func = enqueue_job_func
        self.storage_root = storage_root
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_update_id = 0
        self.ollama = OllamaHelper()

    def start(self):
        """Start polling thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        print("[TelegramPoller] Polling started", flush=True)

    def stop(self):
        """Stop polling thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[TelegramPoller] Polling stopped", flush=True)

    def _poll_loop(self):
        """Main polling loop."""
        print(f"[TelegramPoller] Poll loop started, running={self.running}", flush=True)
        while self.running:
            try:
                # Check if Telegram is enabled
                if not self.telegram_enabled_func():
                    print("[TelegramPoller] Telegram disabled, sleeping...", flush=True)
                    time.sleep(5)
                    continue

                print(f"[TelegramPoller] Polling for updates (offset={self.last_update_id + 1})...", flush=True)

                # Get updates
                updates = self.telegram_api.get_updates(offset=self.last_update_id + 1, timeout=30)

                print(f"[TelegramPoller] Received {len(updates)} updates", flush=True)

                for update in updates:
                    # Update offset
                    update_id = update.get('update_id', 0)
                    if update_id > self.last_update_id:
                        self.last_update_id = update_id

                    print(f"[TelegramPoller] Processing update {update_id}", flush=True)
                    # Process update
                    self._process_update(update)

            except Exception as e:
                print(f"[TelegramPoller] Error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                time.sleep(5)

    def _process_update(self, update: dict):
        """Process a single update.

        Args:
            update: Update dict from Telegram
        """
        print(f"[TelegramPoller] Full update: {update}", flush=True)

        # Extract message
        message = update.get('message')
        if not message:
            print(f"[TelegramPoller] No 'message' in update, keys: {list(update.keys())}", flush=True)
            return

        print(f"[TelegramPoller] Message keys: {list(message.keys())}", flush=True)
        chat_id = str(message['chat']['id'])
        # Text can be in 'text' (text messages) or 'caption' (photo/video with caption)
        text = message.get('text') or message.get('caption', '')
        print(f"[TelegramPoller] chat_id={chat_id}, text='{text}'", flush=True)

        # Check if Telegram is enabled
        enabled = self.telegram_enabled_func()
        print(f"[TelegramPoller] Telegram enabled check: {enabled}", flush=True)
        if not enabled:
            print("[TelegramPoller] Telegram is DISABLED, sending warning and returning", flush=True)
            try:
                self.telegram_api.send_message(
                    chat_id,
                    "⚠️ Telegram bot is currently disabled by administrator."
                )
            except Exception:
                pass
            return

        print("[TelegramPoller] Telegram is ENABLED, processing commands...", flush=True)

        # Handle /help command
        print(f"[TelegramPoller] Checking if text '{text}' starts with '/help'", flush=True)
        if text.startswith('/help'):
            print("[TelegramPoller] Matched /help command, sending help text...", flush=True)
            help_text = self._get_help_text()
            try:
                self.telegram_api.send_message(chat_id, help_text)
                print("[TelegramPoller] Help message sent successfully", flush=True)
            except Exception as e:
                print(f"[TelegramPoller] Failed to send help: {e}", flush=True)
            return

        # Handle /im2vid command
        print(f"[TelegramPoller] Checking if text '{text}' starts with '/im2vid'", flush=True)
        if text.startswith('/im2vid'):
            print("[TelegramPoller] Matched /im2vid command", flush=True)
            self._handle_im2vid(message, chat_id, text)

        # Handle /songai command (check before /song since it starts with /song)
        if text.startswith('/songai'):
            print("[TelegramPoller] Matched /songai command", flush=True)
            self._handle_songai(message, chat_id, text)
        # Handle /song command
        elif text.startswith('/song'):
            print("[TelegramPoller] Matched /song command", flush=True)
            self._handle_song(message, chat_id, text)

    def _handle_im2vid(self, message: dict, chat_id: str, text: str):
        """Handle /im2vid command.

        Args:
            message: Telegram message dict
            chat_id: Chat ID
            text: Message text
        """
        import uuid

        # Check for image
        photo = message.get('photo')
        if not photo:
            try:
                self.telegram_api.send_message(
                    chat_id,
                    "⚠️ Please attach an image with the `/im2vid` command."
                )
            except Exception:
                pass
            return

        # Parse prompt from command
        # Format: /im2vid <prompt>
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            try:
                self.telegram_api.send_message(
                    chat_id,
                    "⚠️ Usage: `/im2vid <your prompt>`\n\nExample: `/im2vid slow camera orbit, cinematic lighting`"
                )
            except Exception:
                pass
            return

        prompt = parts[1].strip()

        # Download image
        try:
            # Get largest photo
            largest_photo = max(photo, key=lambda p: p.get('file_size', 0))
            file_info = self.telegram_api.get_file(largest_photo['file_id'])
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
                    "resolution": "1280x720",
                    "fps": 16,
                    "duration_seconds": 5
                }
            )

            # Download image to job input dir
            input_dir = self.storage_root / job_id / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            image_path = input_dir / "input.png"

            self.telegram_api.download_file(file_path_tg, image_path)

            # Enqueue job
            self.enqueue_job_func(job)

            # Notify user
            self.telegram_api.send_message(
                chat_id,
                f"✅ Job queued: `{job_id}`\n\n"
                f"Prompt: {prompt}\n\n"
                f"Your video will be sent here when ready (est. 2-4 minutes)!"
            )

            print(f"[TelegramPoller] Job {job_id} created from Telegram", flush=True)

        except Exception as e:
            print(f"[TelegramPoller] Error handling /im2vid: {e}", flush=True)

    def _handle_song(self, message: dict, chat_id: str, text: str):
        """Handle /song command.

        Format:
            /song
            <description>
            ---
            <lyrics>

        Args:
            message: Telegram message dict
            chat_id: Chat ID
            text: Message text
        """
        import uuid

        # Parse message - should have format /song\n<description>\n---\n<lyrics>
        if '---' not in text:
            try:
                self.telegram_api.send_message(
                    chat_id,
                    "⚠️ Usage: `/song`\n"
                    "`<description>`\n"
                    "`---`\n"
                    "`<lyrics>`\n\n"
                    "Example:\n"
                    "`/song`\n"
                    "`pop-punk, upbeat, fun, loud drums`\n"
                    "`---`\n"
                    "`This is the first line`\n"
                    "`Second line here`\n"
                    "`Then came the chorus`\n"
                    "`And we all laughed`"
                )
            except Exception:
                pass
            return

        # Split by separator
        parts = text.split('---', 1)
        if len(parts) != 2:
            return

        # First part contains /song and description
        desc_part = parts[0].strip()
        # Remove /song command
        desc_lines = desc_part.split('\n', 1)
        if len(desc_lines) < 2:
            description = ""
        else:
            description = desc_lines[1].strip()

        # Second part is lyrics
        lyrics = parts[1].strip()

        if not description or not lyrics:
            try:
                self.telegram_api.send_message(
                    chat_id,
                    "⚠️ Both description and lyrics are required!"
                )
            except Exception:
                pass
            return

        # Create job
        try:
            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                status=JobStatus.QUEUED,
                created_at=Job.now(),
                updated_at=Job.now(),
                prompt=f"Song: {description[:50]}...",  # Short summary for display
                telegram_chat_id=chat_id,
                params={
                    "workflow_type": "song",
                    "song_description": description,
                    "song_lyrics": lyrics,
                }
            )

            # Enqueue job
            self.enqueue_job_func(job)

            # Notify user
            self.telegram_api.send_message(
                chat_id,
                f"✅ Song queued: `{job_id}`\n\n"
                f"Description: {description[:100]}\n\n"
                f"Your song will be sent here when ready (est. 2-3 minutes)!"
            )

            print(f"[TelegramPoller] Song job {job_id} created from Telegram", flush=True)

        except Exception as e:
            print(f"[TelegramPoller] Error handling /song: {e}", flush=True)
            try:
                self.telegram_api.send_message(
                    chat_id,
                    f"❌ Failed to queue job: {str(e)}"
                )
            except Exception:
                pass

    def _handle_songai(self, message: dict, chat_id: str, text: str):
        """Handle /songai command - AI-generated song.

        Format: /songai <creative prompt>

        Args:
            message: Telegram message dict
            chat_id: Chat ID
            text: Message text
        """
        import uuid

        # Parse prompt from command
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            try:
                self.telegram_api.send_message(
                    chat_id,
                    "⚠️ Usage: `/songai <your creative prompt>`\n\n"
                    "Example: `/songai upbeat song about a robot learning to dance`\n\n"
                    "The AI will generate both the description and lyrics for you!"
                )
            except Exception:
                pass
            return

        user_prompt = parts[1].strip()

        try:
            # Send thinking message
            self.telegram_api.send_message(
                chat_id,
                "🤖 Generating song with AI...\n\nThis may take 30-60 seconds."
            )

            # Generate song with Ollama
            result = self.ollama.generate_song(user_prompt)

            if not result:
                self.telegram_api.send_message(
                    chat_id,
                    "❌ Failed to generate song. Make sure Ollama is running with qwen2.5:7b model."
                )
                return

            description, lyrics = result

            # Create job
            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                status=JobStatus.QUEUED,
                created_at=Job.now(),
                updated_at=Job.now(),
                prompt=f"AI Song: {user_prompt[:50]}...",
                telegram_chat_id=chat_id,
                params={
                    "workflow_type": "song",
                    "song_description": description,
                    "song_lyrics": lyrics,
                }
            )

            # Enqueue job
            self.enqueue_job_func(job)

            # Notify user
            self.telegram_api.send_message(
                chat_id,
                f"✅ AI-generated song queued: `{job_id}`\n\n"
                f"**Description:** {description[:100]}\n\n"
                f"**Lyrics preview:**\n{lyrics[:200]}...\n\n"
                f"Your song will be sent here when ready (est. 2-3 minutes)!"
            )

            print(f"[TelegramPoller] AI song job {job_id} created from Telegram", flush=True)

        except Exception as e:
            print(f"[TelegramPoller] Error handling /songai: {e}", flush=True)
            try:
                self.telegram_api.send_message(
                    chat_id,
                    f"❌ Failed to generate AI song: {str(e)}"
                )
            except Exception:
                pass

    def _get_help_text(self) -> str:
        """Get help text for bot commands.

        Returns:
            Help text string
        """
        return """🎥🎵 **Media Generation Bot**

**Commands:**

`/im2vid <prompt>` - Generate video from image
  • Attach an image with the command
  • Example: `/im2vid slow camera orbit, cinematic`

`/song` - Generate a song (manual)
  • Format:
    ```
    /song
    description here
    ---
    lyrics here
    ```
  • Example:
    ```
    /song
    pop-punk, upbeat, fun
    ---
    This is the first line
    Second line here
    Then came the chorus
    And we all laughed
    ```

`/songai <prompt>` - Generate a song (AI-assisted)
  • AI generates description & lyrics for you
  • Example: `/songai upbeat song about a robot learning to dance`

`/help` - Show this help message

**How it works:**
• **Video**: Send `/im2vid` with image, wait ~2-4 min
• **Song**: Send `/song` with description and lyrics, wait ~2-3 min

**Tips:**
• Describe motion: "person walks", "camera pans left"
• Add atmosphere: "cinematic lighting", "dramatic"
• Be specific: "person turns head and smiles"

**Powered by Wan2.2 Image→Video**
"""
