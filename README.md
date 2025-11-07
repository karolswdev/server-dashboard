# Server Dashboard

A Flask-based web dashboard for managing local server services with ComfyUI integration and Telegram bot support for automated image-to-video generation.

## Features

- 🎛️ **Service Management**: Control systemd services (Ollama, ComfyUI, Sunshine) and Docker containers
- 📊 **System Monitoring**: Real-time CPU, memory, disk, and GPU stats
- 🎥 **Image-to-Video Pipeline**: Background job queue with ComfyUI orchestration
- 🤖 **Telegram Bot**: Send images and prompts via Telegram, receive videos back
- 🔒 **Local Network Security**: Built-in access control for local network use
- ⚙️ **Web Configuration**: Configure services through the web UI

## Architecture

```
┌─────────────────────────────────────┐
│      Flask Dashboard (Port 5000)    │
│                                     │
│  - Service Control                  │
│  - System Monitoring                │
│  - Job Queue Management             │
│  - Telegram Bot Integration         │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│      Background Job Worker          │
│                                     │
│  - Processes image-to-video jobs    │
│  - Communicates with ComfyUI        │
│  - Sends Telegram notifications     │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│         ComfyUI Backend             │
│                                     │
│  - AI/ML video generation           │
│  - Custom workflow execution        │
└─────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- ComfyUI installed and running
- systemd-based Linux system
- Docker (optional, for open-webui)
- Telegram account (optional)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/server-dashboard.git
   cd server-dashboard
   ```

2. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp server-dashboard.env.template /etc/server-dashboard.env
   sudo nano /etc/server-dashboard.env
   ```

5. **Set up directories**:
   ```bash
   mkdir -p data Workflows
   ```

6. **Run the dashboard**:
   ```bash
   python app.py
   ```

7. **Access the dashboard**:
   ```
   http://localhost:5000
   ```

## Configuration

### Environment Variables

Edit `/etc/server-dashboard.env`:

```bash
# Flask Configuration
DASHBOARD_BIND=0.0.0.0
DASHBOARD_PORT=5000

# ComfyUI Configuration
COMFYUI_BASE_URL=http://127.0.0.1:8188

# Storage
STORAGE_ROOT=./data
WORKFLOW_PATH=./Workflows/image_to_video_base.json

# Telegram (optional)
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_BOT_NAME=@YourBotName
TELEGRAM_DEFAULT_CHAT_ID=

# Public URL for webhooks (optional)
PUBLIC_BASE_URL=
```

### ComfyUI Workflow

The dashboard requires a ComfyUI workflow in API format:

1. Create your workflow in ComfyUI
2. Export using "Save (API Format)"
3. Save to `./Workflows/image_to_video_base.json`

Your workflow must include:
- **LoadImage** node for input
- **CLIPTextEncode** node for prompts
- Video output node (e.g., VHS_VideoCombine)

### Telegram Bot Setup

See [README-telegram.md](README-telegram.md) for detailed Telegram configuration.

Quick setup:
1. Get bot token from @BotFather
2. Add to environment configuration
3. Enable via dashboard or set `TELEGRAM_ENABLED=true`

## Usage

### Web Dashboard

Access at `http://localhost:5000`:

- **Service Control**: Start/stop/restart services
- **System Stats**: Monitor CPU, memory, GPU usage
- **Job Management**: View active and completed jobs
- **Configuration**: Set up Telegram and ComfyUI

### API Endpoints

#### Job Management

```bash
# Create image-to-video job
POST /api/jobs/image-to-video
{
  "prompt": "A beautiful sunset",
  "input_image_url": "http://example.com/image.jpg",
  "params": {
    "seed": 42,
    "duration_seconds": 2,
    "fps": 8,
    "resolution": "512x512"
  }
}

# Get job status
GET /api/jobs/{job_id}

# Download result
GET /api/jobs/{job_id}/result

# Cancel job
POST /api/jobs/{job_id}/cancel
```

#### Service Control

```bash
# Control systemd services
POST /api/service/{service}/{action}
# service: ollama, comfyui, sunshine
# action: start, stop, restart

# Control Docker containers
POST /api/docker/{container}/{action}
# container: open-webui
# action: start, stop, restart
```

#### System Status

```bash
# Get all service statuses
GET /api/status

# Get admin panel status
GET /api/admin/status
```

### Telegram Bot

Once configured, send messages to your bot:

```
/im2vid <prompt>
```

Then upload an image. The bot will:
1. Queue the job
2. Process via ComfyUI
3. Send you the generated video

## Security

**⚠️ IMPORTANT**: This dashboard is designed for **local network use only**.

- Built-in access control limits requests to local IPs
- Never expose directly to the internet without additional authentication
- Use VPN for remote access
- See [SECURITY.md](SECURITY.md) for detailed security guidelines

### Key Security Practices

- **Never commit** `.env` files with real credentials
- Use environment variables for all sensitive data
- Protect environment files: `sudo chmod 600 /etc/server-dashboard.env`
- Limit sudo permissions to specific commands only
- Keep dependencies updated

## Development

### Project Structure

```
server-dashboard/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── server-dashboard.env.template  # Environment template
├── comfy/                      # ComfyUI client modules
│   ├── client.py
│   └── workflow.py
├── jobs/                       # Job queue system
│   ├── models.py
│   ├── queue.py
│   ├── store.py
│   └── worker.py
├── telegram/                   # Telegram bot integration
│   ├── api.py
│   ├── poller.py
│   └── webhook.py
├── templates/                  # HTML templates
│   ├── index.html
│   └── config.html
├── static/                     # CSS, JS, images
├── data/                       # Job storage (gitignored)
└── Workflows/                  # ComfyUI workflows (gitignored)
```

### Running Tests

```bash
# TODO: Add test suite
python -m pytest tests/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Troubleshooting

### Dashboard won't start

```bash
# Check if port is in use
sudo lsof -i :5000

# Check environment file
cat /etc/server-dashboard.env

# Check logs
sudo journalctl -u server-dashboard
```

### ComfyUI not reachable

```bash
# Verify ComfyUI is running
curl http://127.0.0.1:8188/system_stats

# Check URL in environment
grep COMFYUI_BASE_URL /etc/server-dashboard.env
```

### Jobs failing

```bash
# Check worker logs in dashboard
# Verify workflow file exists
ls -la Workflows/image_to_video_base.json

# Test ComfyUI workflow manually
```

### Telegram not working

```bash
# Test bot token
curl https://api.telegram.org/bot<TOKEN>/getMe

# Check webhook status
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo

# Enable debug logging in poller.py
```

## Documentation

- [Quick Start Guide](QUICKSTART.md) - Detailed setup walkthrough
- [Telegram Setup](README-telegram.md) - Telegram bot configuration
- [Deployment Guide](DEPLOYMENT.md) - Production deployment
- [Security Guidelines](SECURITY.md) - Security best practices
- [Telegram Usage](TELEGRAM_USAGE.md) - How to use the bot

## License

MIT License - See LICENSE file for details

## Acknowledgments

- Built with [Flask](https://flask.palletsprojects.com/)
- ComfyUI integration via REST API
- Telegram Bot API
- System monitoring with [psutil](https://github.com/giampaolo/psutil)

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing documentation
- Review logs for error messages
