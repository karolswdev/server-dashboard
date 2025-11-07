# 📱 Telegram Bot - How to Use

Your Wan2.2 Image→Video workflow is now integrated with the Telegram bot!

## 🎯 How It Works

### The Prompt Flow

**Your Workflow Structure:**
- **Node 97** (LoadImage) - Receives your uploaded image
- **Node 116** (Wan2.2 Subgraph) - Main processing node
  - `widgets_values[0]` = **Your prompt** ← Injected here!
  - `widgets_values[1]` = Width (1280)
  - `widgets_values[2]` = Height (720)
  - `widgets_values[3]` = Frames (81 frames @ 16 fps = 5 seconds)
- **Node 108** (SaveVideo) - Outputs the final video

When you send a message via Telegram, the system:
1. Downloads your image from Telegram
2. Extracts your prompt from the `/im2vid` command
3. Injects the prompt into Node 116's `widgets_values[0]`
4. Runs the workflow in ComfyUI
5. Downloads the generated video
6. Sends it back to you on Telegram!

---

## 📝 Usage Examples

### Basic Usage

```
/im2vid slow camera orbit, cinematic lighting
```
*Attach an image to the message*

**Result:** Video with slow camera movement and cinematic look

---

### Advanced Examples

#### 1. Action Scene
```
/im2vid person jumps off a building, doing a backflip mid-air, landing smoothly
```

#### 2. Nature Scene
```
/im2vid waves crashing on the beach, seagulls flying overhead, sunset colors
```

#### 3. Portrait Animation
```
/im2vid woman smiling and waving at camera, hair blowing in gentle breeze
```

#### 4. Fantasy/Creative
```
/im2vid magical sparkles appear around the object, glowing ethereal light, mystical atmosphere
```

---

## ⚙️ Default Parameters

When you don't specify, these defaults from your workflow are used:

| Parameter | Default Value | What it means |
|-----------|---------------|---------------|
| Width | 1280px | Video width |
| Height | 720px | Video height |
| Frames | 81 | Total frames |
| FPS | 16 | Frames per second |
| Duration | ~5 seconds | 81 frames ÷ 16 fps |

---

## 🎨 Prompt Tips for Wan2.2

Based on your workflow's capabilities:

### ✅ Good Prompts
- Describe **motion and action**: "person walking", "waves moving", "clouds drifting"
- Include **camera movement**: "slow zoom out", "pan left", "camera orbit"
- Add **atmosphere**: "cinematic", "dramatic lighting", "soft glow"
- Be **specific about action**: "person turns head", "object rotates clockwise"

### ❌ Avoid
- Static descriptions: "a beautiful landscape" (no motion)
- Too many actions: "person runs, jumps, flies, and spins" (confusing)
- Abstract concepts without motion: "happiness" or "peace"

### 🌟 Proven Examples

From your workflow's default prompt:
> "The girl does a back flip, clapping after doing so"

Good structure:
1. Subject ("The girl")
2. Main action ("does a back flip")
3. Secondary action ("clapping after doing so")

---

## 🔧 Customizing Parameters (via API)

If you want custom resolution/duration, you can use the API directly:

```bash
curl -X POST http://192.168.1.21:5000/api/jobs/image-to-video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "slow camera orbit, cinematic lighting",
    "input_image_url": "https://example.com/image.jpg",
    "telegram_chat_id": "YOUR_CHAT_ID",
    "params": {
      "resolution": "1280x720",
      "fps": 16,
      "duration_seconds": 8
    }
  }'
```

This will generate a longer video (8 seconds = 128 frames).

---

## 📊 What Happens Behind the Scenes

```
You send message
    ↓
Telegram Bot receives:
  - Image (downloaded from Telegram)
  - Prompt: "/im2vid slow camera orbit"
    ↓
Job created:
  - prompt = "slow camera orbit"
  - input_image = telegram://path/to/image
    ↓
Worker thread:
  1. Downloads image to data/{job_id}/input/
  2. Uploads to ComfyUI
  3. Loads your workflow
  4. Injects prompt → Node 116 widgets_values[0]
  5. Sends to ComfyUI /prompt endpoint
    ↓
ComfyUI processes:
  - Loads Wan2.2 14B models (high + low noise)
  - Applies 4-step LoRA
  - Encodes your prompt with CLIP
  - Generates 81 frames
  - Saves video to output/
    ↓
Worker thread:
  - Polls ComfyUI /history every 2 seconds
  - Downloads completed video
  - Saves to data/{job_id}/output/
    ↓
Telegram delivery:
  - Sends video back to your chat
  - Or sends link if file >50MB
```

---

## 🚨 Important Notes

### VRAM Requirements
Your Wan2.2 workflow requires **20GB+ VRAM**. You have:
- RTX 4070 Ti: **12GB VRAM**

⚠️ **This may cause issues!** The workflow uses fp8 quantization to reduce VRAM, but you might still hit limits.

**If jobs fail with OOM (Out of Memory):**
1. Use the dashboard's "Kill Models" button to free VRAM
2. Or use smaller image resolutions
3. Or consider using a lighter workflow

### Processing Time
- Wan2.2 with 4-step LoRA is optimized for speed
- Typical generation: **~2-4 minutes** per video
- Depends on your GPU and current load

### File Sizes
- 1280x720, 81 frames ≈ **5-20MB** (compressed)
- Telegram limit: 50MB
- If larger → you'll get a download link instead

---

## 🎬 Ready to Create!

1. **Set up your Telegram bot** (see `README-telegram.md`)
2. **Start a chat** with your bot
3. **Send** `/im2vid <your creative prompt>` with an image
4. **Wait** ~2-4 minutes
5. **Receive** your AI-generated video!

---

## 🔗 Quick Links

- **Dashboard:** http://192.168.1.21:5000
- **Configuration:** http://192.168.1.21:5000/config
- **ComfyUI:** http://192.168.1.21:8188
- **Bot Setup Guide:** `README-telegram.md`

---

**Happy video creating! 🎥✨**
