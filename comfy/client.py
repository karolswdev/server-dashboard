#!/usr/bin/env python3
"""ComfyUI API client."""

import requests
from pathlib import Path
from typing import Optional, Dict, Any


class ComfyUIClient:
    """Client for ComfyUI REST API."""

    def __init__(self, base_url: str, timeout: int = 300):
        """Initialize ComfyUI client.

        Args:
            base_url: ComfyUI server URL (e.g., http://127.0.0.1:8188)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

    def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        """Queue a prompt for execution.

        Args:
            workflow: Complete workflow JSON

        Returns:
            Prompt ID

        Raises:
            requests.RequestException: On API error
        """
        payload = {"prompt": workflow}
        response = self.session.post(
            f"{self.base_url}/prompt",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data['prompt_id']

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """Get execution history for a prompt.

        Args:
            prompt_id: Prompt ID from queue_prompt

        Returns:
            History data dict

        Raises:
            requests.RequestException: On API error
        """
        response = self.session.get(
            f"{self.base_url}/history/{prompt_id}",
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    def download_output(
        self,
        filename: str,
        dest_path: Path,
        subfolder: str = "",
        ftype: str = "output"
    ) -> None:
        """Download output file from ComfyUI.

        Args:
            filename: Output filename
            dest_path: Local destination path
            subfolder: Subfolder within output type
            ftype: File type (output, input, temp)

        Raises:
            requests.RequestException: On download error
        """
        params = {
            "filename": filename,
            "type": ftype
        }
        if subfolder:
            params["subfolder"] = subfolder

        response = self.session.get(
            f"{self.base_url}/view",
            params=params,
            stream=True,
            timeout=self.timeout
        )
        response.raise_for_status()

        # Stream to file
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def upload_image(self, image_path: Path, overwrite: bool = False) -> str:
        """Upload image to ComfyUI.

        Args:
            image_path: Path to local image file
            overwrite: Whether to overwrite existing file

        Returns:
            Server filename

        Raises:
            requests.RequestException: On upload error
        """
        with open(image_path, 'rb') as f:
            files = {'image': (image_path.name, f, 'image/png')}
            data = {'overwrite': str(overwrite).lower()}

            response = self.session.post(
                f"{self.base_url}/upload/image",
                files=files,
                data=data,
                timeout=60
            )
            response.raise_for_status()

        result = response.json()
        return result.get('name', image_path.name)

    def check_reachable(self, timeout: int = 5) -> bool:
        """Check if ComfyUI server is reachable.

        Args:
            timeout: Request timeout in seconds

        Returns:
            True if reachable, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.base_url}/system_stats",
                timeout=timeout
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_latency_ms(self) -> Optional[int]:
        """Measure latency to ComfyUI server.

        Returns:
            Latency in milliseconds or None if unreachable
        """
        import time
        try:
            start = time.time()
            response = self.session.get(
                f"{self.base_url}/system_stats",
                timeout=5
            )
            elapsed = (time.time() - start) * 1000
            if response.status_code == 200:
                return int(elapsed)
        except Exception:
            pass
        return None
