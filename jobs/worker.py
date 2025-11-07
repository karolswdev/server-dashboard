#!/usr/bin/env python3
"""Background job worker thread."""

import threading
import time
import requests
from pathlib import Path
from typing import Optional, Callable

from .models import Job, JobStatus
from .queue import JobQueue
from .store import JobStore
from comfy.client import ComfyUIClient
from comfy.workflow import load_base, apply_overrides, apply_song_overrides


class JobWorker:
    """Background worker for processing jobs."""

    def __init__(
        self,
        queue: JobQueue,
        store: JobStore,
        comfy_client: ComfyUIClient,
        workflow_path: Path,
        telegram_send_func: Optional[Callable[[Job], None]] = None,
        timeout_minutes: int = 10
    ):
        """Initialize job worker.

        Args:
            queue: Job queue
            store: Job store
            comfy_client: ComfyUI client
            workflow_path: Path to base workflow JSON
            telegram_send_func: Optional function to send Telegram notifications
            timeout_minutes: Job timeout in minutes
        """
        self.queue = queue
        self.store = store
        self.comfy_client = comfy_client
        self.workflow_path = workflow_path
        self.telegram_send_func = telegram_send_func
        self.timeout_seconds = timeout_minutes * 60
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Stats
        self.stats = {
            "success": 0,
            "failed": 0,
            "timed_out": 0,
            "canceled": 0
        }

    def start(self):
        """Start worker thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()
        print("[JobWorker] Worker thread started")

    def stop(self):
        """Stop worker thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[JobWorker] Worker thread stopped")

    def _worker_loop(self):
        """Main worker loop."""
        while self.running:
            # Dequeue job with timeout
            job = self.queue.dequeue(timeout=1.0)
            if job is None:
                continue

            print(f"[JobWorker] Processing job {job.id}")

            try:
                self._process_job(job)
            except Exception as e:
                print(f"[JobWorker] Unexpected error processing job {job.id}: {e}")
                self.store.update(
                    job.id,
                    status=JobStatus.FAILED,
                    error=f"Unexpected error: {str(e)}"
                )
                self.stats["failed"] += 1

    def _process_job(self, job: Job):
        """Process a single job.

        Args:
            job: Job to process
        """
        start_time = time.time()

        # Check if canceled
        if job.status == JobStatus.CANCELED:
            print(f"[JobWorker] Job {job.id} was canceled")
            self.stats["canceled"] += 1
            return

        # Update to running
        self.store.update(job.id, status=JobStatus.RUNNING, progress=10)

        try:
            params = job.params or {}
            workflow_type = params.get("workflow_type", "im2vid")

            # Handle song workflow
            if workflow_type == "song":
                # Song workflow - no image needed
                song_workflow_path = Path("/home/karol/ComfyUI/user/default/workflows/song-api.json")
                base_workflow = load_base(song_workflow_path)
                workflow = apply_song_overrides(
                    base_workflow,
                    description=params.get("song_description", ""),
                    lyrics=params.get("song_lyrics", "")
                )
                self.store.update(job.id, progress=40)
            else:
                # Image-to-video workflow
                # Step 1: Download input image
                input_path = self._stage_input(job)
                self.store.update(job.id, progress=20)

                # Step 2: Upload to ComfyUI (if needed)
                uploaded_filename = self.comfy_client.upload_image(input_path)
                self.store.update(job.id, progress=30)

                # Step 3: Build workflow
                base_workflow = load_base(self.workflow_path)
                workflow = apply_overrides(
                    base_workflow,
                    prompt=job.prompt,
                    seed=params.get("seed"),
                    duration_seconds=params.get("duration_seconds"),
                    fps=params.get("fps"),
                    resolution=params.get("resolution"),
                    input_filename=uploaded_filename
                )
                self.store.update(job.id, progress=40)

            # Step 4: Queue prompt
            prompt_id = self.comfy_client.queue_prompt(workflow)
            self.store.update(job.id, prompt_id=prompt_id, progress=50)
            print(f"[JobWorker] Job {job.id} queued as prompt {prompt_id}")

            # Step 5: Poll for completion
            outputs = self._poll_for_outputs(job, prompt_id, start_time)
            self.store.update(job.id, progress=80)

            # Step 6: Download outputs
            output_files = self._download_outputs(job, outputs)
            self.store.update(job.id, progress=90)

            # Step 7: Mark complete
            self.store.update(
                job.id,
                status=JobStatus.COMPLETED,
                progress=100,
                files=output_files
            )
            self.stats["success"] += 1
            print(f"[JobWorker] Job {job.id} completed with {len(output_files)} files")

            # Step 8: Send to Telegram if configured
            if self.telegram_send_func and job.telegram_chat_id:
                try:
                    updated_job = self.store.load(job.id)
                    if updated_job:
                        self.telegram_send_func(updated_job)
                except Exception as e:
                    print(f"[JobWorker] Failed to send Telegram notification: {e}")

            # Step 9: Call webhook if configured
            if job.webhook_url:
                self._call_webhook(job)

        except TimeoutError as e:
            print(f"[JobWorker] Job {job.id} timed out: {e}")
            self.store.update(
                job.id,
                status=JobStatus.TIMED_OUT,
                error=str(e)
            )
            self.stats["timed_out"] += 1

        except Exception as e:
            print(f"[JobWorker] Job {job.id} failed: {e}")
            self.store.update(
                job.id,
                status=JobStatus.FAILED,
                error=str(e)
            )
            self.stats["failed"] += 1

    def _stage_input(self, job: Job) -> Path:
        """Download and stage input image.

        Args:
            job: Job instance

        Returns:
            Path to staged input image

        Raises:
            Exception: On download error
        """
        input_dir = self.store.get_input_dir(job.id)

        # If URL starts with telegram://, it's already downloaded
        if job.input_image_url.startswith("telegram://"):
            existing = list(input_dir.glob("*.png")) + list(input_dir.glob("*.jpg"))
            if existing:
                return existing[0]
            raise Exception("Telegram image not found in input dir")

        # Download from URL
        input_path = input_dir / "input.png"
        if not input_path.exists():
            response = requests.get(job.input_image_url, stream=True, timeout=60)
            response.raise_for_status()

            with open(input_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        return input_path

    def _poll_for_outputs(self, job: Job, prompt_id: str, start_time: float) -> dict:
        """Poll ComfyUI for output files.

        Args:
            job: Job instance
            prompt_id: ComfyUI prompt ID
            start_time: Job start timestamp

        Returns:
            Outputs dict from history

        Raises:
            TimeoutError: If job times out
            Exception: On other errors
        """
        poll_interval = 2.0

        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > self.timeout_seconds:
                raise TimeoutError(f"Job timed out after {elapsed:.1f}s")

            # Check if canceled
            current_job = self.store.load(job.id)
            if current_job and current_job.status == JobStatus.CANCELED:
                raise Exception("Job was canceled")

            # Get history
            try:
                history = self.comfy_client.get_history(prompt_id)
            except Exception as e:
                print(f"[JobWorker] Error fetching history: {e}")
                time.sleep(poll_interval)
                continue

            # Check if prompt is in history
            if prompt_id not in history:
                time.sleep(poll_interval)
                continue

            prompt_data = history[prompt_id]

            # Check for errors
            if 'status' in prompt_data and prompt_data['status'].get('status_str') == 'error':
                error_msg = prompt_data['status'].get('messages', ['Unknown error'])[0]
                raise Exception(f"ComfyUI error: {error_msg}")

            # Check for outputs
            outputs = prompt_data.get('outputs', {})
            if outputs:
                print(f"[JobWorker] Found outputs for prompt {prompt_id}")
                return outputs

            time.sleep(poll_interval)

    def _download_outputs(self, job: Job, outputs: dict) -> list:
        """Download output files from ComfyUI.

        Args:
            job: Job instance
            outputs: Outputs dict from history

        Returns:
            List of output filenames
        """
        output_dir = self.store.get_output_dir(job.id)
        downloaded = []

        for node_id, node_output in outputs.items():
            # Look for videos, images, or audio
            for output_type in ['videos', 'gifs', 'images', 'audio']:
                if output_type in node_output:
                    for file_info in node_output[output_type]:
                        filename = file_info.get('filename')
                        subfolder = file_info.get('subfolder', '')
                        ftype = file_info.get('type', 'output')

                        if filename:
                            dest_path = output_dir / filename
                            print(f"[JobWorker] Downloading {filename}...")

                            self.comfy_client.download_output(
                                filename=filename,
                                dest_path=dest_path,
                                subfolder=subfolder,
                                ftype=ftype
                            )
                            downloaded.append(filename)

        return downloaded

    def _call_webhook(self, job: Job):
        """Call webhook URL with job result.

        Args:
            job: Job instance
        """
        try:
            updated_job = self.store.load(job.id)
            if not updated_job:
                return

            payload = {
                "job_id": updated_job.id,
                "status": updated_job.status.value,
                "files": updated_job.files,
                "error": updated_job.error
            }

            response = requests.post(
                job.webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            print(f"[JobWorker] Webhook called successfully for job {job.id}")

        except Exception as e:
            print(f"[JobWorker] Failed to call webhook: {e}")
