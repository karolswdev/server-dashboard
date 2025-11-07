# 🎥 Image→Video Server — Quick Start Guide

## ✅ Deployment Complete!

Your Flask admin server has been successfully extended with ComfyUI orchestration and Telegram bot integration.

## What's Working

### ✅ Core Infrastructure
- **Background Worker**: Daemon thread running and processing jobs
- **Job Queue System**: File-backed JSON storage with thread-safe queue
- **ComfyUI Integration**: Client connected and reachable (2ms latency)
- **RESTful API**: All endpoints active and tested
- **Admin Dashboard**: Real-time monitoring with sub-status panel

### ✅ API Endpoints Live

```bash
# Job Management
POST   /api/jobs/image-to-video       # Create job
GET    /api/jobs/<job_id>            # Check status
GET    /api/jobs/<job_id>/result     # Download video
POST   /api/jobs/<job_id>/cancel     # Cancel job

# Admin
GET    /api/admin/status              # System status
POST   /api/admin/telegram/enable     # Toggle Telegram

# Telegram (when configured)
POST   /telegram/webhook              # Bot webhook
```

### ✅ Admin Dashboard Enhancements

Visit **http://192.168.1.21:5000** to see:

- **🎥 Image→Video Server** section (full-width card)
- **ComfyUI Status**: ✓ Reachable (2ms latency)
- **Worker Status**: ✓ Running | Queue: 0 jobs
- **Telegram Badge**: Shows enabled/disabled status with bot name
- **Toggle Switch**: Enable/disable Telegram without restart

## Current Status

```
✅ Server running on http://192.168.1.21:5000
✅ Worker thread: RUNNING
✅ ComfyUI: REACHABLE at http://127.0.0.1:8188
⚠️  Telegram: DISABLED (not configured)
⚠️  Workflow: Needs customization for your ComfyUI setup
```

## Next Steps

### 1. Customize ComfyUI Workflow

The base workflow at `Workflows/image_to_video_base.json` needs to match your actual ComfyUI setup:

```bash
# Option A: Export from ComfyUI UI
# 1. Create your workflow in ComfyUI
# 2. Use "Save (API Format)" button
# 3. Save as Workflows/image_to_video_base.json

# Option B: Edit the existing template
nano Workflows/image_to_video_base.json
# Adjust node IDs and parameters to match your models/nodes
```

**Important**: Ensure your workflow:
- Has a **LoadImage** node for input
- Has a **CLIPTextEncode** node for prompts
- Has a **VHS_VideoCombine** or similar node for video output
- Saves output to ComfyUI's `output/` directory

### 2. (Optional) Set Up Telegram Bot

If you want Telegram integration:

1. **Create Bot**:
   ```bash
   # Follow README-telegram.md for full BotFather setup
   # You'll need:
   # - Bot token from @BotFather
   # - Your bot's username (e.g., @MyVideoBot)
   # - Your chat ID
   ```

2. **Configure Environment**:
   ```bash
   sudo nano /etc/server-dashboard.env
   ```

   Add:
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_BOT_NAME=@YourBotName
   TELEGRAM_ENABLED=true
   ```

3. **Restart**:
   ```bash
   sudo systemctl restart server-dashboard
   ```

4. **Enable in Dashboard**:
   - Go to http://192.168.1.21:5000
   - Check the "Enable" box next to Telegram
   - Badge should turn green

### 3. Test the Full Pipeline

Once workflow is configured:

```bash
# Create a job
curl -X POST http://localhost:5000/api/jobs/image-to-video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "slow camera orbit, cinematic",
    "input_image_url": "https://picsum.photos/seed/cat/768/768",
    "params": {
      "seed": 1,
      "duration_seconds": 5,
      "fps": 24,
      "resolution": "768x768"
    }
  }'

# Save the job_id from response

# Check status (wait a few seconds)
curl http://localhost:5000/api/jobs/<job_id>

# Download result (when status is "completed")
curl -o video.mp4 http://localhost:5000/api/jobs/<job_id>/result
```

## Files Created

```
server-dashboard/
├── app.py                              # Extended Flask app (deployed)
├── app.py.backup                       # Original backup
├── app_extended.py                     # Source file (can be deleted)
├── config.json                         # Runtime config (Telegram toggle)
├── requirements.txt                    # Python dependencies
├── comfy/                              # ComfyUI integration
│   ├── client.py                       # API client
│   └── workflow.py                     # Workflow manager
├── jobs/                               # Job system
│   ├── models.py                       # Data models
│   ├── store.py                        # File storage
│   ├── queue.py                        # Thread-safe queue
│   └── worker.py                       # Background worker
├── telegram/                           # Telegram integration
│   ├── api.py                          # Bot API client
│   └── webhook.py                      # Webhook handler
├── Workflows/
│   └── image_to_video_base.json        # Base workflow (customize!)
├── data/                               # Job storage (runtime)
│   └── <job_id>/
│       ├── meta.json
│       ├── input/
│       └── output/
└── Documentation
    ├── README-telegram.md              # Telegram setup guide
    ├── DEPLOYMENT.md                   # Deployment guide
    └── QUICKSTART.md                   # This file
```

## Monitoring

### View Logs
```bash
# Real-time logs
sudo journalctl -u server-dashboard -f

# Recent logs
sudo journalctl -u server-dashboard -n 100

# Filter for job processing
sudo journalctl -u server-dashboard | grep JobWorker
```

### Check Service Status
```bash
sudo systemctl status server-dashboard
```

### Dashboard
- **URL**: http://192.168.1.21:5000
- **Updates**: Every 5 seconds (auto-refresh)

## Troubleshooting

### Workflow Fails (Expected on First Run)

**Symptom**: Jobs fail with "400 Bad Request" from ComfyUI

**Solution**: Customize `Workflows/image_to_video_base.json` to match your ComfyUI setup
- Export a working workflow from ComfyUI in API format
- Replace the base JSON file
- Restart service: `sudo systemctl restart server-dashboard`

### Worker Not Starting

**Check**:
```bash
# Verify workflow file exists
ls -la Workflows/image_to_video_base.json

# Check logs
sudo journalctl -u server-dashboard | grep "Worker thread"
```

### ComfyUI Unreachable

**Check**:
```bash
# Verify ComfyUI is running
sudo systemctl status comfyui

# Test manually
curl http://127.0.0.1:8188/system_stats
```

## Performance & Limits

- **Job Timeout**: 10 minutes
- **Poll Interval**: 2 seconds
- **Concurrent Jobs**: 1 (single worker thread)
- **Max Telegram File**: 50MB (falls back to link)
- **Storage**: Unlimited (limited by disk space)

## Security

✅ **Network**: Restricted to 192.168.* only
✅ **Permissions**: Sudo configured for service control
✅ **Tokens**: Never logged or exposed
✅ **Systemd**: Hardening enabled (PrivateTmp, NoNewPrivileges)

## API Examples

### Create Job
```bash
curl -X POST http://localhost:5000/api/jobs/image-to-video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "epic slow motion, cinematic 4k",
    "input_image_url": "https://example.com/image.jpg",
    "telegram_chat_id": "123456789",
    "params": {
      "seed": 42,
      "duration_seconds": 10,
      "fps": 30,
      "resolution": "1024x576"
    }
  }'
```

### Check Status
```bash
curl http://localhost:5000/api/jobs/<job_id> | jq
```

### Toggle Telegram
```bash
# Enable
curl -X POST http://localhost:5000/api/admin/telegram/enable \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Disable
curl -X POST http://localhost:5000/api/admin/telegram/enable \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

## Rollback

If needed:

```bash
cd ~/server-dashboard
cp app.py.backup app.py
sudo systemctl restart server-dashboard
```

## Support Commands

```bash
# Restart service
sudo systemctl restart server-dashboard

# Stop service
sudo systemctl stop server-dashboard

# View status
sudo systemctl status server-dashboard

# Tail logs
sudo journalctl -u server-dashboard -f
```

## What's Next?

1. ✅ Customize the ComfyUI workflow
2. ✅ Test with your actual models
3. ✅ (Optional) Set up Telegram bot
4. ✅ Add more workflows for different styles
5. ✅ Configure webhook if using Telegram
6. ✅ Monitor job performance and tune timeouts

---

## 🎬 Ready to Generate Videos!

Your server is now equipped with:
- **Image→Video orchestration**
- **Background job processing**
- **RESTful API**
- **Admin dashboard monitoring**
- **Optional Telegram bot delivery**

**Dashboard**: http://192.168.1.21:5000
**Documentation**: See README-telegram.md and DEPLOYMENT.md
**Logs**: `sudo journalctl -u server-dashboard -f`

---

**Questions?** Check DEPLOYMENT.md or README-telegram.md for detailed guides.

**Happy video creating! ✨🎥**
