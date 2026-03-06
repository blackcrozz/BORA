"""
Step 5: Auto-generate short clips from long videos.

Two strategies:
  1. Heuristic-based: Detect natural breaks via pauses in speech.
  2. LLM-based (optional): Use a local LLM via Ollama to pick the
     most interesting moments from the transcript.
"""

import json
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Heuristic-based highlight detection
# ---------------------------------------------------------------------------

def find_highlights(
    segments: list[dict],
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    pause_threshold: float = 2.0,
) -> list[dict]:
    """
    Find clip-worthy sections by detecting natural pauses in speech.

    Args:
        segments:         Whisper segments list.
        min_duration:     Minimum clip length in seconds.
        max_duration:     Maximum clip length in seconds.
        pause_threshold:  Seconds of silence that mark a section boundary.

    Returns:
        List of clip dicts with "start", "end", "duration", "text" (preview).
    """
    if not segments:
        return []

    print(f"[Step 5] Finding highlights (min={min_duration}s, max={max_duration}s)")

    clips = []
    current_start = segments[0]["start"]
    current_texts = []

    for i in range(len(segments)):
        current_texts.append(segments[i]["text"].strip())
        duration = segments[i]["end"] - current_start

        # Check if we should cut here
        is_last = i == len(segments) - 1
        has_pause = (
            not is_last
            and (segments[i + 1]["start"] - segments[i]["end"]) > pause_threshold
        )
        too_long = duration >= max_duration

        if is_last or has_pause or too_long:
            if duration >= min_duration:
                # Add a small buffer around the clip
                clip_start = max(0, current_start - 0.5)
                clip_end = segments[i]["end"] + 0.5

                clips.append({
                    "start": round(clip_start, 2),
                    "end": round(clip_end, 2),
                    "duration": round(clip_end - clip_start, 2),
                    "text": " ".join(current_texts)[:200] + "...",
                })

            # Start a new potential clip
            if not is_last:
                current_start = segments[i + 1]["start"]
                current_texts = []

    print(f"  ✓ Found {len(clips)} potential clips")
    for j, clip in enumerate(clips):
        print(f"    Clip {j + 1}: {clip['start']:.1f}s → {clip['end']:.1f}s  ({clip['duration']:.1f}s)")

    return clips


# ---------------------------------------------------------------------------
# LLM-based highlight detection (requires Ollama)
# ---------------------------------------------------------------------------

def find_highlights_llm(
    segments: list[dict],
    num_clips: int = 3,
    model: str = "llama3.2",
) -> list[dict]:
    """
    Use a local LLM (via Ollama) to find the most engaging moments.

    Requires Ollama to be installed and running locally.
    Install: https://ollama.com

    Args:
        segments:   Whisper segments list.
        num_clips:  Number of clips to extract.
        model:      Ollama model name.

    Returns:
        List of clip dicts with "start", "end", "reason".
    """
    # Build a condensed transcript with timestamps
    transcript_lines = []
    for seg in segments:
        start = seg["start"]
        text = seg["text"].strip()
        transcript_lines.append(f"[{start:.1f}s] {text}")

    transcript = "\n".join(transcript_lines)

    prompt = f"""You are a content editor. Analyze this transcript and find the {num_clips} most engaging/viral-worthy moments for short-form clips (15-60 seconds each).

TRANSCRIPT:
{transcript}

Respond ONLY with valid JSON — no explanation, no markdown:
[
  {{"start": <seconds>, "end": <seconds>, "reason": "<why this is engaging>"}},
  ...
]"""

    print(f"[Step 5] Asking {model} to find {num_clips} highlights...")

    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            print(f"  ⚠ Ollama error: {result.stderr}")
            print("  Falling back to heuristic method...")
            return find_highlights(segments)

        # Parse JSON from the LLM response
        response = result.stdout.strip()

        # Try to extract JSON from the response
        json_match = response
        if "[" in response:
            json_match = response[response.index("["):response.rindex("]") + 1]

        clips = json.loads(json_match)

        print(f"  ✓ LLM found {len(clips)} clips")
        for j, clip in enumerate(clips):
            print(f"    Clip {j + 1}: {clip['start']:.1f}s → {clip['end']:.1f}s  — {clip.get('reason', '')}")

        return clips

    except FileNotFoundError:
        print("  ⚠ Ollama not installed. Falling back to heuristic method...")
        return find_highlights(segments)
    except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        print(f"  ⚠ LLM response parsing failed: {e}")
        print("  Falling back to heuristic method...")
        return find_highlights(segments)


# ---------------------------------------------------------------------------
# Cut clips from video
# ---------------------------------------------------------------------------

def cut_clips(
    video_path: str,
    clips: list[dict],
    output_dir: str = "output",
    prefix: str = "clip",
) -> list[str]:
    """
    Cut video segments using FFmpeg.

    Args:
        video_path:  Path to the source video.
        clips:       List of clip dicts with "start" and "end" keys.
        output_dir:  Directory to save clips.
        prefix:      Filename prefix for clips.

    Returns:
        List of paths to the generated clip files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    video_path = Path(video_path)
    ext = video_path.suffix

    print(f"[Step 5] Cutting {len(clips)} clips from: {video_path.name}")

    output_paths = []
    for i, clip in enumerate(clips):
        output_path = output_dir / f"{prefix}_{i + 1:03d}{ext}"
        start = clip["start"]
        end = clip["end"]

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-ss", str(start),
            "-to", str(end),
            "-c", "copy",       # Fast copy (no re-encoding)
            "-y",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ⚠ Failed to cut clip {i + 1}: {result.stderr[:200]}")
            continue

        output_paths.append(str(output_path))
        print(f"  ✓ Clip {i + 1}: {output_path.name}  ({end - start:.1f}s)")

    return output_paths
