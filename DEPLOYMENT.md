# Image→Video Server Deployment Guide

This guide explains how to deploy the extended server dashboard with ComfyUI orchestration and Telegram bot integration.

## What's New

The server dashboard now includes:

✅ **Image→Video Job System**
- Queue-based job processing with background worker thread
- ComfyUI integration for Stable Video Diffusion
- RESTful API for creating and monitoring jobs
- File-backed job storage with metadata

✅ **Telegram Bot Integration**
- Send images and prompts via Telegram
- Receive videos directly in your chat
- Toggleable on/off switch from admin dashboard
- Webhook support for real-time updates

✅ **Enhanced Admin Dashboard**
- Real-time ComfyUI status monitoring
- Worker thread status and job queue metrics
- Telegram bot status badge with toggle
- Sub-status panel for all components

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Flask Admin Server (app.py)                             │
│ ┌────────────┐  ┌────────────┐  ┌─────────────────┐   │
│ │ Job API    │  │ Admin API  │  │ Telegram        │   │
│ │ Endpoints  │  │ Endpoints  │  │ Webhook         │   │
│ └────────────┘  └────────────┘  └─────────────────┘   │
│                                                         │
│ ┌─────────────────────────────────────────────────┐   │
│ │ Background Worker (daemon thread)                │   │
│ │  • Dequeues jobs                                 │   │
│ │  • Downloads input images                        │   │
│ │  • Calls ComfyUI API                             │   │
│ │  • Polls for completion                          │   │
│ │  • Downloads output videos                       │   │
│ │  • Sends Telegram notifications                  │   │
│ └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ ComfyUI Server         │
              │ (Stable Video          │
              │  Diffusion)            │
              └────────────────────────┘
```

## Files Changed/Added

### New Modules

- `comfy/client.py` - ComfyUI REST API client
- `comfy/workflow.py` - Workflow loading and parameter overrides
- `jobs/models.py` - Job data models and enums
- `jobs/store.py` - File-backed job storage
- `jobs/queue.py` - Thread-safe job queue
- `jobs/worker.py` - Background worker thread
- `telegram/api.py` - Telegram Bot API client
- `telegram/webhook.py` - Telegram webhook handler (Flask blueprint)

### Modified Files

- `app.py` → `app_extended.py` (backup created)
- `templates/index.html` - Added Image→Video Server section
- `/etc/systemd/system/server-dashboard.service` - Updated with environment file support

### New Files

- `Workflows/image_to_video_base.json` - Base ComfyUI workflow
- `config.json` - Runtime configuration
- `requirements.txt` - Python dependencies
- `server-dashboard.env.template` - Environment variables template
- `README-telegram.md` - Telegram bot setup guide
- `DEPLOYMENT.md` - This file

## Prerequisites

Before deploying, ensure:

1. ✅ ComfyUI is installed and running on port 8188
2. ✅ Stable Video Diffusion model (`svd_xt.safetensors`) is downloaded
3. ✅ ComfyUI-VideoHelperSuite custom node is installed
4. ✅ Python venv is set up at `~/server-dashboard/venv`

## Quick Deployment

```bash
cd ~/server-dashboard

# 1. Backup original app.py
cp app.py app.py.backup

# 2. Replace with extended version
cp app_extended.py app.py

# 3. Install dependencies (if not already installed)
source venv/bin/activate
pip install -r requirements.txt

# 4. Create environment file (optional - for Telegram)
sudo cp server-dashboard.env.template /etc/server-dashboard.env
# Edit /etc/server-dashboard.env with your settings

# 5. Update systemd service
sudo cp /tmp/server-dashboard.service.new /etc/systemd/system/server-dashboard.service
sudo systemctl daemon-reload

# 6. Restart service
sudo systemctl restart server-dashboard

# 7. Check status
sudo systemctl status server-dashboard
```

## Configuration

### Minimal (No Telegram)

No configuration needed! The server will run with default settings:
- ComfyUI at `http://127.0.0.1:8188`
- Storage in `./data`
- Telegram disabled

### With Telegram

1. Create `/etc/server-dashboard.env`:

```bash
COMFYUI_BASE_URL=http://127.0.0.1:8188
STORAGE_ROOT=/home/karol/server-dashboard/data
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_BOT_NAME=@YourBotName
TELEGRAM_ENABLED=true
```

2. Follow `README-telegram.md` for BotFather setup

## Verification

### 1. Check Admin Dashboard

Open `http://192.168.1.21:5000` and verify:

- ✅ "🎥 Image→Video Server" section is visible
- ✅ ComfyUI status shows "✓ Reachable"
- ✅ Worker status shows "✓ Running"
- ✅ Telegram badge shows "Disabled" (or "Enabled" if configured)

### 2. Test Job API

```bash
curl -X POST http://localhost:5000/api/jobs/image-to-video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "slow camera orbit, cinematic",
    "input_image_url": "https://picsum.photos/seed/test/768/768",
    "params": {
      "seed": 1,
      "duration_seconds": 5,
      "fps": 24,
      "resolution": "768x768"
    }
  }'
```

Expected response:
```json
{
  "job_id": "abc123-...",
  "status_url": "http://localhost:5000/api/jobs/abc123-.../",
  "result_url": "http://localhost:5000/api/jobs/abc123-.../result"
}
```

### 3. Monitor Job

```bash
# Check job status
curl http://localhost:5000/api/jobs/abc123-.../

# Watch logs
sudo journalctl -u server-dashboard -f
```

### 4. Download Result

Once status is "completed":

```bash
curl -o video.mp4 http://localhost:5000/api/jobs/abc123-.../result
```

## Troubleshooting

### Worker not starting

**Symptom**: Worker status shows "✗ Stopped"

**Solution**:
```bash
# Check if workflow file exists
ls -la Workflows/image_to_video_base.json

# Check logs
sudo journalctl -u server-dashboard -f
```

### ComfyUI unreachable

**Symptom**: ComfyUI status shows "✗ Unreachable"

**Solution**:
```bash
# Check ComfyUI service
sudo systemctl status comfyui

# Test ComfyUI API
curl http://127.0.0.1:8188/system_stats
```

### Job fails with "model not found"

**Solution**:
```bash
# Check if SVD model exists
ls -la ~/ComfyUI/models/checkpoints/svd_xt.safetensors

# Download if missing
cd ~/ComfyUI/models/checkpoints
wget https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt/resolve/main/svd_xt.safetensors
```

### Telegram webhook not working

See `README-telegram.md` for detailed troubleshooting.

## API Endpoints Reference

### Job Management

```
POST   /api/jobs/image-to-video    Create new job
GET    /api/jobs/<job_id>          Get job status
GET    /api/jobs/<job_id>/result   Download result video
POST   /api/jobs/<job_id>/cancel   Cancel job
```

### Admin

```
GET    /api/admin/status           Get system status
POST   /api/admin/telegram/enable  Toggle Telegram on/off
```

### Telegram

```
POST   /telegram/webhook           Telegram webhook endpoint
```

## Rollback

If you need to rollback:

```bash
cd ~/server-dashboard

# 1. Restore original app.py
cp app.py.backup app.py

# 2. Restart service
sudo systemctl restart server-dashboard
```

## Performance Notes

- **Job timeout**: 10 minutes (configurable in `jobs/worker.py`)
- **Poll interval**: 2 seconds (configurable in `jobs/worker.py`)
- **Max file size (Telegram)**: 50MB (Telegram limit)
- **Concurrent jobs**: 1 worker thread (can be extended for multiple workers)

## Security

- ✅ Admin dashboard restricted to 192.168.* network
- ✅ No password required for sudo commands (configured in `/etc/sudoers.d/`)
- ✅ Telegram bot token never logged
- ✅ File paths validated and sanitized
- ✅ Systemd hardening enabled (PrivateTmp, NoNewPrivileges)

## Support

- **Logs**: `sudo journalctl -u server-dashboard -f`
- **Status**: `sudo systemctl status server-dashboard`
- **Restart**: `sudo systemctl restart server-dashboard`
- **Stop**: `sudo systemctl stop server-dashboard`

## Next Steps

1. ✅ Deploy the system
2. ✅ Test job API with curl
3. ✅ (Optional) Set up Telegram bot
4. ✅ Customize workflow in `Workflows/image_to_video_base.json`
5. ✅ Add more video models to ComfyUI

---

**Ready to generate videos! 🎬✨**
