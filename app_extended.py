#!/usr/bin/env python3
"""
Extended Flask Admin Server with ComfyUI + Telegram Integration
"""

from flask import Flask, render_template, jsonify, request, send_file
import subprocess
import psutil
import os
import socket
import json
import uuid
from pathlib import Path
from typing import Optional

# Job system imports
from jobs.models import Job, JobStatus
from jobs.queue import JobQueue
from jobs.store import JobStore
from jobs.worker import JobWorker

# ComfyUI imports
from comfy.client import ComfyUIClient
from comfy.workflow import validate_params

# Telegram imports
from telegram.api import TelegramAPI
from telegram.webhook import telegram_bp, init_webhook

app = Flask(__name__)

# ===== Configuration =====

def get_env(key: str, default: str = "") -> str:
    """Get environment variable."""
    return os.environ.get(key, default)

def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    val = os.environ.get(key, str(default)).lower()
    return val in ('true', '1', 'yes', 'on')

# Paths and URLs
COMFYUI_BASE_URL = get_env("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
STORAGE_ROOT = Path(get_env("STORAGE_ROOT", "./data"))
PUBLIC_BASE_URL = get_env("PUBLIC_BASE_URL", "")
WORKFLOW_PATH = Path(get_env("WORKFLOW_PATH", "./Workflows/image_to_video_base.json"))

# Telegram config
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_NAME = get_env("TELEGRAM_BOT_NAME", "")
TELEGRAM_DEFAULT_CHAT_ID = get_env("TELEGRAM_DEFAULT_CHAT_ID", "")

# Runtime config file
CONFIG_FILE = Path("./config.json")

# ===== Runtime Config =====

class RuntimeConfig:
    """Runtime configuration with persistence."""

    def __init__(self, config_file: Path):
        self.config_file = config_file
        self.data = self._load()

    def _load(self) -> dict:
        """Load config from file."""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return {
            "telegram_enabled": get_env_bool("TELEGRAM_ENABLED", False)
        }

    def _save(self):
        """Save config to file."""
        with open(self.config_file, 'w') as f:
            json.dump(self.data, f, indent=2)

    def get_telegram_enabled(self) -> bool:
        """Get Telegram enabled status."""
        return self.data.get("telegram_enabled", False)

    def set_telegram_enabled(self, enabled: bool):
        """Set Telegram enabled status."""
        self.data["telegram_enabled"] = enabled
        self._save()

runtime_config = RuntimeConfig(CONFIG_FILE)

# ===== Initialize Components =====

# Job system
job_queue = JobQueue()
job_store = JobStore(str(STORAGE_ROOT))
comfy_client = ComfyUIClient(COMFYUI_BASE_URL)

# Telegram (if configured)
telegram_api: Optional[TelegramAPI] = None
if TELEGRAM_BOT_TOKEN:
    telegram_api = TelegramAPI(TELEGRAM_BOT_TOKEN)

# Worker (started later)
job_worker: Optional[JobWorker] = None

# ===== Helper Functions =====

def is_local_network(ip):
    """Check if IP is from local network."""
    return ip.startswith('192.168.') or ip == '127.0.0.1' or ip == 'localhost'

def run_command(cmd):
    """Run a system command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return {"success": True, "output": result.stdout, "error": result.stderr}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_service_status(service):
    """Get systemd service status."""
    result = subprocess.run(f"systemctl is-active {service}", shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def get_docker_status(container):
    """Get Docker container status."""
    result = subprocess.run(f"docker inspect -f '{{{{.State.Running}}}}' {container} 2>/dev/null",
                          shell=True, capture_output=True, text=True)
    return "running" if result.stdout.strip() == "true" else "stopped"

def get_system_stats():
    """Get system statistics."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    # Get GPU stats
    try:
        gpu_result = subprocess.run(
            "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits",
            shell=True, capture_output=True, text=True
        )
        if gpu_result.returncode == 0:
            gpu_util, gpu_mem_used, gpu_mem_total = gpu_result.stdout.strip().split(',')
            gpu_stats = {
                "utilization": int(gpu_util.strip()),
                "memory_used": int(gpu_mem_used.strip()),
                "memory_total": int(gpu_mem_total.strip())
            }
        else:
            gpu_stats = None
    except:
        gpu_stats = None

    return {
        "cpu": cpu_percent,
        "memory": {
            "used": memory.used // (1024**3),
            "total": memory.total // (1024**3),
            "percent": memory.percent
        },
        "disk": {
            "used": disk.used // (1024**3),
            "total": disk.total // (1024**3),
            "percent": disk.percent
        },
        "gpu": gpu_stats
    }

def send_telegram_notification(job: Job):
    """Send Telegram notification for completed job."""
    if not telegram_api or not runtime_config.get_telegram_enabled():
        return

    chat_id = job.telegram_chat_id
    if not chat_id:
        chat_id = TELEGRAM_DEFAULT_CHAT_ID

    if not chat_id:
        return

    try:
        if job.status == JobStatus.COMPLETED and job.files:
            # Get first video file
            video_file = None
            for f in job.files:
                if f.endswith(('.mp4', '.avi', '.mov', '.gif')):
                    video_file = f
                    break

            if video_file:
                video_path = job_store.get_output_dir(job.id) / video_file
                caption = f"✅ Video ready!\n\nPrompt: {job.prompt}"

                # Build fallback link
                link = None
                if PUBLIC_BASE_URL:
                    link = f"{PUBLIC_BASE_URL}/api/jobs/{job.id}/result"

                telegram_api.send_video(chat_id, video_path, caption, link)
            else:
                telegram_api.send_message(chat_id, f"✅ Job {job.id} completed but no video found.")

        elif job.status in [JobStatus.FAILED, JobStatus.TIMED_OUT]:
            telegram_api.send_message(
                chat_id,
                f"❌ Job {job.id} failed\n\nError: {job.error or 'Unknown error'}"
            )

    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")

# ===== Flask Middleware =====

@app.before_request
def limit_remote_addr():
    """Limit access to local network."""
    if not is_local_network(request.remote_addr):
        return jsonify({"error": "Access denied"}), 403

# ===== Existing Routes =====

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')

@app.route('/api/status')
def status():
    """Get status of all services."""
    services = {
        "ollama": get_service_status("ollama"),
        "comfyui": get_service_status("comfyui"),
        "sunshine": get_service_status("sunshine"),
        "open_webui": get_docker_status("open-webui")
    }

    stats = get_system_stats()

    return jsonify({
        "services": services,
        "stats": stats,
        "hostname": socket.gethostname(),
        "ip": request.host.split(':')[0]
    })

@app.route('/api/service/<service>/<action>', methods=['POST'])
def control_service(service, action):
    """Control a service (start/stop/restart)."""
    allowed_services = ['ollama', 'comfyui', 'sunshine']
    allowed_actions = ['start', 'stop', 'restart']

    if service not in allowed_services or action not in allowed_actions:
        return jsonify({"success": False, "error": "Invalid service or action"}), 400

    cmd = f"sudo systemctl {action} {service}"
    result = run_command(cmd)
    return jsonify(result)

@app.route('/api/docker/<container>/<action>', methods=['POST'])
def control_docker(container, action):
    """Control a Docker container."""
    if container != 'open-webui':
        return jsonify({"success": False, "error": "Invalid container"}), 400

    if action not in ['start', 'stop', 'restart']:
        return jsonify({"success": False, "error": "Invalid action"}), 400

    cmd = f"docker {action} {container}"
    result = run_command(cmd)
    return jsonify(result)

@app.route('/api/ollama/kill-models', methods=['POST'])
def kill_ollama_models():
    """Kill all running Ollama models."""
    cmd = "sudo systemctl restart ollama"
    result = run_command(cmd)
    return jsonify(result)

# ===== New Job Routes =====

@app.route('/api/jobs/image-to-video', methods=['POST'])
def create_image_to_video_job():
    """Create image-to-video job."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Extract parameters
    prompt = data.get('prompt', '')
    input_image_url = data.get('input_image_url', '')
    params = data.get('params', {})
    telegram_chat_id = data.get('telegram_chat_id')
    webhook_url = data.get('webhook_url')

    # Validate
    is_valid, error_msg = validate_params(
        prompt=prompt,
        seed=params.get('seed'),
        duration_seconds=params.get('duration_seconds'),
        fps=params.get('fps'),
        resolution=params.get('resolution')
    )

    if not is_valid:
        return jsonify({"error": error_msg}), 400

    if not input_image_url:
        return jsonify({"error": "input_image_url is required"}), 400

    # Validate URL scheme
    if not input_image_url.startswith(('http://', 'https://', 'telegram://')):
        return jsonify({"error": "Invalid input_image_url scheme"}), 400

    # Create job
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        status=JobStatus.QUEUED,
        created_at=Job.now(),
        updated_at=Job.now(),
        prompt=prompt,
        input_image_url=input_image_url,
        telegram_chat_id=telegram_chat_id,
        webhook_url=webhook_url,
        params=params
    )

    # Save and enqueue
    job_store.save(job)
    job_queue.enqueue(job)

    # Build response URLs
    base_url = request.host_url.rstrip('/')
    response = {
        "job_id": job_id,
        "status_url": f"{base_url}/api/jobs/{job_id}",
        "result_url": f"{base_url}/api/jobs/{job_id}/result"
    }

    return jsonify(response), 201

@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """Get job status and metadata."""
    job = job_store.load(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(job.to_dict())

@app.route('/api/jobs/<job_id>/result', methods=['GET'])
def get_job_result(job_id):
    """Stream job result file."""
    job = job_store.load(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status != JobStatus.COMPLETED:
        return jsonify({"error": "Job not completed", "status": job.status.value}), 404

    if not job.files:
        return jsonify({"error": "No output files"}), 404

    # Get first video file
    video_file = None
    for f in job.files:
        if f.endswith(('.mp4', '.avi', '.mov', '.gif')):
            video_file = f
            break

    if not video_file:
        return jsonify({"error": "No video file found"}), 404

    file_path = job_store.get_output_dir(job_id) / video_file

    if not file_path.exists():
        return jsonify({"error": "Output file not found"}), 404

    return send_file(file_path, mimetype='video/mp4')

@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """Cancel a job."""
    job = job_store.load(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMED_OUT, JobStatus.CANCELED]:
        return jsonify({"error": "Job already finished"}), 400

    job_store.update(job_id, status=JobStatus.CANCELED)
    return jsonify({"success": True})

# ===== New Admin Routes =====

@app.route('/api/admin/status', methods=['GET'])
def admin_status():
    """Get admin status for dashboard."""
    # Check ComfyUI reachability
    comfy_reachable = comfy_client.check_reachable()
    comfy_latency = comfy_client.get_latency_ms() if comfy_reachable else None

    # Worker status
    worker_running = job_worker is not None and job_worker.running

    # Job stats
    queued = job_queue.size()
    recent_stats = job_worker.stats if job_worker else {"success": 0, "failed": 0}

    # Telegram status
    telegram_status = {
        "enabled": runtime_config.get_telegram_enabled(),
        "bot_name": TELEGRAM_BOT_NAME if TELEGRAM_BOT_NAME else None
    }

    return jsonify({
        "web_ui_server": "running",
        "comfyui": {
            "reachable": comfy_reachable,
            "base_url": COMFYUI_BASE_URL,
            "latency_ms": comfy_latency
        },
        "image_to_video_agent": {
            "worker": "running" if worker_running else "stopped",
            "queued": queued,
            "recent": recent_stats
        },
        "telegram": telegram_status
    })

@app.route('/api/admin/telegram/enable', methods=['POST'])
def set_telegram_enabled():
    """Enable/disable Telegram bot."""
    data = request.get_json()
    if not data or 'enabled' not in data:
        return jsonify({"error": "Missing 'enabled' field"}), 400

    enabled = bool(data['enabled'])
    runtime_config.set_telegram_enabled(enabled)

    return jsonify({
        "success": True,
        "enabled": enabled
    })

# ===== Register Telegram Blueprint =====

if telegram_api:
    app.register_blueprint(telegram_bp)
    init_webhook(
        telegram_api=telegram_api,
        telegram_enabled_func=runtime_config.get_telegram_enabled,
        enqueue_job_func=lambda job: (job_store.save(job), job_queue.enqueue(job)),
        storage_root=STORAGE_ROOT
    )

# ===== Initialization =====

def init_worker():
    """Initialize and start job worker."""
    global job_worker

    if not WORKFLOW_PATH.exists():
        print(f"[WARN] Workflow not found at {WORKFLOW_PATH}, worker not started")
        return

    job_worker = JobWorker(
        queue=job_queue,
        store=job_store,
        comfy_client=comfy_client,
        workflow_path=WORKFLOW_PATH,
        telegram_send_func=send_telegram_notification,
        timeout_minutes=10
    )
    job_worker.start()
    print("[INFO] Job worker started")

# ===== Main =====

if __name__ == '__main__':
    # Initialize worker
    init_worker()

    # Run Flask
    host = get_env("DASHBOARD_BIND", "0.0.0.0")
    port = int(get_env("DASHBOARD_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
