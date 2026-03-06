"""
Step 1: Extract audio from video using FFmpeg.

Extracts the audio track from a video file and saves it as a WAV file
optimized for Whisper (16kHz, mono, PCM 16-bit).
"""

import subprocess
import shutil
from pathlib import Path


def check_ffmpeg():
    """Verify FFmpeg is installed and accessible."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "FFmpeg not found. Install it:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg\n"
            "  Windows: choco install ffmpeg"
        )


def extract_audio(
    video_path: str,
    output_path: str | None = None,
    sample_rate: int = 16000,
) -> str:
    """
    Extract audio from a video file.

    Args:
        video_path:   Path to the input video file.
        output_path:  Path for the output WAV file. If None, uses the same
                      directory and base name as the video with a .wav extension.
        sample_rate:  Audio sample rate in Hz (default 16000 for Whisper).

    Returns:
        Path to the extracted audio file.
    """
    check_ffmpeg()

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if output_path is None:
        output_path = str(video_path.with_suffix(".wav"))

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",                      # No video
        "-acodec", "pcm_s16le",     # PCM 16-bit little-endian
        "-ar", str(sample_rate),    # Sample rate
        "-ac", "1",                 # Mono
        "-y",                       # Overwrite output
        output_path,
    ]

    print(f"[Step 1] Extracting audio from: {video_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr}")

    print(f"  ✓ Audio saved to: {output_path}")
    return output_path


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    check_ffmpeg()

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error:\n{result.stderr}")

    return float(result.stdout.strip())
