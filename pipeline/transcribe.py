"""
Step 2: Transcribe audio to text using OpenAI Whisper.

Runs Whisper locally to produce timestamped text segments.
Supports model selection and word-level timestamps.
"""

from pathlib import Path

import whisper


# Available models ordered by size / accuracy
MODELS = ["tiny", "base", "small", "medium", "large"]


def transcribe_audio(
    audio_path: str,
    model_name: str = "medium",
    language: str | None = None,
    word_timestamps: bool = True,
) -> dict:
    """
    Transcribe an audio file with Whisper.

    Args:
        audio_path:       Path to the audio file (WAV recommended).
        model_name:       Whisper model size — tiny | base | small | medium | large.
        language:         Language code (e.g. "en"). None = auto-detect.
        word_timestamps:  If True, include per-word timing information.

    Returns:
        Whisper result dict containing:
          - "text":      Full transcription string
          - "segments":  List of segment dicts with start, end, text
          - "language":  Detected language code
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"[Step 2] Loading Whisper model: {model_name}")
    model = whisper.load_model(model_name)

    print(f"  Transcribing: {audio_path.name}")
    result = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=word_timestamps,
        verbose=False,
    )

    seg_count = len(result.get("segments", []))
    detected_lang = result.get("language", "unknown")
    print(f"  ✓ Transcribed {seg_count} segments (language: {detected_lang})")

    return result


def print_transcript(result: dict, max_segments: int | None = None):
    """Pretty-print a Whisper transcript result."""
    segments = result.get("segments", [])
    if max_segments:
        segments = segments[:max_segments]

    for seg in segments:
        start = seg["start"]
        end = seg["end"]
        text = seg["text"].strip()
        print(f"  [{start:7.2f} → {end:7.2f}]  {text}")

    total = len(result.get("segments", []))
    if max_segments and total > max_segments:
        print(f"  ... and {total - max_segments} more segments")
