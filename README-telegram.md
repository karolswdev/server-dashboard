# Telegram Bot Setup Guide

This guide explains how to set up the Telegram bot for the Image→Video server to receive images and prompts via Telegram and get videos delivered directly to your chat.

## Prerequisites

- Server is running and accessible
- ComfyUI is installed and running
- Admin dashboard is accessible at `http://192.168.1.21:5000`

## Step 1: Create Bot with BotFather

1. Open Telegram and search for `@BotFather`
2. Start a conversation: `/start`
3. Create a new bot: `/newbot`
4. Choose a **display name** for your bot (e.g., `Image2Video Assistant`)
5. Choose a **username** ending with `bot` (e.g., `MyImage2VideoBot`)
6. BotFather will reply with your **Bot Token** - save this securely!

Example token: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

## Step 2: Set Bot Commands (Optional)

This makes commands appear in the Telegram UI for easier use:

1. In BotFather, send: `/setcommands`
2. Select your bot from the list
3. Paste the following commands:

```
im2vid - Generate a video from an image with a prompt
help - Show usage instructions
```

## Step 3: Get Your Chat ID

You need your Chat ID to receive messages from the bot:

1. Start a conversation with your bot (search for its username in Telegram)
2. Send any message to it (e.g., "hello")
3. Open this URL in your browser (replace `YOUR_BOT_TOKEN`):

```
https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
```

4. Look for the `"chat":{"id":` field - that's your Chat ID (e.g., `123456789`)

## Step 4: Configure Environment Variables

Add these to your environment file (`/etc/server-dashboard.env`):

```bash
# Required
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_BOT_NAME=@MyImage2VideoBot

# Optional
TELEGRAM_ENABLED=true
TELEGRAM_DEFAULT_CHAT_ID=123456789
```

## Step 5: Set Up Webhook (Recommended)

For instant message delivery, configure a webhook:

### Prerequisites:
- Your server must be accessible from the internet
- You need a public domain or IP with HTTPS (required by Telegram)
- Set `PUBLIC_BASE_URL` environment variable

### Configure Webhook:

Open this URL in your browser (replace placeholders):

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<PUBLIC_BASE_URL>/telegram/webhook
```

Example:
```
https://api.telegram.org/bot123456789:ABC.../setWebhook?url=https://example.com/telegram/webhook
```

You should see:
```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

### Verify Webhook:

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
```

### Remove Webhook (if needed):

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/deleteWebhook
```

## Step 6: Restart Server

```bash
sudo systemctl restart server-dashboard
```

## Step 7: Enable Telegram in Dashboard

1. Open `http://192.168.1.21:5000` in your browser
2. Find the "🎥 Image→Video Server" section
3. Check the **"Enable"** checkbox next to Telegram
4. The badge should turn green and show your bot name

## Using the Bot

### Generate Video from Image

1. Send `/im2vid <your prompt>` with an attached image
2. Example: `/im2vid slow camera orbit, cinematic lighting`
3. The bot will reply with a job ID
4. When complete, you'll receive the video in the chat

### Get Help

Send `/help` to see usage instructions

## Troubleshooting

### Bot doesn't respond

- Check that `TELEGRAM_ENABLED=true` in environment
- Verify bot token is correct
- Check server logs: `sudo journalctl -u server-dashboard -f`
- Ensure webhook is properly configured

### "Bot disabled" message

- Enable Telegram in the admin dashboard
- Or set `TELEGRAM_ENABLED=true` and restart service

### Video not received

- Check ComfyUI is running and reachable
- Check job status in logs
- Video may be too large (50MB limit) - fallback link will be sent

### Webhook not working

- Ensure PUBLIC_BASE_URL is set correctly
- Telegram requires HTTPS for webhooks
- Check firewall allows HTTPS traffic
- Verify webhook URL: `getWebhookInfo` endpoint

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes* | - | Bot token from BotFather |
| `TELEGRAM_BOT_NAME` | Yes* | - | Bot username (e.g., @MyBot) |
| `TELEGRAM_ENABLED` | No | `false` | Enable/disable at startup |
| `TELEGRAM_DEFAULT_CHAT_ID` | No | - | Default chat for notifications |
| `PUBLIC_BASE_URL` | No | - | Public URL for file downloads |

*Required only if using Telegram features

## Security Notes

- Keep your bot token secret
- Bot only accepts commands from authenticated users
- Server restricts access to local network (192.168.*)
- Webhook uses HTTPS encryption
- No sensitive data is logged

## Advanced: Polling Mode (Alternative to Webhook)

If you can't use webhooks, you can implement polling mode:

1. Remove webhook: `deleteWebhook` API call
2. Implement a polling loop in a separate script
3. Call `getUpdates` API periodically
4. Process updates manually

Note: Webhook mode is recommended for better performance and real-time delivery.

## Support

For issues or questions:
- Check server logs: `sudo journalctl -u server-dashboard -f`
- Verify configuration in `/etc/server-dashboard.env`
- Test API endpoints directly with curl
- Contact your system administrator

## Example Usage

```
User: [sends image] /im2vid epic slow-motion explosion, cinematic 4k

Bot: ✅ Job queued: abc123-def456-789
     Prompt: epic slow-motion explosion, cinematic 4k
     Your video will be sent here when ready!

[2 minutes later]

Bot: [sends video] ✅ Video ready!
     Prompt: epic slow-motion explosion, cinematic 4k
```

## API Testing

Test the bot without Telegram:

```bash
curl -X POST http://localhost:5000/api/jobs/image-to-video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "slow camera orbit, cinematic",
    "input_image_url": "https://example.com/image.jpg",
    "telegram_chat_id": "123456789",
    "params": {
      "seed": 1,
      "duration_seconds": 5,
      "fps": 24,
      "resolution": "768x768"
    }
  }'
```

---

**Happy video generating! 🎥✨**
