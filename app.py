#!/usr/bin/env python3
"""
Extended Flask Admin Server with ComfyUI + Telegram Integration
"""

from flask import Flask, render_template, jsonify, request, send_file, make_response
import subprocess
import psutil
import os
import socket
import json
import uuid
import requests
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
from telegram.poller import TelegramPoller

app = Flask(__name__)

# ===== Configuration =====

# Load telegram config from file if it exists
_telegram_config_file = Path('./telegram_config.env')
if _telegram_config_file.exists():
    with open(_telegram_config_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

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

# Docket config
DOCKET_API_PORT = get_env("DOCKET_API_PORT", "3050")
DOCKET_WEB_PORT = get_env("DOCKET_WEB_PORT", "3000")
DOCKET_API_URL = f"http://127.0.0.1:{DOCKET_API_PORT}"
DOCKET_WEB_URL = f"http://127.0.0.1:{DOCKET_WEB_PORT}"

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

# Telegram poller (started later)
telegram_poller: Optional[TelegramPoller] = None

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
            # Check for video or audio files
            video_file = None
            audio_file = None

            for f in job.files:
                if f.endswith(('.mp4', '.avi', '.mov', '.gif')):
                    video_file = f
                    break
                elif f.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                    audio_file = f
                    break

            # Build fallback link
            link = None
            if PUBLIC_BASE_URL:
                link = f"{PUBLIC_BASE_URL}/api/jobs/{job.id}/result"

            if video_file:
                video_path = job_store.get_output_dir(job.id) / video_file
                caption = f"✅ Video ready!\n\nPrompt: {job.prompt}"
                telegram_api.send_video(chat_id, video_path, caption, link)
            elif audio_file:
                audio_path = job_store.get_output_dir(job.id) / audio_file
                caption = f"✅ Song ready!\n\n{job.prompt}"
                telegram_api.send_audio(chat_id, audio_path, caption, link)
            else:
                telegram_api.send_message(chat_id, f"✅ Job {job.id} completed but no media found.")

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
        "open_webui": get_docker_status("open-webui"),
        "docket_converter": get_docker_status("docket-converter")
    }

    stats = get_system_stats()

    return jsonify({
        "services": services,
        "stats": stats,
        "hostname": socket.gethostname(),
        "ip": request.host.split(':')[0],
        "docket_api_url": DOCKET_API_URL,
        "docket_web_url": DOCKET_WEB_URL
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
    if container not in ['open-webui', 'docket-converter']:
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

# ===== Docket Proxy Routes =====

@app.route('/docx/')
@app.route('/docx/<path:path>')
def docket_proxy(path=''):
    """Proxy requests to Docket web UI."""
    try:
        # Forward request to Docket web UI
        target_url = f"{DOCKET_WEB_URL}/{path}"

        # Forward query parameters
        if request.query_string:
            target_url += f"?{request.query_string.decode()}"

        # Make request
        resp = requests.get(target_url, timeout=10)

        # Return response
        return resp.content, resp.status_code, resp.headers.items()
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Docket service unavailable",
            "details": str(e)
        }), 503

@app.route('/api/docket/health', methods=['GET'])
def docket_health():
    """Check Docket API health."""
    try:
        resp = requests.get(f"{DOCKET_API_URL}/api/health", timeout=5)
        return jsonify({
            "reachable": resp.status_code == 200,
            "status": resp.status_code
        })
    except:
        return jsonify({
            "reachable": False,
            "status": None
        })

@app.route('/api/docket/convert', methods=['POST'])
def docket_convert():
    """Proxy conversion requests to Docket API."""
    try:
        # Forward POST request to Docket API
        target_url = f"{DOCKET_API_URL}/api/convert"

        # Get the request body
        body = request.get_json()
        if not body:
            return jsonify({
                "error": "Bad Request",
                "message": "Request body is required"
            }), 400

        # Forward the request body and headers
        resp = requests.post(
            target_url,
            json=body,
            headers={'Content-Type': 'application/json'},
            timeout=30  # Conversion can take time
        )

        # Return the response with appropriate headers
        response = make_response(resp.content, resp.status_code)
        response.headers['Content-Type'] = resp.headers.get('Content-Type', 'application/octet-stream')
        if 'Content-Disposition' in resp.headers:
            response.headers['Content-Disposition'] = resp.headers['Content-Disposition']
        return response
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Docket service unavailable",
            "details": str(e)
        }), 503

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

# ===== Configuration Routes =====

@app.route('/config')
def config_page():
    """Serve configuration page."""
    return render_template('config.html')

@app.route('/api/config/status', methods=['GET'])
def get_config_status():
    """Get current configuration status."""
    # Check if Telegram is configured
    telegram_configured = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_NAME)

    # Check if workflow exists
    workflow_configured = WORKFLOW_PATH.exists()
    workflow_mtime = None
    if workflow_configured:
        import datetime
        mtime = WORKFLOW_PATH.stat().st_mtime
        workflow_mtime = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

    # Check ComfyUI connection
    comfy_reachable = comfy_client.check_reachable()
    comfy_latency = comfy_client.get_latency_ms() if comfy_reachable else None

    return jsonify({
        "telegram": {
            "configured": telegram_configured,
            "bot_name": TELEGRAM_BOT_NAME if telegram_configured else None
        },
        "workflow": {
            "configured": workflow_configured,
            "filename": WORKFLOW_PATH.name if workflow_configured else None,
            "last_updated": workflow_mtime
        },
        "comfyui": {
            "url": COMFYUI_BASE_URL,
            "reachable": comfy_reachable,
            "latency_ms": comfy_latency
        }
    })

@app.route('/api/config/telegram', methods=['POST'])
def save_telegram_config():
    """Save Telegram configuration."""
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    bot_token = data.get('bot_token', '').strip()
    bot_name = data.get('bot_name', '').strip()
    default_chat_id = data.get('default_chat_id', '').strip()
    public_url = data.get('public_url', '').strip()

    if not bot_token or not bot_name:
        return jsonify({"success": False, "error": "bot_token and bot_name are required"}), 400

    # Save to environment file
    env_file = Path('/etc/server-dashboard.env')
    env_lines = []

    # Read existing env file if it exists
    if env_file.exists():
        with open(env_file, 'r') as f:
            env_lines = f.readlines()

    # Update or add Telegram variables
    telegram_vars = {
        'TELEGRAM_BOT_TOKEN': bot_token,
        'TELEGRAM_BOT_NAME': bot_name,
        'TELEGRAM_DEFAULT_CHAT_ID': default_chat_id,
        'PUBLIC_BASE_URL': public_url,
        'TELEGRAM_ENABLED': 'true'
    }

    # Update existing lines or collect new ones
    updated_vars = set()
    new_env_lines = []

    for line in env_lines:
        line = line.strip()
        if not line or line.startswith('#'):
            new_env_lines.append(line + '\n')
            continue

        if '=' in line:
            key = line.split('=', 1)[0].strip()
            if key in telegram_vars:
                new_env_lines.append(f'{key}={telegram_vars[key]}\n')
                updated_vars.add(key)
            else:
                new_env_lines.append(line + '\n')

    # Add any variables that weren't in the file
    for key, value in telegram_vars.items():
        if key not in updated_vars and value:
            new_env_lines.append(f'{key}={value}\n')

    # Write to temp file first (we don't have sudo access in Flask)
    temp_file = Path('./telegram_config.env')
    with open(temp_file, 'w') as f:
        f.writelines(new_env_lines)

    # Update in-memory globals (for immediate effect)
    global TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_NAME, TELEGRAM_DEFAULT_CHAT_ID, PUBLIC_BASE_URL, telegram_api
    TELEGRAM_BOT_TOKEN = bot_token
    TELEGRAM_BOT_NAME = bot_name
    TELEGRAM_DEFAULT_CHAT_ID = default_chat_id
    PUBLIC_BASE_URL = public_url

    # Reinitialize Telegram API
    telegram_api = TelegramAPI(bot_token)

    # Reinitialize webhook if blueprint is registered
    if telegram_api:
        init_webhook(
            telegram_api=telegram_api,
            telegram_enabled_func=runtime_config.get_telegram_enabled,
            enqueue_job_func=lambda job: (job_store.save(job), job_queue.enqueue(job)),
            storage_root=STORAGE_ROOT
        )

    # Restart poller with new config
    global telegram_poller
    print(f"[DEBUG] About to restart poller, current telegram_api={telegram_api}", flush=True)
    if telegram_poller:
        print("[DEBUG] Stopping existing poller", flush=True)
        telegram_poller.stop()
    print("[DEBUG] Calling init_telegram_poller()", flush=True)
    init_telegram_poller()
    print(f"[DEBUG] Finished init_telegram_poller(), telegram_poller={telegram_poller}", flush=True)

    return jsonify({
        "success": True,
        "message": "Telegram config saved and poller restarted! Try sending a message to your bot."
    })

@app.route('/api/config/telegram/test', methods=['POST'])
def test_telegram_config():
    """Test Telegram connection."""
    if not telegram_api:
        return jsonify({"success": False, "error": "Telegram not configured"}), 400

    try:
        # Get bot info
        response = telegram_api.session.get(f"{telegram_api.base_url}/getMe", timeout=10)
        response.raise_for_status()
        bot_info = response.json()

        if bot_info.get('ok'):
            return jsonify({
                "success": True,
                "bot_info": bot_info['result']
            })
        else:
            return jsonify({
                "success": False,
                "error": bot_info.get('description', 'Unknown error')
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/api/config/workflow', methods=['POST'])
def save_workflow_config():
    """Save workflow JSON."""
    data = request.get_json()

    if not data or 'workflow' not in data:
        return jsonify({"success": False, "error": "No workflow data provided"}), 400

    workflow_json = data['workflow']

    # Validate JSON
    try:
        if isinstance(workflow_json, str):
            workflow = json.loads(workflow_json)
        else:
            workflow = workflow_json
    except json.JSONDecodeError as e:
        return jsonify({"success": False, "error": f"Invalid JSON: {str(e)}"}), 400

    # Save workflow
    try:
        WORKFLOW_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(WORKFLOW_PATH, 'w') as f:
            json.dump(workflow, f, indent=2)

        # Restart worker to pick up new workflow
        global job_worker
        if job_worker:
            job_worker.stop()
            init_worker()

        return jsonify({
            "success": True,
            "message": "Workflow saved successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/config/comfyui', methods=['POST'])
def save_comfyui_config():
    """Save ComfyUI URL."""
    data = request.get_json()

    if not data or 'url' not in data:
        return jsonify({"success": False, "error": "No URL provided"}), 400

    url = data['url'].strip()

    # Update in-memory global
    global COMFYUI_BASE_URL, comfy_client
    COMFYUI_BASE_URL = url
    comfy_client = ComfyUIClient(url)

    # Update worker's client
    global job_worker
    if job_worker:
        job_worker.comfy_client = comfy_client

    # Save to temp config file
    temp_file = Path('./comfyui_config.env')
    with open(temp_file, 'w') as f:
        f.write(f'COMFYUI_BASE_URL={url}\n')

    return jsonify({
        "success": True,
        "message": "ComfyUI URL saved. Copy ./comfyui_config.env to /etc/server-dashboard.env for persistence."
    })

@app.route('/api/config/comfyui/test', methods=['POST'])
def test_comfyui_config():
    """Test ComfyUI connection."""
    try:
        latency = comfy_client.get_latency_ms()
        if latency is not None:
            return jsonify({
                "success": True,
                "latency_ms": latency
            })
        else:
            return jsonify({
                "success": False,
                "error": "Could not connect to ComfyUI"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
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
        print(f"[WARN] Workflow not found at {WORKFLOW_PATH}, worker not started", flush=True)
        return

    print(f"[INFO] Using workflow: {WORKFLOW_PATH}", flush=True)
    job_worker = JobWorker(
        queue=job_queue,
        store=job_store,
        comfy_client=comfy_client,
        workflow_path=WORKFLOW_PATH,
        telegram_send_func=send_telegram_notification,
        timeout_minutes=10
    )
    job_worker.start()
    print("[INFO] Job worker started", flush=True)

def init_telegram_poller():
    """Initialize and start Telegram poller."""
    global telegram_poller

    print(f"[DEBUG] init_telegram_poller called, telegram_api={telegram_api}, enabled={runtime_config.get_telegram_enabled()}", flush=True)

    if not telegram_api:
        print("[WARN] Telegram API not configured, poller not started", flush=True)
        return

    telegram_poller = TelegramPoller(
        telegram_api=telegram_api,
        telegram_enabled_func=runtime_config.get_telegram_enabled,
        enqueue_job_func=lambda job: (job_store.save(job), job_queue.enqueue(job)),
        storage_root=STORAGE_ROOT
    )
    telegram_poller.start()
    print("[INFO] Telegram poller started", flush=True)

# ===== Main =====

if __name__ == '__main__':
    # Initialize worker
    init_worker()

    # Initialize Telegram poller
    init_telegram_poller()

    # Run Flask
    host = get_env("DASHBOARD_BIND", "0.0.0.0")
    port = int(get_env("DASHBOARD_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
