"""
Step 2: Transcribe audio to text using OpenAI Whisper.
Runs Whisper locally to produce timestamped text segments.
Supports bilingual Indonesian-English (code-switching) correction via Gemini.
"""

import json
import os
import warnings
from pathlib import Path

import whisper

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

MODELS = ["tiny", "base", "small", "medium", "large"]

# Bilingual prompt — tells Whisper upfront the speaker mixes ID + EN
BILINGUAL_PROMPT = (
    "Transkripsi percakapan bahasa Indonesia yang kadang bercampur "
    "dengan kata-kata bahasa Inggris seperti nama produk, istilah teknis, "
    "dan ungkapan sehari-hari. "
    "Indonesian speech mixed with English words, brand names, and technical terms."
)


def transcribe_audio(
    audio_path: str,
    model_name: str = "medium",
    language: str | None = None,
    word_timestamps: bool = True,
    bilingual_correction: bool = True,
) -> dict:
    """
    Transcribe an audio file with Whisper.

    Args:
        audio_path:            Path to the audio file (WAV recommended).
        model_name:            Whisper model size — tiny | base | small | medium | large.
        language:              Language code (e.g. "id", "en"). None = auto-detect.
        word_timestamps:       If True, include per-word timing information.
        bilingual_correction:  Run Gemini correction pass for ID+EN code-switching.

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
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = whisper.load_model(model_name)

    print(f"  Transcribing: {audio_path.name}")
    result = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=word_timestamps,
        initial_prompt=BILINGUAL_PROMPT,
        task="transcribe",
        verbose=False,
    )

    seg_count = len(result.get("segments", []))
    detected_lang = result.get("language", "unknown")
    print(f"  ✓ Transcribed {seg_count} segments (language: {detected_lang})")

    # Run Gemini bilingual correction if available
    if bilingual_correction and os.getenv("GEMINI_API_KEY") and GEMINI_AVAILABLE:
        result = _correct_bilingual_transcript(result)

    return result


def _correct_bilingual_transcript(result: dict) -> dict:
    """
    Use Gemini Flash to fix misheard words in Indonesian-English mixed speech.

    Corrects common Whisper mistakes:
    - English words transcribed as Indonesian phonetics (e.g. "content" → "konten")
    - Indonesian words written as wrong English words
    - Brand names, technical terms, and proper nouns mangled
    - English phrases written in Indonesian spelling

    Only fixes transcription errors — does NOT translate or rewrite meaning.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return result

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    segments = result.get("segments", [])
    if not segments:
        return result

    batch_size = 30
    print(f"  [Step 2] Gemini bilingual correction on {len(segments)} segments...")

    for i in range(0, len(segments), batch_size):
        batch = segments[i:i + batch_size]
        seg_list = "\n".join(
            f"{j}. {seg['text'].strip()}"
            for j, seg in enumerate(batch)
        )

        prompt = f"""You are correcting a speech-to-text transcript from an Indonesian speaker who mixes in English words.

Whisper (the STT model) makes these common mistakes with bilingual Indonesian-English speech:
- English words transcribed as Indonesian phonetics (e.g. "content" written as "konten", "growth" as "grot", "brand" as "bren")
- Indonesian words mistakenly written as English words
- Brand names, app names, tech terms mangled (e.g. "Instagram" → "Instragram", "TikTok" → "Tik Tok")
- English phrases spelled phonetically in Indonesian

Fix ONLY clear transcription errors. Rules:
- Do NOT translate anything
- Do NOT rewrite sentences or change meaning
- Keep Indonesian words as Indonesian
- Keep English words as English (as the speaker said them)
- Only fix words that are clearly wrong phonetic transcriptions

SEGMENTS:
{seg_list}

Respond ONLY with a JSON array of the corrected texts, same count, same order:
["corrected 0", "corrected 1", ...]

If a segment needs no correction, include it exactly as-is."""

        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            if "[" in text:
                text = text[text.index("["):text.rindex("]") + 1]
            corrected = json.loads(text)

            if len(corrected) == len(batch):
                for seg, new_text in zip(batch, corrected):
                    if new_text.strip():
                        seg["text"] = new_text.strip()

        except Exception as e:
            print(f"  [Correction] Batch {i // batch_size + 1} skipped: {e}")

    result["text"] = " ".join(seg["text"].strip() for seg in segments)
    print(f"  ✓ Bilingual correction complete")
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