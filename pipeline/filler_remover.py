"""
Filler Word & Repetition Remover — Indonesian + English Bilingual
Conservative approach: only removes HIGH-CONFIDENCE fillers to avoid
breaking valid speech. Remaps caption timestamps after cuts.
"""

import json
import os
import re
import subprocess
import shutil
from pathlib import Path

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Only remove these when they appear as STANDALONE short utterances
# (i.e. very short duration, isolated, not part of a sentence)
# ---------------------------------------------------------------------------

# These are SAFE to always remove — pure sounds, never meaningful words
ALWAYS_FILLER = {
    "uh", "uhh", "uhm", "um", "umm", "emmm", "em",
    "eh", "ehm", "eeh",
    "hmm", "hm", "hmm", "hmmm",
    "ah", "ahh", "ahhhh",
    "err", "errr",
}

# These are CONTEXT-DEPENDENT — only remove if very short duration (<0.4s)
# and surrounded by other speech (not at sentence start/end)
CONTEXT_DEPENDENT = {
    "ya", "yaa",
    "nah",
    "kan",
    "tuh", "nih",
    "dong", "deh", "loh", "lho",
    "kok", "sih",
    "gitu", "gini",
}

# Multi-word phrases — safe to remove regardless of context
FILLER_PHRASES = [
    r"\bgimana\s+ya\b",
    r"\bya\s+kan\b",
    r"\bkan\s+ya\b",
    r"\bgitu\s+loh\b",
    r"\bgitu\s+deh\b",
    r"\bjadi\s+gitu\b",
    r"\byou\s+know\b",
    r"\bi\s+mean\b",
]
COMPILED_PHRASES = [re.compile(p, re.IGNORECASE) for p in FILLER_PHRASES]

# Maximum duration (seconds) for a context-dependent word to be considered filler
MAX_FILLER_DURATION = 0.45


def _is_filler_word(word: dict, idx: int, all_words: list) -> bool:
    """
    Determine if a word is a filler with conservative confidence scoring.

    Args:
        word:      Word dict with "word", "start", "end".
        idx:       Index in all_words list.
        all_words: Full word list for context.

    Returns:
        True only if confidently a filler.
    """
    text = re.sub(r"[^\w]", "", word.get("word", "")).lower().strip()
    if not text:
        return False

    duration = word.get("end", 0) - word.get("start", 0)

    # Always remove pure sound fillers regardless of duration
    if text in ALWAYS_FILLER:
        return True

    # Context-dependent: only remove if SHORT and not at sentence boundaries
    if text in CONTEXT_DEPENDENT:
        if duration > MAX_FILLER_DURATION:
            return False  # Long enough to be meaningful speech
        # Don't remove if it's the only word or at sentence start
        if idx == 0 or idx == len(all_words) - 1:
            return False
        return True

    # Immediate repetition (e.g. "jadi jadi", "dan dan")
    if idx > 0:
        prev = re.sub(r"[^\w]", "", all_words[idx-1].get("word", "")).lower()
        if text == prev and text not in {"the", "a", "di", "ke", ""}:
            return True

    return False


# ---------------------------------------------------------------------------
# Gemini-powered detection (context-aware)
# ---------------------------------------------------------------------------

def detect_fillers_gemini(segments: list[dict]) -> list[dict]:
    """Use Gemini Flash to detect fillers in bilingual ID+EN speech."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return detect_fillers_heuristic(segments)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    # Flatten all words
    all_words = []
    for seg in segments:
        for w in seg.get("words", []):
            if w.get("word", "").strip():
                all_words.append(w)

    if not all_words:
        return detect_fillers_heuristic(segments)

    filler_words = []
    batch_size = 150

    for i in range(0, len(all_words), batch_size):
        batch = all_words[i:i + batch_size]
        word_list = "\n".join(
            f"{j}. [{round(w.get('start',0),2)}s-{round(w.get('end',0),2)}s] \"{w.get('word','').strip()}\""
            for j, w in enumerate(batch)
        )

        prompt = f"""You are analyzing bilingual Indonesian-English speech. Identify ONLY clear filler words and thinking sounds that should be REMOVED from the video.

CONSERVATIVE RULES — only flag words you are very confident are fillers:
✅ ALWAYS remove: uh, uhm, um, hmm, eh, ah, err (pure thinking sounds)
✅ REMOVE if clearly a filler sound (very short, isolated): ya, nah, kan, tuh, nih, dong, deh, sih
✅ REMOVE: immediate word repetitions (e.g. "jadi jadi", "dan dan", "the the")
❌ DO NOT remove: ya/nah/kan that are part of meaningful sentences
❌ DO NOT remove words that carry actual meaning even if informal
❌ DO NOT remove English words just because they sound informal
❌ WHEN IN DOUBT: do not flag it

WORD LIST (with timestamps):
{word_list}

Respond ONLY with JSON array of 0-based indices to remove. Empty array if none:
[0, 3, 7]"""

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
            print(f"  [Filler] Gemini error: {e}, using heuristic for batch...")
            filler_words.extend(_heuristic_from_wordlist(batch))

    print(f"[Filler] Gemini flagged {len(filler_words)} filler words")
    return filler_words


def detect_fillers_heuristic(segments: list[dict]) -> list[dict]:
    """Conservative heuristic filler detection."""
    all_words = []
    for seg in segments:
        all_words.extend(seg.get("words", []))

    fillers = []
    for i, w in enumerate(all_words):
        if _is_filler_word(w, i, all_words):
            fillers.append(w)

    print(f"[Filler] Heuristic flagged {len(fillers)} filler words")
    return fillers


def _heuristic_from_wordlist(words: list[dict]) -> list[dict]:
    """Run heuristic on a flat word list."""
    fillers = []
    for i, w in enumerate(words):
        if _is_filler_word(w, i, words):
            fillers.append(w)
    return fillers


# ---------------------------------------------------------------------------
# Clean segments + remap timestamps
# ---------------------------------------------------------------------------

def clean_segments(
    segments: list[dict],
    use_gemini: bool = True,
) -> tuple[list[dict], list[dict]]:
    """
    Remove filler words from segments and return:
    - cleaned segments (text only, timestamps unchanged — for transcript)
    - removed_intervals (for video cutting)
    """
    if use_gemini and os.getenv("GEMINI_API_KEY") and GEMINI_AVAILABLE:
        print("[Filler] Using Gemini for bilingual filler detection...")
        filler_list = detect_fillers_gemini(segments)
    else:
        print("[Filler] Using heuristic filler detection (ID+EN)...")
        filler_list = detect_fillers_heuristic(segments)

    if not filler_list:
        print("[Filler] No fillers detected.")
        return segments, []

    # Build filler time intervals
    filler_intervals = [
        {"start": w.get("start", 0), "end": w.get("end", 0)}
        for w in filler_list
        if w.get("end", 0) > w.get("start", 0)
    ]
    filler_intervals = _merge_intervals(filler_intervals, gap=0.08)

    def is_filler_time(start, end):
        for fi in filler_intervals:
            if start >= fi["start"] - 0.05 and end <= fi["end"] + 0.05:
                return True
        return False

    # Remove filler words from segments (text only)
    cleaned = []
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            cleaned.append(seg)
            continue

        kept = [w for w in words if not is_filler_time(
            w.get("start", 0), w.get("end", 0)
        )]

        if not kept:
            continue

        new_seg = dict(seg)
        new_seg["words"] = kept
        new_seg["text"] = " ".join(w.get("word", "").strip() for w in kept)
        new_seg["start"] = kept[0].get("start", seg["start"])
        new_seg["end"] = kept[-1].get("end", seg["end"])
        cleaned.append(new_seg)

    print(f"[Filler] Cleaned transcript: {len(filler_intervals)} intervals to cut")
    return cleaned, filler_intervals


def remap_timestamps(
    segments: list[dict],
    removed_intervals: list[dict],
) -> list[dict]:
    """
    After cutting filler segments from video, remap all word/segment
    timestamps to match the NEW video timeline.

    This prevents caption drift after filler cuts.

    Args:
        segments:          Cleaned Whisper segments (original timestamps).
        removed_intervals: Intervals that were cut from video.

    Returns:
        Segments with recalculated timestamps matching the new video.
    """
    if not removed_intervals:
        return segments

    def remap_time(t: float) -> float:
        """Subtract total removed duration before time t."""
        removed_before = sum(
            min(iv["end"], t) - iv["start"]
            for iv in removed_intervals
            if iv["start"] < t
        )
        return max(0.0, t - removed_before)

    remapped = []
    for seg in segments:
        new_seg = dict(seg)
        new_seg["start"] = round(remap_time(seg["start"]), 3)
        new_seg["end"] = round(remap_time(seg["end"]), 3)

        new_words = []
        for w in seg.get("words", []):
            new_w = dict(w)
            new_w["start"] = round(remap_time(w.get("start", seg["start"])), 3)
            new_w["end"] = round(remap_time(w.get("end", seg["end"])), 3)
            new_words.append(new_w)

        new_seg["words"] = new_words
        remapped.append(new_seg)

    print("[Filler] Timestamps remapped to new video timeline ✓")
    return remapped


# ---------------------------------------------------------------------------
# Cut filler segments from video
# ---------------------------------------------------------------------------

def _merge_intervals(intervals: list[dict], gap: float = 0.05) -> list[dict]:
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


def cut_filler_segments(
    video_path: str,
    output_path: str,
    removed_intervals: list[dict],
    total_duration: float,
    padding: float = 0.04,
) -> str:
    """Cut filler word segments from video using FFmpeg concat."""
    if not removed_intervals:
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
        shutil.copy2(video_path, output_path)
        return output_path

    print(f"[Filler] Cutting: keeping {len(keep)} segments, removing {len(removed_intervals)} fillers")

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
        raise RuntimeError(f"FFmpeg error:\n{result.stderr[-500:]}")

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"  ✓ Filler-free video: {output_path} ({size_mb:.1f} MB)")
    return output_path