# AI Content Pipeline

A fully local Python pipeline for automating content creation workflows.

**Raw Video → Transcribe → Caption → Translate → Clip → Export**

All processing runs on your machine — no API keys, no cloud costs, no rate limits.

## Features

- **Speech-to-text** — OpenAI Whisper (local, GPU-accelerated)
- **Styled captions** — TikTok/Reels/YouTube style with word-by-word highlighting
- **Translation** — 30+ languages via Argos Translate (fully offline)
- **Auto-clipping** — Detect highlights via speech pauses or local LLM
- **Fast export** — FFmpeg with optional NVIDIA GPU encoding

## Quick Start

### 1. Install system dependencies

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows
choco install ffmpeg
```

### 2. Install Python packages

```bash
pip install -r requirements.txt
```

### 3. Run the pipeline

```bash
# Basic: transcribe + burn styled captions
python main.py --input video.mp4

# Full pipeline
python main.py --input video.mp4 --translate es --style tiktok --clip --word-highlight

# Just generate subtitles (no video encoding)
python main.py --input video.mp4 --srt-only
```

## Usage Examples

```bash
# TikTok-style word highlighting
python main.py -i video.mp4 --style tiktok --word-highlight

# Translate to Spanish with YouTube-style captions
python main.py -i video.mp4 --translate es --style youtube

# Auto-clip + translate to French
python main.py -i video.mp4 --clip --translate fr

# Use the large Whisper model for max accuracy
python main.py -i video.mp4 --model large

# GPU-accelerated encoding
python main.py -i video.mp4 --gpu

# Use a local LLM to find highlights
python main.py -i video.mp4 --clip --clip-method llm
```

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--input, -i` | Input video path | *required* |
| `--output, -o` | Output video path | auto |
| `--model, -m` | Whisper model (tiny/base/small/medium/large) | medium |
| `--language` | Source language code (None = auto-detect) | None |
| `--style, -s` | Caption style (tiktok/youtube/reels/minimal/srt) | tiktok |
| `--word-highlight` | Per-word karaoke highlighting | off |
| `--translate, -t` | Target language code (es, fr, ja, etc.) | None |
| `--clip` | Enable auto-clipping | off |
| `--clip-method` | heuristic or llm | heuristic |
| `--clip-min` | Min clip duration (seconds) | 15 |
| `--clip-max` | Max clip duration (seconds) | 60 |
| `--gpu` | Use NVIDIA NVENC encoding | off |
| `--crf` | Video quality (18=best, 28=smallest) | 23 |
| `--srt-only` | Only generate subtitles | off |

## Project Structure

```
ai-content-pipeline/
├── main.py                  # Entry point
├── pipeline/
│   ├── __init__.py
│   ├── extract_audio.py     # Step 1: FFmpeg audio extraction
│   ├── transcribe.py        # Step 2: Whisper speech-to-text
│   ├── srt_generator.py     # Step 3: SRT/ASS subtitle generation
│   ├── translate.py         # Step 4: Argos offline translation
│   ├── smart_clip.py        # Step 5: Highlight detection + clipping
│   └── burn_captions.py     # Step 6: Burn captions onto video
├── input/                   # Drop raw videos here
├── output/                  # Final videos and subtitles
├── requirements.txt
└── README.md
```

## Hardware Recommendations

| Whisper Model | VRAM Needed | Speed (1hr video) | Accuracy |
|---------------|-------------|-------------------|----------|
| tiny          | ~1 GB       | ~2 min            | Basic    |
| base          | ~1 GB       | ~4 min            | OK       |
| small         | ~2 GB       | ~8 min            | Good     |
| medium        | ~5 GB       | ~15 min           | Great    |
| large         | ~10 GB      | ~30 min           | Best     |

GPU acceleration (CUDA for NVIDIA, MPS for Apple Silicon) makes Whisper ~10x faster.

## License

MIT — use it however you want.
