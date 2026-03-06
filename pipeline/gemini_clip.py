"""
Step 5B: Smart Clip detection using Google Gemini Flash (FREE).

Uses the Google AI Studio API (Gemini Flash model) to analyze your
transcript and find the most engaging moments for short-form clips.

Setup:
  1. Get a free API key at https://aistudio.google.com
  2. Add it to your .env file: GOOGLE_API_KEY=your_key_here
  3. Use: python main.py --input video.mp4 --clip --clip-method gemini

Free tier: 15 requests per minute, 1 million tokens per day.
"""

import json
import os
from pathlib import Path

# Try to load .env file
def _load_env():
    """Load API key from .env file in the project root."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def _get_api_key() -> str:
    """Get the Google API key from environment or .env file."""
    _load_env()
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        raise RuntimeError(
            "Google API key not found.\n\n"
            "To set it up (FREE):\n"
            "  1. Go to https://aistudio.google.com\n"
            "  2. Click 'Get API Key' and create one\n"
            "  3. Open the .env file in this project folder\n"
            "  4. Replace the placeholder with your key:\n"
            "     GOOGLE_API_KEY=your_key_here\n"
        )
    return key


def find_highlights_gemini(
    segments: list[dict],
    num_clips: int = 3,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> list[dict]:
    """
    Use Google Gemini Flash to find the most engaging moments.

    This is FREE via Google AI Studio (15 requests/min, 1M tokens/day).

    Args:
        segments:      Whisper segments list.
        num_clips:     Number of clips to extract.
        min_duration:  Minimum clip length in seconds.
        max_duration:  Maximum clip length in seconds.

    Returns:
        List of clip dicts with "start", "end", "duration", "reason".
    """
    import urllib.request
    import urllib.error

    api_key = _get_api_key()

    # Build a condensed transcript with timestamps
    transcript_lines = []
    for seg in segments:
        start = seg["start"]
        text = seg["text"].strip()
        transcript_lines.append(f"[{start:.1f}s] {text}")

    transcript = "\n".join(transcript_lines)

    # Truncate if very long (Gemini Flash handles 1M tokens but let's be efficient)
    if len(transcript) > 30000:
        transcript = transcript[:30000] + "\n\n[... transcript truncated ...]"

    prompt = (
        f"You are a professional content editor for TikTok/Reels/YouTube Shorts.\n\n"
        f"Analyze this transcript and find the {num_clips} most engaging, "
        f"viral-worthy moments for short-form clips.\n\n"
        f"Rules:\n"
        f"- Each clip must be between {min_duration} and {max_duration} seconds\n"
        f"- Pick moments with emotion, humor, insight, or surprise\n"
        f"- Clips should make sense as standalone content\n"
        f"- Use the timestamps from the transcript\n\n"
        f"TRANSCRIPT:\n{transcript}\n\n"
        f"Respond ONLY with valid JSON array, no markdown, no explanation:\n"
        f'[{{"start": <seconds>, "end": <seconds>, "reason": "<why this is engaging>"}}]'
    )

    # Call Gemini API
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    request_body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
        },
    }).encode("utf-8")

    print(f"[Step 5] Asking Gemini Flash to find {num_clips} highlights...")

    try:
        req = urllib.request.Request(
            url,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Extract the text response
        response_text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        # Clean up and parse JSON
        response_text = response_text.strip()

        # Remove markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:])
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Extract JSON array
        if "[" in response_text:
            json_str = response_text[
                response_text.index("["):response_text.rindex("]") + 1
            ]
            clips = json.loads(json_str)
        else:
            raise ValueError("No JSON array found in response")

        # Validate and add duration
        validated_clips = []
        for clip in clips:
            start = float(clip.get("start", 0))
            end = float(clip.get("end", 0))
            duration = end - start

            if duration < min_duration:
                continue
            if duration > max_duration:
                end = start + max_duration
                duration = max_duration

            validated_clips.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(duration, 2),
                "reason": clip.get("reason", ""),
            })

        print(f"  OK - Gemini found {len(validated_clips)} clips")
        for j, clip in enumerate(validated_clips):
            print(
                f"    Clip {j + 1}: {clip['start']:.1f}s - {clip['end']:.1f}s "
                f"({clip['duration']:.1f}s)"
            )
            if clip.get("reason"):
                print(f"      Reason: {clip['reason']}")

        return validated_clips

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        if e.code == 400:
            print(f"  ERROR: Bad request. Check your API key.")
        elif e.code == 429:
            print(f"  ERROR: Rate limit hit. Wait a moment and try again.")
        elif e.code == 403:
            print(f"  ERROR: API key invalid or disabled. Get a new one at aistudio.google.com")
        else:
            print(f"  ERROR: Gemini API returned {e.code}: {error_body[:200]}")

        print("  Falling back to heuristic method...")
        from .smart_clip import find_highlights
        return find_highlights(segments, min_duration=min_duration, max_duration=max_duration)

    except Exception as e:
        print(f"  ERROR: {e}")
        print("  Falling back to heuristic method...")
        from .smart_clip import find_highlights
        return find_highlights(segments, min_duration=min_duration, max_duration=max_duration)
