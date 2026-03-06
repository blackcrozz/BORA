"""
Step 6: Burn (hardcode) captions onto video using FFmpeg.

Supports both SRT (simple) and ASS (styled) subtitle formats.
"""

import subprocess
from pathlib import Path


def burn_captions(
    video_path: str,
    subtitle_path: str,
    output_path: str,
    video_codec: str = "libx264",
    crf: int = 23,
    preset: str = "medium",
) -> str:
    """
    Burn subtitles permanently onto a video.

    Args:
        video_path:     Path to the source video.
        subtitle_path:  Path to the .srt or .ass subtitle file.
        output_path:    Path for the output video with burned captions.
        video_codec:    FFmpeg video codec (libx264, libx265, h264_nvenc).
        crf:            Constant Rate Factor (lower = better quality, 18-28 typical).
        preset:         Encoding speed preset (ultrafast, fast, medium, slow).

    Returns:
        Path to the output video.
    """
    video_path = Path(video_path)
    subtitle_path = Path(subtitle_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not subtitle_path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    # Determine the correct FFmpeg filter based on subtitle format
    sub_ext = subtitle_path.suffix.lower()

    if sub_ext == ".ass":
        # Use forward slashes — FFmpeg handles them on Windows, avoids escape issues
        fwd_path = str(subtitle_path.resolve()).replace("\\", "/")
        vf_filter = f"ass={fwd_path}"
    elif sub_ext == ".srt":
        fwd_path = str(subtitle_path.resolve()).replace("\\", "/")
        escaped_path = fwd_path.replace(":", "\\:")
        vf_filter = f"subtitles={escaped_path}"
    else:
        raise ValueError(f"Unsupported subtitle format: {sub_ext} (use .srt or .ass)")

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", vf_filter,
        "-c:v", video_codec,
        "-crf", str(crf),
        "-preset", preset,
        "-c:a", "copy",         # Keep audio as-is
        "-y",
        str(output_path),
    ]

    print(f"[Step 6] Burning captions onto video...")
    print(f"  Video:     {video_path.name}")
    print(f"  Subtitles: {subtitle_path.name} ({sub_ext})")
    print(f"  Codec:     {video_codec} (CRF={crf}, preset={preset})")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr}")

    output_size = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"  ✓ Output saved: {output_path} ({output_size:.1f} MB)")
    return output_path


def burn_captions_gpu(
    video_path: str,
    subtitle_path: str,
    output_path: str,
) -> str:
    """
    Burn captions using NVIDIA GPU encoding (much faster).

    Requires an NVIDIA GPU with NVENC support.
    """
    return burn_captions(
        video_path=video_path,
        subtitle_path=subtitle_path,
        output_path=output_path,
        video_codec="h264_nvenc",
        crf=23,
        preset="fast",
    )
