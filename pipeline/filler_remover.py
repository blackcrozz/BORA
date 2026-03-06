"""
Filler Word & Repetition Remover — Indonesian + English Bilingual
Detects and removes:
  - Indonesian fillers: eh, uh, um, hmm, ya, nah, kan, gitu, gini, tuh, nih,
    dong, loh, deh, kok, sih, emang, maksudnya, intinya, pokoknya, gimana ya...
  - English fillers: uh, uhm, um, err, like, you know, i mean, basically...
  - Repeated words/phrases: "it's it's", "jadi jadi", etc.
  - Thinking pauses with short duration words
Uses Gemini Flash for smart bilingual detection, heuristic as fallback.
"""

import json
import os
import re
import subprocess
from pathlib import Path

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Indonesian + English filler word lists
# ---------------------------------------------------------------------------

# Standalone filler words (must match whole word)
INDONESIAN_FILLERS = {
    # Thinking sounds
    "eh", "eh", "eeh", "ehm", "em", "emm",
    "uh", "uhh", "um", "umm", "hmm", "hm", "hmm",
    "ah", "ahh", "err", "errr",
    # Discourse particles (context-dependent — only flag if standalone/repeated)
    "ya", "yaa", "yaaa",
    "nah", "nah",
    "kan", "kan",
    "tuh", "nih",
    "dong", "deh", "loh", "lho", "lo",
    "kok", "sih",
    "gitu", "gini",
    # Filler phrases (handled separately below)
    # "maksudnya", "intinya", etc.
}

ENGLISH_FILLERS = {
    "uh", "uhh", "uhm", "um", "umm", "hmm", "hm",
    "ah", "ahh", "err", "errr", "like",
}

ALL_FILLER_WORDS = INDONESIAN_FILLERS | ENGLISH_FILLERS

# Multi-word filler phrases
INDONESIAN_FILLER_PHRASES = [
    r"\bgimana\s+ya\b",
    r"\bmaksud\s*(nya)?\b",
    r"\bintinya\b",
    r"\bpokoknya\b",
    r"\bpada\s+dasarnya\b",
    r"\bsebenarnya\b(?=.*\bsebenarnya\b)",  # Only if repeated
    r"\bjadi\s+gitu\b",
    r"\bjadi\s+gini\b",
    r"\bgitu\s+loh\b",
    r"\bgitu\s+deh\b",
    r"\bkan\s+ya\b",
    r"\bya\s+kan\b",
    r"\bya\s+gitu\b",
]

ENGLISH_FILLER_PHRASES = [
    r"\byou\s+know\b",
    r"\bi\s+mean\b",
    r"\bkind\s+of\b",
    r"\bsort\s+of\b",
    r"\bbasically\b",
    r"\blike\s+i\s+(said|was\s+saying)\b",
]

ALL_FILLER_PHRASES = [
    re.compile(p, re.IGNORECASE)
    for p in INDONESIAN_FILLER_PHRASES + ENGLISH_FILLER_PHRASES
]


# ---------------------------------------------------------------------------
# Gemini-powered filler detection
# ---------------------------------------------------------------------------

def detect_fillers_gemini(segments: list[dict]) -> list[dict]:
    """
    Use Gemini Flash to detect filler words/phrases in bilingual ID+EN speech.
    Returns list of word dicts (with start/end) that are fillers.
    Falls back to heuristic if Gemini unavailable.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return detect_fillers_heuristic(segments)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    # Build word list with timestamps for Gemini to analyze
    all_words = []
    for seg in segments:
        for w in seg.get("words", []):
            word = w.get("word", "").strip()
            if word:
                all_words.append({
                    "word": word,
                    "start": round(w.get("start", 0), 3),
                    "end": round(w.get("end", 0), 3),
                })

    if not all_words:
        return detect_fillers_heuristic(segments)

    # Send in batches of 200 words to stay within token limits
    filler_words = []
    batch_size = 200

    for i in range(0, len(all_words), batch_size):
        batch = all_words[i:i + batch_size]
        word_list = "\n".join(
            f"{j}. [{w['start']}s] {w['word']}"
            for j, w in enumerate(batch)
        )

        prompt = f"""You are analyzing a transcript from an Indonesian speaker who sometimes mixes in English words.

Identify ALL filler words, thinking pauses, and unnecessary repetitions in this word list.

Indonesian fillers include: eh, uh, um, hmm, ya (when used as filler), nah, kan, tuh, nih, dong, deh, loh, kok, sih, gitu, gini, maksudnya (when overused), intinya, pokoknya, gimana ya, jadi gitu, ya kan, etc.

English fillers include: uh, um, hmm, like (as filler), you know, i mean, basically, kind of, etc.

Also flag: immediate word repetitions (e.g. "jadi jadi", "dan dan", "it's it's")

WORD LIST:
{word_list}

Respond ONLY with a JSON array of indices (0-based) of filler words. No explanation:
[0, 3, 7, ...]

If no fillers found, respond: []"""

        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            if "[" in text:
                text = text[text.index("["):text.rindex("]") + 1]
            indices = json.loads(text)
            for idx in indices:
                if 0 <= idx < len(batch):
                    filler_words.append(batch[idx])
        except Exception as e:
            print(f"  [Filler] Gemini batch error: {e}, using heuristic for this batch...")
            filler_words.extend(_heuristic_from_wordlist(batch))

    print(f"[Filler] Gemini detected {len(filler_words)} filler words/phrases")
    return filler_words


def detect_fillers_heuristic(segments: list[dict]) -> list[dict]:
    """
    Heuristic filler detection — no API needed.
    Handles Indonesian and English fillers.
    """
    filler_words = []

    for seg in segments:
        words = seg.get("words", [])
        filler_words.extend(_heuristic_from_wordlist(words))

    print(f"[Filler] Heuristic detected {len(filler_words)} filler words")
    return filler_words


def _heuristic_from_wordlist(words: list[dict]) -> list[dict]:
    """Run heuristic filler detection on a list of word dicts."""
    fillers = []
    texts = [w.get("word", "").strip().lower() for w in words]

    for i, (w, text) in enumerate(zip(words, texts)):
        # Check standalone filler words
        clean = re.sub(r"[^\w]", "", text)
        if clean in ALL_FILLER_WORDS:
            fillers.append(w)
            continue

        # Check filler phrases (join with next word)
        if i < len(texts) - 1:
            two_words = text + " " + texts[i + 1]
            for pattern in ALL_FILLER_PHRASES:
                if pattern.fullmatch(two_words):
                    fillers.append(w)
                    if i + 1 < len(words):
                        fillers.append(words[i + 1])
                    break

        # Check immediate repetitions
        if i > 0 and clean and clean == re.sub(r"[^\w]", "", texts[i - 1]):
            if clean not in {"the", "a", "di", "ke", "dan", "dan", ""}:
                fillers.append(w)

    return fillers


# ---------------------------------------------------------------------------
# Clean segments using detected fillers
# ---------------------------------------------------------------------------

def clean_segments(
    segments: list[dict],
    use_gemini: bool = True,
    remove_repetitions: bool = True,
) -> tuple[list[dict], list[dict]]:
    """
    Remove filler words from Whisper segments.
    Returns (cleaned_segments, removed_intervals).
    """
    # Detect fillers
    if use_gemini and os.getenv("GEMINI_API_KEY") and GEMINI_AVAILABLE:
        print("[Filler] Using Gemini for bilingual filler detection...")
        filler_word_list = detect_fillers_gemini(segments)
    else:
        print("[Filler] Using heuristic filler detection (ID+EN)...")
        filler_word_list = detect_fillers_heuristic(segments)

    # Build set of filler timestamps for quick lookup
    filler_intervals = [
        {"start": w.get("start", 0), "end": w.get("end", 0)}
        for w in filler_word_list
        if w.get("end", 0) > w.get("start", 0)
    ]
    filler_intervals = _merge_intervals(filler_intervals, gap=0.08)

    def is_filler_time(start, end):
        for fi in filler_intervals:
            if start >= fi["start"] - 0.05 and end <= fi["end"] + 0.05:
                return True
        return False

    # Rebuild segments without fillers
    cleaned = []
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            # No word timestamps — do text-level cleanup
            text = seg["text"].strip()
            for pattern in ALL_FILLER_PHRASES:
                text = pattern.sub("", text)
            # Remove standalone fillers
            words_in_text = text.split()
            kept = [
                w for w in words_in_text
                if re.sub(r"[^\w]", "", w.lower()) not in ALL_FILLER_WORDS
            ]
            text = " ".join(kept).strip()
            if text:
                new_seg = dict(seg)
                new_seg["text"] = text
                cleaned.append(new_seg)
            continue

        kept_words = [
            w for w in words
            if not is_filler_time(w.get("start", 0), w.get("end", 0))
        ]

        if not kept_words:
            continue

        new_seg = dict(seg)
        new_seg["words"] = kept_words
        new_seg["text"] = " ".join(
            w.get("word", "").strip() for w in kept_words
        )
        new_seg["start"] = kept_words[0].get("start", seg["start"])
        new_seg["end"] = kept_words[-1].get("end", seg["end"])
        cleaned.append(new_seg)

    print(f"[Filler] Removed {len(filler_intervals)} intervals from transcript")
    return cleaned, filler_intervals


def _merge_intervals(intervals: list[dict], gap: float = 0.05) -> list[dict]:
    """Merge overlapping or near-adjacent intervals."""
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: x["start"])
    merged = [sorted_iv[0].copy()]
    for iv in sorted_iv[1:]:
        if iv["start"] <= merged[-1]["end"] + gap:
            merged[-1]["end"] = max(merged[-1]["end"], iv["end"])
        else:
            merged.append(iv.copy())
    return merged


# ---------------------------------------------------------------------------
# Cut filler segments from video
# ---------------------------------------------------------------------------

def cut_filler_segments(
    video_path: str,
    output_path: str,
    removed_intervals: list[dict],
    total_duration: float,
    padding: float = 0.04,
) -> str:
    """
    Cut filler word segments from video using FFmpeg concat.
    """
    if not removed_intervals:
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    # Build keep segments
    keep = []
    current = 0.0
    for iv in removed_intervals:
        end = iv["start"] - padding
        if end > current + 0.05:
            keep.append({"start": current, "end": end})
        current = iv["end"] + padding

    if current < total_duration:
        keep.append({"start": current, "end": total_duration})

    keep = [s for s in keep if s["end"] - s["start"] > 0.05]

    if not keep:
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    print(f"[Filler] Cutting video: {len(keep)} segments kept, {len(removed_intervals)} fillers removed")

    video_filters = []
    audio_filters = []
    for i, seg in enumerate(keep):
        s, e = seg["start"], seg["end"]
        video_filters.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        audio_filters.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]")

    n = len(keep)
    v_labels = "".join(f"[v{i}]" for i in range(n))
    a_labels = "".join(f"[a{i}]" for i in range(n))

    filter_complex = ";".join(video_filters + audio_filters + [
        f"{v_labels}concat=n={n}:v=1:a=0[vout]",
        f"{a_labels}concat=n={n}:v=0:a=1[aout]",
    ])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        "-c:a", "aac", "-y", str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg filler cut error:\n{result.stderr[-500:]}")

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"  ✓ Filler-free video: {output_path} ({size_mb:.1f} MB)")
    return output_path