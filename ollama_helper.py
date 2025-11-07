#!/usr/bin/env python3
"""Ollama helper for AI-assisted content generation."""

import requests
from typing import Optional


class OllamaHelper:
    """Helper for generating content with Ollama."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        """Initialize Ollama helper.

        Args:
            base_url: Ollama API base URL
        """
        self.base_url = base_url

    def generate_song(
        self,
        user_prompt: str,
        model: str = "qwen2.5:7b"
    ) -> Optional[tuple[str, str]]:
        """Generate song description and lyrics using Ollama.

        Args:
            user_prompt: User's creative prompt for the song
            model: Ollama model to use

        Returns:
            Tuple of (description, lyrics) or None on error
        """
        system_prompt = """You are a creative songwriter. When given a prompt, generate:
1. A detailed musical description (genre, style, instruments, mood, tempo)
2. Complete song lyrics

Format your response EXACTLY as:
DESCRIPTION: <one line with genre, style, mood, instruments>
LYRICS:
<the actual lyrics, multiple lines>

Be creative but keep descriptions concise. Lyrics should be 8-16 lines."""

        full_prompt = f"{system_prompt}\n\nUser prompt: {user_prompt}\n\nGenerate the song:"

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.8,
                        "top_p": 0.9,
                    }
                },
                timeout=120
            )
            response.raise_for_status()

            result = response.json()
            generated = result.get("response", "")

            # Parse the response
            if "DESCRIPTION:" in generated and "LYRICS:" in generated:
                parts = generated.split("LYRICS:", 1)
                desc_part = parts[0].replace("DESCRIPTION:", "").strip()
                lyrics_part = parts[1].strip()

                return desc_part, lyrics_part

            return None

        except Exception as e:
            print(f"[OllamaHelper] Error generating song: {e}")
            return None

    def test_connection(self) -> bool:
        """Test if Ollama is reachable.

        Returns:
            True if Ollama is accessible
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
