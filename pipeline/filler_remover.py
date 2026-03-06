"""
Filler Word & Repetition Remover
Detects and removes: uh, uhm, err, ah, like (filler), you know,
repeated words/phrases, and thinking pauses from transcript + video.
"""

import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Filler word patterns
# ---------------------------------------------------------------------------

FILLER_PATTERNS = [
    r"\b(uh+|uhm+|um+|err+|hmm+|ah+|eh+)\b",          # Classic fillers
    r"\b(like)\b(?=\s+(i|we|you|he|she|they|it)\b)",   # "like I said" not "I like"
    r"\byou know\b",
    r"\bi mean\b",
    r"\bkind of\b",
    r"\bsort of\b",
    r"\bbasically\b",
    r"\bactually\b(?=\s+\bactually\b)",                 # Only repeated "actually"
]

COMPILED_FILLERS = [re.compile(p, re.IGNORECASE) for p in FILLER_PATTERNS]


def is_filler_word(text: str) -> bool:
    """Check if a word/phrase is a filler."""
    text = text.strip()
    for pattern in COMPILED_FILLERS:
        if pattern.fullmatch(text) or pattern.match(text):
            return True
    return False


def detect_repetitions(words: list[dict], window: int = 6) -> list[int]:
    """
    Detect repeated word indices in a word list.
    E.g. "it's it's going" → mark second "it's" as filler.

    Args:
        words:  List of word dicts with "word", "start", "end".
        window: How many words back to check for repetition.

    Returns:
        List of indices to remove.
    """
    remove_indices = []
    texts = [w.get("word", "").strip().lower() for w in words]

    for i in range(1, len(texts)):
        # Single word repetition
        if texts[i] == texts[i - 1] and texts[i] not in ("the", "a", ""):
            remove_indices.append(i)
            continue

        # Two-word phrase repetition
        if i >= 2:
            phrase = texts[i - 1] + " " + texts[i]
            prev_phrase = texts[i - 2] + " " + texts[i - 1]
            if phrase == prev_phrase:
                remove_indices.extend([i - 1, i])

    return list(set(remove_indices))


def clean_segments(
    segments: list[dict],
    remove_fillers: bool = True,
    remove_repetitions: bool = True,
) -> tuple[list[dict], list[dict]]:
    """
    Remove filler words and repetitions from Whisper segments.

    Returns:
        (cleaned_segments, removed_intervals)
        removed_intervals: list of {"start": float, "end": float} to cut from video
    """
    cleaned = []
    removed_intervals = []

    for seg in segments:
        words = seg.get("words", [])

        if not words:
            # No word timestamps — do text-level filler removal
            text = seg["text"].strip()
            for pattern in COMPILED_FILLERS:
                text = pattern.sub("", text)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                new_seg = dict(seg)
                new_seg["text"] = text
                cleaned.append(new_seg)
            else:
                removed_intervals.append({
                    "start": seg["start"],
                    "end": seg["end"],
                })
            continue

        # Word-level removal
        remove_idx = set()

        if remove_fillers:
            for i, w in enumerate(words):
                word_text = w.get("word", "").strip()
                if is_filler_word(word_text):
                    remove_idx.add(i)

        if remove_repetitions:
            rep_idx = detect_repetitions(words)
            remove_idx.update(rep_idx)

        # Collect removed time intervals
        for i in remove_idx:
            w = words[i]
            start = w.get("start", seg["start"])
            end = w.get("end", start + 0.1)
            removed_intervals.append({"start": start, "end": end})

        # Keep remaining words
        kept_words = [w for i, w in enumerate(words) if i not in remove_idx]

        if not kept_words:
            removed_intervals.append({"start": seg["start"], "end": seg["end"]})
            continue

        new_seg = dict(seg)
        new_seg["words"] = kept_words
        new_seg["text"] = " ".join(
            w.get("word", "").strip() for w in kept_words
        )
        new_seg["start"] = kept_words[0].get("start", seg["start"])
        new_seg["end"] = kept_words[-1].get("end", seg["end"])
        cleaned.append(new_seg)

    # Merge overlapping/adjacent intervals
    removed_intervals = _merge_intervals(removed_intervals, gap=0.05)
    print(f"[Filler] Removed {len(removed_intervals)} filler/repetition intervals")
    return cleaned, removed_intervals


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


def cut_filler_segments(
    video_path: str,
    output_path: str,
    removed_intervals: list[dict],
    total_duration: float,
    padding: float = 0.05,
) -> str:
    """
    Cut filler word segments from video using FFmpeg concat.

    Args:
        video_path:        Source video path.
        output_path:       Output video path.
        removed_intervals: Time intervals to remove.
        total_duration:    Total video duration.
        padding:           Small buffer to avoid harsh cuts.

    Returns:
        Path to output video.
    """
    if not removed_intervals:
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    # Build keep segments (inverse of removed)
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

    print(f"[Filler] Cutting video: keeping {len(keep)} segments, removing {len(removed_intervals)} fillers")

    # Build FFmpeg filter_complex
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
    print(f"  ✓ Filler-free video saved: {output_path} ({size_mb:.1f} MB)")
    return output_path