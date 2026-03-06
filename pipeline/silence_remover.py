"""
Silence Removal: Detect and remove pauses/silences from video.
Uses FFmpeg silencedetect filter — no API needed, fully local.
"""

import subprocess
import re
from pathlib import Path


def detect_silences(
    video_path: str,
    silence_threshold: float = -35.0,
    min_silence_duration: float = 0.5,
) -> list[dict]:
    """
    Detect silent segments in a video using FFmpeg.

    Args:
        video_path:            Path to video file.
        silence_threshold:     dB threshold for silence (default: -35dB).
        min_silence_duration:  Minimum silence length in seconds to detect (default: 0.5s).

    Returns:
        List of dicts with "start" and "end" keys (in seconds).
    """
    print(f"[Silence] Detecting silences (threshold={silence_threshold}dB, min={min_silence_duration}s)...")

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-af", f"silencedetect=noise={silence_threshold}dB:d={min_silence_duration}",
        "-f", "null",
        "-",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr  # FFmpeg outputs to stderr

    silences = []
    starts = re.findall(r"silence_start: ([0-9.]+)", output)
    ends = re.findall(r"silence_end: ([0-9.]+)", output)

    for s, e in zip(starts, ends):
        silences.append({"start": float(s), "end": float(e)})

    print(f"  ✓ Found {len(silences)} silent segments")
    return silences


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def silences_to_keep_segments(
    silences: list[dict],
    total_duration: float,
    padding: float = 0.1,
) -> list[dict]:
    """
    Convert silence segments into the segments we want to KEEP.

    Args:
        silences:       List of silence dicts with "start"/"end".
        total_duration: Total video duration in seconds.
        padding:        Seconds to keep around each cut (avoids hard cuts).

    Returns:
        List of dicts with "start" and "end" to keep.
    """
    keep = []
    current = 0.0

    for silence in silences:
        seg_end = silence["start"] + padding
        if seg_end > current:
            keep.append({"start": current, "end": seg_end})
        current = max(current, silence["end"] - padding)

    # Add the final segment
    if current < total_duration:
        keep.append({"start": current, "end": total_duration})

    # Filter out tiny segments
    keep = [s for s in keep if s["end"] - s["start"] > 0.1]
    return keep


def remove_silences(
    video_path: str,
    output_path: str,
    silence_threshold: float = -35.0,
    min_silence_duration: float = 0.5,
    padding: float = 0.1,
) -> str:
    """
    Remove silent segments from a video and export a clean version.

    Args:
        video_path:            Path to source video.
        output_path:           Path for the output video.
        silence_threshold:     dB level to consider as silence.
        min_silence_duration:  Minimum silence duration to remove (seconds).
        padding:               Keep this many seconds around each cut.

    Returns:
        Path to the output video.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Detect silences
    silences = detect_silences(
        str(video_path), silence_threshold, min_silence_duration
    )

    if not silences:
        print("  ✓ No silences detected — copying original video.")
        import shutil
        shutil.copy2(str(video_path), str(output_path))
        return str(output_path)

    # Step 2: Get duration
    duration = get_video_duration(str(video_path))

    # Step 3: Calculate segments to keep
    segments = silences_to_keep_segments(silences, duration, padding)
    print(f"  Keeping {len(segments)} segments (removed {len(silences)} pauses)")

    # Step 4: Build FFmpeg complex filter to concat segments
    # Use the select/aselect filter approach for clean concatenation
    video_filters = []
    audio_filters = []

    for i, seg in enumerate(segments):
        start = seg["start"]
        end = seg["end"]
        video_filters.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]"
        )
        audio_filters.append(
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
        )

    n = len(segments)
    v_labels = "".join(f"[v{i}]" for i in range(n))
    a_labels = "".join(f"[a{i}]" for i in range(n))

    all_filters = video_filters + audio_filters + [
        f"{v_labels}concat=n={n}:v=1:a=0[vout]",
        f"{a_labels}concat=n={n}:v=0:a=1[aout]",
    ]

    filter_complex = ";".join(all_filters)

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-c:a", "aac",
        "-y",
        str(output_path),
    ]

    print(f"[Silence] Rendering video without silences...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr[-1000:]}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  ✓ Silence-removed video saved: {output_path} ({size_mb:.1f} MB)")
    return str(output_path)