"""
Telegram handler for Docket HTML-to-DOCX conversions

Add this file to your dashboard's telegram/ directory as docket_handler.py

Usage in poller.py:
    from telegram.docket_handler import handle_docx_command

    # In message handler:
    if text.startswith('/docx') or text.startswith('/convert'):
        handle_docx_command(telegram_api, message, DOCKET_URL)
"""

import requests
import tempfile
from pathlib import Path
from typing import Optional


def handle_docx_command(telegram_api, message: dict, docket_url: str):
    """
    Handle /docx and /convert commands from Telegram.

    Commands:
        /docx <HTML content>
        /docx [with HTML file attachment]
        /docx modern <HTML content>  (with theme)
        /convert <HTML>

    Args:
        telegram_api: TelegramAPI instance
        message: Telegram message dict
        docket_url: Docket API URL (e.g., http://127.0.0.1:3050)
    """
    chat_id = message['chat']['id']
    text = message.get('text', '')

    try:
        # Parse command
        parts = text.split(None, 2)  # ['/docx', 'theme?', 'html?']
        command = parts[0] if parts else ''

        # Default options
        theme_id = 'modern'
        html_content = None
        format_type = 'docx'

        # Check for file attachment (document or text file)
        if 'document' in message:
            document = message['document']
            mime_type = document.get('mime_type', '')

            # Only accept text/html or text/plain
            if mime_type in ['text/html', 'text/plain', 'application/octet-stream']:
                file_id = document['file_id']
                html_content = telegram_api.download_file_content(file_id)

                if not html_content:
                    telegram_api.send_message(chat_id, "❌ Failed to download file")
                    return
            else:
                telegram_api.send_message(
                    chat_id,
                    f"❌ Invalid file type: {mime_type}\n\n"
                    "Please send .html or .txt files"
                )
                return

        # Parse inline HTML or options
        if len(parts) >= 2:
            # Check if second part is a theme name
            available_themes = [
                'modern', 'corporate', 'minimal', 'horizon',
                'obsidian', 'enterprise', 'clarity', 'emerald'
            ]

            if parts[1].lower() in available_themes:
                theme_id = parts[1].lower()
                if len(parts) >= 3:
                    html_content = parts[2]
            else:
                # Second part is HTML content
                html_content = ' '.join(parts[1:])

        # Validate we have HTML
        if not html_content:
            telegram_api.send_message(
                chat_id,
                "❌ No HTML content provided\n\n"
                "Usage:\n"
                "/docx <html>\n"
                "/docx modern <html>\n"
                "Or send HTML file with /docx caption"
            )
            return

        # Send processing message
        status_msg = telegram_api.send_message(
            chat_id,
            f"🔄 Converting to DOCX...\n"
            f"Theme: {theme_id}\n"
            f"Size: {len(html_content)} chars"
        )

        # Call Docket API
        try:
            response = requests.post(
                f"{docket_url}/api/convert",
                json={
                    "html": html_content,
                    "format": format_type,
                    "themeId": theme_id
                },
                headers={"Content-Type": "application/json"},
                timeout=60  # 60 second timeout for conversion
            )

            if response.status_code != 200:
                error_text = response.text[:200]
                telegram_api.send_message(
                    chat_id,
                    f"❌ Conversion failed (HTTP {response.status_code})\n\n{error_text}"
                )
                return

            # Save DOCX to temp file
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
                tmp.write(response.content)
                tmp_path = Path(tmp.name)

            # Send DOCX file
            caption = (
                f"✅ Document ready!\n\n"
                f"Theme: {theme_id}\n"
                f"Format: {format_type.upper()}\n"
                f"Size: {len(response.content) // 1024} KB"
            )

            success = telegram_api.send_document(
                chat_id,
                tmp_path,
                caption=caption,
                filename=f"document_{theme_id}.{format_type}"
            )

            # Clean up
            tmp_path.unlink()

            if not success:
                telegram_api.send_message(chat_id, "✅ Conversion complete but failed to send file")

        except requests.exceptions.Timeout:
            telegram_api.send_message(
                chat_id,
                "❌ Conversion timed out (>60s)\n\nTry with smaller HTML or simpler content"
            )
        except requests.exceptions.RequestException as e:
            telegram_api.send_message(
                chat_id,
                f"❌ Failed to reach Docket service\n\nError: {str(e)[:100]}"
            )

    except Exception as e:
        telegram_api.send_message(
            chat_id,
            f"❌ Error processing command\n\n{str(e)[:200]}"
        )
        print(f"[ERROR] Docket Telegram handler: {e}")


def get_help_text() -> str:
    """Get help text for Docket commands."""
    return """
📄 *Docket HTML→DOCX Converter*

Convert HTML to professional Word documents with themes!

*Commands:*
• `/docx <html>` - Convert HTML to DOCX
• `/docx modern <html>` - Use specific theme
• `/convert <html>` - Alias for /docx

*With File:*
Send .html file with caption `/docx` or `/docx modern`

*Available Themes:*
• `modern` - Contemporary design (default)
• `corporate` - Classic business
• `minimal` - Ultra-minimal
• `horizon` - Tech startup
• `obsidian` - Dark mode
• `enterprise` - Corporate authority
• `clarity` - Accessibility-first
• `emerald` - Financial services

*Examples:*
```
/docx <h1>My Document</h1><p>Content here</p>

/docx corporate <h1>Report</h1><ul><li>Item</li></ul>
```

Or attach HTML file with `/docx` caption.
"""


# Integration code for poller.py
INTEGRATION_SNIPPET = """
# Add to telegram/poller.py message handler:

from telegram.docket_handler import handle_docx_command, get_help_text

# In _handle_message() method, add:

def _handle_message(self, message: dict):
    text = message.get('text', '').strip()
    chat_id = message['chat']['id']

    # ... existing command handlers ...

    # Docket HTML→DOCX conversion
    if text.startswith('/docx') or text.startswith('/convert'):
        handle_docx_command(self.telegram_api, message, DOCKET_URL)
        return

    # Update help command to include Docket
    if text == '/help':
        help_text = (
            "Available commands:\\n\\n"
            # ... existing help ...
            + get_help_text()
        )
        self.telegram_api.send_message(chat_id, help_text)
        return
"""
