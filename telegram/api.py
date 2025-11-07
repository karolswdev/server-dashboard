#!/usr/bin/env python3
"""Telegram Bot API client."""

import requests
from pathlib import Path
from typing import Optional


class TelegramAPI:
    """Minimal Telegram Bot API client."""

    # Telegram file size limit: 50MB
    MAX_FILE_SIZE = 50 * 1024 * 1024

    def __init__(self, bot_token: str):
        """Initialize Telegram API client.

        Args:
            bot_token: Bot token from BotFather
        """
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session = requests.Session()

    def send_message(self, chat_id: str, text: str) -> dict:
        """Send text message.

        Args:
            chat_id: Chat ID to send to
            text: Message text

        Returns:
            API response dict

        Raises:
            requests.RequestException: On API error
        """
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        response = self.session.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()

    def send_status(self, chat_id: str, text: str) -> dict:
        """Send status update message.

        Args:
            chat_id: Chat ID
            text: Status text

        Returns:
            API response dict
        """
        return self.send_message(chat_id, text)

    def send_video(
        self,
        chat_id: str,
        file_path: Path,
        caption: Optional[str] = None,
        link_fallback: Optional[str] = None
    ) -> dict:
        """Send video file or link if too large.

        Args:
            chat_id: Chat ID
            file_path: Path to video file
            caption: Optional caption
            link_fallback: Fallback link if file too large

        Returns:
            API response dict

        Raises:
            requests.RequestException: On API error
        """
        file_size = file_path.stat().st_size

        # If file too large, send link instead
        if file_size > self.MAX_FILE_SIZE:
            if link_fallback:
                msg = f"🎥 Video ready!\n\n{caption or ''}\n\n[Download]({link_fallback})"
                return self.send_message(chat_id, msg)
            else:
                msg = f"⚠️ Video is too large ({file_size / 1024 / 1024:.1f}MB) to send directly."
                return self.send_message(chat_id, msg)

        # Send video file
        url = f"{self.base_url}/sendVideo"
        with open(file_path, 'rb') as f:
            files = {'video': f}
            data = {'chat_id': chat_id}
            if caption:
                data['caption'] = caption

            response = self.session.post(url, data=data, files=files, timeout=300)
            response.raise_for_status()
            return response.json()

    def send_audio(
        self,
        chat_id: str,
        file_path: Path,
        caption: Optional[str] = None,
        link_fallback: Optional[str] = None
    ) -> dict:
        """Send audio file or link if too large.

        Args:
            chat_id: Chat ID
            file_path: Path to audio file
            caption: Optional caption
            link_fallback: Fallback link if file too large

        Returns:
            API response dict

        Raises:
            requests.RequestException: On API error
        """
        file_size = file_path.stat().st_size

        # If file too large, send link instead
        if file_size > self.MAX_FILE_SIZE:
            if link_fallback:
                msg = f"🎵 Audio ready!\n\n{caption or ''}\n\n[Download]({link_fallback})"
                return self.send_message(chat_id, msg)
            else:
                msg = f"⚠️ Audio is too large ({file_size / 1024 / 1024:.1f}MB) to send directly."
                return self.send_message(chat_id, msg)

        # Send audio file
        url = f"{self.base_url}/sendAudio"
        with open(file_path, 'rb') as f:
            files = {'audio': f}
            data = {'chat_id': chat_id}
            if caption:
                data['caption'] = caption

            response = self.session.post(url, data=data, files=files, timeout=300)
            response.raise_for_status()
            return response.json()

    def get_file(self, file_id: str) -> dict:
        """Get file info.

        Args:
            file_id: Telegram file ID

        Returns:
            File info dict with 'file_path'

        Raises:
            requests.RequestException: On API error
        """
        url = f"{self.base_url}/getFile"
        response = self.session.post(url, json={"file_id": file_id}, timeout=10)
        response.raise_for_status()
        return response.json()['result']

    def download_file(self, file_path: str, dest_path: Path) -> None:
        """Download file from Telegram servers.

        Args:
            file_path: File path from getFile API
            dest_path: Local destination path

        Raises:
            requests.RequestException: On download error
        """
        url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        response = self.session.get(url, stream=True, timeout=60)
        response.raise_for_status()

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> list:
        """Get updates (polling mode).

        Args:
            offset: Update offset
            timeout: Long polling timeout

        Returns:
            List of updates

        Raises:
            requests.RequestException: On API error
        """
        url = f"{self.base_url}/getUpdates"
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset

        response = self.session.get(url, params=params, timeout=timeout + 5)
        response.raise_for_status()
        return response.json().get('result', [])

    def send_document(self, chat_id: str, file_path, caption: str = "", filename: str = None) -> bool:
        """Send document file to Telegram chat.

        Args:
            chat_id: Telegram chat ID
            file_path: Path to document file
            caption: Optional caption
            filename: Optional custom filename

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                print(f"[ERROR] File not found: {file_path}")
                return False

            # Determine filename
            if not filename:
                filename = file_path.name

            # Send document
            with open(file_path, 'rb') as f:
                files = {'document': (filename, f)}
                data = {'chat_id': chat_id}

                if caption:
                    data['caption'] = caption

                response = self.session.post(
                    f"{self.base_url}/sendDocument",
                    data=data,
                    files=files,
                    timeout=60
                )

                if response.status_code != 200:
                    print(f"[ERROR] Telegram sendDocument failed: {response.text}")
                    return False

                result = response.json()
                return result.get('ok', False)

        except Exception as e:
            print(f"[ERROR] Failed to send document: {e}")
            return False

    def download_file_content(self, file_id: str) -> Optional[str]:
        """Download file content from Telegram and return as string.

        Args:
            file_id: Telegram file ID

        Returns:
            File content as string, or None if failed
        """
        try:
            # Get file path
            response = self.session.get(
                f"{self.base_url}/getFile",
                params={'file_id': file_id},
                timeout=10
            )

            if response.status_code != 200:
                print(f"[ERROR] getFile failed: {response.text}")
                return None

            result = response.json()
            if not result.get('ok'):
                return None

            file_path = result['result']['file_path']

            # Download file
            file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            download_response = self.session.get(file_url, timeout=30)

            if download_response.status_code != 200:
                print(f"[ERROR] File download failed: {download_response.status_code}")
                return None

            # Return as text (decode UTF-8)
            return download_response.content.decode('utf-8', errors='ignore')

        except Exception as e:
            print(f"[ERROR] Failed to download file: {e}")
            return None
